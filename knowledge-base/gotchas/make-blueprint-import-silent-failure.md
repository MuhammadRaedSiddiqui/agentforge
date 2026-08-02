# Gotcha: Make.com Scenario Blueprint Import Fails Silently

**Platform:** Make.com  
**Topic:** Scenario Import  
**Symptom:** Blueprint import returns 200 OK but scenario is not created or is created with incorrect configuration  
**Verification Status:** Verified  
**Approved By:** system  
**Approved At:** 2026-07-14

## Root Cause

Make.com's blueprint import API (`POST /scenarios/import`) can return HTTP 200 even when the blueprint contains validation errors or incompatible module configurations. The scenario may be created in a disabled state or with missing modules, but the API response doesn't indicate the problem.

## Resolution

1. **Always verify scenario after import:**
   ```python
   # After import
   import_response = make_adapter.import_blueprint(blueprint)
   scenario_id = import_response.get("scenario", {}).get("id")
   
   # Verify with GET
   scenario = make_adapter.get_scenario(scenario_id)
   
   # Check for issues
   if scenario.get("isDisabled"):
       raise ValidationError("Scenario created but disabled")
   
   if len(scenario.get("modules", [])) != expected_module_count:
       raise ValidationError("Scenario missing modules")
   ```

2. **Reconcile blueprint hash:**
   ```python
   # Compare expected vs actual blueprint
   actual_blueprint = make_adapter.get_blueprint(scenario_id)
   actual_hash = hash_json(actual_blueprint)
   
   if actual_hash != expected_hash:
       # Scenario differs from blueprint
       # List differences and decide: accept, retry, or compensate
   ```

3. **Pre-validate blueprint structure:**
   - Check all required module types exist
   - Validate connection IDs reference actual connections
   - Ensure webhook URLs are HTTPS
   - Verify scheduling configuration is complete

## Detection

```python
# After blueprint import
scenario = make_adapter.get_scenario(scenario_id)

# Check for silent failures
checks = [
    scenario.get("isDisabled") == False,
    len(scenario.get("modules", [])) > 0,
    scenario.get("teamId") == expected_team_id,
]

if not all(checks):
    # Silent import failure detected
    compensate_or_retry()
```

## Prevention

- Validate blueprint structure before import
- Always verify scenario after creation
- Store blueprint hash with scenario for reconciliation
- Monitor Make.com API changelog for import behavior changes
- Use scenario templates that have been verified in staging

## Common Causes

- Invalid connection IDs in blueprint
- Deprecated module types
- Missing required module parameters
- Team ID mismatch
- Quota limits reached but not reported

## Related Issues

- Hook creation can also succeed without actually creating webhook
- Scenario activation may appear successful but scenario remains paused

## References

- Make.com Scenarios API: https://developers.make.com/api-documentation/api-reference/scenarios
- Make.com Blueprints: https://developers.make.com/api-documentation/api-reference/scenarios/blueprints
- Agent Forge Validation: agents/make_agent/validator.py
- Research Date: 2026-07-14
