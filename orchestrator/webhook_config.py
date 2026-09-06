"""
Wire a deployed client's Make scenarios to the shared backend.

The backend serves one generic route, `/webhook/:org/:capability`, and resolves
where to forward from two environment variables per client:

    CLIENT_<ORG>_ENABLED            admits the client
    MAKE_<ORG>_<CAPABILITY>_URL     where that capability forwards

The first is set as an ordinary action. The second cannot be: the Make hook URL
does not exist until the scenario is deployed, so there is nothing to put in a
payload at plan time. This runs after the action loop, once every scenario has
produced its hook.

Without it a client is admitted and unwired, and every tool call returns 503 —
which is the honest answer, but not a working client.
"""

import os
import re
from dataclasses import dataclass
from typing import Any

from shared.errors import ValidationError

# Mirrors envSlug() in server.js. Both must agree or the backend looks up a
# variable the orchestrator never set.
_NON_ALPHANUMERIC = re.compile(r"[^A-Z0-9]")


def env_slug(organization_id: str) -> str:
    """Normalize an organization id for use in an environment variable name."""
    return _NON_ALPHANUMERIC.sub("_", str(organization_id).upper())


def client_enabled_key(organization_id: str) -> str:
    return f"CLIENT_{env_slug(organization_id)}_ENABLED"


def make_url_key(organization_id: str, capability: str) -> str:
    return f"MAKE_{env_slug(organization_id)}_{capability.upper()}_URL"


@dataclass(frozen=True)
class WebhookBinding:
    """One capability's forwarding target."""

    capability: str
    hook_url: str
    env_key: str


def collect_bindings(
    organization_id: str,
    results: list[dict[str, Any]],
) -> tuple[list[WebhookBinding], list[str]]:
    """Read the scenario results and work out what the backend needs.

    Returns the bindings to apply, and the capabilities that produced a scenario
    but no usable hook URL. Those are reported rather than skipped: a scenario
    the backend cannot reach is a capability the assistant cannot use, and it
    would otherwise look identical to a healthy deployment.
    """
    bindings: list[WebhookBinding] = []
    unresolved: list[str] = []

    for result in results:
        if result.get("platform") != "make" or result.get("operation") != "create_scenario":
            continue
        receipt = result.get("receipt") or {}
        capability = receipt.get("capability")
        if not capability:
            unresolved.append(str(result.get("remote_id") or "unknown scenario"))
            continue
        hook_url = receipt.get("hook_url")
        if not hook_url or not str(hook_url).startswith("https://"):
            unresolved.append(capability)
            continue
        bindings.append(
            WebhookBinding(
                capability=capability,
                hook_url=str(hook_url),
                env_key=make_url_key(organization_id, capability),
            )
        )

    return bindings, unresolved


WEBHOOK_SECRET_PLACEHOLDER = "{{WEBHOOK_SECRET}}"


def resolve_webhook_secret(config: Any) -> Any:
    """Replace the webhook-secret placeholder with the configured value.

    Generated Vapi artifacts carry `{{WEBHOOK_SECRET}}` rather than the secret
    itself: they are written to outputs/ in plaintext and content-hashed, so
    embedding the real value would put it on disk and change the hash whenever
    it rotates. Substitution happens on the way to Vapi instead.

    Raises when the placeholder is present and WEBHOOK_SECRET is not set —
    sending the literal placeholder would configure an assistant whose calls
    the backend rejects, which is the silent kind of broken.
    """

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            return {key: walk(value) for key, value in node.items()}
        if isinstance(node, list):
            return [walk(item) for item in node]
        if node == WEBHOOK_SECRET_PLACEHOLDER:
            secret = os.getenv("WEBHOOK_SECRET")
            if not secret:
                raise ValidationError(
                    "WEBHOOK_SECRET is not set, so the assistant would be created "
                    "with a placeholder secret and every tool call would be "
                    "rejected by the backend.",
                    field="WEBHOOK_SECRET",
                )
            return secret
        return node

    return walk(config)


def apply_bindings(hosting_adapter: Any, bindings: list[WebhookBinding]) -> None:
    """Set each forwarding variable on the backend service.

    Failures propagate. A half-wired client answers some capabilities and 503s
    the rest, which is worse than a deployment that stops and says so.
    """
    for binding in bindings:
        hosting_adapter.set_env_variable(binding.env_key, binding.hook_url)
