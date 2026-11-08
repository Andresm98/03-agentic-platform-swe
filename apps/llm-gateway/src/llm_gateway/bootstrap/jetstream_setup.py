"""Entrada del Job de sync-wave 8: `python -m llm_gateway.bootstrap.jetstream_setup`."""

from __future__ import annotations

import asyncio
import logging

from agentlib.adapters.outbound.json_logging import configure_logging
from agentlib.bootstrap.settings import env_int, env_str
from llm_gateway.adapters.outbound.jetstream_admin import ensure_topology

log = logging.getLogger(__name__)


async def _run_with_retry(attempts: int, delay_s: float) -> None:
    for attempt in range(1, attempts + 1):
        try:
            await ensure_topology(
                env_str("NATS_URL", "nats://nats.nats.svc.cluster.local:4222"),
                env_str("NATS_USER", ""),
                env_str("NATS_PASSWORD", ""),
                env_str("BUDGET_BUCKET", "llm-budget"),
                env_int("STREAM_MAX_MSGS", 20000),
                env_int("STREAM_MAX_BYTES", 1024**3),
            )
            return
        except Exception as exc:  # NATS puede no estar listo todavía
            log.warning("setup failed", extra={"attempt": attempt, "error": str(exc)[:300]})
            if attempt == attempts:
                raise
            await asyncio.sleep(delay_s)


def main() -> None:
    configure_logging("jetstream-setup")
    asyncio.run(_run_with_retry(env_int("SETUP_ATTEMPTS", 30), 5.0))


if __name__ == "__main__":
    main()
