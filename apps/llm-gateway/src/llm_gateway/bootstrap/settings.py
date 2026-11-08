"""Configuración del gateway. Los topes por defecto son los de ADR-0002 §6."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agentlib.bootstrap.settings import BaseSettings, env_bool, env_float, env_int, env_json, env_str

# USD por 1M de tokens, comprobado el 2026-11-08 en developers.openai.com/api/docs/pricing.
# El gateway convierte tokens en USD con estos valores.
DEFAULT_MODELS: dict[str, Any] = {
    "gpt-4o-mini": {"input_usd_per_1m": 0.15, "output_usd_per_1m": 0.60},
    "gpt-4.1-mini": {"input_usd_per_1m": 0.40, "output_usd_per_1m": 1.60},
}
DEFAULT_AGENT_MAX_TOKENS: dict[str, Any] = {"orchestrator": 300, "default": 200}


@dataclass(frozen=True)
class GatewaySettings(BaseSettings):
    global_mode: str = field(default_factory=lambda: env_str("LLM_GLOBAL_MODE", "simulated").lower())
    fake_llm_url: str = field(
        default_factory=lambda: env_str("FAKE_LLM_URL", "http://fake-llm.apps.svc.cluster.local:8000/v1")
    )
    openai_base_url: str = field(
        default_factory=lambda: env_str("OPENAI_BASE_URL", "https://api.openai.com/v1")
    )
    openai_api_key: str = field(default_factory=lambda: env_str("OPENAI_API_KEY", ""), repr=False)
    nats_url: str = field(
        default_factory=lambda: env_str("NATS_URL", "nats://nats.nats.svc.cluster.local:4222")
    )
    nats_user: str = field(default_factory=lambda: env_str("NATS_USER", ""))
    nats_password: str = field(default_factory=lambda: env_str("NATS_PASSWORD", ""), repr=False)
    budget_bucket: str = field(default_factory=lambda: env_str("BUDGET_BUCKET", "llm-budget"))
    budget_usd: float = field(default_factory=lambda: env_float("LLM_BUDGET_USD", 3.0))
    live_tasks_per_minute: int = field(default_factory=lambda: env_int("LIVE_TASKS_PER_MINUTE", 5))
    live_tasks_total: int = field(default_factory=lambda: env_int("LIVE_TASKS_TOTAL", 50))
    task_max_llm_calls: int = field(default_factory=lambda: env_int("TASK_MAX_LLM_CALLS", 6))
    task_max_tokens: int = field(default_factory=lambda: env_int("TASK_MAX_TOKENS", 15000))
    max_input_tokens: int = field(default_factory=lambda: env_int("LLM_MAX_INPUT_TOKENS", 2000))
    agent_max_tokens: dict[str, Any] = field(
        default_factory=lambda: env_json("LLM_AGENT_MAX_TOKENS", DEFAULT_AGENT_MAX_TOKENS)
    )
    allowed_models: dict[str, Any] = field(
        default_factory=lambda: env_json("LLM_ALLOWED_MODELS", DEFAULT_MODELS)
    )
    upstream_timeout_s: float = field(default_factory=lambda: env_float("UPSTREAM_TIMEOUT_S", 20.0))
    upstream_retries: int = field(default_factory=lambda: env_int("UPSTREAM_RETRIES", 2))
    circuit_failure_threshold: int = field(default_factory=lambda: env_int("CIRCUIT_FAILURE_THRESHOLD", 5))
    circuit_window_s: float = field(default_factory=lambda: env_float("CIRCUIT_WINDOW_S", 30.0))
    circuit_open_s: float = field(default_factory=lambda: env_float("CIRCUIT_OPEN_S", 30.0))
    # LangSmith: activado por defecto; sin API key se desactiva solo (aviso en logs, fail-open).
    langsmith_enabled: bool = field(default_factory=lambda: env_bool("LANGSMITH_ENABLED", True))
    langsmith_api_key: str = field(default_factory=lambda: env_str("LANGSMITH_API_KEY", ""), repr=False)
    langsmith_endpoint: str = field(
        default_factory=lambda: env_str("LANGSMITH_OTEL_ENDPOINT", "https://api.smith.langchain.com/otel")
    )
    langsmith_project: str = field(default_factory=lambda: env_str("LANGSMITH_PROJECT", "agentic-platform"))
    langsmith_simulated_sample_rate: float = field(
        default_factory=lambda: env_float("LANGSMITH_SIMULATED_SAMPLE_RATE", 0.01)
    )
