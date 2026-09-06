# Agent Forge — Complete System Documentation

## What It Is

Agent Forge is a Python 3.11+ CLI tool that automates the deployment of AI voice agents across multiple platforms. It provisions a complete client stack — voice assistant, automation scenarios, database schema, and backend hosting — through a single intake form, with mandatory human approval before every external side effect.

It exists because deploying a voice agent today requires coordinating four independent platforms (Vapi, Make.com, Supabase, Render), each with its own API, configuration format, and failure modes. Agent Forge removes that coordination burden while keeping a human in the loop for every action that touches the outside world.

---

## What It Does

### Core Capability

Given a client intake JSON (business name, capabilities, voice preferences, scheduling rules), Agent Forge:

1. Validates the intake against a strict schema
2. Plans a deployment task graph
3. Generates platform-specific configuration artifacts from ground-truth templates
4. Validates every generated artifact for correctness and security
5. Proposes each external action one-at-a-time to the operator
6. Executes approved actions sequentially, persisting a receipt before the next action
7. Records an immutable, hash-chained audit trail of every decision

### Platform Integrations

| Platform | What Gets Created | Purpose |
|----------|-------------------|---------|
| **Vapi** | Voice assistant + tools + phone assignment | AI phone agent with model config, voice settings, first message, system prompt |
| **Make.com** | 4 automation scenarios (4-10 modules each) | Webhook-triggered workflows for availability check, booking creation, cancellation, rescheduling |
| **Supabase** | Organization row + migration | Client database schema with RLS policies for tenant isolation |
| **Render** | Environment variable + deploy trigger | Backend hosting configuration and deployment |

### User Stories Supported

1. **New client onboarding** — Full deployment from intake to live resources
2. **Dry-run preview** — See what would be created without touching any platform
3. **Update/modification flow** — Modify an existing deployment (voice, hours, capabilities) without full re-deployment
4. **Deployment history** — Query past deployments by organization
5. **Health verification** — Check all external resources still exist and are accessible
6. **Cleanup/teardown** — Remove all created resources with approval per deletion
7. **Export/restore** — Portable backup of deployment state with hash verification

---

## Tech Stack

### Language & Runtime

- **Python 3.11+** with type hints throughout
- **No web framework** — pure CLI application
- **Entry point**: `agent-forge` command via setuptools `[project.scripts]`
- **Containerized**: Dockerfile with `python:3.11-slim`

### Dependencies (Production)

| Dependency | Role |
|------------|------|
| `openai-agents>=0.0.4` | OpenAI Agents SDK for agent orchestration |
| `openai>=1.60.0` | OpenAI-compatible model API client (used for Gemini, Meta, Bedrock) |
| `chromadb>=0.5.0` | Local vector database for knowledge base |
| `supabase>=2.0.0` | Supabase client SDK |
| `python-dotenv>=1.0.0` | Environment variable loading |
| `requests>=2.31.0` | HTTP client for platform API calls |
| `pyyaml>=6.0.0` | YAML configuration parsing |
| `boto3>=1.34.0` | Amazon Bedrock model access |

### Dependencies (Dev)

| Dependency | Role |
|------------|------|
| `pytest>=8.0.0` | Test framework |
| `pytest-timeout>=2.2.0` | Test timeout enforcement |
| `pytest-mock>=3.12.0` | Mock utilities |
| `ruff>=0.1.0` | Linter and formatter |
| `mypy>=1.7.0` | Static type checker |
| `types-requests>=2.31.0` | Type stubs for requests |
| `types-pyyaml>=6.0.0` | Type stubs for PyYAML |
| `pip-tools>=7.3.0` | Dependency locking |

### External Services

