import json
import sys
import argparse

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


def load_routes(path="route_data.json"):
    with open(path) as f:
        return json.load(f)["routes"]


def candidate_matches(lat, lng, routes, k=1):
    cell = h3.latlng_to_cell(lat, lng, RES)
    ring = set(h3.grid_disk(cell, k))
    matched = []

    for route in routes:
        route_cells = set(route["h3_cells"])
        exact = route_cells & {cell}
        nearby = route_cells & (ring - {cell})

        stop_based = bool(exact or nearby)

        if stop_based:
            stops = route["route_members"]
            min_dist = min(
                h3.great_circle_distance((lat, lng), (s["lat"], s["lng"]), unit="km")
                for s in stops
            )
            matched.append({
                "route_name": route["route_name"],
                "status": route["status"],
                "assigned_vehicle": route["assigned_vehicle"],
                "driver": route["driver"],
                "exact_match": len(exact) > 0,
                "nearby_match_count": len(nearby),
                "nearest_stop_km": round(min_dist, 3),
                "nearest_stop": min(
                    stops,
                    key=lambda s: h3.great_circle_distance(
                        (lat, lng), (s["lat"], s["lng"]), unit="km"
                    ),
                )["name"],
                "matched_by": "stop",
            })
        else:
            path_cells = interpolate_path_cells(route)
            if path_cells & ring:
                stops = route["route_members"]
                min_dist = min(
                    h3.great_circle_distance((lat, lng), (s["lat"], s["lng"]), unit="km")
                    for s in stops
                ) if stops else 999.0
                matched.append({
                    "route_name": route["route_name"],
                    "status": route["status"],
                    "assigned_vehicle": route["assigned_vehicle"],
                    "driver": route["driver"],
                    "exact_match": False,
                    "nearby_match_count": 0,
                    "nearest_stop_km": round(min_dist, 3),
                    "nearest_stop": min(
                        stops,
                        key=lambda s: h3.great_circle_distance(
                            (lat, lng), (s["lat"], s["lng"]), unit="km"
                        ),
                    )["name"] if stops else "N/A",
                    "matched_by": "path",
                })

    matched.sort(key=lambda m: (not m["exact_match"], {"path": 2, "stop": 1}.get(m.get("matched_by", "stop"), 1), m["nearest_stop_km"]))
    return matched


def main():
    parser = argparse.ArgumentParser(description="Assign a candidate to the best matching route using h3.")
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lng", type=float, required=True)
    parser.add_argument("--k", type=int, default=1, help="k-ring radius (default: 1)")
    parser.add_argument("--file", default="route_data.json")
    args = parser.parse_args()

    routes = load_routes(args.file)
    matches = candidate_matches(args.lat, args.lng, routes, args.k)

    if not matches:
        print("No matching routes found.")
        return

    print(f"Candidate at ({args.lat}, {args.lng}) → h3 cell: {h3.latlng_to_cell(args.lat, args.lng, RES)}")
    print()
    print(f"{'Route':30s} {'Status':12s} {'Driver':20s} {'Vehicle':12s} {'Match':10s} {'Dist(km)':10s} {'Nearest Stop'}")
    print("-" * 110)
    for m in matches:
        match_type = m.get("matched_by", "stop")
        match_label = "STOP" if match_type == "stop" else "PATH"
        print(
            f"{m['route_name']:30s} {m['status']:12s} {m['driver']:20s} {m['assigned_vehicle']:12s} "
            f"{match_label:10s} {m['nearest_stop_km']:8.3f}  {m['nearest_stop']}"
        )


if __name__ == "__main__":
    main()
