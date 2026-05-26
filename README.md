# h3-test — Spatial Route Matching & Dispatch Explainer

**h3-test** is a full-stack spatial route matching tool that uses Uber's [H3 hexagonal hierarchical geospatial indexing system](https://h3geo.org/) to demonstrate how a dispatch system can match a candidate location (e.g., a rider or delivery) to the best available transport route in real time.

Built for Addis Ababa, Ethiopia, with 10 realistic transport routes, it serves as both:

- An **educational reference** for H3-based spatial matching in logistics/dispatch workflows
- A **functional prototype** with a CLI tool, REST API, and interactive map-based UI

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [How the Matching Algorithm Works](#how-the-matching-algorithm-works)
- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)
- [Usage](#usage)
  - [Web UI](#web-ui)
  - [CLI Tool](#cli-tool)
  - [API Endpoints](#api-endpoints)
- [Data Format](#data-format)
- [Project Structure](#project-structure)
- [Configuration](#configuration)
- [Development](#development)
- [License](#license)

---

## Architecture Overview

```
┌──────────────┐     HTTP      ┌──────────────────┐
│  React/TS    │ ◄──────────► │  FastAPI Server   │
│  Frontend    │    (REST)     │  (Python 3.13)    │
│  (Vite/Map)  │               │                  │
└──────────────┘               │  ┌────────────┐  │
                               │  │ H3 Library  │  │
                               │  └────────────┘  │
┌──────────────┐     CLI       │  ┌────────────┐  │
│ assign_routes│ ◄──────────► │  │ route_data  │  │
│ .py          │               │  │ .json       │  │
└──────────────┘               │  └────────────┘  │
                               │  ┌────────────┐  │
                               │  │ OSRM Router│  │
                               │  │ (external)  │  │
                               │  └────────────┘  │
                               └──────────────────┘
```

- **Frontend**: React 19 + TypeScript + Leaflet, served via Vite (dev) or FastAPI static files (prod)
- **Backend**: FastAPI (Python) exposing REST endpoints for routes and matching logic
- **Algorithm**: H3 spatial indexing for cell lookups + Haversine distance scoring + OSRM path-based fallback
- **Data**: 10 predefined transport routes in Addis Ababa, stored as JSON

---

## How the Matching Algorithm Works

The core matching pipeline operates in two phases:

### Phase 1: Candidate Geocoding & Search Area Expansion

```
Candidate (lat, lng)
        │
        ▼
  H3 Cell @ resolution 9
        │
        ▼
  K-Ring expansion (ring radius k)
        │
        ▼
  Set of H3 cells = Search Area
```

1. **Convert** the candidate's latitude/longitude to an H3 cell index at configurable resolution (default: 9)
2. **Expand** the search area using H3 `k-ring()`, producing a pool of neighboring cells (default radius: 1 → 7 cells)
3. **Generate** a mock SQL query demonstrating how a MariaDB/MySQL database with H3 columns would perform this lookup

### Phase 2: Route Matching

```
For each route:
        │
        ├── Check if any route stop's H3 cell is in the k-ring
        │         │
        │         ├── YES → "stop" match (score by Haversine distance)
        │         │
        │         └── NO  → Check if route's OSRM driving path
        │                     passes through the k-ring
        │                       │
        │                       └── YES → "path" match
        │
        ▼
  Return matched routes sorted:
    1. Exact cell matches first
    2. Then by match type ("stop" > "path")
    3. Then by nearest distance (ascending)
```

**Stop-based matching**: If a route stop's H3 cell falls within the k-ring, it scores a match with the candidate. The distance between the candidate and the stop is computed using the **Haversine formula**.

**Path-based fallback**: If no stops are in range, the algorithm requests the route's actual driving geometry from the **OSRM** (Open Source Routing Machine) API. It converts the road-following path coordinates to H3 cells and checks for overlap with the search ring. This ensures routes that *drive through* the area (but don't have a stop there) are still discoverable.

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python ≥3.13, FastAPI, Uvicorn |
| **Spatial Indexing** | H3 v4 (Uber's hex grid) |
| **Path Geometry** | OSRM (router.project-osrm.org) |
| **Frontend** | React 19, TypeScript 6, Vite 8 |
| **Mapping** | Leaflet 1.9 (CARTO dark basemap) |
| **Data** | JSON (static route definitions) |
| **Package Mgmt** | uv (Python), npm (frontend) |

---

## Getting Started

### Prerequisites

- Python ≥ 3.13
- [uv](https://github.com/astral-sh/uv) (Python package manager) or pip
- Node.js ≥ 18 (for frontend development)

### Backend Setup

```bash
# Clone the repository
git clone https://github.com/your-org/h3-test.git
cd h3-test

# Create and activate virtual environment
uv venv
source .venv/bin/activate

# Install Python dependencies
uv sync
# OR: pip install -e .

# Start the backend server
uvicorn server:app --reload --port 8001
```

The API will be available at `http://localhost:8001`.

### Frontend Setup (Development)

```bash
cd visualizer

# Install dependencies
npm install

# Start development server
npm run dev
```

The frontend dev server runs on `http://localhost:5173` and proxies `/api` requests to `http://localhost:8001`.

### Production Build

```bash
cd visualizer
npm run build
```

This compiles the frontend to `visualizer/dist/`, which is served automatically by the FastAPI server when you run it (no separate frontend server needed).

---

## Usage

### Web UI

Once both servers are running, open `http://localhost:5173` (dev) or `http://localhost:8001` (prod).

1. **Click on the map** or enter coordinates to set a candidate location
2. **Adjust parameters**: H3 resolution (6–12), k-ring radius (0–3), max distance (km)
3. **Toggle map layers**: cells, routes, database hits, trail lines
4. **Review matching results**: the sidebar lists matched routes sorted by proximity, with driver/vehicle info and match type (`stop` vs `path`)
5. **Switch to the SQL Explainer tab** to see the step-by-step spatial query construction
6. **Edit routes** via the "Edit Route DB" modal to add/modify/remove stops

### CLI Tool

```bash
python assign_routes.py --lat 9.008 --lng 38.780 --k 1
```

Arguments:

| Argument | Default | Description |
|---|---|---|
| `--lat` | required | Candidate latitude |
| `--lng` | required | Candidate longitude |
| `--k` | 1 | K-ring expansion radius (0–3) |
| `--file` | `route_data.json` | Path to route data JSON |

Output: A formatted table showing matching routes with driver, vehicle, distance, and match type.

### API Endpoints

#### `GET /api/routes`

Returns all route definitions enriched with OSRM road geometry (cached in memory).

```json
[
  {
    "name": "Morning-Bole-001",
    "type": "Drop-off, Short",
    "driver": "Abebe Kebede",
    "vehicle_type": "Sedan",
    "stops": [ ... ],
    "geometry": [[9.002, 38.712], [9.031, 38.754], ...]
  },
  ...
]
```

#### `POST /api/routes`

Update the route data file with new/edited routes.

**Body**: Array of route objects (replaces the entire data file).

#### `GET /api/match?lat=9.008&lng=38.780&res=9&k=1&max_dist_km=2.0`

Execute the matching algorithm.

| Query Param | Default | Description |
|---|---|---|
| `lat` | — | Candidate latitude |
| `lng` | — | Candidate longitude |
| `res` | 9 | H3 resolution (6–12) |
| `k` | 1 | K-ring radius (0–3) |
| `max_dist_km` | 2.0 | Maximum stop distance filter |

**Response**:

```json
{
  "candidate_cell": "893d4a3280fffff",
  "k_ring_cells": 7,
  "matched_routes": [
    {
      "name": "Morning-Bole-001",
      "driver": "Abebe Kebede",
      "vehicle_type": "Sedan",
      "distance_km": 0.85,
      "matched_by": "stop",
      "matched_stop": "Bole Atlas",
      "nearest_stop_lat": 9.012,
      "nearest_stop_lng": 38.785
    }
  ],
  "sql_query": "SELECT ...",
  "database_hits": [
    {
      "stop_name": "Bole Atlas",
      "route_name": "Morning-Bole-001",
      "h3_index": "893d4a3280fffff",
      "matched": true,
      "distance_km": 0.85
    }
  ]
}
```

---

## Data Format

Routes are stored in `route_data.json`. Each route has:

```json
{
  "name": "Route-Name-001",
  "type": "Drop-off, Short | Pick-UP, Short | Drop-off, Long | Pick-UP, Long",
  "driver": "Driver Name",
  "vehicle_type": "Sedan | Minibus | Truck",
  "status": "ACTIVE | PENDING | INACTIVE | CANCELLED",
  "vehicle_number": "AA-1234",
  "stops": [
    {
      "name": "Stop Name",
      "lat": 9.008,
      "lng": 38.780,
      "cell": "893d4a3280fffff"
    }
  ],
  "h3_resolution": 9
}
```

All 10 routes center on Addis Ababa with stops at real locations (Bole, Merkato, Piazza, Megenagna, CMC, Saris, Kaliti, Lideta, etc.).

---

## Project Structure

```
h3-test/
├── server.py            # FastAPI backend — routes, matching, OSRM
├── assign_routes.py     # CLI tool for command-line matching
├── main.py              # Placeholder entry point
├── route_data.json      # 10 Addis Ababa transport routes
├── pyproject.toml       # Python project config & dependencies
├── uv.lock              # Python dependency lock file
├── .python-version      # Python version: 3.13
├── .gitignore           # Git ignore rules
├── agent-talks.md       # Development notes / AI session log
└── visualizer/          # React + TypeScript frontend
    ├── src/
    │   ├── main.tsx           # React entry point
    │   ├── App.tsx            # Main app — dispatch UI, SQL explainer, controls
    │   ├── components/
    │   │   └── Map.tsx        # Leaflet map — routes, cells, markers, layers
    │   ├── types.ts           # TypeScript type definitions
    │   └── index.css          # Dark-themed UI styles (741 lines)
    ├── index.html             # Vite HTML entry
    ├── vite.config.ts         # Vite config with API proxy
    ├── package.json           # Frontend dependencies & scripts
    ├── tsconfig*.json         # TypeScript configuration
    └── dist/                  # Production build output
```

---

## Configuration

### H3 Resolution

The algorithm uses H3 resolution 9 by default, which produces cells roughly **0.1–0.2 km²** at Addis Ababa's latitude. This balances precision with search performance. Resolution can be adjusted via the UI (6–12) or `--res` in the CLI:

| Resolution | Approx. cell area (Addis Ababa) |
|---|---|
| 6 | ~37 km² |
| 8 | ~0.7 km² |
| 9 | ~0.1 km² |
| 10 | ~0.015 km² |
| 12 | ~0.0003 km² |

### K-Ring Radius

Controls how many rings of neighboring cells to include in the search area. A radius of `1` yields 7 cells (center + 6 neighbors); radius `2` yields 19 cells, etc.

### Max Distance

Routes with stops farther than `max_dist_km` from the candidate are filtered out. Default: 2 km.

---

## Development

### Running Tests

There are no formal test suites yet. To validate changes:

```bash
# Backend — run the CLI tool against known coordinates
python assign_routes.py --lat 9.008 --lng 38.780

# Frontend — type-check
cd visualizer && npx tsc --noEmit

# Lint
cd visualizer && npm run lint
```

### Adding Routes

Edit `route_data.json` directly, or use the "Edit Route DB" modal in the UI. For each stop, compute the H3 cell using:

```python
import h3
cell = h3.latlng_to_cell(lat, lng, res=9)
```

### Caching

OSRM road geometry is cached in memory on the FastAPI server (`_geom_cache` dict). Restart the server to clear the cache and re-fetch geometries.

---

## License

This project is for educational and demonstration purposes. Where not otherwise specified, it is available under the MIT License.
