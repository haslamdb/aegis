"""LLM backend abstraction layer."""

from .base import BaseLLMClient, LLMResponse, LLMProfile, StructuredLLMResponse
from .ollama import OllamaClient
from .factory import get_llm_client

# Profiling utilities
from .ollama import (
    get_profile_history,
    get_profile_summary,
    clear_profile_history,
)

__all__ = [
    # Core classes
    "BaseLLMClient",
    "LLMResponse",
    "LLMProfile",
    "StructuredLLMResponse",
    "OllamaClient",
    "get_llm_client",
    # Profiling
    "get_profile_history",
    "get_profile_summary",
    "clear_profile_history",
]
