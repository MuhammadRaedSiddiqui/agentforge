# Gotcha: Make.com Unknown Scheduling Types Default to "immediately"

**Platform:** Make.com  
**Topic:** Scenario Scheduling  
**Symptom:** Scenarios with invalid scheduling configurations are created with "immediately" type instead of failing  
**Verification Status:** Verified  
**Approved By:** system  
**Approved At:** 2026-08-03

## Root Cause

Make.com's scenario API accepts a `scheduling` object that specifies when the scenario should run. Valid types are:
- `"immediately"` - runs as soon as triggered (for webhook-triggered scenarios)
- `"indefinitely"` - runs continuously at specified intervals
- `"once"` - runs once at a specific time
- `"daily"`, `"weekly"`, `"monthly"`, `"yearly"` - recurring schedules

If an invalid scheduling type is provided (e.g., `"on_demand"`, `"manual"`, or any typo), the Make.com adapter now defaults to `{"type": "immediately"}` instead of raising an error. This prevents deployment failures for webhook-triggered scenarios but can mask configuration errors for scheduled scenarios.

**Before fix:**
```python
# Unknown type caused error or unpredictable behavior
scheduling = {"type": "on_demand", "interval": 900}  # Invalid type
# Result: API error or scenario created with wrong schedule
```

**After fix:**
```python
# Unknown type defaults to "immediately"
scheduling = {"type": "on_demand", "interval": 900}  # Invalid type
# Result: {"type": "immediately"} (safe default for webhooks)
```

## Resolution

1. **Validate scheduling type before API call:**
   ```python
   # In adapters/make.py or orchestrator
   
   VALID_SCHEDULING_TYPES = {
       "immediately", "indefinitely", "once", 
       "daily", "weekly", "monthly", "yearly"
   }
   
   def normalize_scheduling(scheduling: dict) -> dict:
       """Normalize scheduling configuration."""
       schedule_type = scheduling.get("type", "immediately")
       
       if schedule_type not in VALID_SCHEDULING_TYPES:
           # Log warning and default to "immediately"
           logger.warning(
               f"Unknown scheduling type '{schedule_type}', defaulting to 'immediately'"
           )
           return {"type": "immediately"}
       
       return scheduling
   ```

2. **Use correct scheduling type for webhook scenarios:**
   ```python
   # For webhook-triggered scenarios (availability, booking, cancellation, rescheduling)
   scheduling = {"type": "immediately"}
   
   # NOT:
   scheduling = {"type": "on_demand"}  # Invalid
   scheduling = {"type": "indefinitely", "interval": 900}  # Wrong for webhooks
   ```

3. **Validate scheduling in blueprint validator:**
   ```python
   # In agents/make_agent/validator.py
   
   def validate_scheduling(scheduling: dict) -> list[str]:
       errors = []
       schedule_type = scheduling.get("type")
       
       if schedule_type not in VALID_SCHEDULING_TYPES:
           errors.append(
               f"Invalid scheduling type: '{schedule_type}'. "
               f"Valid types: {', '.join(VALID_SCHEDULING_TYPES)}"
           )
       
       # Validate type-specific requirements
       if schedule_type == "indefinitely" and "interval" not in scheduling:
           errors.append("Scheduling type 'indefinitely' requires 'interval' field")
       
       if schedule_type == "once" and "timestamp" not in scheduling:
           errors.append("Scheduling type 'once' requires 'timestamp' field")
       
       return errors
   ```

## Detection

```python
# Check if scheduling was normalized
original_type = user_scheduling.get("type")
normalized = normalize_scheduling(user_scheduling)

if normalized["type"] != original_type:
    # Scheduling was changed - log warning
    logger.warning(
        f"Scheduling type changed from '{original_type}' to '{normalized['type']}'. "
        f"Original type was invalid."
    )
```

## Prevention

- Always use `"immediately"` for webhook-triggered scenarios
- Validate scheduling type before passing to adapter
- Document valid scheduling types in intake schema
- Add tests for each valid scheduling type
- Log warnings when unknown types are encountered

## Common Causes

- Using `"on_demand"` instead of `"immediately"`
- Copying scheduling config from other automation platforms
- Typos in scheduling type (e.g., `"immediatly"` vs `"immediately"`)
- Not reading Make.com scheduling documentation

## Webhook Scenarios vs Scheduled Scenarios

| Scenario Type | Trigger | Correct Scheduling |
|---------------|---------|-------------------|
| Webhook (availability, booking, cancellation, rescheduling) | External HTTP request | `{"type": "immediately"}` |
| Polling/Scheduled | Timer/Interval | `{"type": "indefinitely", "interval": 900}` |
| One-time | Specific timestamp | `{"type": "once", "timestamp": "2026-08-05T10:00:00Z"}` |
| Recurring | Daily/Weekly/Monthly | `{"type": "daily", "hour": 9, "minute": 0}` |

## Related Issues

- Scheduling cannot be changed after scenario creation (must recreate scenario)
- `"indefinitely"` requires `interval` in seconds (minimum 60)
- Timezone handling for scheduled scenarios

## References

- Make.com Scheduling API: https://developers.make.com/api-documentation/api-reference/scenarios#scheduling
- Agent Forge Adapter: adapters/make.py - normalize_scheduling()
- Action Builder: orchestrator/action_builder.py — `scheduling` in the Make
  create_scenario payload (was orchestrator/full_orchestrator.py line 422 before
  that module was removed)
- Research Date: 2026-08-03
