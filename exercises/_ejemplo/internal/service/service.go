// Package service contiene la lógica de la aplicación. No sabe nada de HTTP,
// así que se prueba sin levantar un servidor.
package service

import (
	"fmt"
	"sync/atomic"
)

// Greeting es la respuesta de la ruta principal.
type Greeting struct {
	Message string `json:"message"`
	Pod     string `json:"pod"`
}

// RequestCounter cuenta peticiones de forma segura entre goroutines.
type RequestCounter struct {
	total atomic.Int64
}

// Increment suma una petición.
func (c *RequestCounter) Increment() {
	c.total.Add(1)
}

// Total devuelve las peticiones contadas.
func (c *RequestCounter) Total() int64 {
	return c.total.Load()
}

// NewGreeting construye la respuesta principal: cámbiala por la lógica de tu proyecto.
func NewGreeting(pod string) Greeting {
	return Greeting{Message: "Hola desde mi contenedor", Pod: pod}
}

// RenderMetrics devuelve las métricas en el formato de texto de Prometheus.
func RenderMetrics(counter *RequestCounter) string {
	return fmt.Sprintf(
		"# HELP exercise_requests_total Peticiones atendidas.\n"+
			"# TYPE exercise_requests_total counter\n"+
			"exercise_requests_total %d\n",
		counter.Total(),
	)
}
