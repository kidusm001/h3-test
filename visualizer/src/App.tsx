import { useEffect, useState } from 'react';
import type { Route, MatchResponse } from './types';
import { Map } from './components/Map';

export default function App() {
  const [lat, setLat] = useState<number>(9.016423);
  const [lng, setLng] = useState<number>(38.768558);
  const [k, setK] = useState<number>(1);
  const [resolution, setResolution] = useState<number>(9);
  const [maxDistKm, setMaxDistKm] = useState<number>(1.5);
  
  // Navigation
  const [activeTab, setActiveTab] = useState<'dispatch' | 'explainer'>('dispatch');
  
  // Core states
  const [routes, setRoutes] = useState<Route[]>([]);
  const [matchData, setMatchData] = useState<MatchResponse | null>(null);
  const [selectedRouteName, setSelectedRouteName] = useState<string | null>(null);
  const [showH3Rings, setShowH3Rings] = useState<boolean>(true);
  const [showRouteCells, setShowRouteCells] = useState<boolean>(true);
  
  // Modal states
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [jsonText, setJsonText] = useState<string>('');
  const [jsonError, setJsonError] = useState<string | null>(null);
  
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // 1. Fetch routes on load
  const fetchRoutes = async () => {
    try {
      const res = await fetch('/api/routes');
      if (!res.ok) throw new Error('Failed to fetch routes data.');
      const data = await res.json();
      setRoutes(data.routes || []);
      setJsonText(JSON.stringify(data, null, 2));
    } catch (err: any) {
      setError(err.message || 'Error fetching routes');
    }
  };

  useEffect(() => {
    fetchRoutes();
  }, []);

  // 2. Fetch matches when query arguments change
  useEffect(() => {
    const fetchMatches = async () => {
      setLoading(true);
      try {
        const res = await fetch(
          `/api/match?lat=${lat}&lng=${lng}&k=${k}&res=${resolution}&max_dist_km=${maxDistKm}`
        );
        if (!res.ok) throw new Error('Failed to calculate matching routes.');
        const data = await res.json();
        setMatchData(data);
      } catch (err: any) {
        setError(err.message || 'Error processing spatial match');
      } finally {
        setLoading(false);
      }
    };

    fetchMatches();
  }, [lat, lng, k, resolution, maxDistKm]);

  const handleMapClick = (clickLat: number, clickLng: number) => {
    setLat(Number(clickLat.toFixed(6)));
    setLng(Number(clickLng.toFixed(6)));
  };

  const handleJsonSave = async () => {
    try {
      const parsed = JSON.parse(jsonText);
      if (!parsed.routes || !Array.isArray(parsed.routes)) {
        throw new Error('Invalid schema: Missing root "routes" array.');
      }
      
      const res = await fetch('/api/routes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(parsed),
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || 'Failed to save routes to server.');
      }

      await fetchRoutes();
      setIsModalOpen(false);
      setJsonError(null);
    } catch (err: any) {
      setJsonError(err.message || 'Invalid JSON format.');
    }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target?.result as string;
      try {
        JSON.parse(content);
        setJsonText(content);
        setJsonError(null);
      } catch (err) {
        setJsonError('Uploaded file is not valid JSON.');
      }
    };
    reader.readAsText(file);
  };

  const renderSQLHighlight = (sql: string) => {
    const keywords = ['SELECT', 'FROM', 'WHERE', 'IN'];
    const lines = sql.split('\n');
    return lines.map((line, idx) => {
      const words = line.split(' ');
      const highlightedWords = words.map((word, wIdx) => {
        const cleanWord = word.replace(/[^a-zA-Z_]/g, '');
        if (keywords.includes(cleanWord.toUpperCase())) {
          return <span key={wIdx} className="sql-keyword">{word} </span>;
        }
        if (cleanWord === 'route_stops') {
          return <span key={wIdx} className="sql-table">{word} </span>;
        }
        if (word.startsWith("'") || word.includes("'")) {
          return <span key={wIdx} className="sql-string">{word} </span>;
        }
        return word + ' ';
      });
      return <div key={idx}>{highlightedWords}</div>;
    });
  };

  return (
    <div className="app-container">
      {/* Sidebar Panel */}
      <aside className="sidebar">
        <header className="header">
          <div className="header-title-wrapper">
            <div className="header-logo">H3</div>
            <h1>Route Matcher</h1>
          </div>
          <p>Database Spatial Indexing & Dispatch Explainer</p>
        </header>

        {/* Inputs Control Panel */}
        <section className="panel">
          <h2 className="section-title">Dispatch Controls</h2>
          
          <div className="form-group">
            <div className="coordinate-inputs">
              <div>
                <label htmlFor="latitude">Latitude</label>
                <input
                  type="number"
                  id="latitude"
                  value={lat}
                  step="0.000001"
                  onChange={(e) => setLat(Number(e.target.value))}
                />
              </div>
              <div>
                <label htmlFor="longitude">Longitude</label>
                <input
                  type="number"
                  id="longitude"
                  value={lng}
                  step="0.000001"
                  onChange={(e) => setLng(Number(e.target.value))}
                />
              </div>
            </div>
          </div>

          <div className="form-group">
            <div className="coordinate-inputs" style={{ gridTemplateColumns: '1.2fr 0.8fr' }}>
              <div>
                <label htmlFor="resolution">H3 Resolution</label>
                <select 
                  id="resolution" 
                  value={resolution} 
                  onChange={(e) => setResolution(Number(e.target.value))}
                >
                  <option value="8">Res 8 (~460m edges)</option>
                  <option value="9">Res 9 (~170m edges)</option>
                  <option value="10">Res 10 (~66m edges)</option>
                </select>
              </div>
              <div>
                <label>Ring radius (k)</label>
                <div className="range-slider-container">
                  <input
                    type="range"
                    min="0"
                    max="4"
                    value={k}
                    onChange={(e) => setK(Number(e.target.value))}
                  />
                  <span className="slider-val">{k}</span>
                </div>
              </div>
            </div>
          </div>

          <div className="form-group">
            <label>Haversine Distance Filter</label>
            <div className="range-slider-container">
              <input
                type="range"
                min="0.3"
                max="3.0"
                step="0.1"
                value={maxDistKm}
                onChange={(e) => setMaxDistKm(Number(e.target.value))}
              />
              <span className="slider-val" style={{ minWidth: 60 }}>{maxDistKm.toFixed(1)} km</span>
            </div>
          </div>

          <div className="toggle-group">
            <label className="toggle-item">
              <input
                type="checkbox"
                checked={showH3Rings}
                onChange={(e) => setShowH3Rings(e.target.checked)}
              />
              Show Search Rings
            </label>
            <label className="toggle-item">
              <input
                type="checkbox"
                checked={showRouteCells}
                onChange={(e) => setShowRouteCells(e.target.checked)}
              />
              Show Stop Hexagons
            </label>
          </div>

          <div className="actions-container">
            <button className="btn btn-secondary" onClick={() => setIsModalOpen(true)}>
              Edit Route DB
            </button>
            <button
              className="btn btn-primary"
              onClick={() => {
                setLat(9.016423);
                setLng(38.768558);
                setK(1);
                setResolution(9);
                setMaxDistKm(1.5);
              }}
            >
              Reset Config
            </button>
          </div>
        </section>

        {/* Tab Selection */}
        <div className="tabs-header">
          <button
            className={`tab-btn ${activeTab === 'dispatch' ? 'active' : ''}`}
            onClick={() => setActiveTab('dispatch')}
          >
            Matches ({matchData?.matches.length || 0})
          </button>
          <button
            className={`tab-btn ${activeTab === 'explainer' ? 'active' : ''}`}
            onClick={() => setActiveTab('explainer')}
          >
            SQL Explainer
          </button>
        </div>

        {/* Main Content Area */}
        <section className="results-container">
          {error && <div style={{ color: 'var(--accent-red)', marginBottom: 12, fontSize: '0.85rem' }}>{error}</div>}

          {loading ? (
            <div style={{ textAlign: 'center', padding: '40px', color: 'var(--accent)' }}>
              Processing...
            </div>
          ) : activeTab === 'dispatch' ? (
            /* Dispatch Tab */
            <div className="route-list">
              {matchData && (
                <div className="candidate-cell-badge">
                  Candidate H3 (Res {resolution}): <span>{matchData.candidate_cell.index}</span>
                </div>
              )}

              {matchData?.matches && matchData.matches.length > 0 ? (
                matchData.matches.map((match) => {
                  const isSelected = selectedRouteName === match.route_name;
                  const routeMeta = routes.find(r => r.route_name === match.route_name);
                  
                  return (
                    <div
                      key={match.route_name}
                      className={`route-card ${match.exact_match ? 'exact' : 'nearby'} ${
                        isSelected ? 'selected' : ''
                      }`}
                      onClick={() => setSelectedRouteName(isSelected ? null : match.route_name)}
                    >
                      <div className="route-card-header">
                        <span className="route-name">{match.route_name}</span>
                        <span className={`match-badge ${match.exact_match ? 'exact' : 'nearby'}`}>
                          {match.exact_match ? 'Exact Match' : 'Nearby'}
                        </span>
                      </div>

                      <div className="route-meta">
                        <div className="meta-item">
                          <span className="meta-label">Driver:</span> {match.driver}
                        </div>
                        <div className="meta-item">
                          <span className="meta-label">Vehicle:</span> {match.assigned_vehicle}
                        </div>
                        <div className="meta-item">
                          <span className="meta-label">Status:</span>
                          <span className={`status-indicator status-${match.status.toLowerCase()}`} />
                          {match.status}
                        </div>
                        <div className="meta-item">
                          <span className="meta-label">Type:</span> {routeMeta?.route_type || 'Drop-off'}
                        </div>
                      </div>

                      <div className="distance-highlight">
                        <span>Nearest Stop: <strong>{match.nearest_stop}</strong></span>
                        <span className="distance-value">{match.nearest_stop_km.toFixed(3)} km</span>
                      </div>
                    </div>
                  );
                })
              ) : (
                <div className="no-matches">
                  No routes within the {k}-ring threshold. Increase k or the distance filter.
                </div>
              )}
            </div>
          ) : (
            /* Explainer Tab */
            <div className="explainer-container">
              {matchData && (
                <>
                  {/* Step 1 */}
                  <div className="explainer-step">
                    <span className="step-badge">Step 1</span>
                    <h3>Pre-Index Route Stops</h3>
                    <p>
                      Stops coordinates are converted once on setup to H3 indexes at Resolution {resolution} and stored in the database.
                    </p>
                    <table className="db-sample-table">
                      <thead>
                        <tr><th>Stop Name</th><th>H3 Index (Res {resolution})</th></tr>
                      </thead>
                      <tbody>
                        {routes.length > 0 ? (
                          routes.slice(0, 3).map((r, i) => {
                            const stop = r.route_members[1] || r.route_members[0];
                            return (
                              <tr key={i}>
                                <td>{stop.name}</td>
                                <td>{stop.h3_index.substring(0, 15)}</td>
                              </tr>
                            );
                          })
                        ) : (
                          <tr><td colSpan={2}>No stops loaded</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>

                  {/* Step 2 */}
                  <div className="explainer-step">
                    <span className="step-badge">Step 2</span>
                    <h3>Index Candidate Location</h3>
                    <p>
                      Convert candidate coordinates `({lat.toFixed(4)}, {lng.toFixed(4)})` to H3 cell at Resolution {resolution}:
                    </p>
                    <div className="hex-badge candidate" style={{ display: 'inline-block', fontSize: '0.85rem' }}>
                      {matchData.candidate_cell.index}
                    </div>
                  </div>

                  {/* Step 3 */}
                  <div className="explainer-step">
                    <span className="step-badge">Step 3</span>
                    <h3>Grid Ring Expansion (gridDisk)</h3>
                    <p>
                      Generate the search zone keys matching neighbors within radius k={k}. (Total cell strings in pool: {matchData.k_ring_cells.length + 1}).
                    </p>
                    <div className="hex-badges-list">
                      <div className="hex-badge candidate">{matchData.candidate_cell.index} (Candidate)</div>
                      {matchData.k_ring_cells.map(c => (
                        <div key={c.index} className="hex-badge">{c.index}</div>
                      ))}
                    </div>
                  </div>

                  {/* Step 4 */}
                  <div className="explainer-step">
                    <span className="step-badge">Step 4</span>
                    <h3>Relational MariaDB IN Query</h3>
                    <p>
                      Query the database using an indexed string search. This avoids doing CPU-heavy spatial geometry distance calculations on the database server.
                    </p>
                    <div className="sql-code-container">
                      {renderSQLHighlight(matchData.sql_query)}
                    </div>
                    <div style={{ marginTop: 8, fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                      {matchData.db_hits.length} rows returned
                    </div>
                  </div>

                  {/* Step 5 */}
                  <div className="explainer-step">
                    <span className="step-badge">Step 5</span>
                    <h3>App-Layer Haversine Filter & Score</h3>
                    <p>
                      Calculate straight-line physical distances for SQL query hits in memory. Weed out false-positive stops near hexagons' corners exceeding {maxDistKm} km.
                    </p>
                    
                    <div className="hits-list">
                      {matchData.db_hits.length > 0 ? (
                        matchData.db_hits.map((hit, idx) => (
                          <div key={idx} className={`hit-item ${hit.passed ? 'passed' : 'filtered'}`}>
                            <div className="hit-info">
                              <span className="hit-title">{hit.stop_name} <span style={{ color: 'var(--text-muted)', fontSize: '0.7rem' }}>({hit.route_name})</span></span>
                              <span className="hit-subtitle">Hex: {hit.stop_h3}</span>
                            </div>
                            <div className="hit-status">
                              <span className="hit-dist" style={{ color: hit.passed ? 'var(--accent-green)' : 'var(--text-muted)' }}>
                                {hit.distance_km.toFixed(3)} km
                              </span>
                              <span className={`hit-badge ${hit.passed ? 'pass' : 'filter'}`}>
                                {hit.passed ? 'PASS' : 'FILTERED'}
                              </span>
                            </div>
                          </div>
                        ))
                      ) : (
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                          No stops within the search hex pool.
                        </div>
                      )}
                    </div>
                  </div>
                </>
              )}
            </div>
          )}
        </section>
      </aside>

      {/* Main Map */}
      <Map
        lat={lat}
        lng={lng}
        routes={routes}
        matchData={matchData}
        selectedRouteName={selectedRouteName}
        onMapClick={handleMapClick}
        showH3Rings={showH3Rings}
        showRouteCells={showRouteCells}
      />

      {/* Edit Route Database Modal */}
      {isModalOpen && (
        <div className="modal-backdrop" onClick={() => setIsModalOpen(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Edit Route Database</h2>
              <button className="close-btn" onClick={() => setIsModalOpen(false)}>&times;</button>
            </div>
            
            <div className="form-group">
              <label>Import custom JSON routes file</label>
              <input type="file" accept=".json" onChange={handleFileUpload} style={{ color: 'var(--text-primary)', marginBottom: 12 }} />
            </div>

            <div className="form-group">
              <label>Raw JSON Content</label>
              <textarea
                style={{
                  width: '100%',
                  height: '350px',
                  background: 'var(--bg-primary)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border)',
                  borderRadius: '8px',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.8rem',
                  padding: '12px',
                  resize: 'vertical'
                }}
                value={jsonText}
                onChange={(e) => setJsonText(e.target.value)}
              />
            </div>

            {jsonError && (
              <div style={{ color: 'var(--accent-red)', fontSize: '0.85rem', marginBottom: 16 }}>
                {jsonError}
              </div>
            )}

            <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
              <button className="btn btn-secondary" onClick={() => setIsModalOpen(false)}>
                Cancel
              </button>
              <button className="btn btn-primary" onClick={handleJsonSave}>
                Save Routes
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
