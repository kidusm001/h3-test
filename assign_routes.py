import json
import sys
import argparse
import urllib.request

import h3

RES = 9


def geometry_to_cells(geometry, res=RES):
    cells = set()
    for lat, lng in geometry:
        cells.add(h3.latlng_to_cell(lat, lng, res))
    return cells


def interpolate_path_cells(route, res=RES):
    cells = set()
    stops = route.get("route_members", [])
    if len(stops) < 2:
        if stops:
            cells.add(h3.latlng_to_cell(stops[0]["lat"], stops[0]["lng"], res))
        return cells
    for i in range(len(stops) - 1):
        lat1, lng1 = stops[i]["lat"], stops[i]["lng"]
        lat2, lng2 = stops[i+1]["lat"], stops[i+1]["lng"]
        dist_km = h3.great_circle_distance((lat1, lng1), (lat2, lng2), unit="km")
        num_steps = max(2, int(dist_km / 0.05))
        for j in range(num_steps + 1):
            frac = j / num_steps
            lat = lat1 + (lat2 - lat1) * frac
            lng = lng1 + (lng2 - lng1) * frac
            cells.add(h3.latlng_to_cell(lat, lng, res))
    return cells


def get_boundary_coords(cell_index):
    try:
        boundary = h3.cell_to_boundary(cell_index)
        return [[lat, lng] for lat, lng in boundary]
    except Exception:
        return []


def compute_stop_score(ring_distance, haversine_km, k, max_dist_km):
    ring_score = 1.0 - (ring_distance / (k + 1))
    dist_score = 1.0 - min(haversine_km / max_dist_km, 1.0)
    return round((ring_score * 0.6 + dist_score * 0.4) * 0.5, 4)


def compute_path_score(overlap_ratio, nearest_stop_km, max_dist_km):
    dist_score = max(0.0, 1.0 - (nearest_stop_km / max_dist_km))
    return round(overlap_ratio * 0.7 + dist_score * 0.3, 4)


def fetch_osrm_route(coords):
    if len(coords) < 2:
        return coords
    coords_str = ";".join([f"{lng},{lat}" for lat, lng in coords])
    url = f"http://router.project-osrm.org/route/v1/driving/{coords_str}?overview=full&geometries=geojson"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "H3-Route-Matcher/1.0"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            if res_data.get("code") == "Ok" and res_data.get("routes"):
                geojson_coords = res_data["routes"][0]["geometry"]["coordinates"]
                return [[lat, lng] for lng, lat in geojson_coords]
    except Exception as e:
        print(f"Error fetching OSRM route: {e}")
    return coords


def check_red_zone(lat, lng, red_zone_cells, res=RES):
    if not red_zone_cells:
        return False
    red_zones_by_res = {}
    for cz in red_zone_cells:
        cz_res = h3.get_resolution(cz)
        red_zones_by_res.setdefault(cz_res, set()).add(cz)
    for rz_res, cells_at_res in red_zones_by_res.items():
        if h3.latlng_to_cell(lat, lng, rz_res) in cells_at_res:
            return True
    return False


