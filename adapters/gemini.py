"""
Backward-compatible Gemini wrapper.

This module now delegates to the flexible model_wrapper for actual functionality.
Maintained for backward compatibility with existing code.
"""

from adapters.model_wrapper import ModelWrapper, get_model, initialize_model
from adapters.model_wrapper import reset_model as reset_model_wrapper

# Backward compatibility aliases
GeminiModelWrapper = ModelWrapper


def initialize_gemini(api_key: str, model_id: str = "gemini-2.5-pro") -> ModelWrapper:
    """
    Initialize the global Gemini model wrapper.

    Backward compatibility: now uses the flexible model_wrapper.

    Args:
        api_key: Google Gemini API key (ignored if MODEL_PROVIDER is set)
        model_id: Model identifier (ignored if MODEL_NAME is set)

    Returns:
        Initialized ModelWrapper instance

    Raises:
        ValueError: If already initialized
        ConnectionError: If model is unavailable
    """
    # Use the new flexible initialization
    return initialize_model()


def get_gemini() -> ModelWrapper:
    """
    Get the global model wrapper.

    Returns:
        Initialized ModelWrapper instance

    Raises:
        ValueError: If not yet initialized
    """
    return get_model()


def reset_gemini() -> None:
    """
    Reset the global model wrapper.

    Used primarily for testing.
    """
    reset_model_wrapper()
