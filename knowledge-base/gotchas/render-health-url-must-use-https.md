# Gotcha: Render Health URL Must Use HTTPS

**Platform:** Render / Configuration  
**Topic:** Health Check Configuration  
**Symptom:** Configuration validation fails with "HOSTING_HEALTH_URL must start with https://"  
**Verification Status:** Verified  
**Approved By:** system  
**Approved At:** 2026-08-03

## Root Cause

Agent Forge's configuration validation enforces that the `HOSTING_HEALTH_URL` environment variable must use HTTPS (not HTTP) for security reasons. This is because:

1. **Production services must use TLS/SSL** for encrypted communication
2. **Render automatically provisions SSL** for all services on `.onrender.com` domains
3. **Health checks expose service status** and should be encrypted
4. **HTTP health URLs indicate misconfiguration** that could lead to production issues

The validation in `cli/config.py` explicitly checks:
```python
if not config.hosting_health_url.startswith("https://"):
    raise ConfigurationError("HOSTING_HEALTH_URL must start with https://")
```

## Resolution

1. **Always use HTTPS for Render health URLs:**
   ```bash
   # .env file - Correct
   HOSTING_HEALTH_URL=https://myservice.onrender.com/health
   
   # Wrong - will fail validation
   HOSTING_HEALTH_URL=http://myservice.onrender.com/health
   ```

2. **Render services automatically get HTTPS:**
   ```
   Service created on Render: myservice
   Automatic HTTPS URL: https://myservice.onrender.com
   Health endpoint: https://myservice.onrender.com/health
   
   DO NOT use: http://myservice.onrender.com/health
   ```

3. **Configuration validation in code:**
   ```python
   # In cli/config.py - load_config()
   
   def load_config(env_file: str | None = None) -> AgentForgeConfig:
       # ... load environment variables ...
       
       # Validate HTTPS requirement
       if not health_url.startswith("https://"):
           raise ConfigurationError(
               "HOSTING_HEALTH_URL must use HTTPS. "
               f"Got: {health_url}. "
               "Render services automatically support HTTPS on .onrender.com domains."
           )
       
       return config
   ```

## Detection

```python
# When configuration fails to load
try:
    config = load_config()
except ConfigurationError as e:
    if "https://" in str(e).lower():
        print("Error: Health URL must use HTTPS, not HTTP")
        print("Update your .env file:")
        print("  HOSTING_HEALTH_URL=https://yourservice.onrender.com/health")
        sys.exit(1)
```

## Prevention

- Always set HTTPS URLs in `.env` file
- Document HTTPS requirement in `.env.example`
- Validate health URL at configuration load time (already implemented)
- Provide clear error messages when HTTP is used
- Test configuration with `agent-forge config check` after setup

## Common Causes

- Copying HTTP URL from Render dashboard (should use HTTPS)
- Not knowing that Render automatically provisions SSL
- Testing locally with HTTP and forgetting to change for Render
- Typo in `.env` file (http:// instead of https://)

## Related Issues

- Health endpoint must return 200 OK for verification to succeed
- Health URL must be publicly accessible (not behind authentication)
- Render may take 30-60 seconds after deploy before health endpoint responds

## Render Service URL Patterns

| Service Type | URL Pattern | HTTPS Support |
|--------------|-------------|---------------|
| Web Service | `https://{service-name}.onrender.com` | ✅ Automatic |
| Private Service | Internal only, no public URL | N/A |
| Static Site | `https://{site-name}.onrender.com` | ✅ Automatic |

## Custom Domains

If using a custom domain with Render:
```bash
# Render automatically provisions SSL for custom domains
HOSTING_HEALTH_URL=https://yourdomain.com/health

# NOT:
HOSTING_HEALTH_URL=http://yourdomain.com/health  # Will fail validation
```

Render handles SSL certificate provisioning for custom domains automatically via Let's Encrypt.

## Testing Health Endpoint

```bash
# Verify health endpoint works with HTTPS
curl -v https://myservice.onrender.com/health

# Should return:
# < HTTP/2 200
# < content-type: application/json
# {"status":"ok","timestamp":1722700000000}
```

## References

- Render SSL Documentation: https://render.com/docs/free-ssl
- Agent Forge Config Validation: cli/config.py - load_config()
- Configuration Example: .env.example
- Research Date: 2026-08-03
