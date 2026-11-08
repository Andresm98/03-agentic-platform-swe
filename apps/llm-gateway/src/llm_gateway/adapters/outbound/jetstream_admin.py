"""Crea de forma idempotente el stream `TASKS`, la DLQ, los consumidores durables y el KV.

Los consumidores se crean ANTES que los agentes: KEDA necesita ver `num_pending` aunque haya cero
réplicas. Son consumidores push con `deliver_group` porque así los usa el componente
`pubsub.jetstream` de Dapr (components-contrib `jetstream.go`): al arrancar, Dapr llama a
`AddConsumer`, comprueba que la configuración coincide (ack, ack_wait, max_deliver,
max_ack_pending, deliver_policy) y se enlaza al consumidor ya existente. Estos valores deben ser
IDÉNTICOS a la metadata de `gitops/apps/dapr/pubsub.yaml`.

Retención `interest`: lo confirmado por todos los consumidores se borra, así `max_msgs` mide
trabajo pendiente y `discard=new` da backpressure real. Con `limits`, el stream se llenaría con
mensajes ya procesados y acabaría rechazándolo todo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import nats
from nats.js.api import (
    AckPolicy,
    ConsumerConfig,
    DeliverPolicy,
    DiscardPolicy,
    KeyValueConfig,
    RetentionPolicy,
    StorageType,
    StreamConfig,
)
from nats.js.errors import BucketNotFoundError, NotFoundError

log = logging.getLogger(__name__)

STREAM = "TASKS"
ACK_WAIT_S = 60.0
MAX_DELIVER = 5
MAX_ACK_PENDING = 100


@dataclass(frozen=True)
class ConsumerSpec:
    name: str
    subject: str


CONSUMERS: tuple[ConsumerSpec, ...] = (
    ConsumerSpec("orchestrator", "agent.*.completed"),
    ConsumerSpec("researcher", "agent.research.requested"),
    ConsumerSpec("analyst", "agent.analysis.requested"),
    ConsumerSpec("executor", "agent.execution.requested"),
)


def stream_config(max_msgs: int, max_bytes: int) -> StreamConfig:
    return StreamConfig(
        name=STREAM,
        subjects=["tasks.>", "agent.>"],
        storage=StorageType.FILE,
        retention=RetentionPolicy.INTEREST,
        discard=DiscardPolicy.NEW,
        max_age=24 * 3600,  # nats-py convierte segundos a nanosegundos al serializar
        max_msgs=max_msgs,
        max_bytes=max_bytes,
        duplicate_window=120,
        num_replicas=1,
    )


def consumer_config(spec: ConsumerSpec) -> ConsumerConfig:
    return ConsumerConfig(
        durable_name=spec.name,
        deliver_subject=f"_INBOX.{spec.name}",
        deliver_group=spec.name,
        filter_subject=spec.subject,
        ack_policy=AckPolicy.EXPLICIT,
        ack_wait=ACK_WAIT_S,
        max_deliver=MAX_DELIVER,
        max_ack_pending=MAX_ACK_PENDING,
        deliver_policy=DeliverPolicy.ALL,
    )


def dlq_config() -> ConsumerConfig:
    return ConsumerConfig(durable_name="dlq", filter_subject="tasks.dead", ack_policy=AckPolicy.EXPLICIT)


async def ensure_topology(
    url: str, user: str, password: str, bucket: str, max_msgs: int, max_bytes: int
) -> None:
    opts: dict[str, Any] = {"servers": [url], "name": "jetstream-setup"}
    if user:
        opts.update(user=user, password=password)
    nc = await nats.connect(**opts)
    js = nc.jetstream()
    cfg = stream_config(max_msgs, max_bytes)
    try:
        await js.stream_info(STREAM)
        await js.update_stream(config=cfg)
    except NotFoundError:
        await js.add_stream(config=cfg)
    for spec in CONSUMERS:
        try:
            await js.consumer_info(STREAM, spec.name)
        except NotFoundError:
            await js.add_consumer(STREAM, config=consumer_config(spec))
        log.info("consumer ready", extra={"consumer": spec.name, "subject": spec.subject})
    try:
        await js.consumer_info(STREAM, "dlq")
    except NotFoundError:  # con retención interest, sin consumidor no se retendría tasks.dead
        await js.add_consumer(STREAM, config=dlq_config())
    try:
        await js.key_value(bucket)
    except BucketNotFoundError:
        await js.create_key_value(config=KeyValueConfig(bucket=bucket, history=1, storage=StorageType.FILE))
    await nc.drain()
    log.info("jetstream topology ready", extra={"stream": STREAM, "bucket": bucket})