| Service | Role | Auth |
|---------|------|------|
| Supabase (internal) | Operational store — deployments, resources, audit events | Service role key |
| Supabase (client) | Client-facing database provisioned per-org | Service role key |
| Vapi | Voice assistant API | Bearer token |
| Make.com | Automation scenario API | API token + zone-specific endpoint |
| Render | Hosting deployment API | API key |
| Amazon Bedrock | AI model (Claude) for config generation | AWS credentials |
| Gemini (optional) | Alternative model provider | API key |
| DuckDuckGo HTML | Fallback web search (no API key) | None |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        CLI Layer                             │
│  main.py → argparse commands → SessionManager               │
│  chat.py → ConversationAgent → IntakeExtractor              │
└─────────────────┬───────────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────────┐
│                    Orchestrator Layer                         │
│  orchestrator.py         — main deployment coordinator       │
│  action_builder.py       — onboarding action construction    │
│  planner.py              — task graph construction            │
│  make_deployer.py        — hook-first Make.com deployment    │
│  selective_regenerator.py— update/modification flow          │
│  assembler.py            — artifact package assembly         │
│  approval.py             — human approval flow               │
│  state_machine.py        — deployment lifecycle states       │
│  recovery.py             — failure handling & compensation   │
│  audit.py                — immutable event recording         │
│  org_lock.py             — per-org deployment serialization  │
│  conversation_agent.py   — conversational intake             │
│  dialogue_engine.py      — dialogue management              │
│  intake_extractor.py     — structured data extraction        │
└─────────────────┬───────────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────────┐
│                      Agent Layer                              │
│  vapi_agent/       — voice assistant config generation       │
│  make_agent/       — Make.com blueprint generation           │
│  supabase_agent/   — SQL migration generation               │
│  nodejs_agent/     — Backend code generation                 │
│  information_agent/— knowledge retrieval (RAG)              │
└─────────────────┬───────────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────────┐
│                     Adapter Layer                             │
│  vapi.py             — Vapi REST API client                  │
│  make.py             — Make.com REST API client              │
│  supabase_client.py  — Client Supabase operations            │
│  supabase_internal.py— Internal ops store                    │
│  hosting.py          — Render deployment API client          │
│  model_wrapper.py    — OpenAI-compatible model interface     │
│  bedrock_wrapper.py  — Amazon Bedrock Converse API           │
│  gemini.py           — Backward-compatible Gemini wrapper    │
│  brave_search.py     — DuckDuckGo HTML search fallback       │
└─────────────────┬───────────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────────┐
│                     Shared Layer                              │
│  errors.py           — typed error hierarchy & classification│
│  hashing.py          — SHA-256 content hashing & chain link  │
│  ids.py              — deterministic ID generation           │
│  redaction.py        — secret stripping for logs/exports     │
│  action_contract.py  — action type definitions               │
│  task_object.py      — task data structure                   │
│  result_object.py    — result data structure                 │
└─────────────────────────────────────────────────────────────┘
```

---

## How It Works

### 1. Intake Validation

The operator provides a JSON file describing the client:

```json
{
  "organization_name": "Acme Dental",
  "organization_id": "acme-dental-001",
  "industry": "healthcare",
  "capabilities": ["availability_check", "booking", "cancellation", "rescheduling"],
  "voice_config": {
    "provider": "11labs",
    "voice_id": "burt",
    "first_message": "Hello, this is Acme Dental..."
  },
  "business_hours": { "timezone": "America/New_York", "hours": {} },
  "supabase_project_ref": "abcdefghij",
  "backend_service_id": "srv-xyz"
}
```

The intake schema enforces:
- Required fields present and typed correctly
- Organization ID format (lowercase, alphanumeric, hyphens)
- Capabilities from allowed set
- Voice provider from supported list
- No embedded secrets

### 2. Planning

The Planner builds a directed task graph:

```
insert_org_record → run_migration → create_assistant → create_scenario(×4) → set_env_variable → trigger_deploy
```

Each task is a `TaskObject` specifying:
- `task_id`, `deployment_id`
- `agent_target` (which agent handles it)
- `action_type` (operation to perform)
- `context_hash` (content hash to detect staleness)
- `constraints`, `dependencies`
- `verification_required` flag
- `status`: pending | running | success | validation_failed | error | blocked | aborted

### 3. Artifact Generation

Each agent generates platform-specific configs from ground-truth templates:

- **Vapi Agent**: Produces assistant JSON (model, voice, system prompt, first message) + tool configs
- **Make Agent**: Produces 4 blueprint JSONs (availability: 4 modules, booking: 5, cancellation: 8, rescheduling: 10)
- **Supabase Agent**: Produces SQL migration with RLS policies
- **Node.js Agent**: Produces backend route handlers

Each generated artifact passes through a platform-specific validator:
- Structure conformance
- Module/field allowlists
- Placeholder resolution checks
- Secret scanning (regex-based)
- Cross-reference validation

### 4. Make.com Hook-First Deployment

The `MakeScenarioDeployer` implements a multi-step deployment strategy:

1. **Create webhook hook** — hook must exist before scenario can reference it
2. **Load blueprint** from `ground-truth/configs/make_blueprints/`
3. **Inject hook ID** into the blueprint's webhook module
4. **Inject connection ID** if provided
5. **Create scenario** with full blueprint (fallback: create stub, then update with full blueprint via PUT)
6. **Verify module count** — expected counts: availability=4, booking=5, cancellation=8, rescheduling=10
7. **Activate scenario**

This ensures full multi-module scenarios are deployed, not single-module stubs.

### 5. Approval Flow

Every external action requires explicit human approval. The flow:

```
┌──────────────────────────────────────────────┐
│  PROPOSAL DISPLAYED                          │
│  ─────────────────                           │
│  Action: create_assistant                    │
│  Platform: Vapi                              │
│  Details: Create voice assistant "Acme..."   │
│  Content Hash: sha256:a1b2c3...              │
│                                              │
│  [A]pprove  [R]eject  [V]iew details         │
└──────────────────────────────────────────────┘
```

Approval rules:
- One action at a time — never batched
- Staleness check: if config changed since proposal, re-display
- Hash binding: approval is tied to exact content hash
- No timeout: operator takes as long as needed
- Rejection options: abort entire deployment, or revise and re-propose

### 6. Sequential Execution

Actions execute one at a time in dependency order:

```
Action 1: Insert org record into Supabase (internal)
  ↓ receipt persisted
Action 2: Create Vapi assistant
  ↓ receipt persisted (includes remote_resource_id)
Action 3: Create Make hook + scenario (availability_check, 4 modules)
  ↓ receipt persisted
Action 4: Create Make hook + scenario (booking, 5 modules)
  ↓ receipt persisted
Action 5: Create Make hook + scenario (cancellation, 8 modules)
  ↓ receipt persisted
Action 6: Create Make hook + scenario (rescheduling, 10 modules)
  ↓ receipt persisted
