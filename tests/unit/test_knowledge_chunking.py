"""
Unit tests for knowledge chunking.

Tests T120: Knowledge chunking (one-file-per-gotcha, section-level for docs,
deterministic IDs, checksums)
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from scripts.embed_knowledge import (
    chunk_knowledge_base,
    compute_file_hash,
    parse_doc_file,
    parse_gotcha_file,
)


@pytest.mark.unit
class TestKnowledgeChunking:
    """Test knowledge chunking logic."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        # Create temp directory
        self.temp_dir = Path(tempfile.mkdtemp())
        self.gotchas_dir = self.temp_dir / "gotchas"
        self.docs_dir = self.temp_dir / "docs"
        self.gotchas_dir.mkdir()
        self.docs_dir.mkdir()

    def teardown_method(self) -> None:
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir)

    def test_parse_gotcha_file_one_chunk_per_file(self) -> None:
        """Test: One gotcha file produces one chunk."""
        # Create sample gotcha
        gotcha_content = """# Gotcha: Test Issue

**Platform:** Vapi
**Topic:** Testing
**Symptom:** Test symptom
**Verification Status:** Verified
**Approved By:** system
**Approved At:** 2026-07-14

## Root Cause

Test root cause explanation.

## Resolution

Test resolution steps.
"""
        gotcha_file = self.gotchas_dir / "test-issue.md"
        gotcha_file.write_text(gotcha_content, encoding="utf-8")

        # Parse
        chunk = parse_gotcha_file(gotcha_file)

        # Verify one chunk
        assert chunk is not None
        assert chunk["id"] == "gotcha_test-issue"
        assert chunk["content"] == gotcha_content

        # Verify metadata
        assert chunk["metadata"]["platform"] == "Vapi"
        assert chunk["metadata"]["topic"] == "Testing"
        assert chunk["metadata"]["symptom"] == "Test symptom"
        assert chunk["metadata"]["verification_status"] == "verified"
        assert chunk["metadata"]["entry_type"] == "gotcha"

    def test_parse_doc_file_deep_heading_chunks(self) -> None:
        """Test: Doc file chunks at ## heading level."""
        # Create sample doc with multiple sections
        doc_content = """# Platform Guide

Overview content here.

## Section One

Content for section one.

## Section Two

Content for section two.

## Section Three

Content for section three.
"""
        doc_file = self.docs_dir / "platform-guide.md"
        doc_file.write_text(doc_content, encoding="utf-8")

        # Parse
        chunks = parse_doc_file(doc_file)

        # Verify one chunk per section + overview
        assert len(chunks) == 4  # Overview + 3 sections

        # Check overview chunk
        assert chunks[0]["id"] == "doc_platform-guide_overview"
        assert chunks[0]["metadata"]["section"] == "Overview"
        assert chunks[0]["metadata"]["doc_title"] == "Platform Guide"

        # Check section chunks
        assert chunks[1]["id"] == "doc_platform-guide_section_1"
        assert chunks[1]["metadata"]["section"] == "Section One"

        assert chunks[2]["id"] == "doc_platform-guide_section_2"
        assert chunks[2]["metadata"]["section"] == "Section Two"

        assert chunks[3]["id"] == "doc_platform-guide_section_3"
        assert chunks[3]["metadata"]["section"] == "Section Three"

    def test_chunk_deterministic_ids(self) -> None:
        """Test: Chunk IDs are deterministic based on file and position."""
        # Create gotcha
        gotcha_content = """# Gotcha: Deterministic Test

**Platform:** Test
**Topic:** Testing
**Symptom:** Test
**Verification Status:** Verified
**Approved By:** system
**Approved At:** 2026-07-14

## Root Cause
Test

## Resolution
Test
"""
        gotcha_file = self.gotchas_dir / "deterministic-test.md"
        gotcha_file.write_text(gotcha_content, encoding="utf-8")

        # Parse twice
        chunk1 = parse_gotcha_file(gotcha_file)
        chunk2 = parse_gotcha_file(gotcha_file)

        # IDs should be identical
        assert chunk1["id"] == chunk2["id"]
        assert chunk1["id"] == "gotcha_deterministic-test"

    def test_chunk_includes_checksum(self) -> None:
        """Test: Each chunk includes content checksum."""
        # Create gotcha
        gotcha_content = """# Gotcha: Checksum Test

**Platform:** Test
**Topic:** Testing
**Symptom:** Test
**Verification Status:** Verified
**Approved By:** system
**Approved At:** 2026-07-14

## Root Cause
Test

## Resolution
Test
"""
        gotcha_file = self.gotchas_dir / "checksum-test.md"
        gotcha_file.write_text(gotcha_content, encoding="utf-8")

        # Parse
        chunk = parse_gotcha_file(gotcha_file)

        # Verify checksum exists and matches file
        assert "content_hash" in chunk["metadata"]
        expected_hash = compute_file_hash(gotcha_file)
        assert chunk["metadata"]["content_hash"] == expected_hash

    def test_chunk_includes_required_metadata(self) -> None:
        """Test: Chunks include all required metadata fields."""
        # Create gotcha
        gotcha_content = """# Gotcha: Metadata Test

**Platform:** Supabase
**Topic:** RLS
**Symptom:** Policy not working
**Verification Status:** Verified
**Approved By:** system
**Approved At:** 2026-07-14

## Root Cause

RLS not enabled.

## Resolution

Enable RLS on table.
"""
        gotcha_file = self.gotchas_dir / "metadata-test.md"
        gotcha_file.write_text(gotcha_content, encoding="utf-8")

        # Parse
        chunk = parse_gotcha_file(gotcha_file)

        # Verify required fields
        required = [
            "source_path",
            "content_hash",
            "entry_id",
            "entry_type",
            "platform",
            "topic",
            "symptom",
            "verification_status",
        ]

        for field in required:
            assert field in chunk["metadata"], f"Missing required field: {field}"

    def test_chunk_knowledge_base_collects_all(self) -> None:
        """Test: chunk_knowledge_base finds all gotchas and docs."""
        # Create multiple files
        gotcha1 = self.gotchas_dir / "gotcha1.md"
        gotcha1.write_text(
            """# Gotcha: One
**Platform:** Vapi
**Topic:** Test
**Symptom:** Test
**Verification Status:** Verified
**Approved By:** system
**Approved At:** 2026-07-14

## Root Cause
Test

## Resolution
Test
""",
            encoding="utf-8",
        )

        gotcha2 = self.gotchas_dir / "gotcha2.md"
        gotcha2.write_text(
            """# Gotcha: Two
**Platform:** Make
**Topic:** Test
**Symptom:** Test
**Verification Status:** Verified
**Approved By:** system
**Approved At:** 2026-07-14

## Root Cause
Test

## Resolution
Test
""",
            encoding="utf-8",
        )

        doc1 = self.docs_dir / "doc1.md"
        doc1.write_text(
            """# Doc One

Overview

## Section A

Content A

## Section B

Content B
""",
            encoding="utf-8",
        )

        # Chunk all
        chunks = chunk_knowledge_base(self.temp_dir)

        # Should have: 2 gotchas + 1 overview + 2 sections = 5 chunks
        assert len(chunks) == 5

        # Verify mix of types
        gotcha_chunks = [c for c in chunks if c["metadata"]["entry_type"] == "gotcha"]
        doc_chunks = [c for c in chunks if c["metadata"]["entry_type"] == "doc"]

        assert len(gotcha_chunks) == 2
        assert len(doc_chunks) == 3

    def test_nested_headings_only_chunk_at_level_2(self) -> None:
        """Test: Only ## headings create new chunks, not ###."""
        doc_content = """# Guide

Overview

## Major Section

Content

### Subsection

This should be part of Major Section chunk, not separate.

## Another Major

Content
"""
        doc_file = self.docs_dir / "nested.md"
        doc_file.write_text(doc_content, encoding="utf-8")

        chunks = parse_doc_file(doc_file)

        # Should be: overview + 2 major sections = 3 chunks
        # NOT 4 chunks (subsection should not be separate)
        assert len(chunks) == 3

        # Check that subsection is part of Major Section chunk
        major_section_chunk = chunks[1]
        assert "### Subsection" in major_section_chunk["content"]
