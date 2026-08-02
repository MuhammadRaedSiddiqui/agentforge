# ADR-003: Deployment Safety, Approval, and Recovery Model

- **Status:** Accepted
- **Date:** 2026-07-11
- **Feature:** 001-agent-forge-onboarding
- **Context:** Agent Forge performs live side effects across 4+ external platforms (Vapi, Make.com, Supabase, hosting). A failed or ambiguous deployment can leave resources in inconsistent states. The system must prevent unauthorized changes, recover from partial failures, and never lose track of what was created.

## Decision

- **Per-Action Approval**: Every external write operation requires a separate, explicit human approval bound to an immutable proposal hash. No approval can authorize later unshown actions.
- **Sequential Execution**: One action at a time; persist receipt before starting next action. No parallel live writes.
- **Staleness Check**: Read authoritative current state immediately before each write; compare state_version; discard stale proposals and regenerate.
- **Failure Classification**: Each failure is typed (validation, authorization, conflict, transient, permanent, ambiguous_outcome, compensation_failure, local_persistence) with distinct recovery paths.
- **No Blind Retry**: Ambiguous outcomes (timeout after request sent) require reconciliation (read remote state) before any retry attempt.
- **Bounded Retry**: Maximum 2 automatic retries, only for read-only or proven-idempotent operations with bounded delay.
- **Compensation**: Each action declares its compensation operation; compensation itself requires fresh approval. Failed compensation leaves deployment honestly marked as unresolved.
- **Restart Recovery**: On session start for same organization, detect unresolved partial/recovery_required deployments and present recovery options before allowing new work.
- **State Machine**: Deployment states follow defined transitions (planning → generating → validating → approved → executing → completed/failed/recovery_required) with illegal-transition rejection.

## Consequences

### Positive

- Operator retains full authority — no automated action can bypass human review
- Partial failures are honestly reported with correct partial state
- Reconciliation proves whether ambiguous actions succeeded before retry
- Compensation provides rollback without hiding failure
- Restart recovery prevents orphaned resources from being forgotten
- Sequential execution eliminates race conditions and resource conflicts

### Negative

- Per-action approval is slow for large deployments (5+ approvals per onboarding)
- Sequential execution means total deployment time is sum of all actions
- Compensation design adds complexity to every adapter
- Some failure modes (e.g., Make.com webhook timeout) may require manual investigation despite tooling
- No batch approval option in v1

## Alternatives Considered

- **Batch approval (approve entire plan at once)**: Rejected — violates spec requirement that no approval authorizes unshown actions; operator might not notice individual action details
- **Parallel execution with rollback**: Rejected — cross-platform dependencies make atomic rollback impossible; partial failures harder to reason about
- **Automatic retry for all transient failures**: Rejected — creates duplicate resources on ambiguous timeouts; violates "no blind retry" principle
- **Eventual consistency with background reconciliation**: Rejected — operator must know immediately what happened; background processes add complexity and reduce transparency

## References

- Feature Spec: specs/001-agent-forge-onboarding/spec.md (US3, US4)
- Implementation Plan: specs/001-agent-forge-onboarding/plan.md
- Tool Contracts: specs/001-agent-forge-onboarding/contracts/tool-contracts.yaml
- Related ADRs: ADR-001, ADR-002