Action 7: Set Render environment variable
  ↓ receipt persisted
Action 8: Trigger Render deploy
  ↓ receipt persisted
```

Each receipt (`AdapterReceipt`) records:
- `remote_resource_id` (platform's ID for the created thing)
- Timestamp
- Content hash at time of creation
- Status (succeeded/failed/ambiguous)

The receipt is persisted to the internal store **before** the next action begins.

### 7. Update/Modification Flow

The `SelectiveRegenerator` enables partial updates without full re-deployment:

1. `determine_affected_artifacts(intent, changes)` — maps the intent to which artifacts need regeneration
2. `generate_update_tasks(...)` — produces `TaskObject` list scoped to affected resources
3. `preserve_unchanged_resources(...)` — identifies resources that should not be touched

Supported intents:
- `update_assistant` → affects `vapi_assistant`
- `update_scenario` → affects `make_scenario` (+ `make_hooks` if webhook URL changed)
- `update_schema` → affects `supabase_migration`
- `update_backend` → affects `nodejs_diff` + `hosting_deploy`

The CLI's `_build_update_actions()` converts tasks into `ActionContract` objects routed through the same approval + adapter + receipt pipeline as onboarding.

### 8. State Machine

Deployments transition through a strict state machine:

```
planning → awaiting_plan_approval → generating → awaiting_action_approval → executing
    ↓              ↓                     ↓               ↓                      ↓
 aborted        aborted               failed          aborted              verifying
                                                     generating ←─┐           ↓
                                                     (revision)    │       complete
                                                                   │
                                              executing → partial → recovery_required
                                                                         ↓
                                                                    compensating
                                                                         ↓
                                                                    failed/aborted
```

Terminal states: `complete`, `failed`, `aborted`
Recovery states: `partial`, `recovery_required`, `compensating`

Invalid transitions are rejected with a `StateTransitionError` explaining what transitions are legal from the current state.

### 9. Recovery & Compensation

When an action fails mid-deployment:

1. **Ambiguous outcome** — network timeout after API call sent. Marked for reconciliation.
2. **Reconciliation** — query the platform API to determine if the resource exists.
3. **Retry** — if resource doesn't exist, re-propose the action with fresh approval.
4. **Compensation** — if deployment must be rolled back, generate reverse actions (delete what was created), each requiring separate approval.

Recovery is triggered automatically on CLI restart if a deployment is in `partial` or `recovery_required` state.

### 10. Audit Trail

Every significant event is recorded as an immutable audit entry:

```
Event Types:
- deployment_created, deployment_completed, deployment_failed
- task_started, task_completed, task_failed
- approval_requested, approval_granted, approval_rejected
- action_executing, action_succeeded, action_failed, action_ambiguous
- recovery_started, compensation_executed
- export_created, restore_completed
```

Each event includes:
- Timestamp (UTC)
- Actor (operator or system)
- Subject (deployment_id, resource_id)
- Sanitized details (secrets stripped via regex + allowlist)
- SHA-256 hash of event content
- Previous event hash (chain link)

The hash chain means any tampering (insertion, deletion, modification) breaks the chain and is detectable.

### 11. Tenant Isolation

Multi-tenancy is enforced at every layer:

- **Database**: Row-Level Security (RLS) policies filter by `organization_id`
- **Internal store**: All queries scoped by organization
- **Artifacts**: Cross-organization references detected and rejected at validation time
- **Exports**: Only include data for the specified organization
- **Org lock**: Only one deployment per organization can execute at a time
- **Adapter allowlists**: `supabase_client.py` restricts operations to `ALLOWED_TABLES`

### 12. Secret Management

Secrets never appear in:
- Generated artifacts (validated by regex scanner)
- Audit event details (redacted before recording)
- Exported data (`redact_dict` strips known patterns)
- CLI output (config display shows redacted values)

Secret patterns detected:
```python
SECRET_PATTERNS = [
    (r"sk-[a-zA-Z0-9]{10,}", "sk-***"),
    (r"pk-[a-zA-Z0-9]{10,}", "pk-***"),
    (r"Bearer\s+[a-zA-Z0-9\-._~+/]+=*", "Bearer ***"),
    (r"api[_-]?key['\"]?\s*[:=]\s*['\"]?(...)", "api_key=***"),
    (r"AKIA[0-9A-Z]{16}", "AKIA***"),
    (r"AIza[0-9A-Za-z\-_]{35}", "AIza***"),
    (r"eyJ[...]\.eyJ[...]\..*", "eyJ***"),
    # ... plus password, token, AWS, base64 patterns
]
```

Secrets are loaded exclusively from `.env` and injected at runtime by the adapter layer.

---

## CI/CD Pipeline

### GitHub Actions

| Workflow | Trigger | Steps |
|----------|---------|-------|
| **CI** (`ci.yml`) | Push to `master`, all PRs | lint (ruff) → typecheck (mypy) → test (pytest, unit+contract, 30s timeout) |
| **Security Scan** (`security.yml`) | PRs to `master` | TruffleHog secret scanning (`--only-verified`) |

### Dependabot

- **pip ecosystem**: Weekly updates targeting `pyproject.toml`
- **github-actions ecosystem**: Weekly updates

### Lint Rules

Ruff is configured with these rule sets: E (pycodestyle errors), W (warnings), F (pyflakes), I (isort), N (pep8-naming), UP (pyupgrade), B (flake8-bugbear), C4 (comprehensions), SIM (simplify). Line length: 100. Target: Python 3.11.

---

## CLI Commands

### Conversational Onboarding (Primary)

```bash
# Start conversational intake (recommended - default when no args given)
agent-forge

