# Build en dos etapas: la primera ejecuta los tests y compila, y la segunda solo lleva el binario.
# Si un test falla, la imagen no se construye.
FROM golang:1.27.3-bookworm@sha256:dc0963f32053e4bc451d24d87e3892d42d01021b61f093e98eb95c0352bb84b0 AS builder
WORKDIR /build
COPY go.mod ./
COPY cmd ./cmd
COPY internal ./internal
RUN go vet ./... && go test ./...
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/server ./cmd/server

# Imagen final sin shell ni gestor de paquetes.
FROM gcr.io/distroless/static-debian12:nonroot@sha256:afa5c872c891853ca7fcf1f12c3edb23f7eeef36189728842dd51042ff57f7ab
WORKDIR /app
COPY --from=builder /out/server /app/server
ENV PORT=8000
# Obligatorio: usuario numérico distinto de 0. El cluster rechaza contenedores root.
USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["/app/server"]
