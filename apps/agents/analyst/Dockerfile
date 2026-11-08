# syntax=docker/dockerfile:1
# Contexto de build: apps/. Multistage a distroless (ADR-0001 §3).
# Builder en Python 3.11 porque python3-debian12 trae 3.11.2 (verificado con `docker run`).
FROM python:3.11-slim-bookworm@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39 AS builder
WORKDIR /build
COPY agents/analyst/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --no-compile --require-hashes --no-deps --target /install -r requirements.txt
COPY common/agentlib/src/agentlib /install/agentlib
COPY agents/analyst/src/analyst /install/analyst
RUN python -m compileall -q /install

FROM gcr.io/distroless/python3-debian12:nonroot@sha256:7d1042ce588ab97019fe95c24ffca7bc5a82ccdac572511d5e09bda4435c89c5
WORKDIR /app
COPY --from=builder /install /app
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PORT=8000 SERVICE_NAME=analyst
USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["/usr/bin/python3.11", "-m", "analyst"]
