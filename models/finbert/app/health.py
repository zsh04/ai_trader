from __future__ import annotations

from fastapi import APIRouter, Response, status

from .runtime import FinbertRuntime


def build_health_router(runtime: FinbertRuntime) -> APIRouter:
    router = APIRouter()

    @router.get("/healthz")
    async def healthz() -> dict:
        return {"status": "ok", "service": runtime.service_name}

    @router.get("/ready")
    async def ready() -> Response:
        if runtime.ready:
            return Response(status_code=status.HTTP_200_OK)
        return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

    return router
