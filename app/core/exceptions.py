class ProviderError(Exception):
    """Raised when a data provider returns an invalid or failed response."""

class ConfigError(Exception):
    """Raised for missing/malformed configuration."""