# Or explicitly
agent-forge chat

# Interactive flow:
# 1. Collects client details through natural dialogue
# 2. Asks about capabilities, voice preferences, business hours
# 3. Confirms platform connection details
# 4. Extracts and validates structured intake automatically
# 5. Pre-validates voice ID against Vapi API
# 6. Presents deployment plan for approval
# 7. Executes with per-action approval gates
```

### File-Based Intake (Automation/Scripting)

```bash
# For CI/CD pipelines or pre-existing intake JSON files

# Validate intake JSON
agent-forge intake validate --file <file>

# Preview deployment plan (dry-run, no external changes)
agent-forge onboard --dry-run --intake <file>

# Execute deployment with per-action approval
agent-forge onboard --execute --environment staging --intake <file>

# Generate artifacts without deploying
agent-forge generate --intake <file>

# Validate generated package
agent-forge validate package --manifest <file>
```

### Update/Modification Flow

```bash
# Update existing deployment (selective regeneration)
agent-forge update --organization <org> --intent update_assistant --updates <file> --dry-run
agent-forge update --organization <org> --intent update_assistant --updates <file> --execute

# Supported intents: update_assistant, update_scenario, update_schema, update_backend
```

### Operations & Monitoring

```bash
# Configuration check
agent-forge config check              # Validate all env vars (redacted display)

# Smoke tests
agent-forge smoke-test gemini         # Test model provider connectivity
agent-forge smoke-test chroma         # Test ChromaDB write/read cycle

# History & audit
agent-forge history --organization <org>           # List deployments for org
agent-forge verify health                          # Check all external resources exist

# Cleanup
agent-forge cleanup --organization <org> --dry-run # Preview resource deletion
agent-forge cleanup --organization <org>           # Delete with per-action approval

# Security
agent-forge security scan --path <dir>             # Scan for exposed secrets

# Export/Restore
agent-forge export --organization <org> --output <path>
agent-forge restore --manifest <path>
```

### Knowledge Base Management

```bash
# Gotcha proposal workflow (agent-assisted knowledge base growth)
agent-forge gotcha list                           # List pending proposals
agent-forge gotcha approve <number>               # Approve and convert to markdown
agent-forge gotcha approve <number> --yes         # Skip confirmation prompt
agent-forge gotcha approve <number> --no-rebuild  # Skip embedding rebuild
agent-forge gotcha reject <number>                # Reject with optional reason
agent-forge gotcha reject <number> --reason "..." # Reject with specified reason

# Agents can propose new gotchas via propose_new_knowledge() tool
# Proposals include duplicate detection (similarity > 0.75)
# Approval converts JSON to markdown and rebuilds embeddings automatically
```

---

## Development

### Quick Start

```bash
# Install with dev dependencies
pip install -e ".[dev]"
# Or:
make install

# Run linting
make lint

# Run type checking
make typecheck

# Run unit + contract tests
make test

# Run all tests
make test-all

# Lock dependencies
make lock
```

### Docker

```bash
# Build
docker build -t agent-forge .

# Run
docker run --env-file .env agent-forge config check
docker run --env-file .env agent-forge onboard --dry-run --intake /app/tests/fixtures/staging_client.json
```

The Dockerfile uses `python:3.11-slim`, installs from `requirements.txt`, and sets the entrypoint to `python -m cli.main`.

---

## Running Tests

618 tests across 7 categories:

```bash
# All tests
pytest tests/

# By category
pytest tests/unit/                # 321 unit tests
pytest tests/contract/            # 97 contract tests
pytest tests/integration/         # 63 integration tests
pytest tests/security/            # 51 security tests
pytest tests/regression/          # 56 regression tests (prompt/template stability)
pytest tests/failure_injection/   # 20 failure injection tests
pytest tests/restoration/         # 10 restoration tests

