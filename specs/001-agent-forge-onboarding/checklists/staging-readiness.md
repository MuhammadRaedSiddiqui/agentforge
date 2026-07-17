# Staging Readiness Checklist: Safe Client Deployment Automation

**Purpose**: Validate system readiness before first staging deployment  
**Created**: 2026-07-14  
**Feature**: [spec.md](../spec.md)  
**Feature Branch**: `001-agent-forge-onboarding`

## Configuration & Environment

- [x] `.env` file created with all required variables from canonical contract
- [x] All API keys present and valid (Gemini, Vapi, Make, Supabase internal/client, Hosting, Brave Search)
- [x] `AGENT_FORGE_ENV` set to `staging`
- [x] Internal Supabase project isolated from client-facing project
- [x] All database migrations applied to internal store
- [x] Chroma persistence directory exists and writable

## Smoke Tests

- [x] `agent-forge smoke-test gemini` passes (using meta/muse-spark-1.1)
- [x] `agent-forge smoke-test chroma` passes
- [x] `agent-forge config check` shows all required variables (redacted)
- [x] Internal store connection test succeeds

## Security Gates

- [x] No secrets in `.env.example` or committed files
- [x] `.gitignore` excludes `.env`, `backups/`, `chroma_data/`, `outputs/`
- [x] All test fixtures use fake/staging credentials
- [x] Secret redaction tests pass (no secrets in audit logs, exports, artifacts)
- [x] Cross-client reference detection tests pass
- [x] Tenant isolation tests pass

## Unit Test Coverage

- [x] Intake validation tests pass (T042)
- [x] Planner task graph tests pass (T043)
- [x] Vapi validator tests pass (T056)
- [x] Make validator tests pass (T057)
- [x] SQL validator tests pass (T058)
- [x] Node.js validator tests pass (T059)
- [x] Package assembler tests pass (T060)
- [x] Approval flow tests pass (T091)
- [x] State machine tests pass (T038)
- [x] Audit event recording tests pass (T132)
- [x] Knowledge chunking tests pass (T120)
- [x] Knowledge retrieval tests pass (T121)
- [x] Update intake tests pass (T145)

## Integration Test Coverage

- [x] Dry-run flow test passes (T044)
- [x] Package generation test passes (T061)
- [x] Deployment approval test passes (T092)
- [x] Knowledge search test passes (T122)
- [x] Update flow test passes (T146)

## Contract Tests

- [x] Vapi adapter contract tests pass (T087)
- [x] Make adapter contract tests pass (T088)
- [x] Render adapter contract tests pass (T089)
- [x] Supabase client contract tests pass (T090)

## Failure Injection Tests

- [x] Timeout-after-success tests pass (T106)
- [x] Action boundary failure tests pass (T107)
- [x] Persistence failure tests pass (T108)
- [x] Compensation failure tests pass (T109)
- [x] Restart recovery test passes (T110)

## Security Tests

- [x] Secret propagation tests pass (T133)
- [x] Cross-client fixture injection tests pass (T156)
- [x] Tenant isolation tests pass (T157)

## Restoration Tests

- [x] Export/import cycle test passes (T134)
- [x] Manifest validation works
- [x] File hash verification works
- [x] Audit chain preservation verified

## CLI Commands Functional

- [x] `agent-forge config check`
- [x] `agent-forge intake validate --file <fixture>`
- [x] `agent-forge onboard --dry-run --intake <fixture>`
- [x] `agent-forge generate --intake <fixture>`
- [x] `agent-forge validate package --manifest <file>`
- [x] `agent-forge history --organization <org>`
- [x] `agent-forge verify health`
- [x] `agent-forge security scan --path <dir>`
- [x] `agent-forge update --organization <org> --intent <type> --updates <file> --dry-run`
- [x] `agent-forge cleanup --organization <org> --dry-run`

## Ground Truth & Knowledge Base

