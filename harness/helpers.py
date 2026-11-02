import os
from collections.abc import Callable

def load_env_var_or_else_throw(
    name: str,
    *,
    exc: type[Exception] = ValueError,
    msg: str | None = None,
) -> str:
    """ Load the environment variable, throw an exception (or provided) if not loaded. """

    if (value := os.getenv(name)) is None:
        raise exc(
            msg or f"'{name}' enviornment variable is not set."
        )

    return value

def load_env_var_or_default(
    name: str,
    *,
    default: str,
) -> str:
    """ Load the environment variable, return the provided default if not loaded. """

    if (value := os.getenv(name)) is None:
        return default

    return value

def load_env_var_as_or_else_throw[T](
    name: str,
    *,
    cast: Callable[[str], T],
    cast_exc: type[Exception] = ValueError,
    cast_msg: str | None = None,
    load_exc: type[Exception] = ValueError,
    load_msg: str | None = None,
) -> T:
    """ Load env var and cast, else error. """

    try:
        if (value := os.getenv(name)) is None:
            raise load_exc(
                load_msg or f"'{name}' enviornment variable is not set."
            )

        return cast(value)

    except (ValueError, TypeError) as exc:
        raise cast_exc(
            cast_msg or f"Invalid or missing '{name}' enviornment variable."
        ) from exc

def load_env_var_as_or_default[T](
    name: str,
    *,
    cast: Callable[[str], T],
    default: T,
) -> T:
    """ Load and cast enviornment variable, provided default if ValueError or TypeError. """

    if (value := os.getenv(name)) is None:
        return default

    try:
        return cast(value)
    except (ValueError, TypeError):
        return default
    