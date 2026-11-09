package service

import (
	"strings"
	"testing"
)

func TestNewGreetingIncludesPod(t *testing.T) {
	if got := NewGreeting("pod-1").Pod; got != "pod-1" {
		t.Fatalf("pod = %q, se esperaba pod-1", got)
	}
}

func TestCounterAppearsInMetrics(t *testing.T) {
	counter := &RequestCounter{}
	counter.Increment()

	if metrics := RenderMetrics(counter); !strings.Contains(metrics, "exercise_requests_total 1") {
		t.Fatalf("métricas sin el contador: %q", metrics)
	}
}
