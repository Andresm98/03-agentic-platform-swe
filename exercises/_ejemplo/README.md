# Ejercicio de ejemplo (Go)

Esta carpeta es la referencia de lo que debes subir. **No la modifiques:** cópiala y adáptala.
Las instrucciones completas están en [exercises/README.md](../README.md).

```
exercises/<tu-nombre>/
├── Dockerfile              Build en dos etapas; la imagen final corre con usuario numérico, no root
├── exercise.yaml           owner, port y description; nada más
├── README.md               Qué hace tu aplicación
├── .dockerignore           Lo que no debe entrar en la imagen
├── go.mod                  Módulo de Go
├── internal/service/       Lógica, sin HTTP, con sus tests
└── cmd/server/             Servidor HTTP, con sus tests
```

Los tests se ejecutan durante el build: si fallan, la imagen no se construye.

Puedes usar otro lenguaje mientras cumplas el contrato: escuchar en el puerto de `exercise.yaml`
y responder `200` en `/healthz` y `/readyz`.

Si añades dependencias de Go, incluye `go.sum` y cópialo en el `Dockerfile` junto a `go.mod`.
Durante el build sí hay acceso a Internet para descargarlas; en ejecución, no.

Pruébalo en tu máquina:

```bash
docker build -t mi-ejercicio .
docker run --rm -p 8000:8000 --read-only --user 10001 mi-ejercicio
curl http://localhost:8000/
```
