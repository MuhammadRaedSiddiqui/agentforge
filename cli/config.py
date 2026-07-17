"""
Configuration loader and validator for Agent Forge.

Loads environment variables, validates presence, and provides redacted display.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class AgentForgeConfig:
    """Agent Forge runtime configuration."""

    # Model provider
    gemini_api_key: str

    # External platforms
    vapi_api_key: str
    make_api_token: str
    make_team_id: str
    make_zone: str

    # Supabase projects
    supabase_client_url: str
    supabase_client_service_role_key: str
    supabase_internal_url: str
    supabase_internal_service_role_key: str
    supabase_project_ref_staging: str | None

    # Hosting provider
    hosting_api_token: str
    hosting_service_id: str
    hosting_health_url: str

    # Brave Search
    brave_search_api_key: str

    # Local configuration
    chroma_persist_dir: str
    server_source_path: str
    server_test_command: str

    # Runtime environment
    agent_forge_env: str

    @property
    def is_staging(self) -> bool:
        """Check if running in staging mode."""
        return self.agent_forge_env.lower() == "staging"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.agent_forge_env.lower() == "production"


class ConfigurationError(Exception):
    """Configuration validation error."""

    pass


def _redact_secret(value: str, visible_chars: int = 4) -> str:
    """
    Redact a secret value, showing only first few characters.

    Args:
        value: The secret value to redact
        visible_chars: Number of characters to show (default 4)

    Returns:
        Redacted string like "sk-a***" (hides all but first 4 chars)
    """
    if not value or len(value) <= visible_chars:
        return "***"
    return f"{value[:visible_chars]}***"


def _check_production_identifiers(config: AgentForgeConfig) -> list[str]:
    """
    Check for production-looking identifiers when in staging mode.

    Returns:
        List of warning messages for production-looking values
    """
    warnings: list[str] = []

    if not config.is_staging:
        return warnings

    # Check for production keywords in URLs and identifiers
    production_keywords = ["prod", "production", "live", "main"]

    fields_to_check = {
        "SUPABASE_CLIENT_URL": config.supabase_client_url,
        "SUPABASE_INTERNAL_URL": config.supabase_internal_url,
        "HOSTING_SERVICE_ID": config.hosting_service_id,
        "HOSTING_HEALTH_URL": config.hosting_health_url,
    }

    for field_name, field_value in fields_to_check.items():
        lower_value = field_value.lower()
        for keyword in production_keywords:
            if keyword in lower_value:
                warnings.append(f"⚠️  {field_name} contains '{keyword}' but AGENT_FORGE_ENV=staging")

    return warnings


def load_config(env_file: str | None = None) -> AgentForgeConfig:
    """
    Load and validate Agent Forge configuration from environment.

    Args:
        env_file: Optional path to .env file (defaults to .env in current directory)

    Returns:
        Validated AgentForgeConfig instance

    Raises:
        ConfigurationError: If required variables are missing or invalid
    """
    # Load environment variables
    if env_file:
        env_path = Path(env_file)
        if not env_path.exists():
            raise ConfigurationError(f"Environment file not found: {env_file}")
        load_dotenv(env_path)
    else:
        # Load from .env in current directory if it exists
        load_dotenv()

    # Required variables
    required_vars = {
        "GEMINI_API_KEY": "gemini_api_key",
        "VAPI_API_KEY": "vapi_api_key",
        "MAKE_API_TOKEN": "make_api_token",
        "MAKE_TEAM_ID": "make_team_id",
        "MAKE_ZONE": "make_zone",
        "SUPABASE_CLIENT_URL": "supabase_client_url",
        "SUPABASE_CLIENT_SERVICE_ROLE_KEY": "supabase_client_service_role_key",
        "SUPABASE_INTERNAL_URL": "supabase_internal_url",
        "SUPABASE_INTERNAL_SERVICE_ROLE_KEY": "supabase_internal_service_role_key",
        "HOSTING_API_TOKEN": "hosting_api_token",
        "HOSTING_SERVICE_ID": "hosting_service_id",
        "HOSTING_HEALTH_URL": "hosting_health_url",
        "BRAVE_SEARCH_API_KEY": "brave_search_api_key",
        "CHROMA_PERSIST_DIR": "chroma_persist_dir",
        "SERVER_SOURCE_PATH": "server_source_path",
        "SERVER_TEST_COMMAND": "server_test_command",
        "AGENT_FORGE_ENV": "agent_forge_env",
    }

    # Optional variables
    optional_vars = {
        "SUPABASE_PROJECT_REF_STAGING": "supabase_project_ref_staging",
    }

    # Check for missing required variables
    missing_vars = []
    config_values: dict[str, str | None] = {}

    for env_var, field_name in required_vars.items():
        value = os.getenv(env_var)
        if not value:
            missing_vars.append(env_var)
        else:
            config_values[field_name] = value

    if missing_vars:
        raise ConfigurationError(
            f"Missing required environment variables: {', '.join(missing_vars)}"
        )

    # Add optional variables
    for env_var, field_name in optional_vars.items():
        config_values[field_name] = os.getenv(env_var)

    # Create config instance
    config = AgentForgeConfig(
        gemini_api_key=config_values["gemini_api_key"] or "",
        vapi_api_key=config_values["vapi_api_key"] or "",
        make_api_token=config_values["make_api_token"] or "",
        make_team_id=config_values["make_team_id"] or "",
        make_zone=config_values["make_zone"] or "",
        supabase_client_url=config_values["supabase_client_url"] or "",
        supabase_client_service_role_key=config_values["supabase_client_service_role_key"] or "",
        supabase_internal_url=config_values["supabase_internal_url"] or "",
        supabase_internal_service_role_key=config_values["supabase_internal_service_role_key"]
        or "",
        supabase_project_ref_staging=config_values["supabase_project_ref_staging"],
        hosting_api_token=config_values["hosting_api_token"] or "",
        hosting_service_id=config_values["hosting_service_id"] or "",
        hosting_health_url=config_values["hosting_health_url"] or "",
        brave_search_api_key=config_values["brave_search_api_key"] or "",
        chroma_persist_dir=config_values["chroma_persist_dir"] or "",
        server_source_path=config_values["server_source_path"] or "",
        server_test_command=config_values["server_test_command"] or "",
        agent_forge_env=config_values["agent_forge_env"] or "",
    )

    # Validate AGENT_FORGE_ENV
    if config.agent_forge_env not in ["staging", "production"]:
        raise ConfigurationError(
            f"AGENT_FORGE_ENV must be 'staging' or 'production', got: {config.agent_forge_env}"
        )

    # Validate MAKE_ZONE
    valid_zones = ["eu1", "eu2", "us1", "us2"]
    if config.make_zone not in valid_zones:
        raise ConfigurationError(f"MAKE_ZONE must be one of {valid_zones}, got: {config.make_zone}")

    # Validate URLs
    if not config.hosting_health_url.startswith("https://"):
        raise ConfigurationError(
            f"HOSTING_HEALTH_URL must use HTTPS, got: {config.hosting_health_url}"
        )

    # Check for production identifiers in staging mode
    prod_warnings = _check_production_identifiers(config)
    if prod_warnings:
        error_msg = "\n".join(["Production identifiers detected in staging mode:"] + prod_warnings)
        raise ConfigurationError(error_msg)

    return config


def display_config(config: AgentForgeConfig) -> str:
    """
    Generate a redacted display of the current configuration.

    Args:
        config: The configuration to display

    Returns:
        Multi-line string with redacted configuration
    """
    lines = [
        "Agent Forge Configuration",
        "=" * 50,
        "",
        f"Environment: {config.agent_forge_env.upper()}",
        "",
        "Model Provider:",
        f"  GEMINI_API_KEY: {_redact_secret(config.gemini_api_key)}",
        "",
        "External Platforms:",
        f"  VAPI_API_KEY: {_redact_secret(config.vapi_api_key)}",
        f"  MAKE_API_TOKEN: {_redact_secret(config.make_api_token)}",
        f"  MAKE_TEAM_ID: {config.make_team_id}",
        f"  MAKE_ZONE: {config.make_zone}",
        "",
        "Supabase (Client):",
        f"  URL: {config.supabase_client_url}",
        f"  Service Role Key: {_redact_secret(config.supabase_client_service_role_key)}",
        "",
        "Supabase (Internal):",
        f"  URL: {config.supabase_internal_url}",
        f"  Service Role Key: {_redact_secret(config.supabase_internal_service_role_key)}",
    ]

    if config.supabase_project_ref_staging:
        lines.append(f"  Staging Project Ref: {config.supabase_project_ref_staging}")

    lines.extend(
        [
            "",
            "Hosting Provider:",
            f"  API Token: {_redact_secret(config.hosting_api_token)}",
            f"  Service ID: {config.hosting_service_id}",
            f"  Health URL: {config.hosting_health_url}",
            "",
            "Brave Search:",
            f"  API Key: {_redact_secret(config.brave_search_api_key)}",
            "",
            "Local Configuration:",
            f"  Chroma Persist Dir: {config.chroma_persist_dir}",
            f"  Server Source Path: {config.server_source_path}",
            f"  Server Test Command: {'(configured)' if config.server_test_command else '(not configured)'}",
            "",
            "✓ All required variables present",
            "✓ No secrets displayed",
        ]
    )

    return "\n".join(lines)
