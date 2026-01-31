"""
Tool Base Classes and Schemas

The foundation of ApexAurum's tool system.
"Hands for the mind"
"""

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ToolCategory(str, Enum):
    """Tool categories for organization and filtering."""
    UTILITY = "utility"
    WEB = "web"
    MEMORY = "memory"
    FILES = "files"
    AGENT = "agent"
    MUSIC = "music"
    BROWSER = "browser"
    CREATIVE = "creative"  # Suno compiler, prompt engineering
    NURSERY = "nursery"  # Model training studio


class ToolResult(BaseModel):
    """Result of a tool execution."""
    success: bool
    result: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0
    metadata: dict = Field(default_factory=dict)

    def to_claude_format(self) -> dict:
        """Format result for Claude's tool_result content block."""
        if self.success:
            # Convert result to string for Claude
            if isinstance(self.result, (dict, list)):
                import json
                content = json.dumps(self.result, indent=2, default=str)
            else:
                content = str(self.result)
            return {
                "type": "tool_result",
                "content": content,
                "is_error": False,
            }
        else:
            return {
                "type": "tool_result",
                "content": f"Error: {self.error}",
                "is_error": True,
            }


class ToolContext(BaseModel):
    """Context passed to tool execution."""
    user_id: Optional[UUID] = None
    conversation_id: Optional[UUID] = None
    agent_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True


class ToolSchema(BaseModel):
    """Schema describing a tool for Claude API."""
    name: str
    description: str
    input_schema: dict  # JSON Schema for parameters
    category: ToolCategory = ToolCategory.UTILITY
    requires_confirmation: bool = False
    requires_auth: bool = False

    def to_claude_format(self) -> dict:
        """Format for Claude's tools parameter."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class BaseTool(ABC):
    """
    Abstract base class for all ApexAurum tools.

    Each tool must implement:
    - schema: The tool's schema (name, description, input_schema)
    - execute(): The actual execution logic
    """

    @property
    @abstractmethod
    def schema(self) -> ToolSchema:
        """Return the tool's schema."""
        pass

    @abstractmethod
    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        """
        Execute the tool with given parameters.

        Args:
            params: The parameters matching input_schema
            context: Execution context (user, conversation, etc.)

        Returns:
            ToolResult with success/failure and result/error
        """
        pass

    @property
    def name(self) -> str:
        """Shortcut to get tool name."""
        return self.schema.name

    @property
    def category(self) -> ToolCategory:
        """Shortcut to get tool category."""
        return self.schema.category

    def validate_params(self, params: dict) -> tuple[bool, Optional[str]]:
        """
        Basic parameter validation.

        Returns (is_valid, error_message)
        """
        # Check required fields from schema
        required = self.schema.input_schema.get("required", [])
        for field in required:
            if field not in params:
                return False, f"Missing required parameter: {field}"
        return True, None


class SyncTool(BaseTool):
    """
    Base class for synchronous tools.

    Use this for simple tools that don't need async I/O.
    Implement execute_sync() instead of execute().
    """

    @abstractmethod
    def execute_sync(self, params: dict, context: ToolContext) -> ToolResult:
        """Synchronous execution."""
        pass

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        """Wrap sync execution in async."""
        return self.execute_sync(params, context)