def match_candidate(
    lat, lng, routes,
    k=1, res=RES, max_dist_km=1.5,
    red_zone_cells=None,
    osrm_geometry_cache=None
):
    candidate_cell = h3.latlng_to_cell(lat, lng, res)

    if check_red_zone(lat, lng, red_zone_cells, res):
        return {
            "rejected": True,
            "reason": "Candidate location is in a restricted area",
            "candidate_cell": candidate_cell,
            "matches": [],
        }

    ring_cells = list(h3.grid_disk(candidate_cell, k))
    ring_set = set(ring_cells)

    routes_summary = {}

    # Stop-based matching
    for route in routes:
        for stop in route.get("route_members", []):
            stop_hex = h3.latlng_to_cell(stop["lat"], stop["lng"], res)
            if stop_hex not in ring_set:
                continue

            distance_km = h3.great_circle_distance(
                (lat, lng), (stop["lat"], stop["lng"]), unit="km"
            )
            if distance_km > max_dist_km:
                continue

            r_name = route["route_name"]
            if r_name not in routes_summary:
                routes_summary[r_name] = {
                    "route_name": r_name,
                    "status": route["status"],
                    "assigned_vehicle": route["assigned_vehicle"],
                    "driver": route["driver"],
                    "exact_match": False,
                    "nearby_match_count": 0,
                    "nearest_stop_km": distance_km,
                    "nearest_stop": stop["name"],
                    "matched_by": "stop",
                    "score": 0.0,
                }

            summary = routes_summary[r_name]
            is_exact = stop_hex == candidate_cell
            ring_distance = h3.grid_distance(candidate_cell, stop_hex)

            if is_exact:
                summary["exact_match"] = True
            else:
                summary["nearby_match_count"] += 1

            if distance_km < summary["nearest_stop_km"]:
                summary["nearest_stop_km"] = distance_km
                summary["nearest_stop"] = stop["name"]

            stop_score = compute_stop_score(
                ring_distance, distance_km, k, max_dist_km
            )
            if stop_score > summary["score"]:
                summary["score"] = stop_score

    # Path-based matching
    cache = osrm_geometry_cache if osrm_geometry_cache is not None else {}
    for route in routes:
        r_name = route["route_name"]
        if r_name in routes_summary:
            continue

        geom = route.get("osrm_geometry") or cache.get(r_name)
        if geom:
            path_cells = geometry_to_cells(geom, res)
        else:
            coords = [[s["lat"], s["lng"]] for s in route.get("route_members", [])]
            geom = fetch_osrm_route(coords)
            cache[r_name] = geom
            path_cells = geometry_to_cells(geom, res)

        overlap_cells = path_cells & ring_set
        if overlap_cells:
            total_weight = sum(
                1.0 / (h3.grid_distance(candidate_cell, c) + 1) for c in ring_cells
            )
            overlap_weight = sum(
                1.0 / (h3.grid_distance(candidate_cell, c) + 1) for c in overlap_cells
            )
            weighted_overlap_ratio = overlap_weight / total_weight if total_weight > 0 else 0

            stops = route.get("route_members", [])
            nearest_stop_km = min(
                h3.great_circle_distance((lat, lng), (s["lat"], s["lng"]), unit="km")
                for s in stops
            ) if stops else 999.0
            nearest_stop = min(
                stops,
                key=lambda s: h3.great_circle_distance(
                    (lat, lng), (s["lat"], s["lng"]), unit="km"
                ),
            )["name"] if stops else "N/A"

            routes_summary[r_name] = {
                "route_name": r_name,
                "status": route["status"],
                "assigned_vehicle": route["assigned_vehicle"],
                "driver": route["driver"],
                "exact_match": False,
                "nearby_match_count": 0,
                "nearest_stop_km": round(nearest_stop_km, 3),
                "nearest_stop": nearest_stop,
                "matched_by": "path",
                "score": compute_path_score(
                    weighted_overlap_ratio, nearest_stop_km, max_dist_km
                ),
            }

    matches = list(routes_summary.values())
    matches.sort(key=lambda m: (-m["score"], m["nearest_stop_km"]))

    return {
        "rejected": False,
        "candidate_cell": candidate_cell,
        "matches": matches,
    }


def main():
    parser = argparse.ArgumentParser(description="Assign a candidate to the best matching route using h3.")
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lng", type=float, required=True)
    parser.add_argument("--k", type=int, default=1, help="k-ring radius (default: 1)")
    parser.add_argument("--res", type=int, default=RES, help="H3 resolution (default: 9)")
    parser.add_argument("--max-dist-km", type=float, default=1.5, help="Max walking distance in km (default: 1.5)")
    parser.add_argument("--routes", type=str, help="JSON string of routes list (pipe from stdin if omitted)")
    parser.add_argument("--red-zones", type=str, help="JSON string of red zone cell list")
    args = parser.parse_args()

    if args.routes:
        routes = json.loads(args.routes)
    else:
        routes = json.loads(sys.stdin.read())

    red_zone_cells = json.loads(args.red_zones) if args.red_zones else None

    result = match_candidate(
        args.lat, args.lng, routes,
        k=args.k, res=args.res, max_dist_km=args.max_dist_km,
        red_zone_cells=red_zone_cells,
    )

    if result["rejected"]:
        print(f"REJECTED: Candidate at ({args.lat}, {args.lng}) is in a restricted area")
        return

    print(f"Candidate at ({args.lat}, {args.lng}) \u2192 h3 cell: {result['candidate_cell']}")
    print()
    print(f"{'Route':30s} {'Status':12s} {'Driver':20s} {'Vehicle':12s} {'Match':10s} {'Score':8s} {'Dist(km)':10s} {'Nearest Stop'}")
    print("-" * 120)
    for m in result["matches"]:
        match_label = m.get("matched_by", "stop").upper()
        print(
            f"{m['route_name']:30s} {m['status']:12s} {m['driver']:20s} {m['assigned_vehicle']:12s} "
            f"{match_label:10s} {m['score']:8.4f} {m['nearest_stop_km']:8.3f}  {m['nearest_stop']}"
        )


if __name__ == "__main__":
    main()
