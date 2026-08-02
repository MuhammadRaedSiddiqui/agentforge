# ADR-002: Data Storage and Tenant Isolation

- **Status:** Accepted
- **Date:** 2026-07-11
- **Feature:** 001-agent-forge-onboarding
- **Context:** Agent Forge manages deployment state, audit trails, and client data across multiple external platforms. The system must enforce strict tenant isolation, maintain tamper-evident audit records, and separate operational data from client-facing data.

## Decision

- **Internal Operational Store**: Isolated Supabase project (separate from client data) with 14 tables covering organizations, deployments, sessions, tasks, artifacts, actions, approvals, resources, recovery, audit, and templates
- **Client Database**: Separate Supabase project accessed via allowlisted table operations only
- **Knowledge Index**: Embedded Chroma for vector retrieval; Git-tracked Markdown files are canonical source
- **Audit Trail**: Append-only events with SHA-256 hash chains linking each event to its predecessor
- **Tenant Isolation**: Organization-scoped queries at every layer; cross-client reference detection in all generated artifacts; RLS policies enforced at database level
- **Secrets**: Environment variables only, never persisted in artifacts/logs/exports/model context; redaction enforced by shared utility

## Consequences

### Positive

- Complete separation of concerns: operational state vs. client data vs. derived indexes
- Hash-chained audit is tamper-evident and exportable/restorable
- Supabase provides managed PostgreSQL with RLS without self-hosting
- Cross-client detection prevents artifact contamination
- Export/restore cycle enables disaster recovery and environment cloning

### Negative

- Two Supabase projects means two sets of credentials and two billing accounts
- 14 migration files to manage; schema changes require careful ordering
- Chroma embeddings are derived state that must be rebuilt if source changes
- Append-only audit tables grow without bound (no retention policy yet)

## Alternatives Considered

- **Single Supabase project with schema separation**: Rejected — risk of accidental cross-access; RLS alone insufficient when service role key bypasses it
- **SQLite local database**: Rejected — no remote access for future multi-device, no managed backups, harder to inspect
- **PostgreSQL self-hosted**: Rejected — operational burden inappropriate for single-operator tool
- **File-based JSON state**: Rejected — no transactional guarantees, harder to query, no built-in concurrent access protection

## References

- Feature Spec: specs/001-agent-forge-onboarding/spec.md
- Data Model: specs/001-agent-forge-onboarding/data-model.md
- Implementation Plan: specs/001-agent-forge-onboarding/plan.md
- Related ADRs: ADR-001, ADR-003
