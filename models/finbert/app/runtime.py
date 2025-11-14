from __future__ import annotations

import os
import tarfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import torch
from loguru import logger
from peft import PeftModel
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    TextClassificationPipeline,
)

from models.common.adapters import (
    AdapterResult,
    maybe_apply_adapter,
    persist_effective_metadata,
)
from models.common.logging import configure_tracing


class FinbertRuntime:
    def __init__(self) -> None:
        self.model_id = os.getenv("MODEL_ID_FINBERT", "ProsusAI/finbert")
        self.hf_commit = os.getenv("HF_COMMIT_SHA", "unknown")
        self.baked_adapter = os.getenv("BAKED_ADAPTER_TAG", "base")
        self.desired_adapter = os.getenv("ADAPTER_TAG", self.baked_adapter)
        self.storage_account = os.getenv("STORAGE_ACCOUNT") or os.getenv("STG_ACCOUNT")
        self.adapters_url = os.getenv("BLOB_ADAPTERS_URL", "blob://adapters")
        self.cache_dir = Path(os.getenv("MODEL_CACHE_DIR", "/models-cache"))
        self.service_name = "ai-trader-nlp"
        self.service_instance = os.getenv("SERVICE_INSTANCE_ID", str(uuid.uuid4()))

        self._tokenizer: Optional[AutoTokenizer] = None
        self._model: Optional[AutoModelForSequenceClassification] = None
        self._pipeline: Optional[TextClassificationPipeline] = None
        self.ready = False
        self.effective_adapter = self.baked_adapter

    def _model_kwargs(self) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {"torch_dtype": torch.float32}
        if self.hf_commit not in {"", "unknown"}:
            kwargs["revision"] = self.hf_commit
        return kwargs

    def _load_base_model(self) -> None:
        logger.info(
            "[finbert] loading model=%s revision=%s", self.model_id, self.hf_commit
        )
        self._tokenizer = AutoTokenizer.from_pretrained(
            self.model_id, **self._model_kwargs()
        )
        self._model = AutoModelForSequenceClassification.from_pretrained(
            self.model_id,
            **self._model_kwargs(),
        )
        self._pipeline = TextClassificationPipeline(
            model=self._model,
            tokenizer=self._tokenizer,
            top_k=1,
            truncation=True,
        )

    def _apply_adapter_tarball(self, tar_path: Path) -> Path:
        target_root = self.cache_dir / "finbert" / "adapters" / self.desired_adapter
        target_root.mkdir(parents=True, exist_ok=True)
        with tarfile.open(tar_path, "r:gz") as archive:
            archive.extractall(target_root)
        return target_root

    def _attach_adapter(self, adapter_dir: Path) -> None:
        if not self._model:
            return
        try:
            self._model = PeftModel.from_pretrained(
                self._model,
                adapter_dir,
                is_trainable=False,
            ).merge_and_unload()
            logger.info("[finbert] adapter merged from %s", adapter_dir)
        except Exception as exc:  # pragma: no cover - dependent on adapter contents
            logger.warning("[finbert] adapter merge failed: %s", exc)

    def _adapter_flow(self) -> AdapterResult:
        return maybe_apply_adapter(
            service="finbert",
            desired_tag=self.desired_adapter,
            baked_tag=self.baked_adapter,
            storage_account=self.storage_account,
            adapters_url=self.adapters_url,
            cache_dir=self.cache_dir,
            apply_callback=lambda tar_path: self._attach_adapter(
                self._apply_adapter_tarball(tar_path)
            ),
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
        persist_effective_metadata(self.cache_dir / "finbert", payload)

    def load(self) -> None:
        if self.ready:
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._load_base_model()
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
            "[finbert] runtime ready adapter=%s hf_sha=%s",
            self.effective_adapter,
            self.hf_commit,
        )

    def classify(self, text: str) -> Dict[str, Any]:
        if not self.ready or not self._pipeline:
            raise RuntimeError("runtime not ready")
        result = self._pipeline(text)[0]
        top = result if isinstance(result, dict) else result[0]
        return {
            "label": top.get("label"),
            "score": float(top.get("score", 0.0)),
            "adapter_tag": self.effective_adapter,
            "hf_sha": self.hf_commit,
        }
