# Agent Forge Environment Setup Guide

This guide helps you configure your `.env` file for Agent Forge.

## Priority Levels

### 🔴 REQUIRED for Smoke Tests
These are needed to run integration tests and verify the foundation:

1. **GEMINI_API_KEY** - AI model access
2. **SUPABASE_INTERNAL_URL** - Operational database
3. **SUPABASE_INTERNAL_SERVICE_ROLE_KEY** - Database access

### 🟡 REQUIRED for Full Functionality
These are needed for actual client deployments:

4. **VAPI_API_KEY** - Voice assistant platform
5. **MAKE_API_TOKEN** - Automation scenarios
6. **SUPABASE_CLIENT_URL** - Client-facing database
7. **SUPABASE_CLIENT_SERVICE_ROLE_KEY** - Client database access
8. **HOSTING_API_TOKEN** - Backend deployment

### 🟢 OPTIONAL
These enhance functionality but aren't blocking:

9. **BRAVE_SEARCH_API_KEY** - External research fallback

---

## Step-by-Step Setup

### 1. Gemini API Key (Google AI)

**What it's for:** AI model calls for agent reasoning and generation

**How to get it:**
1. Go to https://aistudio.google.com/app/apikey
2. Sign in with your Google account
3. Click "Create API Key"
4. Copy the key (starts with `AIza...`)

**Add to .env:**
```bash
GEMINI_API_KEY=AIzaSy...your-actual-key-here
```

**Test it:**
```bash
pytest tests/integration/test_gemini_smoke.py -v -m integration
```

---

### 2. Supabase Internal Project (Operational Data)

**What it's for:** Stores deployment records, task execution history, and operational state

**How to get it:**
1. Go to https://supabase.com/dashboard
2. Sign in or create account
3. Click "New Project"
4. Name it: "agent-forge-internal" (or your choice)
5. Choose a secure database password
6. Wait for project to provision (~2 minutes)
7. Go to Settings → API
8. Copy the **Project URL**
9. Copy the **service_role key** (NOT the anon key)

**Add to .env:**
```bash
SUPABASE_INTERNAL_URL=https://xxxxx.supabase.co
SUPABASE_INTERNAL_SERVICE_ROLE_KEY=eyJhbGc...your-service-role-key
```

**Apply migrations:**
```bash
# Install Supabase CLI if needed
# Then apply migrations:
cd supabase
supabase db push
```

**Test it:**
```bash
pytest tests/integration/test_internal_store.py -v -m integration
```

---

### 3. Optional: Additional Services

#### VAPI (Voice Assistant Platform)
1. Go to https://vapi.ai
2. Sign up for an account
3. Go to Dashboard → API Keys
4. Create a new API key
5. Add to .env: `VAPI_API_KEY=pk_...`

#### Make.com (Automation)
1. Go to https://www.make.com
2. Sign up for an account
3. Go to Profile → API Tokens
4. Create a new token
5. Find your Team ID in the URL
6. Add to .env:
   ```bash
   MAKE_API_TOKEN=your-token
   MAKE_TEAM_ID=your-team-id
   MAKE_ZONE=us1
   ```

#### Supabase Client (Client-Facing Database)
Create a second Supabase project:
1. Name it: "agent-forge-client"
2. Copy URL and service_role key
3. Add to .env:
   ```bash
   SUPABASE_CLIENT_URL=https://yyyyy.supabase.co
   SUPABASE_CLIENT_SERVICE_ROLE_KEY=eyJhbGc...
   ```

---

## Quick Start (Minimal Setup)

For just running smoke tests, you only need:

```bash
# Minimal .env for smoke tests
GEMINI_API_KEY=AIzaSy...
SUPABASE_INTERNAL_URL=https://xxxxx.supabase.co
SUPABASE_INTERNAL_SERVICE_ROLE_KEY=eyJhbGc...

# Leave others empty for now
VAPI_API_KEY=
MAKE_API_TOKEN=
# ... etc
```

---

## Verification Checklist

After configuring your .env:

```bash
# 1. Verify file exists and is not tracked by git
ls -la .env
git status | grep .env  # Should NOT appear

# 2. Run smoke tests
pytest tests/integration/test_gemini_smoke.py -v -m integration
pytest tests/integration/test_internal_store.py -v -m integration

# 3. Verify all unit tests still pass
pytest tests/unit/ tests/security/ -v

# 4. Check configuration is loaded
python -c "from cli.config import load_config; c = load_config(); print('Config loaded successfully')"
```

---

## Security Reminders

- ✅ .env is in .gitignore (never commit it)
- ✅ Use service_role keys only in server environments
- ✅ Rotate keys regularly
- ✅ Keep API keys secret (never share in screenshots/logs)
- ✅ Use different keys for staging vs production

---

## Troubleshooting

**"GEMINI_API_KEY not configured" when running tests**
→ Ensure the key is set in .env and the file is in the project root

**"Connection failed" for Supabase**
→ Check URL format (must include https://)
→ Verify service_role key, not anon key
→ Check if project is paused (free tier pauses after inactivity)

**"ModuleNotFoundError: No module named 'supabase'"**
→ Install dependencies: `pip install -r requirements.txt`

---

## Next Steps After Setup

1. Run integration tests to verify connectivity
2. Apply Supabase migrations
3. Load constitution into ChromaDB
4. Test a dry-run deployment
5. Begin client onboarding workflow

Need help with any specific service? Let me know!
