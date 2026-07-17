"""
Information agent for troubleshooting and diagnosis.

T128: Implement information agent (verified-first lookup, threshold-configured
      fallback to Brave search, clear labeling of unverified results)
T130: Implement knowledge approval flow
"""

from typing import Any

from agents.information_agent import tools


class InformationAgent:
    """
    Information agent for troubleshooting and providing diagnostic guidance.

    Implements verified-first knowledge retrieval with clearly-labeled
    external fallback.
    """

    def __init__(self, fallback_enabled: bool = True):
        """
        Initialize information agent.

        Args:
            fallback_enabled: Allow fallback to external search if True
        """
        self.fallback_enabled = fallback_enabled

    def diagnose(
        self,
        problem_description: str,
        platform: str | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        """
        Diagnose a problem using verified knowledge first, external fallback second.

        This is the main entry point for troubleshooting.

        Args:
            problem_description: Description of the problem
            platform: Optional platform filter
            error_message: Optional error message

        Returns:
            Diagnosis result with sources clearly labeled
        """
        diagnosis: dict[str, Any] = {
            "query": problem_description,
            "platform": platform,
            "verified_results": None,
            "fallback_results": None,
            "recommendation": None,
        }

        # Step 1: Search verified internal knowledge
        verified_results = tools.search_knowledge(
            query=problem_description,
            platform=platform,
            verified_only=True,
        )

        diagnosis["verified_results"] = verified_results

        # If we found verified results, use them
        if verified_results["found"]:
            diagnosis["recommendation"] = self._format_verified_recommendation(verified_results)
            diagnosis["source"] = "verified_internal_knowledge"
            diagnosis["confidence"] = "high"
            return diagnosis

        # Step 2: Try symptom-specific search
        symptom_results = tools.search_by_symptom(
            symptom=problem_description,
            platform=platform,
        )

        if symptom_results["found"]:
            diagnosis["verified_results"] = symptom_results
            diagnosis["recommendation"] = self._format_gotcha_recommendation(symptom_results)
            diagnosis["source"] = "verified_internal_gotchas"
            diagnosis["confidence"] = "high"
            return diagnosis

        # Step 3: Fallback to external search if enabled
        if self.fallback_enabled:
            context = {
                "platform": platform,
                "error_type": self._classify_error_type(error_message) if error_message else None,
            }

            fallback_results = tools.search_web_fallback(
                query=problem_description,
                context=context,
            )

            diagnosis["fallback_results"] = fallback_results
            diagnosis["recommendation"] = self._format_fallback_recommendation(fallback_results)
            diagnosis["source"] = "external_web_search"
            diagnosis["confidence"] = "low"
            diagnosis["warning"] = (
                "⚠️  No verified internal knowledge found. Using unverified external sources."
            )

            return diagnosis

        # No results found
        diagnosis["recommendation"] = {
            "status": "no_information_available",
            "message": "No verified knowledge found for this problem.",
            "next_steps": [
                "Check platform documentation directly",
                "Review recent error logs",
                "Consider proposing this as new knowledge after resolution",
            ],
        }
        diagnosis["source"] = "none"
        diagnosis["confidence"] = "none"

        return diagnosis

    def get_documentation(
        self,
        platform: str,
        topic: str | None = None,
    ) -> dict[str, Any]:
        """
        Get verified documentation for a platform.

        Args:
            platform: Platform name
            topic: Optional topic within platform

        Returns:
            Documentation result
        """
        docs = tools.get_platform_documentation(
            platform=platform,
            topic=topic,
        )

        return {
            "platform": platform,
            "topic": topic,
            "documentation": docs,
            "source": "verified_internal_documentation",
        }

    def propose_knowledge(
        self,
        symptom: str,
        root_cause: str,
        resolution: str,
        platform: str,
        topic: str,
    ) -> dict[str, Any]:
        """
        Propose new knowledge entry for human approval.

        Implements T130: Knowledge approval flow with duplicate/contradiction
        check and human approval requirement.

        Args:
            symptom: Problem symptom
            root_cause: Root cause explanation
            resolution: Resolution steps
            platform: Platform
            topic: Topic category

        Returns:
            Proposal result
        """
        # Check for duplicates
        existing = tools.search_by_symptom(symptom=symptom, platform=platform)

        if existing["found"]:
            return {
                "status": "duplicate_detected",
                "message": f"Found {existing['count']} existing entries with similar symptoms.",
                "existing_entries": existing["gotchas"],
                "recommendation": "Review existing entries before creating new one.",
            }

        # Check for contradictions (similar symptoms but different resolutions)
        # This would require more sophisticated comparison in production
        # For now, just flag for human review

        # Create proposal
        proposal = tools.propose_new_knowledge(
            symptom=symptom,
            root_cause=root_cause,
            resolution=resolution,
            platform=platform,
            topic=topic,
        )

        proposal["requires_human_approval"] = True
        proposal["approval_steps"] = [
            "1. Human reviewer verifies accuracy",
            "2. Check against existing knowledge for duplicates/contradictions",
            "3. Convert to proper Markdown format if approved",
            "4. Rebuild embeddings to make searchable",
        ]

        return proposal

    def _format_verified_recommendation(
        self,
        results: dict[str, Any],
    ) -> dict[str, Any]:
        """Format recommendation from verified results."""
        matches = results["matches"]

        if not matches:
            return {"status": "no_matches"}

        # Use top match
        top_match = matches[0]

        return {
            "status": "verified_solution_found",
            "confidence": "high",
            "solution": top_match["content"],
            "citation": top_match["citation"],
            "similarity": top_match["similarity"],
            "additional_matches": len(matches) - 1,
        }

    def _format_gotcha_recommendation(
        self,
        results: dict[str, Any],
    ) -> dict[str, Any]:
        """Format recommendation from gotcha results."""
        gotchas = results["gotchas"]

        if not gotchas:
            return {"status": "no_gotchas"}

        # Use top gotcha
        top_gotcha = gotchas[0]

        return {
            "status": "gotcha_found",
            "confidence": "high",
            "symptom": top_gotcha["symptom"],
            "root_cause": top_gotcha["root_cause"],
            "resolution": top_gotcha["resolution"],
            "citation": top_gotcha["citation"],
            "similarity": 1.0 - top_gotcha["distance"],
            "additional_matches": len(gotchas) - 1,
        }

    def _format_fallback_recommendation(
        self,
        results: dict[str, Any],
    ) -> dict[str, Any]:
        """Format recommendation from external fallback results."""
        if not results["found"]:
            return {
                "status": "no_fallback_results",
                "message": "External search also found no results.",
            }

        return {
            "status": "unverified_results_found",
            "confidence": "low",
            "warning": results["warning"],
            "results": results["results"],
            "verification_status": "unverified",
            "recommendation": "Verify these external results independently before applying.",
        }

    def _classify_error_type(self, error_message: str) -> str:
        """Classify error type from message."""
        error_lower = error_message.lower()

        if "timeout" in error_lower or "timed out" in error_lower:
            return "timeout"
        elif "connection" in error_lower or "network" in error_lower:
            return "connection"
        elif "permission" in error_lower or "unauthorized" in error_lower:
            return "authorization"
        elif "not found" in error_lower or "404" in error_lower:
            return "not_found"
        elif "conflict" in error_lower or "409" in error_lower:
            return "conflict"
        else:
            return "unknown"

    def get_stats(self) -> dict[str, Any]:
        """Get knowledge base statistics."""
        return tools.get_knowledge_stats()
