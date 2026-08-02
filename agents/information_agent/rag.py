"""
RAG (Retrieval-Augmented Generation) system for Agent Forge.

Implements Chroma-based knowledge retrieval with verified-first logic.

T126: Chroma collection management (create/rebuild, explicit distance metric,
      embedding function, configurable threshold)
T127: Verified knowledge retrieval (search, threshold filter, verification
      status check, source citation)
"""

import os
from pathlib import Path
from typing import Any, cast

import chromadb
from chromadb.config import Settings


class KnowledgeRetrieval:
    """
    Manages knowledge retrieval from Chroma vector store.

    Implements verified-first retrieval with configurable distance threshold.
    """

    # Default distance threshold for retrieval
    # Research decision: 1.5 as initial configurable default
    # Must be calibrated against labeled fixtures before production
    DEFAULT_DISTANCE_THRESHOLD = 1.5

    def __init__(
        self,
        chroma_dir: Path | None = None,
        distance_threshold: float = DEFAULT_DISTANCE_THRESHOLD,
    ):
        """
        Initialize knowledge retrieval system.

        Args:
            chroma_dir: Path to Chroma persistence directory
            distance_threshold: Maximum cosine distance for matches
        """
        # Default to CHROMA_PERSIST_DIR from environment
        if chroma_dir is None:
            chroma_dir = Path(os.getenv("CHROMA_PERSIST_DIR", "chroma_data"))

        self.chroma_dir = chroma_dir
        self.distance_threshold = distance_threshold

        # Create client with explicit configuration
        self.client = chromadb.PersistentClient(
            path=str(self.chroma_dir),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True,
            ),
        )

        self.collection: Any | None = None

    def get_or_create_collection(self) -> Any:
        """
        Get or create the knowledge base collection.

        Collection configuration:
        - Distance metric: cosine
        - Embedding function: default (Chroma's sentence transformers)

        Returns:
            Chroma collection
        """
        if self.collection is None:
            try:
                # Try to get existing collection
                self.collection = self.client.get_collection(name="knowledge_base")
            except Exception:
                # Create if doesn't exist
                self.collection = self.client.create_collection(
                    name="knowledge_base",
                    metadata={
                        "hnsw:space": "cosine",  # Explicit distance metric
                        "description": "Agent Forge verified knowledge base",
                    },
                )

        if self.collection is None:
            raise RuntimeError("Failed to initialize knowledge collection")
        return self.collection

    def search_knowledge(
        self,
        query: str,
        verified_only: bool = True,
        n_results: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Search knowledge base for relevant entries.

        Implements T127: verified knowledge retrieval with threshold filter,
        verification status check, and source citation.

        Args:
            query: Search query text
            verified_only: If True, only return verified entries
            n_results: Maximum number of results

        Returns:
            List of matching knowledge entries with metadata
        """
        collection = self.get_or_create_collection()

        # Build where filter for verified entries
        where: Any = None
        if verified_only:
            where = {"verification_status": "verified"}

        # Query collection
        results = cast(
            dict[str, Any],
            collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where,
                include=["documents", "metadatas", "distances"],
            ),
        )

        # Filter by distance threshold and structure results
        matches = []
        distances = cast(list[list[float]], results.get("distances") or [[]])
        ids = cast(list[list[str]], results.get("ids") or [[]])
        documents = cast(list[list[str]], results.get("documents") or [[]])
        metadatas = cast(list[list[dict[str, Any]]], results.get("metadatas") or [[]])

        for i, distance in enumerate(distances[0]):
            # Apply threshold filter
            if distance > self.distance_threshold:
                continue

            match = {
                "id": ids[0][i],
                "content": documents[0][i],
                "metadata": metadatas[0][i],
                "distance": distance,
                "similarity": 1.0 - distance,  # Convert distance to similarity
            }

            # Add source citation
            metadata = cast(dict[str, Any], match["metadata"])
            match["citation"] = self._format_citation(metadata)

            matches.append(match)

        return matches

    def search_by_symptom(
        self,
        symptom: str,
        platform: str | None = None,
        n_results: int = 3,
    ) -> list[dict[str, Any]]:
        """
        Search for gotchas matching a symptom.

        Args:
            symptom: Problem symptom
            platform: Optional platform filter
            n_results: Maximum number of results

        Returns:
            List of matching gotchas
        """
        collection = self.get_or_create_collection()

        # Build where filter using $and for multiple conditions
        conditions = [
            {"verification_status": "verified"},
            {"entry_type": "gotcha"},
        ]

        if platform:
            conditions.append({"platform": platform.lower()})

        where: Any = {"$and": conditions} if len(conditions) > 1 else conditions[0]

        # Query
        results = cast(
            dict[str, Any],
            collection.query(
                query_texts=[symptom],
                n_results=n_results,
                where=where,
                include=["documents", "metadatas", "distances"],
            ),
        )

        # Filter and structure
        matches = []
        distances = cast(list[list[float]], results.get("distances") or [[]])
        ids = cast(list[list[str]], results.get("ids") or [[]])
        documents = cast(list[list[str]], results.get("documents") or [[]])
        metadatas = cast(list[list[dict[str, Any]]], results.get("metadatas") or [[]])

        for i, distance in enumerate(distances[0]):
            if distance > self.distance_threshold:
                continue

            match = {
                "id": ids[0][i],
                "content": documents[0][i],
                "metadata": metadatas[0][i],
                "distance": distance,
                "symptom": metadatas[0][i].get("symptom"),
                "root_cause": metadatas[0][i].get("root_cause"),
                "resolution": metadatas[0][i].get("resolution"),
                "citation": self._format_citation(metadatas[0][i]),
            }

            matches.append(match)

        return matches

    def search_docs(
        self,
        query: str,
        platform: str | None = None,
        n_results: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Search documentation entries.

        Args:
            query: Search query
            platform: Optional platform filter
            n_results: Maximum number of results

        Returns:
            List of matching doc sections
        """
        collection = self.get_or_create_collection()

        # Build where filter using $and for multiple conditions
        conditions = [
            {"verification_status": "verified"},
            {"entry_type": "doc"},
        ]

        if platform:
            conditions.append({"platform": platform.lower()})

        where: Any = {"$and": conditions} if len(conditions) > 1 else conditions[0]

        # Query
        results = cast(
            dict[str, Any],
            collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where,
                include=["documents", "metadatas", "distances"],
            ),
        )

        # Filter and structure
        matches = []
        distances = cast(list[list[float]], results.get("distances") or [[]])
        ids = cast(list[list[str]], results.get("ids") or [[]])
        documents = cast(list[list[str]], results.get("documents") or [[]])
        metadatas = cast(list[list[dict[str, Any]]], results.get("metadatas") or [[]])

        for i, distance in enumerate(distances[0]):
            if distance > self.distance_threshold:
                continue

            match = {
                "id": ids[0][i],
                "content": documents[0][i],
                "metadata": metadatas[0][i],
                "distance": distance,
                "doc_title": metadatas[0][i].get("doc_title"),
                "section": metadatas[0][i].get("section"),
                "citation": self._format_citation(metadatas[0][i]),
            }

            matches.append(match)

        return matches

    def _format_citation(self, metadata: dict[str, Any]) -> str:
        """
        Format a citation for a knowledge entry.

        Args:
            metadata: Entry metadata

        Returns:
            Formatted citation string
        """
        source_path = metadata.get("source_path", "unknown")
        entry_type = metadata.get("entry_type", "unknown")

        if entry_type == "gotcha":
            symptom = metadata.get("symptom", "Unknown issue")
            return f"Gotcha: {symptom} ({source_path})"
        elif entry_type == "doc":
            doc_title = metadata.get("doc_title", "Documentation")
            section = metadata.get("section", "")
            if section:
                return f"{doc_title} - {section} ({source_path})"
            return f"{doc_title} ({source_path})"
        else:
            return f"Source: {source_path}"

    def get_stats(self) -> dict[str, Any]:
        """
        Get knowledge base statistics.

        Returns:
            Statistics dictionary
        """
        collection = self.get_or_create_collection()

        # Get all entries
        results = cast(dict[str, Any], collection.get(include=["metadatas"]))

        metadata_rows = cast(list[dict[str, Any]], results.get("metadatas") or [])
        total = len(cast(list[str], results.get("ids") or []))

        # Count by type
        gotchas = sum(1 for m in metadata_rows if m.get("entry_type") == "gotcha")
        docs = sum(1 for m in metadata_rows if m.get("entry_type") == "doc")

        # Count by platform
        platforms: dict[str, int] = {}
        for metadata in metadata_rows:
            platform = metadata.get("platform", "unknown")
            platform_key = str(platform)
            platforms[platform_key] = platforms.get(platform_key, 0) + 1

        # Count verified
        verified = sum(1 for m in metadata_rows if m.get("verification_status") == "verified")

        return {
            "total_entries": total,
            "gotchas": gotchas,
            "docs": docs,
            "verified": verified,
            "by_platform": platforms,
            "distance_threshold": self.distance_threshold,
            "chroma_dir": str(self.chroma_dir),
        }

    def reset_collection(self) -> None:
        """
        Delete the knowledge base collection.

        Use with caution - requires rebuild after.
        """
        try:
            self.client.delete_collection("knowledge_base")
            self.collection = None
        except Exception:
            pass

    def close(self) -> None:
        """
        Close the Chroma client and release resources.

        Important for Windows to avoid file locking issues.
        """
        self.collection = None
        if hasattr(self.client, "close"):
            self.client.close()
