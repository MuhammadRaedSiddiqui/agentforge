"""
Information agent tools for troubleshooting and diagnosis.

T129: Implement information agent tools (search_knowledge, search_web_fallback,
      propose_new_knowledge)
"""

from typing import Any


def search_knowledge(
    query: str,
    platform: str | None = None,
    verified_only: bool = True,
) -> dict[str, Any]:
    """
    Search verified internal knowledge base.

    This is the primary troubleshooting tool. Always try this first before
    external search.

    Args:
        query: Problem description or search query
        platform: Optional platform filter (vapi, make, supabase, render)
        verified_only: Only return verified entries (default True)

    Returns:
        Dictionary with matches and metadata
    """
    from agents.information_agent.rag import KnowledgeRetrieval

    retrieval = KnowledgeRetrieval()

    # Search knowledge base
    matches = retrieval.search_knowledge(
        query=query,
        verified_only=verified_only,
        n_results=5,
    )

    # Filter by platform if specified
    if platform:
        matches = [
            m for m in matches if m["metadata"].get("platform", "").lower() == platform.lower()
        ]

    return {
        "found": len(matches) > 0,
        "count": len(matches),
        "matches": matches,
        "source": "verified_internal_knowledge",
    }


def search_web_fallback(
    query: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Fallback to external web search when internal knowledge doesn't have answer.

    IMPORTANT: Results from this are UNVERIFIED and must be clearly labeled.

    Args:
        query: Search query
        context: Optional context (platform, error message, etc.)

    Returns:
        Dictionary with search results marked as unverified
    """
    from adapters.brave_search import BraveSearchAdapter

    adapter = BraveSearchAdapter()

    # Enhance query with context if available
    enhanced_query = query
    if context:
        if context.get("platform"):
            enhanced_query = f"{context['platform']} {query}"
        if context.get("error_type"):
            enhanced_query = f"{enhanced_query} {context['error_type']}"

    # Perform search
    try:
        receipt = adapter.web_search(
            query=enhanced_query,
            count=5,
        )
        result_list = receipt.response_data.get("results", [])

        return {
            "found": len(result_list) > 0,
            "count": len(result_list),
            "results": result_list,
            "source": "external_web_search",
            "verification_status": "unverified",
            "warning": "These results are from external sources and have not been verified. Use with caution and verify independently.",
        }

    except Exception as e:
        return {
            "found": False,
            "count": 0,
            "results": [],
            "source": "external_web_search",
            "error": str(e),
            "warning": "External search failed. Unable to provide unverified fallback.",
        }


def propose_new_knowledge(
    symptom: str,
    root_cause: str,
    resolution: str,
    platform: str,
    topic: str,
) -> dict[str, Any]:
    """
    Propose a new knowledge entry for human review with duplicate checking.

    New knowledge entries require human approval before being marked as verified.
    This function checks for similar existing gotchas before proposing.

    Args:
        symptom: Problem symptom
        root_cause: Root cause explanation
        resolution: Resolution steps
        platform: Platform (vapi, make, supabase, render)
        topic: Topic category

    Returns:
        Dictionary with proposal details and duplicate check results
    """
    import json
    from datetime import UTC, datetime
    from pathlib import Path

    from agents.information_agent.rag import KnowledgeRetrieval

    # Step 1: Check for duplicates
    retrieval = KnowledgeRetrieval()
    duplicate_check = retrieval.search_knowledge(
        query=f"{platform} {topic} {symptom}",
        verified_only=True,
        n_results=3,
    )

    # Flag potential duplicates (similarity > 0.75)
    potential_duplicates = [
        match for match in duplicate_check
        if match.get("similarity", 0) > 0.75
    ]

    # Step 2: Create proposal structure
    proposal = {
        "symptom": symptom,
        "root_cause": root_cause,
        "resolution": resolution,
        "platform": platform,
        "topic": topic,
        "proposed_at": datetime.now(UTC).isoformat(),
        "verification_status": "proposed",
        "requires_approval": True,
        "duplicate_check": {
            "performed": True,
            "potential_duplicates": len(potential_duplicates),
            "similar_gotchas": [
                {
                    "id": match["id"],
                    "similarity": match["similarity"],
                    "source": match["metadata"].get("source", "unknown"),
                }
                for match in potential_duplicates
            ],
        },
    }

    # Step 3: Save to proposals directory
    proposals_dir = Path("knowledge-base/proposals")
    proposals_dir.mkdir(parents=True, exist_ok=True)

    # Generate filename from symptom
    filename_slug = symptom.lower()[:50].replace(" ", "-").replace("/", "-")
    # Remove non-alphanumeric characters
    filename_slug = "".join(c if c.isalnum() or c == "-" else "" for c in filename_slug)
    proposal_file = proposals_dir / f"{filename_slug}.json"

    # Handle filename collisions
    counter = 1
    while proposal_file.exists():
        proposal_file = proposals_dir / f"{filename_slug}-{counter}.json"
        counter += 1

    # Save proposal
    with open(proposal_file, "w", encoding="utf-8") as f:
        json.dump(proposal, f, indent=2)

    return {
        "status": "proposed",
        "proposal_file": str(proposal_file),
        "duplicate_check": proposal["duplicate_check"],
        "message": f"Knowledge proposal saved to {proposal_file}. "
                   f"Found {len(potential_duplicates)} potential duplicate(s). "
                   "Requires human approval before becoming verified.",
        "next_steps": [
            "Review potential duplicates (if any)",
            "Human reviewer should verify accuracy",
            "Use 'agent-forge gotcha review' to approve or reject",
            "Embeddings will be rebuilt automatically after approval",
        ],
    }


def search_by_symptom(
    symptom: str,
    platform: str | None = None,
) -> dict[str, Any]:
    """
    Search for gotchas by symptom description.

    Optimized for troubleshooting - searches gotcha entries specifically.

    Args:
        symptom: Problem symptom description
        platform: Optional platform filter

    Returns:
        Dictionary with matching gotchas
    """
    from agents.information_agent.rag import KnowledgeRetrieval

    retrieval = KnowledgeRetrieval()

    # Search gotchas
    matches = retrieval.search_by_symptom(
        symptom=symptom,
        platform=platform,
        n_results=3,
    )

    return {
        "found": len(matches) > 0,
        "count": len(matches),
        "gotchas": matches,
        "source": "verified_internal_gotchas",
    }


def get_platform_documentation(
    platform: str,
    topic: str | None = None,
) -> dict[str, Any]:
    """
    Get documentation for a specific platform.

    Args:
        platform: Platform name (vapi, make, supabase, render)
        topic: Optional topic to search within docs

    Returns:
        Dictionary with documentation sections
    """
    from agents.information_agent.rag import KnowledgeRetrieval

    retrieval = KnowledgeRetrieval()

    # Search docs for platform
    query = topic if topic else f"{platform} guide"

    matches = retrieval.search_docs(
        query=query,
        platform=platform,
        n_results=5,
    )

    return {
        "found": len(matches) > 0,
        "count": len(matches),
        "sections": matches,
        "platform": platform,
        "source": "verified_internal_documentation",
    }


def get_knowledge_stats() -> dict[str, Any]:
    """
    Get statistics about the knowledge base.

    Returns:
        Dictionary with knowledge base statistics
    """
    from agents.information_agent.rag import KnowledgeRetrieval

    retrieval = KnowledgeRetrieval()
    return retrieval.get_stats()
