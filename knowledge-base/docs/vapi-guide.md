# Vapi Platform Guide

## Overview

Vapi provides voice AI assistant APIs for creating, configuring, and deploying conversational agents.

## Assistants

### Creating an Assistant

Assistants are the main entity in Vapi. Each assistant has a voice, model, and set of tools.

```python
assistant = vapi_adapter.create_assistant({
    "name": "Customer Service Bot",
    "model": {
        "provider": "openai",
        "model": "gpt-4",
        "temperature": 0.7
    },
    "voice": {
        "provider": "11labs",
        "voiceId": "reviewed-voice-id"
    },
    "firstMessage": "Hello! How can I help you today?"
})
```

### Updating Assistants

Assistant updates are partial - only specified fields are changed.

```python
updated = vapi_adapter.update_assistant(
    assistant_id="asst_123",
    updates={
        "firstMessage": "New greeting message"
    }
)
```

## Tools

### Custom Tools

Tools allow assistants to call external APIs.

```python
tool = vapi_adapter.create_tool({
    "type": "function",
    "function": {
        "name": "check_availability",
        "description": "Check appointment availability",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Date in YYYY-MM-DD"}
            }
        },
        "url": "https://api.example.com/availability"
    }
})
```

### Tool Server Requirements

- **HTTPS required** - Tool URLs must use HTTPS
- **HMAC validation** - Implement HMAC signature verification
- **Timeout** - Respond within 10 seconds
- **Error handling** - Return structured errors

## Phone Numbers

### Assignment

Phone numbers must be assigned to an assistant to receive calls.

```python
vapi_adapter.assign_phone_number(
    phone_number_id="ph_123",
    assistant_id="asst_456"
)
```

**Important:** Assignment can take 30-60 seconds. See gotcha: vapi-phone-assignment-timeout.md

### Verification

Always verify phone assignment after operation:

```python
phone = vapi_adapter.get_phone_number(phone_number_id)
assert phone["assistantId"] == expected_assistant_id
```

## Common Issues

### Assistant Not Responding

**Symptom:** Assistant created but doesn't respond to calls

**Check:**
1. Phone number assigned to assistant
2. Tool URLs are HTTPS
3. First message is set
4. Model and voice IDs are valid

### Tool Calls Failing

**Symptom:** Assistant says tool is unavailable

**Check:**
1. Tool URL returns 200 OK
2. HMAC signature is valid
3. Response format matches tool schema
4. Server responds within timeout

## Best Practices

- **Always verify after operations** - Don't assume success from 200 OK
- **Use reconciliation** - Check remote state after timeouts
- **Test with staging resources** - Never test with production phone numbers
- **Monitor API rate limits** - Vapi has per-minute limits
- **Store resource IDs** - Keep mapping of assistants, tools, and phone numbers

## Rate Limits

- **Assistant operations:** 60/minute
- **Tool operations:** 60/minute
- **Phone operations:** 30/minute

## References

- Official Docs: https://docs.vapi.ai/
- API Reference: https://docs.vapi.ai/api-reference
- Agent Forge Adapter: adapters/vapi.py
