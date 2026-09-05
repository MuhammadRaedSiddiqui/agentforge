"""
Unit tests for Node.js diff validator.

Tests cover:
- HMAC verification presence
- Embedded secret detection
- Unrelated change detection
- File hash matching
- Diff format validation
"""

import pytest

from agents.nodejs_agent.validator import NodeJsValidator

pytestmark = pytest.mark.unit


class TestNodeJsDiffValidator:
    """Test suite for Node.js server diff validation."""

    def test_valid_diff(self) -> None:
        """Test that a valid diff with HMAC verification passes."""
        diff = """
--- server.js
+++ server.js
@@ -10,6 +10,15 @@
 const app = express();
 app.use(express.json());

+// HMAC verification middleware
+function verifyHmac(req, res, next) {
+    const signature = req.headers['x-signature'];
+    const hmac = crypto.createHmac('sha256', process.env.WEBHOOK_SECRET);
+    const expectedSignature = hmac.update(JSON.stringify(req.body)).digest('hex');
+    if (signature === expectedSignature) return next();
+    res.status(401).json({ error: 'Invalid signature' });
+}
+
 // Test Org webhook endpoint
 app.post('/webhook/test_org', verifyHmac, async (req, res) => {
     const { event, data } = req.body;
"""

        validator = NodeJsValidator()
        result = validator.validate_diff(diff, expected_org_id="test_org", file_hash="abc123")

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_missing_hmac_verification(self) -> None:
        """Test that missing HMAC verification is detected."""
        diff = """
--- server.js
+++ server.js
@@ -10,6 +10,8 @@
 const app = express();
 app.use(express.json());

 // Test Org webhook endpoint
-app.post('/webhook/test_org', async (req, res) => {
+app.post('/webhook/test_org', async (req, res) => {
     const { event, data } = req.body;
+    console.log('Received event:', event);
     res.json({ success: true });
"""

        validator = NodeJsValidator()
        result = validator.validate_diff(diff, expected_org_id="test_org", file_hash="abc123")

        assert result.is_valid is False
        assert any(
            "hmac" in error.lower() or "verification" in error.lower() for error in result.errors
        )

    def test_embedded_secret_detected(self) -> None:
        """Test that embedded secrets in diff are detected."""
        diff = """
--- server.js
+++ server.js
@@ -10,6 +10,10 @@
 const app = express();
 app.use(express.json());

+// Webhook endpoint
+const WEBHOOK_SECRET = 'sk-1234567890abcdef';  // Hardcoded secret!
+
 app.post('/webhook/test_org', verifyHmac, async (req, res) => {
     res.json({ success: true });
 });
"""

        validator = NodeJsValidator()
        result = validator.validate_diff(diff, expected_org_id="test_org", file_hash="abc123")

        assert result.is_valid is False
        assert any("secret" in error.lower() for error in result.errors)

    def test_unrelated_change_detected(self) -> None:
        """Test that changes to unrelated organization endpoints are detected."""
        diff = """
--- server.js
+++ server.js
@@ -15,7 +15,7 @@
 });

 // Other Org webhook endpoint
-app.post('/webhook/other_org', verifyHmac, async (req, res) => {
+app.post('/webhook/other_org', async (req, res) => {  // HMAC removed!
     const { event, data } = req.body;
     res.json({ success: true });
 });
"""

        validator = NodeJsValidator()
        result = validator.validate_diff(diff, expected_org_id="test_org", file_hash="abc123")

        assert result.is_valid is False
        assert any(
            "unrelated" in error.lower() or "other" in error.lower() for error in result.errors
        )

    def test_file_hash_mismatch(self) -> None:
        """Test that file hash mismatch is detected."""
        diff = """
--- server.js
+++ server.js
@@ -10,6 +10,8 @@
 const app = express();
"""

        validator = NodeJsValidator()
        # Provide mismatched hash
        result = validator.validate_diff(
            diff, expected_org_id="test_org", file_hash="abc123", actual_source_hash="def456"
        )

        assert result.is_valid is False
        assert any(
            "hash" in error.lower() or "mismatch" in error.lower() for error in result.errors
        )

    def test_malformed_diff_format(self) -> None:
        """Test that malformed diff format is detected."""
        diff = """
This is not a valid unified diff format
Just some random text
"""

        validator = NodeJsValidator()
        result = validator.validate_diff(diff, expected_org_id="test_org", file_hash="abc123")

        assert result.is_valid is False
        assert any("diff" in error.lower() or "format" in error.lower() for error in result.errors)

    def test_valid_diff_with_proper_scoping(self) -> None:
        """Test that properly scoped changes pass validation."""
        diff = """
--- server.js
+++ server.js
@@ -30,6 +30,20 @@
 app.post('/webhook/existing_org', verifyHmac, async (req, res) => {
     res.json({ success: true });
 });

+// Test Org webhook endpoints
+app.post('/webhook/test_org/booking', verifyHmac, async (req, res) => {
+    const { appointmentId, clientName } = req.body;
+    // Process booking
+    res.json({ success: true, appointmentId });
+});
+
+app.post('/webhook/test_org/cancellation', verifyHmac, async (req, res) => {
+    const { appointmentId } = req.body;
+    // Process cancellation
+    res.json({ success: true });
+});
+
 // Health check
 app.get('/health', (req, res) => {
     res.json({ status: 'ok' });
"""

        validator = NodeJsValidator()
        result = validator.validate_diff(diff, expected_org_id="test_org", file_hash="abc123")

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_environment_variable_usage_allowed(self) -> None:
        """Test that environment variable usage is allowed (not hardcoded secrets)."""
        diff = """
--- server.js
+++ server.js
@@ -10,6 +10,10 @@
 const app = express();

+// Load webhook secret from environment
+const webhookSecret = process.env.WEBHOOK_SECRET;
+if (!webhookSecret) throw new Error('WEBHOOK_SECRET not configured');
+
 app.post('/webhook/test_org', verifyHmac, async (req, res) => {
     res.json({ success: true });
 });
"""

        validator = NodeJsValidator()
        result = validator.validate_diff(diff, expected_org_id="test_org", file_hash="abc123")

        # Should not flag environment variable usage as a secret
        secret_errors = [
            e for e in result.errors if "secret" in e.lower() and "hardcoded" in e.lower()
        ]
        assert len(secret_errors) == 0

    def test_deletion_only_diff(self) -> None:
        """Test that deletion-only diffs are validated."""
        diff = """
--- server.js
+++ server.js
@@ -15,10 +15,5 @@
 app.use(express.json());

-// Old Test Org endpoint (being removed)
-app.post('/webhook/test_org_old', async (req, res) => {
-    res.json({ success: true });
-});
-
 // Health check
 app.get('/health', (req, res) => {
"""

        validator = NodeJsValidator()
        result = validator.validate_diff(diff, expected_org_id="test_org", file_hash="abc123")

        # Deletion should be allowed if it's for the correct org
        assert result.is_valid is True

    def test_multiple_client_changes_detected(self) -> None:
        """Test that changes affecting multiple clients are detected."""
        diff = """
--- server.js
+++ server.js
@@ -10,6 +10,8 @@

 // Modified for all clients
-app.use(express.json());
+app.use(express.json({ limit: '10mb' }));  // Affects all endpoints
+app.use(cors());  // New global middleware

 app.post('/webhook/test_org', verifyHmac, async (req, res) => {
"""

        validator = NodeJsValidator()
        result = validator.validate_diff(diff, expected_org_id="test_org", file_hash="abc123")

        assert result.is_valid is False
        assert any(
            "global" in error.lower() or "unrelated" in error.lower() for error in result.errors
        )

    def test_placeholder_detection(self) -> None:
        """Test that unresolved placeholders are detected."""
        diff = """
--- server.js
+++ server.js
@@ -10,6 +10,8 @@

+// {{CLIENT_NAME}} webhook endpoint
+app.post('/webhook/{{ORG_ID}}', verifyHmac, async (req, res) => {
     res.json({ success: true });
 });
"""

        validator = NodeJsValidator()
        result = validator.validate_diff(diff, expected_org_id="test_org", file_hash="abc123")

        assert result.is_valid is False
        assert any("placeholder" in error.lower() for error in result.errors)
