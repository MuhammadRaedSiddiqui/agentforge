"""
Node.js agent for generating backend server diffs.

This agent reads the current server.js file, generates unified diffs for
adding new client webhook routes, and validates HMAC security.
"""

import hashlib
from pathlib import Path
from typing import Any

from agents.nodejs_agent.tools import generate_diff, verify_hmac_presence
from agents.nodejs_agent.validator import NodeJsValidator
from shared.hashing import compute_content_hash
from shared.result_object import ResultObject
from shared.task_object import TaskObject


class NodeJsAgent:
    """
    Specialist agent for generating Node.js backend diffs.

    Responsibilities:
    - Read current server.js file
    - Generate unified diff for new client routes
    - Ensure HMAC verification is present
    - Validate no unrelated changes
    - Validate no embedded secrets
    - Record field provenance
    - Return typed ResultObject
    """

    def __init__(self) -> None:
        """Initialize the Node.js agent."""
        self.agent_name = "nodejs_agent"
        self.validator = NodeJsValidator()

    def execute(self, task: TaskObject, intake: dict[str, Any]) -> ResultObject:
        """
        Execute the Node.js diff generation task.

        Args:
            task: Task object with generation parameters
            intake: Validated intake data

        Returns:
            ResultObject with generated diff and provenance
        """
        # Get server.js path from environment or intake
        server_source_path = intake.get("server_source_path") or task.metadata.get(
            "server_source_path"
        )
        if not server_source_path:
            raise ValueError("SERVER_SOURCE_PATH not configured")

        server_path = Path(server_source_path)
        if not server_path.exists():
            raise ValueError(f"Server file not found: {server_path}")

        # Read current server.js
        with open(server_path, encoding="utf-8") as f:
            current_content = f.read()

        # Compute hash of current file
        current_hash = hashlib.sha256(current_content.encode("utf-8")).hexdigest()

        # Extract required data from intake
        organization_id = intake.get("organization_id")
        if not isinstance(organization_id, str):
            raise ValueError("organization_id must be a string")

        organization_display_name = intake.get("business_name")
        if not isinstance(organization_display_name, str):
            raise ValueError("business_name must be a string")

        capabilities = intake.get("capabilities", intake.get("enabled_capabilities", []))
        if not isinstance(capabilities, list):
            raise ValueError("capabilities must be a list")

        # Generate new routes for this organization
        new_routes = self._generate_routes(organization_id, capabilities)

        # Generate unified diff
        diff_content = generate_diff(
            current_content=current_content, new_routes=new_routes, organization_id=organization_id
        )

        # Verify HMAC is present in diff
        hmac_check = verify_hmac_presence(diff_content)
        if not hmac_check:
            raise ValueError("Generated diff missing HMAC verification middleware")

        # Validate diff
        validation_result = self.validator.validate_diff(
            diff_content,
            expected_org_id=organization_id,
            file_hash=current_hash,
            actual_source_hash=current_hash,
        )

        if not validation_result.is_valid:
            raise ValueError(f"Generated diff failed validation: {validation_result.errors}")

        # Save diff to output file
        output_dir = Path("outputs") / organization_id / "nodejs"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "server.diff"

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(diff_content)

        # Also save the new routes as a separate file for reference
        routes_path = output_dir / "routes.js"
        with open(routes_path, "w", encoding="utf-8") as f:
            f.write(new_routes)

        # Compute content hash
        content_hash = compute_content_hash(diff_content)

        # Mark field provenance
        field_provenance = {
            "routes": {"type": "derived", "source": "intake.capabilities"},
            "organization_id": {"type": "copied", "source": "intake.organization_id"},
            "hmac_verification": {"type": "defaulted", "source": "template"},
            "webhook_paths": {"type": "derived", "source": "intake.capabilities"},
        }

        # Create result object
        result = ResultObject(
            task_id=task.task_id,
            agent_source=self.agent_name,
            content_hash=content_hash,
            storage_path=str(output_path),
            summary=f"Generated server.js diff for {organization_display_name}",
            field_provenance=field_provenance,
            model_id="gemini-2.5-pro",
            validation_status="verified",
        )

        return result

    def _generate_routes(self, organization_id: str, capabilities: list) -> str:
        """
        Generate webhook route handlers for capabilities.

        Args:
            organization_id: Organization identifier
            capabilities: List of capability names

        Returns:
            JavaScript code for routes
        """
        routes = []

        # HMAC verification middleware (should already exist, but include in comment)
        hmac_middleware = """
// HMAC verification middleware (ensure this exists in server.js)
function verifyHmac(req, res, next) {
    const signature = req.headers['x-signature'];
    if (!signature) {
        return res.status(401).json({ error: 'Missing signature' });
    }
    const hmac = crypto.createHmac('sha256', process.env.WEBHOOK_SECRET);
    const expectedSignature = hmac.update(JSON.stringify(req.body)).digest('hex');
    if (signature === expectedSignature) {
        return next();
    }
    res.status(401).json({ error: 'Invalid signature' });
}
"""

        # Generate routes for each capability
        capability_endpoints = {
            "availability": "availability",
            "booking": "booking",
            "cancellation": "cancellation",
            "rescheduling": "rescheduling",
        }

        for capability in capabilities:
            endpoint = capability_endpoints.get(capability)
            if not endpoint:
                continue

            route_code = f"""
// {organization_id} - {capability} endpoint
app.post('/webhook/{organization_id}/{endpoint}', verifyHmac, async (req, res) => {{
    try {{
        console.log(`[{organization_id}] {capability} request:`, req.body);

        // Forward to Make.com scenario
        const makeResponse = await axios.post(
            process.env.MAKE_{organization_id.upper()}_{capability.upper()}_URL,
            req.body,
            {{
                headers: {{
                    'Content-Type': 'application/json'
                }}
            }}
        );

        res.json(makeResponse.data);
    }} catch (error) {{
        console.error(`[{organization_id}] {capability} error:`, error.message);
        res.status(500).json({{ error: 'Internal server error', capability: '{capability}' }});
    }}
}});
"""
            routes.append(route_code)

        return hmac_middleware + "\n" + "\n".join(routes)
