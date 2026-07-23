from typing import Any

from orchestrator.conversation_state import PartialIntakeData


EXTRACT_FUNCTION = {
    "type": "function",
    "function": {
        "name": "update_intake",
        "description": (
            "Extract structured intake fields from the conversation so far. "
            "Only populate fields you are confident about from what the user said. "
            "Leave all other fields absent — do not guess."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "org_id": {
                    "type": "string",
                    "description": (
                        "A unique slug for this client. If the user gave a business name "
                        "but no explicit org_id, derive it: lowercase, underscores, no spaces. "
                        "e.g. miami_glow_salon"
                    ),
                },
                "business_name": {
                    "type": "string",
                    "description": "The display name of the business exactly as the user stated it.",
                },
                "phone_number": {
                    "type": "string",
                    "description": "Vapi phone number in E.164 format e.g. +13055551234",
                },
                "voice_id": {
                    "type": "string",
                    "description": (
                        "Vapi voice ID. If the user described a voice style but did not "
                        "name a specific voice ID, leave this absent."
                    ),
                },
                "capabilities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "List of capabilities from: booking, cancellation, rescheduling, "
                        "availability, human_transfer. Map natural language to these "
                        "exact strings. e.g. 'add/check/cancel bookings' → "
                        "['booking', 'availability', 'cancellation']"
                    ),
                },
                "industry": {
                    "type": "string",
                    "description": "The business vertical e.g. salon, dental, fitness, restaurant",
                },
                "timezone": {
                    "type": "string",
                    "description": "IANA timezone string e.g. America/New_York",
                },
            },
            "required": [],
        },
    },
}


def extract_from_conversation(
    messages: list[dict[str, Any]],
    model: Any,
) -> dict[str, Any]:
    """
    Sends conversation history to the model with the extraction function schema.
    Returns a dict of confidently extracted fields (may be empty).
    Never raises — returns {} on any failure so conversation continues.

    Supports both ModelWrapper (OpenAI-compatible) and BedrockModelWrapper.
    For providers that support forced tool calling (bedrock, openai), tool_choice
    is set to force the function call. For others (meta), it is omitted.
    """
    try:
        extraction_messages = [
            {
                "role": "system",
                "content": (
                    "You are a structured data extraction tool. Your ONLY job is to call "
                    "the update_intake function with fields extracted from the conversation. "
                    "You MUST call update_intake — never respond with text. "
                    "Extract ALL fields you can identify from the ENTIRE conversation history. "
                    "Include fields mentioned in ANY message, not just the latest one. "
                    "Only populate fields you are confident about. Do not guess."
                ),
            },
            *_convert_messages(messages),
        ]

        provider = getattr(model, "provider", "generic")

        call_kwargs: dict[str, Any] = {
            "messages": extraction_messages,
            "tools": [EXTRACT_FUNCTION],
            "temperature": 0.0,
            "max_tokens": 512,
        }

        if provider in ("bedrock", "openai", "gemini"):
            call_kwargs["tool_choice"] = {
                "type": "function",
                "function": {"name": "update_intake"},
            }

        response = model.create_completion(**call_kwargs)

        if not response or not response.choices:
            return {}

        message = response.choices[0].message
        if message.tool_calls:
            for tool_call in message.tool_calls:
                if tool_call.function.name == "update_intake":
                    import json

                    args = json.loads(tool_call.function.arguments)
                    return {k: v for k, v in args.items() if v is not None and v != ""}

        return {}
    except Exception:
        return {}


def apply_extraction(
    state_partial: PartialIntakeData,
    extracted: dict[str, Any],
) -> PartialIntakeData:
    """
    Merges newly extracted fields into the partial intake.
    Only updates fields that were absent (None) — never overwrites confirmed values.
    """
    for field_name, value in extracted.items():
        if not value:
            continue
        if hasattr(state_partial, field_name) and getattr(state_partial, field_name) is None:
            setattr(state_partial, field_name, value)
    return state_partial


def apply_correction(
    state_partial: PartialIntakeData,
    field_name: str,
    new_value: Any,
) -> PartialIntakeData:
    """
    Applies an explicit user correction — overwrites even existing values.
    """
    if hasattr(state_partial, field_name):
        setattr(state_partial, field_name, new_value)
    return state_partial


def _convert_messages(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Convert internal message format to OpenAI message format."""
    converted: list[dict[str, str]] = []
    for msg in messages:
        role = msg.get("role", "user")
        if role == "model":
            role = "assistant"
        parts = msg.get("parts", [])
        content = parts[0] if parts else ""
        if isinstance(content, str):
            converted.append({"role": role, "content": content})
    return converted
