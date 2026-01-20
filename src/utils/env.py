"""Environment switching utilities for Corporate Context.

This module provides utilities for environment-aware configuration:
- Env enum for type-safe environment values
- current_env() to get the current environment
- switch_env() to select values based on environment
"""

from collections.abc import Callable
from enum import Enum
from typing import TypeVar

from src.utils.config import get_grapevine_environment

T = TypeVar("T")


class Env(str, Enum):
    """Grapevine deployment environment."""

    LOCAL = "local"
    STAGING = "staging"
    PRODUCTION = "production"


def current_env() -> Env:
    """Get the current Grapevine environment.

    Returns:
        Current environment from GRAPEVINE_ENVIRONMENT env var

    Raises:
        ValueError: If GRAPEVINE_ENVIRONMENT contains an unexpected value
    """
    env_str = get_grapevine_environment()

    try:
        return Env(env_str)
    except ValueError:
        raise ValueError(f"Unexpected environment: {env_str}")


def switch_env(envs: dict[str, T | Callable[[], T]], env: Env | None = None) -> T:
    """Switch on environment to return environment-specific values.

    Args:
        envs: Dictionary mapping environments to values or callables that return values
        env: Optional environment to use (defaults to current_env())

    Returns:
        The value for the specified environment

    Example:
        >>> from src.utils.env import Env, switch_env
        >>> api_url = switch_env({
        ...     Env.LOCAL: "http://localhost:3000/api",
        ...     Env.STAGING: "https://staging.api.example.com",
        ...     Env.PRODUCTION: "https://api.example.com"
        ... })
        >>> # Or with callables:
        >>> config = switch_env({
        ...     Env.LOCAL: lambda: load_local_config(),
        ...     Env.STAGING: lambda: load_staging_config(),
        ...     Env.PRODUCTION: lambda: load_prod_config()
        ... })
    """
    if env is None:
        env = current_env()

    value = envs[env]

    # If it's a callable, call it; otherwise return the value directly
    if callable(value):
        return value()
    return value


# This map assumes environment parity between grapevine and gather, which may not always be accurate/appropriate
# for your use-case, so adjust accordingly.
GATHER_API_URL = switch_env(
    {
        Env.PRODUCTION: "https://api.v2.gather.town/api/v2",
        Env.STAGING: "https://api.v2.staging.gather.town/api/v2",
        Env.LOCAL: "http://localhost:3000/api/v2",
    }
)
