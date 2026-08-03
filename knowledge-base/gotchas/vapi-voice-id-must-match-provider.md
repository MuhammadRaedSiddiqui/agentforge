# Gotcha: Vapi Voice ID Must Match Provider

**Platform:** Vapi  
**Topic:** Voice Configuration  
**Symptom:** Assistant created successfully but fails at runtime with "Invalid voice ID" error  
**Verification Status:** Verified  
**Approved By:** system  
**Approved At:** 2026-08-03

## Root Cause

Vapi supports multiple voice providers (11labs, PlayHT, Deepgram, Azure, etc.), and each provider has its own set of voice IDs. A voice ID that works for one provider will not work for another provider.

For example:
- 11labs voice ID: `"burt"`, `"rachel"`, `"antoni"`
- PlayHT voice ID: `"jennifer"`, `"matthew"`
- Deepgram voice ID: `"aura-asteria-en"`, `"aura-luna-en"`

If you configure an assistant with `provider: "11labs"` but use a PlayHT voice ID like `"jennifer"`, the assistant will be created successfully (Vapi doesn't validate at creation time), but it will fail when the assistant receives a call.

## Resolution

1. **Pre-validate voice ID against Vapi API:**
   ```python
   # In cli/chat.py or orchestrator
   from adapters.vapi import VapiAdapter
   
   vapi = VapiAdapter()
   receipt = vapi.list_voices()
   voices = receipt.response_data.get("voices", [])
   
   # Extract voice IDs
   available_ids = [
       v.get("voiceId") or v.get("id") or v.get("name", "")
       for v in voices
   ]
   
   # Validate user's voice ID
   if voice_id not in available_ids:
       raise ValidationError(
           f"Voice ID '{voice_id}' not found. "
           f"Available voices: {', '.join(available_ids[:15])}"
       )
   ```

2. **Match voice ID to provider in intake validation:**
   ```python
   # In orchestrator/intake_schema.py
   
   def validate_voice_config(voice_config: dict) -> list[str]:
       errors = []
       provider = voice_config.get("provider")
       voice_id = voice_config.get("voice_id")
       
       # Provider-specific voice ID patterns
       if provider == "11labs":
           # 11labs uses simple names
           if not re.match(r"^[a-z]+$", voice_id):
               errors.append(
                   f"Voice ID '{voice_id}' doesn't match 11labs format (lowercase letters)"
               )
       elif provider == "deepgram":
           # Deepgram uses "aura-{name}-{lang}" format
           if not re.match(r"^aura-[a-z]+-[a-z]{2}$", voice_id):
               errors.append(
                   f"Voice ID '{voice_id}' doesn't match Deepgram format (aura-name-lang)"
               )
       
       return errors
   ```

3. **Conversational agent validation:**
   ```python
   # In cli/chat.py - already implemented
   # After intake extraction, before execution:
   
   voice_id = normalized_intake.get("voice_id", "")
   if voice_id:
       try:
           vapi = VapiAdapter()
           receipt = vapi.list_voices()
           voices = receipt.response_data.get("voices", [])
           available_ids = [v.get("voiceId") or v.get("id") for v in voices]
           
           if available_ids and voice_id not in available_ids:
               print(f"\nVoice '{voice_id}' not found in Vapi.")
               print(f"Available voices: {', '.join(available_ids[:15])}")
               print("\nPlease restart with a valid voice ID.")
               return 1
       except Exception:
           pass  # Continue if voice list fails
   ```

## Detection

```python
# After assistant creation, test with a sample call
try:
    # Make test call to assistant
    test_result = vapi.test_assistant(assistant_id)
except VapiError as e:
    if "voice" in str(e).lower() or "invalid" in str(e).lower():
        # Voice ID validation failure at runtime
        raise ValidationError(
            f"Assistant {assistant_id} has invalid voice configuration. "
            f"Voice ID '{voice_id}' may not match provider '{provider}'."
        ) from e
```

## Prevention

- Always list available voices from Vapi API before presenting to user
- In conversational flow, show valid voice options for selected provider
- Pre-validate voice ID before creating assistant
- Store provider-to-voice-ID mappings in config
- Document voice IDs per provider in knowledge base

## Common Causes

- Using voice ID from one provider with a different provider
- Typos in voice ID (e.g., `"burt"` vs `"bert"`)
- Using deprecated or removed voice IDs
- Not checking Vapi's current voice catalog

## Provider-Specific Voice ID Formats

| Provider | Format | Example |
|----------|--------|---------|
| 11labs | Lowercase name | `"burt"`, `"rachel"`, `"antoni"` |
| PlayHT | Title case name | `"Jennifer"`, `"Matthew"` |
| Deepgram | aura-{name}-{lang} | `"aura-asteria-en"`, `"aura-luna-en"` |
| Azure | GUID or name | `"en-US-JennyNeural"` |

## Related Issues

- Voice provider must be a valid provider in Vapi's list
- Some voices have language variants (e.g., en-US vs en-GB)
- Voice availability may vary by Vapi plan/tier

## References

- Vapi Voices API: https://docs.vapi.ai/api-reference/voices
- Agent Forge Adapter: adapters/vapi.py - list_voices()
- CLI Chat Validation: cli/chat.py lines 1695-1713
- Research Date: 2026-08-03