# By marker
pytest -m unit                    # Fast deterministic tests
pytest -m regression              # Prompt and blueprint stability baselines
pytest -m "unit or contract"      # CI gate (fast, no external deps)
pytest -m "not integration"       # Skip tests requiring external services
```

### Regression Test Suite

The regression suite (`tests/regression/`) prevents breaking changes to:

- **System prompts** (`test_prompt_stability.py`, 11 tests):
  - Required sections present (role, gathering, confirmation, prohibitions)
  - No JSON field names in user-facing text (critical UX requirement)
  - Confirmation/cancellation keyword stability (yes/no/cancel must work)
  - Phase transition correctness (gathering → confirming → executing)
  - Confirmed intake structure (field mapping, required fields)

- **Blueprint templates** (`test_blueprint_stability.py`, 45 tests):
  - JSON structural validity for all capability blueprints
  - Required fields (name, flow, metadata) present
  - Module structure (id, module, version, mapper in each)
  - First module is webhook trigger (gateway:CustomWebHook)
  - Module count baselines: availability=4, booking=5, cancellation=4, rescheduling=5
  - Webhook configuration present for parameterization
  - Metadata consistency (version, capability, template_version)

These tests establish stability baselines. Changes that break them require verification that the new behavior is intentional and documented.

CI runs `pytest -m "unit or contract" --timeout=30` as the gate.

---

## Project Directory Structure

```
agentforge/
├── .github/
│   ├── dependabot.yml               # Weekly pip + actions updates
│   └── workflows/
│       ├── ci.yml                   # Lint, typecheck, test
│       └── security.yml             # TruffleHog secret scanning
│
├── adapters/                        # Platform API clients (11 files)
│   ├── base.py                      # AdapterReceipt dataclass, base HTTP adapter
│   ├── vapi.py                      # VapiAdapter: assistants, tools, phone numbers
│   ├── make.py                      # MakeAdapter: scenarios, blueprints, hooks
│   ├── supabase_client.py           # Client Supabase ops (table allowlists)
│   ├── supabase_internal.py         # SupabaseInternalClient (ops store)
│   ├── hosting.py                   # RenderAdapter: env vars, deployments
│   ├── model_wrapper.py             # ModelWrapper: OpenAI-compatible client
│   ├── bedrock_wrapper.py           # BedrockModelWrapper: AWS Converse API
│   ├── gemini.py                    # Backward-compat Gemini alias
│   └── brave_search.py             # DuckDuckGo HTML fallback search
│
├── agents/                          # Config generation agents (5 agents, 21 files)
│   ├── vapi_agent/
│   │   ├── agent.py                 # Assistant config generator
│   │   ├── tools.py                 # Hook injection, reference extraction
│   │   └── validator.py             # Vapi config validator
│   ├── make_agent/
│   │   ├── agent.py                 # Blueprint generator
│   │   ├── tools.py                 # inject_hook_urls, extract_hook_references
│   │   └── validator.py             # Blueprint validator
│   ├── supabase_agent/
│   │   ├── agent.py                 # Migration generator
│   │   ├── tools.py                 # SQL tooling
│   │   └── validator.py             # SQL validator
│   ├── nodejs_agent/
│   │   ├── agent.py                 # Backend code generator
│   │   ├── tools.py                 # Node.js tooling
│   │   └── validator.py             # Node.js validator
│   └── information_agent/
│       ├── agent.py                 # Knowledge retrieval
│       └── rag.py                   # ChromaDB RAG interface
│
├── orchestrator/                    # Core deployment logic (20 files)
│   ├── orchestrator.py              # Main coordinator (Orchestrator class)
│   ├── action_builder.py            # Onboarding ProposedAction construction
│   ├── planner.py                   # Task graph builder
│   ├── make_deployer.py             # MakeScenarioDeployer (hook-first)
│   ├── selective_regenerator.py     # SelectiveRegenerator (update flow)
│   ├── assembler.py                 # Package assembly
│   ├── approval.py                  # Human approval flow
│   ├── state_machine.py             # DeploymentStateMachine (12 states)
│   ├── recovery.py                  # Failure recovery & compensation
│   ├── audit.py                     # Immutable audit trail
│   ├── org_lock.py                  # Per-org deployment lock
│   ├── deployment_lookup.py         # Deployment queries
│   ├── intake_schema.py             # Intake validation
│   ├── current_state_reader.py      # Platform state reader
│   ├── template_registry.py         # Ground-truth template loader
│   ├── conversation_agent.py        # Conversational intake agent
│   ├── conversation_state.py        # Conversation state management
│   ├── dialogue_engine.py           # Dialogue management
│   └── intake_extractor.py          # Structured intake extraction
│
├── shared/                          # Cross-cutting utilities (8 files)
│   ├── errors.py                    # 11 error classes + classify_error()
│   ├── hashing.py                   # SHA-256 hashing + chain linking
│   ├── ids.py                       # Deterministic ID generation
│   ├── redaction.py                 # Secret pattern scanning + redaction
│   ├── action_contract.py           # ActionContract dataclass
│   ├── task_object.py               # TaskObject dataclass
│   └── result_object.py             # Result object pattern
│
├── cli/                             # CLI interface (7 files)
│   ├── main.py                      # Argparse commands, entry point
│   ├── chat.py                      # Conversational chat interface
│   ├── config.py                    # AgentForgeConfig, load_config, ConfigurationError
│   ├── prompts.py                   # Interactive approval UI
│   ├── session.py                   # Session management
│   └── history.py                   # Deployment history queries
│
├── ground-truth/                    # Source templates
│   ├── configs/
│   │   ├── make_blueprints/         # 4 blueprint JSONs (availability, booking, cancellation, rescheduling)
│   │   ├── vapi_tools/              # 4 tool configs (per capability)
│   │   └── vapi_assistant_template.json
│   └── schemas/
│       └── client_database_template.sql
│
├── knowledge-base/                  # RAG knowledge store
│   ├── docs/                        # Platform guides (make, supabase, vapi)
│   ├── gotchas/                     # Known pitfalls (3 documented)
│   └── proposals/                   # Feature proposals
│
├── config/                          # Runtime configuration
│   ├── agent_registry.json          # Agent definitions
│   ├── capability_map.json          # Capability → agent mapping
│   └── vendor_contract_versions.json# API version tracking
│
├── templates/
│   └── backend/
│       └── package.json             # Express template for client backends
│
├── scripts/                         # Operational scripts
│   ├── embed_knowledge.py           # Build ChromaDB embeddings
│   ├── export_internal_tables.py    # Export deployment data
│   ├── restore_internal_tables.py   # Restore from export
│   ├── reconcile_deployment.py      # Reconcile partial deployments
│   └── verify_staging.py            # Staging environment verification
│
├── supabase/migrations/             # 16 migration files (15 migrations + consolidated schema)
│
├── tests/                           # 562 tests across 6 categories
│   ├── unit/                        # 321 tests (23 test files)
│   ├── contract/                    # 97 tests (4 test files)
│   ├── integration/                 # 63 tests (10 test files)
│   ├── security/                    # 51 tests (4 test files)
│   ├── failure_injection/           # 20 tests (4 test files)
│   ├── restoration/                 # 10 tests (1 test file)
│   ├── fixtures/                    # Test data
│   └── snapshots/                   # Golden file comparisons
│
├── Dockerfile                       # python:3.11-slim container
├── .dockerignore                    # Excludes .git, .env, tests, etc.
├── Makefile                         # lint, typecheck, test, test-all, lock, install
├── pyproject.toml                   # Package config, ruff, mypy, pytest settings
├── requirements.txt                 # Production dependencies
└── .env.example                     # All environment variables documented
```

---

## Database Schema (Internal Store)

16 migration files managing these core tables:

### Core Tables

**`deployments`** — One row per deployment attempt
- `deployment_id` (PK), `organization_id`, `status` (enum), `intake_hash`, `created_at`, `completed_at`

**`deployment_resources`** — External resources created during deployment
- `resource_id` (PK), `deployment_id` (FK), `resource_type` (enum), `remote_resource_id`, `platform`, `content_hash`, `created_at`

**`audit_events`** — Immutable append-only audit log
- `event_id` (PK), `deployment_id`, `event_type`, `actor`, `subject`, `details` (JSONB), `event_hash`, `previous_hash`, `created_at`

**`proposed_actions`** — Actions awaiting or past approval
- `action_id` (PK), `deployment_id`, `operation`, `platform`, `content_hash`, `status`, `sequence_number`

**`sessions`** — CLI session tracking

**`task_executions`** — Task execution records

**`artifacts`** — Generated artifact metadata

### Deployment Status Enum

```sql
CREATE TYPE deployment_status AS ENUM (
  'planning',
  'awaiting_plan_approval',
  'generating',
  'awaiting_action_approval',
  'executing',
  'verifying',
  'partial',
  'recovery_required',
  'compensating',
  'complete',
  'failed',
  'aborted'
);
```

---

## Error Handling

### Error Hierarchy

```
AgentForgeError(Exception)
├── ValidationError          — intake/artifact validation failures
├── AuthorizationError       — permission denied
├── ConflictError            — resource already exists / org locked
├── TransientError           — retryable API errors (5xx, network)
├── PermanentError           — non-retryable API errors (4xx)
├── AmbiguousOutcomeError    — timeout after request sent
├── CompensationError        — failure during rollback
├── PersistenceError         — local storage failures
├── StateTransitionError     — invalid state machine transition
├── OrganizationLockError    — org deployment already in progress
└── RecoveryRequiredError    — deployment needs recovery before proceeding
```

### Error Classification

Every adapter error is classified via `classify_error()` before propagation:
- **4xx** → `PermanentError` (don't retry)
- **5xx** → `TransientError` (retry with backoff)
- **Timeout** → `AmbiguousOutcomeError` (reconcile before retry)
- **Connection refused** → `TransientError`

---

## Configuration

### Environment Variables (`.env`)

```bash
# Model Provider (choose one: gemini, meta, openai, bedrock)
MODEL_PROVIDER=bedrock

