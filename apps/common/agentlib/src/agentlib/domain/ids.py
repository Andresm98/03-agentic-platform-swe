"""UUIDv7 (RFC 9562). Python 3.11 no trae `uuid.uuid7` (llega en 3.14).

`Uuid7Factory` no guarda estado global: cada composition root crea la suya.
"""

from __future__ import annotations

import os
import re
import threading
import time
import uuid
from collections.abc import Callable

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def is_uuid(value: str) -> bool:
    return bool(UUID_RE.match(value))


class Uuid7Factory:
    """Genera UUIDv7 monótonos: 48 bits de ms + 12 de contador + 62 aleatorios."""

    def __init__(
        self,
        clock_ns: Callable[[], int] = time.time_ns,
        entropy: Callable[[int], bytes] = os.urandom,
    ) -> None:
        self._clock_ns = clock_ns
        self._entropy = entropy
        self._lock = threading.Lock()
        self._last_ms = 0
        self._counter = 0

    def _tick(self) -> tuple[int, int]:
        ms = self._clock_ns() // 1_000_000
        if ms <= self._last_ms:
            self._counter += 1
            if self._counter > 0xFFF:
                self._last_ms += 1
                self._counter = 0
            return self._last_ms, self._counter
        self._last_ms = ms
        self._counter = int.from_bytes(self._entropy(2), "big") & 0x3FF
        return ms, self._counter

    def new(self) -> str:
        with self._lock:
            ms, counter = self._tick()
        rand = int.from_bytes(self._entropy(8), "big") & ((1 << 62) - 1)
        value = (ms & ((1 << 48) - 1)) << 80 | 0x7 << 76 | (counter & 0xFFF) << 64 | 0b10 << 62 | rand
        return str(uuid.UUID(int=value))
