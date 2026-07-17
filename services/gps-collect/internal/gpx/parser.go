// Package gpx implements a streaming GPX parser with kinematic enrichment
// (speed + bearing) computed from consecutive track points.
package gpx

import (
	"encoding/xml"
	"errors"
	"io"
	"math"
	"time"
)

// Point is an enriched GPX track point.
type Point struct {
	Latitude   float64    `json:"latitude"`
	Longitude  float64    `json:"longitude"`
	Elevation  *float64   `json:"elevation"`
	RecordedAt *time.Time `json:"recorded_at"`
	SpeedKmh   *float64   `json:"speed_kmh"`
	Bearing    *float64   `json:"bearing"`
}

// xmlTrkpt mirrors the <trkpt> element for encoding/xml streaming.
type xmlTrkpt struct {
	Lat float64 `xml:"lat,attr"`
	Lon float64 `xml:"lon,attr"`
	Ele *string `xml:"ele"`
	// Local name "time" matched regardless of namespace via Decoder token walk.
	Time *string `xml:"time"`
}

const earthRadiusM = 6371000.0

// Haversine returns the great-circle distance in metres between two points.
func Haversine(lat1, lon1, lat2, lon2 float64) float64 {
	phi1 := lat1 * math.Pi / 180
	phi2 := lat2 * math.Pi / 180
	dphi := (lat2 - lat1) * math.Pi / 180
	dlambda := (lon2 - lon1) * math.Pi / 180
	a := math.Sin(dphi/2)*math.Sin(dphi/2) +
		math.Cos(phi1)*math.Cos(phi2)*math.Sin(dlambda/2)*math.Sin(dlambda/2)
	return 2 * earthRadiusM * math.Atan2(math.Sqrt(a), math.Sqrt(1-a))
}

// Bearing returns the initial bearing in degrees [0,360).
func Bearing(lat1, lon1, lat2, lon2 float64) float64 {
	phi1 := lat1 * math.Pi / 180
	phi2 := lat2 * math.Pi / 180
	dlambda := (lon2 - lon1) * math.Pi / 180
	x := math.Sin(dlambda) * math.Cos(phi2)
	y := math.Cos(phi1)*math.Sin(phi2) - math.Sin(phi1)*math.Cos(phi2)*math.Cos(dlambda)
	return math.Mod(math.Atan2(x, y)*180/math.Pi+360, 360)
}

func round2(v float64) float64 { return math.Round(v*100) / 100 }

func parseTime(s string) *time.Time {
	// Accept RFC3339 with or without fractional seconds; "Z" or offset.
	for _, layout := range []string{time.RFC3339Nano, time.RFC3339, "2006-01-02T15:04:05Z"} {
		if t, err := time.Parse(layout, s); err == nil {
			u := t.UTC()
			return &u
		}
	}
	return nil
}

// Parse decodes GPX content as a stream, yielding enriched track points.
// It uses encoding/xml token streaming so large files never load fully into
// structured memory. Namespace is ignored (matches by local element name).
func Parse(r io.Reader) ([]Point, error) {
	dec := xml.NewDecoder(r)
	var points []Point
	var prev *Point

	for {
		tok, err := dec.Token()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, errors.New("invalid GPX XML: " + err.Error())
		}
		se, ok := tok.(xml.StartElement)
		if !ok || se.Name.Local != "trkpt" {
			continue
		}
		var raw xmlTrkpt
		if err := dec.DecodeElement(&raw, &se); err != nil {
			// Skip malformed point, keep streaming.
			continue
		}

		p := Point{Latitude: raw.Lat, Longitude: raw.Lon}
		if raw.Ele != nil {
			if v := parseFloat(*raw.Ele); v != nil {
				p.Elevation = v
			}
		}
		if raw.Time != nil {
			p.RecordedAt = parseTime(*raw.Time)
		}

		if prev != nil && prev.RecordedAt != nil && p.RecordedAt != nil {
			dt := p.RecordedAt.Sub(*prev.RecordedAt).Seconds()
			if dt > 0 {
				dist := Haversine(prev.Latitude, prev.Longitude, p.Latitude, p.Longitude)
				spd := round2((dist / dt) * 3.6)
				brg := round2(Bearing(prev.Latitude, prev.Longitude, p.Latitude, p.Longitude))
				p.SpeedKmh = &spd
				p.Bearing = &brg
			}
		}

		points = append(points, p)
		last := points[len(points)-1]
		prev = &last
	}
	return points, nil
}

func parseFloat(s string) *float64 {
	var v float64
	var neg bool
	i := 0
	if len(s) > 0 && (s[0] == '-' || s[0] == '+') {
		neg = s[0] == '-'
		i = 1
	}
	seen := false
	frac := 0.0
	scale := 1.0
	inFrac := false
	for ; i < len(s); i++ {
		c := s[i]
		switch {
		case c >= '0' && c <= '9':
			seen = true
			if inFrac {
				scale *= 10
				frac += float64(c-'0') / scale
			} else {
				v = v*10 + float64(c-'0')
			}
		case c == '.':
			inFrac = true
		default:
			// stop at first invalid char
			i = len(s)
		}
	}
	if !seen {
		return nil
	}
	res := v + frac
	if neg {
		res = -res
	}
	return &res
}
