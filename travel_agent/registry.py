"""ToolRegistry — unified tool registration and routing."""

from __future__ import annotations

from typing import Any, Callable, Optional


class Tool:
    """A tool definition for the LLM."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict,
        handler: Callable[..., str],
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.handler = handler

    def to_openai_tool(self) -> dict:
        """Convert to OpenAI tool format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Registry for all tools. Tools are registered by name and routed to handlers."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool

    def get_openai_tools(self) -> list[dict]:
        """Get all tool definitions in OpenAI format."""
        return [t.to_openai_tool() for t in self._tools.values()]

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """Execute a tool by name with given arguments.

        Returns the result as a string (for LLM consumption).
        """
        tool = self._tools.get(name)
        if not tool:
            return f"错误：未找到工具 '{name}'"

        try:
            result = tool.handler(**arguments)
            return str(result)
        except Exception as e:
            return f"{name} 查询不可用（{e}），请按无此数据推荐"

    def get_tool_names(self) -> list[str]:
        """Get all registered tool names."""
        return list(self._tools.keys())
