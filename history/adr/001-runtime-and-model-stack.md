# ADR-001: Runtime and Model Provider Stack

- **Status:** Accepted
- **Date:** 2026-07-11
- **Feature:** 001-agent-forge-onboarding
- **Context:** Agent Forge needs a runtime, model provider, and orchestration framework that supports structured tool calling, sequential deployment, and local-first execution for a single operator.

## Decision

- **Runtime**: Python 3.11+ CLI application, local-only execution
- **Agent Framework**: OpenAI Agents SDK for delegation and tool invocation
- **Model Provider**: Flexible via `MODEL_PROVIDER` env var — supports Gemini 2.5 Pro, Meta muse-spark-1.1, or any OpenAI-compatible API through a unified `ModelWrapper`
- **Model Role**: All model output is untrusted proposed data; deterministic validators enforce correctness
- **Interface**: Interactive CLI with `--dry-run` for non-mutating planning

## Consequences

### Positive

- Single language (Python) for entire application reduces complexity
- OpenAI-compatible API allows swapping model providers without code changes
- Local-first means no infrastructure to manage, no multi-tenant concerns
- Sequential execution simplifies state management and debugging
- Model-agnostic design proved valuable when Gemini quota was exhausted (switched to muse-spark-1.1 with zero code changes)

### Negative

- No web UI limits accessibility to terminal-comfortable operators
- Single-threaded sequential execution means long deployments block the terminal
- OpenAI Agents SDK is early-stage (v0.0.4) with potential breaking changes
- Python performance adequate for orchestration but not for high-throughput

## Alternatives Considered

- **Node.js/TypeScript**: Rejected — existing server.js is a deployment target, not the orchestrator; mixing concerns would complicate the codebase
- **LangChain/LangGraph**: Rejected — heavier abstraction with more magic, harder to audit deterministic validation boundaries
- **Direct API calls without agent framework**: Rejected — would require reimplementing tool dispatch and multi-turn management
- **Cloud-hosted with web UI**: Rejected — scope creep for v1; local-first is safer and simpler for single-operator use

## References

- Feature Spec: specs/001-agent-forge-onboarding/spec.md
- Implementation Plan: specs/001-agent-forge-onboarding/plan.md
- Related ADRs: ADR-002, ADR-003
