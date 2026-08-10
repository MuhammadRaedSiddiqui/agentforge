# Gotcha: Make.com Blueprint Creation Fallback Strategy

**Platform:** Make.com  
**Topic:** Scenario Creation Resilience  
**Symptom:** Full blueprint creation fails but stub + update succeeds  
**Verification Status:** Verified  
**Approved By:** system  
**Approved At:** 2026-08-03

## Root Cause

Make.com's scenario creation API (`POST /scenarios`) can reject complex blueprints with validation errors that are not always clearly reported. However, a two-step approach often succeeds:

1. **Create a minimal stub scenario** with only the webhook trigger module
2. **Update the scenario blueprint** via PUT with the full multi-module blueprint

This pattern works because:
- The stub scenario passes initial validation easily (minimal complexity)
- The update endpoint has more lenient validation than the create endpoint
- Scenario ID is established, so subsequent updates are treated as modifications rather than new creations

The `MakeScenarioDeployer` implements this fallback automatically when direct creation fails.

## Resolution

1. **Automatic fallback in MakeScenarioDeployer:**
   ```python
   # In orchestrator/make_deployer.py
   
   def deploy_scenario(self, capability: str, blueprint_path: str, ...) -> dict:
       # Load full blueprint
       full_blueprint = self._load_blueprint(blueprint_path)
       full_blueprint = self._inject_hook_id(full_blueprint, hook_id)
       
       # Try direct creation with full blueprint first
       try:
           scenario_receipt = self.adapter.create_scenario(
               blueprint=full_blueprint,
               scheduling={"type": "immediately"},
               confirmed=True
           )
           scenario_id = scenario_receipt.response_data["scenario"]["id"]
           used_fallback = False
           
       except Exception as e:
           # Direct creation failed - use stub + update fallback
           logger.info(f"Direct creation failed, trying stub + update fallback: {e}")
           
           # Create minimal stub with just webhook trigger
           stub_blueprint = self._create_stub_blueprint(capability, hook_id)
           stub_receipt = self.adapter.create_scenario(
               blueprint=stub_blueprint,
               scheduling={"type": "immediately"},
               confirmed=True
           )
           scenario_id = stub_receipt.response_data["scenario"]["id"]
           
           # Update with full blueprint
           self.adapter.update_scenario_blueprint(
               scenario_id=scenario_id,
               blueprint=full_blueprint,
               confirmed=True
           )
           used_fallback = True
       
       return {
           "scenario_id": scenario_id,
           "used_fallback": used_fallback,
           ...
       }
   ```

2. **Create minimal stub blueprint:**
   ```python
   def _create_stub_blueprint(capability: str, hook_url: str) -> dict:
       """Create minimal blueprint with just webhook trigger."""
       return {
           "name": f"{capability}-stub",
           "flow": [
               {
                   "id": 1,
                   "module": "gateway:CustomWebHook",
                   "version": 1,
                   "webhook": {
                       "url": hook_url,
                       "method": "POST",
                       "headers": True,
                       "stringify": True
                   },
                   "mapper": {}
               }
           ],
           "metadata": {
               "scenario": {
                   "roundtrips": 1,
                   "maxErrors": 3,
                   "autoCommit": True,
                   "sequential": False
               }
           }
       }
   ```

3. **Manual fallback implementation:**
   ```python
   # Try full blueprint first
   try:
       scenario = make_adapter.create_scenario(full_blueprint, scheduling)
       scenario_id = scenario.response_data["scenario"]["id"]
   except Exception as create_error:
       # Fallback: stub + update
       stub = create_stub_blueprint(capability, hook_url)
       stub_scenario = make_adapter.create_scenario(stub, scheduling)
       scenario_id = stub_scenario.response_data["scenario"]["id"]
       
       # Update with full blueprint
       make_adapter.update_scenario_blueprint(
           scenario_id=scenario_id,
           blueprint=full_blueprint,
           confirmed=True
       )
   ```

## Detection

```python
# Check if fallback was used (in deployment receipt)
deployment_receipt = internal_store.get_deployment(deployment_id)
make_actions = [a for a in deployment_receipt["actions"] if a["platform"] == "make"]

for action in make_actions:
    if action.get("metadata", {}).get("used_fallback"):
        logger.warning(
            f"Scenario {action['scenario_id']} was created using fallback strategy. "
            f"Direct creation failed, but stub + update succeeded."
        )
```

## Prevention

- Always try direct creation first (faster, simpler)
- Have fallback ready for production resilience
- Log when fallback is used for monitoring
- Store `used_fallback` flag in deployment receipt
- Investigate blueprint validation errors when fallback is needed frequently

## Common Causes of Direct Creation Failure

- Complex module configurations that fail validation
- Connection IDs that are valid but cause creation-time issues
- Blueprint size exceeding undocumented limits
- Race conditions with resource creation on Make.com side
- Transient API issues

## When to Use Each Strategy

| Scenario | Strategy | Reason |
|----------|----------|--------|
| Initial deployment | Try direct, fallback if fails | Best of both: speed when possible, resilience when needed |
| Known problematic blueprint | Use fallback directly | Skip failed direct attempt |
| Simple scenarios (1-3 modules) | Direct only | Unlikely to fail |
| Complex scenarios (8+ modules) | Always use fallback | Higher failure rate |

## Verification After Fallback

After using fallback, always verify:
1. Module count matches expected (see make-module-count-verification gotcha)
2. All modules present in blueprint
3. Hook URLs correctly injected
4. Connection IDs correctly injected
5. Scenario activates successfully

## Related Issues

- Module count verification is critical after fallback
- Update endpoint may silently accept invalid modules (check after update)
- Fallback adds ~2-3 seconds to deployment time

## References

- Make.com Scenarios API: https://developers.make.com/api-documentation/api-reference/scenarios
- Make.com Blueprints API: https://developers.make.com/api-documentation/api-reference/scenarios/blueprints
- Agent Forge Deployer: orchestrator/make_deployer.py - deploy_scenario()
- Research Date: 2026-08-03
