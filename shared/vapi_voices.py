"""
Canonical Vapi voice catalog.

Source of truth for valid Vapi built-in voice IDs (provider: "vapi").
Vapi's built-in voices require `provider: "vapi"` and must NOT be
configured with a third-party provider like 11labs, otherwise Vapi
returns "Couldn't Find <provider> Voice" at call time.

Verified against the Vapi documentation (Vapi Voices / Vapi Voices V2)
and the Vapi API OpenAPI schema (VapiVoice.voiceId enum).
"""

# Voice IDs are case-sensitive and must match Vapi's API exactly.
DEFAULT_VOICE_ID = "Elliot"

# voiceId -> short description shown to users during intake.
VAPI_VOICES: dict[str, str] = {
    "Elliot": "Friendly, professional male voice (recommended)",
    "Savannah": "Warm, straightforward female voice",
    "Rohan": "Bright, energetic male voice",
    "Emma": "Warm, conversational female voice",
    "Clara": "Warm, professional female voice",
    "Nico": "Casual, natural male voice",
    "Kai": "Friendly, relaxed male voice",
    "Sagar": "Steady, professional male voice",
    "Godfrey": "Energetic, young male voice",
    "Neil": "Clear, professional male voice",
    "Layla": "Warm, cheerful female voice",
    "Sid": "Smooth, deep-toned male voice",
    "Naina": "Calm, professional female voice",
}


def is_valid_vapi_voice(voice_id: str | None) -> bool:
    """Return True if voice_id is a known Vapi built-in voice ID."""
    return voice_id in VAPI_VOICES
