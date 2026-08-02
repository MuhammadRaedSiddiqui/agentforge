"""
Supabase client adapter for Agent Forge.

Implements allowlisted operations for the client-facing Supabase project
following tool-contracts.yaml.

IMPORTANT: This adapter is for CLIENT data operations, not internal
operational store. It enforces strict table allowlists and never
executes arbitrary model-generated SQL.
"""

import os
from typing import Any

import requests

from adapters.base import AdapterReceipt
from shared.errors import (
    AuthorizationError,
    ConflictError,
    PermanentError,
    TransientError,
    ValidationError,
)

# Allowlisted tables for client operations
ALLOWED_TABLES = {
    "organizations",  # Client organization records
}


class SupabaseClientAdapter:
    """
    Live adapter for Supabase client project REST API operations.

    All operations follow contracts from tool-contracts.yaml:
    - Timeout: 10s connect, 30s read
    - Retry: max 2 for transient failures on read-only operations
    - Redaction: all secrets removed from logs and receipts
    - Table enforcement: only allowlisted tables permitted
    """

    def __init__(self) -> None:
        """Initialize Supabase client adapter with credentials from environment."""
        self.project_url = self._load_project_url()
        self.service_role_key = self._load_service_role_key()
        self.base_url = f"{self.project_url}/rest/v1"
        self.session = requests.Session()

    def _load_project_url(self) -> str:
        """Load Supabase client project URL from environment."""
        url = os.getenv("SUPABASE_CLIENT_URL")
        if not url:
            raise ValidationError(
                "SUPABASE_CLIENT_URL not found in environment",
                field="SUPABASE_CLIENT_URL",
                context={"adapter": "supabase_client"},
            )

        # Validate HTTPS
        if not url.startswith("https://"):
            raise ValidationError(
                "SUPABASE_CLIENT_URL must use HTTPS",
                field="SUPABASE_CLIENT_URL",
                context={"url": url},
            )

        return url.rstrip("/")

    def _load_service_role_key(self) -> str:
        """Load Supabase client service role key from environment."""
        key = os.getenv("SUPABASE_CLIENT_SERVICE_ROLE_KEY")
        if not key:
            raise ValidationError(
                "SUPABASE_CLIENT_SERVICE_ROLE_KEY not found in environment",
                field="SUPABASE_CLIENT_SERVICE_ROLE_KEY",
                context={"adapter": "supabase_client"},
            )
        return key

    def _get_headers(self) -> dict[str, str]:
        """Build request headers with authorization."""
        return {
            "apikey": self.service_role_key,
            "Authorization": f"Bearer {self.service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=representation",
        }

    def _request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        operation: str,
        json_data: dict[str, Any] | None = None,
    ) -> Any:
        """
        Make HTTP request with error handling.

        Args:
            method: HTTP method
            url: Full URL
            headers: Request headers
            operation: Operation name for error context
            json_data: JSON payload

        Returns:
            Response JSON data (array or object)

        Raises:
            Typed exceptions based on error classification
        """
        try:
            response = self.session.request(
                method=method,
                url=url,
                headers=headers,
                json=json_data,
                timeout=(10, 30),  # 10s connect, 30s read
            )

            # Check status code
            if response.status_code == 401 or response.status_code == 403:
                raise AuthorizationError(f"HTTP {response.status_code}: Unauthorized")
            elif response.status_code == 404:
                raise PermanentError(f"HTTP {response.status_code}: Not found")
            elif response.status_code == 409:
                raise ConflictError(f"HTTP {response.status_code}: Conflict")
            elif response.status_code >= 500:
                raise TransientError(f"HTTP {response.status_code}: Server error")
            elif response.status_code >= 400:
                raise PermanentError(f"HTTP {response.status_code}: Client error")

            # Success - return JSON
            return response.json()

        except requests.Timeout as e:
            raise TransientError(f"Request timeout: {e}")
        except requests.ConnectionError as e:
            raise TransientError(f"Connection error: {e}")
        except requests.RequestException as e:
            raise PermanentError(f"Request failed: {e}")

    def _validate_table_name(self, table_name: str) -> None:
        """
        Validate table name is in the allowlist.

        This is a critical security boundary. Table names MUST come from
        deterministic adapter code, never from model output.
        """
        if table_name not in ALLOWED_TABLES:
            raise ValidationError(
                f"Table '{table_name}' is not in the allowlist",
                field="table_name",
                context={
                    "adapter": "supabase_client",
                    "requested": table_name,
                    "allowed": list(ALLOWED_TABLES),
                },
            )

    def select_rows(
        self,
        table_name: str | None = None,
        organization_id: str | None = None,
        select_fields: str | None = None,
        *,
        table: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> AdapterReceipt:
        """
        Read rows from an allowlisted table.

        Args:
            table_name: Table name (must be in ALLOWED_TABLES)
            organization_id: Filter by organization_id (optional)
            select_fields: PostgREST select parameter (optional)

        Returns:
            AdapterReceipt with rows array

        Contract: tool-contracts.yaml#/paths/~1rest~1v1~1{tableName}/get
        """
        resolved_table = table_name or table
        if not resolved_table:
            raise ValidationError(
                "table_name is required",
                field="table_name",
                context={"operation": "select_rows"},
            )

        self._validate_table_name(resolved_table)

        url = f"{self.base_url}/{resolved_table}"

        # Build query parameters
        params = []
        if select_fields:
            params.append(f"select={select_fields}")
        filter_organization_id = organization_id
        if filters and "organization_id" in filters and isinstance(filters["organization_id"], str):
            filter_organization_id = filters["organization_id"]

        if filter_organization_id:
            # PostgREST filter syntax
            params.append(f"organization_id=eq.{filter_organization_id}")
        if filters:
            for field_name, field_value in filters.items():
                if field_name == "organization_id":
                    continue
                params.append(f"{field_name}=eq.{field_value}")

        if params:
            url += "?" + "&".join(params)

        response = self._request(
            method="GET",
            url=url,
            headers=self._get_headers(),
            operation="select_rows",
        )

        # Response is an array of rows
        if not isinstance(response, list):
            raise PermanentError(
                "Supabase select_rows response must be an array",
                context={
                    "operation": "select_rows",
                    "table": resolved_table,
                    "type": type(response).__name__,
                },
            )

        return AdapterReceipt(
            platform="supabase_client",
            operation="select_rows",
            remote_id=None,
            status="success",
            response_data={"rows": response, "count": len(response), "table": resolved_table},
            idempotency_key=None,
            can_retry=True,
        )

    def insert_org_record(
        self,
        organization_id: str,
        business_name: str,
        timezone: str | None = None,
        configuration: dict[str, Any] | None = None,
    ) -> AdapterReceipt:
        """
        Insert an organization record into the client database.

        Args:
            organization_id: Unique organization identifier (slug)
            business_name: Business name
            timezone: IANA timezone (optional)
            configuration: Additional configuration (optional)

        Returns:
            AdapterReceipt with inserted record

        Contract: tool-contracts.yaml#/paths/~1rest~1v1~1{tableName}/post
        """
        # This operation is hardcoded to the organizations table
        table_name = "organizations"
        self._validate_table_name(table_name)

        # Validate required fields
        if not organization_id or not business_name:
            raise ValidationError(
                "organization_id and business_name are required",
                field="organization_id,business_name",
                context={"operation": "insert_org_record"},
            )

        # Validate organization_id format (lowercase alphanumeric and underscores)
        import re

        if not re.match(r"^[a-z][a-z0-9_]*$", organization_id):
            raise ValidationError(
                "organization_id must start with a lowercase letter and contain only lowercase letters, digits, and underscores",
                field="organization_id",
                context={"value": organization_id},
            )

        # Build payload following SupabaseOrganizationInsert schema
        payload: dict[str, Any] = {
            "organization_id": organization_id,
            "display_name": business_name,
        }

        if timezone:
            payload["timezone"] = timezone

        if configuration:
            payload["metadata"] = configuration

        url = f"{self.base_url}/{table_name}"
        response = self._request(
            method="POST",
            url=url,
            headers=self._get_headers(),
            json_data=payload,
            operation="insert_org_record",
        )

        # Response is an array with the inserted row
        if not isinstance(response, list) or len(response) == 0:
            raise PermanentError(
                "Supabase insert_org_record response must be a non-empty array",
                context={
                    "operation": "insert_org_record",
                    "table": table_name,
                    "type": type(response).__name__,
                },
            )

        inserted_row = response[0]

        return AdapterReceipt(
            platform="supabase_client",
            operation="insert_org_record",
            remote_id=organization_id,
            status="success",
            response_data=inserted_row,
            idempotency_key=organization_id,  # organization_id is immutable
            can_retry=False,  # Requires reconciliation before retry
        )

    def update_org_record(
        self,
        organization_id: str,
        updates: dict[str, Any],
    ) -> AdapterReceipt:
        """
        Update an organization record.

        Args:
            organization_id: Organization identifier
            updates: Fields to update

        Returns:
            AdapterReceipt with updated record

        Note: This is a future operation for US7 (updates). Included for completeness.
        """
        table_name = "organizations"
        self._validate_table_name(table_name)

        if not organization_id or not updates:
            raise ValidationError(
                "organization_id and updates are required",
                field="organization_id,updates",
                context={"operation": "update_org_record"},
            )

        # Cannot update the immutable organization_id field
        if "organization_id" in updates:
            raise ValidationError(
                "organization_id is immutable and cannot be updated",
                field="updates.organization_id",
                context={"operation": "update_org_record"},
            )

        url = f"{self.base_url}/{table_name}?organization_id=eq.{organization_id}"
        response = self._request(
            method="PATCH",
            url=url,
            headers=self._get_headers(),
            json_data=updates,
            operation="update_org_record",
        )

        # Response is an array with the updated row(s)
        if not isinstance(response, list):
            raise PermanentError(
                "Supabase update_org_record response must be an array",
                context={
                    "operation": "update_org_record",
                    "table": table_name,
                    "type": type(response).__name__,
                },
            )

        if len(response) == 0:
            raise PermanentError(
                f"Organization not found with organization_id: {organization_id}",
                context={"operation": "update_org_record", "organization_id": organization_id},
            )

        updated_row = response[0]

        return AdapterReceipt(
            platform="supabase_client",
            operation="update_org_record",
            remote_id=organization_id,
            status="success",
            response_data=updated_row,
            idempotency_key=None,
            can_retry=False,  # Updates require read-before-write staleness check
        )

    def delete_org_record(self, organization_id: str) -> AdapterReceipt:
        """
        Delete an organization record (compensation operation).

        Args:
            organization_id: Organization identifier

        Returns:
            AdapterReceipt confirming deletion

        Note: This is a destructive compensation operation requiring separate approval.
        """
        table_name = "organizations"
        self._validate_table_name(table_name)

        if not organization_id:
            raise ValidationError(
                "organization_id is required",
                field="organization_id",
                context={"operation": "delete_org_record"},
            )

        url = f"{self.base_url}/{table_name}?organization_id=eq.{organization_id}"

        # Use Prefer: return=representation to get deleted row
        headers = self._get_headers()

        response = self._request(
            method="DELETE",
            url=url,
            headers=headers,
            operation="delete_org_record",
        )

        # Response is an array with deleted row(s)
        if not isinstance(response, list):
            raise PermanentError(
                "Supabase delete_org_record response must be an array",
                context={
                    "operation": "delete_org_record",
                    "table": table_name,
                    "type": type(response).__name__,
                },
            )

        return AdapterReceipt(
            platform="supabase_client",
            operation="delete_org_record",
            remote_id=organization_id,
            status="success",
            response_data={"deleted": True, "rows": response, "count": len(response)},
            idempotency_key=None,
            can_retry=True,  # Deletion is idempotent
        )
