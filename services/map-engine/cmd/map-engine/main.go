// map-engine: consumes gps.raw, map-matches traces via the routing service,
// detects off-road segments as new edges, and persists them to PostGIS.
// Also serves a small HTTP API for edge queries. Stdlib net/http.
package main

import (
	"context"
	"encoding/json"
	"log"
	"net/http"
	"os"
	"os/signal"
	"sort"
	"strconv"
	"syscall"
	"time"

	"github.com/Cabrel10/Mapnet/services/map-engine/internal/broker"
	"github.com/Cabrel10/Mapnet/services/map-engine/internal/edge"
	"github.com/Cabrel10/Mapnet/services/map-engine/internal/routing"
	"github.com/Cabrel10/Mapnet/services/map-engine/internal/store"
)

func env(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func envFloat(k string, def float64) float64 {
	if v, err := strconv.ParseFloat(env(k, ""), 64); err == nil {
		return v
	}
	return def
}

type api struct{ db *store.Store }

func main() {
	port := env("PORT", "8082")
	dsn := env("DATABASE_URL", "postgres://postgres:secure_password@localhost:5432/quamtechs_db")
	bootstrap := env("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
	rawTopic := env("KAFKA_TOPIC_GPS_RAW", "quamtechs.mapnet.gps.raw")
	group := env("KAFKA_GROUP_ID", "map-engine-consumer")
	routingURL := env("ROUTING_SERVICE_URL", "http://localhost:8085")
	threshold := envFloat("MAPMATCHING_THRESHOLD", 15.0)
	minConf, _ := strconv.Atoi(env("MIN_CONFIRMATIONS", "3"))

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	db, err := store.New(ctx, dsn, minConf)
	if err != nil {
		log.Fatalf("db init: %v", err)
	}
	defer db.Close()

	rc := routing.NewClient(routingURL)
	consumer := broker.NewConsumer(bootstrap, rawTopic, group, 50, 10*time.Second)
	defer consumer.Close()

	handler := func(traceID string, pts []broker.RawPoint) {
		process(ctx, db, rc, traceID, pts, threshold)
	}

	go func() {
		log.Printf("map-engine consumer started (topic=%s group=%s)", rawTopic, group)
		if err := consumer.Run(ctx, handler); err != nil && ctx.Err() == nil {
			log.Printf("consumer stopped: %v", err)
		}
	}()

	a := &api{db: db}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", a.health)
	mux.HandleFunc("GET /api/v1/map/edges/nearby", a.nearby)
	mux.HandleFunc("GET /api/v1/map/edges", a.list)
	mux.HandleFunc("GET /api/v1/map/edges.geojson", a.edgesGeoJSON)
	mux.HandleFunc("GET /api/v1/sync/manifest", a.manifest)
	mux.HandleFunc("GET /api/v1/sync/delta", a.mapDelta)

	srv := &http.Server{Addr: ":" + port, Handler: withCORS(mux), ReadHeaderTimeout: 10 * time.Second}
	go func() {
		<-ctx.Done()
		sctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = srv.Shutdown(sctx)
	}()

	log.Printf("map-engine HTTP listening on :%s", port)
	if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatal(err)
	}
}

// process runs map-matching + edge detection for a completed trace window.
func process(ctx context.Context, db *store.Store, rc *routing.Client,
	traceID string, pts []broker.RawPoint, threshold float64) {
	if len(pts) < 2 {
		return
	}
	// Order by recorded_at (nil sorts first, stable).
	sort.SliceStable(pts, func(i, j int) bool {
		ai, aj := "", ""
		if pts[i].RecordedAt != nil {
			ai = *pts[i].RecordedAt
		}
		if pts[j].RecordedAt != nil {
			aj = *pts[j].RecordedAt
		}
		return ai < aj
	})

	coords := make([]map[string]float64, 0, len(pts))
	for _, p := range pts {
		coords = append(coords, map[string]float64{"latitude": *p.Latitude, "longitude": *p.Longitude})
	}

	// Map-matching enriches traces with OSM geometry, but its unavailability
	// must NOT block new-road discovery (résilience systématique). On error we
	// log and still run off-road edge detection from the raw points below.
	mctx, cancel := context.WithTimeout(ctx, 60*time.Second)
	defer cancel()
	if res, err := rc.MapMatch(mctx, coords); err != nil {
		log.Printf("map-match trace %s (continuing to edge detection): %v", traceID, err)
	} else {
		for _, m := range res.Matchings {
			if len(m.Geometry) == 0 {
				continue
			}
			if err := db.StoreMatched(ctx, traceID, m.Geometry); err != nil {
				log.Printf("store matched %s: %v", traceID, err)
			}
		}
	}

	// Off-road detection uses raw points against existing edges.
	ep := make([]edge.Point, 0, len(pts))
	for _, p := range pts {
		ep = append(ep, edge.Point{Lat: *p.Latitude, Lon: *p.Longitude})
	}
	for _, c := range edge.Detect(ep, db, threshold) {
		if err := db.UpsertCandidate(ctx, c); err != nil {
			log.Printf("upsert candidate %s: %v", c.EdgeID, err)
			continue
		}
		log.Printf("new edge candidate %s (%d pts) trace=%s", c.EdgeID, len(c.Coords), traceID)
	}
}

// withCORS allows the browser frontend (served from a different origin) to
// call this API for local testing of latency, bandwidth and bottlenecks.
func withCORS(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

func (a *api) health(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer cancel()
	st, code := "ok", http.StatusOK
	if err := a.db.Ping(ctx); err != nil {
		st, code = "error", http.StatusServiceUnavailable
	}
	writeJSON(w, code, map[string]string{"status": st, "service": "map-engine"})
}

func (a *api) nearby(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	lat, _ := strconv.ParseFloat(q.Get("lat"), 64)
	lon, _ := strconv.ParseFloat(q.Get("lon"), 64)
	radius := 15.0
	if v, err := strconv.ParseFloat(q.Get("radius"), 64); err == nil {
		radius = v
	}
	edges, err := a.db.NearbyEdges(r.Context(), lat, lon, radius)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "query failed"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok", "count": len(edges), "edges": edges})
}

func (a *api) list(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	status := q.Get("status")
	limit := 100
	if v, err := strconv.Atoi(q.Get("limit")); err == nil && v > 0 {
		limit = v
	}
	edges, err := a.db.ListEdges(r.Context(), status, limit)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "query failed"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok", "count": len(edges), "edges": edges})
}

// edgesGeoJSON serves all edges as a GeoJSON FeatureCollection for MapLibre.
func (a *api) edgesGeoJSON(w http.ResponseWriter, r *http.Request) {
	limit := 5000
	if v, err := strconv.Atoi(r.URL.Query().Get("limit")); err == nil && v > 0 {
		limit = v
	}
	fc, err := a.db.EdgesGeoJSON(r.Context(), limit)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "geojson failed"})
		return
	}
	w.Header().Set("Content-Type", "application/geo+json")
	_, _ = w.Write(fc)
}

// manifest returns the current version of every dataset (Git-like HEAD).
// Mobile clients call this first, then request deltas for datasets they lag on.
func (a *api) manifest(w http.ResponseWriter, r *http.Request) {
	versions, err := a.db.Manifest(r.Context())
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "manifest failed"})
		return
	}
	m := map[string]int64{}
	for _, v := range versions {
		m[v.Dataset] = v.Version
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok", "versions": m})
}

// mapDelta returns only edge changes newer than ?since=vN, geometry as encoded
// polyline. This is the offline-sync transmission core: no full download, ever.
func (a *api) mapDelta(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	since, _ := strconv.ParseInt(q.Get("since"), 10, 64)
	limit := 1000
	if v, err := strconv.Atoi(q.Get("limit")); err == nil && v > 0 && v <= 5000 {
		limit = v
	}
	deltas, head, err := a.db.MapDelta(r.Context(), since, limit)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "delta failed"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"status":         "ok",
		"dataset":        "map",
		"since":          since,
		"head":           head,
		"count":          len(deltas),
		"has_more":       len(deltas) == limit,
		"changes":        deltas,
	})
}
