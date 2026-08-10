"""
Gotcha proposal approval workflow.

Handles review and approval of proposed gotchas from agents.
"""

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def list_proposals() -> list[dict[str, Any]]:
    """
    List all pending gotcha proposals.

    Returns:
        List of proposal dictionaries with file paths
    """
    proposals_dir = Path("knowledge-base/proposals")
    if not proposals_dir.exists():
        return []

    proposals = []
    for proposal_file in proposals_dir.glob("*.json"):
        try:
            with open(proposal_file, encoding="utf-8") as f:
                proposal = json.load(f)
                proposal["_file"] = str(proposal_file)
                proposals.append(proposal)
        except Exception as e:
            print(f"Warning: Failed to load {proposal_file}: {e}")

    return proposals


def convert_proposal_to_gotcha(proposal: dict[str, Any]) -> str:
    """
    Convert a proposal JSON to gotcha markdown format.

    Args:
        proposal: Proposal dictionary

    Returns:
        Markdown content for gotcha file
    """
    symptom = proposal.get("symptom", "Unknown symptom")
    root_cause = proposal.get("root_cause", "No root cause provided")
    resolution = proposal.get("resolution", "No resolution provided")
    platform = proposal.get("platform", "unknown")
    topic = proposal.get("topic", "general")
    proposed_at = proposal.get("proposed_at", datetime.now(UTC).isoformat())

    # Generate title from symptom
    title = f"Gotcha: {symptom}"

    # Format markdown
    markdown = f"""# {title}

**Platform:** {platform.title()}
**Topic:** {topic.title()}
**Symptom:** {symptom}
**Verification Status:** Verified
**Approved By:** human
**Approved At:** {datetime.now(UTC).strftime('%Y-%m-%d')}

## Root Cause

{root_cause}

## Resolution

{resolution}

## Detection

```python
# Add detection code here based on the symptom
# Example: Check for specific error conditions, API responses, or configuration issues
```

## Prevention

- Follow best practices for {platform} platform
- Validate configuration before deployment
- Test thoroughly in staging environment
- Monitor for similar symptoms in production

## Common Causes

- Configuration errors
- API changes or version mismatches
- Missing or invalid credentials
- Environment-specific issues

## Related Issues

- See other {platform} gotchas in this directory
- Check platform documentation for updates

## References

- {platform.title()} Documentation: (add link)
- Agent Forge: (add relevant file references)
- Research Date: {datetime.now(UTC).strftime('%Y-%m-%d')}
- Proposed At: {proposed_at[:10]}
"""

    return markdown


def approve_proposal(proposal: dict[str, Any]) -> dict[str, Any]:
    """
    Approve a gotcha proposal and convert it to markdown.

    Args:
        proposal: Proposal dictionary with _file key

    Returns:
        Dictionary with approval results
    """
    proposal_file = Path(proposal["_file"])
    platform = proposal.get("platform", "unknown")
    symptom = proposal.get("symptom", "unknown-symptom")

    # Generate filename slug
    filename_slug = symptom.lower()[:50].replace(" ", "-")
    filename_slug = "".join(c if c.isalnum() or c == "-" else "" for c in filename_slug)
    filename_slug = f"{platform}-{filename_slug}"

    # Create gotcha file
    gotchas_dir = Path("knowledge-base/gotchas")
    gotchas_dir.mkdir(parents=True, exist_ok=True)

    gotcha_file = gotchas_dir / f"{filename_slug}.md"

    # Handle filename collisions
    counter = 1
    while gotcha_file.exists():
        gotcha_file = gotchas_dir / f"{filename_slug}-{counter}.md"
        counter += 1

    # Convert to markdown and write
    markdown_content = convert_proposal_to_gotcha(proposal)
    gotcha_file.write_text(markdown_content, encoding="utf-8")

    # Delete proposal file
    proposal_file.unlink()

    return {
        "status": "approved",
        "gotcha_file": str(gotcha_file),
        "proposal_file": str(proposal_file),
        "message": f"Approved and saved to {gotcha_file}",
    }


def reject_proposal(proposal: dict[str, Any], reason: str | None = None) -> dict[str, Any]:
    """
    Reject a gotcha proposal.

    Args:
        proposal: Proposal dictionary with _file key
        reason: Optional rejection reason

    Returns:
        Dictionary with rejection results
    """
    proposal_file = Path(proposal["_file"])

    # Log rejection reason if provided
    if reason:
        rejection_log = Path("knowledge-base/proposals/rejected.log")
        with open(rejection_log, "a", encoding="utf-8") as f:
            f.write(
                f"{datetime.now(UTC).isoformat()} | "
                f"{proposal_file.name} | "
                f"Reason: {reason}\n"
            )

    # Delete proposal file
    proposal_file.unlink()

    return {
        "status": "rejected",
        "proposal_file": str(proposal_file),
        "reason": reason,
        "message": f"Rejected and deleted {proposal_file.name}",
    }


def rebuild_embeddings() -> dict[str, Any]:
    """
    Rebuild knowledge base embeddings after approvals.

    Returns:
        Dictionary with rebuild results
    """
    try:
        # Run embed_knowledge.py script
        result = subprocess.run(
            ["python", "scripts/embed_knowledge.py", "--rebuild"],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode == 0:
            return {
                "status": "success",
                "message": "Embeddings rebuilt successfully",
                "output": result.stdout,
            }
        else:
            return {
                "status": "error",
                "message": "Failed to rebuild embeddings",
                "error": result.stderr,
            }

    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "message": "Embedding rebuild timed out after 120 seconds",
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to rebuild embeddings: {e}",
        }
