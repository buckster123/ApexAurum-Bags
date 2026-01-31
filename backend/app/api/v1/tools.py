"""
Tools API Endpoints

Expose tool registry and execution to the frontend.
"The interface between mind and hand"
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth.deps import get_current_user, get_current_user_optional
from app.models.user import User
from app.tools import registry, ToolCategory
from app.services.tool_executor import create_tool_executor

logger = logging.getLogger(__name__)
router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

class ToolInfo(BaseModel):
    """Basic tool information."""
    name: str
    description: str
    category: str
    requires_confirmation: bool
    requires_auth: bool


class ToolListResponse(BaseModel):
    """Response with list of tools."""
    tools: list[ToolInfo]
    count: int


class ToolSchemaResponse(BaseModel):
    """Full tool schema including input_schema."""
    name: str
    description: str
    category: str
    input_schema: dict
    requires_confirmation: bool
    requires_auth: bool


class ToolExecuteRequest(BaseModel):
    """Request to execute a tool."""
    params: dict = {}
    conversation_id: Optional[UUID] = None
    agent_id: Optional[str] = None


class ToolExecuteResponse(BaseModel):
    """Response from tool execution."""
    success: bool
    result: Optional[dict] = None
    error: Optional[str] = None
    execution_time_ms: float


class ClaudeToolsResponse(BaseModel):
    """Tools in Claude API format."""
    tools: list[dict]
    count: int


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("", response_model=ToolListResponse)
async def list_tools(
    category: Optional[str] = None,
):
    """
    List all available tools.

    Optional filtering by category.
    No authentication required for listing.
    """
    tools = registry.list_tools()

    # Filter by category if specified
    if category:
        tools = [t for t in tools if t["category"] == category]

    return ToolListResponse(
        tools=[ToolInfo(**t) for t in tools],
        count=len(tools),
    )


@router.get("/categories")
async def list_categories():
    """List all tool categories."""
    return {
        "categories": [c.value for c in ToolCategory],
    }


@router.get("/claude-format", response_model=ClaudeToolsResponse)
async def get_claude_tools(
    categories: Optional[str] = None,
):
    """
    Get tools in Claude API format.

    This is the format needed for the 'tools' parameter in Claude API calls.

    Args:
        categories: Comma-separated list of categories to include (e.g., "utility,web")
    """
    cat_list = None
    if categories:
        try:
            cat_list = [ToolCategory(c.strip()) for c in categories.split(",")]
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid category: {str(e)}",
            )

    tools = registry.get_claude_tools(cat_list)
    return ClaudeToolsResponse(tools=tools, count=len(tools))


@router.get("/{tool_name}", response_model=ToolSchemaResponse)
async def get_tool_schema(tool_name: str):
    """
    Get full schema for a specific tool.

    Includes the input_schema (JSON Schema) for the tool's parameters.
    """
    tool = registry.get_tool(tool_name)
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool not found: {tool_name}",
        )

    schema = tool.schema
    return ToolSchemaResponse(
        name=schema.name,
        description=schema.description,
        category=schema.category.value,
        input_schema=schema.input_schema,
        requires_confirmation=schema.requires_confirmation,
        requires_auth=schema.requires_auth,
    )


@router.post("/{tool_name}/execute", response_model=ToolExecuteResponse)
async def execute_tool(
    tool_name: str,
    request: ToolExecuteRequest,
    user: User = Depends(get_current_user_optional),
):
    """
    Execute a tool directly.

    This endpoint allows executing tools outside of a chat context.
    Useful for testing tools or building custom workflows.

    Authentication is optional but some tools may require it.
    """
    tool = registry.get_tool(tool_name)
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool not found: {tool_name}",
        )

    # Check if tool requires auth
    if tool.schema.requires_auth and not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This tool requires authentication",
        )

    # Create executor with context
    executor = create_tool_executor(
        user_id=user.id if user else None,
        conversation_id=request.conversation_id,
        agent_id=request.agent_id,
    )

    # Execute
    result = await executor.execute(tool_name, request.params)

    return ToolExecuteResponse(
        success=result.success,
        result=result.result if result.success else None,
        error=result.error if not result.success else None,
        execution_time_ms=result.execution_time_ms,
    )


@router.post("/batch/execute")
async def execute_batch(
    tool_calls: list[dict],
    stop_on_error: bool = False,
    user: User = Depends(get_current_user_optional),
):
    """
    Execute multiple tools in sequence.

    Body should be a list of objects with 'name' and 'params' keys.

    Args:
        tool_calls: List of {name: str, params: dict}
        stop_on_error: Stop execution on first error

    Returns:
        List of tool results
    """
    executor = create_tool_executor(
        user_id=user.id if user else None,
    )

    results = []
    for call in tool_calls:
        tool_name = call.get("name")
        params = call.get("params", {})

        result = await executor.execute(tool_name, params)
        results.append(result)

        if stop_on_error and not result.success:
            break

    return {
        "results": [
            {
                "success": r.success,
                "result": r.result if r.success else None,
                "error": r.error if not r.success else None,
                "execution_time_ms": r.execution_time_ms,
            }
            for r in results
        ],
        "count": len(results),
        "all_succeeded": all(r.success for r in results),
    }
