# Gotcha: Make.com Blueprint Must Be JSON-Stringified in API Payload

**Platform:** Make.com  
**Topic:** API Request Format  
**Symptom:** 400 Bad Request when creating scenario with blueprint object  
**Verification Status:** Verified  
**Approved By:** system  
**Approved At:** 2026-08-03

## Root Cause

Make.com's scenario creation API endpoint (`POST /scenarios`) requires the `blueprint` field to be a **JSON-encoded string**, not a nested object. If you pass the blueprint as a Python dict/object directly, the API returns 400 Bad Request with an error indicating the blueprint format is invalid.

**Wrong:**
```python
payload = {
    "blueprint": {
        "name": "My Scenario",
        "flow": [...]  # ❌ Object, not string
    },
    "scheduling": {"type": "immediately"}
}
```

**Correct:**
```python
payload = {
    "blueprint": json.dumps({
        "name": "My Scenario",
        "flow": [...]  # ✅ JSON-stringified
    }),
    "scheduling": {"type": "immediately"}
}
```

## Resolution

1. **Always JSON-stringify blueprint before API call:**
   ```python
   # In adapters/make.py - create_scenario()
   
   payload = {
       "blueprint": json.dumps(blueprint),  # Must be string
       "scheduling": scheduling
   }
   
   response = self._request(
       method="POST",
       endpoint=f"/teams/{self.team_id}/scenarios",
       json=payload
   )
   ```

2. **Validate blueprint is stringified:**
   ```python
   # Before API call
   if not isinstance(payload.get("blueprint"), str):
       raise ValueError("Blueprint must be JSON-stringified string, not object")
   ```

3. **Handle in adapter layer, not caller:**
   ```python
   # Callers pass blueprint as dict
   result = make_adapter.create_scenario(
       blueprint={"name": "...", "flow": [...]},  # Dict is fine here
       scheduling={"type": "immediately"}
   )
   
   # Adapter stringifies internally
   def create_scenario(self, blueprint: dict, scheduling: dict) -> AdapterReceipt:
       payload = {
           "blueprint": json.dumps(blueprint),  # Adapter handles stringification
           "scheduling": scheduling
       }
       return self._request("POST", f"/teams/{self.team_id}/scenarios", json=payload)
   ```

## Detection

```python
# If you see 400 Bad Request with message about blueprint format
try:
    response = make_adapter.create_scenario(blueprint, scheduling)
except requests.exceptions.HTTPError as e:
    if e.response.status_code == 400:
        error_msg = e.response.json().get("message", "")
        if "blueprint" in error_msg.lower():
            # Likely blueprint not stringified
            raise ValueError(
                "Blueprint must be JSON-stringified. "
                f"Original error: {error_msg}"
            ) from e
```

## Prevention

- Always stringify blueprint in the adapter layer
- Document this requirement in adapter method docstrings
- Add validation that blueprint is a string before API call
- Test with real Make.com API, not just mocks

## Common Causes

- Assuming blueprint can be passed as nested JSON object
- Not reading Make.com API documentation carefully (requirement is easy to miss)
- Copying examples from other APIs that accept nested objects

## Related Issues

- The `update_scenario_blueprint` endpoint (PUT) also requires stringified blueprint
- When retrieving a blueprint with GET, the response returns it as a string that must be JSON-parsed

## References

- Make.com Scenarios API: https://developers.make.com/api-documentation/api-reference/scenarios
- Agent Forge Adapter: adapters/make.py - create_scenario(), update_scenario_blueprint()
- Research Date: 2026-08-03
