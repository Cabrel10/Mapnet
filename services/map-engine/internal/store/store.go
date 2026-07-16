// Package store persists and queries mapnet_edges in PostGIS.
package store

import (
	"context"
	"encoding/json"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/quamtech/mapnet/map-engine/internal/edge"
)

// Store wraps a pgx pool.
type Store struct {
	pool    *pgxpool.Pool
	minConf int
}

// New opens a pool.
func New(ctx context.Context, dsn string, minConf int) (*Store, error) {
	cfg, err := pgxpool.ParseConfig(dsn)
	if err != nil {
		return nil, err
	}
	cfg.MaxConns = 10
	cfg.MaxConnLifetime = time.Hour
	pool, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		return nil, err
	}
	return &Store{pool: pool, minConf: minConf}, nil
}

// Ping checks connectivity.
func (s *Store) Ping(ctx context.Context) error { return s.pool.Ping(ctx) }

// Close releases the pool.
func (s *Store) Close() { s.pool.Close() }

// HasNearby implements edge.NearbyChecker using a geography ST_DWithin query.
func (s *Store) HasNearby(lat, lon, radiusM float64) bool {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	var n int
	err := s.pool.QueryRow(ctx, `
		SELECT COUNT(1) FROM mapnet_edges
		WHERE ST_DWithin(
			geom::geography,
			ST_SetSRID(ST_MakePoint($2,$1),4326)::geography,
			$3)`, lat, lon, radiusM).Scan(&n)
	return err == nil && n > 0
}

// NearbyEdge is a returned nearby edge row.
type NearbyEdge struct {
	EdgeID      string   `json:"edge_id"`
	Name        *string  `json:"name"`
	HighwayType *string  `json:"highway_type"`
	Status      string   `json:"status"`
	LengthM     *float64 `json:"length_m"`
	DistanceM   float64  `json:"distance_m"`
}

// NearbyEdges returns edges within radiusM ordered by distance.
func (s *Store) NearbyEdges(ctx context.Context, lat, lon, radiusM float64) ([]NearbyEdge, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT edge_id, name, highway_type, status, length_m,
		       ST_Distance(geom::geography, ST_SetSRID(ST_MakePoint($2,$1),4326)::geography) AS dist
		FROM mapnet_edges
		WHERE ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint($2,$1),4326)::geography, $3)
		ORDER BY dist`, lat, lon, radiusM)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []NearbyEdge
	for rows.Next() {
		var e NearbyEdge
		if err := rows.Scan(&e.EdgeID, &e.Name, &e.HighwayType, &e.Status, &e.LengthM, &e.DistanceM); err != nil {
			return nil, err
		}
		out = append(out, e)
	}
	return out, rows.Err()
}

// EdgeSummary is a listing row.
type EdgeSummary struct {
	ID                int64   `json:"id"`
	EdgeID            string  `json:"edge_id"`
	Name              *string `json:"name"`
	HighwayType       *string `json:"highway_type"`
	Status            string  `json:"status"`
	ConfirmationCount int     `json:"confirmation_count"`
}

// ListEdges returns edges optionally filtered by status.
func (s *Store) ListEdges(ctx context.Context, status string, limit int) ([]EdgeSummary, error) {
	q := `SELECT id, edge_id, name, highway_type, status, confirmation_count FROM mapnet_edges`
	args := []any{}
	if status != "" {
		q += ` WHERE status=$1`
		args = append(args, status)
	}
	q += ` ORDER BY id LIMIT $` + itoa(len(args)+1)
	args = append(args, limit)

	rows, err := s.pool.Query(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []EdgeSummary
	for rows.Next() {
		var e EdgeSummary
		if err := rows.Scan(&e.ID, &e.EdgeID, &e.Name, &e.HighwayType, &e.Status, &e.ConfirmationCount); err != nil {
			return nil, err
		}
		out = append(out, e)
	}
	return out, rows.Err()
}

// UpsertCandidate inserts a detected edge (GeoJSON), bumping confirmation on conflict.
func (s *Store) UpsertCandidate(ctx context.Context, c edge.Candidate) error {
	geom, err := json.Marshal(c.Geometry)
	if err != nil {
		return err
	}
	_, err = s.pool.Exec(ctx, `
		INSERT INTO mapnet_edges (edge_id, geom, highway_type, status, first_seen_at, last_seen_at)
		VALUES ($1, ST_SetSRID(ST_GeomFromGeoJSON($2),4326), 'unclassified', $3, NOW(), NOW())
		ON CONFLICT (edge_id) DO UPDATE SET
			confirmation_count = mapnet_edges.confirmation_count + 1,
			last_seen_at = NOW(),
			status = CASE
				WHEN mapnet_edges.confirmation_count + 1 >= $4 THEN 'validated'
				ELSE mapnet_edges.status END`,
		c.EdgeID, string(geom), c.Status, s.minConf)
	return err
}

// StoreMatched persists a map-matched geometry as an osm_existing edge candidate.
func (s *Store) StoreMatched(ctx context.Context, traceID string, geom json.RawMessage) error {
	_, err := s.pool.Exec(ctx, `
		INSERT INTO mapnet_edges (edge_id, geom, highway_type, status, first_seen_at, last_seen_at)
		VALUES ($1, ST_SetSRID(ST_GeomFromGeoJSON($2),4326), 'unclassified', 'osm_existing', NOW(), NOW())
		ON CONFLICT (edge_id) DO UPDATE SET
			confirmation_count = mapnet_edges.confirmation_count + 1,
			last_seen_at = NOW(),
			status = CASE
				WHEN mapnet_edges.confirmation_count + 1 >= $3 THEN 'validated'
				ELSE mapnet_edges.status END`,
		"matched-"+traceID, string(geom), s.minConf)
	return err
}

func itoa(i int) string {
	if i == 0 {
		return "0"
	}
	var b [8]byte
	pos := len(b)
	for i > 0 {
		pos--
		b[pos] = byte('0' + i%10)
		i /= 10
	}
	return string(b[pos:])
}
