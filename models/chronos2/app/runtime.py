from __future__ import annotations

import os
import tarfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from loguru import logger

from models.common.adapters import (
    AdapterResult,
    maybe_apply_adapter,
    persist_effective_metadata,
)
from models.common.logging import configure_tracing


class ChronosRuntime:
    def __init__(self) -> None:
        self.model_id = os.getenv("MODEL_ID_CHRONOS2", "amazon/chronos-2")
        self.hf_commit = os.getenv("HF_COMMIT_SHA", "unknown")
        self.baked_adapter = os.getenv("BAKED_ADAPTER_TAG", "base")
        self.desired_adapter = os.getenv("ADAPTER_TAG", self.baked_adapter)
        self.storage_account = os.getenv("STORAGE_ACCOUNT") or os.getenv("STG_ACCOUNT")
        self.adapters_url = os.getenv("BLOB_ADAPTERS_URL", "blob://adapters")
        self.cache_dir = Path(os.getenv("MODEL_CACHE_DIR", "/models-cache"))
        self.service_name = "ai-trader-forecast"
        self.service_instance = os.getenv("SERVICE_INSTANCE_ID", str(uuid.uuid4()))
        self.ready = False
        self.effective_adapter = self.baked_adapter

    def _apply_adapter_tarball(self, tar_path: Path) -> Path:
        target_root = self.cache_dir / "chronos2" / "adapters" / self.desired_adapter
        target_root.mkdir(parents=True, exist_ok=True)
        with tarfile.open(tar_path, "r:gz") as archive:
            archive.extractall(target_root)
        return target_root

    def _adapter_flow(self) -> AdapterResult:
        return maybe_apply_adapter(
            service="chronos2",
            desired_tag=self.desired_adapter,
            baked_tag=self.baked_adapter,
            storage_account=self.storage_account,
            adapters_url=self.adapters_url,
            cache_dir=self.cache_dir,
            apply_callback=lambda tar_path: self._apply_adapter_tarball(tar_path),
        )

    def _write_metadata(self, adapter_result: AdapterResult) -> None:
        payload = {
            "service": self.service_name,
            "hf_model": self.model_id,
            "hf_sha": self.hf_commit,
            "adapter_tag": adapter_result.effective_tag,
            "adapter_source": adapter_result.source,
            "adapter_metadata": adapter_result.metadata,
            "loaded_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        persist_effective_metadata(self.cache_dir / "chronos2", payload)

    def load(self) -> None:
        if self.ready:
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        adapter_result = self._adapter_flow()
        self.effective_adapter = adapter_result.effective_tag
        self._write_metadata(adapter_result)
        configure_tracing(
            service_name=self.service_name,
            resource_attrs={
                "service.instance.id": self.service_instance,
                "ai.model.id": self.model_id,
                "ai.hf.repo.sha": self.hf_commit,
                "ai.adapter.tag": self.effective_adapter,
            },
        )
        self.ready = True
        logger.info(
            "[chronos2] runtime ready adapter=%s hf_sha=%s",
            self.effective_adapter,
            self.hf_commit,
        )

    def _trend_forecast(self, series: List[float], horizon: int) -> List[float]:
        arr = np.asarray(series, dtype=float)
        if arr.size == 0:
            return [0.0 for _ in range(horizon)]
        if arr.size == 1:
            return [float(arr[0]) for _ in range(horizon)]
        x = np.arange(arr.size)
        slope = float(np.polyfit(x, arr, 1)[0])
        start = float(arr[-1])
        return [start + slope * (i + 1) for i in range(horizon)]

    def forecast(self, series: List[float], horizon: int) -> Dict[str, Any]:
        if not self.ready:
            raise RuntimeError("runtime not ready")
        if horizon <= 0:
            raise ValueError("horizon must be > 0")
        forecast = self._trend_forecast(series, horizon)
        return {
            "forecast": [float(x) for x in forecast],
            "adapter_tag": self.effective_adapter,
            "hf_sha": self.hf_commit,
        }
