import os
from collections.abc import Callable
from typing import Final, overload
from .exceptions import EnvVarNotSetError, EnvVarCastError

_NO_DEFAULT: Final = object()

@overload
def load_env(name: str, *, cast: None = None) -> str: ...
@overload
def load_env[T](name: str, *, cast: Callable[[str], T]) -> T: ...
@overload
def load_env[D](name: str, *, default: D, cast: None = None) -> D | str: ...
@overload
def load_env[T, D](name: str, *, cast: Callable[[str], T], default: D) -> T | D: ...

def load_env[T](
    name: str,
    *,
    cast: Callable[[str], T] | None = None,
    default: object = _NO_DEFAULT,
) -> T | str | object:
    """
    Load an environment variable, optionally casting its value or returning a default.

    Behaviour depends on whether a cast function and a default value are provided:

    | Configuration       | Missing variable  | Invalid cast      |
    |---------------------|-------------------|-------------------|
    | No cast, no default | EnvVarNotSetError | N/A               |
    | Cast, no default    | EnvVarNotSetError | EnvVarCastError   |
    | No cast, default    | Return default    | N/A               |
    | Cast, default       | Return default    | Return default    |

    The default value is optional. If omitted, missing variables and casting
    failures raise their respective exceptions. Passing `None` explicitly as
    the default is supported.

    Args:
        name: Name of the environment variable to load.
        cast: Optional callable used to convert the environment variable's
            string value into the desired type.
        default: Optional fallback value returned when the variable is missing
            or casting fails. If omitted, the corresponding exception is raised.

    Returns:
        The environment variable's value, optionally cast, or the provided
        default value.

    Raises:
        EnvVarNotSetError: If the variable is missing and no default is provided.
        EnvVarCastError: If casting fails and no default is provided.

    Usage Examples:

        ```python
        # Missing variable raises EnvVarNotSetError
        api_key = load_env("API_KEY")

        # Missing variable returns None
        optional_key = load_env("OPTIONAL_KEY", default=None)

        # Missing or invalid integer returns 8080
        port = load_env("PORT", cast=int, default=8080)

        # Missing or invalid value returns None
        timeout = load_env("TIMEOUT", cast=float, default=None)

        # Missing or invalid value raises EnvVarCastError
        timeout = load_env("TIMEOUT", cast=float)
        ```
    """

    if (value := os.getenv(name)) is None:
        if default is not _NO_DEFAULT:
            return default

        raise EnvVarNotSetError(name)

    if cast is None:
        return value

    try:
        return cast(value)
    except (ValueError, TypeError) as exc:
        if default is not _NO_DEFAULT:
            return default

        raise EnvVarCastError(name) from exc
    