"""
Unit tests for orchestrator/webhook_config.py.

The backend resolves where to forward from MAKE_<ORG>_<CAPABILITY>_URL. That
value is a Make hook URL, which does not exist until the scenario is deployed,
so it cannot be planned into an action payload — it has to be read out of the
results afterwards.

The failure this guards is quiet: a client admitted by CLIENT_<ORG>_ENABLED but
missing a forwarding variable answers 503 on that capability forever, while the
deployment looks complete.
"""

from typing import Any
from unittest.mock import MagicMock

import pytest

from orchestrator.webhook_config import (
    apply_bindings,
    client_enabled_key,
    collect_bindings,
    env_slug,
    make_url_key,
)

pytestmark = pytest.mark.unit


def _scenario(capability: str, hook_url: str | None, remote_id: str = "1") -> dict[str, Any]:
    return {
        "platform": "make",
        "operation": "create_scenario",
        "remote_id": remote_id,
        "receipt": {"capability": capability, "hook_url": hook_url},
    }


class TestEnvVarNaming:
    """These names are duplicated in server.js; both sides must agree."""

    @pytest.mark.parametrize(
        ("org", "expected"),
        [
            ("northgate_dental", "NORTHGATE_DENTAL"),
            ("clinic-2024", "CLINIC_2024"),
            ("Café_Solstice", "CAF__SOLSTICE"),
            ("a.b c", "A_B_C"),
        ],
    )
    def test_slug_matches_the_javascript_rule(self, org: str, expected: str) -> None:
        assert env_slug(org) == expected

    def test_keys_match_what_the_backend_reads(self) -> None:
        assert client_enabled_key("northgate_dental") == "CLIENT_NORTHGATE_DENTAL_ENABLED"
        assert make_url_key("northgate_dental", "booking") == "MAKE_NORTHGATE_DENTAL_BOOKING_URL"


class TestCollectBindings:
    def test_one_binding_per_deployed_scenario(self) -> None:
        results = [
            _scenario("availability", "https://hook.us2.make.com/aaa"),
            _scenario("booking", "https://hook.us2.make.com/bbb"),
        ]

        bindings, unresolved = collect_bindings("northgate_dental", results)

        assert unresolved == []
        assert [b.capability for b in bindings] == ["availability", "booking"]
        assert bindings[0].env_key == "MAKE_NORTHGATE_DENTAL_AVAILABILITY_URL"
        assert bindings[0].hook_url == "https://hook.us2.make.com/aaa"

    def test_non_make_results_are_ignored(self) -> None:
        results = [
            {"platform": "vapi", "operation": "create_assistant", "remote_id": "a"},
            {"platform": "render", "operation": "trigger_deploy", "remote_id": "d"},
            _scenario("booking", "https://hook.us2.make.com/bbb"),
        ]

        bindings, unresolved = collect_bindings("org", results)

        assert len(bindings) == 1
        assert unresolved == []

    def test_a_deployment_with_no_scenarios_binds_nothing(self) -> None:
        """human_transfer alone generates no scenario and needs no wiring."""
        results = [{"platform": "vapi", "operation": "create_assistant", "remote_id": "a"}]

        assert collect_bindings("org", results) == ([], [])

    @pytest.mark.parametrize(
        "hook_url",
        [None, "", "not-a-url", "http://hook.us2.make.com/x"],
    )
    def test_missing_or_unusable_url_is_reported_not_skipped(self, hook_url: Any) -> None:
        """Skipping would ship a capability that answers 503 forever."""
        bindings, unresolved = collect_bindings("org", [_scenario("booking", hook_url)])

        assert bindings == []
        assert unresolved == ["booking"]

    def test_scenario_without_a_capability_is_reported(self) -> None:
        result = {
            "platform": "make",
            "operation": "create_scenario",
            "remote_id": "6171331",
            "receipt": {},
        }

        bindings, unresolved = collect_bindings("org", [result])

        assert bindings == []
        assert unresolved == ["6171331"]

    def test_partial_failure_still_reports_the_bad_one(self) -> None:
        results = [
            _scenario("availability", "https://hook.us2.make.com/aaa"),
            _scenario("booking", None),
        ]

        bindings, unresolved = collect_bindings("org", results)

        assert [b.capability for b in bindings] == ["availability"]
        assert unresolved == ["booking"]


