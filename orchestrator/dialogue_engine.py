from orchestrator.conversation_state import PartialIntakeData
from shared.vapi_voices import DEFAULT_VOICE_ID, VAPI_VOICES

FIELD_PRIORITY = [
    "capabilities",
    "phone_number",
    "voice_id",
    "timezone",
    "business_hours",
]

FIELD_QUESTIONS: dict[str, str] = {
    "capabilities": (
        "What should the assistant be able to do? For example: take bookings, "
        "check availability, handle cancellations or rescheduling?"
    ),
    "phone_number": (
        "Do you have a Vapi phone number set up for this client? "
        "If yes, share it in +1XXXXXXXXXX format."
    ),
    "voice_id": (
        "What voice should the assistant use? If you have a specific Vapi voice "
        "ID, share it now. Otherwise just say 'suggest' and I'll list a few options."
    ),
    "timezone": (
        "What timezone is the business in? For example: Eastern, Pacific, "
        "Central, or a city name works too."
    ),
    "business_hours": (
        "What are their business hours? A rough answer like "
        "'Mon-Sat 9am to 6pm' is fine."
    ),
}

VOICE_SUGGESTIONS = "Common Vapi voice options (pick one of these IDs):\n" + "\n".join(
    f"  {voice_id}     — {description}" for voice_id, description in VAPI_VOICES.items()
) + "\n\nShare the voice ID directly once you've decided."


def default_voice_id() -> str:
    """Return the default voice used when the user does not pick one."""
    return DEFAULT_VOICE_ID


def next_question(partial: PartialIntakeData) -> str | None:
    """
    Returns the next question to ask, or None if all required fields
    are present and the conversation can move to plan presentation.
    """
    missing = partial.missing_required_fields()
    if not missing:
        return None

    for field_name in FIELD_PRIORITY:
        if field_name in missing:
            return FIELD_QUESTIONS[field_name]

    return f"Could you tell me your {missing[0].replace('_', ' ')}?"


def handle_voice_suggestion_request(text: str) -> bool:
    """Returns True if the user's message is asking for voice suggestions."""
    text_lower = text.lower()
    return any(
        word in text_lower
        for word in ["suggest", "options", "which voice", "recommend", "voice options"]
    )
