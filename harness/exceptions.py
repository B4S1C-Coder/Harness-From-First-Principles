import errno
from pathlib import Path

class ApplicationException(Exception):
    """ Base exception for application specific errors. """

    log_trace: bool = False

    def __init__(self, message: str) -> None:
        self.message = message
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

class NotADirectory(ConfigurationError, NotADirectoryError):
    """ Specified path is not a directory. """

    def __init__(self, root: str | Path) -> None:
        root_str = str(root)
        msg = f"Path: '{root_str}' is not a directory."

        ConfigurationError.__init__(self, msg)
        NotADirectoryError.__init__(self, errno.ENOTDIR, msg, root_str)

# External Service Related Errors
class ExternalServiceError(ApplicationException):
    """ Raised for errors related to external services such as rate limits, empty response etc. """

class ConnectionError(ExternalServiceError):
    """ Raised when connection with external service can't be established """

    def __init__(self, service: str = "external service") -> None:
        super().__init__(f"{service}: Unable to establish connection with external servce.")

class TimeoutError(ExternalServiceError):
    """ Raised when connection with external service has timed out """

    def __init__(self, service: str = "external service") -> None:
        super().__init__(f"{service}: Conection timed out.")

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

# Tool Execution related errors
class ToolExecutionError(ApplicationException):
    """ Raised for errors during tool execution or invalid tool calls. """

class PermissionDenied(ToolExecutionError, PermissionError):
    """ Raised when a general action lacks the required permissions. """

    def __init__(self, message: str) -> None:
        ToolExecutionError.__init__(self, message)
        PermissionError.__init__(self, None, message)