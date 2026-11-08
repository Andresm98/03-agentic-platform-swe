"""Lectura de configuración por variables de entorno (12-factor).

Los servicios extienden `BaseSettings`. Sin pydantic-settings: dataclasses con lectura explícita.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any


def env_str(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    return float(raw) if raw else default


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    return raw in {"1", "true", "yes", "on"} if raw else default


def env_json(name: str, default: dict[str, Any]) -> dict[str, Any]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return dict(default)
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    return value


@dataclass(frozen=True)
class BaseSettings:
    service_name: str = field(default_factory=lambda: env_str("SERVICE_NAME", "agent"))
    port: int = field(default_factory=lambda: env_int("PORT", 8000))
    log_level: str = field(default_factory=lambda: env_str("LOG_LEVEL", "INFO"))
    pod_name: str = field(default_factory=lambda: env_str("POD_NAME", env_str("HOSTNAME", "local")))
    dapr_http_endpoint: str = field(
        default_factory=lambda: env_str(
            "DAPR_HTTP_ENDPOINT", f"http://127.0.0.1:{env_str('DAPR_HTTP_PORT', '3500')}"
        )
    )
    pubsub_name: str = field(default_factory=lambda: env_str("PUBSUB_NAME", "pubsub"))
    dead_letter_topic: str = field(default_factory=lambda: env_str("DEAD_LETTER_TOPIC", "tasks.dead"))
    llm_base_url: str = field(
        default_factory=lambda: env_str("LLM_BASE_URL", "http://llm-gateway.apps.svc.cluster.local:8000/v1")
    )
    llm_model: str = field(default_factory=lambda: env_str("LLM_MODEL", "gpt-4o-mini"))
    llm_max_tokens: int = field(default_factory=lambda: env_int("LLM_MAX_TOKENS", 200))
    llm_timeout_s: float = field(default_factory=lambda: env_float("LLM_TIMEOUT_S", 30.0))
    llm_max_input_tokens: int = field(default_factory=lambda: env_int("LLM_MAX_INPUT_TOKENS", 2000))
    otel_enabled: bool = field(default_factory=lambda: env_bool("OTEL_ENABLED", False))
    otel_endpoint: str = field(
        default_factory=lambda: env_str(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://alloy-otlp.monitoring.svc.cluster.local:4317"
        )
    )
    otel_sample_ratio: float = field(default_factory=lambda: env_float("OTEL_SAMPLE_RATIO", 1.0))
    graceful_timeout_s: int = field(default_factory=lambda: env_int("GRACEFUL_TIMEOUT_S", 30))
