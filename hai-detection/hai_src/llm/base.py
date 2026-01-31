"""Abstract base class for LLM clients."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class LLMProfile:
    """Detailed profiling data from an LLM call.

    All durations are in milliseconds for readability.
    """

    # Token counts
    input_tokens: int = 0
    output_tokens: int = 0

    # Timing breakdown (milliseconds)
    total_ms: float = 0.0
    load_ms: float = 0.0  # Model loading time (0 if already loaded)
    prefill_ms: float = 0.0  # Time to process input (prompt_eval)
    generation_ms: float = 0.0  # Time to generate output (eval)

    # Derived metrics
    @property
    def tokens_per_second(self) -> float:
        """Output tokens per second."""
        if self.generation_ms > 0:
            return self.output_tokens / (self.generation_ms / 1000)
        return 0.0

    @property
    def prefill_tokens_per_second(self) -> float:
        """Input tokens processed per second."""
        if self.prefill_ms > 0:
            return self.input_tokens / (self.prefill_ms / 1000)
        return 0.0

    @property
    def model_was_cold(self) -> bool:
        """Whether model had to be loaded (cold start)."""
        return self.load_ms > 1000  # >1s indicates cold load

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_ms": round(self.total_ms, 1),
            "load_ms": round(self.load_ms, 1),
            "prefill_ms": round(self.prefill_ms, 1),
            "generation_ms": round(self.generation_ms, 1),
            "tokens_per_second": round(self.tokens_per_second, 1),
            "prefill_tokens_per_second": round(self.prefill_tokens_per_second, 1),
            "model_was_cold": self.model_was_cold,
        }

    def summary(self) -> str:
        """Human-readable summary."""
        parts = [
            f"in={self.input_tokens}tok",
            f"out={self.output_tokens}tok",
            f"total={self.total_ms:.0f}ms",
        ]
        if self.model_was_cold:
            parts.append(f"load={self.load_ms:.0f}ms")
        parts.extend([
            f"prefill={self.prefill_ms:.0f}ms",
            f"gen={self.generation_ms:.0f}ms",
            f"({self.tokens_per_second:.1f}tok/s)",
        ])
        return " | ".join(parts)


@dataclass
class LLMResponse:
    """Response from an LLM call."""
    content: str
    raw_response: dict[str, Any] | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    finish_reason: str | None = None
    profile: LLMProfile | None = None  # Detailed profiling data


@dataclass
class StructuredLLMResponse:
    """Response from a structured LLM call with profiling."""
    data: dict[str, Any]  # Parsed JSON response
    profile: LLMProfile
    raw_response: dict[str, Any] | None = None


class BaseLLMClient(ABC):
    """Abstract base class for LLM API clients."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Generate a response from the LLM.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature (0.0 = deterministic)
            max_tokens: Maximum tokens in response

        Returns:
            LLMResponse with content and metadata
        """
        pass

    @abstractmethod
    def generate_structured(
        self,
        prompt: str,
        output_schema: dict[str, Any],
        system_prompt: str | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Generate a structured response matching a JSON schema.

        Args:
            prompt: The user prompt
            output_schema: JSON schema for the expected output
            system_prompt: Optional system prompt
            temperature: Sampling temperature

        Returns:
            Parsed JSON response matching the schema
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the LLM backend is available."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Get the model name being used."""
        pass
