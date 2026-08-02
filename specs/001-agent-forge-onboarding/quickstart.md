# Quickstart: Agent Forge Staging and Verification

**Feature**: `001-agent-forge-onboarding`  
**Artifact Version**: 1.0.0  
**Constitution Version**: 1.0.0  
**Spec Version**: 1.0.0  
**Plan Version**: 1.0.0  
**Created**: 2026-07-11  
**Target**: Local Agent Forge process connected only to staging resources

## Purpose

Use this runbook to prove Agent Forge is safe before the first real client deployment. It covers local setup, contract validation, isolated database migrations, dry-run planning, generation, staging writes, failure recovery, tenant isolation, audit verification, export, and restoration.

Do not substitute production identifiers while following this guide. Every command that can change an external resource is marked **LIVE STAGING WRITE** and requires a separate approval inside Agent Forge.

## Required Repository Layout

Run all commands from the repository root unless a step says otherwise.

```text
memory/
â””â”€â”€ constitution.md

specs/
â””â”€â”€ 001-agent-forge-onboarding/
    â”œâ”€â”€ spec.md
    â”œâ”€â”€ plan.md
    â”œâ”€â”€ research.md
    â”œâ”€â”€ data-model.md
    â”œâ”€â”€ quickstart.md
    â”œâ”€â”€ tasks.md
    â”œâ”€â”€ contracts/
    â”‚   â””â”€â”€ tool-contracts.yaml
    â””â”€â”€ checklists/
        â””â”€â”€ requirements.md
```

## Safety Rules

1. Use staging Vapi, Make, Supabase, and Render resources only.
2. Never paste secrets into prompts, task descriptions, fixtures, snapshots, or command history.
3. Confirm all project, team, service, phone, and resource identifiers before any write.
4. Never approve more than one live action from one prompt.
5. Stop immediately if a production hostname, project reference, phone number, or service ID appears.
6. Do not enable backend writes unless `SERVER_TEST_COMMAND` is real and passes.
7. Do not retry an ambiguous create until reconciliation proves whether it succeeded.

## 1. Verify Prerequisites

### 1.1 Required tools

```bash
python --version
git --version
node --version
supabase --version
```

Expected:

- Python 3.11 or later
- Git available
- Node.js compatible with the existing backend test suite
- A reviewed and pinned Supabase CLI version

Record versions:

```bash
mkdir -p outputs/verification
{
  python --version
  git --version
  node --version
  supabase --version
} > outputs/verification/tool-versions.txt 2>&1
```

### 1.2 Confirm the feature files exist

```bash
test -f memory/constitution.md
test -f specs/001-agent-forge-onboarding/spec.md
test -f specs/001-agent-forge-onboarding/plan.md
test -f specs/001-agent-forge-onboarding/research.md
test -f specs/001-agent-forge-onboarding/data-model.md
test -f specs/001-agent-forge-onboarding/tasks.md
test -f specs/001-agent-forge-onboarding/contracts/tool-contracts.yaml
```

### 1.3 Create the local Python environment

```bash
python -m venv .venv
```

Activate on Linux or macOS:

```bash
source .venv/bin/activate
```

Activate on PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If the project uses an exact lock file after T143:

```bash
python -m pip install -r requirements.lock.txt
```

## 2. Create and Validate Staging Configuration

### 2.1 Create the local environment file

```bash
cp .env.example .env
```

Populate `.env` locally. Do not commit it.

Required staging variables:

```dotenv
GEMINI_API_KEY=
VAPI_API_KEY=
MAKE_API_TOKEN=
MAKE_TEAM_ID=
MAKE_ZONE=us1
SUPABASE_CLIENT_URL=
SUPABASE_CLIENT_SERVICE_ROLE_KEY=
SUPABASE_INTERNAL_URL=
SUPABASE_INTERNAL_SERVICE_ROLE_KEY=
SUPABASE_PROJECT_REF_STAGING=
HOSTING_API_TOKEN=
HOSTING_SERVICE_ID=
HOSTING_HEALTH_URL=
BRAVE_SEARCH_API_KEY=
CHROMA_PERSIST_DIR=./chroma_data
SERVER_SOURCE_PATH=
SERVER_TEST_COMMAND=
AGENT_FORGE_ENV=staging
```

