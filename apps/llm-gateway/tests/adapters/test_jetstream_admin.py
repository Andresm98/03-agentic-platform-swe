"""La topología debe coincidir con lo que Dapr comprueba al enlazarse al consumidor existente."""

from __future__ import annotations

import pytest
from nats.js.api import AckPolicy, DiscardPolicy, RetentionPolicy

from llm_gateway.adapters.outbound.jetstream_admin import (
    CONSUMERS,
    ConsumerSpec,
    consumer_config,
    stream_config,
)


def test_stream_has_backpressure_and_interest_retention() -> None:
    cfg = stream_config(10, 1024)
    assert cfg.name == "TASKS" and cfg.subjects == ["tasks.>", "agent.>"]
    assert (
        cfg.discard == DiscardPolicy.NEW and cfg.retention == RetentionPolicy.INTEREST and cfg.max_msgs == 10
    )
    wire = cfg.as_dict()
    assert wire["max_age"] == 24 * 3600 * 10**9 and wire["duplicate_window"] == 120 * 10**9


@pytest.mark.parametrize("spec", CONSUMERS, ids=lambda s: s.name)
def test_consumers_are_push_queue_durables(spec: ConsumerSpec) -> None:
    cfg = consumer_config(spec)
    assert cfg.durable_name == cfg.deliver_group == spec.name and cfg.ack_policy == AckPolicy.EXPLICIT
    assert (
        (cfg.deliver_subject or "").startswith("_INBOX.")
        and cfg.max_deliver == 5
        and cfg.max_ack_pending == 100
    )
    assert cfg.as_dict()["ack_wait"] == 60 * 10**9


def test_contract_consumers_exist() -> None:
    assert {c.name for c in CONSUMERS} == {"orchestrator", "researcher", "analyst", "executor"}
