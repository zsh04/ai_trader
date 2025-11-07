from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import pandas as pd
from loguru import logger

_DEFAULT_DIR = Path("artifacts/probabilistic/frames")


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


def persist_probabilistic_frame(
    symbol: str,
    strategy: str,
    frame: pd.DataFrame,
    *,
    vendor: Optional[str] = None,
    interval: Optional[str] = None,
    root: Optional[Path] = None,
) -> Optional[Path]:
    if frame is None or getattr(frame, "empty", True):
        logger.debug(
            "[prob-cache] Skip persist symbol=%s strategy=%s empty frame",
            symbol,
            strategy,
        )
        return None
    path = build_frame_path(
        symbol,
        strategy,
        vendor=vendor,
        interval=interval,
        root=root,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path)
    logger.debug(
        "[prob-cache] Persisted probabilistic frame symbol=%s strategy=%s -> %s",
        symbol,
        strategy,
        path,
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
