"""
Shared pytest configuration.

Agent Forge reads platform credentials and model-provider settings straight
from the environment, and adapters resolve them at construction time. A
developer with a populated `.env` therefore has real staging credentials in
scope for every test run, and a unit test that constructs an adapter can reach
a live API without anything in the test itself looking like it would.

That is not hypothetical: `tests/integration/test_gemini_smoke.py` made a live
call during a full-suite run and hung it until the timeout fired.

This fixture replaces every credential and endpoint variable with an obviously
fake sentinel for any test *not* marked `integration` or `staging`. Those two
markers opt back into the real environment, because reaching real services is
the point of those suites.
"""

import os
from pathlib import Path

import pytest

# Credentials and endpoints that could reach an external service if real.
# Keep in sync with the adapters' `_load_*` helpers and adapters/model_wrapper.py.
_STUBBED_ENV = {
    # Model providers
    "MODEL_PROVIDER": "gemini",
    "MODEL_NAME": "test-model",
    "MODEL_BASE_URL": "http://localhost.invalid/v1/",
    "GEMINI_API_KEY": "test-gemini-key",
    "OPENAI_API_KEY": "test-openai-key",
    "META_API_KEY": "test-meta-key",
    # Bedrock
    "AWS_ACCESS_KEY_ID": "test-aws-access-key-id",
    "AWS_SECRET_ACCESS_KEY": "test-aws-secret-access-key",
    "AWS_REGION": "us-east-1",
    "BEDROCK_MODEL_ID": "test-bedrock-model",
    # Vapi
    "VAPI_API_KEY": "test-vapi-key",
    "VAPI_PHONE_NUMBER_ID": "test-phone-number-id",
    # Make
    "MAKE_API_TOKEN": "test-make-token",
    "MAKE_TEAM_ID": "000000",
    "MAKE_ZONE": "us1",
    "MAKE_SUPABASE_CONNECTION_ID": "000000",
    # Hosting (Render)
    "HOSTING_API_TOKEN": "test-hosting-token",
    "HOSTING_SERVICE_ID": "srv-test",
    "HOSTING_HEALTH_URL": "https://localhost.invalid/health",
    # Client-facing Supabase project
    "SUPABASE_CLIENT_URL": "https://localhost.invalid",
    "SUPABASE_CLIENT_SERVICE_ROLE_KEY": "test-client-service-role-key",
    "SUPABASE_PROJECT_REF_STAGING": "test-project-ref",
    # Internal operational store
    "SUPABASE_INTERNAL_URL": "https://localhost.invalid",
    "SUPABASE_INTERNAL_SERVICE_ROLE_KEY": "test-internal-service-role-key",
    # Knowledge retrieval
    "BRAVE_SEARCH_API_KEY": "test-brave-key",
    # Environment guard — never let a test think it is in production
    "AGENT_FORGE_ENV": "staging",
}

# Required by load_config() but pointing at paths rather than services. Set to a
# per-test temp directory so a test that actually writes cannot land in the repo.
_STUBBED_PATH_ENV = ("CHROMA_PERSIST_DIR", "SERVER_SOURCE_PATH")


@pytest.fixture(autouse=True)
def stub_external_credentials(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Replace real credentials with sentinels outside integration/staging tests.

    `_STUBBED_ENV` must cover every variable `load_config()` lists as required
    (cli/config.py). Masking is not enough: a developer's .env supplies the real
    ones, so an omission here passes locally and fails only on a clean checkout
    where the variable never existed to be overwritten. That is exactly how
    SUPABASE_INTERNAL_URL, BRAVE_SEARCH_API_KEY and the two path variables
    reached CI unset.
    """
    if request.node.get_closest_marker("integration") or request.node.get_closest_marker("staging"):
        return

    for key, value in _STUBBED_ENV.items():
        monkeypatch.setenv(key, value)

    for key in _STUBBED_PATH_ENV:
        monkeypatch.setenv(key, str(tmp_path / key.lower()))

    monkeypatch.setenv("SERVER_TEST_COMMAND", "true")

    # Credential names vary by deployment, so clear anything that looks like a
    # Supabase credential rather than enumerating every variant.
    for key in list(os.environ):
        if key.startswith("SUPABASE_") and key not in _STUBBED_ENV:
            monkeypatch.setenv(key, "test-internal-placeholder")
