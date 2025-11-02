from __future__ import annotations

from typing import Any, Dict

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM

from app.filters.base import ProbabilisticFilter
from app.strats.common import pick_col, safe_atr


class VolatilityRegimeFilter(ProbabilisticFilter):
    """Detect volatility regimes using HMM.

    Returns probability that asset is in high-volatility regime.
    Useful for strategy selection (e.g., mean reversion in high-vol regime).

    Example:
        filter = VolatilityRegimeFilter(n_states=2, lookback=60)
        filter.fit(historical_data)  # Train on history

        # Get current regime probabilities
        scores = filter.score(current_data)
        # scores[symbol] = 0.85 means 85% confidence in high-vol regime
    """

    def __init__(
        self,
        n_states: int = 2,
        lookback: int = 60,
        atr_period: int = 14,
        name: str | None = None
    ):
        """Initialize volatility regime filter.

        Args:
            n_states: Number of HMM states (2=low/high, 3=low/medium/high)
            lookback: Number of periods for regime detection
            atr_period: Period for ATR calculation
            name: Optional custom name
        """
        super().__init__(name)
        self.n_states = n_states
        self.lookback = lookback
        self.atr_period = atr_period

        # HMM model (will be fitted per symbol)
        self.hmm = GaussianHMM(
            n_components=n_states,
            covariance_type="full",
            n_iter=100,
            random_state=42
        )

        # Maps state indices to regime labels
        # Will be populated during fit based on mean volatility per state
        self.regime_labels = {}

    def _extract_features(self, data: pd.DataFrame) -> np.ndarray:
        """Extract volatility features from OHLCV data.

        Returns:
            Array of shape (n_periods, 2) with [atr, returns_vol]
        """
        # ATR (Average True Range)
        atr = safe_atr(data, self.atr_period)

        # Returns volatility
        close = pick_col(data, "close", "adj_close", "c", "ohlc_close")
        returns = close.pct_change()
        returns_vol = returns.rolling(self.atr_period).std()

        # Combine features
        features = pd.DataFrame({
            'atr': atr,
            'returns_vol': returns_vol
        }).dropna()

        return features.values

    def fit(self, data: pd.DataFrame, labels: pd.Series | None = None) -> VolatilityRegimeFilter:
        """Train HMM on historical volatility data.

        Args:
            data: Historical OHLCV data (single symbol)
            labels: Not used (unsupervised learning)

        Returns:
            self
        """
        features = self._extract_features(data)

        if len(features) < self.lookback:
            self._fitted = False
            return self
        
        # Fit HMM
        self.hmm.fit(features)

        # Label states by mean ATR (state 0 = lowest vol, state n-1 = highest vol)
        states = self.hmm.predict(features)
        state_means = []
        for i in range(self.n_states):
            state_data = features[states == i]
            if len(state_data) > 0:
                mean_atr = state_data[:, 0].mean()  # First column is ATR
                state_means.append((i, mean_atr))
        
        # Sort by volatility
        # self.hmm.means_ is shape (n_components, n_features)
        state_means = [(i, mean[0]) for i, mean in enumerate(self.hmm.means_)]
        
        # Sort by volatility (mean of the first feature - ATR)
        state_means.sort(key=lambda x: x[1])

        # Map indices to labels
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
        """Return probability of high-volatility regime.

        Args:
            data: OHLCV data (can be single or multi-symbol)
            context: Optional context (not used by this filter)

        Returns:
            pd.Series with symbol -> probability of high-vol regime
        """
        if not self._fitted:
            raise ValueError(
                f"{self.name} must be fitted before scoring. Call .fit() first."
            )

        # Check if multi-symbol data
        if 'symbol' in data.columns:
            # Wide format with symbol column
            return self._score_multi_symbol(data)

        # Single symbol
        return self._score_single_symbol(data)

    def _score_single_symbol(self, data: pd.DataFrame) -> pd.Series:
        """Score single symbol data."""
        features = self._extract_features(data)

        if len(features) < self.lookback:
            # Not enough data - return neutral probability
            return pd.Series([0.5], index=['symbol'])

        # Use last N periods for regime detection
        recent_features = features[-self.lookback:]

        # Get state probabilities
        state_probs = self.hmm.predict_proba(recent_features)

        # Probability of high-vol regime = prob of highest state
        high_vol_state = max(self.regime_labels.keys(),
                            key=lambda k: k)  # Highest numbered state

        # Use latest probability
        high_vol_prob = state_probs[-1, high_vol_state]

        return pd.Series([high_vol_prob], index=['symbol'])

    def _score_multi_symbol(self, data: pd.DataFrame) -> pd.Series:
        """Score multiple symbols."""
        scores = {}

        for symbol in data['symbol'].unique():
            symbol_data = data[data['symbol'] == symbol].copy()

            try:
                score = self._score_single_symbol(symbol_data)
                scores[symbol] = score.iloc[0]
            except Exception as e:
                # Handle errors gracefully - return neutral probability
                print(f"Warning: Failed to score {symbol}: {e}")
                scores[symbol] = 0.5

        return pd.Series(scores)

    def get_current_regime(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Get current regime label and confidence.

        Returns:
            {
                'regime': 'low_vol' | 'high_vol' | ...,
                'confidence': float,
                'state_probs': dict
            }
        """
        features = self._extract_features(data)
        recent = features[-self.lookback:]

        state_probs = self.hmm.predict_proba(recent)
        latest_probs = state_probs[-1]

        # Most likely state
        most_likely_state = int(np.argmax(latest_probs))
        regime = self.regime_labels.get(most_likely_state, 'unknown')
        confidence = float(latest_probs[most_likely_state])

        # All state probabilities
        state_prob_dict = {
            self.regime_labels[i]: float(latest_probs[i])
            for i in range(self.n_states)
        }

        return {
            'regime': regime,
            'confidence': confidence,
            'state_probs': state_prob_dict
        }