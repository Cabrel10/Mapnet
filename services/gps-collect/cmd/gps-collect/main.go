// gps-collect: MapNet GPS collection service.
// Accepts GPX uploads, persists points to PostGIS and publishes them to Kafka.
// Stdlib net/http only (Directive 6) — no web framework needed for 3 routes.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/google/uuid"

	"github.com/Cabrel10/Mapnet/services/gps-collect/internal/broker"
	"github.com/Cabrel10/Mapnet/services/gps-collect/internal/gpx"
	"github.com/Cabrel10/Mapnet/services/gps-collect/internal/store"
)

const maxUploadBytes = 32 << 20 // 32 MiB cap on GPX upload

type server struct {
	db        *store.Store
	prod      *broker.Producer
	bootstrap string
}

func env(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func main() {
	port := env("PORT", "8081")
	dsn := env("DATABASE_URL", "postgres://postgres:secure_password@localhost:5432/quamtechs_db")
	bootstrap := env("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
	topic := env("KAFKA_TOPIC_GPS_RAW", "quamtechs.mapnet.gps.raw")

	ctx := context.Background()
	db, err := store.New(ctx, dsn)
	if err != nil {
		log.Fatalf("db init: %v", err)
	}
	defer db.Close()

	prod := broker.NewProducer(bootstrap, topic)
	defer prod.Close()

	s := &server{db: db, prod: prod, bootstrap: bootstrap}

	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", s.health)
	mux.HandleFunc("POST /api/v1/collecte/gpx/upload", s.uploadGPX)
	mux.HandleFunc("GET /api/v1/traces/{trace_id}", s.getTrace)

	srv := &http.Server{
		Addr:              ":" + port,
		Handler:           withCORS(mux),
		ReadHeaderTimeout: 10 * time.Second,
	}
	log.Printf("gps-collect listening on :%s", port)
	log.Fatal(srv.ListenAndServe())
}

// withCORS enables the browser frontend to upload GPX cross-origin (local test).
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

func writeErr(w http.ResponseWriter, code int, msg string) {
	writeJSON(w, code, map[string]string{"error": msg})
}

func (s *server) health(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer cancel()

	dbStatus, kafkaStatus := "ok", "ok"
	if err := s.db.Ping(ctx); err != nil {
		dbStatus = "error"
	}
	if err := s.prod.Ping(ctx, s.bootstrap); err != nil {
		kafkaStatus = "error"
	}
	code := http.StatusOK
	if dbStatus != "ok" || kafkaStatus != "ok" {
		code = http.StatusServiceUnavailable
	}
	writeJSON(w, code, map[string]string{
		"status": "ok", "service": "gps-collect", "db": dbStatus, "kafka": kafkaStatus,
	})
}

type uploadResponse struct {
	TraceID         string `json:"trace_id"`
	PointsReceived  int    `json:"points_received"`
	PointsPublished int    `json:"points_published"`
	ChauffeurID     string `json:"chauffeur_id"`
}

func (s *server) uploadGPX(w http.ResponseWriter, r *http.Request) {
	if err := r.ParseMultipartForm(maxUploadBytes); err != nil {
		writeErr(w, http.StatusBadRequest, "invalid multipart form")
		return
	}
	chauffeurID := strings.TrimSpace(r.FormValue("chauffeur_id"))
	if chauffeurID == "" {
		writeErr(w, http.StatusBadRequest, "chauffeur_id is required")
		return
	}

	file, hdr, err := r.FormFile("file")
	if err != nil {
		writeErr(w, http.StatusBadRequest, "file is required")
		return
	}
	defer file.Close()

	if !strings.HasSuffix(strings.ToLower(hdr.Filename), ".gpx") {
		writeErr(w, http.StatusBadRequest, "only .gpx files are accepted")
		return
	}

	pts, err := gpx.Parse(io.LimitReader(file, maxUploadBytes))
	if err != nil {
		writeErr(w, http.StatusBadRequest, err.Error())
		return
	}
	if len(pts) == 0 {
		writeErr(w, http.StatusBadRequest, "no valid track points found in GPX")
		return
	}

	traceID := uuid.NewString()
	ctx := r.Context()

	if _, err := s.db.InsertPoints(ctx, traceID, chauffeurID, pts); err != nil {
		log.Printf("db insert: %v", err)
		writeErr(w, http.StatusInternalServerError, "failed to persist trace")
		return
	}

	published := 0
	for _, p := range pts {
		payload := map[string]any{
			"trace_id": traceID, "chauffeur_id": chauffeurID,
			"latitude": p.Latitude, "longitude": p.Longitude,
			"elevation": p.Elevation, "recorded_at": p.RecordedAt,
			"speed_kmh": p.SpeedKmh, "bearing": p.Bearing,
		}
		pctx, cancel := context.WithTimeout(ctx, 5*time.Second)
		err := s.prod.Publish(pctx, traceID, payload)
		cancel()
		if err != nil {
			log.Printf("kafka publish: %v", err)
			continue
		}
		published++
	}

	writeJSON(w, http.StatusOK, uploadResponse{
		TraceID: traceID, PointsReceived: len(pts),
		PointsPublished: published, ChauffeurID: chauffeurID,
	})
}

func (s *server) getTrace(w http.ResponseWriter, r *http.Request) {
	traceID := r.PathValue("trace_id")
	rows, err := s.db.GetTrace(r.Context(), traceID)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "query failed")
		return
	}
	if len(rows) == 0 {
		writeErr(w, http.StatusNotFound, "trace not found")
		return
	}
	writeJSON(w, http.StatusOK, rows)
}

var _ = errors.New // keep errors import stable across edits