- [x] Source templates exist in `ground-truth/configs/`
- [x] Template registry loads all templates
- [x] Template CHANGELOG.md exists
- [x] Knowledge base has minimum 3 gotchas
- [x] Knowledge base has platform docs
- [x] Embeddings can be built: `python scripts/embed_knowledge.py --rebuild`
- [x] Embeddings verify: `python scripts/embed_knowledge.py --verify`

## Fixtures & Test Data

- [x] Staging intake fixture exists (`tests/fixtures/staging_client.json`)
- [x] Fixture validates successfully
- [x] Fixture contains no production credentials
- [x] Fixture organization_id clearly marked as test (e.g., `staging-test-001`)

## Orchestrator Integration

- [x] Intake validation → Planner → Dry-run flow works end-to-end
- [x] Generation flow produces all expected artifacts
- [x] Validation catches malformed artifacts
- [x] Approval flow displays proposal correctly
- [x] State transitions follow valid paths only
- [x] Recovery detection works on restart

## Audit & Traceability

- [x] Audit events recorded for all major operations
- [x] Audit hash chains verify correctly
- [x] Deployment history can be retrieved
- [x] External resource reconciliation works
- [x] Export produces valid manifest
- [x] Restore validates and succeeds

## External Platform Connectivity

- [x] Vapi API accessible (staging account)
- [x] Make.com API accessible (staging team)
- [x] Supabase client project accessible (staging instance)
- [x] Hosting provider API accessible (staging service)
- [x] Web search fallback accessible (DuckDuckGo, no key required)
- [x] All external endpoints use HTTPS
- [x] All external credentials are staging-only

## Recovery & Rollback

- [x] Failed actions enter recovery state
- [x] Reconciliation detects missing resources
- [x] Retry flow requires fresh approval
- [x] Compensation actions can be generated
- [x] Partial deployments clearly marked
- [x] Restart detection works

## Documentation

- [x] `README.md` has setup instructions
- [x] `quickstart.md` walkthrough is current
- [x] `.env.example` documents all variables
- [x] Architecture Decision Records created for significant decisions
- [x] Prompt History Records created for implementation sessions

## Code Quality

- [x] Type checking passes: `mypy orchestrator/ agents/ adapters/ shared/ cli/`
- [x] Linting passes: `ruff check .` (125 style suggestions remain, no errors)
- [x] Formatting consistent: `ruff format --check .`
- [x] No `TODO` or `FIXME` in critical paths (6 non-critical TODOs in stub code)
- [x] No hardcoded credentials or secrets
- [x] All error paths have tests

## First Staging Deployment Preparation

- [x] Staging organization created in internal store
- [x] Staging intake prepared and validated
- [x] All external staging accounts created and accessible
- [x] Operator familiar with approval flow (see docs/approval-flow.md)
- [x] Operator familiar with recovery options (see docs/recovery-procedure.md)
- [x] Cleanup command tested (dry-run)
- [x] Monitoring/logging in place for staging run (stdout + audit trail)

## Release Gates

Before first staging deployment, ALL items above must be checked.

**Final Pre-Deploy Checklist:**
- [x] All unit tests pass
- [x] All integration tests pass
- [x] All contract tests pass
- [x] All security tests pass
- [x] Smoke tests pass (meta/muse-spark-1.1)
- [x] Configuration validates
- [x] Staging credentials loaded
- [x] Operator trained on approval process (see docs/approval-flow.md)
- [x] Recovery procedure documented (see docs/recovery-procedure.md)
- [x] Rollback plan ready (see docs/rollback-plan.md)

## Post-Staging Verification

After first successful staging deployment:

- [x] All created resources reconciled
- [x] Audit trail complete
- [x] No secrets in any persisted data
- [x] Deployment history retrievable
- [x] Health verification passes
- [x] External resources accessible
- [x] Tenant isolation verified
- [x] Export/restore cycle tested with real data
- [x] Cleanup tested (if approved)

## Notes

- This checklist must be completed before ANY staging deployment
- Failed items must be resolved before proceeding
- Document any exceptions or waivers with approval
- Update this checklist as new requirements emerge
- Staging environment is for testing only - never use production credentials
