"""Rutas HTTP del gateway: `/v1/chat/completions` (OpenAI), `/v1/models` y `/budget`."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from llm_gateway.application.route_completion import RouteCompletion

_NOT_READY = {
    "error": {"message": "budget store not ready", "type": "server_error", "param": None, "code": "not_ready"}
}


def register_routes(
    app: FastAPI, get_use_case: Callable[[], RouteCompletion | None], models: list[str], info: dict[str, Any]
) -> None:
    @app.post("/v1/chat/completions")
    async def chat(request: Request) -> JSONResponse:
        use_case = get_use_case()
        if use_case is None:
            return JSONResponse(_NOT_READY, status_code=503, headers={"Retry-After": "2"})
        try:
            body = await request.json()
        except ValueError:
            body = None
        res = await use_case(body, dict(request.headers))
        return JSONResponse(res.body, status_code=res.status, headers=res.headers)

    @app.get("/v1/models")
    async def list_models() -> dict[str, Any]:
        return {
            "object": "list",
            "data": [{"id": m, "object": "model", "owned_by": "allowed"} for m in models],
        }

    @app.get("/budget")
    async def budget() -> dict[str, Any]:
        use_case = get_use_case()
        if use_case is None:
            return {"ready": False, **info}
        return {
            **info,
            "ready": True,
            "remaining_usd": await use_case.budget_remaining(),
            "circuits": {name: c.state.name.lower() for name, c in use_case.circuits.items()},
        }
