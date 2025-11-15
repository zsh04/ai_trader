from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.domain.model_registry import get_registry

router = APIRouter(prefix="/models", tags=["models"])
registry = get_registry()


class AdapterSyncRequest(BaseModel):
    adapter_tag: Optional[str] = None


class ModelResponse(BaseModel):
    service: str
    name: str
    adapter_tag: str
    status: str
    warm: bool
    shadow: bool
    last_warm_at: Optional[str] = None
    last_sync_at: Optional[str] = None
    metadata: Dict[str, Any]


def _ensure(service: str) -> None:
    try:
        registry.get(service)
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"model {service} not found"
        ) from exc


@router.get("/", response_model=List[ModelResponse])
def list_models() -> List[Dict[str, Any]]:
    return registry.all()


@router.post("/{service}/warm", response_model=ModelResponse)
def warm_model(service: str) -> Dict[str, Any]:
    _ensure(service)
    return registry.warm(service)


@router.post("/{service}/adapters/sync", response_model=ModelResponse)
def sync_adapter(
    service: str, payload: AdapterSyncRequest | None = None
) -> Dict[str, Any]:
    _ensure(service)
    adapter_tag = payload.adapter_tag if payload else None
    return registry.sync_adapter(service, adapter_tag)


@router.post("/{service}/shadow", response_model=ModelResponse)
def toggle_shadow(service: str) -> Dict[str, Any]:
    _ensure(service)
    return registry.toggle_shadow(service)
