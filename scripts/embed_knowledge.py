"""
Knowledge embedding script for Agent Forge.

Implements deterministic chunking and embedding of verified knowledge base
into Chroma for retrieval during troubleshooting.

T125: Deterministic chunking (one chunk per gotcha file, deep-heading chunks
      for docs, metadata with platform/topic/symptom/resolution)
T131: --verify and --rebuild flags
"""

import argparse
import hashlib
import re
import sys
from pathlib import Path
from typing import Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def compute_file_hash(file_path: Path) -> str:
    """
    Compute SHA-256 hash of file contents.

    Args:
        file_path: Path to file

    Returns:
        Hex digest of file hash
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def parse_gotcha_file(file_path: Path) -> dict[str, Any]:
    """
    Parse a gotcha Markdown file into structured chunk.

    One gotcha file = one chunk with full metadata.

    Args:
        file_path: Path to gotcha file

    Returns:
        Chunk dictionary with metadata and content
    """
    content = file_path.read_text(encoding="utf-8")

    # Extract metadata from Markdown structure
    # Handle both relative and absolute paths
    try:
        source_path = str(file_path.relative_to(Path.cwd()))
    except ValueError:
        # Already relative or not in cwd
        source_path = str(file_path)

    metadata = {
        "source_path": source_path,
        "content_hash": compute_file_hash(file_path),
        "entry_id": file_path.stem,  # filename without .md
        "entry_type": "gotcha",
    }

    # Parse structured fields
    # Format: **FieldName:** Value
    lines = content.split("\n")
    for i, line in enumerate(lines):
        # Split on ':** ' to handle markdown bold format
        if ":**" in line:
            parts = line.split(":**", 1)
            if len(parts) == 2:
                field_name = parts[0].strip("*").strip()
                value = parts[1].strip()

                if field_name == "Platform":
                    metadata["platform"] = value
                elif field_name == "Topic":
                    metadata["topic"] = value
                elif field_name == "Symptom":
                    metadata["symptom"] = value
                elif field_name == "Verification Status":
                    metadata["verification_status"] = value.lower()
                elif field_name == "Approved By":
                    metadata["approved_by"] = value
                elif field_name == "Approved At":
                    metadata["approved_at"] = value

    # Extract root cause section
    root_cause_match = re.search(r"## Root Cause\n\n(.*?)\n\n##", content, re.DOTALL)
    if root_cause_match:
        metadata["root_cause"] = root_cause_match.group(1).strip()

    # Extract resolution section
    resolution_match = re.search(r"## Resolution\n\n(.*?)(?=\n\n##|$)", content, re.DOTALL)
    if resolution_match:
        metadata["resolution"] = resolution_match.group(1).strip()

    return {
        "id": f"gotcha_{metadata['entry_id']}",
        "content": content,
        "metadata": metadata,
    }


def parse_doc_file(file_path: Path) -> list[dict[str, Any]]:
    """
    Parse a documentation Markdown file into chunks at deep heading level.

    Each ## heading becomes a separate chunk.

    Args:
        file_path: Path to doc file

    Returns:
        List of chunk dictionaries
    """
    content = file_path.read_text(encoding="utf-8")

    # Split by ## headings
    sections = re.split(r"\n(?=## )", content)

    chunks = []

    # Handle both relative and absolute paths
    try:
        source_path = str(file_path.relative_to(Path.cwd()))
    except ValueError:
        # Already relative or not in cwd
        source_path = str(file_path)

    # First section is title and overview
    if sections:
        title_section = sections[0]
        title_match = re.match(r"# (.+)", title_section)
        doc_title = title_match.group(1) if title_match else file_path.stem

        # Overview chunk (everything before first ## heading)
        if len(sections) > 1:
            chunks.append(
                {
                    "id": f"doc_{file_path.stem}_overview",
                    "content": title_section,
                    "metadata": {
                        "source_path": source_path,
                        "content_hash": compute_file_hash(file_path),
                        "entry_id": f"{file_path.stem}_overview",
                        "entry_type": "doc",
                        "doc_title": doc_title,
                        "section": "Overview",
                        "platform": extract_platform_from_filename(file_path),
                        "verification_status": "verified",
                    },
                }
            )

        # Section chunks
        for i, section in enumerate(sections[1:], start=1):
            # Extract section heading
            heading_match = re.match(r"## (.+)", section)
            if heading_match:
                section_title = heading_match.group(1)

                chunks.append(
                    {
                        "id": f"doc_{file_path.stem}_section_{i}",
                        "content": section,
                        "metadata": {
                            "source_path": source_path,
                            "content_hash": compute_file_hash(file_path),
                            "entry_id": f"{file_path.stem}_section_{i}",
                            "entry_type": "doc",
                            "doc_title": doc_title,
                            "section": section_title,
                            "platform": extract_platform_from_filename(file_path),
                            "verification_status": "verified",
                        },
                    }
                )

    return chunks


def extract_platform_from_filename(file_path: Path) -> str:
    """
    Extract platform from filename.

    Args:
        file_path: Path to file

    Returns:
        Platform name
    """
    filename = file_path.stem
    if "supabase" in filename:
        return "supabase"
    elif "vapi" in filename:
        return "vapi"
    elif "make" in filename:
        return "make"
    elif "render" in filename:
        return "render"
    else:
        return "general"


def chunk_knowledge_base(base_path: Path) -> list[dict[str, Any]]:
    """
    Chunk entire knowledge base deterministically.

    Args:
        base_path: Path to knowledge-base directory

    Returns:
        List of all chunks
    """
    all_chunks = []

    # Process gotchas (one file = one chunk)
    gotchas_path = base_path / "gotchas"
    if gotchas_path.exists():
        for gotcha_file in sorted(gotchas_path.glob("*.md")):
            chunk = parse_gotcha_file(gotcha_file)
            all_chunks.append(chunk)
            print(f"  Chunked gotcha: {gotcha_file.name}")

    # Process docs (deep heading = one chunk)
    docs_path = base_path / "docs"
    if docs_path.exists():
        for doc_file in sorted(docs_path.glob("*.md")):
            chunks = parse_doc_file(doc_file)
            all_chunks.extend(chunks)
            print(f"  Chunked doc: {doc_file.name} ({len(chunks)} sections)")

    return all_chunks


def verify_embeddings(base_path: Path, collection: Any) -> bool:
    """
    Verify embedded knowledge matches source files.

    Args:
        base_path: Path to knowledge-base directory
        collection: Chroma collection

    Returns:
        True if all checksums match
    """
    print("\nVerifying embeddings...")

    chunks = chunk_knowledge_base(base_path)

    # Get all IDs from collection
    results = collection.get(include=["metadatas"])

    embedded_ids = set(results["ids"])
    source_ids = {chunk["id"] for chunk in chunks}

    # Check for missing
    missing = source_ids - embedded_ids
    if missing:
        print(f"  [ERROR] Missing embeddings: {len(missing)}")
        for chunk_id in sorted(missing):
            print(f"    - {chunk_id}")
        return False

    # Check for stale (hash mismatch)
    stale = []
    for chunk in chunks:
        # Get embedded metadata
        embedded = collection.get(ids=[chunk["id"]], include=["metadatas"])

        if embedded["ids"]:
            embedded_hash = embedded["metadatas"][0].get("content_hash")
            source_hash = chunk["metadata"]["content_hash"]

            if embedded_hash != source_hash:
                stale.append(chunk["id"])

    if stale:
        print(f"  [ERROR] Stale embeddings (hash mismatch): {len(stale)}")
        for chunk_id in sorted(stale):
            print(f"    - {chunk_id}")
        return False

    print(f"  [OK] All {len(source_ids)} embeddings verified")
    return True


def rebuild_embeddings(base_path: Path, chroma_dir: Path) -> None:
    """
    Rebuild all embeddings from scratch.

    Args:
        base_path: Path to knowledge-base directory
        chroma_dir: Path to Chroma persistence directory
    """
    print("\nRebuilding embeddings from scratch...")

    # Import Chroma
    try:
        import chromadb
    except ImportError:
        print("Error: chromadb not installed. Run: pip install chromadb")
        sys.exit(1)

    # Create client
    client = chromadb.PersistentClient(path=str(chroma_dir))

    # Delete existing collection if it exists
    try:
        client.delete_collection("knowledge_base")
        print("  Deleted existing collection")
    except Exception:
        pass

    # Create new collection
    collection = client.create_collection(
        name="knowledge_base",
        metadata={"hnsw:space": "cosine", "description": "Agent Forge verified knowledge base"},
    )

    # Chunk knowledge
    chunks = chunk_knowledge_base(base_path)

    print(f"\nEmbedding {len(chunks)} chunks...")

    # Add chunks in batches
    batch_size = 100
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]

        collection.add(
            ids=[chunk["id"] for chunk in batch],
            documents=[chunk["content"] for chunk in batch],
            metadatas=[chunk["metadata"] for chunk in batch],
        )

        print(
            f"  Embedded batch {i // batch_size + 1}/{(len(chunks) + batch_size - 1) // batch_size}"
        )

    print(f"\n[OK] Successfully embedded {len(chunks)} chunks")
    print(f"  Chroma directory: {chroma_dir}")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Embed Agent Forge knowledge base into Chroma")
    parser.add_argument(
        "--verify", action="store_true", help="Verify existing embeddings match source files"
    )
    parser.add_argument("--rebuild", action="store_true", help="Rebuild embeddings from scratch")
    parser.add_argument(
        "--base-path",
        type=Path,
        default=Path("knowledge-base"),
        help="Path to knowledge-base directory",
    )
    parser.add_argument(
        "--chroma-dir",
        type=Path,
        default=Path("chroma_data"),
        help="Path to Chroma persistence directory",
    )

    args = parser.parse_args()

    # Validate base path
    if not args.base_path.exists():
        print(f"Error: Knowledge base not found at {args.base_path}")
        sys.exit(1)

    # Execute command
    if args.rebuild:
        rebuild_embeddings(args.base_path, args.chroma_dir)
    elif args.verify:
        # Import Chroma
        try:
            import chromadb
        except ImportError:
            print("Error: chromadb not installed. Run: pip install chromadb")
            sys.exit(1)

        # Load collection
        client = chromadb.PersistentClient(path=str(args.chroma_dir))
        try:
            collection = client.get_collection("knowledge_base")
        except Exception:
            print("Error: Collection not found. Run with --rebuild first.")
            sys.exit(1)

        # Verify
        if verify_embeddings(args.base_path, collection):
            print("\n[OK] Verification passed")
            sys.exit(0)
        else:
            print("\n[ERROR] Verification failed")
            print("  Run with --rebuild to fix")
            sys.exit(1)
    else:
        print("Error: Specify --rebuild or --verify")
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
