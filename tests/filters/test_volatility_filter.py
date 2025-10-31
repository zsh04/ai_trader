import numpy as np
import pandas as pd
import pytest

from app.filters.volatility import VolatilityRegimeFilter
from app.filters.base import FilterPipeline


@pytest.fixture
def sample_ohlcv_data():
    """Generate synthetic OHLCV data with regime switches."""
    np.random.seed(42)
    dates = pd.date_range('2023-01-01', periods=200, freq='D')
    
    # Create low-vol period (first 100 days)
    low_vol_returns = np.random.normal(0.001, 0.01, 100)
    
    # Create high-vol period (next 100 days)
    high_vol_returns = np.random.normal(0.001, 0.03, 100)
    
    returns = np.concatenate([low_vol_returns, high_vol_returns])
    
    # Generate price from returns
    prices = 100 * np.cumprod(1 + returns)
    
    # Generate OHLC around close
    df = pd.DataFrame({
        'close': prices,
        'open': prices * (1 + np.random.uniform(-0.005, 0.005, 200)),
        'high': prices * (1 + np.random.uniform(0, 0.01, 200)),
        'low': prices * (1 + np.random.uniform(-0.01, 0, 200)),
        'volume': np.random.randint(1000000, 5000000, 200)
    }, index=dates)
    
    return df


@pytest.fixture
def multi_symbol_data():
    """Generate multi-symbol data."""
    np.random.seed(42)
    dates = pd.date_range('2023-01-01', periods=100, freq='D')
    
    symbols = ['AAPL', 'MSFT', 'GOOGL']
    data_list = []
    
    for symbol in symbols:
        returns = np.random.normal(0.001, 0.02, 100)
        prices = 100 * np.cumprod(1 + returns)
        
        df = pd.DataFrame({
            'symbol': symbol,
            'close': prices,
            'open': prices * (1 + np.random.uniform(-0.005, 0.005, 100)),
            'high': prices * (1 + np.random.uniform(0, 0.01, 100)),
            'low': prices * (1 + np.random.uniform(-0.01, 0, 100)),
            'volume': np.random.randint(1000000, 5000000, 100)
        }, index=dates)
        
        data_list.append(df)
    
    return pd.concat(data_list, ignore_index=True)


def test_filter_initialization():
    """Test filter can be initialized."""
    filter = VolatilityRegimeFilter(n_states=2, lookback=60)
    
    assert filter.n_states == 2
    assert filter.lookback == 60
    assert not filter.is_fitted


def test_filter_fit(sample_ohlcv_data):
    """Test filter can be fitted on data."""
    filter = VolatilityRegimeFilter(n_states=2, lookback=60)
    
    # Fit should succeed
    filter.fit(sample_ohlcv_data)
    
    assert filter.is_fitted
    assert len(filter.regime_labels) == 2
    assert 'low_vol' in filter.regime_labels.values()
    assert 'high_vol' in filter.regime_labels.values()


def test_filter_score_single_symbol(sample_ohlcv_data):
    """Test scoring on single symbol."""
    filter = VolatilityRegimeFilter(n_states=2, lookback=60)
    filter.fit(sample_ohlcv_data[:150])  # Fit on training data
    
    # Score on test data (high-vol period)
    scores = filter.score(sample_ohlcv_data[150:])
    
    assert isinstance(scores, pd.Series)
    assert len(scores) == 1
    assert 0 <= scores.iloc[0] <= 1
    
    # Should detect high volatility in second half
    # (this is probabilistic, so we use a loose threshold)
    assert scores.iloc[0] > 0.3  # At least some signal


def test_filter_score_multi_symbol(multi_symbol_data):
    """Test scoring on multiple symbols."""
    filter = VolatilityRegimeFilter(n_states=2, lookback=50)
    
    # Fit on first symbol
    aapl_data = multi_symbol_data[multi_symbol_data['symbol'] == 'AAPL']
    filter.fit(aapl_data)
    
    # Score all symbols
    scores = filter.score(multi_symbol_data)
    
    assert isinstance(scores, pd.Series)
    assert len(scores) == 3
    assert all(0 <= s <= 1 for s in scores)
    assert 'AAPL' in scores.index


def test_filter_binary_threshold(sample_ohlcv_data):
    """Test binary filtering with threshold."""
    filter = VolatilityRegimeFilter(n_states=2, lookback=60)
    filter.fit(sample_ohlcv_data[:150])
    
    # Binary filter with threshold
    mask = filter.filter(sample_ohlcv_data[150:], threshold=0.6)
    
    assert isinstance(mask, pd.Series)
    assert mask.dtype == bool


def test_get_current_regime(sample_ohlcv_data):
    """Test regime extraction."""
    filter = VolatilityRegimeFilter(n_states=2, lookback=60)
    filter.fit(sample_ohlcv_data)
    
    regime_info = filter.get_current_regime(sample_ohlcv_data)
    
    assert 'regime' in regime_info
    assert 'confidence' in regime_info
    assert 'state_probs' in regime_info
    
    assert regime_info['regime'] in ['low_vol', 'high_vol']
    assert 0 <= regime_info['confidence'] <= 1
    assert len(regime_info['state_probs']) == 2


def test_filter_pipeline():
    """Test FilterPipeline with volatility filter."""
    filter1 = VolatilityRegimeFilter(n_states=2, lookback=60)
    filter2 = VolatilityRegimeFilter(n_states=2, lookback=30)  # Different window
    
    pipeline = FilterPipeline(
        filters=[filter1, filter2],
        combination_method='mean'
    )
    
    assert len(pipeline.filters) == 2
    assert pipeline.combination_method == 'mean'


def test_pipeline_score(sample_ohlcv_data):
    """Test pipeline scoring."""
    filter1 = VolatilityRegimeFilter(n_states=2, lookback=60)
    filter1.fit(sample_ohlcv_data)
    
    filter2 = VolatilityRegimeFilter(n_states=2, lookback=30)
    filter2.fit(sample_ohlcv_data)
    
    pipeline = FilterPipeline(
        filters=[filter1, filter2],
        combination_method='product'
    )
    
    scores = pipeline.score(sample_ohlcv_data)
    
    assert isinstance(scores, pd.Series)
    assert len(scores) == 1
    assert 0 <= scores.iloc[0] <= 1


def test_insufficient_data_handling():
    """Test graceful handling of insufficient data."""
    filter = VolatilityRegimeFilter(n_states=2, lookback=60)
    
    # Create minimal data
    short_data = pd.DataFrame({
        'close': [100, 101, 102],
        'open': [100, 101, 102],
        'high': [101, 102, 103],
        'low': [99, 100, 101],
        'volume': [1000, 1000, 1000]
    })
    
    with pytest.raises(ValueError, match="Need at least"):
        filter.fit(short_data)


def test_score_before_fit():
    """Test that scoring before fit raises error."""
    filter = VolatilityRegimeFilter(n_states=2, lookback=60)
    
    data = pd.DataFrame({
        'close': [100, 101, 102],
        'open': [100, 101, 102],
        'high': [101, 102, 103],
        'low': [99, 100, 101],
        'volume': [1000, 1000, 1000]
    })
    
    with pytest.raises(ValueError, match="must be fitted"):
        filter.score(data)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])