# ADR-005: Conversational Interface Over JSON Intake

- **Status:** Accepted
- **Date:** 2026-07-23
- **Feature:** 010-conversational-orchestrator
- **Context:** Agent Forge's intake layer requires operators to provide client deployment information. The original design requires writing a JSON file with specific field names, formats, and values. This creates friction: operators must know the schema, get field names exactly right, and provide all information upfront. The decision is whether the primary interface should remain JSON-file-based or become conversational with JSON as a secondary automation path.

## Decision

- **Primary interface**: Natural language conversation via `agent-forge chat` — operators describe clients in plain English
- **Extraction method**: Gemini function calling with typed schemas (not free-form text parsing) to extract structured IntakeData from dialogue
- **Question strategy**: One field at a time, priority-ordered, with natural language (no JSON field names shown to user)
- **Confirmation**: Plain-language plan summary before execution — never raw JSON
- **Backward compatibility**: JSON intake (`--intake file.json`) preserved as automation/scripting path
- **Handoff boundary**: The conversational layer produces the same `IntakeData` object that JSON intake produces — everything downstream is identical

## Consequences

### Positive

- Operators do not need to learn the intake schema to deploy a client
- Field validation errors become clarifying questions rather than cryptic rejection messages
- The system can infer fields (e.g., org_id from business name) and confirm, reducing input burden
- Ambiguous capability descriptions are resolved interactively rather than rejected
- The JSON path still exists for CI/CD automation, scripting, and batch operations

### Negative

- Adds a Gemini API dependency to the intake path (previously only execution used the model)
- Extraction quality depends on prompt engineering and function-calling reliability
- Multi-turn conversation state adds complexity (session tracking, partial data, phase management)
- Users with well-structured JSON workflows see no benefit from the conversational path

## Alternatives Considered

- **JSON-only with better error messages**: Improve validation errors to be more helpful. Rejected because: even perfect error messages still require the operator to know the schema upfront; the friction is in the format, not the error quality.
- **Form-based CLI (interactive prompts)**: Use `inquirer`-style sequential prompts for each field. Rejected because: this is essentially the dialogue engine without the intelligence — it cannot handle partial information, corrections, or capability mapping; it is a glorified form, not a conversation.
- **Web UI with form**: Build a web interface. Rejected because: out of scope for v1 (local-first CLI), adds infrastructure, and does not solve the fundamental problem that operators still need to know what fields exist.
- **YAML with comments**: Use a commented YAML template. Rejected because: still requires the operator to edit a structured file; comments help but do not eliminate the friction of format compliance.

## References

- Feature Spec: specs/010-conversational-orchestrator/spec.md
- Implementation Plan: Agent_Forge_Conversational_Implementation_Plan.md
- Constitution: Principle IX (Natural Language Is the Interface)
- Related ADRs: ADR-001 (runtime stack — interface was CLI-only), ADR-004 (deterministic pipeline — unchanged by this decision)