### 2.2 Protect the environment file

Linux or macOS:

```bash
chmod 600 .env
```

Confirm Git ignores it:

```bash
git check-ignore .env
```

Expected output:

```text
.env
```

### 2.3 Validate configuration without displaying secrets

```bash
python -m cli.main config check
```

Expected:

- Environment is `staging`.
- Every required variable is present.
- Staging resource identities are shown in redacted form.
- No secret values are printed.
- Production-looking targets block startup.

## 3. Run Static and Contract Validation

### 3.1 Validate Markdown and YAML artifacts

```bash
python - <<'PY'
from pathlib import Path
import yaml

contract = Path("specs/001-agent-forge-onboarding/contracts/tool-contracts.yaml")
with contract.open("r", encoding="utf-8") as handle:
    document = yaml.safe_load(handle)

assert document["openapi"] == "3.1.0"
assert document["info"]["version"] == "1.0.0"
assert document["paths"]
assert document["components"]["schemas"]
print("tool-contracts.yaml: valid YAML with paths and schemas")
PY
```

### 3.2 Run formatting, linting, and typing

```bash
ruff format --check .
ruff check .
mypy agents orchestrator adapters shared cli scripts
```

### 3.3 Run unit and vendor contract tests

```bash
pytest -m unit -q
pytest -m contract -q
```

Expected:

- All deterministic schemas and validators pass.
- Contract tests match `tool-contracts.yaml`.
- Sensitive response fields are redacted.
- Missing required vendor fields fail closed.

## 4. Verify Gemini and Chroma Smoke Tests

### 4.1 Verify Gemini compatibility

```bash
python -m cli.main smoke-test gemini
```

The smoke test MUST verify:

1. explicit model selection;
2. structured output parsing;
3. one local function-tool call;
4. a multi-turn tool result;
5. sanitized error handling;
6. no API key in captured logs.

Expected result:

```text
Gemini compatibility: PASS
```

Record the verified versions in:

```text
config/vendor_contract_versions.json
```

### 4.2 Verify Chroma persistence

```bash
python -m cli.main smoke-test chroma
```

Expected behavior:

- Create or open `CHROMA_PERSIST_DIR`.
- Insert one temporary document.
- Retrieve it by similarity.
- Delete the temporary collection.

### 4.3 Build the verified knowledge index

```bash
python scripts/embed_knowledge.py --rebuild
```

Verify source checksums:

```bash
python scripts/embed_knowledge.py --verify
```

## 5. Initialize the Local Supabase Stack

### 5.1 Initialize and start local Supabase

Run `supabase init` only if the repository has not been initialized:

```bash
test -f supabase/config.toml || supabase init
supabase start
```

Capture local status without committing credentials:

```bash
supabase status
```

### 5.2 Reset the local database from migrations

```bash
supabase db reset
```

Expected:

- All canonical internal operational tables exist.
- Constraints and partial unique indexes are created.
- Append-only entities reject application updates and deletes.
- Seed fixtures load successfully, if configured.

### 5.3 Run internal-store tests

```bash
pytest tests/integration/test_internal_store.py -q
pytest tests/unit/test_state_machine.py -q
pytest tests/restoration/test_operational_restore.py -q
```

## 6. Verify the Staging Supabase Target

### 6.1 Log in and link to staging

```bash
supabase login
supabase link --project-ref "$SUPABASE_PROJECT_REF_STAGING"
```

Verify the linked target before proceeding:

```bash
supabase projects list
supabase migration list --linked
```

Stop if the linked project reference does not exactly match the approved staging reference.

### 6.2 Preview the migration difference

```bash
supabase db diff --linked > outputs/verification/staging-schema-diff.sql
```

Review the file manually:

```bash
sed -n '1,240p' outputs/verification/staging-schema-diff.sql
```

### 6.3 Apply migrations to staging

**LIVE STAGING WRITE**

Agent Forge must display the project reference, migration hashes, validation evidence, and recovery limitations before approval.

```bash
supabase db push --linked
```

### 6.4 Verify staging migrations and tenant isolation

```bash
supabase migration list --linked
pytest tests/security/test_tenant_isolation.py -m staging -q
```

Expected:

