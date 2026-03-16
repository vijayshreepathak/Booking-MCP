"""
Metadata registry shared by the MCP server and REST compatibility endpoints.

The actual protocol server lives in `app.mcp_server_app` and exposes tools through
JSON-RPC MCP methods such as `initialize`, `tools/list`, and `tools/call`.
"""
from typing import Any

from app.mcp_tool_registry import registry
import app.tool_dispatcher  # noqa: F401  Ensures tools register at import time.

BASE_URL = "http://localhost:8000"


def get_tools_metadata(base_url: str = BASE_URL) -> list[dict[str, Any]]:
    """Return dynamic MCP tool metadata with input/output schemas and call URL."""
    return registry.list_legacy_metadata(base_url)
