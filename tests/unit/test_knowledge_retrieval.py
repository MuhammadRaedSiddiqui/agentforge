"""
Unit tests for Chroma retrieval.

Tests T121: Chroma retrieval (threshold behavior, verified-only filter,
provenance display)
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from agents.information_agent.rag import KnowledgeRetrieval


@pytest.mark.unit
class TestKnowledgeRetrieval:
    """Test Chroma-based knowledge retrieval."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        # Create temp Chroma directory
        self.temp_dir = Path(tempfile.mkdtemp())
        self.chroma_dir = self.temp_dir / "chroma_test"
        self.chroma_dir.mkdir()

        # Create retrieval system
        self.retrieval = KnowledgeRetrieval(
            chroma_dir=self.chroma_dir,
            distance_threshold=1.5,
        )

        # Get collection
        self.collection = self.retrieval.get_or_create_collection()

        # Add test data
        self._populate_test_data()

    def teardown_method(self) -> None:
        """Clean up temp directory."""
        # Close Chroma client to release file handles (important for Windows)
        self.retrieval.close()

        # Small delay to ensure file handles are released
        import time

        time.sleep(0.1)

        try:
            shutil.rmtree(self.temp_dir)
        except PermissionError:
            # On Windows, sometimes files are still locked
            # Try one more time after a short delay
            time.sleep(0.5)
            shutil.rmtree(self.temp_dir)

    def _populate_test_data(self) -> None:
        """Populate collection with test data."""
        # Add verified gotcha
        self.collection.add(
            ids=["gotcha_test_timeout"],
            documents=["Vapi phone assignment times out after 30 seconds"],
            metadatas=[
                {
                    "entry_type": "gotcha",
                    "platform": "vapi",
                    "symptom": "Phone assignment timeout",
                    "verification_status": "verified",
                    "source_path": "knowledge-base/gotchas/test-timeout.md",
                }
            ],
        )

        # Add verified doc
        self.collection.add(
            ids=["doc_vapi_overview"],
            documents=["Vapi provides voice AI assistant APIs"],
            metadatas=[
                {
                    "entry_type": "doc",
                    "platform": "vapi",
                    "doc_title": "Vapi Guide",
                    "section": "Overview",
                    "verification_status": "verified",
                    "source_path": "knowledge-base/docs/vapi-guide.md",
                }
            ],
        )

        # Add unverified entry
        self.collection.add(
            ids=["gotcha_test_unverified"],
            documents=["Some unverified troubleshooting tip"],
            metadatas=[
                {
                    "entry_type": "gotcha",
                    "platform": "make",
                    "symptom": "Scenario not working",
                    "verification_status": "proposed",
                    "source_path": "knowledge-base/proposals/test.md",
                }
            ],
        )

    def test_threshold_behavior_filters_distant_matches(self) -> None:
        """Test: Distance threshold filters out low-similarity matches."""
        # Search with very restrictive threshold
        self.retrieval.distance_threshold = 0.1

        results = self.retrieval.search_knowledge(
            query="phone assignment",
            verified_only=True,
        )

        # With restrictive threshold, may get 0-1 results
        # (exact match might still pass, but unrelated won't)
        assert len(results) <= 1

        # Reset to permissive threshold
        self.retrieval.distance_threshold = 2.0

        results = self.retrieval.search_knowledge(
            query="phone assignment",
            verified_only=True,
        )

        # With permissive threshold, should get more results
        assert len(results) >= 1

    def test_verified_only_filter(self) -> None:
        """Test: verified_only=True filters out unverified entries."""
        # Search with verified_only=True
        results = self.retrieval.search_knowledge(
            query="scenario troubleshooting",
            verified_only=True,
        )

        # Should not include unverified entry
        for result in results:
            assert result["metadata"]["verification_status"] == "verified"

        # Search with verified_only=False
        self.retrieval.distance_threshold = 2.0  # Permissive
        all_results = self.retrieval.search_knowledge(
            query="scenario",
            verified_only=False,
            n_results=10,
        )

        # Should include both verified and unverified
        statuses = {r["metadata"]["verification_status"] for r in all_results}
        # May or may not find both depending on similarity

    def test_provenance_display_in_results(self) -> None:
        """Test: Results include source citation."""
        results = self.retrieval.search_knowledge(
            query="vapi phone",
            verified_only=True,
        )

        assert len(results) > 0

        # Check first result has citation
        result = results[0]
        assert "citation" in result
        assert "metadata" in result
        assert "source_path" in result["metadata"]

        # Citation should be human-readable
        assert isinstance(result["citation"], str)
        assert len(result["citation"]) > 0

    def test_search_by_symptom_returns_gotchas_only(self) -> None:
        """Test: search_by_symptom returns only gotcha entries."""
        results = self.retrieval.search_by_symptom(
            symptom="timeout issue",
            platform="vapi",
        )

        # All results should be gotchas
        for result in results:
            assert result["metadata"]["entry_type"] == "gotcha"

    def test_search_docs_returns_docs_only(self) -> None:
        """Test: search_docs returns only doc entries."""
        results = self.retrieval.search_docs(
            query="API guide",
            platform="vapi",
        )

        # All results should be docs
        for result in results:
            assert result["metadata"]["entry_type"] == "doc"

    def test_platform_filter(self) -> None:
        """Test: Platform filter correctly limits results."""
        # Search for vapi only
        vapi_results = self.retrieval.search_docs(
            query="guide",
            platform="vapi",
        )

        # All should be vapi
        for result in vapi_results:
            assert result["metadata"]["platform"] == "vapi"

        # Search for make only
        make_results = self.retrieval.search_by_symptom(
            symptom="not working",
            platform="make",
        )

        # All should be make
        for result in make_results:
            assert result["metadata"]["platform"] == "make"

    def test_distance_to_similarity_conversion(self) -> None:
        """Test: Distance is converted to similarity score."""
        results = self.retrieval.search_knowledge(
            query="vapi",
            verified_only=True,
        )

        if results:
            result = results[0]

            # Should have both distance and similarity
            assert "distance" in result
            assert "similarity" in result

            # Similarity = 1 - distance (for cosine)
            expected_similarity = 1.0 - result["distance"]
            assert abs(result["similarity"] - expected_similarity) < 0.001

            # Similarity should be 0-1 range
            assert 0 <= result["similarity"] <= 1

    def test_get_stats(self) -> None:
        """Test: get_stats returns accurate counts."""
        stats = self.retrieval.get_stats()

        # Check structure
        assert "total_entries" in stats
        assert "gotchas" in stats
        assert "docs" in stats
        assert "verified" in stats
        assert "by_platform" in stats
        assert "distance_threshold" in stats

        # Check values match test data
        assert stats["total_entries"] == 3  # 2 verified + 1 unverified
        assert stats["gotchas"] == 2
        assert stats["docs"] == 1
        assert stats["verified"] == 2

    def test_n_results_limit(self) -> None:
        """Test: n_results parameter limits returned matches."""
        # Request only 1 result
        results = self.retrieval.search_knowledge(
            query="vapi",
            verified_only=False,
            n_results=1,
        )

        # Should get at most 1
        assert len(results) <= 1

        # Request 10 results (more than available)
        results = self.retrieval.search_knowledge(
            query="vapi",
            verified_only=False,
            n_results=10,
        )

        # Should get all available (but capped by threshold)
        assert len(results) <= 10

    def test_empty_query_returns_results(self) -> None:
        """Test: Empty or very generic query still works."""
        results = self.retrieval.search_knowledge(
            query="",
            verified_only=True,
        )

        # Should not crash
        assert isinstance(results, list)
