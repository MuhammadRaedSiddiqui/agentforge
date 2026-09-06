"""
Conversational intake session for Agent Forge.

Provides a natural language interface for client onboarding.
"""

from typing import Any

from orchestrator.conversation_agent import ConversationAgent
from orchestrator.conversation_state import SessionPhase


def run_chat_session(model: Any, **platform_keys: Any) -> dict[str, Any] | None:
    """
    Main conversational session loop.
    Handles: greeting -> intake conversation -> plan confirmation -> return confirmed intake.

    Returns the confirmed intake dict when the user confirms, or None if aborted.
    """
    agent = ConversationAgent(model)
    state = agent.new_session()

    print()
    print("=" * 60)
    print("  Agent Forge — Conversational Deployment")
    print("=" * 60)
    print()

    greeting = agent.greet()
    print(f"Agent Forge: {greeting}\n")

    while state.phase not in (
        SessionPhase.EXECUTING,
        SessionPhase.ABORTED,
        SessionPhase.COMPLETE,
    ):
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nSession interrupted. Nothing was deployed.")
            return None

        if not user_input:
            continue

        if user_input.lower() in {"exit", "quit", "q"}:
            print("\nSession ended. Nothing was deployed.")
            return None

        response, state = agent.turn(user_input, state)

        if response:
            print(f"\nAgent Forge: {response}\n")

    if state.phase == SessionPhase.ABORTED:
        return None

    if state.phase == SessionPhase.EXECUTING:
        return state.confirmed_plan

    return None
