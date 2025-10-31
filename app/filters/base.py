"""
Probabilistic filter base classes.

Integrates with existing ai_trader structure:
- Uses app/strats/common.py utilities (pick_col, as_series, etc.)
- Returns pandas Series with probabilistic scores [0,1]
- Compatible with existing OHLCV data format
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

import pandas as pd


class ProbabilisticFilter(ABC):
    """Base class for probabilistic filters.

    Unlike boolean filters, these return confidence scores [0,1]
    representing belief that an asset satisfies the criterion.

    Example:
        filter = VolatilityRegimeFilter()
        scores = filter.score(data, context={'vix': 18.5})
        # Returns: pd.Series with index=symbols, values=[0,1]

        # Can also use as boolean filter with threshold
        mask = filter.filter(data, threshold=0.7)
    """

    def __init__(self, name: str | None = None):
        """Initialize filter with optional custom name."""
        self.name = name or self.__class__.__name__
        self._fitted = False

    @abstractmethod
    def score(self, data: pd.DataFrame, context: Dict[str, Any] | None = None) -> pd.Series:
        """Return probability [0,1] for each symbol.

        Args:
            data: OHLCV DataFrame. Can be:
                  - Single symbol: index=datetime, columns=[open,high,low,close,volume]
                  - Multi-symbol: index=datetime, columns=MultiIndex[(symbol,field)]
                  - Wide format: columns=[symbol1_close, symbol1_volume, symbol2_close, ...]
            context: Optional dict with market state (vix, regime, etc.)

        Returns:
            pd.Series with:
                - index = symbol names (str)
                - values = probability scores [0,1]

        Raises:
            ValueError: If data format is invalid or required columns missing
        """
        pass

    def filter(
        self,
        data: pd.DataFrame,
        threshold: float = 0.5,
        context: Dict[str, Any] | None = None
    ) -> pd.Series:
        """Binary filter using threshold on probability scores.

        Args:
            data: OHLCV DataFrame
            threshold: Minimum probability to pass filter [0,1]
            context: Optional market context dict

        Returns:
            pd.Series of booleans (True = passes filter)
        """
        scores = self.score(data, context or {})
        return scores >= threshold

    def fit(self, data: pd.DataFrame, labels: pd.Series | None = None) -> ProbabilisticFilter:
        """Train filter on historical data (optional, for ML-based filters).

        Args:
            data: Historical OHLCV data
            labels: Optional binary labels (1=positive, 0=negative)

        Returns:
            self (for method chaining)
        """
        self._fitted = True
        return self

    @property
    def is_fitted(self) -> bool:
        """Check if filter has been trained (for ML filters)."""
        return self._fitted

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}')"


class FilterPipeline:
    """Compose multiple probabilistic filters with different combination methods.

    Example:
        pipeline = FilterPipeline(
            filters=[VolatilityFilter(), LiquidityFilter()],
            combination_method='product'
        )
        final_scores = pipeline.score(data, context)
    """

    VALID_METHODS = {'product', 'weighted_avg', 'min', 'max', 'mean'}

    def __init__(
        self,
        filters: list[ProbabilisticFilter],
        combination_method: str = 'product',
        weights: list[float] | None = None
    ):
        """Initialize pipeline.

        Args:
            filters: List of ProbabilisticFilter instances
            combination_method: How to combine scores:
                - 'product': Multiply scores (assumes independence)
                - 'weighted_avg': Weighted average (requires weights)
                - 'min': Conservative (take minimum)
                - 'max': Aggressive (take maximum)
                - 'mean': Simple average
            weights: Optional weights for weighted_avg method
        """
        if not filters:
            raise ValueError("filters list cannot be empty")

        if combination_method not in self.VALID_METHODS:
            raise ValueError(
                f"Invalid combination_method '{combination_method}'. "
                f"Must be one of {self.VALID_METHODS}"
            )

        self.filters = filters
        self.combination_method = combination_method
        self.weights = weights

        if combination_method == 'weighted_avg':
            if weights is None:
                # Default to equal weights
                self.weights = [1.0 / len(filters)] * len(filters)
            elif len(weights) != len(filters):
                raise ValueError(
                    f"weights length ({len(weights)}) must match "
                    f"filters length ({len(filters)})"
                )

    def score(self, data: pd.DataFrame, context: Dict[str, Any] | None = None) -> pd.Series:
        """Compute combined probability scores from all filters.

        Args:
            data: OHLCV DataFrame
            context: Optional market context

        Returns:
            pd.Series with combined scores [0,1]
        """
        context = context or {}

        # Compute all filter scores
        scores_list = []
        for f in self.filters:
            try:
                score = f.score(data, context)
                scores_list.append(score)
            except Exception as e:
                print(f"Warning: Filter {f.name} failed: {e}")
                continue

        if not scores_list:
            raise RuntimeError("All filters failed - no scores computed")

        # Combine into DataFrame for easier manipulation
        scores_df = pd.concat(scores_list, axis=1, keys=[f.name for f in self.filters])

        # Apply combination method
        if self.combination_method == 'product':
            # Independent assumption: P(A and B) = P(A) * P(B)
            return scores_df.prod(axis=1)

        elif self.combination_method == 'weighted_avg':
            return scores_df.dot(self.weights)

        elif self.combination_method == 'min':
            # Conservative: weakest link
            return scores_df.min(axis=1)

        elif self.combination_method == 'max':
            # Aggressive: strongest signal
            return scores_df.max(axis=1)

        elif self.combination_method == 'mean':
            return scores_df.mean(axis=1)

        else:
            raise NotImplementedError(f"Method {self.combination_method} not implemented")

    def filter(
        self,
        data: pd.DataFrame,
        threshold: float = 0.5,
        context: Dict[str, Any] | None = None
    ) -> pd.Series:
        """Binary filter using combined scores."""
        scores = self.score(data, context)
        return scores >= threshold

    def __repr__(self) -> str:
        return (
            f"FilterPipeline("
            f"n_filters={len(self.filters)}, "
            f"method='{self.combination_method}')"
        )