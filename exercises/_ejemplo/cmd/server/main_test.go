package main

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"example.com/ejercicio/internal/service"
)

func TestRoutes(t *testing.T) {
	mux := newMux("pod-1", &service.RequestCounter{})

	cases := map[string]int{
		"/":        http.StatusOK,
		"/healthz": http.StatusOK,
		"/readyz":  http.StatusOK,
		"/metrics": http.StatusOK,
		"/nope":    http.StatusNotFound,
	}
	for path, want := range cases {
		recorder := httptest.NewRecorder()
		mux.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, path, nil))
		if recorder.Code != want {
			t.Errorf("GET %s = %d, se esperaba %d", path, recorder.Code, want)
		}
	}
}
