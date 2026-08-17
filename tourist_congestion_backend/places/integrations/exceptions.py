class ExternalAPIError(RuntimeError):
    """Raised when an external data provider cannot return usable data."""


class ExternalAPIConfigurationError(ExternalAPIError):
    """Raised when credentials or required provider settings are missing."""
