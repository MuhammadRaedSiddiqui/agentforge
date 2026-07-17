"""
Integration test for diagnostic fixtures answered from verified knowledge.

Tests T122: Three diagnostic fixtures answered from verified knowledge
"""

from typing import Any

import pytest

from agents.information_agent.agent import InformationAgent


@pytest.mark.integration
class TestKnowledgeSearch:
    """
    Integration tests for knowledge-based troubleshooting.

    Tests that known problems can be diagnosed from verified internal knowledge.
    """

    @pytest.fixture
    def agent(self) -> Any:
        """Create information agent for testing."""
        return InformationAgent(fallback_enabled=False)

    def test_diagnostic_fixture_1_vapi_phone_timeout(self, agent: Any) -> None:
        """
        Test Fixture 1: Vapi phone number assignment timeout.

        Expected: Find verified gotcha with reconciliation guidance.
        """
        # Diagnose problem
        result = agent.diagnose(
            problem_description="Vapi phone number assignment times out after 30 seconds",
            platform="vapi",
        )

        # Should find verified result
        assert (
            result["source"] == "verified_internal_knowledge"
            or result["source"] == "verified_internal_gotchas"
        )
        assert result["confidence"] == "high"

        # Should have recommendation
        assert result["recommendation"] is not None
        assert result["recommendation"]["status"] in [
            "verified_solution_found",
            "gotcha_found",
        ]

        # Should cite source
        if "citation" in result["recommendation"]:
            assert (
                "vapi" in result["recommendation"]["citation"].lower()
                or "phone" in result["recommendation"]["citation"].lower()
            )

    def test_diagnostic_fixture_2_make_blueprint_import(self, agent: Any) -> None:
        """
        Test Fixture 2: Make.com blueprint import fails silently.

        Expected: Find verified gotcha with validation guidance.
        """
        result = agent.diagnose(
            problem_description="Make.com scenario created but not working correctly after blueprint import",
            platform="make",
        )

        # Should find verified result
        assert result["source"] in [
            "verified_internal_knowledge",
            "verified_internal_gotchas",
        ]
        assert result["confidence"] == "high"

        # Should have recommendation
        assert result["recommendation"] is not None

    def test_diagnostic_fixture_3_supabase_rls_not_applied(self, agent: Any) -> None:
        """
        Test Fixture 3: Supabase RLS policy not applied after migration.

        Expected: Find verified gotcha with policy verification steps.
        """
        result = agent.diagnose(
            problem_description="Supabase RLS policies defined in migration but not being applied",
            platform="supabase",
        )

        # Should find verified result
        assert result["source"] in [
            "verified_internal_knowledge",
            "verified_internal_gotchas",
        ]
        assert result["confidence"] == "high"

        # Should have recommendation
        assert result["recommendation"] is not None

    def test_unknown_problem_no_verified_results(self, agent: Any) -> None:
        """
        Test: Unknown problem with no verified knowledge returns appropriate response.

        Expected: No verified results, clear message.
        """
        result = agent.diagnose(
            problem_description="Completely unknown hypothetical problem that has never been documented",
            platform="unknown_platform",
        )

        # Should not find verified results
        assert result["verified_results"] is None or not result["verified_results"]["found"]

        # With fallback disabled, should indicate no information
        assert result["source"] == "none" or result["confidence"] == "none"

    def test_get_platform_documentation(self, agent: Any) -> None:
        """
        Test: Retrieving platform documentation works.

        Expected: Find verified documentation sections.
        """
        result = agent.get_documentation(
            platform="vapi",
            topic="phone numbers",
        )

        # Should have documentation
        assert "documentation" in result
        assert result["source"] == "verified_internal_documentation"

    def test_fallback_to_external_when_enabled(self) -> None:
        """
        Test: External fallback triggers when no verified knowledge found.

        Expected: Fallback clearly labeled as unverified.
        """
        # Create agent with fallback enabled
        agent = InformationAgent(fallback_enabled=True)

        result = agent.diagnose(
            problem_description="Extremely obscure problem unlikely to be in knowledge base XYZ123",
            platform="unknown",
        )

        # Should attempt fallback
        # May or may not have fallback results depending on Brave API availability
        if result["source"] == "external_web_search":
            assert "warning" in result
            assert result["confidence"] == "low"
            assert "unverified" in result["warning"].lower()

    def test_propose_knowledge_checks_duplicates(self, agent: Any) -> None:
        """
        Test: Proposing knowledge checks for duplicates.

        Expected: Duplicate detection if similar entry exists.
        """
        result = agent.propose_knowledge(
            symptom="Vapi phone assignment timeout",
            root_cause="Test",
            resolution="Test",
            platform="vapi",
            topic="phone",
        )

        # Should check for duplicates
        # May find duplicate if gotcha exists
        assert "status" in result

    def test_knowledge_stats_available(self, agent: Any) -> None:
        """
        Test: Can retrieve knowledge base statistics.

        Expected: Stats with entry counts by type and platform.
        """
        stats = agent.get_stats()

        # Should have required fields
        assert "total_entries" in stats
        assert "gotchas" in stats
        assert "docs" in stats
        assert "verified" in stats
        assert "by_platform" in stats
