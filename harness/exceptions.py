class ApplicationException(Exception):
    """ Base exception for application specific errors. """

    log_trace: bool = False

    def __init__(self, message: str) -> None:
        super().__init__(message)

# Configuration Related Errors
class ConfigurationError(ApplicationException):
    """ Raised for invalid configurations such as invalid api keys, env vars, etc. """

class EnvVarNotSetError(ConfigurationError):
    """ Raised when a required env var is not set. """

    def __init__(self, name: str) -> None:
        super().__init__(f"Required environment variable '{name}' is not set.")

class EnvVarCastError(ConfigurationError, ValueError):
    """ Raised when a loaded env var can't be casted to the specified type. """

    def __init__(self, name: str) -> None:
        super().__init__(f"Environment variable '{name}' has an invalid value or format.")

class InvalidAPIKeyError(ConfigurationError):
    """ Raised when the API Key is invalid. """

    def __init__(self, service: str = "external service") -> None:
        super().__init__(f"Invalid API key for '{service}'.")

# External Service Related Errors
class ExternalServiceError(ApplicationException):
    """ Raised for errors related to external services such as rate limits, empty response etc. """

class RateLimitedError(ExternalServiceError):
    """ Raised when the external service has applied rate limits and execution can't procced. """

    def __init__(self, service: str = "external service", retry_after: float | None = None) -> None:
        message = f"'{service}' has applied rate limits."

        if retry_after is not None:
            message += f" Retry after {retry_after} seconds."

        super().__init__(message)
        self.retry_after = retry_after

class UnexpectedResponseError(ExternalServiceError):
    """ Raised when the response from the external service is not in an acceptable form. """

    log_trace = True

    def __init__(self, service: str = "external service", detail: str | None = None) -> None:
        message = f"'{service}' returned an unexpected response."

        if detail:
            message += f" {detail}"

        super().__init__(message)