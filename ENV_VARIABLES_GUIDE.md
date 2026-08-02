# Environment Variables Guide - Agent Forge

This guide explains each environment variable required by Agent Forge.

## Current Status

✅ **Configured:**
- `SUPABASE_INTERNAL_URL` - Internal Supabase database URL
- `SUPABASE_INTERNAL_SERVICE_ROLE_KEY` - Internal database service key
- `GEMINI_API_KEY` - Google Gemini API for AI model calls (if set)
- `AGENT_FORGE_ENV` - Runtime environment (staging/production)
- `CHROMA_PERSIST_DIR` - Local vector database directory

❌ **Missing (Required):**

### External Platforms

#### VAPI (Voice Assistant Platform)
```bash
VAPI_API_KEY=your_vapi_api_key_here
```
- **Purpose:** Manages voice assistants for client organizations
- **Get it from:** https://vapi.ai → Dashboard → API Keys
- **Used for:** Creating/updating voice assistants, phone numbers, tools

#### Make.com (Automation Platform)
```bash
MAKE_API_TOKEN=your_make_api_token_here
MAKE_TEAM_ID=your_make_team_id_here
MAKE_ZONE=us1  # or eu1, eu2, us2
```
- **Purpose:** Manages automation scenarios (webhooks, workflows)
- **Get it from:** https://www.make.com → Profile → API
- **Used for:** Creating and managing Make scenarios for organizations

#### Supabase Client Project (Tenant Data)
```bash
SUPABASE_CLIENT_URL=https://your-client-project.supabase.co
SUPABASE_CLIENT_SERVICE_ROLE_KEY=your_client_service_role_key
```
- **Purpose:** Stores client organization data (separate from internal ops)
- **Get it from:** Supabase Dashboard → Project Settings → API
- **Note:** This is DIFFERENT from your internal Supabase (already configured)
- **Used for:** Storing client-specific schemas, business data

#### Supabase Project Reference (Optional)
```bash
SUPABASE_PROJECT_REF_STAGING=your_project_ref
```
- **Purpose:** Project reference ID for staging environment
- **Get it from:** Supabase Dashboard → Project Settings → General
- **Optional:** Only needed if running in staging mode

#### Hosting Provider (Render, Railway, etc.)
```bash
HOSTING_API_TOKEN=your_hosting_api_token
HOSTING_SERVICE_ID=your_service_id
HOSTING_HEALTH_URL=https://your-backend.onrender.com/health
```
- **Purpose:** Manages backend service deployments
- **Get it from:** Your hosting provider's API/settings page
- **Used for:** Deploying and monitoring backend services

#### Brave Search (Research Fallback)
```bash
BRAVE_SEARCH_API_KEY=your_brave_api_key
```
- **Purpose:** External research and information gathering
- **Get it from:** https://brave.com/search/api/
- **Used for:** Fallback for external knowledge queries

### Local Configuration

#### Server Source Path
```bash
SERVER_SOURCE_PATH=./backend/server.js
```
- **Purpose:** Path to your backend source code
- **Used for:** Code analysis and modifications
- **Example:** `./backend/server.js` or `./src/app.py`

#### Server Test Command
```bash
SERVER_TEST_COMMAND=npm test
```
- **Purpose:** Command to run backend tests before deployments
- **Used for:** Validation before applying changes
- **Example:** `npm test`, `pytest`, `npm run test:integration`

---

## Setup Priority

### Critical for Basic Operation (Must Have):
1. ✅ `SUPABASE_INTERNAL_URL` + `SUPABASE_INTERNAL_SERVICE_ROLE_KEY` (Done)
2. ❌ `SUPABASE_CLIENT_URL` + `SUPABASE_CLIENT_SERVICE_ROLE_KEY`
3. ❌ `GEMINI_API_KEY` (if not already set)

### For Full Deployment Capability:
4. ❌ `VAPI_API_KEY`
5. ❌ `MAKE_API_TOKEN` + `MAKE_TEAM_ID`
6. ❌ `HOSTING_API_TOKEN` + `HOSTING_SERVICE_ID` + `HOSTING_HEALTH_URL`

### Nice to Have:
7. ❌ `BRAVE_SEARCH_API_KEY`
8. ❌ `SERVER_SOURCE_PATH` + `SERVER_TEST_COMMAND`

---

## Testing Configuration

After adding variables to `.env`, test with:

```bash
# Test configuration loading
python -c "from cli.config import load_config, display_config; config = load_config(); print(display_config(config))"
```

This will:
- ✅ Verify all required variables are present
- ✅ Show redacted values for security
- ✅ Validate URLs and formats
- ❌ Error if anything is missing or invalid

---

## Example .env Structure

```bash
# ============================================
# Model Provider
# ============================================
GEMINI_API_KEY=AIza...

# ============================================
# External Platforms
# ============================================
VAPI_API_KEY=sk-...
MAKE_API_TOKEN=...
MAKE_TEAM_ID=...
MAKE_ZONE=us1

# Client-facing Supabase (tenant data)
SUPABASE_CLIENT_URL=https://xyz.supabase.co
SUPABASE_CLIENT_SERVICE_ROLE_KEY=eyJ...

# Internal Supabase (operational records) - ALREADY CONFIGURED
SUPABASE_INTERNAL_URL=https://abc.supabase.co
SUPABASE_INTERNAL_SERVICE_ROLE_KEY=eyJ...

# Hosting provider
HOSTING_API_TOKEN=...
HOSTING_SERVICE_ID=srv-...
HOSTING_HEALTH_URL=https://...

# Brave Search
BRAVE_SEARCH_API_KEY=BSA...

# ============================================
# Local Configuration
# ============================================
CHROMA_PERSIST_DIR=./chroma_data
SERVER_SOURCE_PATH=./backend/server.js
SERVER_TEST_COMMAND=npm test

# ============================================
# Runtime Environment
# ============================================
AGENT_FORGE_ENV=staging
```

---

## Security Notes

- ⚠️ Never commit `.env` to version control
- ✅ `.env` is already in `.gitignore`
- 🔒 Use service role keys, not anon keys
- 🔒 All API tokens should be kept secret
- 🌐 All external URLs must use HTTPS
