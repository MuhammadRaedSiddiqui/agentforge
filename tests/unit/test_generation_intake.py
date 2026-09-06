"""
Unit tests for intake loading and the generation-intake shape.

Found by running 19 varied client profiles through `agent-forge generate`:

  - the command failed on every single input, because the reshaping the
    agents depend on lived inline in the execute path only
  - an intake for "Café München" loaded as "CafÃ© MÃ¼nchen", because the file
    was opened with the platform's locale codec instead of UTF-8, and that
    mojibake propagated into the generated assistant name
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from cli.main import build_generation_intake, load_intake_file

pytestmark = pytest.mark.unit


def _config(tmp_path: Any) -> MagicMock:
    server = tmp_path / "server.js"
    server.write_text("// server", encoding="utf-8")
    config = MagicMock()
    config.hosting_health_url = "https://svc.onrender.com/health"
    config.server_source_path = str(server)
    return config


def _intake(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "organization_id": "test_org",
        "business_name": "Test Biz",
        "voice_id": "Elliot",
        "enabled_capabilities": ["booking", "availability"],
    }
    base.update(overrides)
    return base


class TestLoadIntakeFilePreservesUnicode:
    """A non-ASCII business name must survive loading byte for byte."""

    def test_accented_name_round_trips(self, tmp_path: Any) -> None:
        path = tmp_path / "intake.json"
        name = "Café München Friseursalon"
        path.write_text(json.dumps({"business_name": name}, ensure_ascii=False), encoding="utf-8")

        loaded = load_intake_file(str(path))

        assert loaded["business_name"] == name
        # The specific corruption seen live: é read as its two UTF-8 bytes.
        assert "Ã©" not in loaded["business_name"]

    def test_non_latin_script_round_trips(self, tmp_path: Any) -> None:
        path = tmp_path / "intake.json"
        name = "東京ウェルネス"
        path.write_text(json.dumps({"business_name": name}, ensure_ascii=False), encoding="utf-8")

        assert load_intake_file(str(path))["business_name"] == name

    def test_ascii_escaped_json_still_loads(self, tmp_path: Any) -> None:
        """A writer using ensure_ascii=True must load identically."""
        path = tmp_path / "intake.json"
        name = "Café München"
        path.write_text(json.dumps({"business_name": name}), encoding="utf-8")

        assert load_intake_file(str(path))["business_name"] == name

    def test_invalid_utf8_is_reported_clearly(self, tmp_path: Any) -> None:
        path = tmp_path / "intake.json"
        path.write_bytes(b'{"business_name": "\xff\xfe bad"}')

        with pytest.raises(ValueError, match="UTF-8"):
            load_intake_file(str(path))


class TestBuildGenerationIntake:
    """`generate` handed the raw intake to the agents and failed on every input."""

    def test_supplies_every_key_the_agents_read(self, tmp_path: Any) -> None:
        result = build_generation_intake(_intake(), _config(tmp_path))

        assert result["capabilities"] == ["booking", "availability"]
        assert result["vapi"]["voice_id"] == "Elliot"
        assert result["hosting"]["webhook_base_url"] == "https://svc.onrender.com"
        assert result["server_source_path"]

    def test_webhook_base_is_not_the_health_endpoint(self, tmp_path: Any) -> None:
        result = build_generation_intake(_intake(), _config(tmp_path))

        assert "/health" not in result["hosting"]["webhook_base_url"]

    def test_original_fields_are_preserved(self, tmp_path: Any) -> None:
        result = build_generation_intake(_intake(), _config(tmp_path))

        assert result["organization_id"] == "test_org"
        assert result["business_name"] == "Test Biz"

    def test_does_not_mutate_the_input(self, tmp_path: Any) -> None:
        intake = _intake()
        build_generation_intake(intake, _config(tmp_path))

        assert "capabilities" not in intake
        assert "hosting" not in intake

    def test_falls_back_to_the_intake_server_path(self, tmp_path: Any) -> None:
        fallback = tmp_path / "fallback.js"
        fallback.write_text("// fallback", encoding="utf-8")
        config = _config(tmp_path)
        config.server_source_path = str(tmp_path / "missing.js")

        result = build_generation_intake(_intake(server_source_path=str(fallback)), config)

        assert result["server_source_path"] == str(fallback)

    def test_no_server_source_anywhere_is_an_error(self, tmp_path: Any) -> None:
        config = _config(tmp_path)
        config.server_source_path = str(tmp_path / "missing.js")

        with pytest.raises(ValueError, match="Server source file not found"):
            build_generation_intake(_intake(), config)

    def test_missing_capabilities_becomes_an_empty_list(self, tmp_path: Any) -> None:
        intake = _intake()
        del intake["enabled_capabilities"]

        assert build_generation_intake(intake, _config(tmp_path))["capabilities"] == []


class TestNoEncodinglessTextReads:
    """Reading text without an explicit encoding is the mojibake bug's shape.

    On Windows the default is cp1252, so any UTF-8 content silently corrupts.
    This walks the source rather than trusting that the four known sites were
    the only ones.
    """

    def test_source_files_specify_an_encoding_for_text_reads(self) -> None:
        import re

        root = Path(__file__).resolve().parents[2]
        pattern = re.compile(
            r"""(\.open\(\s*["']r["']\s*\)|\.read_text\(\s*\)|open\(\s*[^,()]+,\s*["']r["']\s*\))"""
        )
        offenders = []
        for directory in ("adapters", "agents", "orchestrator", "cli", "shared"):
            for path in (root / directory).rglob("*.py"):
                for number, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), start=1
                ):
                    if pattern.search(line) and "encoding" not in line:
                        offenders.append(f"{path.relative_to(root)}:{number}")

        assert offenders == [], f"text reads without an explicit encoding: {offenders}"
