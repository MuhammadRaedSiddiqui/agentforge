# Gotcha: Make.com API Requires Team ID, Not Organization ID

**Platform:** Make.com  
**Topic:** API Authentication  
**Symptom:** API calls return 403 Forbidden or 404 Not Found when using organization ID  
**Verification Status:** Verified  
**Approved By:** system  
**Approved At:** 2026-08-03

## Root Cause

Make.com's API documentation and UI display both "Organization ID" and "Team ID", but the REST API endpoints require the Team ID for resource operations. Using the organization ID will result in 403 (permission denied) or 404 (resource not found) errors, even with a valid API token.

The Organization ID and Team ID are different values with different formats:
- Organization ID: typically numeric (e.g., `12345`)
- Team ID: typically numeric but different value (e.g., `67890`)

## Resolution

1. **Use Team ID from environment configuration:**
   ```python
   # Correct - uses Team ID
   team_id = os.getenv("MAKE_TEAM_ID")
   url = f"https://{zone}.make.com/api/v2/teams/{team_id}/scenarios"
   
   # Wrong - uses Organization ID
   org_id = os.getenv("MAKE_ORG_ID")  # DO NOT USE
   url = f"https://{zone}.make.com/api/v2/organizations/{org_id}/scenarios"  # FAILS
   ```

2. **Verify Team ID in Make.com dashboard:**
   - Navigate to Team settings in Make.com UI
   - Copy the Team ID value (not Organization ID)
   - Set `MAKE_TEAM_ID` in `.env`

3. **Update configuration validation:**
   ```python
   # In cli/config.py
   if not config.make_team_id:
       raise ConfigurationError("MAKE_TEAM_ID required (not Organization ID)")
   ```

## Detection

```python
# Test Team ID validity
try:
    response = requests.get(
        f"https://{zone}.make.com/api/v2/teams/{team_id}/scenarios",
        headers={"Authorization": f"Token {api_token}"},
        timeout=10
    )
    if response.status_code in (403, 404):
        raise ConfigurationError(
            "Invalid Team ID. Verify MAKE_TEAM_ID is set to Team ID, not Organization ID."
        )
except requests.exceptions.RequestException as e:
    raise ConfigurationError(f"Cannot validate Team ID: {e}")
```

## Prevention

- Store Team ID in environment variable, not Organization ID
- Validate Team ID on first API call (fail fast)
- Document the difference clearly in `.env.example`
- Add smoke test that verifies Team ID works

## Common Causes

- Copying Organization ID instead of Team ID from Make.com dashboard
- Confusing the two IDs when both are visible in the UI
- Using API documentation examples that show placeholder IDs without clarifying which is which

## Related Issues

- Connection IDs also differ between teams and cannot be shared across organizations
- Webhook URLs are team-specific

## References

- Make.com API Docs: https://developers.make.com/api-documentation/api-reference
- Agent Forge Adapter: adapters/make.py
- Configuration: cli/config.py
- Research Date: 2026-08-03
