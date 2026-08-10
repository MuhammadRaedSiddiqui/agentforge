# Gotcha: Make.com Blueprint Must Strip Metadata Before API Call

**Platform:** Make.com  
**Topic:** Blueprint Structure  
**Symptom:** 400 Bad Request when creating scenario with blueprint containing metadata fields  
**Verification Status:** Verified  
**Approved By:** system  
**Approved At:** 2026-08-03

## Root Cause

Make.com blueprint files downloaded from the UI or stored in templates contain metadata fields like `teamId`, `description`, and `scheduling` at the top level. However, when creating a scenario via the API, these fields must be:

1. **Removed from the blueprint** (passed separately in the request payload)
2. **Or cause 400 Bad Request** if left in the blueprint

The API expects:
- `blueprint` field containing only the scenario flow and configuration
- `scheduling` field at the payload level (not inside blueprint)
- `teamId` is inferred from the API endpoint path, not from blueprint

**Wrong:**
```python
blueprint = {
    "name": "Booking",
    "teamId": 12345,           # ❌ Must remove
    "description": "...",      # ❌ Must remove
    "scheduling": {...},       # ❌ Must remove
    "flow": [...],
    "metadata": {...}
}
```

**Correct:**
```python
# Strip metadata from blueprint
clean_blueprint = {
    "name": blueprint["name"],
    "flow": blueprint["flow"],
    "metadata": blueprint["metadata"]
}

# Pass scheduling separately
payload = {
    "blueprint": json.dumps(clean_blueprint),
    "scheduling": {"type": "immediately"}
}
```

## Resolution

1. **Strip metadata fields before API call:**
   ```python
   # In orchestrator/make_deployer.py or adapters/make.py
   
   def clean_blueprint_for_api(blueprint: dict) -> dict:
       """Remove fields that must be passed separately in API payload."""
       clean = blueprint.copy()
       
       # Remove metadata fields
       for field in ["teamId", "description", "scheduling"]:
           clean.pop(field, None)
       
       return clean
   ```

2. **Validate blueprint structure before API call:**
   ```python
   # In agents/make_agent/validator.py
   
   def validate_blueprint_for_api(blueprint: dict) -> list[str]:
       """Validate blueprint is ready for API submission."""
       errors = []
       
       # Check for fields that should not be in blueprint
       forbidden_fields = ["teamId", "description", "scheduling"]
       for field in forbidden_fields:
           if field in blueprint:
               errors.append(
                   f"Blueprint contains '{field}' which must be removed before API call"
               )
       
       return errors
   ```

3. **Separate concerns in deployment:**
   ```python
   # Load raw blueprint from template
   with open(blueprint_path) as f:
       raw_blueprint = json.load(f)
   
   # Extract scheduling if present
   scheduling = raw_blueprint.pop("scheduling", {"type": "immediately"})
   
   # Clean blueprint for API
   clean_blueprint = clean_blueprint_for_api(raw_blueprint)
   
   # Create scenario with clean blueprint + separate scheduling
   result = make_adapter.create_scenario(
       blueprint=clean_blueprint,
       scheduling=scheduling,
       confirmed=True
   )
   ```

## Detection

```python
# Check if blueprint has forbidden metadata fields
forbidden_fields = ["teamId", "description", "scheduling"]
found_forbidden = [f for f in forbidden_fields if f in blueprint]

if found_forbidden:
    raise ValidationError(
        f"Blueprint contains forbidden fields that must be removed: {found_forbidden}. "
        "These should be passed separately in the API payload."
    )
```

## Prevention

- Always clean blueprints before API submission
- Store templates with metadata but strip before use
- Add validation step in blueprint loading
- Document which fields are metadata vs blueprint structure
- Test with real Make.com API to catch metadata field rejections

## Common Causes

- Using blueprint files directly from Make.com UI export
- Not reading Make.com API documentation about blueprint structure
- Assuming blueprint can contain all fields from GET response
- Copy-pasting blueprint structure from UI without cleaning

## Affected Fields

| Field | Where It Goes | Notes |
|-------|---------------|-------|
| `teamId` | API endpoint path | `/teams/{teamId}/scenarios` |
| `scheduling` | Payload top-level | `{"blueprint": "...", "scheduling": {...}}` |
| `description` | Not used in API | Optional field, can be omitted |
| `name` | Inside blueprint | Required in blueprint |
| `flow` | Inside blueprint | Required in blueprint |
| `metadata` | Inside blueprint | Required in blueprint |

## Related Issues

- `update_scenario_blueprint` (PUT) also requires clean blueprint
- GET blueprint response includes these fields, so they must be stripped when updating

## References

- Make.com Scenarios API: https://developers.make.com/api-documentation/api-reference/scenarios
- Agent Forge Deployer: orchestrator/make_deployer.py - _load_blueprint()
- Research Date: 2026-08-03
