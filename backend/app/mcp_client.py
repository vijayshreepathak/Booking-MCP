"""Minimal MCP client for protocol-based tool discovery and invocation."""
import os
from typing import Any, Optional

import httpx

MCP_PROTOCOL_VERSION = "2024-11-05"


class MCPClientError(RuntimeError):
    """Raised when the MCP server returns an error."""


def _server_url() -> str:
    return os.getenv("MCP_SERVER_URL", "http://localhost:8100/mcp")


def _request(method: str, params: Optional[dict[str, Any]] = None, request_id: str = "1") -> dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params or {},
    }
    response = httpx.post(_server_url(), json=payload, timeout=30)
    response.raise_for_status()
    body = response.json()
    if "error" in body:
        raise MCPClientError(body["error"]["message"])
    return body.get("result", {})


def initialize() -> dict[str, Any]:
    return _request(
        "initialize",
        {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "clientInfo": {"name": "agentic-appointment-backend", "version": "1.0.0"},
            "capabilities": {},
        },
        request_id="init",
    )


def list_tools() -> list[dict[str, Any]]:
    initialize()
    result = _request("tools/list", request_id="tools-list")
    return result.get("tools", [])


def call_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    initialize()
    result = _request(
        "tools/call",
        {"name": tool_name, "arguments": arguments},
        request_id=f"call-{tool_name}",
    )
    return result.get("structuredContent", {})


def get_legacy_tools_metadata(base_url: str) -> list[dict[str, Any]]:
    """Convert protocol tool metadata into the legacy REST shape used by the UI/tests."""
    tools = list_tools()
    return [
        {
            "name": tool["name"],
            "description": tool["description"],
            "input_schema": tool.get("inputSchema", {}),
            "output_schema": tool.get("outputSchema", {}),
            "call_url": f"{base_url}/mcp/tools/{tool['name']}/call",
        }
        for tool in tools
    ]
