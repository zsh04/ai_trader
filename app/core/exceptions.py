class AITraderError(Exception):
    """Base class for all AI Trader exceptions."""


class ProviderError(AITraderError):
    """Raised when a data provider returns an invalid or failed response."""


class ConfigError(AITraderError):
    """Raised for missing/malformed configuration."""


class DataValidationError(AITraderError):
    """Raised when retrieved data fails sanity or schema validation."""


class TradeExecutionError(AITraderError):
    """Raised when order placement or trade logic fails."""


__all__ = [
    "AITraderError",
    "ProviderError",
    "ConfigError",
    "DataValidationError",
    "TradeExecutionError",
]
