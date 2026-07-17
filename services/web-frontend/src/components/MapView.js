import React, { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import { getTrace, getEdges, searchPlaces } from '../services/api';

const MapView = () => {
  const mapContainer = useRef(null);
  const map = useRef(null);
  const [traceId, setTraceId] = useState('');
  const [edges, setEdges] = useState([]);
  const [places, setPlaces] = useState([]);
  const [query, setQuery] = useState('');

  useEffect(() => {
    if (map.current) return;

    map.current = new maplibregl.Map({
      container: mapContainer.current,
      style: {
        version: 8,
        sources: {
          osm: {
            type: 'raster',
            tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
            tileSize: 256,
          },
        },
        layers: [
          {
            id: 'osm',
            type: 'raster',
            source: 'osm',
          },
        ],
      },
      center: [11.5021, 3.848],
      zoom: 14,
    });

    map.current.addControl(new maplibregl.NavigationControl(), 'top-right');
  }, []);

  const loadTrace = async () => {
    if (!traceId) return;
    try {
      const { data } = await getTrace(traceId);
      const coordinates = data.map((p) => [p.longitude, p.latitude]);
      if (coordinates.length === 0) return;

      map.current.addSource('trace', {
        type: 'geojson',
        data: {
          type: 'Feature',
          geometry: { type: 'LineString', coordinates },
        },
      });
      map.current.addLayer({
        id: 'trace',
        type: 'line',
        source: 'trace',
        paint: { 'line-color': '#3b82f6', 'line-width': 4 },
      });
      map.current.fitBounds(coordinates.reduce((b, c) => b.extend(c), new maplibregl.LngLatBounds(coordinates[0], coordinates[0])), { padding: 40 });
    } catch (err) {
      alert('Trace non trouvée');
    }
  };

  const loadEdges = async () => {
    try {
      const { data } = await getEdges('non_cartographie_osm');
      setEdges(data.edges || []);
      const features = (data.edges || []).map((e) => ({
        type: 'Feature',
        properties: { edge_id: e.edge_id },
        geometry: e.geom,
      }));
      if (map.current.getSource('edges')) {
        map.current.getSource('edges').setData({ type: 'FeatureCollection', features });
      } else {
        map.current.addSource('edges', { type: 'geojson', data: { type: 'FeatureCollection', features } });
        map.current.addLayer({ id: 'edges', type: 'line', source: 'edges', paint: { 'line-color': '#ef4444', 'line-width': 3 } });
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleSearch = async () => {
    if (!query) return;
    try {
      const { data } = await searchPlaces(query);
      setPlaces(data.places || []);
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div style={{ display: 'flex', height: '100vh' }}>
      <div style={{ width: 320, padding: 16, background: '#f3f4f6', overflowY: 'auto' }}>
        <h1>MapNet Dashboard</h1>
        <div style={{ marginBottom: 16 }}>
          <h3>Trace GPX</h3>
          <input
            type="text"
            placeholder="trace_id"
            value={traceId}
            onChange={(e) => setTraceId(e.target.value)}
            style={{ width: '100%', marginBottom: 8 }}
          />
          <button onClick={loadTrace} style={{ width: '100%' }}>Charger</button>
        </div>
        <div style={{ marginBottom: 16 }}>
          <h3>Nouvelles routes</h3>
          <button onClick={loadEdges} style={{ width: '100%' }}>Charger</button>
          <p>{edges.length} segments détectés</p>
        </div>
        <div style={{ marginBottom: 16 }}>
          <h3>Recherche POI</h3>
          <input
            type="text"
            placeholder="pharmacie, supermarché..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            style={{ width: '100%', marginBottom: 8 }}
          />
          <button onClick={handleSearch} style={{ width: '100%' }}>Rechercher</button>
          <ul>
            {places.map((p) => (
              <li key={p.place_id}>{p.name} ({p.category})</li>
            ))}
          </ul>
        </div>
      </div>
      <div ref={mapContainer} style={{ flex: 1 }} />
    </div>
  );
};

export default MapView;
