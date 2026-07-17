// Package broker wraps a Kafka producer for GPS raw events.
// Uses segmentio/kafka-go (pure Go, no CGo) — justified: Kafka client.
package broker

import (
	"context"
	"encoding/json"
	"time"

	"github.com/segmentio/kafka-go"
)

// Producer publishes GPS points to the raw topic.
type Producer struct {
	w *kafka.Writer
}

// NewProducer builds a writer targeting the given bootstrap servers and topic.
func NewProducer(bootstrap, topic string) *Producer {
	return &Producer{
		w: &kafka.Writer{
			Addr:                   kafka.TCP(bootstrap),
			Topic:                  topic,
			Balancer:               &kafka.Hash{}, // key-based partitioning by trace_id
			AllowAutoTopicCreation: true,
			BatchTimeout:           50 * time.Millisecond,
			RequiredAcks:           kafka.RequireAll,
		},
	}
}

// Publish sends one JSON payload keyed by traceID. Blocking with a bounded ctx.
func (p *Producer) Publish(ctx context.Context, traceID string, payload any) error {
	b, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	return p.w.WriteMessages(ctx, kafka.Message{
		Key:   []byte(traceID),
		Value: b,
	})
}

// Ping verifies broker reachability by dialing the bootstrap address.
func (p *Producer) Ping(ctx context.Context, bootstrap string) error {
	d := &kafka.Dialer{Timeout: 3 * time.Second}
	conn, err := d.DialContext(ctx, "tcp", bootstrap)
	if err != nil {
		return err
	}
	defer conn.Close()
	_, err = conn.Brokers()
	return err
}

// Close flushes and closes the writer.
func (p *Producer) Close() error { return p.w.Close() }
