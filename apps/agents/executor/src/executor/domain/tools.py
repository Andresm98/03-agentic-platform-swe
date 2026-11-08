"""Catálogo CERRADO de herramientas de CPU del agente de ejecución. Sin shell ni código arbitrario.

Cada herramienta es una función pura y determinista cuyo coste crece con `complexity` (1..10),
acotado para que una ejecución dure como mucho unos segundos en un t3.medium.
`run_tool` es la única entrada y es picklable (se ejecuta en un proceso aparte).
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from typing import Any


class UnknownToolError(ValueError):
    pass


def prime_count(complexity: int) -> dict[str, Any]:
    limit = 20_000 * complexity
    sieve = bytearray([1]) * (limit + 1)
    sieve[0:2] = b"\x00\x00"
    for i in range(2, int(limit**0.5) + 1):
        if sieve[i]:
            sieve[i * i :: i] = bytearray(len(sieve[i * i :: i]))
    return {"limit": limit, "primes": int(sum(sieve))}


def sha256_chain(complexity: int) -> dict[str, Any]:
    rounds = 30_000 * complexity
    digest = b"agentic-platform"
    for _ in range(rounds):
        digest = hashlib.sha256(digest).digest()
    return {"rounds": rounds, "digest": digest.hex()[:16]}


def matrix_multiply(complexity: int) -> dict[str, Any]:
    n = 20 + 6 * complexity
    a = [[(i * j) % 7 + 1 for j in range(n)] for i in range(n)]
    b = [[(i + j) % 5 + 1 for j in range(n)] for i in range(n)]
    c = [[sum(a[i][k] * b[k][j] for k in range(n)) for j in range(n)] for i in range(n)]
    return {"size": n, "trace": sum(c[i][i] for i in range(n))}


def fibonacci_mod(complexity: int) -> dict[str, Any]:
    n, a, b = 100_000 * complexity, 0, 1
    for _ in range(n):
        a, b = b, (a + b) % 1_000_000_007
    return {"n": n, "value": a}


def sort_numbers(complexity: int) -> dict[str, Any]:
    count = 40_000 * complexity
    data = [(i * 2_654_435_761) % 1_000_003 for i in range(count)]
    data.sort()
    return {"count": count, "median": data[count // 2]}


CATALOG: dict[str, Callable[[int], dict[str, Any]]] = {
    "prime_count": prime_count,
    "sha256_chain": sha256_chain,
    "matrix_multiply": matrix_multiply,
    "fibonacci_mod": fibonacci_mod,
    "sort_numbers": sort_numbers,
}


def clamp_complexity(value: Any) -> int:
    try:
        return max(1, min(10, int(value)))
    except (TypeError, ValueError):
        return 3


def run_tool(name: str, complexity: int, min_duration_ms: int = 0) -> dict[str, Any]:
    """Ejecuta una herramienta del catálogo. `min_duration_ms` repite el trabajo hasta ese mínimo
    (`WORK_DURATION_MS`) para que la demo de HPA por CPU sea predecible."""
    fn = CATALOG.get(name)
    if fn is None:
        raise UnknownToolError(f"tool '{name}' is not in the closed catalog")
    level = clamp_complexity(complexity)
    start = time.perf_counter()
    result = fn(level)
    iterations = 1
    while (time.perf_counter() - start) * 1000 < min(max(0, min_duration_ms), 30_000):
        fn(level)
        iterations += 1
    return {
        "tool": name,
        "complexity": level,
        "iterations": iterations,
        "elapsed_ms": round((time.perf_counter() - start) * 1000, 1),
        **result,
    }
