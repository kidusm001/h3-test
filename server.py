import os
import json
import urllib.request
import h3
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import List, Optional

app = FastAPI(title="H3 Route Matcher SQL Explainer API")

# Enable CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_PATH = os.path.join(os.path.dirname(__file__), "route_data.json")


def load_routes_data():
    if not os.path.exists(DATA_PATH):
        return {"routes": []}
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_routes_data(data):
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def geometry_to_cells(geometry: list, res: int) -> set:
    cells = set()
    for pt in geometry:
        lat, lng = pt[0], pt[1]
        cells.add(h3.latlng_to_cell(lat, lng, res))
    return cells


def interpolate_path_cells(route: dict, res: int) -> set:
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


def get_boundary_coords(cell_index: str) -> List[List[float]]:
    try:
        boundary = h3.cell_to_boundary(cell_index)
        return [[lat, lng] for lat, lng in boundary]
    except Exception:
        return []


def compute_stop_score(ring_distance: int, haversine_km: float, k: int, max_dist_km: float) -> float:
    ring_score = 1.0 - (ring_distance / (k + 1))
    dist_score = 1.0 - min(haversine_km / max_dist_km, 1.0)
    return round((ring_score * 0.6 + dist_score * 0.4) * 0.5, 4)


def compute_path_score(overlap_ratio: float, nearest_stop_km: float, max_dist_km: float) -> float:
    dist_score = max(0.0, 1.0 - (nearest_stop_km / max_dist_km))
    return round(overlap_ratio * 0.7 + dist_score * 0.3, 4)


def fetch_osrm_route(coords: list) -> list:
    if len(coords) < 2:
        return coords
    coords_str = ";".join([f"{lng},{lat}" for lat, lng in coords])
    url = f"http://router.project-osrm.org/route/v1/driving/{coords_str}?overview=full&geometries=geojson"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "H3-Route-Matcher-Visualizer/1.0"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            if res_data.get("code") == "Ok" and res_data.get("routes"):
                geojson_coords = res_data["routes"][0]["geometry"]["coordinates"]
                return [[lat, lng] for lng, lat in geojson_coords]
    except Exception as e:
        print(f"Error fetching OSRM route: {e}")
    return coords


# Models for API validation
class Stop(BaseModel):
    stop_order: int
    name: str
    lat: float
    lng: float
    address: str
    estimated_arrival: str
    h3_index: str


class Route(BaseModel):
    route_name: str
    route_range: str
    route_type: str
    assigned_to: str
    vendor: Optional[str] = None
    vehicle_category: str
    driver: str
    branch: str
    calculated_distance: float
    estimated_cost: float
    status: str
    assigned_vehicle: str
    route_members: List[Stop]
    h3_cells: List[str]
    osrm_geometry: Optional[List[List[float]]] = None
    vehicle_capacity: Optional[int] = None


class RoutesPayload(BaseModel):
    routes: List[Route]
    red_zones: Optional[List[str]] = None


OSRM_GEOMETRY_CACHE = {}


class RedZonePayload(BaseModel):
    red_zones: List[str]


@app.get("/api/cell-info")
def cell_info(
    lat: float = Query(...),
    lng: float = Query(...),
    res: int = Query(9),
):
    cell = h3.latlng_to_cell(lat, lng, res)
    return {"index": cell, "boundary": get_boundary_coords(cell)}


@app.get("/api/red-zones")
def get_red_zones():
    try:
        data = load_routes_data()
        rz_list = data.get("red_zones", [])
        cells = []
        for cz in rz_list:
            try:
                cells.append({"index": cz, "boundary": get_boundary_coords(cz)})
            except Exception:
                cells.append({"index": cz, "boundary": []})
        return {"red_zones": rz_list, "cells": cells}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/routes")