- Allowed tenant access succeeds.
- Cross-tenant access fails.
- No reusable policy contains a hardcoded organization ID.

## 7. Run the Zero-Write Onboarding Preview

### 7.1 Create a staging intake fixture

Create `tests/fixtures/staging_client.json` with non-production values:

```json
{
  "organization_id": "agent_forge_staging",
  "business_name": "Agent Forge Staging Salon",
  "phone_number": "+15555550199",
  "voice_id": "reviewed-staging-voice",
  "timezone": "America/New_York",
  "business_hours": {
    "monday": [{"open": "09:00", "close": "17:00"}]
  },
  "services_offered": [
    {"name": "Consultation", "duration_minutes": 30}
  ],
  "booking_calendar_id": "staging-calendar-id",
  "cancellation_window_hours": 24,
  "rescheduling_policy": {"minimum_notice_hours": 12},
  "transfer_destination": "+15555550198",
  "enabled_capabilities": [
    "availability",
    "booking",
    "cancellation",
    "rescheduling",
    "human_transfer"
  ],
  "external_identifiers": {
    "vapi_phone_number_id": "staging-phone-resource-id"
  }
}
```

Never use this sample phone number without confirming it is valid for your staging setup. Replace resource placeholders with reviewed staging IDs.

### 7.2 Validate intake

```bash
python -m cli.main intake validate \
  --file tests/fixtures/staging_client.json
```

### 7.3 Generate a dry-run plan

```bash
python -m cli.main onboard \
  --intake tests/fixtures/staging_client.json \
  --dry-run \
  --output outputs/staging-dry-run.json
```

Verify zero writes:

```bash
pytest tests/integration/test_dry_run.py -q
```

The plan MUST show:

- normalized organization identity;
- existing deployment lookup;
- ordered specialist tasks;
- validations;
- inferred fields;
- intended external writes;
- one approval point per write;
- compensation and reconciliation strategy;
- no executed side effects.

## 8. Generate the Staging Deployment Package

```bash
python -m cli.main generate \
  --intake tests/fixtures/staging_client.json \
  --output outputs/agent_forge_staging/
```

Run validators:

```bash
python -m cli.main validate package \
  --path outputs/agent_forge_staging/
```

Run generation tests:

```bash
pytest tests/integration/test_generation_package.py -q
pytest tests/unit/test_vapi_validator.py -q
pytest tests/unit/test_make_validator.py -q
pytest tests/unit/test_sql_validator.py -q
pytest tests/unit/test_nodejs_validator.py -q
pytest tests/unit/test_assembler.py -q
```

Inspect the package manifest:

```bash
python -m cli.main package inspect \
  --path outputs/agent_forge_staging/
```

Expected:

- Every artifact has a hash and trusted agent source.
- Every inferred field is highlighted.
- Every source template and validator version is recorded.
- No unresolved placeholder or foreign-client identifier remains.
- No secret scan finding remains.

## 9. Verify the Backend Candidate Before Writes

### 9.1 Confirm the source path

```bash
test -f "$SERVER_SOURCE_PATH"
```

### 9.2 Run the configured backend test command

```bash
bash -lc "$SERVER_TEST_COMMAND"
```

If this command is empty, fake, or failing, stop. `write_server_file` must remain disabled.

### 9.3 Generate and inspect the diff

```bash
python -m cli.main backend diff \
  --intake tests/fixtures/staging_client.json \
  --source "$SERVER_SOURCE_PATH" \
  --output outputs/agent_forge_staging/server.diff
```

Review:

```bash
sed -n '1,260p' outputs/agent_forge_staging/server.diff
```

Verify:

- HMAC validation is present on new routes.
- No secret is embedded.
- No unrelated client configuration changes.
- The original file hash is recorded.

## 10. Execute the Staging Deployment

Run staging mode only:

```bash
python -m cli.main onboard \
  --intake tests/fixtures/staging_client.json \
  --execute \
  --environment staging
```

**LIVE STAGING WRITES** occur here. Approve each action separately.

Expected action categories include:

1. create or update client database records;
2. create Vapi tools;
3. create Vapi assistant;
4. assign the Vapi phone number;
5. create Make hooks;
6. create Make scenarios from reviewed blueprints;
7. activate scenarios;
8. write the approved backend candidate;
9. set required hosting environment variables;
10. trigger a Render staging deploy.

