"""Ollama LLM client for local inference.

Ollama provides local LLM inference, keeping PHI on-premise without
requiring a BAA.
"""

import json
import logging
import time
from typing import Any

import requests

from ..config import Config
from .base import BaseLLMClient, LLMResponse, LLMProfile, StructuredLLMResponse

logger = logging.getLogger(__name__)

# Module-level profiling storage for analysis
_profile_history: list[dict[str, Any]] = []
_profile_history_max = 100  # Keep last N profiles


def _extract_profile(data: dict[str, Any]) -> LLMProfile:
    """Extract profiling data from Ollama response.

    Ollama returns timing in nanoseconds, we convert to milliseconds.
    """
    ns_to_ms = 1_000_000  # nanoseconds to milliseconds

    return LLMProfile(
        input_tokens=data.get("prompt_eval_count", 0),
        output_tokens=data.get("eval_count", 0),
        total_ms=data.get("total_duration", 0) / ns_to_ms,
        load_ms=data.get("load_duration", 0) / ns_to_ms,
        prefill_ms=data.get("prompt_eval_duration", 0) / ns_to_ms,
        generation_ms=data.get("eval_duration", 0) / ns_to_ms,
    )


def _store_profile(profile: LLMProfile, context: str = "") -> None:
    """Store profile in history for analysis."""
    global _profile_history
    _profile_history.append({
        "timestamp": time.time(),
        "context": context,
        **profile.to_dict(),
    })
    # Trim to max size
    if len(_profile_history) > _profile_history_max:
        _profile_history = _profile_history[-_profile_history_max:]


def get_profile_history() -> list[dict[str, Any]]:
    """Get stored profile history for analysis."""
    return _profile_history.copy()


def get_profile_summary() -> dict[str, Any]:
    """Get summary statistics from profile history."""
    if not _profile_history:
        return {"count": 0, "message": "No profiles recorded"}

    profiles = _profile_history
    n = len(profiles)

    def avg(key: str) -> float:
        vals = [p[key] for p in profiles if key in p]
        return sum(vals) / len(vals) if vals else 0

    def percentile(key: str, pct: float) -> float:
        vals = sorted(p[key] for p in profiles if key in p)
        if not vals:
            return 0
        idx = int(len(vals) * pct)
        return vals[min(idx, len(vals) - 1)]

    cold_starts = sum(1 for p in profiles if p.get("model_was_cold", False))

    return {
        "count": n,
        "cold_starts": cold_starts,
        "avg_total_ms": round(avg("total_ms"), 1),
        "avg_prefill_ms": round(avg("prefill_ms"), 1),
        "avg_generation_ms": round(avg("generation_ms"), 1),
        "avg_input_tokens": round(avg("input_tokens"), 0),
        "avg_output_tokens": round(avg("output_tokens"), 0),
        "avg_tokens_per_second": round(avg("tokens_per_second"), 1),
        "p50_total_ms": round(percentile("total_ms", 0.5), 1),
        "p95_total_ms": round(percentile("total_ms", 0.95), 1),
        "p50_generation_ms": round(percentile("generation_ms", 0.5), 1),
        "p95_generation_ms": round(percentile("generation_ms", 0.95), 1),
    }


def clear_profile_history() -> None:
    """Clear stored profile history."""
    global _profile_history
    _profile_history = []


