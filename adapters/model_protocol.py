"""
Structural interface shared by the model wrappers.

`ModelWrapper` (OpenAI-compatible) and `BedrockModelWrapper` are deliberately
interchangeable — the Bedrock wrapper's docstring says it "provides the same
interface as ModelWrapper" — but nothing expressed that, so call sites that
select a provider at runtime could not be typed and mypy flagged every
assignment as incompatible.

This is a Protocol rather than a base class on purpose: neither wrapper should
have to import the other or a shared parent, and the compatibility is
structural, not an inheritance relationship.
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ModelProvider(Protocol):
    """A chat-completion provider usable by the intake extractor and CLI."""

    def get_model_id(self) -> str:
        """Return the concrete model identifier in use."""
        ...

    def get_provider(self) -> str:
        """Return the provider name (e.g. gemini, openai, bedrock)."""
        ...

    def create_completion(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Create a chat completion."""
        ...

    def create_completion_with_retry(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        max_retries: int = 2,
        **kwargs: Any,
    ) -> Any:
        """Create a chat completion, retrying transient failures."""
        ...
