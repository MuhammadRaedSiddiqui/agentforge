# Gotcha: Make.com Requires Hook Creation Before Scenario

**Platform:** Make.com  
**Topic:** Deployment Order  
**Symptom:** Scenarios created with placeholder webhook URLs fail at runtime  
**Verification Status:** Verified  
**Approved By:** system  
**Approved At:** 2026-08-03

## Root Cause

Make.com scenarios that use webhook triggers require a real webhook hook URL at creation time. If a scenario is created with a placeholder URL (e.g., `{{hook_url}}` or `https://placeholder.example.com`), the scenario will be created successfully but will fail when triggered because the webhook URL is invalid.

The webhook hook must be created **before** the scenario so that the real hook URL can be injected into the blueprint before scenario creation.

**Deployment order must be:**
1. Create webhook hook → get real hook URL
2. Inject hook URL into blueprint
3. Create scenario with parameterized blueprint
4. Activate scenario

**NOT:**
1. ❌ Create scenario with placeholder
2. ❌ Create hook
3. ❌ Try to update scenario with real URL (doesn't work reliably)

## Resolution

1. **Use MakeScenarioDeployer for hook-first deployment:**
   ```python
   from orchestrator.make_deployer import MakeScenarioDeployer
   
   deployer = MakeScenarioDeployer(make_adapter)
   result = deployer.deploy_scenario(
       capability="booking",
       blueprint_path="ground-truth/configs/make_blueprints/booking.json",
       hook_name="booking-webhook",
       connection_id="conn-123"
   )
   
   # Result includes:
   # - scenario_id
   # - hook_id
   # - module_count (verified against expected)
   # - activated (True/False)
   ```

2. **Manual hook-first flow:**
   ```python
   # Step 1: Create hook first
   hook_receipt = make_adapter.create_hook(
       name=f"{org_id}-{capability}-webhook",
       type_name="custom",
       method=True,
       headers=True,
       stringify=True
   )
   hook_id = hook_receipt.response_data["hook"]["id"]
   hook_url = hook_receipt.response_data["hook"]["url"]
   
   # Step 2: Load and parameterize blueprint
   with open(blueprint_path) as f:
       blueprint = json.load(f)
   
   # Step 3: Inject hook URL into blueprint
   from agents.make_agent.tools import inject_hook_urls
   blueprint = inject_hook_urls(blueprint, hook_url)
   
   # Step 4: Inject connection ID if needed
   if connection_id:
       blueprint = inject_connection_id(blueprint, connection_id)
   
   # Step 5: Create scenario with parameterized blueprint
   scenario_receipt = make_adapter.create_scenario(
       blueprint=blueprint,
       scheduling={"type": "immediately"},
       confirmed=True
   )
   ```

3. **Validate hook URL in blueprint before creation:**
   ```python
   # Before creating scenario, verify hook URL was injected
   webhook_modules = [
       m for m in blueprint.get("flow", [])
       if m.get("module") in ("webhook:CustomWebHook", "gateway:CustomWebHook")
   ]
   
   for module in webhook_modules:
       url = module.get("webhook", {}).get("url", "")
       if not url.startswith("https://hook."):
           raise ValueError(
               f"Invalid hook URL: {url}. Must create hook before scenario."
           )
   ```

## Detection

```python
# Check if scenario has placeholder webhook URL
scenario_blueprint = make_adapter.get_scenario_blueprint(scenario_id)

webhook_modules = [
    m for m in scenario_blueprint.get("flow", [])
    if m.get("module") in ("webhook:CustomWebHook", "gateway:CustomWebHook")
]

for module in webhook_modules:
    url = module.get("webhook", {}).get("url", "")
    if "placeholder" in url or "{{" in url or not url.startswith("https://hook."):
        # Scenario has placeholder - will fail at runtime
        raise ValidationError(
            f"Scenario {scenario_id} has placeholder webhook URL: {url}"
        )
```

## Prevention

- Always create hooks before scenarios
- Use `MakeScenarioDeployer` which enforces hook-first order
- Validate webhook URLs in blueprints before scenario creation
- Store hook_id with scenario in deployment receipts
- Test scenarios immediately after creation to verify webhooks work

## Common Causes

- Creating scenario before hook
- Assuming placeholder URLs can be updated later
- Not injecting hook URL into blueprint before scenario creation
- Copying blueprints from UI without parameterizing webhook URLs

## Expected Module Counts

When verifying scenario creation, check module counts match expected:
- **availability**: 4 modules
- **booking**: 6 modules
- **cancellation**: 8 modules
- **rescheduling**: 10 modules

## Related Issues

- Connection IDs must also be injected before scenario creation
- Scheduling must be set to `"immediately"` for webhook-triggered scenarios
- Hooks cannot be deleted while scenarios reference them

## References

- Make.com Hooks API: https://developers.make.com/api-documentation/api-reference/hooks
- Agent Forge Deployer: orchestrator/make_deployer.py
- Hook Injection: agents/make_agent/tools.py
- Research Date: 2026-08-03
