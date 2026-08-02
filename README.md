# Agent Forge

Safe client deployment automation. Onboards new clients to voice assistant infrastructure (Vapi, Make.com, Supabase, hosting) through a human-approved, auditable pipeline with failure recovery.

[![CI](https://github.com/MuhammadRaedSiddiqui/agentforge/actions/workflows/ci.yml/badge.svg)](https://github.com/MuhammadRaedSiddiqui/agentforge/actions/workflows/ci.yml)
[![Security Scan](https://github.com/MuhammadRaedSiddiqui/agentforge/actions/workflows/security.yml/badge.svg)](https://github.com/MuhammadRaedSiddiqui/agentforge/actions/workflows/security.yml)

## Features

- **Full onboarding pipeline** — conversational intake to deployed infrastructure in one command
- **Make.com blueprint deployment** — hook-first orchestration deploys complete multi-module scenarios (4-10 modules), not stubs
- **Update/modification flow** — change voice, add capabilities, or modify webhooks without full re-deployment
- **Human approval gates** — every external write requires explicit confirmation
- **Failure recovery** — rollback, reconciliation, and retry with audit trail
- **CI/CD** — GitHub Actions (lint, typecheck, test, secret scanning, Dependabot)

## Prerequisites

- Python 3.11+
- Staging accounts for: Vapi, Make.com, Supabase (2 projects), Render (or hosting provider)
- Docker (optional, for containerized deployment)

## Setup

```bash
# Clone and install
git clone https://github.com/MuhammadRaedSiddiqui/agentforge.git && cd agentforge
pip install -e ".[dev]"

# Or use Make
make install

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
agent-forge config check

# Test model provider connectivity
agent-forge smoke-test gemini

# Test vector store
agent-forge smoke-test chroma

# System health check
agent-forge verify health
```

## Usage

```bash
# Validate a client intake file
agent-forge intake validate --file tests/fixtures/staging_client.json

# Preview onboarding plan (no external changes)
agent-forge onboard --dry-run --intake tests/fixtures/staging_client.json

# Execute deployment with per-action approval
agent-forge onboard --execute --environment staging --intake <file>

# Update existing deployment (dry-run)
agent-forge update --organization <org> --intent update_assistant --updates <file> --dry-run

# Update existing deployment (execute)
agent-forge update --organization <org> --intent update_assistant --updates <file> --execute

# View deployment history
agent-forge history --organization <org>

# Security scan outputs
agent-forge security scan --path outputs/

# Cleanup staging resources (dry-run first)
agent-forge cleanup --organization <org> --dry-run
```

## Development

```bash
# Lint
make lint

# Type check
make typecheck

# Run unit + contract tests
make test

# Run all tests
make test-all

# Lock dependencies
make lock
```

## Running Tests

```bash
# All tests (562 total)
python -m pytest tests/

# By category
python -m pytest tests/unit/                # 321 unit tests
python -m pytest tests/contract/            # 97 contract tests
python -m pytest tests/integration/         # 63 integration tests
python -m pytest tests/security/            # 51 security tests
python -m pytest tests/failure_injection/   # 20 failure injection tests
python -m pytest tests/restoration/         # 10 restoration tests
```

## Docker

```bash
# Build
docker build -t agent-forge .

# Run
docker run --env-file .env agent-forge config check
docker run --env-file .env agent-forge onboard --dry-run --intake /app/tests/fixtures/staging_client.json
```

## Project Structure

```
adapters/         # External platform adapters (Vapi, Make, Supabase, Render, Brave)
agents/           # Specialist agents (vapi, make, supabase, nodejs, information)
cli/              # CLI commands, session management, interactive prompts
config/           # Agent registry, capability map, vendor contracts
ground-truth/     # Source templates and schemas for artifact generation
knowledge-base/   # Verified troubleshooting docs and gotchas
orchestrator/     # Core logic: planner, deployer, state machine, approval, recovery
scripts/          # Operational scripts: embed, export, restore, reconcile
shared/           # Shared contracts: errors, IDs, hashing, redaction
supabase/         # Database migrations (14 tables)
templates/        # Deployment templates (backend server, packages)
tests/            # Test suites by category (562 tests)
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  CLI (cli/main.py)                                      │
│  - onboard --dry-run | --execute                        │
│  - update --intent <type> --execute                     │
└────────────────┬────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────┐
│  Orchestrator                                           │
│  - Planner (task graph from intake)                     │
│  - SelectiveRegenerator (update flow)                   │
│  - MakeScenarioDeployer (hook-first blueprint deploy)   │
│  - Approval gate (human confirms each action)           │
└────────────────┬────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────┐
│  Specialist Agents                                      │
│  - VapiAgent (assistants, tools, phone numbers)         │
│  - MakeAgent (scenarios, hooks, blueprints)             │
│  - SupabaseAgent (schemas, RLS, migrations)             │
│  - NodeJsAgent (backend code generation)                │
└────────────────┬────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────┐
│  Adapters (HTTP clients with retry, audit, receipts)    │
│  - Vapi API    - Make.com API    - Supabase API         │
│  - Render API  - Brave Search API                       │
└─────────────────────────────────────────────────────────┘
```

## Key Design Principles

- **Human approval required** for every external write operation
- **Tenant isolation** enforced at every layer
- **No blind retries** — ambiguous outcomes require reconciliation first
- **Audit trail** with tamper-evident hash chains
- **Secrets never persisted** in artifacts, logs, exports, or model context
- **Hook-first deployment** — Make.com hooks created before scenarios to ensure correct wiring

## Environment Variables

See `.env.example` for the full list. Key variables:

| Variable | Purpose |
|----------|---------|
| `MODEL_PROVIDER` | Model backend: `meta`, `gemini`, or `openai` |
| `MODEL_NAME` | Model ID (e.g., `muse-spark-1.1`) |
| `AGENT_FORGE_ENV` | Must be `staging` (blocks production-looking targets) |
| `SUPABASE_INTERNAL_URL` | Operational store (deployments, audit, state) |
| `SUPABASE_CLIENT_URL` | Client-facing project (tenant data) |
| `MAKE_API_TOKEN` | Make.com API token for scenario deployment |
| `VAPI_API_KEY` | Vapi API key for assistant management |

## Documentation

- `specs/001-agent-forge-onboarding/quickstart.md` — Full staging verification walkthrough
- `specs/001-agent-forge-onboarding/spec.md` — Feature specification
- `specs/001-agent-forge-onboarding/plan.md` — Architecture and technical plan
