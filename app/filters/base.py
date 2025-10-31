"""
Probabilistic filter base classes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

import pandas as pd


class ProbabilisticFilter(ABC):
    """
    An abstract base class for probabilistic filters.
    """

    def __init__(self, name: str | None = None):
        """
        Initializes the ProbabilisticFilter.

        Args:
            name (str | None): The name of the filter.
        """
        self.name = name or self.__class__.__name__
        self._fitted = False

    @abstractmethod
    def score(self, data: pd.DataFrame, context: Dict[str, Any] | None = None) -> pd.Series:
        """
        Scores the data based on the filter's criteria.

        Args:
            data (pd.DataFrame): The data to score.
            context (Dict[str, Any] | None): The context for scoring.

        Returns:
            pd.Series: A Series of scores.
        """
        pass

    def filter(
        self,
        data: pd.DataFrame,
        threshold: float = 0.5,
        context: Dict[str, Any] | None = None
    ) -> pd.Series:
        """
        Filters the data based on a threshold.

        Args:
            data (pd.DataFrame): The data to filter.
            threshold (float): The threshold to use for filtering.
            context (Dict[str, Any] | None): The context for filtering.

        Returns:
            pd.Series: A Series of booleans indicating which data points passed the filter.
        """
        scores = self.score(data, context or {})
        return scores >= threshold

    def fit(self, data: pd.DataFrame, labels: pd.Series | None = None) -> ProbabilisticFilter:
        """
        Fits the filter to the data.

        Args:
            data (pd.DataFrame): The data to fit the filter to.
            labels (pd.Series | None): The labels for the data.

        Returns:
            ProbabilisticFilter: The fitted filter.
        """
        self._fitted = True
        return self

    @property
    def is_fitted(self) -> bool:
        """
        Whether the filter has been fitted.
        """
        return self._fitted

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}')"


class FilterPipeline:
    """
    A pipeline of probabilistic filters.
    """

    VALID_METHODS = {'product', 'weighted_avg', 'min', 'max', 'mean'}

    def __init__(
        self,
        filters: list[ProbabilisticFilter],
        combination_method: str = 'product',
        weights: list[float] | None = None
    ):
        """
        Initializes the FilterPipeline.

        Args:
            filters (list[ProbabilisticFilter]): A list of filters to use.
            combination_method (str): The method to use for combining scores.
            weights (list[float] | None): The weights to use for the 'weighted_avg' method.
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
                self.weights = [1.0 / len(filters)] * len(filters)
            elif len(weights) != len(filters):
                raise ValueError(
                    f"weights length ({len(weights)}) must match "
                    f"filters length ({len(filters)})"
                )

    def score(self, data: pd.DataFrame, context: Dict[str, Any] | None = None) -> pd.Series:
        """
        Scores the data using the pipeline.

        Args:
            data (pd.DataFrame): The data to score.
            context (Dict[str, Any] | None): The context for scoring.

        Returns:
            pd.Series: A Series of scores.
        """
        context = context or {}

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

        scores_df = pd.concat(scores_list, axis=1, keys=[f.name for f in self.filters])

        if self.combination_method == 'product':
            return scores_df.prod(axis=1)

        elif self.combination_method == 'weighted_avg':
            return scores_df.dot(self.weights)

        elif self.combination_method == 'min':
            return scores_df.min(axis=1)

        elif self.combination_method == 'max':
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
        """
        Filters the data using the pipeline.

        Args:
            data (pd.DataFrame): The data to filter.
            threshold (float): The threshold to use for filtering.
            context (Dict[str, Any] | None): The context for filtering.

        Returns:
            pd.Series: A Series of booleans indicating which data points passed the filter.
        """
        scores = self.score(data, context)
        return scores >= threshold

    def __repr__(self) -> str:
        return (
            f"FilterPipeline("
            f"n_filters={len(self.filters)}, "
            f"method='{self.combination_method}')"
        )
