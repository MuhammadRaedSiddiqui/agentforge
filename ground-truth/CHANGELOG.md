# Ground Truth Template Changelog

This file tracks all versions of ground truth templates used by Agent Forge for client onboarding.

## Version 1.0.0 (2026-07-14)

**Status**: Active  
**Git Commit**: Initial implementation  
**Reviewed By**: System validation  
**Production Status**: Staging-ready

### Templates Included

#### Vapi Templates
- **vapi_assistant_template.json** (v1.0.0)
  - Purpose: Base configuration for Vapi voice assistant
  - Features: GPT-4 model, 11labs voice, 4 function tools
  - Placeholders: organization_display_name, voice_id, server_url, server_url_secret, organization_id
  - Capabilities: availability, booking, cancellation, rescheduling
  - Hash: `<computed-at-runtime>`

#### Vapi Tool Schemas
- **vapi_tools/availability.json** (v1.0.0)
  - Function: check_availability
  - Required params: date
  - Optional params: service_type, duration_minutes
  - Hash: `<computed-at-runtime>`

- **vapi_tools/booking.json** (v1.0.0)
  - Function: book_appointment
  - Required params: date, time, service_type, client_name, client_phone
  - Optional params: client_email, notes
  - Hash: `<computed-at-runtime>`

- **vapi_tools/cancellation.json** (v1.0.0)
  - Function: cancel_appointment
  - Required params: appointment_id, phone
  - Optional params: reason
  - Hash: `<computed-at-runtime>`

- **vapi_tools/rescheduling.json** (v1.0.0)
  - Function: reschedule_appointment
  - Required params: appointment_id, phone, new_date, new_time
  - Optional params: reason
  - Hash: `<computed-at-runtime>`

#### Make.com Blueprints
- **make_blueprints/availability.json** (v1.0.0)
  - Scenario: Availability check workflow
  - Modules: webhook → supabase select → json transform → http response
  - Placeholders: organization_display_name, make_team_id, availability_hook_id, supabase_connection_id, organization_id
  - Hash: `<computed-at-runtime>`

- **make_blueprints/booking.json** (v1.0.0)
  - Scenario: Appointment booking workflow
  - Modules: webhook → generate ID → supabase insert → update availability → json transform → http response
  - Placeholders: organization_display_name, make_team_id, booking_hook_id, supabase_connection_id, organization_id
  - Hash: `<computed-at-runtime>`

- **make_blueprints/cancellation.json** (v1.0.0)
  - Scenario: Appointment cancellation workflow
  - Modules: webhook → verify appointment → router → update status → restore availability → json transform → http response
  - Placeholders: organization_display_name, make_team_id, cancellation_hook_id, supabase_connection_id, organization_id
  - Hash: `<computed-at-runtime>`

- **make_blueprints/rescheduling.json** (v1.0.0)
  - Scenario: Appointment rescheduling workflow
  - Modules: webhook → verify appointment → check new availability → router → update records → json transform → http response
  - Placeholders: organization_display_name, make_team_id, rescheduling_hook_id, supabase_connection_id, organization_id
  - Hash: `<computed-at-runtime>`

#### Database Schema
- **schemas/client_database_template.sql** (v1.0.0)
  - Tables: organizations, appointments, availability_slots
  - RLS policies: Full tenant isolation on all tables
  - Indexes: Performance indexes on key columns
  - Triggers: Auto-update updated_at timestamps
  - Placeholders: organization_id, display_name, phone, email, industry
  - Hash: `<computed-at-runtime>`

### Template Dependencies

All templates in v1.0.0 are mutually compatible and tested together as a cohesive package.

**Cross-template References:**
- Vapi tools reference Make.com webhook endpoints via `server_url`
- Make.com scenarios reference Supabase tables defined in database schema
- All templates share `organization_id` as the primary tenant isolation key

### Validation Rules

Templates in this version enforce:
1. **Security**: No secrets in templates; all credentials via placeholders
2. **Isolation**: All database operations filtered by organization_id
3. **HTTPS**: All webhook URLs must use HTTPS protocol
4. **E.164**: Phone numbers must follow E.164 international format
5. **Idempotency**: Database operations use ON CONFLICT / conditional updates
6. **Provenance**: All generated fields track their source (intake/inferred/defaulted)

### Breaking Changes

None (initial version)

### Known Limitations

1. **Service Types**: Hardcoded enum placeholder `{{service_types}}` requires runtime substitution
2. **Voice Selection**: Single voice_id placeholder; multi-voice scenarios require template extension
3. **Timezone**: Database defaults to UTC; business hours respect organization timezone setting
4. **Appointment Duration**: Fixed 60-minute slots in availability template
5. **Retry Logic**: Make.com scenarios do not include automatic retry on transient failures

### Upgrade Path

To upgrade to a future version:
1. Review the upgrade notes in the new version's changelog entry
2. Run the template registry's version compatibility check
3. Regenerate all artifacts for affected organizations
4. Test in staging before production deployment

### Verification Checklist

Before using templates from this version in production:
- [ ] All template files load without JSON/SQL syntax errors
- [ ] Placeholder patterns are consistent across all templates
- [ ] Database schema migrations pass on isolated test instance
- [ ] Vapi assistant config passes Vapi API validation
- [ ] Make.com blueprints import successfully in Make.com UI
- [ ] Generated artifacts pass all validators (Vapi, Make, SQL, Node.js)
- [ ] Cross-client reference detection catches foreign organization_ids
- [ ] Secret scanner confirms no secrets in any template

---

## Future Versions

Version history for subsequent releases will appear here.

### Version Numbering

- **Major version** (X.0.0): Breaking changes requiring regeneration
- **Minor version** (1.X.0): New features, backward-compatible additions
- **Patch version** (1.0.X): Bug fixes, documentation updates

### Deprecation Policy

Templates remain active for at least 90 days after superseded version is released. Deprecated templates will be marked with:
```
**Status**: Deprecated (use v2.0.0 instead)
**End of Life**: 2026-XX-XX
```

### Template Modification Guidelines

1. Never modify templates directly in ground-truth/ during deployment
2. All template changes require:
   - New version number
   - Changelog entry with rationale
   - Validator updates if structure changes
   - Snapshot test updates for affected fixtures
   - ADR if architectural impact
3. Test new versions with at least one full staging deployment
4. Document migration path for existing deployments

---

**Document Version**: 1.0.0  
**Last Updated**: 2026-07-14  
**Next Review**: 2026-10-14 (quarterly review cycle)
