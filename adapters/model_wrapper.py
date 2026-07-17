"""
Generic OpenAI-compatible model wrapper for Agent Forge.

Supports multiple providers: Gemini, Meta AI, OpenAI, and any OpenAI-compatible API.
"""

import os
from typing import Any

from openai import OpenAI


class ModelWrapper:
    """
    Generic wrapper for OpenAI-compatible model APIs.

    Supports multiple providers through configuration.
    Constructs once at startup and provides model access to agents.
    """

    def __init__(self, api_key: str, model_id: str, base_url: str, provider: str = "generic"):
        """
        Initialize model wrapper.

        Args:
            api_key: API key for the model provider
            model_id: Model identifier
            base_url: Base URL for the API endpoint
            provider: Provider name (for logging/debugging)

        Raises:
            ValueError: If API key is missing
            ConnectionError: If model is unavailable
        """
        if not api_key:
            raise ValueError(f"{provider.upper()}_API_KEY is required")

        self.api_key = api_key
        self.model_id = model_id
        self.base_url = base_url
        self.provider = provider

        # Create OpenAI client configured for the provider
        self._client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

        # Verify model is available at startup
        self._verify_model_availability()

    def _verify_model_availability(self) -> None:
        """
        Verify that the model is available and accessible.

        Raises:
            ConnectionError: If model is unavailable or misconfigured
        """
        try:
            # Make a minimal test request
            response = self._client.chat.completions.create(
                model=self.model_id,
                messages=[{"role": "user", "content": "test"}],
                max_tokens=5,
                temperature=0.0,
            )

            if not response or not response.choices:
                raise ConnectionError(
                    f"Model {self.model_id} ({self.provider}) returned empty response"
                )

        except Exception as e:
            raise ConnectionError(
                f"Failed to verify {self.provider} model {self.model_id} availability: {e}"
            ) from e

    @property
    def client(self) -> OpenAI:
        """
        Get the configured OpenAI client.

        Returns:
            OpenAI client configured for the provider endpoint
        """
        return self._client

    def get_model_id(self) -> str:
        """
        Get the model identifier.

        Returns:
            Model ID string
        """
        return self.model_id

    def get_provider(self) -> str:
        """
        Get the provider name.

        Returns:
            Provider name string
        """
        return self.provider

    def create_completion(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Any:
        """
        Create a chat completion.

        Args:
            messages: List of message dictionaries
            temperature: Sampling temperature (0.0 = deterministic)
            max_tokens: Maximum tokens to generate
            tools: Optional tool definitions for function calling
            **kwargs: Additional OpenAI API parameters

        Returns:
            OpenAI ChatCompletion response

        Raises:
            Exception: If API call fails
        """
        params: dict[str, Any] = {
            "model": self.model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }

        if tools:
            params["tools"] = tools

        return self._client.chat.completions.create(**params)

    def create_completion_with_retry(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        max_retries: int = 2,
        **kwargs: Any,
    ) -> Any:
        """
        Create a chat completion with automatic retry on transient failures.

        Args:
            messages: List of message dictionaries
            temperature: Sampling temperature (0.0 = deterministic)
            max_tokens: Maximum tokens to generate
            tools: Optional tool definitions for function calling
            max_retries: Maximum number of retry attempts
            **kwargs: Additional OpenAI API parameters

        Returns:
            OpenAI ChatCompletion response

        Raises:
            Exception: If all retries fail
        """
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                return self.create_completion(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools,
                    **kwargs,
                )
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    # Simple backoff: wait 1s, then 2s
                    import time

                    time.sleep(2**attempt)
                    continue
                # Out of retries
                break

        raise Exception(f"Failed after {max_retries + 1} attempts: {last_error}") from last_error


# Singleton instance - should be initialized once at application startup
_model_wrapper: ModelWrapper | None = None


def initialize_model() -> ModelWrapper:
    """
    Initialize the global model wrapper from environment variables.

    Reads configuration from:
    - MODEL_PROVIDER: Provider name (gemini, meta, openai, etc.)
    - MODEL_NAME: Model identifier
    - MODEL_BASE_URL: API base URL (optional, has defaults)
    - <PROVIDER>_API_KEY: API key for the provider

    Returns:
        Initialized ModelWrapper instance

    Raises:
        ValueError: If already initialized or configuration is missing
        ConnectionError: If model is unavailable
    """
    global _model_wrapper

    if _model_wrapper is not None:
        raise ValueError("Model wrapper already initialized")

    # Read provider configuration
    provider = os.getenv("MODEL_PROVIDER", "gemini").lower()

    # Provider-specific configuration
    if provider == "meta":
        api_key = os.getenv("META_API_KEY", "")
        model_id = os.getenv("MODEL_NAME", "muse-spark-1.1")
        base_url = os.getenv("MODEL_BASE_URL", "https://api.meta.ai/v1/")
    elif provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY", "")
        model_id = os.getenv("MODEL_NAME", "gemini-2.5-pro")
        base_url = os.getenv(
            "MODEL_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"
        )
    elif provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "")
        model_id = os.getenv("MODEL_NAME", "gpt-4")
        base_url = os.getenv("MODEL_BASE_URL", "https://api.openai.com/v1/")
    else:
        # Generic provider - requires all env vars
        api_key = os.getenv(f"{provider.upper()}_API_KEY", "")
        model_id = os.getenv("MODEL_NAME", "")
        base_url = os.getenv("MODEL_BASE_URL", "")

        if not model_id or not base_url:
            raise ValueError(
                f"For provider '{provider}', MODEL_NAME and MODEL_BASE_URL are required"
            )

    if not api_key:
        raise ValueError(
            f"API key not found for provider '{provider}'. "
            f"Set {provider.upper()}_API_KEY in environment."
        )

    _model_wrapper = ModelWrapper(
        api_key=api_key, model_id=model_id, base_url=base_url, provider=provider
    )

    return _model_wrapper


def get_model() -> ModelWrapper:
    """
    Get the global model wrapper.

    Returns:
        Initialized ModelWrapper instance

    Raises:
        ValueError: If not yet initialized
    """
    if _model_wrapper is None:
        raise ValueError("Model wrapper not initialized. Call initialize_model() first.")

    return _model_wrapper


def reset_model() -> None:
    """
    Reset the global model wrapper.

    Used primarily for testing.
    """
    global _model_wrapper
    _model_wrapper = None
