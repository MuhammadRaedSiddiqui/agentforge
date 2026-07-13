"""
Supabase internal client wrapper for Agent Forge operational store.

Provides connection management and typed access to the internal
Supabase project that stores deployment state and audit records.
"""

from typing import Any, Dict, List, Optional

from supabase import Client, create_client

from cli.config import AgentForgeConfig


class SupabaseInternalClient:
    """
    Wrapper for Supabase internal operational store.

    Manages connection to the separate internal Supabase project
    used for Agent Forge operational records.
    """

    def __init__(self, config: AgentForgeConfig):
        """
        Initialize Supabase internal client.

        Args:
            config: Agent Forge configuration with internal Supabase credentials
        """
        self.config = config
        self._client: Optional[Client] = None

    @property
    def client(self) -> Client:
        """
        Get or create Supabase client.

        Returns:
            Initialized Supabase client

        Raises:
            ConnectionError: If client cannot be created
        """
        if self._client is None:
            try:
                self._client = create_client(
                    self.config.supabase_internal_url,
                    self.config.supabase_internal_service_role_key,
                )
            except Exception as e:
                raise ConnectionError(
                    f"Failed to create Supabase internal client: {e}"
                ) from e

        return self._client

    def health_check(self) -> bool:
        """
        Check if connection to internal Supabase is healthy.

        Returns:
            True if connection is healthy, False otherwise
        """
        try:
            # Try a simple query to verify connection
            result = self.client.table("organizations").select("count").limit(1).execute()
            return result is not None
        except Exception:
            return False

    def insert(self, table: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Insert a row into a table.

        Args:
            table: Table name
            data: Row data to insert

        Returns:
            Inserted row data

        Raises:
            Exception: If insert fails
        """
        result = self.client.table(table).insert(data).execute()
        if result.data:
            return result.data[0]
        raise Exception(f"Insert failed for table {table}")

    def select(
        self,
        table: str,
        columns: str = "*",
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Select rows from a table.

        Args:
            table: Table name
            columns: Columns to select (default "*")
            filters: Filter conditions (e.g., {"status": "active"})
            order_by: Column to order by
            limit: Maximum number of rows to return

        Returns:
            List of matching rows
        """
        query = self.client.table(table).select(columns)

        if filters:
            for key, value in filters.items():
                query = query.eq(key, value)

        if order_by:
            query = query.order(order_by)

        if limit:
            query = query.limit(limit)

        result = query.execute()
        return result.data if result.data else []

    def update(
        self, table: str, filters: Dict[str, Any], data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Update rows in a table.

        Args:
            table: Table name
            filters: Filter conditions to identify rows to update
            data: Data to update

        Returns:
            List of updated rows
        """
        query = self.client.table(table).update(data)

        for key, value in filters.items():
            query = query.eq(key, value)

        result = query.execute()
        return result.data if result.data else []

    def delete(self, table: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Delete rows from a table.

        Args:
            table: Table name
            filters: Filter conditions to identify rows to delete

        Returns:
            List of deleted rows
        """
        query = self.client.table(table).delete()

        for key, value in filters.items():
            query = query.eq(key, value)

        result = query.execute()
        return result.data if result.data else []

    def get_by_id(self, table: str, id_column: str, id_value: str) -> Optional[Dict[str, Any]]:
        """
        Get a single row by ID.

        Args:
            table: Table name
            id_column: Name of ID column
            id_value: ID value to search for

        Returns:
            Row data if found, None otherwise
        """
        result = self.client.table(table).select("*").eq(id_column, id_value).execute()

        if result.data and len(result.data) > 0:
            return result.data[0]
        return None

    def close(self) -> None:
        """
        Close the Supabase client connection.

        Note: The Supabase Python client doesn't require explicit closing,
        but this method is provided for consistency.
        """
        self._client = None
