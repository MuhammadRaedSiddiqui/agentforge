# Gotcha: Make.com Webhook Module Name Mismatch

**Platform:** Make.com  
**Topic:** Blueprint Module Types  
**Symptom:** Blueprint validation fails or hooks not properly wired to webhook modules  
**Verification Status:** Verified  
**Approved By:** system  
**Approved At:** 2026-08-03

## Root Cause

Make.com blueprints use inconsistent module type names for webhook triggers across different contexts:

- **In blueprints downloaded from UI:** module type is `webhook:CustomWebHook`
- **In API responses and new blueprints:** module type is `gateway:CustomWebHook`
- **Both are valid:** but must match the actual module type in the blueprint

When injecting hook URLs into blueprints, the code must handle both variants. Failing to check for both will result in the hook URL not being injected, leaving the blueprint with a placeholder URL that fails at runtime.

## Resolution

1. **Check for both module type variants when injecting hook URLs:**
   ```python
   # In agents/make_agent/tools.py - inject_hook_urls()
   
   for module in blueprint.get("flow", []):
       module_type = module.get("module")
       
       # Check BOTH variants
       if module_type in ("webhook:CustomWebHook", "gateway:CustomWebHook"):
           # Inject hook URL
           if "webhook" in module:
               module["webhook"]["url"] = hook_url
               injected = True
   ```

2. **Extract hook references with both variants:**
   ```python
   # In agents/make_agent/tools.py - extract_hook_references()
   
   def extract_hook_references(blueprint: dict) -> list[str]:
       references = []
       for module in blueprint.get("flow", []):
           if module.get("module") in ("webhook:CustomWebHook", "gateway:CustomWebHook"):
               url = module.get("webhook", {}).get("url", "")
               if url:
                   references.append(url)
       return references
   ```

3. **Validate both are handled in tests:**
   ```python
   # Test with both module types
   test_cases = [
       {"module": "webhook:CustomWebHook", "webhook": {"url": ""}},
       {"module": "gateway:CustomWebHook", "webhook": {"url": ""}},
   ]
   
   for test_module in test_cases:
       result = inject_hook_urls({"flow": [test_module]}, hook_url)
       assert result["flow"][0]["webhook"]["url"] == hook_url
   ```

## Detection

```python
# Check if hook URL was actually injected
blueprint_with_hook = inject_hook_urls(blueprint, hook_url)

webhook_modules = [
    m for m in blueprint_with_hook.get("flow", [])
    if m.get("module") in ("webhook:CustomWebHook", "gateway:CustomWebHook")
]

for module in webhook_modules:
    actual_url = module.get("webhook", {}).get("url", "")
    if not actual_url or "placeholder" in actual_url.lower():
        raise ValueError(
            f"Hook URL not injected for module type: {module.get('module')}"
        )
```

## Prevention

- Always check for both `webhook:CustomWebHook` and `gateway:CustomWebHook` module types
- Use `in ("webhook:CustomWebHook", "gateway:CustomWebHook")` pattern consistently
- Add tests that verify both variants work
- Validate hook URL injection in the validator
- Grep for webhook module type checks in codebase to ensure consistency

## Common Causes

- Hardcoding only one module type variant in the code
- Copying blueprint from UI (uses `webhook:`) but API returns (`gateway:`)
- Not testing against both module type variants
- Make.com API inconsistency across versions

## Related Issues

- Hook URL placeholders like `{{hook_url}}` must be replaced before deployment
- Connection IDs in other modules have similar variant issues

## References

- Make.com Blueprints API: https://developers.make.com/api-documentation/api-reference/scenarios/blueprints
- Agent Forge Hook Injection: agents/make_agent/tools.py lines 100, 231
- Fix Commit: phase2-make-blueprints branch
- Research Date: 2026-08-03
