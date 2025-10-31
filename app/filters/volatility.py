from __future__ import annotations

from typing import Any, Dict

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM

from app.filters.base import ProbabilisticFilter
from app.strats.common import pick_col, safe_atr


class VolatilityRegimeFilter(ProbabilisticFilter):
    """
    A probabilistic filter that detects volatility regimes using a Hidden Markov Model (HMM).
    """

    def __init__(
        self,
        n_states: int = 2,
        lookback: int = 60,
        atr_period: int = 14,
        name: str | None = None
    ):
        """
        Initializes the VolatilityRegimeFilter.

        Args:
            n_states (int): The number of HMM states.
            lookback (int): The number of periods to use for regime detection.
            atr_period (int): The period for ATR calculation.
            name (str | None): The name of the filter.
        """
        super().__init__(name)
        self.n_states = n_states
        self.lookback = lookback
        self.atr_period = atr_period
        self.hmm = GaussianHMM(
            n_components=n_states,
            covariance_type="full",
            n_iter=100,
            random_state=42
        )
        self.regime_labels = {}

    def _extract_features(self, data: pd.DataFrame) -> np.ndarray:
        """
        Extracts volatility features from OHLCV data.

        Args:
            data (pd.DataFrame): The OHLCV data.

        Returns:
            np.ndarray: An array of features.
        """
        atr = safe_atr(data, self.atr_period)
        close = pick_col(data, "close", "adj_close", "c", "ohlc_close")
        returns = close.pct_change()
        returns_vol = returns.rolling(self.atr_period).std()
        features = pd.DataFrame({
            'atr': atr,
            'returns_vol': returns_vol
        }).dropna()
        return features.values

    def fit(self, data: pd.DataFrame, labels: pd.Series | None = None) -> VolatilityRegimeFilter:
        """
        Fits the HMM to the data.

        Args:
            data (pd.DataFrame): The historical OHLCV data.
            labels (pd.Series | None): Not used.

        Returns:
            VolatilityRegimeFilter: The fitted filter.
        """
        features = self._extract_features(data)
        if len(features) < self.lookback:
            raise ValueError(
                f"Need at least {self.lookback} periods of clean data, "
                f"got {len(features)}"
            )
        self.hmm.fit(features)
        states = self.hmm.predict(features)
        state_means = []
        for i in range(self.n_states):
            state_data = features[states == i]
            if len(state_data) > 0:
                mean_atr = state_data[:, 0].mean()
                state_means.append((i, mean_atr))
        state_means.sort(key=lambda x: x[1])
        if self.n_states == 2:
            labels = ['low_vol', 'high_vol']
        elif self.n_states == 3:
            labels = ['low_vol', 'medium_vol', 'high_vol']
        else:
            labels = [f'vol_state_{i}' for i in range(self.n_states)]
        self.regime_labels = {state_means[i][0]: labels[i] for i in range(len(state_means))}
        self._fitted = True
        return self

    def score(self, data: pd.DataFrame, context: Dict[str, Any] | None = None) -> pd.Series:
        """
        Scores the data based on the probability of being in a high-volatility regime.

        Args:
            data (pd.DataFrame): The OHLCV data.
            context (Dict[str, Any] | None): Not used.

        Returns:
            pd.Series: A Series of scores.
        """
        if not self._fitted:
            raise ValueError(
                f"{self.name} must be fitted before scoring. Call .fit() first."
            )
        if 'symbol' in data.columns:
            return self._score_multi_symbol(data)
        return self._score_single_symbol(data)

    def _score_single_symbol(self, data: pd.DataFrame) -> pd.Series:
        """
        Scores a single symbol.

        Args:
            data (pd.DataFrame): The OHLCV data for a single symbol.

        Returns:
            pd.Series: A Series with the score for the symbol.
        """
        features = self._extract_features(data)
        if len(features) < self.lookback:
            return pd.Series([0.5], index=['symbol'])
        recent_features = features[-self.lookback:]
        state_probs = self.hmm.predict_proba(recent_features)
        high_vol_state = max(self.regime_labels.keys(), key=lambda k: k)
        high_vol_prob = state_probs[-1, high_vol_state]
        return pd.Series([high_vol_prob], index=['symbol'])

    def _score_multi_symbol(self, data: pd.DataFrame) -> pd.Series:
        """
        Scores multiple symbols.

        Args:
            data (pd.DataFrame): The OHLCV data for multiple symbols.

        Returns:
            pd.Series: A Series with the scores for each symbol.
        """
        scores = {}
        for symbol in data['symbol'].unique():
            symbol_data = data[data['symbol'] == symbol].copy()
            try:
                score = self._score_single_symbol(symbol_data)
                scores[symbol] = score.iloc[0]
            except Exception as e:
                print(f"Warning: Failed to score {symbol}: {e}")
                scores[symbol] = 0.5
        return pd.Series(scores)

    def get_current_regime(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Gets the current volatility regime.

        Args:
            data (pd.DataFrame): The OHLCV data.

        Returns:
            Dict[str, Any]: A dictionary with the current regime information.
        """
        features = self._extract_features(data)
        recent = features[-self.lookback:]
        state_probs = self.hmm.predict_proba(recent)
        latest_probs = state_probs[-1]
        most_likely_state = int(np.argmax(latest_probs))
        regime = self.regime_labels.get(most_likely_state, 'unknown')
        confidence = float(latest_probs[most_likely_state])
        state_prob_dict = {
            self.regime_labels[i]: float(latest_probs[i])
            for i in range(self.n_states)
        }
        return {
            'regime': regime,
            'confidence': confidence,
            'state_probs': state_prob_dict
        }
