"""Standalone MCP server exposing tools over JSON-RPC HTTP."""
from contextlib import asynccontextmanager
import json
import os
from typing import Any, Optional

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.db import get_db, init_db
from app.mcp_registry import get_tools_metadata
from app.tool_dispatcher import execute_tool

MCP_PROTOCOL_VERSION = "2024-11-05"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Agentic Appointment MCP Server",
    description="Protocol-based MCP tool server for appointment workflows",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _success(request_id: Optional[str], result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Optional[str], code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _mcp_tools_payload(base_url: str) -> list[dict[str, Any]]:
    legacy_tools = get_tools_metadata(base_url)
    return [
        {
            "name": tool["name"],
            "description": tool["description"],
            "inputSchema": tool["input_schema"],
        }
        for tool in legacy_tools
    ]


@app.post("/mcp")
async def handle_mcp_request(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    body = await request.json()
    request_id = body.get("id")
    method = body.get("method")
    params = body.get("params", {}) or {}
    base_url = os.getenv("BASE_URL", "http://localhost:8000")

    if method == "initialize":
        return _success(
            request_id,
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "serverInfo": {"name": "agentic-appointment-mcp-server", "version": "1.0.0"},
                "capabilities": {"tools": {}},
            },
        )

    if method == "notifications/initialized":
        return _success(request_id, {})

    if method == "tools/list":
        return _success(request_id, {"tools": _mcp_tools_payload(base_url)})

    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {}) or {}
        if not tool_name:
            return _error(request_id, -32602, "Missing tool name.")

        result = execute_tool(tool_name, arguments, db)
        is_error = bool(result.get("error")) and not bool(result.get("success"))
        return _success(
            request_id,
            {
                "content": [{"type": "text", "text": json.dumps(result)}],
                "structuredContent": result,
                "isError": is_error,
            },
        )

    return _error(request_id, -32601, f"Method '{method}' not found.")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8100)
