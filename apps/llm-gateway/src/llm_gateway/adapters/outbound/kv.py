"""Adaptadores de `KeyValuePort`: NATS KV (producción) y en memoria (tests y desarrollo)."""

from __future__ import annotations

import logging
from typing import Any

from llm_gateway.application.ports import CasConflictError

log = logging.getLogger(__name__)


class InMemoryKeyValue:
    """Misma semántica CAS que NATS KV: `create` falla si existe, `update` exige la revisión."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[bytes, int]] = {}
        self._rev = 0

    async def get(self, key: str) -> tuple[bytes, int] | None:
        return self._data.get(key)

    async def create(self, key: str, value: bytes) -> int:
        if key in self._data:
            raise CasConflictError(key)
        return self._put(key, value)

    async def update(self, key: str, value: bytes, last: int) -> int:
        cur = self._data.get(key)
        if cur is None or cur[1] != last:
            raise CasConflictError(key)
        return self._put(key, value)

    def _put(self, key: str, value: bytes) -> int:
        self._rev += 1
        self._data[key] = (value, self._rev)
        return self._rev


class NatsKeyValue:
    """Envuelve `nats.js.kv.KeyValue` (nats-py 2.16)."""

    def __init__(self, kv: Any) -> None:
        self._kv = kv

    async def get(self, key: str) -> tuple[bytes, int] | None:
        from nats.js.errors import KeyNotFoundError

        try:
            entry = await self._kv.get(key)
        except KeyNotFoundError:  # incluye KeyDeletedError
            return None
        return None if entry.value is None else (entry.value, entry.revision)

    async def create(self, key: str, value: bytes) -> int:
        from nats.js.errors import KeyWrongLastSequenceError

        try:
            return int(await self._kv.create(key, value))
        except KeyWrongLastSequenceError as exc:
            raise CasConflictError(key) from exc

    async def update(self, key: str, value: bytes, last: int) -> int:
        from nats.js.errors import KeyWrongLastSequenceError

        try:
            return int(await self._kv.update(key, value, last=last))
        except KeyWrongLastSequenceError as exc:
            raise CasConflictError(key) from exc


class NatsConnection:
    """Conexión NATS con reconexión infinita; el bucket lo crea el Job de sync-wave 8."""

    def __init__(self, url: str, user: str, password: str, bucket: str, name: str) -> None:
        self._url, self._user, self._password, self._bucket, self._name = url, user, password, bucket, name
        self._nc: Any = None

    @property
    def connected(self) -> bool:
        return bool(self._nc is not None and self._nc.is_connected)

    async def connect(self) -> NatsKeyValue:
        import nats
        from nats.js.api import KeyValueConfig, StorageType
        from nats.js.errors import BucketNotFoundError

        opts: dict[str, Any] = {
            "servers": [self._url],
            "name": self._name,
            "max_reconnect_attempts": -1,
            "reconnect_time_wait": 1,
        }
        if self._user:
            opts.update(user=self._user, password=self._password)
        self._nc = await nats.connect(**opts)
        js = self._nc.jetstream()
        try:
            kv = await js.key_value(self._bucket)
        except BucketNotFoundError:  # red de seguridad si el Job aún no corrió (p. ej. compose)
            kv = await js.create_key_value(
                config=KeyValueConfig(bucket=self._bucket, history=1, storage=StorageType.FILE)
            )
        log.info("nats kv ready", extra={"bucket": self._bucket})
        return NatsKeyValue(kv)

    async def close(self) -> None:
        if self._nc is not None:
            await self._nc.drain()
