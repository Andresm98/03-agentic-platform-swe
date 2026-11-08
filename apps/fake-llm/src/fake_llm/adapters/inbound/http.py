"""Rutas HTTP de fake-llm: `/v1/chat/completions`, `/v1/models` y `/admin/faults`.

`/admin/faults` permite activar el caos en caliente (escenario 14). Solo es alcanzable dentro del
cluster: la NetworkPolicy de fake-llm solo admite tráfico del gateway; el operador llega por
port-forward.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from fake_llm.application.complete_chat import CompleteChat, FaultControl


def register_routes(app: FastAPI, complete: CompleteChat, faults: FaultControl, admin_enabled: bool) -> None:
    @app.get("/v1/models")
    async def models() -> dict[str, Any]:
        return {
            "object": "list",
            "data": [{"id": "fake", "object": "model", "created": 0, "owned_by": "lab"}],
        }

    @app.post("/v1/chat/completions")
    async def chat(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except json.JSONDecodeError:
            body = None
        outcome = await complete(body, request.headers.get("x-agent", "unknown"))
        return JSONResponse(outcome.body, status_code=outcome.status, headers=outcome.headers)

    @app.get("/admin/faults")
    async def get_faults() -> dict[str, float]:
        return faults.profile.as_dict()

    @app.put("/admin/faults")
    async def put_faults(request: Request) -> JSONResponse:
        if not admin_enabled:
            return JSONResponse({"error": "admin disabled"}, status_code=403)
        try:
            changes = await request.json()
            if not isinstance(changes, dict):
                raise ValueError("body must be an object")
            profile = faults.update(changes)
        except (ValueError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(profile.as_dict())
