"""
ApexAurum Tool Registry

Central registry for all available tools.
"The hands that serve the mind"
"""

import asyncio
import logging
from typing import Optional

from .base import BaseTool, ToolSchema, ToolResult, ToolContext, ToolCategory

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Central registry for all ApexAurum tools.

    The registry:
    - Stores all available tools
    - Provides Claude-compatible schemas
    - Routes execution requests to tools
    """

    _instance: Optional["ToolRegistry"] = None
    _tools: dict[str, BaseTool]

    def __new__(cls):
        """Singleton pattern for global registry."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = {}
        return cls._instance

    def register(self, tool: BaseTool) -> None:
        """Register a tool in the registry."""
        name = tool.name
        if name in self._tools:
            logger.warning(f"Tool '{name}' already registered, overwriting")
        self._tools[name] = tool
        logger.debug(f"Registered tool: {name} ({tool.category.value})")

    def unregister(self, name: str) -> bool:
        """Remove a tool from the registry."""
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def get_all_tools(self) -> list[BaseTool]:
        """Get all registered tools."""
        return list(self._tools.values())

    def get_tools_by_category(self, category: ToolCategory) -> list[BaseTool]:
        """Get tools filtered by category."""
        return [t for t in self._tools.values() if t.category == category]

    def get_all_schemas(self) -> list[ToolSchema]:
        """Get schemas for all tools."""
        return [tool.schema for tool in self._tools.values()]

    def get_claude_tools(self, categories: Optional[list[ToolCategory]] = None) -> list[dict]:
        """
        Get tools in Claude API format.

        Args:
            categories: Optional filter by categories

        Returns:
            List of tool definitions for Claude's tools parameter
        """
        tools = self._tools.values()
        if categories:
            tools = [t for t in tools if t.category in categories]
        return [tool.schema.to_claude_format() for tool in tools]

    async def execute(
        self,
        name: str,
        params: dict,
        context: ToolContext,
    ) -> ToolResult:
        """
        Execute a tool by name.

        Args:
            name: Tool name
            params: Parameters for the tool
            context: Execution context

        Returns:
            ToolResult with success/failure
        """
        import time
        from app.services.village_events import get_village_broadcaster

        tool = self.get_tool(name)
        if not tool:
            return ToolResult(
                success=False,
                error=f"Unknown tool: {name}",
            )

        # Validate parameters
        is_valid, error = tool.validate_params(params)
        if not is_valid:
            return ToolResult(
                success=False,
                error=error,
            )

        # Get Village broadcaster for real-time visualization
        broadcaster = get_village_broadcaster()
        agent_id = getattr(context, 'agent_id', None) or "CLAUDE"

        # Broadcast tool start to Village GUI
        await broadcaster.broadcast_tool_start(name, params, agent_id)

        # Execute with timing and timeout
        from app.config import get_settings
        timeout = get_settings().tool_execution_timeout

        start_time = time.time()
        try:
            result = await asyncio.wait_for(
                tool.execute(params, context),
                timeout=timeout,
            )
            result.execution_time_ms = (time.time() - start_time) * 1000

            # Broadcast tool complete to Village GUI
            await broadcaster.broadcast_tool_complete(
                name,
                result.result if result.success else result.error,
                success=result.success,
                agent_id=agent_id
            )

            return result
        except asyncio.TimeoutError:
            elapsed = (time.time() - start_time) * 1000
            error_msg = f"Tool execution timed out after {timeout}s"
            logger.warning(f"Tool timeout: {name} ({elapsed:.0f}ms)")

            await broadcaster.broadcast_tool_error(name, error_msg, agent_id)

            # Track tool timeout
            try:
                from app.database import get_db_context
                from app.services.error_tracking import log_error as _log_error
                async with get_db_context() as db:
                    await _log_error(
                        db=db,
                        category="tool_failure",
                        error_type="TimeoutError",
                        message=error_msg,
                        severity="warning",
                        response_time_ms=elapsed,
                        context={"tool_name": name, "agent_id": agent_id},
                    )
            except Exception:
                pass

            return ToolResult(
                success=False,
                error=error_msg,
                execution_time_ms=elapsed,
            )
        except Exception as e:
            logger.exception(f"Tool execution failed: {name}")

            # Broadcast tool error to Village GUI
            await broadcaster.broadcast_tool_error(name, str(e), agent_id)

            # Track tool failure
            try:
                from app.database import get_db_context
                from app.services.error_tracking import log_error as _log_error
                async with get_db_context() as db:
                    await _log_error(
                        db=db,
                        category="tool_failure",
                        error_type=e.__class__.__name__,
                        message=str(e),
                        severity="error",
                        response_time_ms=(time.time() - start_time) * 1000,
                        context={"tool_name": name, "agent_id": agent_id},
                    )
            except Exception:
                pass

            return ToolResult(
                success=False,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )

    @property
    def tool_count(self) -> int:
        """Number of registered tools."""
        return len(self._tools)

    def list_tools(self) -> list[dict]:
        """List all tools with basic info."""
        return [
            {
                "name": tool.name,
                "description": tool.schema.description,
                "category": tool.category.value,
                "requires_confirmation": tool.schema.requires_confirmation,
                "requires_auth": tool.schema.requires_auth,
            }
            for tool in self._tools.values()
        ]


# Global registry instance
registry = ToolRegistry()


def get_registry() -> ToolRegistry:
    """Get the global tool registry."""
    return registry


def register_all_tools():
    """
    Register all available tools.

    Called on application startup.
    """
    # Import tool modules to trigger registration
    from . import utilities  # noqa: F401
    from . import web  # noqa: F401
    from . import vault  # noqa: F401
    from . import knowledge_base  # noqa: F401
    from . import scratch  # noqa: F401
    from . import code_exec  # noqa: F401
    from . import agents  # noqa: F401
    from . import vectors  # noqa: F401
    from . import music  # noqa: F401
    from . import browser  # noqa: F401
    from . import cortex  # noqa: F401
    from . import suno_compiler  # noqa: F401
    from . import midi  # noqa: F401
    from . import jam  # noqa: F401
    from . import nursery  # noqa: F401

    # All 15 tiers loaded!

    logger.info(f"Tool registry initialized with {registry.tool_count} tools")


# Export commonly used items
__all__ = [
    "registry",
    "get_registry",
    "register_all_tools",
    "BaseTool",
    "SyncTool",
    "ToolSchema",
    "ToolResult",
    "ToolContext",
    "ToolCategory",
]

# Re-export from base
from .base import SyncTool  # noqa: E402, F401
