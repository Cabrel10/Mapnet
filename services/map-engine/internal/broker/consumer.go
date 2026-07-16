// Package broker consumes gps.raw and aggregates points per trace into windows.
package broker

import (
	"context"
	"encoding/json"
	"log"
	"sync"
	"time"

	"github.com/segmentio/kafka-go"
)

// RawPoint is a decoded gps.raw message.
type RawPoint struct {
	TraceID     string   `json:"trace_id"`
	ChauffeurID string   `json:"chauffeur_id"`
	Latitude    *float64 `json:"latitude"`
	Longitude   *float64 `json:"longitude"`
	RecordedAt  *string  `json:"recorded_at"`
}

// Consumer reads gps.raw and flushes trace windows to a handler.
type Consumer struct {
	reader    *kafka.Reader
	maxPoints int
	timeout   time.Duration
	windows   map[string][]RawPoint
	mu        sync.Mutex
}

// NewConsumer builds a group consumer on the raw topic.
func NewConsumer(bootstrap, topic, group string, maxPoints int, timeout time.Duration) *Consumer {
	return &Consumer{
		reader: kafka.NewReader(kafka.ReaderConfig{
			Brokers:     []string{bootstrap},
			Topic:       topic,
			GroupID:     group,
			StartOffset: kafka.FirstOffset,
			MinBytes:    1,
			MaxBytes:    10e6,
		}),
		maxPoints: maxPoints,
		timeout:   timeout,
		windows:   map[string][]RawPoint{},
	}
}

// Close stops the reader.
func (c *Consumer) Close() error { return c.reader.Close() }

// Handler processes a completed trace window.
type Handler func(traceID string, points []RawPoint)

// Run blocks reading messages until ctx is cancelled, flushing windows either
// when they reach maxPoints or when the read poll times out.
func (c *Consumer) Run(ctx context.Context, h Handler) error {
	for {
		select {
		case <-ctx.Done():
			c.flushAll(h)
			return ctx.Err()
		default:
		}

		readCtx, cancel := context.WithTimeout(ctx, c.timeout)
		m, err := c.reader.ReadMessage(readCtx)
		cancel()
		if err != nil {
			if ctx.Err() != nil {
				c.flushAll(h)
				return ctx.Err()
			}
			// timeout with no message -> flush pending windows
			c.flushAll(h)
			continue
		}

		var rp RawPoint
		if err := json.Unmarshal(m.Value, &rp); err != nil {
			log.Printf("skip invalid message: %v", err)
			continue
		}
		if rp.TraceID == "" || rp.Latitude == nil || rp.Longitude == nil {
			continue
		}

		c.mu.Lock()
		c.windows[rp.TraceID] = append(c.windows[rp.TraceID], rp)
		full := len(c.windows[rp.TraceID]) >= c.maxPoints
		var window []RawPoint
		if full {
			window = c.windows[rp.TraceID]
			delete(c.windows, rp.TraceID)
		}
		c.mu.Unlock()

		if full {
			h(rp.TraceID, window)
		}
	}
}

func (c *Consumer) flushAll(h Handler) {
	c.mu.Lock()
	pending := c.windows
	c.windows = map[string][]RawPoint{}
	c.mu.Unlock()
	for tid, pts := range pending {
		if len(pts) > 0 {
			h(tid, pts)
		}
	}
}
