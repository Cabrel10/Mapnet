package gpx

import (
	"strings"
	"testing"
)

const sample = `<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="GPS Logger" xmlns="http://www.topografix.com/GPX/1/1">
  <trk>
    <name>Trajet_Benskin_Ndokoti</name>
    <trkseg>
      <trkpt lat="3.8480" lon="11.5021"><ele>720.5</ele><time>2026-07-16T12:00:00Z</time></trkpt>
      <trkpt lat="3.8481" lon="11.5022"><ele>721.0</ele><time>2026-07-16T12:00:10Z</time></trkpt>
    </trkseg>
  </trk>
</gpx>`

func TestParse(t *testing.T) {
	pts, err := Parse(strings.NewReader(sample))
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if len(pts) != 2 {
		t.Fatalf("want 2 points, got %d", len(pts))
	}
	if pts[0].Latitude != 3.8480 || pts[0].Longitude != 11.5021 {
		t.Fatalf("bad first coord: %+v", pts[0])
	}
	if pts[0].Elevation == nil || *pts[0].Elevation != 720.5 {
		t.Fatalf("bad elevation: %+v", pts[0].Elevation)
	}
	if pts[1].SpeedKmh == nil || pts[1].Bearing == nil {
		t.Fatalf("expected kinematics on 2nd point: %+v", pts[1])
	}
	if *pts[1].SpeedKmh <= 0 {
		t.Fatalf("expected positive speed, got %v", *pts[1].SpeedKmh)
	}
}

func TestHaversine(t *testing.T) {
	d := Haversine(3.8480, 11.5021, 3.8481, 11.5022)
	if d <= 0 || d >= 50 {
		t.Fatalf("distance out of range: %v", d)
	}
}

func TestBearingRange(t *testing.T) {
	b := Bearing(3.8480, 11.5021, 3.8481, 11.5022)
	if b < 0 || b >= 360 {
		t.Fatalf("bearing out of range: %v", b)
	}
}

func TestParseInvalid(t *testing.T) {
	if _, err := Parse(strings.NewReader("<gpx><trkpt")); err == nil {
		t.Fatal("expected error on malformed XML")
	}
}
