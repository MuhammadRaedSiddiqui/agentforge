# Gotcha: Vapi Assistant Phone Number Assignment Timeout

**Platform:** Vapi  
**Topic:** Phone Number Assignment  
**Symptom:** Phone number assignment API call times out after 30 seconds  
**Verification Status:** Verified  
**Approved By:** system  
**Approved At:** 2026-07-14

## Root Cause

Vapi's phone number assignment operation can take longer than the default 30-second timeout when the phone number requires provisioning or configuration changes. The operation often succeeds on the Vapi side but the client times out before receiving the response.

## Resolution

1. **Increase timeout for phone assignment operations to 60 seconds:**
   ```python
   adapter = VapiAdapter(read_timeout=60.0)
   ```

2. **Implement reconciliation after timeout:**
   - List phone numbers via `GET /phone-number`
   - Check if target phone number's `assistantId` field matches expected assistant
   - If matched, accept as success and persist receipt retroactively
   - If not matched, safe to retry

3. **Use idempotent assignment:**
   - Vapi assignment is idempotent by phone number ID
   - Retrying the same assignment overwrites previous assignment
   - No duplicate resources created

## Detection

```python
# Timeout on assignment
try:
    receipt = vapi_adapter.assign_phone_number(phone_id, assistant_id)
except AmbiguousOutcomeError as e:
    # Reconcile
    result = recovery.reconcile_remote_state({
        "platform": "vapi",
        "operation": "assign_phone_number",
        "target": {"phone_number_id": phone_id}
    })
    if result.resource_found and result.matches_expected:
        # Accept as success
        persist_receipt_retroactively(result)
```

## Prevention

- Configure phone assignment operations with 60s read timeout
- Always reconcile after ambiguous timeout
- Monitor Vapi API status for provisioning delays
- Consider webhook callbacks for long-running operations

## Related Issues

- Vapi assistant creation can also timeout during initial setup
- Make.com scenario activation has similar timeout patterns

## References

- Vapi Phone Number API: https://docs.vapi.ai/api-reference/phone-numbers
- Agent Forge Recovery: orchestrator/recovery.py
- Research Date: 2026-07-14
