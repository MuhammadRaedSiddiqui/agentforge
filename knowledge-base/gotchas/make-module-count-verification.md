# Gotcha: Make.com Scenario Module Count Validation Required

**Platform:** Make.com  
**Topic:** Blueprint Deployment Verification  
**Symptom:** Scenarios created successfully but with fewer modules than expected, causing runtime failures  
**Verification Status:** Verified  
**Approved By:** system  
**Approved At:** 2026-08-03

## Root Cause

Make.com's scenario creation API can succeed but create a scenario with fewer modules than expected from the blueprint. This happens when:
- Some modules in the blueprint are silently rejected due to validation errors
- Connection IDs in the blueprint are invalid or expired
- Module parameters don't meet API validation rules (not always reported in response)
- The API returns 200 OK but the scenario is incomplete

Without explicit module count verification, these incomplete scenarios go undetected until runtime when they fail because expected modules are missing.

## Expected Module Counts

Each capability scenario has a known module count:

| Capability | Expected Modules | Description |
|------------|------------------|-------------|
| **availability** | 4 | Webhook trigger + availability check + response formatter + webhook response |
| **booking** | 5 | Webhook trigger + database insert (createARow with generated appointment_id) + availability update + response formatter + webhook response |
| **cancellation** | 8 | Webhook trigger + lookup + router (found/not found) + database update + notification + 2 error handlers + response |
| **rescheduling** | 10 | Webhook trigger + validation + lookup + router + availability check + update + conflict handler + notification + error handler + response |

## Resolution

1. **Verify module count after scenario creation:**
   ```python
   # In orchestrator/make_deployer.py
   
   EXPECTED_MODULE_COUNTS = {
       "availability": 4,
       "booking": 5,
       "cancellation": 8,
       "rescheduling": 10,
   }
   
   def verify_module_count(scenario_id: int, capability: str) -> bool:
       """Verify scenario has expected number of modules."""
       # Get scenario blueprint
       receipt = make_adapter.get_scenario_blueprint(scenario_id)
       blueprint = json.loads(receipt.response_data.get("blueprint", "{}"))
       
       # Count modules in flow
       actual_count = len(blueprint.get("flow", []))
       expected_count = EXPECTED_MODULE_COUNTS.get(capability)
       
       if expected_count is None:
           logger.warning(f"No expected module count for capability: {capability}")
           return True
       
       if actual_count != expected_count:
           logger.error(
               f"Module count mismatch for {capability}: "
               f"expected {expected_count}, got {actual_count}"
           )
           return False
       
       return True
   ```

2. **MakeScenarioDeployer automatic verification:**
   ```python
   # Already implemented in orchestrator/make_deployer.py
   
   def deploy_scenario(self, capability: str, blueprint_path: str, ...) -> dict:
       # ... create scenario ...
       
       # Verify module count
       blueprint = self.adapter.get_scenario_blueprint(scenario_id)
       actual_count = len(json.loads(blueprint.response_data["blueprint"]).get("flow", []))
       expected_count = EXPECTED_MODULE_COUNTS.get(capability, 0)
       
       if actual_count != expected_count:
           logger.warning(
               f"Module count mismatch: expected {expected_count}, got {actual_count}"
           )
       
       return {
           "scenario_id": scenario_id,
           "module_count": actual_count,
           "module_count_match": actual_count == expected_count,
           ...
       }
   ```

3. **Fallback strategy when count is wrong:**
   ```python
   # If module count doesn't match after creation
   if not verify_module_count(scenario_id, capability):
       # Try stub + update fallback
       logger.info("Module count mismatch, trying stub + update fallback")
       
       # Create minimal stub scenario
       stub_blueprint = create_stub_blueprint(capability, hook_url)
       stub_scenario = make_adapter.create_scenario(stub_blueprint, scheduling)
       stub_id = stub_scenario.response_data["scenario"]["id"]
       
       # Update with full blueprint
       update_result = make_adapter.update_scenario_blueprint(
           scenario_id=stub_id,
           blueprint=full_blueprint,
           confirmed=True
       )
       
       # Verify again
       if verify_module_count(stub_id, capability):
           return stub_id
       else:
           raise DeploymentError(
               f"Failed to create {capability} scenario with correct module count"
           )
   ```

## Detection

```python
# After any scenario creation or update
def check_scenario_completeness(scenario_id: int, capability: str) -> dict:
    """Check if scenario matches expected structure."""
    receipt = make_adapter.get_scenario_blueprint(scenario_id)
    blueprint = json.loads(receipt.response_data["blueprint"])
    
    flow = blueprint.get("flow", [])
    actual_count = len(flow)
    expected_count = EXPECTED_MODULE_COUNTS.get(capability)
    
    # Check for specific module types
    has_webhook = any(
        m.get("module") in ("webhook:CustomWebHook", "gateway:CustomWebHook")
        for m in flow
    )
    has_response = any(
        "response" in m.get("module", "").lower()
        for m in flow
    )
    
    return {
        "module_count": actual_count,
        "expected_count": expected_count,
        "match": actual_count == expected_count,
        "has_webhook_trigger": has_webhook,
        "has_response_module": has_response,
        "complete": actual_count == expected_count and has_webhook and has_response
    }
```

## Prevention

- Always verify module count after scenario creation
- Use `MakeScenarioDeployer` which includes automatic verification
- Store expected module counts as constants
- Add module count to deployment receipts
- Test scenarios immediately after creation
- Log module count mismatches for investigation

## Common Causes

- Invalid connection IDs causing modules to be silently dropped
- Blueprint validation errors not reported by API
- Module parameters failing API validation rules
- Make.com API changes affecting module acceptance
- Expired or deleted resources referenced in blueprint

## What to Do When Count is Wrong

1. **Check the actual blueprint:** GET the scenario blueprint and inspect which modules are missing
2. **Review validation errors:** Look for modules that might have failed validation
3. **Verify connection IDs:** Ensure all connection IDs in the blueprint exist and are accessible
4. **Try stub + update fallback:** Create minimal scenario, then update with full blueprint
5. **Contact Make.com support:** If issue persists, it may be an API bug

## Related Issues

- Silent blueprint import failure (separate gotcha)
- Connection IDs must be valid at scenario creation time
- Module parameters must meet undocumented API validation rules

## References

- Make.com Scenarios API: https://developers.make.com/api-documentation/api-reference/scenarios
- Agent Forge Deployer: orchestrator/make_deployer.py - EXPECTED_MODULE_COUNTS, verify_module_count()
- Research Date: 2026-08-03