For every prompt, verify:

- environment is staging;
- organization is `agent_forge_staging`;
- target identifier is expected;
- proposal hash is present;
- validation passed;
- inferred fields are correct;
- compensation or non-reversibility is stated.

Reject immediately if any target is unexpected.

## 11. Verify Live Staging Resources

### 11.1 Reconcile all resources

```bash
python scripts/reconcile_deployment.py \
  --organization agent_forge_staging \
  --environment staging \
  --read-only \
  --output outputs/verification/reconciliation.json
```

### 11.2 Verify Vapi state

```bash
python -m cli.main verify vapi \
  --organization agent_forge_staging
```

Expected:

- Assistant exists.
- Expected tool IDs are attached.
- Phone number points to the staging assistant.
- Server URLs use HTTPS and match the resource registry.

### 11.3 Verify Make state

```bash
python -m cli.main verify make \
  --organization agent_forge_staging
```

Expected:

- Four scenarios exist.
- Scenario blueprints match stored hashes.
- Hooks are attached and not gone.
- Scenarios are active.

### 11.4 Verify Render deploy state

```bash
python -m cli.main verify hosting \
  --service-id "$HOSTING_SERVICE_ID" \
  --wait \
  --timeout-seconds 900
```

Expected terminal state:

```text
live
```

### 11.5 Verify the project-owned health endpoint

```bash
python -m cli.main verify health \
  --url "$HOSTING_HEALTH_URL"
```

Expected JSON includes:

```json
{
  "status": "healthy"
}
```

`"ok"` is also allowed by the contract.

## 12. Verify End-to-End Staging Behavior

Run staging smoke tests:

```bash
pytest -m staging tests/integration -q
```

Verify the four automation capabilities with non-production data:

```bash
python -m cli.main verify capability availability \
  --organization agent_forge_staging

python -m cli.main verify capability booking \
  --organization agent_forge_staging

python -m cli.main verify capability cancellation \
  --organization agent_forge_staging

python -m cli.main verify capability rescheduling \
  --organization agent_forge_staging
```

Verify human transfer separately through the staging Vapi configuration because it has no Make scenario.

## 13. Exercise Failure and Recovery

### 13.1 Run automated failure-injection tests

```bash
pytest tests/failure_injection -q
```

Required cases:

- timeout after remote success;
- failure after each action boundary;
- local receipt persistence failure;
- compensation failure;
- process stop and restart;
- target change while approval is open;
- source template change during a session.

### 13.2 Run a controlled partial deployment simulation

```bash
AGENT_FORGE_FAIL_AFTER_ACTION=make_create_scenario \
python -m cli.main onboard \
  --intake tests/fixtures/staging_client.json \
  --execute \
  --environment staging
```

Expected:

- deployment moves to `recovery_required`;
- completed live resources are listed;
- no blind retry occurs;
- operator receives retry or compensation choices;
- each compensation requires separate approval.

### 13.3 Verify restart recovery

Stop the process while recovery is pending, then run:

```bash
python -m cli.main onboard \
  --intake tests/fixtures/staging_client.json \
  --environment staging
```

Expected: recovery is presented before any new work.

Remove the test-only failure injection after the exercise:

```bash
unset AGENT_FORGE_FAIL_AFTER_ACTION
```

## 14. Verify Audit and Secret Safety

### 14.1 Render deployment history

```bash
python -m cli.main history \
  --organization agent_forge_staging \
  --output outputs/verification/audit-history.json
```

Expected:

- every task and action appears in order;
- each approval binds to a proposal hash;
- external request IDs are present where available;
- corrections and retries are explicit;
- artifact, model, prompt, validator, template, and vendor versions are traceable.

### 14.2 Run secret propagation tests

```bash
pytest tests/security/test_redaction.py -q
pytest tests/security/test_secret_propagation.py -q
```

### 14.3 Scan generated outputs

```bash
python -m cli.main security scan \
  --path outputs/agent_forge_staging/
```

Expected:

```text
Secret scan: PASS
```

## 15. Export and Restore Operational Records

### 15.1 Export staging records

