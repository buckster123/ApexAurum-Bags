"""
Tool Executor Service

Safe execution of tools with context management.
"The bridge between thought and action"
"""

import logging
from typing import Optional
from uuid import UUID

from app.tools import registry, ToolContext, ToolResult, ToolCategory

logger = logging.getLogger(__name__)


class ToolExecutor:
    """
    Safe tool execution with context management.

    Handles:
    - Context creation
    - Tool lookup and validation
    - Execution with error handling
    - Multi-tool execution
    """

    def __init__(
        self,
        user_id: Optional[UUID] = None,
        conversation_id: Optional[UUID] = None,
        agent_id: Optional[str] = None,
    ):
        """Initialize executor with context."""
        self.context = ToolContext(
            user_id=user_id,
            conversation_id=conversation_id,
            agent_id=agent_id,
        )

    async def execute(
        self,
        tool_name: str,
        params: dict,
    ) -> ToolResult:
        """
        Execute a single tool.

        Args:
            tool_name: Name of the tool to execute
            params: Parameters for the tool

        Returns:
            ToolResult with success/failure and result/error
        """
        return await registry.execute(tool_name, params, self.context)

    async def execute_tool_use(
        self,
        tool_use_block: dict,
    ) -> dict:
        """
        Execute a Claude tool_use block and return tool_result.

        Args:
            tool_use_block: Claude's tool_use content block with:
                - id: Tool use ID
                - name: Tool name
                - input: Tool parameters

        Returns:
            Claude-compatible tool_result content block
        """
        tool_id = tool_use_block.get("id")
        tool_name = tool_use_block.get("name")
        tool_input = tool_use_block.get("input", {})

        logger.info(f"Executing tool: {tool_name} (id={tool_id})")

        result = await self.execute(tool_name, tool_input)

        # Format for Claude
        tool_result = result.to_claude_format()
        tool_result["tool_use_id"] = tool_id

        return tool_result

    async def execute_multiple(
        self,
        tool_use_blocks: list[dict],
    ) -> list[dict]:
        """
        Execute multiple tool_use blocks.

        Args:
            tool_use_blocks: List of Claude tool_use content blocks

        Returns:
            List of tool_result content blocks
        """
        results = []
        for block in tool_use_blocks:
            result = await self.execute_tool_use(block)
            results.append(result)
        return results

    @staticmethod
    def get_available_tools(
        categories: Optional[list[ToolCategory]] = None,
    ) -> list[dict]:
        """
        Get tools in Claude API format.

        Args:
            categories: Optional filter by categories

        Returns:
            List of tool definitions for Claude's tools parameter
        """
        return registry.get_claude_tools(categories)

    @staticmethod
    def get_tool_count() -> int:
        """Get number of registered tools."""
        return registry.tool_count

    @staticmethod
    def list_tools() -> list[dict]:
        """List all tools with basic info."""
        return registry.list_tools()


def create_tool_executor(
    user_id: Optional[UUID] = None,
    conversation_id: Optional[UUID] = None,
    agent_id: Optional[str] = None,
) -> ToolExecutor:
    """Create a tool executor with context."""
    return ToolExecutor(
        user_id=user_id,
        conversation_id=conversation_id,
        agent_id=agent_id,
    )
