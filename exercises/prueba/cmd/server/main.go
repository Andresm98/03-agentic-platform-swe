// Servidor HTTP: traduce las rutas a llamadas al paquete service.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"example.com/ejercicio/internal/service"
)

const shutdownTimeout = 10 * time.Second

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(body); err != nil {
		log.Printf("no se pudo escribir la respuesta: %v", err)
	}
}

func health(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func newMux(pod string, counter *service.RequestCounter) *http.ServeMux {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", health)
	mux.HandleFunc("GET /readyz", health)
	mux.HandleFunc("GET /metrics", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/plain; version=0.0.4")
		if _, err := io.WriteString(w, service.RenderMetrics(counter)); err != nil {
			log.Printf("no se pudieron escribir las métricas: %v", err)
		}
	})
	// {$} hace que esta ruta coincida solo con "/" exacto.
	mux.HandleFunc("GET /{$}", func(w http.ResponseWriter, _ *http.Request) {
		counter.Increment()
		writeJSON(w, http.StatusOK, service.NewGreeting(pod))
	})
	return mux
}

func envOr(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func run() error {
	server := &http.Server{
		Addr:              ":" + envOr("PORT", "8000"),
		Handler:           newMux(envOr("POD_NAME", "local"), &service.RequestCounter{}),
		ReadHeaderTimeout: 5 * time.Second,
	}

	// Kubernetes envía SIGTERM al parar el pod: se termina lo que esté en curso.
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, os.Interrupt)
	defer stop()

	failed := make(chan error, 1)
	go func() { failed <- server.ListenAndServe() }()

	select {
	case err := <-failed:
		return err
	case <-ctx.Done():
	}

	shutdownCtx, cancel := context.WithTimeout(context.Background(), shutdownTimeout)
	defer cancel()
	return server.Shutdown(shutdownCtx)
}

func main() {
	if err := run(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		log.Fatal(err)
	}
}
