"""
Post-deployment verification.

Every action in an onboarding can succeed while the client remains unusable.
That is not hypothetical: a deployment reported "8 of 8 actions" and produced
an assistant with no tools attached, endpoints pointed at a health check, and a
phone number still bound to somebody else's assistant. Eight receipts, a green
audit trail and exit 0 all described a client that could not take a call.

The gap is that an action's success criterion is "the API accepted the write",
which says nothing about the resulting resource. These checks re-read what was
created and compare it against what was generated, so the difference between
"performed" and "usable" becomes a deployment failure rather than something
found by hand afterwards.

Failures are collected rather than raised on the first one: an operator fixing
a broken deployment wants the whole list, not the earliest item in it. A check
that cannot read the resource counts as a failure — unknown state is not
evidence of success.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orchestrator.approval import ProposedAction


@dataclass(frozen=True)
class VerificationFailure:
    """One thing that is wrong with a deployment that otherwise reported success."""

    check: str
    detail: str

    def __str__(self) -> str:
        return f"{self.check}: {self.detail}"


def expected_tool_count(config_path: str | None) -> int:
    """How many tools the generated assistant config declared.

    Returns 0 when the config is missing or unreadable rather than raising:
    the caller turns a mismatch into a failure, and a config that cannot be
    read produces no expectation to compare against.
    """
    if not config_path:
        return 0
    path = Path(config_path)
    if not path.exists():
        return 0
    try:
        with path.open(encoding="utf-8") as handle:
            config = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return 0
    tools = config.get("tools")
    return len(tools) if isinstance(tools, list) else 0


def _remote_id_for(results: list[dict[str, Any]], platform: str, operation: str) -> str | None:
    for result in results:
        if result.get("platform") == platform and result.get("operation") == operation:
            remote_id = result.get("remote_id")
            return str(remote_id) if remote_id else None
    return None


def _verify_assistant_tools(
    vapi_adapter: Any,
    assistant_id: str,
    expected: int,
) -> list[VerificationFailure]:
    if expected == 0:
        return []
    try:
        data = vapi_adapter.get_assistant(assistant_id).response_data
    except Exception as error:  # noqa: BLE001 - any read failure is a failed check
        return [
            VerificationFailure(
                "assistant_readable",
                f"could not re-read assistant {assistant_id}: {type(error).__name__}: {error}",
            )
        ]

    model = data.get("model") or {}
    attached = model.get("toolIds") or data.get("toolIds") or []
    if len(attached) < expected:
        return [
            VerificationFailure(
                "assistant_tools_attached",
                f"assistant {assistant_id} has {len(attached)} tool(s) attached but the "
                f"generated config declared {expected}; it cannot invoke the "
                f"capabilities it was deployed for",
            )
        ]
    return []


def _verify_phone_binding(
    vapi_adapter: Any,
    phone_number_id: str,
    assistant_id: str,
) -> list[VerificationFailure]:
    try:
        data = vapi_adapter.list_phone_numbers().response_data
    except Exception as error:  # noqa: BLE001 - any read failure is a failed check
        return [
            VerificationFailure(
                "phone_readable",
                f"could not list phone numbers: {type(error).__name__}: {error}",
            )
        ]

    numbers = data.get("phone_numbers") or data.get("phoneNumbers") or []
    for number in numbers:
        if str(number.get("id")) != str(phone_number_id):
            continue
        bound_to = number.get("assistantId")
        if str(bound_to) == str(assistant_id):
            return []
        return [
            VerificationFailure(
                "phone_bound_to_assistant",
                f"phone {number.get('number') or phone_number_id} is bound to "
                f"{bound_to!r}, not to the assistant just created ({assistant_id}); "
                f"nobody can reach this client",
            )
        ]

    return [
        VerificationFailure(
            "phone_bound_to_assistant",
            f"phone number {phone_number_id} was not found on the Vapi account, "
            f"so it cannot be confirmed bound to {assistant_id}",
        )
    ]


def verify_onboarding(
    actions: list[ProposedAction],
    results: list[dict[str, Any]],
    vapi_adapter: Any,
) -> list[VerificationFailure]:
    """Re-read what an onboarding created and report anything unusable.

    Args:
        actions: The proposed actions that were executed, for the generated
            config path and the phone number the deployment intended to bind.
        results: Execution results, for the remote ids actually created.
        vapi_adapter: Adapter used to re-read remote state.

    Returns:
        Every failure found, empty when the deployment is usable.
    """
    failures: list[VerificationFailure] = []

    create_assistant = next((a for a in actions if a.operation == "create_assistant"), None)
    if create_assistant is None:
        return failures

    assistant_id = _remote_id_for(results, "vapi", "create_assistant")
    if not assistant_id:
        # The action was planned but produced no id, and every later check
        # needs one. Reported rather than skipped.
        return [
            VerificationFailure(
                "assistant_created",
                "create_assistant produced no remote id, so the assistant cannot be verified",
            )
        ]

    failures.extend(
        _verify_assistant_tools(
            vapi_adapter,
            assistant_id,
            expected_tool_count(create_assistant.payload.get("config_path")),
        )
    )

    phone_number_id = create_assistant.payload.get("phone_number_id")
    if phone_number_id:
        failures.extend(_verify_phone_binding(vapi_adapter, str(phone_number_id), assistant_id))

    return failures
