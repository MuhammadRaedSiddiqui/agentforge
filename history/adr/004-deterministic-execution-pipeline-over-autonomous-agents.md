# ADR-004: Deterministic Execution Pipeline Over Autonomous Agents

- **Status:** Accepted
- **Date:** 2026-07-23
- **Feature:** 010-conversational-orchestrator
- **Context:** The execution layer (planner → specialist agents → approval → adapters) must reliably deploy configurations across 4+ external platforms with per-action human approval, compensation on failure, and tamper-evident audit. The decision is whether this pipeline should be an autonomous agent loop (where a model decides what to do next) or a deterministic state machine (where code controls the flow and models only generate artifacts).

## Decision

- **Execution model**: Deterministic pipeline controlled by code — the state machine, planner, and approval gate drive the flow; models never decide what action to take next
- **Agent role**: Specialist agents generate artifacts (configs, SQL, diffs) but do not choose their own tasks, order, or whether to proceed
- **Approval**: Code-enforced per-action gates — no model can bypass, weaken, or pre-answer an approval decision
- **Recovery**: Deterministic reconciliation logic checks remote state; model is not asked to "figure out what went wrong"
- **State transitions**: Validated by `DeploymentStateMachine` with an explicit transition table; invalid transitions raise exceptions

## Consequences

### Positive

- Every execution path is testable without invoking a model — the pipeline is code, not prompt-dependent behavior
- Approval gates are guaranteed by the state machine — no prompt injection or model hallucination can skip them
- Recovery is predictable: reconcile → retry or compensate, with bounded retries (max 2)
- Audit trail is complete because every transition is code-logged, not dependent on model "remembering" to log
- Debugging is straightforward: state machine + step counter, not model chain-of-thought

### Negative

- Adding new platform operations requires code changes to the planner and state machine (not just a prompt edit)
- The pipeline cannot adapt to unexpected platform responses the way an autonomous agent might
- Sequential execution means no parallelism across independent platform operations (a conscious trade for simplicity)

## Alternatives Considered

- **Autonomous agent loop (ReAct/AutoGPT pattern)**: A model receives the full context and decides each next step. Rejected because: approval gates cannot be guaranteed by prompting alone; recovery logic is too important for probabilistic behavior; testing becomes prompt-sensitivity testing rather than logic testing; and constitutional Principle II explicitly forbids model self-governance over live state.
- **Hybrid: model plans, code executes**: The model generates the task graph dynamically per deployment. Rejected because: the task graph is deterministic from the intake's enabled capabilities — there is no creative planning needed; and dynamic planning introduces a failure mode where the model "forgets" a required step.
- **OpenAI Agents SDK autonomous mode**: Let the SDK's built-in agent loop manage tool calls. Rejected because: the SDK loop does not enforce per-action approval, does not integrate with the state machine, and cannot be bounded to prevent runaway retries.

## References

- Feature Spec: specs/010-conversational-orchestrator/spec.md
- Implementation Plan: Agent_Forge_Conversational_Implementation_Plan.md (section "What Does Not Change")
- Constitution: Principle II (Deterministic Controls Over Model Judgment), Principle III (Human Authority Over Live State)
- Related ADRs: ADR-001 (runtime stack), ADR-003 (deployment safety and recovery)
