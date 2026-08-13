import argparse
import sys


def cmd_gotcha_review(args: argparse.Namespace) -> int:
    """
    Review and approve/reject gotcha proposals.

    Args:
        args: Command arguments

    Returns:
        Exit code (0 for success)
    """
    from cli.gotcha_approval import (
        approve_proposal,
        list_proposals,
        rebuild_embeddings,
        reject_proposal,
    )

    try:
        if args.gotcha_command == "list":
            # List pending proposals
            proposals = list_proposals()

            if not proposals:
                print("No pending gotcha proposals.")
                return 0

            print(f"\n{len(proposals)} pending gotcha proposal(s):\n")
            for i, proposal in enumerate(proposals, 1):
                print(f"[{i}] {proposal.get('platform', 'unknown').upper()} - {proposal.get('symptom', 'No symptom')}")
                print(f"    Topic: {proposal.get('topic', 'unknown')}")
                print(f"    Proposed: {proposal.get('proposed_at', 'unknown')[:10]}")

                # Show duplicate check results
                dup_check = proposal.get("duplicate_check", {})
                if dup_check.get("potential_duplicates", 0) > 0:
                    print(f"    ⚠️  {dup_check['potential_duplicates']} potential duplicate(s) found")

                print(f"    File: {proposal.get('_file', 'unknown')}")
                print()

            print("Use 'agent-forge gotcha approve <number>' or 'agent-forge gotcha reject <number>'")
            return 0

        elif args.gotcha_command == "approve":
            # Approve a proposal
            proposals = list_proposals()

            if not proposals:
                print("No pending gotcha proposals.")
                return 0

            proposal_num = getattr(args, "proposal_number", None)
            if proposal_num is None:
                print("Error: Proposal number required", file=sys.stderr)
                print("Usage: agent-forge gotcha approve <number>", file=sys.stderr)
                return 1

            if proposal_num < 1 or proposal_num > len(proposals):
                print(f"Error: Invalid proposal number. Must be 1-{len(proposals)}", file=sys.stderr)
                return 1

            proposal = proposals[proposal_num - 1]

            # Show proposal details
            print("\nApproving proposal:")
            print(f"  Platform: {proposal.get('platform', 'unknown').upper()}")
            print(f"  Symptom: {proposal.get('symptom', 'unknown')}")
            print(f"  Topic: {proposal.get('topic', 'unknown')}")

            # Show duplicate warnings
            dup_check = proposal.get("duplicate_check", {})
            if dup_check.get("potential_duplicates", 0) > 0:
                print(f"\n  ⚠️  WARNING: {dup_check['potential_duplicates']} potential duplicate(s):")
                for dup in dup_check.get("similar_gotchas", []):
                    print(f"      - {dup['id']} (similarity: {dup['similarity']:.2f})")
                print()

            # Confirm approval unless --yes flag
            if not getattr(args, "yes", False):
                response = input("Approve this proposal? [y/N]: ")
                if response.lower() != "y":
                    print("Cancelled.")
                    return 0

            # Approve
            result = approve_proposal(proposal)
            print(f"✓ {result['message']}")

            # Rebuild embeddings
            if not getattr(args, "no_rebuild", False):
                print("\nRebuilding knowledge base embeddings...")
                rebuild_result = rebuild_embeddings()
                if rebuild_result["status"] == "success":
                    print("✓ Embeddings rebuilt successfully")
                else:
                    print(f"⚠️  Warning: {rebuild_result['message']}", file=sys.stderr)

            return 0

        elif args.gotcha_command == "reject":
            # Reject a proposal
            proposals = list_proposals()

            if not proposals:
                print("No pending gotcha proposals.")
                return 0

            proposal_num = getattr(args, "proposal_number", None)
            if proposal_num is None:
                print("Error: Proposal number required", file=sys.stderr)
                print("Usage: agent-forge gotcha reject <number> [--reason \"...\"]", file=sys.stderr)
                return 1

            if proposal_num < 1 or proposal_num > len(proposals):
                print(f"Error: Invalid proposal number. Must be 1-{len(proposals)}", file=sys.stderr)
                return 1

            proposal = proposals[proposal_num - 1]

            # Show proposal details
            print("\nRejecting proposal:")
            print(f"  Platform: {proposal.get('platform', 'unknown').upper()}")
            print(f"  Symptom: {proposal.get('symptom', 'unknown')}")

            # Get rejection reason
            reason = getattr(args, "reason", None)
            if not reason and not getattr(args, "yes", False):
                reason = input("Rejection reason (optional): ").strip() or None

            # Confirm rejection unless --yes flag
            if not getattr(args, "yes", False):
                response = input("Reject this proposal? [y/N]: ")
                if response.lower() != "y":
                    print("Cancelled.")
                    return 0

            # Reject
            result = reject_proposal(proposal, reason)
            print(f"✓ {result['message']}")

            return 0

        else:
            print("Unknown gotcha command. Use 'list', 'approve', or 'reject'.", file=sys.stderr)
            return 1

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
