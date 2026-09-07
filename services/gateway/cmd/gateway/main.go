// MAPNET
//
// Repository:
// github.com/Cabrel10/Mapnet
//
// gateway is the single HTTP entrypoint for the MAPNET browser client.
// It serves the static frontend and reverse-proxies API traffic to the
// backend microservices, so the browser only ever talks to one origin
// (no CORS, no hard-coded localhost ports).
//
//	/               -> static frontend (mapnet.html)
//	/assets/*       -> static assets
//	/api/gps/*        -> gps-collect   (GPX ingestion)
//	/api/map/*        -> map-engine    (edges + versioned sync)
//	/api/route/*      -> routing       (itineraries: route, nearest, map-match)
//	/api/v1/places/*  -> places        (search, building-at, nearest-district, categories, status)
//	/tiles/*          -> pg_tileserv   (PostGIS vector tiles: buildings, POIs, roads, districts)
//	/health           -> gateway liveness
package main

import (
	"log"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"
)

func env(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

// resolveStaticDir returns the first existing candidate directory that holds
// the built frontend (mapnet.html). It probes, in order:
//  1. ./services/web-frontend/public   (gateway launched from the repo root)
//  2. ../../web-frontend/public         (gateway launched from services/gateway)
//  3. dir(executable)/../web-frontend/public
//
// If none exist it returns the first candidate so the log makes the missing
// path obvious instead of silently 404-ing on an unrelated /home/<user> path.
func resolveStaticDir() string {
	candidates := []string{
		"services/web-frontend/public",
		filepath.Join("..", "..", "web-frontend", "public"),
	}
	if exe, err := os.Executable(); err == nil {
		candidates = append(candidates,
			filepath.Join(filepath.Dir(exe), "..", "web-frontend", "public"))
	}
	if wd, err := os.Getwd(); err == nil {
		candidates = append(candidates,
			filepath.Join(wd, "services", "web-frontend", "public"))
	}
	for _, c := range candidates {
		if st, err := os.Stat(filepath.Join(c, "mapnet.html")); err == nil && !st.IsDir() {
			if abs, err := filepath.Abs(c); err == nil {
				return abs
			}
			return c
		}
	}
	return candidates[0]
}

// newProxy builds a reverse proxy to target, stripping stripPrefix from the
// incoming path so /api/gps/... reaches the backend as /...
func newProxy(target, stripPrefix string) (*httputil.ReverseProxy, error) {
	u, err := url.Parse(target)
	if err != nil {
		return nil, err
	}
	p := httputil.NewSingleHostReverseProxy(u)
	base := p.Director
	p.Director = func(r *http.Request) {
		base(r)
		r.URL.Path = strings.TrimPrefix(r.URL.Path, stripPrefix)
		if !strings.HasPrefix(r.URL.Path, "/") {
			r.URL.Path = "/" + r.URL.Path
		}
		r.Host = u.Host
	}
	p.ErrorHandler = func(w http.ResponseWriter, r *http.Request, err error) {
		log.Printf("proxy error %s%s -> %s: %v", stripPrefix, r.URL.Path, target, err)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusBadGateway)
		_, _ = w.Write([]byte(`{"error":"upstream unavailable","upstream":"` + target + `"}`))
	}
	p.Transport = &http.Transport{
		DialContext:         (&net.Dialer{Timeout: 5 * time.Second}).DialContext,
		TLSHandshakeTimeout: 5 * time.Second,
	}
	return p, nil
}

func main() {
	port := env("PORT", "8080")
	// STATIC_DIR points at the built frontend served at "/". The default is
	// resolved relative to the gateway's working directory (the MAPNET repo
	// root) so it is not tied to a specific home directory. We probe a few
	// well-known locations and fall back to the repo-relative path.
	staticDir := env("STATIC_DIR", resolveStaticDir())
	gpsTarget := env("GPS_COLLECT_URL", "http://localhost:8081")
	mapTarget := env("MAP_ENGINE_URL", "http://localhost:8082")
	routeTarget := env("ROUTING_URL", "http://localhost:8093")
	placesTarget := env("PLACES_URL", "http://localhost:8083")
	tilesTarget := env("TILES_URL", "http://localhost:7800")

	gpsProxy, err := newProxy(gpsTarget, "/api/gps")
	if err != nil {
		log.Fatalf("gps proxy: %v", err)
	}
	mapProxy, err := newProxy(mapTarget, "/api/map")
	if err != nil {
		log.Fatalf("map proxy: %v", err)
	}
	routeProxy, err := newProxy(routeTarget, "/api/route")
	if err != nil {
		log.Fatalf("route proxy: %v", err)
	}
	// places keeps its full /api/v1/places prefix (the FastAPI service routes on
	// it), so we strip nothing.
	placesProxy, err := newProxy(placesTarget, "")
	if err != nil {
		log.Fatalf("places proxy: %v", err)
	}
	// pg_tileserv serves vector tiles at /public.<table>/{z}/{x}/{y}.pbf, so we
	// strip the /tiles prefix before proxying.
	tilesProxy, err := newProxy(tilesTarget, "/tiles")
	if err != nil {
		log.Fatalf("tiles proxy: %v", err)
	}

	mux := http.NewServeMux()
	mux.Handle("/api/gps/", gpsProxy)
	mux.Handle("/api/map/", mapProxy)
	mux.Handle("/api/route/", routeProxy)
	mux.Handle("/api/v1/places/", placesProxy)
	mux.Handle("/tiles/", tilesProxy)

	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"service":"gateway","status":"ok"}`))
	})

	// Serve the console at "/" and static assets everywhere else.
	fs := http.FileServer(http.Dir(staticDir))
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/" {
			http.ServeFile(w, r, filepath.Join(staticDir, "mapnet.html"))
			return
		}
		fs.ServeHTTP(w, r)
	})

	srv := &http.Server{
		Addr:              ":" + port,
		Handler:           mux,
		ReadHeaderTimeout: 10 * time.Second,
	}
	log.Printf("gateway listening on :%s (gps=%s map=%s route=%s places=%s tiles=%s static=%s)", port, gpsTarget, mapTarget, routeTarget, placesTarget, tilesTarget, staticDir)

	if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("listen: %v", err)
	}
}