def get_routes():
    try:
        data = load_routes_data()
        routes = data.get("routes", [])
        for route in routes:
            r_name = route["route_name"]
            if r_name not in OSRM_GEOMETRY_CACHE:
                coords = [[s["lat"], s["lng"]] for s in route.get("route_members", [])]
                actual_path = fetch_osrm_route(coords)
                OSRM_GEOMETRY_CACHE[r_name] = actual_path
            route["osrm_geometry"] = OSRM_GEOMETRY_CACHE[r_name]
        return {"routes": routes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/red-zones")
def save_red_zones(payload: RedZonePayload):
    try:
        data = load_routes_data()
        data["red_zones"] = payload.red_zones
        save_routes_data(data)
        return {"status": "success", "message": "Red zones saved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/routes")
def save_routes(payload: RoutesPayload):
    try:
        data = payload.model_dump()
        if payload.red_zones is None:
            existing = load_routes_data()
            data["red_zones"] = existing.get("red_zones", [])
        save_routes_data(data)
        return {"status": "success", "message": "Routes saved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/cells-in-bounds")
def cells_in_bounds(data: dict):
    north = data.get("north")
    south = data.get("south")
    east = data.get("east")
    west = data.get("west")
    res = data.get("res", 9)

    if any(v is None for v in [north, south, east, west]):
        raise HTTPException(status_code=400, detail="north, south, east, west are required")

    poly = h3.LatLngPoly([
        (north, west),
        (north, east),
        (south, east),
        (south, west),
        (north, west),
    ])

    try:
        cells = list(h3.polygon_to_cells(poly, res))
        if len(cells) > 10000:
            raise HTTPException(status_code=400, detail=f"Too many cells ({len(cells)}). Maximum is 10000.")
    except HTTPException:
        raise
    except Exception:
        centroid_lat = (north + south) / 2
        centroid_lng = (east + west) / 2
        cells = [h3.latlng_to_cell(centroid_lat, centroid_lng, res)]

    result = []
    for cell in cells:
        try:
            boundary = get_boundary_coords(cell)
            result.append({"index": cell, "boundary": boundary})
        except Exception:
            result.append({"index": cell, "boundary": []})

    return {"cells": result}


@app.get("/api/match")
def match_candidate(
    lat: float = Query(..., description="Latitude of the candidate"),
    lng: float = Query(..., description="Longitude of the candidate"),
    k: int = Query(1, ge=0, description="k-ring radius"),
    res: int = Query(9, ge=1, le=15, description="H3 resolution"),
    max_dist_km: float = Query(1.5, ge=0.1, le=10.0, description="Max walking distance (km)"),
):
    try:
        routes_data = load_routes_data()
        routes = routes_data.get("routes", [])

        # Exclude fully loaded routes — no capacity for new passengers
        routes = [
            r for r in routes
            if not (
                r.get("vehicle_capacity") and
                len(r.get("route_members", [])) >= r["vehicle_capacity"]
            )
        ]

        # Step 2: Index Candidate (Convert candidate coords to H3 Cell)
        candidate_cell = h3.latlng_to_cell(lat, lng, res)
        candidate_boundary = get_boundary_coords(candidate_cell)

        # Red Zone Check — works at any resolution the cells were saved at
        red_zone_cells_raw = routes_data.get("red_zones", [])
        # Group red zone cells by their actual resolution so we check correctly
        red_zones_by_res = {}
        for cz in red_zone_cells_raw:
            try:
                cz_res = h3.get_resolution(cz)
                red_zones_by_res.setdefault(cz_res, set()).add(cz)
            except Exception:
                pass

        red_zone_cells = []
        for cz in red_zone_cells_raw:
            try:
                cz_boundary = get_boundary_coords(cz)
                red_zone_cells.append({"index": cz, "boundary": cz_boundary})
            except Exception:
                pass

        rejected = False
        for rz_res_tmp, cells_at_res in red_zones_by_res.items():
            if h3.latlng_to_cell(lat, lng, rz_res_tmp) in cells_at_res:
                rejected = True
                break

        if rejected:
            return {
                "rejected": True,
                "reason": "Candidate location is in a restricted area",
                "candidate_cell": {
                    "index": candidate_cell,
                    "boundary": candidate_boundary
                },
                "red_zone_cells": red_zone_cells
            }

        # Step 3: Grid Ring Expansion (Search Pool)
        ring_cells = list(h3.grid_disk(candidate_cell, k))
        ring_set = set(ring_cells)

        k_ring_data = []
        for cell in ring_cells:
            k_ring_data.append({
                "index": cell,
                "boundary": get_boundary_coords(cell)
            })

        # Step 4: Mock MariaDB SQL Query generation
        hex_list_str = ", ".join([f"'{c}'" for c in ring_cells])
        mock_sql = f"SELECT route_name, stop_name, lat, lng, h3_index\nFROM route_stops\nWHERE h3_index IN ({hex_list_str});"

        # Relational database lookup simulation
        db_hits = []
        for route in routes:
            for stop in route.get("route_members", []):
                # Calculate the stop's hex at the query resolution dynamically
                stop_hex = h3.latlng_to_cell(stop["lat"], stop["lng"], res)
                
                # Check if stop hex index is in the candidate search pool
                if stop_hex in ring_set:
                    # Step 5: Haversine scoring
                    distance_km = h3.great_circle_distance((lat, lng), (stop["lat"], stop["lng"]), unit="km")
                    passed = distance_km <= max_dist_km
                    is_exact = stop_hex == candidate_cell
                    ring_distance = h3.grid_distance(candidate_cell, stop_hex)
                    
                    db_hits.append({
                        "route_name": route["route_name"],
                        "stop_name": stop["name"],
                        "lat": stop["lat"],
                        "lng": stop["lng"],
                        "stop_h3": stop_hex,
                        "distance_km": round(distance_km, 3),
                        "passed": passed,
                        "is_exact_cell": is_exact,
                        "ring_distance": ring_distance,
                    })

        # Group valid matches by route to structure route assignment results
        routes_summary = {}
        for hit in db_hits:
            if not hit["passed"]:
                continue
                
            r_name = hit["route_name"]
            route_ref = next((r for r in routes if r["route_name"] == r_name), None)
            if not route_ref:
                continue

            if r_name not in routes_summary:
                routes_summary[r_name] = {
                    "route_name": r_name,
                    "status": route_ref["status"],
                    "assigned_vehicle": route_ref["assigned_vehicle"],
                    "driver": route_ref["driver"],
                    "exact_match": False,
                    "nearby_match_count": 0,
                    "nearest_stop_km": hit["distance_km"],
                    "nearest_stop": hit["stop_name"],
                    "exact_cells": [],
                    "nearby_cells": [],
                    "matched_by": "stop",
                    "score": 0.0,
                }
            
            summary = routes_summary[r_name]
            
            # Update matching statistics
            if hit["is_exact_cell"]:
                summary["exact_match"] = True
                summary["exact_cells"].append({
                    "index": hit["stop_h3"],
                    "boundary": get_boundary_coords(hit["stop_h3"])
                })
            else:
                summary["nearby_match_count"] += 1
                summary["nearby_cells"].append({
                    "index": hit["stop_h3"],
                    "boundary": get_boundary_coords(hit["stop_h3"])
                })

            if hit["distance_km"] < summary["nearest_stop_km"]:
                summary["nearest_stop_km"] = hit["distance_km"]
                summary["nearest_stop"] = hit["stop_name"]

            # Compute score for this stop and keep the best per route
            stop_score = compute_stop_score(
                hit["ring_distance"], hit["distance_km"], k, max_dist_km
            )
            if stop_score > summary["score"]:
                summary["score"] = stop_score

        # Collect path-match geometry cells for map visualization
        path_pass_cells = []

        # Path-based matching: check routes whose actual driving path passes through the
        # k-ring even though no stop is within range — uses OSRM road geometry when
        # available for accuracy, falls back to straight-line interpolation between stops
        for route in routes:
            r_name = route["route_name"]
            if r_name in routes_summary:
                continue

            # Try OSRM road geometry first (cached from /api/routes or freshly fetched)
            geom = route.get("osrm_geometry") or OSRM_GEOMETRY_CACHE.get(r_name)
            if geom:
                path_cells = geometry_to_cells(geom, res)
            else:
                coords = [[s["lat"], s["lng"]] for s in route.get("route_members", [])]
                geom = fetch_osrm_route(coords)
                OSRM_GEOMETRY_CACHE[r_name] = geom
                path_cells = geometry_to_cells(geom, res)

            overlap_cells = path_cells & ring_set
            if overlap_cells:
                # Weighted overlap: each overlapping cell counts proportionally
                # to how close its ring is to the candidate (ring 0 = 1.0, ring k = 1/(k+1))
                total_weight = sum(
                    1.0 / (h3.grid_distance(candidate_cell, c) + 1) for c in ring_cells
                )
                overlap_weight = sum(
                    1.0 / (h3.grid_distance(candidate_cell, c) + 1) for c in overlap_cells
                )
                weighted_overlap_ratio = overlap_weight / total_weight if total_weight > 0 else 0
                # Route path passes through candidate area — find nearest stop regardless
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

                overlap_geom = [{
                    "index": c,
                    "boundary": get_boundary_coords(c)
                } for c in overlap_cells]
                path_pass_cells.extend(overlap_geom)

                routes_summary[r_name] = {
                    "route_name": r_name,
                    "status": route["status"],
                    "assigned_vehicle": route["assigned_vehicle"],
                    "driver": route["driver"],
                    "exact_match": False,
                    "nearby_match_count": 0,
                    "nearest_stop_km": round(nearest_stop_km, 3),
                    "nearest_stop": nearest_stop,
                    "exact_cells": [],
                    "nearby_cells": [],
                    "matched_by": "path",
                    "path_overlap_cells": overlap_geom,
                    "score": compute_path_score(
                        weighted_overlap_ratio, nearest_stop_km, max_dist_km
                    ),
                }

        # Attach load info to each route match for frontend display
        matches = list(routes_summary.values())
        for m in matches:
            route_ref = next((r for r in routes if r["route_name"] == m["route_name"]), None)
            if route_ref:
                m["current_load"] = len(route_ref.get("route_members", []))
                m["vehicle_capacity"] = route_ref.get("vehicle_capacity")

        # Sort summary results by score descending, then distance as tiebreaker
        matches.sort(key=lambda m: (-m["score"], m["nearest_stop_km"]))

        return {
            "sql_query": mock_sql,
            "candidate_cell": {
                "index": candidate_cell,
                "boundary": candidate_boundary
            },
            "k_ring_cells": k_ring_data,
            "db_hits": db_hits,
            "matches": matches,
            "path_pass_cells": path_pass_cells,
            "red_zone_cells": red_zone_cells
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Serve production build of Vite frontend if it exists
dist_path = os.path.join(os.path.dirname(__file__), "visualizer", "dist")
if os.path.exists(dist_path):
    app.mount("/", StaticFiles(directory=dist_path, html=True), name="static")