class TestApplyBindings:
    def test_every_binding_is_set(self) -> None:
        adapter = MagicMock()
        bindings, _ = collect_bindings(
            "org",
            [
                _scenario("availability", "https://hook.us2.make.com/aaa"),
                _scenario("booking", "https://hook.us2.make.com/bbb"),
            ],
        )

        apply_bindings(adapter, bindings)

        assert adapter.set_env_variable.call_count == 2
        adapter.set_env_variable.assert_any_call(
            "MAKE_ORG_AVAILABILITY_URL", "https://hook.us2.make.com/aaa"
        )

    def test_failure_is_not_swallowed(self) -> None:
        """A half-wired client answers some capabilities and 503s the rest."""
        adapter = MagicMock()
        adapter.set_env_variable.side_effect = RuntimeError("render rejected it")
        bindings, _ = collect_bindings(
            "org", [_scenario("booking", "https://hook.us2.make.com/bbb")]
        )

        with pytest.raises(RuntimeError):
            apply_bindings(adapter, bindings)


class TestResolveWebhookSecret:
    """Artifacts carry the placeholder; the real value is substituted in memory.

    The generated assistant config is written to outputs/ in plaintext and
    content-hashed, so embedding the secret would put it on disk and change the
    hash whenever it rotates.
    """

    def test_placeholder_is_replaced(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from orchestrator.webhook_config import resolve_webhook_secret

        monkeypatch.setenv("WEBHOOK_SECRET", "s3cret")
        config = {"serverUrlSecret": "{{WEBHOOK_SECRET}}"}

        assert resolve_webhook_secret(config) == {"serverUrlSecret": "s3cret"}

    def test_nested_and_listed_placeholders_are_replaced(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from orchestrator.webhook_config import resolve_webhook_secret

        monkeypatch.setenv("WEBHOOK_SECRET", "s3cret")
        config = {"tools": [{"server": {"url": "https://x", "secret": "{{WEBHOOK_SECRET}}"}}]}

        result = resolve_webhook_secret(config)

        assert result["tools"][0]["server"]["secret"] == "s3cret"
        assert result["tools"][0]["server"]["url"] == "https://x"

    def test_input_is_not_mutated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from orchestrator.webhook_config import resolve_webhook_secret

        monkeypatch.setenv("WEBHOOK_SECRET", "s3cret")
        config = {"serverUrlSecret": "{{WEBHOOK_SECRET}}"}

        resolve_webhook_secret(config)

        assert config["serverUrlSecret"] == "{{WEBHOOK_SECRET}}"

    def test_config_without_the_placeholder_is_untouched(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from orchestrator.webhook_config import resolve_webhook_secret

        monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
        config = {"name": "A", "model": {"provider": "openai"}}

        assert resolve_webhook_secret(config) == config

    def test_missing_secret_is_an_error_not_a_passthrough(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sending the literal placeholder deploys an assistant the backend rejects."""
        from orchestrator.webhook_config import resolve_webhook_secret
        from shared.errors import ValidationError

        monkeypatch.delenv("WEBHOOK_SECRET", raising=False)

        with pytest.raises(ValidationError, match="WEBHOOK_SECRET"):
            resolve_webhook_secret({"serverUrlSecret": "{{WEBHOOK_SECRET}}"})


class TestTemplateCarriesToolSecrets:
    def test_every_tool_declares_a_server_secret(self) -> None:
        """Vapi sends `server.secret` as x-vapi-secret; without it calls are anonymous."""
        import json
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        template = json.loads(
            (root / "ground-truth" / "configs" / "vapi_assistant_template.json").read_text(
                encoding="utf-8"
            )
        )

        for tool in template["tools"]:
            assert tool["server"].get("secret") == "{{server_url_secret}}", (
                f"{tool['function']['name']} has no server secret"
            )
