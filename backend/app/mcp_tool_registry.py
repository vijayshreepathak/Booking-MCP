"""Dynamic MCP tool registry with executable handlers and schemas."""
from dataclasses import dataclass
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session


ToolHandler = Callable[[Session, dict[str, Any]], dict[str, Any]]


@dataclass
class MCPToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    handler: ToolHandler

    def to_protocol_tool(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "outputSchema": self.output_schema,
        }

    def to_legacy_metadata(self, base_url: str) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "call_url": f"{base_url}/mcp/tools/{self.name}/call",
        }


class MCPToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, MCPToolDefinition] = {}

    def register(
        self,
        *,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        output_schema: dict[str, Any],
    ) -> Callable[[ToolHandler], ToolHandler]:
        def decorator(func: ToolHandler) -> ToolHandler:
            self._tools[name] = MCPToolDefinition(
                name=name,
                description=description,
                input_schema=input_schema,
                output_schema=output_schema,
                handler=func,
            )
            return func

        return decorator

    def list_protocol_tools(self) -> list[dict[str, Any]]:
        return [tool.to_protocol_tool() for tool in self._tools.values()]

    def list_legacy_metadata(self, base_url: str) -> list[dict[str, Any]]:
        return [tool.to_legacy_metadata(base_url) for tool in self._tools.values()]

    def get(self, name: str) -> Optional[MCPToolDefinition]:
        return self._tools.get(name)

    def call(self, name: str, arguments: dict[str, Any], db: Session) -> dict[str, Any]:
        tool = self.get(name)
        if not tool:
            return {"success": False, "error": f"Tool '{name}' not found."}
        return tool.handler(db, arguments)


registry = MCPToolRegistry()
