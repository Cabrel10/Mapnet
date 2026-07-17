// Package store persists GPX traces into PostGIS via pgx.
// pgx justified: high-performance Postgres driver (Directive 6 allows it over gorm).
package store

import (
	"context"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/quamtech/mapnet/gps-collect/internal/gpx"
)

// Store owns a pgx connection pool.
type Store struct {
	pool *pgxpool.Pool
}

// New opens a pool against dsn.
func New(ctx context.Context, dsn string) (*Store, error) {
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
	return &Store{pool: pool}, nil
}

// Ping checks DB connectivity.
func (s *Store) Ping(ctx context.Context) error { return s.pool.Ping(ctx) }

// Close releases the pool.
func (s *Store) Close() { s.pool.Close() }

// InsertPoints bulk-inserts enriched track points inside a single transaction.
// Returns the number of rows inserted.
func (s *Store) InsertPoints(ctx context.Context, traceID, chauffeurID string, pts []gpx.Point) (int, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return 0, err
	}
	defer tx.Rollback(ctx)

	// Explicit casts so PostgreSQL can deduce a single type per parameter
	// (lat/lon are reused both as columns and inside ST_MakePoint).
	const q = `
		INSERT INTO gpx_traces
			(trace_id, chauffeur_id, latitude, longitude, elevation,
			 recorded_at, speed_kmh, bearing, geom)
		VALUES ($1,$2,$3::double precision,$4::double precision,$5,$6,$7,$8,
			ST_SetSRID(ST_MakePoint($4::double precision,$3::double precision),4326))`

	n := 0
	for _, p := range pts {
		var recorded any
		if p.RecordedAt != nil {
			recorded = *p.RecordedAt
		}
		if _, err := tx.Exec(ctx, q,
			traceID, chauffeurID, p.Latitude, p.Longitude,
			p.Elevation, recorded, p.SpeedKmh, p.Bearing,
		); err != nil {
			return n, err
		}
		n++
	}
	if err := tx.Commit(ctx); err != nil {
		return n, err
	}
	return n, nil
}

// TracePoint is a stored point row.
type TracePoint struct {
	ID          int64      `json:"id"`
	TraceID     string     `json:"trace_id"`
	ChauffeurID string     `json:"chauffeur_id"`
	Latitude    float64    `json:"latitude"`
	Longitude   float64    `json:"longitude"`
	Elevation   *float64   `json:"elevation"`
	RecordedAt  *time.Time `json:"recorded_at"`
	SpeedKmh    *float64   `json:"speed_kmh"`
	Bearing     *float64   `json:"bearing"`
}

// GetTrace returns all points for a trace ordered by time.
func (s *Store) GetTrace(ctx context.Context, traceID string) ([]TracePoint, error) {
	const q = `
		SELECT id, trace_id, chauffeur_id, latitude, longitude,
		       elevation, recorded_at, speed_kmh, bearing
		FROM gpx_traces WHERE trace_id=$1 ORDER BY recorded_at`
	rows, err := s.pool.Query(ctx, q, traceID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []TracePoint
	for rows.Next() {
		var t TracePoint
		if err := rows.Scan(&t.ID, &t.TraceID, &t.ChauffeurID, &t.Latitude,
			&t.Longitude, &t.Elevation, &t.RecordedAt, &t.SpeedKmh, &t.Bearing); err != nil {
			return nil, err
		}
		out = append(out, t)
	}
	return out, rows.Err()
}
