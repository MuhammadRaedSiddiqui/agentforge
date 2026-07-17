# Agent Forge

Safe client deployment automation. Onboards new clients to voice assistant infrastructure (Vapi, Make.com, Supabase, hosting) through a human-approved, auditable pipeline with failure recovery.

## Prerequisites

- Python 3.11+
- Staging accounts for: Vapi, Make.com, Supabase (2 projects), Render (or hosting provider)

## Setup

```bash
# Clone and install
git clone <repo-url> && cd agentforge
pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Edit .env with your staging credentials

# Apply database migrations to internal Supabase project
# Use Supabase Dashboard SQL Editor or: supabase db push

# Build knowledge embeddings
python scripts/embed_knowledge.py --rebuild
```

## Verify Installation

```bash
# Check all environment variables are set
python -m cli.main config check

# Test model provider connectivity
python -m cli.main smoke-test gemini

# Test vector store
python -m cli.main smoke-test chroma

# System health check
python -m cli.main verify health
```

## Usage

```bash
# Validate a client intake file
python -m cli.main intake validate --file tests/fixtures/staging_client.json

# Preview onboarding plan (no external changes)
python -m cli.main onboard --dry-run --intake tests/fixtures/staging_client.json

# Generate deployment package
python -m cli.main generate --intake tests/fixtures/staging_client.json

# Validate generated package
python -m cli.main validate package --manifest outputs/<org>/package_manifest.json

# Execute deployment with per-action approval
python -m cli.main onboard --execute --environment staging --intake <file>

# Update existing deployment
python -m cli.main update --organization <org> --intent update_assistant --updates <file> --dry-run

# View deployment history
python -m cli.main history --organization <org>

# Security scan outputs
python -m cli.main security scan --path outputs/

# Cleanup staging resources (dry-run first)
python -m cli.main cleanup --organization <org> --dry-run
```

## Running Tests

```bash
# All tests
python -m pytest tests/

# By category
python -m pytest tests/unit/           # 230 unit tests
python -m pytest tests/contract/       # 97 contract tests
python -m pytest tests/integration/    # 59 integration tests
python -m pytest tests/security/       # 51 security tests
python -m pytest tests/failure_injection/  # 20 failure injection tests
python -m pytest tests/restoration/    # 10 restoration tests

# Type checking
mypy orchestrator/ agents/ adapters/ shared/ cli/ --ignore-missing-imports

# Linting and formatting
ruff check .
ruff format --check .
```

## Project Structure

```
adapters/         # External platform adapters (Vapi, Make, Supabase, Render, Brave)
agents/           # Specialist agents (vapi, make, supabase, nodejs, information)
cli/              # CLI commands, session management, interactive prompts
config/           # Agent registry, capability map, vendor contracts
ground-truth/     # Source templates and schemas for artifact generation
knowledge-base/   # Verified troubleshooting docs and gotchas
orchestrator/     # Core logic: planner, state machine, approval, recovery, audit
scripts/          # Operational scripts: embed, export, restore, reconcile
shared/           # Shared contracts: errors, IDs, hashing, redaction
supabase/         # Database migrations (14 tables)
tests/            # Test suites by category
```

## Key Design Principles

- **Human approval required** for every external write operation
- **Tenant isolation** enforced at every layer
- **No blind retries** — ambiguous outcomes require reconciliation first
- **Audit trail** with tamper-evident hash chains
- **Secrets never persisted** in artifacts, logs, exports, or model context

## Environment Variables

See `.env.example` for the full list. Key variables:

| Variable | Purpose |
|----------|---------|
| `MODEL_PROVIDER` | Model backend: `meta`, `gemini`, or `openai` |
| `MODEL_NAME` | Model ID (e.g., `muse-spark-1.1`) |
| `AGENT_FORGE_ENV` | Must be `staging` (blocks production-looking targets) |
| `SUPABASE_INTERNAL_URL` | Operational store (deployments, audit, state) |
| `SUPABASE_CLIENT_URL` | Client-facing project (tenant data) |

## Documentation

- `specs/001-agent-forge-onboarding/quickstart.md` — Full staging verification walkthrough
- `specs/001-agent-forge-onboarding/spec.md` — Feature specification
- `specs/001-agent-forge-onboarding/plan.md` — Architecture and technical plan
- `HANDOFF.md` — Implementation handoff and next steps
