"""
Gemini OpenAI-compatible model wrapper for Agent Forge.

Provides a single, explicit construction point for the Gemini model
through Google's OpenAI-compatible endpoint.
"""

from typing import Any, Optional

from openai import OpenAI


class GeminiModelWrapper:
    """
    Wrapper for Gemini 2.5 Pro through OpenAI-compatible endpoint.

    Constructs once at startup and provides model access to agents.
    Validates model availability and fails fast if misconfigured.
    """

    def __init__(self, api_key: str, model_id: str = "gemini-2.5-pro"):
        """
        Initialize Gemini model wrapper.

        Args:
            api_key: Google Gemini API key
            model_id: Model identifier (default: gemini-2.5-pro)

        Raises:
            ValueError: If API key is missing
            ConnectionError: If model is unavailable
        """
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required")

        self.api_key = api_key
        self.model_id = model_id
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"

        # Create OpenAI client configured for Gemini
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
                    f"Model {self.model_id} returned empty response"
                )

        except Exception as e:
            raise ConnectionError(
                f"Failed to verify model {self.model_id} availability: {e}"
            ) from e

    @property
    def client(self) -> OpenAI:
        """
        Get the configured OpenAI client.

        Returns:
            OpenAI client configured for Gemini endpoint
        """
        return self._client

    def get_model_id(self) -> str:
        """
        Get the model identifier.

        Returns:
            Model ID string (e.g., "gemini-2.5-pro")
        """
        return self.model_id

    def create_completion(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        tools: Optional[list[dict[str, Any]]] = None,
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
        tools: Optional[list[dict[str, Any]]] = None,
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
                    time.sleep(2 ** attempt)
                    continue
                # Out of retries
                break

        raise Exception(
            f"Failed after {max_retries + 1} attempts: {last_error}"
        ) from last_error


# Singleton instance - should be initialized once at application startup
_gemini_wrapper: Optional[GeminiModelWrapper] = None


def initialize_gemini(api_key: str, model_id: str = "gemini-2.5-pro") -> GeminiModelWrapper:
    """
    Initialize the global Gemini model wrapper.

    Should be called once at application startup.

    Args:
        api_key: Google Gemini API key
        model_id: Model identifier (default: gemini-2.5-pro)

    Returns:
        Initialized GeminiModelWrapper instance

    Raises:
        ValueError: If already initialized
        ConnectionError: If model is unavailable
    """
    global _gemini_wrapper

    if _gemini_wrapper is not None:
        raise ValueError("Gemini wrapper already initialized")

    _gemini_wrapper = GeminiModelWrapper(api_key=api_key, model_id=model_id)
    return _gemini_wrapper


def get_gemini() -> GeminiModelWrapper:
    """
    Get the global Gemini model wrapper.

    Returns:
        Initialized GeminiModelWrapper instance

    Raises:
        ValueError: If not yet initialized
    """
    if _gemini_wrapper is None:
        raise ValueError(
            "Gemini wrapper not initialized. Call initialize_gemini() first."
        )

    return _gemini_wrapper


def reset_gemini() -> None:
    """
    Reset the global Gemini wrapper.

    Used primarily for testing.
    """
    global _gemini_wrapper
    _gemini_wrapper = None
