from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List, Optional


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ModelState:
    service: str
    name: str
    adapter_tag: str
    status: str = "ready"
    warm: bool = False
    shadow: bool = False
    last_warm_at: Optional[datetime] = None
    last_sync_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "service": self.service,
            "name": self.name,
            "adapter_tag": self.adapter_tag,
            "status": self.status,
            "warm": self.warm,
            "shadow": self.shadow,
            "last_warm_at": (
                self.last_warm_at.isoformat() if self.last_warm_at else None
            ),
            "last_sync_at": (
                self.last_sync_at.isoformat() if self.last_sync_at else None
            ),
            "metadata": self.metadata,
        }


class ModelRegistry:
    def __init__(self, initial: Optional[List[ModelState]] = None) -> None:
        self._lock = Lock()
        self._models: Dict[str, ModelState] = {
            state.service: state for state in (initial or [])
        }

    def all(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [state.to_dict() for state in self._models.values()]

    def get(self, service: str) -> ModelState:
        normalized = service.lower()
        try:
            return self._models[normalized]
        except KeyError as exc:  # pragma: no cover - guarded by API
            raise KeyError(f"model {service} not found") from exc

    def warm(self, service: str) -> Dict[str, Any]:
        with self._lock:
            state = self.get(service)
            state.warm = True
            state.last_warm_at = _now()
            state.status = "warming"
            state.metadata["last_action"] = "warm"
            return state.to_dict()

    def sync_adapter(self, service: str, adapter_tag: Optional[str]) -> Dict[str, Any]:
        with self._lock:
            state = self.get(service)
            if adapter_tag:
                state.adapter_tag = adapter_tag
            state.last_sync_at = _now()
            state.metadata["last_action"] = "adapter_sync"
            return state.to_dict()

    def toggle_shadow(self, service: str) -> Dict[str, Any]:
        with self._lock:
            state = self.get(service)
            state.shadow = not state.shadow
            state.metadata["last_action"] = "shadow_toggle"
            return state.to_dict()


_REGISTRY: Optional[ModelRegistry] = None


def get_registry() -> ModelRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = ModelRegistry(
            [
                ModelState(
                    service="finbert",
                    name="ai-trader-nlp",
                    adapter_tag="base",
                    metadata={"hf_repo": "ProsusAI/finbert"},
                ),
                ModelState(
                    service="chronos2",
                    name="ai-trader-forecast",
                    adapter_tag="base",
                    metadata={"hf_repo": "amazon/chronos-2"},
                ),
            ]
        )
    return _REGISTRY
