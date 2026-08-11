// Package store persists GPX traces into PostGIS via pgx.
// pgx justified: high-performance Postgres driver (Directive 6 allows it over gorm).
package store

import (
	"context"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/Cabrel10/Mapnet/services/gps-collect/internal/gpx"
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

// EnsurePositionsTable creates the agent_positions table if absent.
// Called at startup so the service is self-initializing (no manual SQL step).
func (s *Store) EnsurePositionsTable(ctx context.Context) error {
	const q = `
		CREATE TABLE IF NOT EXISTS agent_positions (
			id BIGSERIAL PRIMARY KEY,
			agent_id TEXT NOT NULL,
			latitude DOUBLE PRECISION NOT NULL,
			longitude DOUBLE PRECISION NOT NULL,
			accuracy DOUBLE PRECISION,
			speed_kmh DOUBLE PRECISION,
			bearing DOUBLE PRECISION,
			recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
			geom GEOGRAPHY(POINT,4326)
		);
		CREATE INDEX IF NOT EXISTS idx_agent_positions_agent ON agent_positions(agent_id);
		CREATE INDEX IF NOT EXISTS idx_agent_positions_time ON agent_positions(recorded_at DESC);
		CREATE INDEX IF NOT EXISTS idx_agent_positions_geom ON agent_positions USING GIST(geom);`
	_, err := s.pool.Exec(ctx, q)
	return err
}

// PositionUpdate is one live position report from a field agent.
type PositionUpdate struct {
	AgentID    string     `json:"agent_id"`
	Latitude   float64    `json:"lat"`
	Longitude  float64    `json:"lon"`
	Accuracy   *float64   `json:"accuracy"`
	SpeedKmh   *float64   `json:"speed_kmh"`
	Bearing    *float64   `json:"bearing"`
	RecordedAt *time.Time `json:"timestamp"`
}

// InsertPosition persists one live agent position.
func (s *Store) InsertPosition(ctx context.Context, p PositionUpdate) error {
	var recorded any
	if p.RecordedAt != nil {
		recorded = *p.RecordedAt
	} else {
		recorded = time.Now().UTC()
	}
	const q = `
		INSERT INTO agent_positions
			(agent_id, latitude, longitude, accuracy, speed_kmh, bearing, recorded_at, geom)
		VALUES ($1,$2::double precision,$3::double precision,$4,$5,$6,$7,
			ST_SetSRID(ST_MakePoint($3::double precision,$2::double precision),4326))`
	_, err := s.pool.Exec(ctx, q,
		p.AgentID, p.Latitude, p.Longitude, p.Accuracy, p.SpeedKmh, p.Bearing, recorded)
	return err
}

// AgentPosition is the latest known position of one agent.
type AgentPosition struct {
	AgentID    string    `json:"agent_id"`
	Latitude   float64   `json:"lat"`
	Longitude  float64   `json:"lon"`
	Accuracy   *float64  `json:"accuracy"`
	RecordedAt time.Time `json:"timestamp"`
}

// LatestPositions returns the most recent position per agent within the window.
func (s *Store) LatestPositions(ctx context.Context, windowMinutes int) ([]AgentPosition, error) {
	const q = `
		SELECT DISTINCT ON (agent_id)
			agent_id, latitude, longitude, accuracy, recorded_at
		FROM agent_positions
		WHERE recorded_at > now() - ($1::int * interval '1 minute')
		ORDER BY agent_id, recorded_at DESC`
	rows, err := s.pool.Query(ctx, q, windowMinutes)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	out := []AgentPosition{}
	for rows.Next() {
		var a AgentPosition
		if err := rows.Scan(&a.AgentID, &a.Latitude, &a.Longitude, &a.Accuracy, &a.RecordedAt); err != nil {
			return nil, err
		}
		out = append(out, a)
	}
	return out, rows.Err()
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