# Amazon Bedrock (recommended)
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-20250514

# Google Gemini (alternative)
GEMINI_API_KEY=

# Meta AI (alternative)
META_API_KEY=

# Voice assistant
VAPI_API_KEY=
VAPI_PHONE_NUMBER_ID=

# Automation
MAKE_API_TOKEN=
MAKE_TEAM_ID=
MAKE_ZONE=us1              # eu1, eu2, us1, us2

# Client-facing Supabase
SUPABASE_CLIENT_URL=
SUPABASE_CLIENT_SERVICE_ROLE_KEY=

# Internal operational store
SUPABASE_INTERNAL_URL=
SUPABASE_INTERNAL_SERVICE_ROLE_KEY=

# Hosting
HOSTING_API_TOKEN=
HOSTING_SERVICE_ID=
HOSTING_HEALTH_URL=

# Search (fallback uses DuckDuckGo if empty)
BRAVE_SEARCH_API_KEY=

# Local
CHROMA_PERSIST_DIR=./chroma_data
SERVER_SOURCE_PATH=
SERVER_TEST_COMMAND=

# Runtime
AGENT_FORGE_ENV=staging    # staging or production
```

### Validation Rules

`load_config()` enforces:
- `AGENT_FORGE_ENV` must be `staging` or `production`
- `MAKE_ZONE` must be one of: `eu1`, `eu2`, `us1`, `us2`
- `HOSTING_HEALTH_URL` must start with `https://`
- Production identifiers detected in staging mode raises `ConfigurationError`

### Zone-Specific Endpoints

