// Package edge detects candidate new road edges from map-matched traces.
// The core segmentation is pure logic (Directive 3 exception): a point that
// snaps to no existing OSM edge starts/continues an "off-road" segment; when
// the run reaches >=2 points it becomes a candidate edge.
package edge

import (
	"crypto/rand"
	"encoding/hex"
)

// Point is a lat/lon coordinate.
type Point struct {
	Lat float64
	Lon float64
}

// Candidate is a detected off-road segment as a GeoJSON LineString.
type Candidate struct {
	EdgeID            string      `json:"edge_id"`
	Geometry          LineString  `json:"geometry"`
	Status            string      `json:"status"`
	ConfirmationCount int         `json:"confirmation_count"`
	Coords            [][]float64 `json:"-"` // [lon,lat] pairs for DB insert
}

// LineString is a minimal GeoJSON LineString.
type LineString struct {
	Type        string      `json:"type"`
	Coordinates [][]float64 `json:"coordinates"`
}

// NearbyChecker reports whether a point is within threshold of an existing edge.
type NearbyChecker interface {
	HasNearby(lat, lon, radiusM float64) bool
}

func newEdgeID() string {
	b := make([]byte, 6)
	_, _ = rand.Read(b)
	return "mapnet-" + hex.EncodeToString(b)
}

// Detect walks the ordered trace and returns candidate edges for every run of
// >=2 consecutive off-road points. thresholdM is the snap distance in metres.
func Detect(pts []Point, nc NearbyChecker, thresholdM float64) []Candidate {
	if len(pts) < 2 {
		return nil
	}
	var out []Candidate
	var seg [][]float64 // [lon,lat]

	flush := func() {
		if len(seg) >= 2 {
			out = append(out, buildCandidate(seg))
		}
		seg = nil
	}

	for _, p := range pts {
		if nc.HasNearby(p.Lat, p.Lon, thresholdM) {
			flush() // snapped to existing road -> close current off-road run
			continue
		}
		seg = append(seg, []float64{p.Lon, p.Lat})
	}
	flush()
	return out
}

func buildCandidate(coords [][]float64) Candidate {
	// copy to avoid aliasing the shared slice across candidates
	cp := make([][]float64, len(coords))
	copy(cp, coords)
	return Candidate{
		EdgeID:            newEdgeID(),
		Geometry:          LineString{Type: "LineString", Coordinates: cp},
		Status:            "non_cartographie_osm",
		ConfirmationCount: 1,
		Coords:            cp,
	}
}
