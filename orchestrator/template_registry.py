"""
Source template registry for Agent Forge.

Manages loading, versioning, and validation of ground-truth templates used
for generating client-specific deployment artifacts.

Features:
- Load templates from ground-truth/ directory
- Version tracking and hash verification
- Active/superseded status management
- Thread-safe singleton pattern
"""

import hashlib
import json
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


@dataclass
class TemplateMetadata:
    """Metadata for a source template."""

    template_id: str
    version: str
    template_type: str  # 'vapi_assistant', 'vapi_tool', 'make_blueprint', 'database_schema'
    file_path: Path
    content_hash: str
    loaded_at: datetime
    status: str  # 'active', 'superseded', 'deprecated'
    placeholders: list[str]
    capabilities: list[str] | None = None
    metadata: dict[str, Any] | None = None


class TemplateRegistry:
    """
    Registry for managing source templates.

    Implements singleton pattern to ensure only one registry instance exists.
    Thread-safe for concurrent access.
    """

    _instance: Optional["TemplateRegistry"] = None
    _lock = threading.Lock()
    _initialized: bool

    def __new__(cls) -> "TemplateRegistry":
        """Ensure singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialize the template registry."""
        if self._initialized:
            return

        self._templates: dict[str, TemplateMetadata] = {}
        self._templates_by_type: dict[str, list[str]] = {}
        self._ground_truth_dir = Path(__file__).parent.parent / "ground-truth"
        self._initialized = True

    def load_all_templates(self) -> None:
        """
        Load all templates from the ground-truth directory.

        Scans the directory structure and loads:
        - Vapi assistant config
        - Vapi tool schemas
        - Make.com blueprints
        - Database schema templates
        """
        self._templates.clear()
        self._templates_by_type.clear()

        # Load Vapi assistant template
        vapi_assistant_path = self._ground_truth_dir / "configs" / "vapi_assistant_template.json"
        if vapi_assistant_path.exists():
            self._load_json_template(vapi_assistant_path, "vapi_assistant", "vapi_assistant_config")

        # Load Vapi tool schemas
        vapi_tools_dir = self._ground_truth_dir / "configs" / "vapi_tools"
        if vapi_tools_dir.exists():
            for tool_file in vapi_tools_dir.glob("*.json"):
                template_id = f"vapi_tool_{tool_file.stem}"
                self._load_json_template(tool_file, template_id, "vapi_tool")

        # Load Make.com blueprints
        make_blueprints_dir = self._ground_truth_dir / "configs" / "make_blueprints"
        if make_blueprints_dir.exists():
            for blueprint_file in make_blueprints_dir.glob("*.json"):
                template_id = f"make_blueprint_{blueprint_file.stem}"
                self._load_json_template(blueprint_file, template_id, "make_blueprint")

        # Load database schema
        schema_path = self._ground_truth_dir / "schemas" / "client_database_template.sql"
        if schema_path.exists():
            self._load_sql_template(schema_path, "database_schema", "database_schema")

    def _load_json_template(self, file_path: Path, template_id: str, template_type: str) -> None:
        """Load a JSON template file."""
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
                template_data = json.loads(content)

            # Compute content hash
            content_hash = self._compute_hash(content)

            # Extract placeholders
            placeholders = self._extract_placeholders(content)

            # Extract metadata if present
            metadata = template_data.get("metadata", {})
            version = metadata.get("template_version", "1.0.0")
            capabilities = (
                metadata.get("capabilities", [])
                if isinstance(metadata.get("capabilities"), list)
                else None
            )

            # Create template metadata
            template_meta = TemplateMetadata(
                template_id=template_id,
                version=version,
                template_type=template_type,
                file_path=file_path,
                content_hash=content_hash,
                loaded_at=datetime.now(),
                status="active",
                placeholders=placeholders,
                capabilities=capabilities,
                metadata=metadata,
            )

            # Store template
            self._templates[template_id] = template_meta

            # Index by type
            if template_type not in self._templates_by_type:
                self._templates_by_type[template_type] = []
            self._templates_by_type[template_type].append(template_id)

        except Exception as e:
            raise ValueError(f"Failed to load template {file_path}: {str(e)}")

    def _load_sql_template(self, file_path: Path, template_id: str, template_type: str) -> None:
        """Load a SQL template file."""
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            # Compute content hash
            content_hash = self._compute_hash(content)

            # Extract placeholders
            placeholders = self._extract_placeholders(content)

            # Create template metadata
            template_meta = TemplateMetadata(
                template_id=template_id,
                version="1.0.0",  # Extract from SQL comments if needed
                template_type=template_type,
                file_path=file_path,
                content_hash=content_hash,
                loaded_at=datetime.now(),
                status="active",
                placeholders=placeholders,
            )

            # Store template
            self._templates[template_id] = template_meta

            # Index by type
            if template_type not in self._templates_by_type:
                self._templates_by_type[template_type] = []
            self._templates_by_type[template_type].append(template_id)

        except Exception as e:
            raise ValueError(f"Failed to load SQL template {file_path}: {str(e)}")

    def _compute_hash(self, content: str) -> str:
        """Compute SHA-256 hash of template content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _extract_placeholders(self, content: str) -> list[str]:
        """
        Extract placeholder variables from template content.

        Placeholders are in the format: {{variable_name}}
        """
        import re

        pattern = r"\{\{([^}]+)\}\}"
        matches = re.findall(pattern, content)
        return sorted(set(matches))

    def get_template(self, template_id: str) -> TemplateMetadata | None:
        """
        Get template metadata by ID.

        Args:
            template_id: Unique identifier for the template

        Returns:
            TemplateMetadata if found, None otherwise
        """
        # Agents may be used directly by CLI commands and tests. Load lazily
        # so generation never depends on a separate registry bootstrap step.
        if not self._templates:
            self.load_all_templates()
        return self._templates.get(template_id)

    def get_template_content(self, template_id: str) -> str | None:
        """
        Load and return template content.

        Args:
            template_id: Unique identifier for the template

        Returns:
            Template content as string, or None if not found
        """
        template = self.get_template(template_id)
        if not template:
            return None

        try:
            with open(template.file_path, encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            raise ValueError(f"Failed to read template {template_id}: {str(e)}")

    def get_templates_by_type(self, template_type: str) -> list[TemplateMetadata]:
        """
        Get all templates of a specific type.

        Args:
            template_type: Type of templates to retrieve

        Returns:
            List of template metadata objects
        """
        template_ids = self._templates_by_type.get(template_type, [])
        return [self._templates[tid] for tid in template_ids if tid in self._templates]

    def verify_template_hash(self, template_id: str) -> bool:
        """
        Verify that template file hash matches stored hash.

        Args:
            template_id: Template to verify

        Returns:
            True if hash matches, False otherwise
        """
        template = self.get_template(template_id)
        if not template:
            return False

        try:
            with open(template.file_path, encoding="utf-8") as f:
                current_content = f.read()

            current_hash = self._compute_hash(current_content)
            return current_hash == template.content_hash
        except Exception:
            return False

    def get_active_templates(self) -> list[TemplateMetadata]:
        """Get all templates with 'active' status."""
        return [t for t in self._templates.values() if t.status == "active"]

    def get_template_by_capability(self, capability: str) -> list[TemplateMetadata]:
        """
        Get templates that support a specific capability.

        Args:
            capability: Capability name (e.g., 'booking', 'availability')

        Returns:
            List of templates supporting this capability
        """
        results = []
        for template in self._templates.values():
            if template.capabilities and capability in template.capabilities:
                results.append(template)
        return results

    def get_version_info(self) -> dict[str, Any]:
        """
        Get version information for all loaded templates.

        Returns:
            Dictionary with template versions and metadata
        """
        return {
            "total_templates": len(self._templates),
            "templates_by_type": {
                template_type: len(template_ids)
                for template_type, template_ids in self._templates_by_type.items()
            },
            "templates": {
                template_id: {
                    "version": template.version,
                    "status": template.status,
                    "hash": template.content_hash,
                    "loaded_at": template.loaded_at.isoformat(),
                }
                for template_id, template in self._templates.items()
            },
        }

    def list_templates(self) -> list[str]:
        """Get list of all template IDs."""
        return list(self._templates.keys())

    def reload(self) -> None:
        """Reload all templates from disk."""
        self.load_all_templates()


# Convenience function to get the singleton instance
def get_template_registry() -> TemplateRegistry:
    """Get the singleton template registry instance."""
    return TemplateRegistry()
