export interface Stop {
  stop_order: number;
  name: string;
  lat: number;
  lng: number;
  address: string;
  estimated_arrival: string;
  h3_index: string;
}

export interface Route {
  route_name: string;
  route_range: string;
  route_type: string;
  assigned_to: string;
  vendor: string | null;
  vehicle_category: string;
  driver: string;
  branch: string;
  calculated_distance: number;
  estimated_cost: number;
  status: string;
  assigned_vehicle: string;
  route_members: Stop[];
  h3_cells: string[];
  osrm_geometry?: [number, number][];
}

export interface H3CellGeometry {
  index: string;
  boundary: [number, number][]; // Array of [lat, lng] coordinates
}

export interface RouteMatch {
  route_name: string;
  status: string;
  assigned_vehicle: string;
  driver: string;
  exact_match: boolean;
  nearby_match_count: number;
  nearest_stop_km: number;
  nearest_stop: string;
  exact_cells: H3CellGeometry[];
  nearby_cells: H3CellGeometry[];
  matched_by?: 'stop' | 'path';
  path_overlap_cells?: H3CellGeometry[];
}

export interface DatabaseHit {
  route_name: string;
  stop_name: string;
  lat: number;
  lng: number;
  stop_h3: string;
  distance_km: number;
  passed: boolean;
  is_exact_cell: boolean;
}

export interface MatchResponse {
  sql_query: string;
  candidate_cell: H3CellGeometry;
  k_ring_cells: H3CellGeometry[];
  db_hits: DatabaseHit[];
  matches: RouteMatch[];
  path_pass_cells?: H3CellGeometry[];
}
