import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import type { Route, MatchResponse, H3CellGeometry } from '../types';

const C = {
  accent: '#e8a840',
  accentGreen: '#4db896',
  accentAmber: '#e8a840',
  accentRed: '#b84a3f',
  white: '#ffffff',
  dark: '#1b1d23',
  muted: '#9ca3af',
} as const;

interface MapProps {
  lat: number;
  lng: number;
  routes: Route[];
  matchData: MatchResponse | null;
  selectedRouteName: string | null;
  onMapClick: (lat: number, lng: number) => void;
  showH3Rings: boolean;
  showRouteCells: boolean;
  redZoneEditMode?: boolean;
  pendingRedZones?: H3CellGeometry[];
  redZones?: string[];
  onGridCellToggle?: (index: string, boundary: [number, number][]) => void;
}

const getRouteColor = (name: string) => {
  const colors = [
    '#c084fc', // Light Purple
    '#60a5fa', // Light Blue
    '#f472b6', // Light Pink
    '#fb923c', // Orange
    '#2dd4bf', // Teal
    '#fb7185', // Rose
    '#818cf8', // Indigo
    '#a7f3d0', // Mint
  ];
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  const index = Math.abs(hash) % colors.length;
  return colors[index];
};

export const Map: React.FC<MapProps> = ({
  lat,
  lng,
  routes,
  matchData,
  selectedRouteName,
  onMapClick,
  showH3Rings,
  showRouteCells,
  redZoneEditMode = false,
  pendingRedZones = [],
  redZones = [],
  onGridCellToggle,
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layersGroupRef = useRef<L.LayerGroup | null>(null);
  const [gridCells, setGridCells] = useState<H3CellGeometry[]>([]);

  // 1. Initialize Map
  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    const map = L.map(mapContainerRef.current, {
      zoomControl: false
    }).setView([9.016423, 38.768558], 13);
    
    L.control.zoom({ position: 'topright' }).addTo(map);

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
      subdomains: 'abcd',
      maxZoom: 20
    }).addTo(map);

    mapRef.current = map;

    const layersGroup = L.layerGroup().addTo(map);
    layersGroupRef.current = layersGroup;

    map.on('click', (e: L.LeafletMouseEvent) => {
      onMapClick(e.latlng.lat, e.latlng.lng);
    });

    return () => {
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
  }, []);

  // 1b. Always keep grid cells cached so they're instantly available in edit mode
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    let timeout: number;
    const DEBOUNCE = redZoneEditMode ? 300 : 2000;

    const fetchCells = () => {
      const bounds = map.getBounds();
      fetch('/api/cells-in-bounds', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          north: bounds.getNorth(),
          south: bounds.getSouth(),
          east: bounds.getEast(),
          west: bounds.getWest(),
          res: 9,
        }),
      })
        .then(r => r.json())
        .then(data => {
          if (data.cells) setGridCells(data.cells);
        })
        .catch(() => {});
    };

    fetchCells();
    map.on('moveend', () => {
      clearTimeout(timeout);
      timeout = window.setTimeout(fetchCells, DEBOUNCE);
    });

    return () => {
      clearTimeout(timeout);
      map.off('moveend');
    };
  }, [redZoneEditMode]);

  // 2. Redraw Layers
  useEffect(() => {
    const map = mapRef.current;
    const layers = layersGroupRef.current;
    if (!map || !layers) return;

    layers.clearLayers();

    // A. Draw all route lines
    routes.forEach(route => {
      const isSelected = selectedRouteName === route.route_name;
      const color = getRouteColor(route.route_name);
      
      const stopLatLngs = route.route_members.map(s => [s.lat, s.lng] as [number, number]);

      const routePath = (route.osrm_geometry && route.osrm_geometry.length > 0)
        ? route.osrm_geometry
        : stopLatLngs;

      if (routePath.length > 1) {
        L.polyline(routePath, {
          color,
          weight: isSelected ? 4.5 : 1.5,
          opacity: isSelected ? 0.95 : 0.25,
          dashArray: isSelected ? undefined : '5, 5',
          lineCap: 'round',
          lineJoin: 'round'
        }).addTo(layers);
      }

      // Draw original stops as tiny background points
      route.route_members.forEach(stop => {
        const stopMarker = L.circleMarker([stop.lat, stop.lng], {
          radius: 3,
          color: isSelected ? color : '#374151',
          fillColor: isSelected ? '#ffffff' : '#1f2937',
          fillOpacity: isSelected ? 0.9 : 0.3,
          weight: 1
        });
        stopMarker.bindPopup(`
          <div style="font-family: 'Inter', sans-serif; font-size: 0.78rem; color: #fff; padding: 4px;">
            <div style="font-weight: 700;">${stop.name}</div>
            <div style="color: ${C.muted};">Route: ${route.route_name}</div>
          </div>
        `);
        stopMarker.addTo(layers);
      });
    });

    // B. Draw candidate matching geometry
    if (matchData) {
      const { candidate_cell, k_ring_cells, matches, db_hits, path_pass_cells, red_zone_cells } = matchData;

      // 1. Draw K-Ring Cells (outer rings) if enabled
      if (showH3Rings && k_ring_cells) {
        k_ring_cells.forEach(cell => {
          L.polygon(cell.boundary, {
            color: C.accent,
            weight: 1.5,
            opacity: 0.35,
            fillColor: C.accent,
            fillOpacity: 0.04,
            dashArray: '3, 4'
          }).addTo(layers);
        });
      }

      // 2. Draw Candidate Cell
      if (candidate_cell) {
        L.polygon(candidate_cell.boundary, {
          color: C.accent,
          weight: 3,
          opacity: 0.9,
          fillColor: C.accent,
          fillOpacity: 0.2
        }).addTo(layers);
      }

      // 2b. Draw Red Zone Cells (existing) — only when NOT in grid edit mode
      if (!redZoneEditMode && red_zone_cells && red_zone_cells.length > 0) {
        red_zone_cells.forEach(cell => {
          if (!cell.boundary || cell.boundary.length === 0) return;
          L.polygon(cell.boundary, {
            color: C.accentRed,
            weight: 2.5,
            opacity: 0.7,
            fillColor: C.accentRed,
            fillOpacity: 0.18
          }).addTo(layers);
        });
      }

      // 2c. Draw Pending Red Zone Cells — only when NOT in grid edit mode
      if (!redZoneEditMode && pendingRedZones && pendingRedZones.length > 0) {
        pendingRedZones.forEach(cell => {
          if (!cell.boundary || cell.boundary.length === 0) return;
          L.polygon(cell.boundary, {
            color: '#f97316',
            weight: 2.5,
            opacity: 0.85,
            fillColor: '#f97316',
            fillOpacity: 0.25,
            dashArray: '6, 4'
          }).addTo(layers);
        });
      }

      // 3. Highlight Overlapping Route Cells if enabled
      if (showRouteCells && selectedRouteName && matches) {
        const currentMatch = matches.find(m => m.route_name === selectedRouteName);
        if (currentMatch) {
          currentMatch.exact_cells.forEach(cell => {
            L.polygon(cell.boundary, {
              color: C.accentGreen,
              weight: 2.5,
              opacity: 0.9,
              fillColor: C.accentGreen,
              fillOpacity: 0.35
            }).addTo(layers);
          });

          currentMatch.nearby_cells.forEach(cell => {
            L.polygon(cell.boundary, {
              color: C.accentAmber,
              weight: 2.5,
              opacity: 0.85,
              fillColor: C.accentAmber,
              fillOpacity: 0.25
            }).addTo(layers);
          });
        }
      }

      // 3b. Draw path-pass cells (overlap between route geometry and k-ring, no stops nearby)
      if (path_pass_cells && path_pass_cells.length > 0) {
        path_pass_cells.forEach(cell => {
          L.polygon(cell.boundary, {
            color: '#f472b6',
            weight: 2,
            opacity: 0.8,
            fillColor: '#f472b6',
            fillOpacity: 0.25,
            dashArray: '4, 4'
          }).addTo(layers);
        });
      }

      // 3c. H3 Grid overlay for red zone edit mode
      if (redZoneEditMode && gridCells.length > 0) {
        const redZoneSet = new Set(redZones);
        const pendingSet = new Set(pendingRedZones.map(c => c.index));

        gridCells.forEach(cell => {
          if (!cell.boundary || cell.boundary.length === 0) return;

          const isSaved = redZoneSet.has(cell.index);
          const isPending = pendingSet.has(cell.index);

          const poly = L.polygon(cell.boundary, {
            color: isSaved ? C.accentRed : isPending ? '#f97316' : '#555',
            weight: isSaved ? 2.5 : isPending ? 2.5 : 0.8,
            opacity: isSaved ? 0.7 : isPending ? 0.85 : 0.35,
            fillColor: isSaved ? C.accentRed : isPending ? '#f97316' : 'transparent',
            fillOpacity: isSaved ? 0.18 : isPending ? 0.25 : 0,
            dashArray: isPending ? '6, 4' : undefined,
          });
          poly.on('click', (e) => {
            L.DomEvent.stopPropagation(e.originalEvent);
            onGridCellToggle?.(cell.index, cell.boundary);
          });
          poly.addTo(layers);
        });
      }

      // 4. Draw database query hits on map (descriptive validation)
      if (db_hits) {
        db_hits.forEach(hit => {
          const color = hit.passed ? C.accentGreen : C.accentRed;
          const fillOpacity = hit.passed ? 0.85 : 0.4;
          const radius = hit.passed ? 6 : 4.5;
          const weight = hit.passed ? 2 : 1;

          const hitMarker = L.circleMarker([hit.lat, hit.lng], {
            radius,
            color: '#ffffff',
            fillColor: color,
            fillOpacity,
            weight
          });

          hitMarker.bindPopup(`
            <div style="font-family: 'Inter', sans-serif; font-size: 0.8rem; color: #fff; padding: 4px;">
              <div style="font-weight: 700; font-size: 0.88rem; margin-bottom: 4px; color: ${color};">
                ${hit.stop_name}
              </div>
              <div style="color: #d1d5db; margin-bottom: 2px;">Route: ${hit.route_name}</div>
              <div style="color: #d1d5db; margin-bottom: 4px;">Distance: <strong>${hit.distance_km.toFixed(3)} km</strong></div>
              <div style="font-family: monospace; font-size: 0.72rem; color: #9ca3af; background: rgba(0,0,0,0.3); padding: 2px 6px; border-radius: 4px; display: inline-block; margin-bottom: 6px;">
                Hex: ${hit.stop_h3}
              </div>
              <br/>
              <div style="font-weight: 600; font-size: 0.72rem; display: inline-block; padding: 2px 6px; border-radius: 3px; background: ${hit.passed ? 'rgba(77,184,150,0.2)' : 'rgba(184,74,63,0.2)'}; color: ${color};">
                ${hit.passed ? 'PASS (In Range)' : 'FILTERED (False Positive)'}
              </div>
            </div>
          `);
          hitMarker.addTo(layers);
        });
      }

      // 5. Highlight Nearest Stop path for selected route
      if (selectedRouteName && matches) {
        const currentMatch = matches.find(m => m.route_name === selectedRouteName);
        const routeObj = routes.find(r => r.route_name === selectedRouteName);
        if (currentMatch && routeObj) {
          const nearestStopObj = routeObj.route_members.find(s => s.name === currentMatch.nearest_stop);
          if (nearestStopObj) {
            L.polyline([[lat, lng], [nearestStopObj.lat, nearestStopObj.lng]], {
              color: C.accent,
              weight: 2,
              opacity: 0.9,
              dashArray: '4, 4'
            }).addTo(layers);

            L.circle([nearestStopObj.lat, nearestStopObj.lng], {
              radius: 100,
              color: C.accent,
              weight: 1.5,
              opacity: 0.5,
              fillColor: C.accent,
              fillOpacity: 0.06
            }).addTo(layers);
          }
        }
      }
    }

    // C. Draw candidate dispatch point (cyan pulsing dot)
    const candidateMarker = L.circleMarker([lat, lng], {
      radius: 7.5,
      color: C.white,
      fillColor: C.accent,
      fillOpacity: 1,
      weight: 2
    });

    candidateMarker.bindPopup(`
      <div style="font-family: 'Inter', sans-serif; font-size: 0.8rem; color: #fff;">
        <strong>Candidate Position</strong><br/>
        Lat: ${lat.toFixed(6)}<br/>
        Lng: ${lng.toFixed(6)}<br/>
        <span style="color: ${C.accent}; font-family: monospace;">Cell: ${matchData?.candidate_cell.index || 'Computing...'}</span>
      </div>
    `);
    candidateMarker.addTo(layers);

  }, [lat, lng, routes, matchData, selectedRouteName, showH3Rings, showRouteCells, redZoneEditMode, pendingRedZones]);

  useEffect(() => {
    if (mapRef.current) {
      mapRef.current.panTo([lat, lng]);
    }
  }, [lat, lng]);

  return (
    <div className={`map-container ${redZoneEditMode ? 'rz-edit-mode' : ''}`}>
      <div ref={mapContainerRef} className="map-element" />
      <div className={`map-overlay-instructions ${redZoneEditMode ? 'rz-edit-active' : ''}`}>
        {redZoneEditMode
          ? 'Click any hexagon on the grid to toggle it as a red zone'
          : 'Click map to set candidate location'}
      </div>
    </div>
  );
};
