// Package routing calls the routing service for map matching, wrapped in a
// simple circuit breaker (Directive: résilience systématique).
package routing

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"sync"
	"time"
)

// Client talks to the routing service map-match endpoint.
type Client struct {
	baseURL string
	http    *http.Client
	cb      *breaker
}

// NewClient builds a routing client with a 60s HTTP timeout.
func NewClient(baseURL string) *Client {
	return &Client{
		baseURL: baseURL,
		http:    &http.Client{Timeout: 60 * time.Second},
		cb:      newBreaker(5, 30*time.Second),
	}
}

// MatchResult is the routing service response subset we consume.
type MatchResult struct {
	Matchings []struct {
		Geometry json.RawMessage `json:"geometry"`
	} `json:"matchings"`
}

// ErrOpen is returned when the circuit breaker is open.
var ErrOpen = errors.New("routing circuit open")

// MapMatch posts points and returns matched geometries.
func (c *Client) MapMatch(ctx context.Context, points any) (*MatchResult, error) {
	if !c.cb.allow() {
		return nil, ErrOpen
	}
	body, err := json.Marshal(map[string]any{"points": points})
	if err != nil {
		return nil, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		c.baseURL+"/api/v1/routing/map-match", bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.http.Do(req)
	if err != nil {
		c.cb.fail()
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 500 {
		c.cb.fail()
		return nil, errors.New("routing service error")
	}
	c.cb.success()

	var out MatchResult
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, err
	}
	return &out, nil
}

// breaker is a minimal count-based circuit breaker.
type breaker struct {
	mu        sync.Mutex
	failures  int
	threshold int
	openUntil time.Time
	cooldown  time.Duration
}

func newBreaker(threshold int, cooldown time.Duration) *breaker {
	return &breaker{threshold: threshold, cooldown: cooldown}
}

func (b *breaker) allow() bool {
	b.mu.Lock()
	defer b.mu.Unlock()
	return time.Now().After(b.openUntil)
}

func (b *breaker) fail() {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.failures++
	if b.failures >= b.threshold {
		b.openUntil = time.Now().Add(b.cooldown)
		b.failures = 0
	}
}

func (b *breaker) success() {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.failures = 0
}
