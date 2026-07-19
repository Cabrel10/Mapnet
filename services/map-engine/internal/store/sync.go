package store

import (
	"context"
	"encoding/json"
	"time"
)

// DatasetVersion is one row of the sync manifest.
type DatasetVersion struct {
	Dataset string `json:"dataset"`
	Version int64  `json:"version"`
}

// Manifest returns the current version of every dataset (Git-like HEAD).
// The mobile client compares its held versions against this to know what to pull.
func (s *Store) Manifest(ctx context.Context) ([]DatasetVersion, error) {
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	rows, err := s.pool.Query(ctx,
		`SELECT dataset, version FROM sync_dataset_version ORDER BY dataset`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []DatasetVersion
	for rows.Next() {
		var d DatasetVersion
		if err := rows.Scan(&d.Dataset, &d.Version); err != nil {
			return nil, err
		}
		out = append(out, d)
	}
	return out, rows.Err()
}

// EdgeDelta is a single change transmitted to the client.
// Geometry is an encoded polyline (compact) except for deletions.
type EdgeDelta struct {
	EdgeID     string  `json:"edge_id"`
	ChangeType string  `json:"change_type"` // "A" add, "M" modify, "D" delete
	Version    int64   `json:"version"`
	Status     *string `json:"status,omitempty"`
	Highway    *string `json:"highway_type,omitempty"`
	Polyline   *string `json:"polyline,omitempty"` // encoded polyline (nil for deletes)
}

// MapDelta returns every edge change strictly after `since`, ordered by version.
// This is the core transmission primitive: the server sends only what changed,
// never the full dataset. Geometry is polyline-encoded server-side (PostGIS).
func (s *Store) MapDelta(ctx context.Context, since int64, limit int) ([]EdgeDelta, int64, error) {
	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()

	// Current head version to report back so the client can advance its cursor.
	var head int64
	if err := s.pool.QueryRow(ctx,
		`SELECT version FROM sync_dataset_version WHERE dataset='map'`).Scan(&head); err != nil {
		return nil, 0, err
	}

	// Join the latest changelog entry per edge (> since) with current edge state.
	// For deletions the edge row may still exist with is_deleted=true.
	rows, err := s.pool.Query(ctx, `
		SELECT e.edge_id,
		       CASE WHEN e.is_deleted THEN 'D' ELSE cl.change_type END AS change_type,
		       e.version,
		       e.status,
		       e.highway_type,
		       CASE WHEN e.is_deleted THEN NULL
		            ELSE ST_AsEncodedPolyline(e.geom) END AS polyline
		FROM mapnet_edges e
		JOIN LATERAL (
		    SELECT change_type FROM sync_edge_changelog c
		    WHERE c.edge_id = e.edge_id
		    ORDER BY c.version DESC LIMIT 1
		) cl ON true
		WHERE e.version > $1
		ORDER BY e.version ASC
		LIMIT $2`, since, limit)
	if err != nil {
		return nil, head, err
	}
	defer rows.Close()

	var out []EdgeDelta
	for rows.Next() {
		var d EdgeDelta
		if err := rows.Scan(&d.EdgeID, &d.ChangeType, &d.Version,
			&d.Status, &d.Highway, &d.Polyline); err != nil {
			return nil, head, err
		}
		out = append(out, d)
	}
	return out, head, rows.Err()
}

// EdgesGeoJSON returns all non-deleted edges as a GeoJSON FeatureCollection,
// ready to be added as a MapLibre source. Geometry built server-side by PostGIS.
func (s *Store) EdgesGeoJSON(ctx context.Context, limit int) (json.RawMessage, error) {
	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	if limit <= 0 || limit > 20000 {
		limit = 5000
	}
	var fc json.RawMessage
	err := s.pool.QueryRow(ctx, `
		SELECT COALESCE(
		  json_build_object(
		    'type','FeatureCollection',
		    'features', COALESCE(json_agg(f.feature), '[]'::json)
		  )::text::json,
		  '{"type":"FeatureCollection","features":[]}'::json)
		FROM (
		  SELECT json_build_object(
		    'type','Feature',
		    'id', edge_id,
		    'properties', json_build_object(
		        'edge_id', edge_id,
		        'status', status,
		        'highway_type', highway_type,
		        'confirmation_count', confirmation_count,
		        'version', version),
		    'geometry', ST_AsGeoJSON(geom)::json
		  ) AS feature
		  FROM mapnet_edges
		  WHERE is_deleted = false AND geom IS NOT NULL
		  ORDER BY id
		  LIMIT $1
		) f`, limit).Scan(&fc)
	if err != nil {
		return nil, err
	}
	return fc, nil
}
