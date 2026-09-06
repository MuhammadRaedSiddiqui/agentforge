"""
The Vapi assistant and the backend must agree on one URL.

They did not. Vapi tools called `/tools/<capability>`; the Node generator, its
route extractor and its validator all used `/webhook/<org>/<capability>`. Every
tool call on every deployed assistant 404'd, and nothing detected it because
each side was internally consistent.

`/webhook/<org>/<capability>` is canonical: one Render service hosts every
client, so a path without the organization cannot be multi-tenant — two clients
would collide on `/tools/booking`.

These tests hold the two sides together at the contract, not at one end of it.
"""

import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
VAPI_TEMPLATE = ROOT / "ground-truth" / "configs" / "vapi_assistant_template.json"
SERVER_JS = ROOT / "server.js"
BACKEND_PACKAGE = ROOT / "templates" / "backend" / "package.json"

# The capability each template tool maps to, keyed by function name.
TOOL_CAPABILITIES = {
    "check_availability": "availability",
    "book_appointment": "booking",
    "cancel_appointment": "cancellation",
    "reschedule_appointment": "rescheduling",
}


def _template() -> dict:
    return json.loads(VAPI_TEMPLATE.read_text(encoding="utf-8"))


class TestVapiToolUrlsAreOrgScoped:
    def test_every_tool_url_carries_the_organization(self) -> None:
        for tool in _template()["tools"]:
            url = tool["server"]["url"]
            assert "{{organization_id}}" in url, (
                f"{tool['function']['name']} has no organization in its path; "
                f"a shared service cannot route it: {url}"
            )

    def test_no_tool_uses_the_old_unscoped_prefix(self) -> None:
        raw = VAPI_TEMPLATE.read_text(encoding="utf-8")
        assert "{{server_url}}/tools/" not in raw

    def test_tool_paths_match_the_capability_they_serve(self) -> None:
        for tool in _template()["tools"]:
            name = tool["function"]["name"]
            capability = TOOL_CAPABILITIES.get(name)
            if capability is None:
                continue
            expected = f"{{{{server_url}}}}/webhook/{{{{organization_id}}}}/{capability}"
            assert tool["server"]["url"] == expected

    def test_template_and_node_generator_agree(self) -> None:
        """The contract itself: both sides build the same path shape."""
        from agents.nodejs_agent.agent import NodeJsAgent  # noqa: F401

        generator = (ROOT / "agents" / "nodejs_agent" / "agent.py").read_text(encoding="utf-8")
        assert "/webhook/{organization_id}/{endpoint}" in generator

        for tool in _template()["tools"]:
            assert tool["server"]["url"].startswith("{{server_url}}/webhook/{{organization_id}}/")


class TestSharedBackendHandlesEveryCapability:
    """The service is generic, so onboarding is configuration rather than code."""

    def test_generic_route_exists(self) -> None:
        source = SERVER_JS.read_text(encoding="utf-8")
        assert '"/webhook/:org/:capability"' in source

    def test_every_scenario_capability_is_accepted(self) -> None:
        from orchestrator.intake_schema import DATABASE_BACKED_CAPABILITIES

        source = SERVER_JS.read_text(encoding="utf-8")
        block = re.search(r"const CAPABILITIES = new Set\(\[(.*?)\]\)", source, re.DOTALL)
        assert block is not None
        declared = set(re.findall(r'"([a-z_]+)"', block.group(1)))

        assert declared == set(DATABASE_BACKED_CAPABILITIES), (
            "the backend accepts a different capability set than the planner deploys"
        )

    def test_human_transfer_is_not_routed_through_the_backend(self) -> None:
        """It is handled inside Vapi and generates no scenario."""
        source = SERVER_JS.read_text(encoding="utf-8")
        block = re.search(r"const CAPABILITIES = new Set\(\[(.*?)\]\)", source, re.DOTALL)
        assert block is not None
        assert "human_transfer" not in block.group(1)

    def test_env_var_names_match_what_onboarding_sets(self) -> None:
        """`CLIENT_<ORG>_ENABLED` is written by action_builder."""
        source = SERVER_JS.read_text(encoding="utf-8")
        assert "CLIENT_${envSlug(organizationId)}_ENABLED" in source
        assert "MAKE_${envSlug(organizationId)}_${capability.toUpperCase()}_URL" in source

    def test_hmac_uses_a_constant_time_comparison(self) -> None:
        source = SERVER_JS.read_text(encoding="utf-8")
        assert "timingSafeEqual" in source
        assert "signature === expectedSignature" not in source

    def test_length_mismatch_does_not_throw(self) -> None:
        """timingSafeEqual raises on differing lengths; a bad signature is a 401."""
        source = SERVER_JS.read_text(encoding="utf-8")
        assert "given.length !== want.length" in source


class TestBackendDependencies:
    def test_axios_is_declared(self) -> None:
        """Generated routes and the shared handler both forward with axios."""
        deps = json.loads(BACKEND_PACKAGE.read_text(encoding="utf-8"))["dependencies"]
        assert "axios" in deps

    def test_server_imports_everything_it_uses(self) -> None:
        source = SERVER_JS.read_text(encoding="utf-8")
        for module in ("crypto", "express", "axios"):
            assert f'require("{module}")' in source, f"{module} used but not imported"
