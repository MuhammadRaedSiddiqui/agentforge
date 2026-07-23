from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SessionPhase(Enum):
    GATHERING = "gathering"
    CONFIRMING = "confirming"
    EXECUTING = "executing"
    COMPLETE = "complete"
    ABORTED = "aborted"


@dataclass
class PartialIntakeData:
    org_id: Optional[str] = None
    business_name: Optional[str] = None
    phone_number: Optional[str] = None
    voice_id: Optional[str] = None
    capabilities: Optional[list[str]] = None
    industry: Optional[str] = None
    timezone: Optional[str] = None
    business_hours: Optional[dict[str, str]] = None

    def required_fields_present(self) -> bool:
        return all([
            self.org_id,
            self.business_name,
            self.phone_number,
            self.voice_id,
            self.capabilities,
        ])

    def missing_required_fields(self) -> list[str]:
        missing: list[str] = []
        if not self.org_id:
            missing.append("org_id")
        if not self.business_name:
            missing.append("business_name")
        if not self.phone_number:
            missing.append("phone_number")
        if not self.voice_id:
            missing.append("voice_id")
        if not self.capabilities:
            missing.append("capabilities")
        return missing

    def to_dict(self) -> dict[str, object]:
        return {
            "org_id": self.org_id,
            "business_name": self.business_name,
            "phone_number": self.phone_number,
            "voice_id": self.voice_id,
            "capabilities": self.capabilities,
            "industry": self.industry,
            "timezone": self.timezone,
            "business_hours": self.business_hours,
        }


@dataclass
class ConversationState:
    phase: SessionPhase = SessionPhase.GATHERING
    partial_intake: PartialIntakeData = field(default_factory=PartialIntakeData)
    messages: list[dict[str, object]] = field(default_factory=list)
    confirmed_plan: Optional[dict[str, object]] = None
    session_id: Optional[str] = None