```bash
python scripts/export_internal_tables.py \
  --environment staging \
  --output backups/staging-verification/
```

Verify the manifest:

```bash
python scripts/restore_internal_tables.py \
  --bundle backups/staging-verification/ \
  --dry-run
```

### 15.2 Restore into an isolated target

Never restore into the active internal project.

```bash
python scripts/restore_internal_tables.py \
  --bundle backups/staging-verification/ \
  --target-env-file .env.restore-test \
  --require-empty-target
```

### 15.3 Verify restored recovery queries

```bash
pytest tests/restoration/test_operational_restore.py \
  --restore-env-file .env.restore-test \
  -q
```

Expected:

- manifest hashes pass;
- row counts match;
- foreign keys are valid;
- audit hash chains are complete;
- partial deployment recovery queries still work.

## 16. Run the Full Release Gate

```bash
ruff format --check .
ruff check .
mypy agents orchestrator adapters shared cli scripts
pytest -q
python tests/run_regression_suite.py
python -m cli.main security scan --path outputs/
python scripts/reconcile_deployment.py \
  --organization agent_forge_staging \
  --environment staging \
  --read-only
```

Then complete:

```text
specs/001-agent-forge-onboarding/checklists/staging-readiness.md
```

The staging gate passes only when:

- all mandatory tests pass;
- no critical `/sp.analyze` finding remains;
- no unresolved partial deployment remains;
- no secret appears in persisted or generated artifacts;
- tenant isolation passes positive and negative tests;
- every external resource reconciles;
- backend tests and health verification pass;
- export and isolated restoration pass.

## 17. Clean Up Staging Resources

Cleanup is destructive and MUST use the normal per-action approval flow.

Preview cleanup:

```bash
python -m cli.main cleanup \
  --organization agent_forge_staging \
  --environment staging \
  --dry-run
```

Execute approved cleanup:

```bash
python -m cli.main cleanup \
  --organization agent_forge_staging \
  --environment staging \
  --execute
```

Reconcile after cleanup:

```bash
python scripts/reconcile_deployment.py \
  --organization agent_forge_staging \
  --environment staging \
  --read-only
```

Expected:

- staging scenarios are inactive or deleted as approved;
- staging hooks are deleted as approved;
- staging Vapi resources are deleted or detached as approved;
- operational history remains intact;
- no resource is reported as an unexplained orphan.

## Troubleshooting

### Configuration fails before startup

```bash
python -m cli.main config check
```

Check variable presence and target identity. Do not print variable values.

### Gemini tool smoke test fails

```bash
python -m cli.main smoke-test gemini --verbose-sanitized
```

Verify the pinned Agents SDK, OpenAI client, endpoint, and model identifier. Do not bypass the smoke gate.

### Chroma results are poor

```bash
python scripts/embed_knowledge.py --verify
pytest tests/integration/test_knowledge_search.py -q
```

Do not change the distance threshold without labeled calibration evidence.

### Supabase migration fails

```bash
supabase migration list --linked
supabase db reset
pytest tests/unit/test_sql_validator.py -q
```

Do not rerun production or staging migration commands until the live migration state is reconciled.

### Make create or activation times out

```bash
python -m cli.main reconcile make \
  --organization agent_forge_staging \
  --read-only
```

Do not blindly create another scenario or hook.

### Render deploy fails

```bash
python -m cli.main verify hosting \
  --service-id "$HOSTING_SERVICE_ID"
```

Inspect sanitized deploy status. Rollback requires a separate reviewed action and approval.

## Evidence Produced

A successful run should produce:

```text
outputs/verification/
â”œâ”€â”€ tool-versions.txt
â”œâ”€â”€ staging-schema-diff.sql
â”œâ”€â”€ reconciliation.json
â”œâ”€â”€ audit-history.json
â””â”€â”€ staging-readiness-summary.json

outputs/agent_forge_staging/
â”œâ”€â”€ manifest.json
â”œâ”€â”€ artifacts/
â”œâ”€â”€ validation/
â”œâ”€â”€ server.diff
â””â”€â”€ deployment-summary.md

backups/staging-verification/
â”œâ”€â”€ manifest.json
â””â”€â”€ *.json
```

All evidence MUST be sanitized before review or sharing.