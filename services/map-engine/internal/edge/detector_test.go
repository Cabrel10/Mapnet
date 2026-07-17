package edge

import "testing"

// fakeChecker treats any point with lat < 0 as "on an existing road".
type fakeChecker struct{}

func (fakeChecker) HasNearby(lat, lon, r float64) bool { return lat < 0 }

func TestDetectOffRoadRun(t *testing.T) {
	pts := []Point{
		{Lat: 3.85, Lon: 11.50}, // off-road
		{Lat: 3.86, Lon: 11.51}, // off-road
		{Lat: -1, Lon: 11.52},   // snaps -> closes segment (2 pts)
		{Lat: 3.87, Lon: 11.53}, // off-road (single, dropped)
	}
	c := Detect(pts, fakeChecker{}, 15)
	if len(c) != 1 {
		t.Fatalf("want 1 candidate, got %d", len(c))
	}
	if len(c[0].Geometry.Coordinates) != 2 {
		t.Fatalf("want 2 coords, got %d", len(c[0].Geometry.Coordinates))
	}
	if c[0].Status != "non_cartographie_osm" {
		t.Fatalf("bad status: %s", c[0].Status)
	}
}

func TestDetectAllOnRoad(t *testing.T) {
	pts := []Point{{Lat: -1, Lon: 1}, {Lat: -2, Lon: 2}}
	if got := Detect(pts, fakeChecker{}, 15); got != nil {
		t.Fatalf("expected no candidates, got %d", len(got))
	}
}

func TestDetectTooFewPoints(t *testing.T) {
	if got := Detect([]Point{{Lat: 1, Lon: 1}}, fakeChecker{}, 15); got != nil {
		t.Fatal("expected nil for <2 points")
	}
}
