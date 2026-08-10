# Gotcha: Render Deploy Trigger is Fire-and-Forget

**Platform:** Render  
**Topic:** Deployment API  
**Symptom:** API returns success immediately but actual deployment status unknown  
**Verification Status:** Verified  
**Approved By:** system  
**Approved At:** 2026-08-03

## Root Cause

Render's deploy trigger API (`POST /services/{serviceId}/deploys`) is **asynchronous and fire-and-forget**. When you trigger a deployment:

1. The API returns 200 OK immediately
2. The response does NOT include deployment status, build logs, or completion time
3. The actual build and deployment happens in the background on Render's infrastructure
4. There is no webhook callback or notification when deployment completes

This means you cannot know from the API response whether the deployment succeeded, failed, or is still in progress. The only way to verify deployment status is to:
- Poll the Render dashboard manually
- Check the health endpoint after waiting
- Monitor application logs

## Resolution

1. **Set environment variables before deploying:**
   ```python
   # In adapters/hosting.py - RenderAdapter
   
   # Step 1: Set environment variables first
   for key, value in env_vars.items():
       self.set_env_variable(service_id, key, value)
   
   # Step 2: Trigger deploy (fire-and-forget)
   deploy_receipt = self.trigger_deploy(service_id)
   
   # Step 3: Wait for reasonable build time
   time.sleep(60)  # Wait 60s for typical Node.js deployment
   
   # Step 4: Verify via health check
   health_url = f"https://{service_name}.onrender.com/health"
   health_response = requests.get(health_url, timeout=10)
   
   if health_response.status_code != 200:
       raise DeploymentError(
           f"Health check failed after deploy. Status: {health_response.status_code}"
       )
   ```

2. **Don't wait for deployment completion in the API call:**
   ```python
   def trigger_deploy(self, service_id: str) -> AdapterReceipt:
       """
       Trigger a deployment.
       
       Note: This is async/fire-and-forget. The API returns immediately.
       The actual deployment happens in the background on Render.
       Use health check verification to confirm deployment success.
       """
       response = self._request(
           method="POST",
           endpoint=f"/services/{service_id}/deploys",
           json={}
       )
       
       # API returned 200 but deployment is still in progress
       return AdapterReceipt(
           success=True,
           response_data=response,
           remote_resource_id=service_id,
           message="Deploy triggered (async - verify via health check)"
       )
   ```

3. **Use health check for verification:**
   ```python
   # In orchestrator - after Render deploy action
   
   # Trigger deploy (returns immediately)
   deploy_result = hosting_adapter.trigger_deploy(service_id)
   
   # Record receipt (deploy triggered, not completed)
   internal_store.record_action_receipt({
       "action": "trigger_deploy",
       "status": "triggered",  # Not "completed"
       "timestamp": datetime.now(UTC)
   })
   
   # Transition to verifying state
   state_machine.transition("verifying")
   
   # Wait for reasonable deploy time (30-120s depending on service)
   time.sleep(90)
   
   # Verify deployment via health check
   health_url = intake["hosting_health_url"]
   try:
       response = requests.get(health_url, timeout=10)
       if response.status_code == 200:
           # Deployment successful
           state_machine.transition("complete")
       else:
           # Deployment may have failed
           state_machine.transition("recovery_required")
   except requests.exceptions.RequestException:
       # Health check failed - deployment issue
       state_machine.transition("recovery_required")
   ```

## Detection

```python
# After deploy trigger, you CANNOT detect success from API response
# Must use external verification

# Wrong:
deploy_response = render.trigger_deploy(service_id)
if deploy_response["status"] == "success":  # ❌ This doesn't exist
    print("Deploy succeeded")

# Correct:
deploy_response = render.trigger_deploy(service_id)
# Wait for build time
time.sleep(90)
# Verify via health endpoint
health_ok = verify_health_endpoint(health_url)
if health_ok:
    print("Deploy succeeded")
```

## Prevention

- Never assume deploy success from API response
- Always include health check verification after deploy
- Set reasonable wait times based on application build complexity
- Document that deploy is async in adapter method docstrings
- Store health URL in intake for verification
- Add timeout to health check (don't wait forever)

## Common Causes

- Assuming deploy API is synchronous like other platforms
- Not implementing health check verification
- Treating 200 OK response as "deployment completed"
- Not waiting for build time before health check

## Deployment Wait Times

| Application Type | Typical Build Time | Recommended Wait |
|------------------|-------------------|------------------|
| Static site | 10-30 seconds | 30 seconds |
| Node.js/Express | 30-90 seconds | 60-90 seconds |
| Python/Django | 60-120 seconds | 90-120 seconds |
| Docker build | 90-180 seconds | 120-180 seconds |

## Health Check Best Practices

1. **Health endpoint must return 200 OK when ready:**
   ```javascript
   // In backend server.js
   app.get('/health', (req, res) => {
       res.status(200).json({ status: 'ok', timestamp: Date.now() });
   });
   ```

2. **Use timeout on health check:**
   ```python
   try:
       response = requests.get(health_url, timeout=10)
       return response.status_code == 200
   except requests.exceptions.Timeout:
       return False
   ```

3. **Retry health check with backoff:**
   ```python
   for attempt in range(5):
       if verify_health(health_url):
           return True
       time.sleep(20 * (attempt + 1))  # 20s, 40s, 60s, 80s, 100s
   return False
   ```

## Related Issues

- Environment variables must be set before triggering deploy
- Health URL must use HTTPS (separate gotcha)
- Render may rate-limit deploy triggers (max ~10/hour per service)

## References

- Render Deploys API: https://api-docs.render.com/reference/create-deploy
- Agent Forge Adapter: adapters/hosting.py - RenderAdapter.trigger_deploy()
- Research Date: 2026-08-03
