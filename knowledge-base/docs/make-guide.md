# Make.com Platform Guide

## Overview

Make.com provides visual workflow automation. Agent Forge uses Make for backend automation scenarios.

## Scenarios

### Creating from Blueprint

Scenarios are created by importing pre-defined blueprints.

```python
scenario = make_adapter.create_scenario(
    blueprint={
        "name": "Booking Flow",
        "teamId": team_id,
        "flow": [...],
        "modules": [...]
    },
    scheduling={
        "type": "indefinitely"
    }
)
```

**Important:** Always verify scenario after import. See gotcha: make-blueprint-import-silent-failure.md

### Activating Scenarios

Scenarios must be explicitly activated to run.

```python
make_adapter.activate_scenario(scenario_id)

# Verify activation
scenario = make_adapter.get_scenario(scenario_id)
assert scenario["isDisabled"] == False
```

## Hooks (Webhooks)

### Creating Hooks

Hooks receive incoming webhook requests.

```python
hook = make_adapter.create_hook(
    name="Booking Webhook",
    type_name="custom",
    method=True,
    headers=True,
    stringify=True
)

webhook_url = hook["hookUrl"]  # Use this as your webhook endpoint
```

### Hook Configuration

- **method**: Accept any HTTP method
- **headers**: Include headers in payload
- **stringify**: Convert body to string if not JSON

## Blueprints

### Blueprint Structure

Blueprints define scenario flows as JSON:

```json
{
  "name": "Scenario Name",
  "flow": [...],
  "modules": [
    {
      "id": 1,
      "module": "http:ActionSendData",
      "parameters": {...}
    }
  ]
}
```

### Validation Before Import

Required checks:
- All connection IDs exist
- All module types are valid
- Required parameters present
- Webhook URLs are HTTPS

## Teams and Zones

### API Zones

Make.com has multiple zones:
- **us1**: North America
- **us2**: North America (alternate)
- **eu1**: Europe
- **eu2**: Europe (alternate)

Set via `MAKE_ZONE` environment variable.

### Team ID

All operations are scoped to a team:

```python
# List scenarios for team
scenarios = make_adapter.list_scenarios()
```

## Common Issues

### Scenario Created But Not Working

**Symptoms:**
- Scenario exists but doesn't trigger
- Webhook returns 404

**Check:**
1. Scenario is activated (not disabled)
2. All modules are present (count matches blueprint)
3. Hooks are attached and not gone
4. Scheduling is configured correctly

### Hook URL Changes

**Symptom:** Webhook suddenly stops receiving requests

**Cause:** Hooks can be automatically removed or URL changed

**Resolution:**
- Reconcile hooks regularly
- Store hook ID and verify URL hasn't changed
- Recreate hook if removed

## Best Practices

- **Verify after import** - Check module count and configuration
- **Store blueprint hashes** - Detect drift between expected and actual
- **Test scenarios in staging** - Use non-production connections
- **Monitor scenario execution** - Check logs for failures
- **Handle rate limits** - Make has per-team quotas

## Rate Limits

- **Scenario operations:** 60/minute per team
- **Blueprint operations:** 30/minute per team
- **Hook operations:** 60/minute per team

## Reconciliation

After timeout or ambiguous operations:

```python
# List scenarios and match by name
scenarios = make_adapter.list_scenarios()
for scenario in scenarios.get("scenarios", []):
    if scenario["name"] == expected_name:
        # Found it - was created successfully
        return scenario["id"]
```

## References

- Official Docs: https://www.make.com/en/help
- API Docs: https://developers.make.com/api-documentation
- Agent Forge Adapter: adapters/make.py
