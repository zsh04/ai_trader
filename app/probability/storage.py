from __future__ import annotations

import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
from loguru import logger

_DEFAULT_DIR = Path("artifacts/probabilistic/frames")
_MANIFEST_FILENAME = "manifest.jsonl"


def _default_dir() -> Path:
    override = os.getenv("BACKTEST_PROB_FRAME_DIR")
    if override:
        return Path(override)
    return _DEFAULT_DIR


def build_frame_path(
    symbol: str,
    strategy: str,
    *,
    vendor: Optional[str] = None,
    interval: Optional[str] = None,
    root: Optional[Path] = None,
) -> Path:
    root_dir = root or _default_dir()
    safe_symbol = symbol.upper().replace("/", "-")
    safe_strategy = strategy.replace(" ", "_").replace("-", "_").lower()
    parts = [safe_symbol, safe_strategy]
    if vendor:
        parts.append(vendor.lower())
    if interval:
        parts.append(interval.lower())
    filename = "_".join(parts) + ".parquet"
    return root_dir / filename


def _manifest_path(root: Path) -> Path:
    return root / _MANIFEST_FILENAME


def _append_manifest(
    *,
    root: Path,
    path: Path,
    symbol: str,
    strategy: str,
    vendor: Optional[str],
    interval: Optional[str],
    frame: pd.DataFrame,
    source: Optional[str],
) -> None:
    entry = {
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "path": str(path),
        "symbol": symbol,
        "strategy": strategy,
        "vendor": vendor,
        "interval": interval,
        "rows": int(frame.shape[0]),
        "cols": int(frame.shape[1]),
        "columns": list(frame.columns),
        "source": source or "unknown",
    }
    manifest_path = _manifest_path(root)
    try:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with manifest_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    except (
        Exception
    ) as exc:  # pragma: no cover - manifest failures shouldn't break pipeline
        logger.debug("[prob-cache] Failed to append manifest entry %s: %s", path, exc)


def persist_probabilistic_frame(
    symbol: str,
    strategy: str,
    frame: pd.DataFrame,
    *,
    vendor: Optional[str] = None,
    interval: Optional[str] = None,
    root: Optional[Path] = None,
    source: Optional[str] = None,
) -> Optional[Path]:
    if frame is None or getattr(frame, "empty", True):
        logger.debug(
            "[prob-cache] Skip persist symbol=%s strategy=%s empty frame",
            symbol,
            strategy,
        )
        return None
    root_dir = root or _default_dir()
    path = build_frame_path(
        symbol,
        strategy,
        vendor=vendor,
        interval=interval,
        root=root_dir,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path)
    logger.debug(
        "[prob-cache] Persisted probabilistic frame symbol=%s strategy=%s -> %s",
        symbol,
        strategy,
        path,
    )
    _append_manifest(
        root=root_dir,
        path=path,
        symbol=symbol,
        strategy=strategy,
        vendor=vendor,
        interval=interval,
        frame=frame,
        source=source,
    )
    return path


def load_probabilistic_frame(
    symbol: str,
    strategy: str,
    *,
    vendor: Optional[str] = None,
    interval: Optional[str] = None,
    root: Optional[Path] = None,
) -> Optional[pd.DataFrame]:
    path = build_frame_path(
        symbol,
        strategy,
        vendor=vendor,
        interval=interval,
        root=root,
    )
    if not path.exists():
        return None
    return pd.read_parquet(path)


__all__ = [
    "build_frame_path",
    "persist_probabilistic_frame",
    "load_probabilistic_frame",
]
