import re
from typing import Any

from orchestrator.conversation_state import PartialIntakeData
from shared.vapi_voices import VAPI_VOICES

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


def _extract_tool_call(response: Any) -> dict[str, Any]:
    """Parse an update_intake tool call out of a completion response. Returns {} if none."""
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


# Deterministic fallback extraction for providers whose tool calling is
# unreliable (e.g. meta/muse-spark-1.1 only supports tool_choice="auto").
# These patterns are intentionally conservative: they only pick up fields
# that appear explicitly in the user's messages, so the conversation always
# makes progress even if the model never emits a tool call.
_CAPABILITY_PATTERNS: list[tuple[str, list[str]]] = [
    ("availability", ["availability", "check open appointment slots", "open slots", "availability check"]),
    ("booking", ["booking", "book appointments", "book new appointments", "take bookings", "appointment booking"]),
    ("cancellation", ["cancellation", "cancel appointments", "appointment cancellation"]),
    ("rescheduling", ["reschedul"]),
    ("human_transfer", ["human transfer", "transfer to a human", "transfer calls", "speak to a person", "human agent", "front desk"]),
]

_ORG_ID_PATTERNS = [
    re.compile(r"(?:organization\s*id|org\s*id|org_id|organization_id)\s*(?:is|:|=)?\s*['\"]?([a-zA-Z0-9_]+)", re.IGNORECASE),
]

_BUSINESS_NAME_PATTERNS = [
    re.compile(r"(?:client|business|company)\s+(?:named|called)\s+(.+)", re.IGNORECASE),
    re.compile(r"(?:business|company)\s+name\s+(?:is|:|=)?\s+(.+)", re.IGNORECASE),
]

_PHONE_PATTERN = re.compile(r"\+[1-9]\d{1,14}")

_TIMEZONE_PATTERNS = [
    re.compile(r"\b(America/(?:New_York|Los_Angeles|Chicago|Denver|Phoenix|Toronto|Vancouver|Anchorage|Honolulu))\b"),
    re.compile(r"\b(Europe/(?:London|Paris|Berlin))\b"),
    re.compile(r"\b(Asia/(?:Tokyo|Shanghai|Dubai))\b"),
    re.compile(r"\b(Australia/Sydney)\b"),
]

_KNOWN_VOICES = sorted(VAPI_VOICES.keys(), key=len, reverse=True)


def _clean_candidate(value: str) -> str:
    """Trim a regex-captured name down to a single logical phrase."""
    return re.split(r"[,;.\n]| and ", value, maxsplit=1)[0].strip()


def fallback_extract(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Deterministic regex-based extraction over the user's messages.

    Used when the model fails to produce an update_intake tool call, so the
    conversation never gets stuck re-asking for the same fields.
    """
    user_text = "\n".join(
        str(msg.get("parts", [""])[0])
        for msg in messages
        if msg.get("role") == "user"
    )
    if not user_text:
        return {}

    extracted: dict[str, Any] = {}

    for pattern in _ORG_ID_PATTERNS:
        match = pattern.search(user_text)
        if match:
            org_id = match.group(1).strip().lower()
            if org_id:
                extracted["org_id"] = org_id
                break

    for pattern in _BUSINESS_NAME_PATTERNS:
        match = pattern.search(user_text)
        if match:
            name = _clean_candidate(match.group(1))
            if len(name) >= 2:
                extracted["business_name"] = name
                break

    phone = _PHONE_PATTERN.search(user_text)
    if phone:
        extracted["phone_number"] = phone.group(0)

    capabilities: list[str] = []
    text_lower = user_text.lower()
    for capability, keywords in _CAPABILITY_PATTERNS:
        if any(keyword in text_lower for keyword in keywords):
            capabilities.append(capability)
    if capabilities:
        extracted["capabilities"] = capabilities

    for pattern in _TIMEZONE_PATTERNS:
        match = pattern.search(user_text)
        if match:
            extracted["timezone"] = match.group(1)
            break

    for voice in _KNOWN_VOICES:
        if re.search(rf"\b{voice}\b", user_text, re.IGNORECASE):
            extracted["voice_id"] = voice
            break

    return extracted


def extract_from_conversation(
    messages: list[dict[str, Any]],
    model: Any,
) -> dict[str, Any]:
    """
    Sends conversation history to the model with the extraction function schema.
    Returns a dict of confidently extracted fields (may be empty).
    Never raises — returns {} on any failure so conversation continues.

    Supports both ModelWrapper (OpenAI-compatible) and BedrockModelWrapper.
    For providers that support forced tool calling (bedrock, openai, gemini), tool_choice
    is set to force the function call. For others (e.g. meta), it is omitted because the
    API rejects named tool_choice. On a text (non-tool-call) response from such providers,
    the extraction is retried once with an explicit instruction to call the function.
    As a last resort for ANY provider, a deterministic regex fallback extracts explicit
    fields from the user's messages — without this, a model that never emits a tool call
    leaves the state empty and the conversation loops asking for the same fields.
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
        extracted = _extract_tool_call(response)
        if extracted:
            return extracted

        # Providers without forced tool_choice may reply with text. Retry once,
        # explicitly instructing the model to call the function.
        if provider not in ("bedrock", "openai", "gemini"):
            retry_messages = extraction_messages + [
                {
                    "role": "system",
                    "content": (
                        "Your previous reply did not call the update_intake function. "
                        "You MUST now call update_intake with all fields you can identify "
                        "from the conversation. Return no text — only the function call."
                    ),
                }
            ]
            response = model.create_completion(
                messages=retry_messages,
                tools=[EXTRACT_FUNCTION],
                temperature=0.0,
                max_tokens=512,
            )
            retried = _extract_tool_call(response)
            if retried:
                return retried

        # Last resort: deterministic regex extraction so the conversation always
        # progresses even when the model refuses to emit a tool call.
        return fallback_extract(messages)
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
