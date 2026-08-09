"""Seed SDK — BytePlus Seed Audio generation (BytePlus by default; fal.ai optional)."""
from .client import SeedClient
from .config import __version__
from .exceptions import (
    APIError,
    AuthError,
    ProviderError,
    SeedError,
    ValidationError,
)
from .llm import LLMParams, LLMResult, SeedLLM
from .providers import AudioProvider, BytePlusProvider, FalProvider, get_provider
from .types import AudioParams, TaskResult

__all__ = [
    "SeedClient",
    "__version__",
    # Exceptions
    "SeedError",
    "AuthError",
    "ValidationError",
    "APIError",
    "ProviderError",
    # Types
    "AudioParams",
    "TaskResult",
    "LLMParams",
    "LLMResult",
    # Providers
    "AudioProvider",
    "FalProvider",
    "BytePlusProvider",
    "get_provider",
    # LLM
    "SeedLLM",
]
