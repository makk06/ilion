class ExternalAPIError(RuntimeError):
    """Raised when an external data provider cannot return usable data."""


class ExternalAPIConfigurationError(ExternalAPIError):
    """Raised when credentials or required provider settings are missing."""


class ExternalAPIAuthError(ExternalAPIError):
    """Raised for rejected credentials; retrying unchanged credentials is wasteful."""


class ExternalAPIQuotaError(ExternalAPIError):
    """Raised when a provider asks clients to stop until its quota resets."""