class OllamaClient(BaseLLMClient):
    """Ollama API client for local LLM inference."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int = 300,  # Increased for large models like 70b
        num_ctx: int = 8192,  # Context window size
        enable_profiling: bool = True,  # Store profiles for analysis
    ):
        """Initialize Ollama client.

        Args:
            base_url: Ollama API base URL. Uses config if None.
            model: Model to use. Uses config if None.
            timeout: Request timeout in seconds.
            num_ctx: Context window size in tokens.
            enable_profiling: Whether to store profiles in history.
        """
        self.base_url = (base_url or Config.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or Config.OLLAMA_MODEL
        self.timeout = timeout
        self.num_ctx = num_ctx
        self.enable_profiling = enable_profiling
        self.session = requests.Session()

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        profile_context: str = "",
    ) -> LLMResponse:
        """Generate a response using Ollama.

        Args:
            prompt: The user prompt.
            system_prompt: Optional system prompt.
            temperature: Sampling temperature (0.0 = deterministic).
            max_tokens: Maximum tokens in response.
            profile_context: Optional context string for profiling (e.g., "clabsi_extraction").

        Returns:
            LLMResponse with content, metadata, and profiling data.
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": self.num_ctx,
            },
        }

        try:
            response = self.session.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()

            data = response.json()

            # Extract detailed profiling
            profile = _extract_profile(data)

            # Log profiling summary
            logger.info(f"LLM generate [{profile_context or 'unnamed'}]: {profile.summary()}")

            # Store for analysis
            if self.enable_profiling:
                _store_profile(profile, profile_context)

            return LLMResponse(
                content=data.get("message", {}).get("content", ""),
                raw_response=data,
                input_tokens=profile.input_tokens,
                output_tokens=profile.output_tokens,
                model=self.model,
                finish_reason=data.get("done_reason"),
                profile=profile,
            )

        except requests.RequestException as e:
            logger.error(f"Ollama request failed: {e}")
            raise

    def generate_structured(
        self,
        prompt: str,
        output_schema: dict[str, Any],
        system_prompt: str | None = None,
        temperature: float = 0.0,
        profile_context: str = "",
    ) -> dict[str, Any]:
        """Generate a structured JSON response.

        Uses Ollama's format parameter for JSON output.

        Note: For profiling data, use generate_structured_with_profile() instead.
        """
        result = self.generate_structured_with_profile(
            prompt=prompt,
            output_schema=output_schema,
            system_prompt=system_prompt,
            temperature=temperature,
            profile_context=profile_context,
        )
        return result.data

    def generate_structured_with_profile(
        self,
        prompt: str,
        output_schema: dict[str, Any],
        system_prompt: str | None = None,
        temperature: float = 0.0,
        profile_context: str = "",
    ) -> StructuredLLMResponse:
        """Generate a structured JSON response with profiling data.

        Args:
            prompt: The user prompt.
            output_schema: JSON schema for the expected output.
            system_prompt: Optional system prompt.
            temperature: Sampling temperature (0.0 = deterministic).
            profile_context: Optional context string for profiling.

        Returns:
            StructuredLLMResponse with parsed data and profiling.
        """
        # Build system prompt with JSON schema
        schema_prompt = f"""You must respond with valid JSON matching this schema:
{json.dumps(output_schema, indent=2)}

{system_prompt or ''}"""

        messages = [
            {"role": "system", "content": schema_prompt},
            {"role": "user", "content": prompt},
        ]

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": temperature,
                "num_ctx": self.num_ctx,
            },
        }

        try:
            response = self.session.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()

            data = response.json()
            content = data.get("message", {}).get("content", "{}")

            # Extract detailed profiling
            profile = _extract_profile(data)

            # Log profiling summary
            logger.info(f"LLM structured [{profile_context or 'unnamed'}]: {profile.summary()}")

            # Store for analysis
            if self.enable_profiling:
                _store_profile(profile, profile_context)

            # Parse JSON response
            parsed = json.loads(content)

            return StructuredLLMResponse(
                data=parsed,
                profile=profile,
                raw_response=data,
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Ollama JSON response: {e}")
            raise ValueError(f"Invalid JSON response: {e}")
        except requests.RequestException as e:
            logger.error(f"Ollama request failed: {e}")
            raise

    def is_available(self) -> bool:
        """Check if Ollama is running and the model is available."""
        try:
            response = self.session.get(
                f"{self.base_url}/api/tags",
                timeout=5,
            )
            response.raise_for_status()

            # Check if our model is in the list
            data = response.json()
            models = [m.get("name") for m in data.get("models", [])]

            # Handle model names with and without tags
            model_base = self.model.split(":")[0]
            return any(
                m == self.model or m.startswith(model_base)
                for m in models
            )

        except requests.RequestException:
            return False

    @property
    def model_name(self) -> str:
        """Get the model name."""
        return self.model

    def pull_model(self) -> bool:
        """Pull the model if not available."""
        try:
            logger.info(f"Pulling model {self.model}...")
            response = self.session.post(
                f"{self.base_url}/api/pull",
                json={"name": self.model},
                timeout=3600,  # Long timeout for model download
                stream=True,
            )
            response.raise_for_status()

            # Stream progress
            for line in response.iter_lines():
                if line:
                    data = json.loads(line)
                    if "status" in data:
                        logger.info(f"Pull status: {data['status']}")

            return True

        except requests.RequestException as e:
            logger.error(f"Failed to pull model: {e}")
            return False
