import os
import uuid
from pathlib import Path
from typing import Any

from orchestrator.conversation_state import ConversationState, SessionPhase
from orchestrator.dialogue_engine import (
    VOICE_SUGGESTIONS,
    handle_voice_suggestion_request,
    next_question,
)
from orchestrator.intake_extractor import apply_extraction, extract_from_conversation


SYSTEM_PROMPT_PATH = Path(__file__).parent.parent / "memory" / "orchestrator_system_prompt.md"


class ConversationAgent:
    """
    Conversational orchestrator supporting any model provider.
    Manages a multi-turn session, extracts structured IntakeData,
    and hands off to the execution pipeline when the user confirms.
    """

    def __init__(self, model: Any):
        self.model = model
        self.system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")

    def new_session(self) -> ConversationState:
        state = ConversationState()
        state.session_id = str(uuid.uuid4())
        return state

    def greet(self) -> str:
        return (
            "Agent Forge ready. Tell me about the client you want to set up — "
            "their business name, what the assistant should do, and any other "
            "details you have. I'll ask for anything missing."
        )

    def turn(
        self, user_message: str, state: ConversationState
    ) -> tuple[str, ConversationState]:
        """
        Process one user turn. Returns (response_text, updated_state).
        """
        state.messages.append({"role": "user", "parts": [user_message]})

        if state.phase == SessionPhase.GATHERING:
            if handle_voice_suggestion_request(user_message):
                response = VOICE_SUGGESTIONS
                state.messages.append({"role": "model", "parts": [response]})
                return response, state

            extracted = extract_from_conversation(state.messages, self.model)
            state.partial_intake = apply_extraction(state.partial_intake, extracted)

            if state.partial_intake.required_fields_present():
                state.phase = SessionPhase.CONFIRMING
                response = self._build_plan_summary(state)
            else:
                response = self._conversational_response(user_message, state)

        elif state.phase == SessionPhase.CONFIRMING:
            if self._is_confirmation(user_message):
                state.phase = SessionPhase.EXECUTING
                state.confirmed_plan = self._build_confirmed_intake(state)
                response = (
                    "Confirmed. Starting deployment — you'll see an approval "
                    "prompt for each action before anything is sent to the platforms."
                )
            elif self._is_cancellation(user_message):
                state.phase = SessionPhase.ABORTED
                response = "Deployment cancelled. Nothing was sent to any platform."
            else:
                state.phase = SessionPhase.GATHERING
                extracted = extract_from_conversation(state.messages, self.model)
                for field_name, value in extracted.items():
                    if value and hasattr(state.partial_intake, field_name):
                        setattr(state.partial_intake, field_name, value)
                if state.partial_intake.required_fields_present():
                    state.phase = SessionPhase.CONFIRMING
                    response = self._build_plan_summary(state)
                else:
                    response = self._conversational_response(user_message, state)

        else:
            response = ""

        if response:
            state.messages.append({"role": "model", "parts": [response]})

        return response, state

    def _conversational_response(self, user_message: str, state: ConversationState) -> str:
        """
        Generate a natural conversational response that acknowledges what
        was provided and asks the single next missing question.
        """
        next_q = next_question(state.partial_intake)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
        ]

        for msg in state.messages:
            role = msg.get("role", "user")
            if role == "model":
                role = "assistant"
            parts = msg.get("parts", [])
            content = parts[0] if parts else ""
            if isinstance(content, str):
                messages.append({"role": role, "content": content})

        if next_q:
            messages.append({
                "role": "system",
                "content": (
                    f"[Internal guidance] The next missing required field needs this question: "
                    f"{next_q}. Ask naturally — do not quote this guidance verbatim."
                ),
            })

        try:
            response = self.model.create_completion(
                messages=messages,
                temperature=0.4,
                max_tokens=1024,
            )
            if response and response.choices:
                return response.choices[0].message.content or next_q or ""
            return next_q or "Could you tell me more about what you need?"
        except Exception:
            return next_q or "Could you tell me more about what you need?"

    def _build_plan_summary(self, state: ConversationState) -> str:
        """
        Presents the deployment plan in plain language for user confirmation.
        """
        p = state.partial_intake
        caps_display: dict[str, str] = {
            "booking": "take bookings",
            "cancellation": "handle cancellations",
            "rescheduling": "reschedule appointments",
            "availability": "check availability",
            "human_transfer": "transfer to a human agent",
        }
        cap_lines = "\n".join(
            f"  - {caps_display.get(c, c)}" for c in (p.capabilities or [])
        )

        return (
            f"Here's what I'll build for {p.business_name}:\n\n"
            f"  - A Vapi voice assistant ({p.voice_id} voice) on {p.phone_number}\n"
            f"  - Automation scenarios:\n{cap_lines}\n"
            f"  - A Supabase tenant record for this client\n"
            f"  - Backend webhook routes for each capability\n\n"
            f"Type 'yes' to proceed, or tell me what to change."
        )

    def _build_confirmed_intake(self, state: ConversationState) -> dict[str, object]:
        """
        Converts the confirmed PartialIntakeData into a dict suitable for
        IntakeData validation and handoff to the planner.

        Maps conversational field names to the execution schema:
          org_id → organization_id
          capabilities → enabled_capabilities
        Provides sensible defaults for fields not gathered conversationally.
        """
        p = state.partial_intake
        capabilities = p.capabilities or []

        capability_defaults: dict[str, dict[str, object]] = {}
        if "booking" in capabilities:
            capability_defaults["booking_calendar_id"] = "pending-setup"
        if "cancellation" in capabilities:
            capability_defaults["cancellation_window_hours"] = 24
        if "rescheduling" in capabilities:
            capability_defaults["rescheduling_policy"] = {
                "minimum_notice_hours": 12,
                "maximum_reschedules": 2,
                "allowed": True,
            }
        if "human_transfer" in capabilities:
            capability_defaults["transfer_destination"] = p.phone_number or ""

        intake: dict[str, object] = {
            "organization_id": p.org_id,
            "business_name": p.business_name,
            "phone_number": p.phone_number,
            "voice_id": p.voice_id,
            "timezone": p.timezone or "America/New_York",
            "business_hours": p.business_hours or {
                "monday": [{"open": "09:00", "close": "17:00"}],
                "tuesday": [{"open": "09:00", "close": "17:00"}],
                "wednesday": [{"open": "09:00", "close": "17:00"}],
                "thursday": [{"open": "09:00", "close": "17:00"}],
                "friday": [{"open": "09:00", "close": "17:00"}],
                "saturday": [],
                "sunday": [],
            },
            "services_offered": [
                {
                    "name": "General Appointment",
                    "duration_minutes": 30,
                    "description": f"Standard appointment at {p.business_name}",
                }
            ],
            "enabled_capabilities": capabilities,
            "external_identifiers": {
                "vapi_phone_number_id": os.getenv("VAPI_PHONE_NUMBER_ID", "pending-setup"),
                "make_team_id": os.getenv("MAKE_TEAM_ID", "pending-setup"),
                "supabase_project_ref": os.getenv("SUPABASE_PROJECT_REF_STAGING", "pending-setup"),
            },
            **capability_defaults,
        }

        if p.industry:
            intake["industry"] = p.industry

        return intake

    @staticmethod
    def _is_confirmation(text: str) -> bool:
        affirmatives = {
            "yes", "y", "yep", "yeah", "correct", "proceed",
            "go ahead", "looks good", "confirmed", "ok", "okay",
        }
        return text.strip().lower() in affirmatives

    @staticmethod
    def _is_cancellation(text: str) -> bool:
        negatives = {"no", "n", "cancel", "stop", "abort", "quit", "exit"}
        return text.strip().lower() in negatives
