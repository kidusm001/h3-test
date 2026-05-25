import json
import sys
import argparse

import h3

RES = 9


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

        if exact or nearby:
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
            })

    matched.sort(key=lambda m: (not m["exact_match"], m["nearest_stop_km"]))
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
    print(f"{'Route':30s} {'Status':12s} {'Driver':20s} {'Vehicle':12s} {'Exact':6s} {'Nearby':7s} {'Dist(km)':10s} {'Nearest Stop'}")
    print("-" * 110)
    for m in matches:
        print(
            f"{m['route_name']:30s} {m['status']:12s} {m['driver']:20s} {m['assigned_vehicle']:12s} "
            f"{'YES' if m['exact_match'] else 'no':6s} {m['nearby_match_count']:3d}      "
            f"{m['nearest_stop_km']:8.3f}  {m['nearest_stop']}"
        )


if __name__ == "__main__":
    main()