Make.com uses zone-specific API endpoints:
- `eu1.make.com` / `eu2.make.com` / `us1.make.com` / `us2.make.com`

The `MAKE_ZONE` variable determines the base URL: `https://{zone}.make.com/api/v2`

---

## Deployment Flow (End-to-End)

### Conversational Path (Recommended)

```
Operator runs: agent-forge (or agent-forge chat)

Conversational Intake Phase:
1. ConversationAgent starts interactive dialogue
2. Operator answers questions about client details:
   - Organization name, industry
   - Capabilities needed (availability, booking, cancellation, rescheduling)
   - Voice preferences (provider, voice ID, first message)
   - Business hours and timezone
   - Platform connection details (Supabase project ref, backend service ID)
3. IntakeExtractor parses conversation and extracts structured intake data
4. System validates extracted intake against schema
5. Voice ID pre-validated against Vapi API (list_voices)
6. Operator reviews and confirms extracted intake data
7. Handoff to execution pipeline below

Execution Phase (common to both paths):
1. Check org lock (one deployment per org at a time)
2. Create deployment record (status: planning)
3. Build task graph from intake capabilities
4. Transition to: generating
5. For each task in graph:
   a. Load ground-truth template
   b. Generate platform config via agent + model
   c. Validate generated config
   d. Write artifact to outputs/<org>/<platform>/
6. Assemble deployment package with manifest
7. Transition to: awaiting_action_approval
8. For each action in sequence:
   a. Compute content hash
   b. Display proposal to operator
   c. Wait for approval
   d. Check staleness (content hash still matches?)
   e. Execute via platform adapter
   f. Persist receipt (remote_resource_id, status, timestamp)
   g. Record audit event
   h. If failed → enter recovery flow
9. Transition to: verifying
10. Reconcile: query each platform, confirm resources exist
11. Transition to: complete
12. Record completion audit event
13. Release org lock
```

### File-Based Path (Automation/CI/CD)

```
Operator runs: agent-forge onboard --execute --environment staging --intake staging_client.json

1. Load & validate intake JSON
2-13. [Same execution phase as conversational path above, starting from "Check org lock"]
```

---

## Knowledge Base & RAG

Agent Forge includes a local ChromaDB vector store containing:

- **Platform guides**: API documentation for Vapi, Make.com, Supabase (`knowledge-base/docs/`)
- **Platform gotchas**: Known issues and undocumented behaviors (`knowledge-base/gotchas/`)
  - 11 verified gotchas covering Make.com, Vapi, Render, and Supabase
  - Examples: `make-hook-first-deployment.md`, `vapi-voice-id-must-match-provider.md`

The information agent queries this store during generation to avoid known pitfalls.

### Agent-Assisted Knowledge Growth

Agents can propose new gotchas via the `propose_new_knowledge()` tool:

1. **Agent proposes**: During troubleshooting, agents identify patterns and propose new gotchas
2. **Duplicate detection**: System checks vector similarity (threshold > 0.75) against existing knowledge
3. **Human review**: Proposals saved to `knowledge-base/proposals/` as JSON with duplicate warnings
4. **Approval workflow**:
   ```bash
   agent-forge gotcha list                    # Review pending proposals
   agent-forge gotcha approve <number>        # Convert to markdown, rebuild embeddings
   agent-forge gotcha reject <number>         # Reject with logged reason
   ```
5. **Automatic integration**: Approved gotchas are converted to markdown, saved to `knowledge-base/gotchas/`, and embeddings are rebuilt automatically

Embeddings can be manually managed via:

```bash
python scripts/embed_knowledge.py --rebuild
python scripts/embed_knowledge.py --verify
```

---

## Security Model

### Principle of Least Privilege

- Each platform API key is scoped to staging/production environment
- Internal store uses service role (bypasses RLS for ops)
- Client store uses service role + RLS policies (enforced tenant isolation)
- Supabase client adapter restricts operations to `ALLOWED_TABLES = {"organizations"}`

### Defense in Depth

| Layer | Protection |
|-------|-----------|
| Intake | Schema validation rejects malformed input |
| Generation | Validators scan for secrets, disallowed modules, unresolved placeholders |
| Approval | Human reviews every external action |
| Execution | Sequential with receipts — partial state always known |
| Audit | Hash-chained — tampering detectable |
| Export | Secrets redacted before serialization |
| CLI output | Config display redacts sensitive values |
| CI | TruffleHog scans PRs for leaked credentials |

---

## Platform-Specific Notes

### Vapi

- Model config requires `provider` and `model` fields
- Voice ID must be valid for the provider (e.g., `burt` for 11labs)
- Phone number assignment via `assign_phone_number(phone_number_id, assistant_id)`
- Adapter methods: `create_assistant`, `get_assistant`, `update_assistant`, `delete_assistant`, `create_tool`, `list_tools`, `get_tool`, `assign_phone_number`, `list_phone_numbers`, `list_voices`

### Make.com

- Zone-specific endpoints (`MAKE_ZONE` determines base URL)
- Team ID (not org ID) required for API calls
- Blueprint must be JSON-stringified in API payload
- Module name is `gateway:CustomWebHook` (adapter also matches `webhook:CustomWebHook`)
- Scheduling type must be one of: immediately, indefinitely, once, daily, weekly, monthly, yearly
- Unknown scheduling types default to `immediately`
- Hook-first deployment: hooks created before scenarios via `MakeScenarioDeployer`
- Fallback: if full blueprint rejected, create stub + update with full blueprint via PUT
- Expected module counts: availability=4, booking=5, cancellation=4, rescheduling=5
- Adapter methods: `create_scenario`, `get_scenario`, `list_scenarios`, `delete_scenario`, `get_scenario_blueprint`, `update_scenario_blueprint`, `activate_scenario`, `deactivate_scenario`, `create_hook`, `get_hook`, `list_hooks`, `delete_hook`, `verify_hook`

### Supabase

- Internal store uses service role key (bypasses RLS)
- Client store migrations include RLS policies scoped by `organization_id`
- Dual-store architecture: ops data never mixes with client data
- Client adapter enforces table allowlists

### Render

- Environment variables set before deploy trigger
- Deploy trigger is fire-and-forget (async on Render side)
- Service ID from intake (`backend_service_id`)
- Health URL verified with HTTPS requirement

---

## Design Principles

1. **Human approval for every side effect** — No action touches an external platform without explicit operator consent.
2. **Sequential execution with receipts** — Always know exactly what was created; never lose track of resources.
3. **Hash-chained audit** — Every decision is recorded immutably; tampering is detectable.
4. **Fail-safe recovery** — Ambiguous outcomes are reconciled, not retried blindly.
5. **Tenant isolation at every layer** — Organization data never leaks across boundaries.
6. **No hardcoded secrets** — All credentials from environment; validated absent from artifacts.
7. **Smallest viable diff** — Each deployment action does one thing; rollback is granular.
8. **Ground-truth templates** — Generated configs derive from version-controlled source templates.
9. **Hook-first deployment** — Make.com hooks always created before scenarios to ensure correct wiring.
10. **Selective regeneration** — Updates modify only affected resources, preserving everything else.

---

## Operational Procedures

### First-Time Setup

1. Clone repository: `git clone https://github.com/MuhammadRaedSiddiqui/agentforge.git`
2. Create Python 3.11+ virtualenv
3. `pip install -e ".[dev]"` (or `make install`)
4. Copy `.env.example` → `.env` and fill all values
5. Apply internal store migrations: `supabase db push`
6. Build knowledge embeddings: `python scripts/embed_knowledge.py --rebuild`
7. Run smoke tests: `agent-forge smoke-test gemini && agent-forge smoke-test chroma`
8. Validate config: `agent-forge config check`

### Running a Deployment

**Conversational Path (Recommended):**

1. Start the conversational interface: `agent-forge` (or `agent-forge chat`)
2. Answer questions about your client:
   - Organization name and industry
   - Capabilities needed (availability check, booking, cancellation, rescheduling)
   - Voice preferences (provider, voice ID, first message)
   - Business hours and timezone
   - Platform connection details (Supabase project ref, backend service ID)
3. Review the extracted intake data when presented
4. Confirm the deployment plan
5. Approve each action as prompted (Vapi assistant, Make scenarios, database migration, hosting deployment)
6. Verify: `agent-forge verify health`

**File-Based Path (For Automation/CI/CD):**

1. Prepare intake JSON (see `tests/fixtures/staging_client.json` for example)
2. Validate: `agent-forge intake validate --file intake.json`
3. Preview: `agent-forge onboard --dry-run --intake intake.json`
4. Deploy: `agent-forge onboard --execute --environment staging --intake intake.json`
5. Approve each action as prompted
6. Verify: `agent-forge verify health`

### Updating an Existing Deployment

1. Preview: `agent-forge update --organization <org> --intent update_assistant --updates changes.json --dry-run`
2. Execute: `agent-forge update --organization <org> --intent update_assistant --updates changes.json --execute`
3. Only affected resources are modified; everything else is preserved

### Recovery After Failure

1. Re-run: `agent-forge onboard --execute --environment staging --intake intake.json` (detects partial state)
2. System presents recovery options: reconcile, retry, or compensate
3. Each recovery action requires fresh approval

### Cleanup

1. Dry run: `agent-forge cleanup --organization <org> --dry-run`
2. Execute: `agent-forge cleanup --organization <org>`
3. Approve each deletion individually

---

## Glossary

| Term | Definition |
|------|-----------|
| **Intake** | JSON document describing a new client's requirements |
| **Deployment** | A single execution of the onboarding pipeline |
| **Proposed Action** | An external side effect awaiting human approval |
| **Receipt** | `AdapterReceipt` — record of a completed action (includes remote resource ID) |
| **Reconciliation** | Querying a platform to confirm resource existence |
| **Compensation** | Reverse action to undo a previously successful action |
| **Ground Truth** | Version-controlled source templates for all generated configs |
| **Org Lock** | Mutex ensuring one deployment per organization at a time |
| **Hash Chain** | Linked SHA-256 hashes forming a tamper-evident audit log |
| **Staleness** | When config changes between proposal display and execution |
| **TaskObject** | Dataclass representing a single unit of work in the task graph |
| **ActionContract** | Dataclass defining the execution contract for a platform action |
| **SelectiveRegenerator** | Component that determines which artifacts need updating |
| **MakeScenarioDeployer** | Hook-first multi-step Make.com deployment orchestrator |
| **Hook-First** | Pattern where Make.com webhooks are created before scenarios that reference them |
