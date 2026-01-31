"""
Tier 1 Utility Tools - Zero Dependencies

Stateless tools that require no external services.
"The simple hands that do the simple work"
"""

import math
import random
import uuid
from datetime import datetime, timezone
from typing import Optional

from . import registry
from .base import SyncTool, ToolSchema, ToolResult, ToolContext, ToolCategory


# ═══════════════════════════════════════════════════════════════════════════════
# GET CURRENT TIME
# ═══════════════════════════════════════════════════════════════════════════════

class GetCurrentTimeTool(SyncTool):
    """Get the current date and time in various formats."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="get_current_time",
            description="Get the current date and time. Can return in different formats and timezones.",
            category=ToolCategory.UTILITY,
            input_schema={
                "type": "object",
                "properties": {
                    "format": {
                        "type": "string",
                        "description": "Output format: 'iso', 'human', 'unix', 'date', 'time'",
                        "enum": ["iso", "human", "unix", "date", "time"],
                        "default": "human",
                    },
                    "timezone": {
                        "type": "string",
                        "description": "Timezone name (e.g., 'UTC', 'US/Eastern'). Default is UTC.",
                        "default": "UTC",
                    },
                },
                "required": [],
            },
        )

    def execute_sync(self, params: dict, context: ToolContext) -> ToolResult:
        try:
            format_type = params.get("format", "human")
            tz_name = params.get("timezone", "UTC")

            # Get current time in UTC
            now = datetime.now(timezone.utc)

            # Try to convert to requested timezone
            try:
                import zoneinfo
                if tz_name != "UTC":
                    tz = zoneinfo.ZoneInfo(tz_name)
                    now = now.astimezone(tz)
            except Exception:
                # If zoneinfo fails, stay with UTC
                pass

            # Format output
            if format_type == "iso":
                result = now.isoformat()
            elif format_type == "unix":
                result = int(now.timestamp())
            elif format_type == "date":
                result = now.strftime("%Y-%m-%d")
            elif format_type == "time":
                result = now.strftime("%H:%M:%S")
            else:  # human
                result = now.strftime("%A, %B %d, %Y at %I:%M %p %Z")

            return ToolResult(
                success=True,
                result={
                    "formatted": result,
                    "timezone": tz_name,
                    "iso": now.isoformat(),
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# CALCULATOR
# ═══════════════════════════════════════════════════════════════════════════════

class CalculatorTool(SyncTool):
    """Evaluate mathematical expressions safely."""

    # Safe functions and constants for eval
    SAFE_MATH = {
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "sum": sum,
        "pow": pow,
        "sqrt": math.sqrt,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "asin": math.asin,
        "acos": math.acos,
        "atan": math.atan,
        "log": math.log,
        "log10": math.log10,
        "log2": math.log2,
        "exp": math.exp,
        "floor": math.floor,
        "ceil": math.ceil,
        "factorial": math.factorial,
        "pi": math.pi,
        "e": math.e,
        "tau": math.tau,
        "inf": math.inf,
    }

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="calculator",
            description="Evaluate mathematical expressions. Supports basic arithmetic (+, -, *, /, **, %), "
                       "functions (sqrt, sin, cos, tan, log, exp, floor, ceil, factorial), "
                       "and constants (pi, e, tau).",
            category=ToolCategory.UTILITY,
            input_schema={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Mathematical expression to evaluate (e.g., '2 + 2', 'sqrt(16)', 'sin(pi/2)')",
                    },
                },
                "required": ["expression"],
            },
        )

    def execute_sync(self, params: dict, context: ToolContext) -> ToolResult:
        expression = params.get("expression", "")

        if not expression:
            return ToolResult(success=False, error="No expression provided")

        # Security: Only allow safe characters
        allowed_chars = set("0123456789+-*/%().^ abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_,")
        if not all(c in allowed_chars for c in expression):
            return ToolResult(success=False, error="Expression contains invalid characters")

        # Replace ^ with ** for exponentiation
        expression = expression.replace("^", "**")

        try:
            # Evaluate with restricted globals
            result = eval(expression, {"__builtins__": {}}, self.SAFE_MATH)

            # Format result
            if isinstance(result, float):
                # Round to avoid floating point weirdness
                if result == int(result):
                    result = int(result)
                else:
                    result = round(result, 10)

            return ToolResult(
                success=True,
                result={
                    "expression": params.get("expression"),
                    "result": result,
                },
            )
        except ZeroDivisionError:
            return ToolResult(success=False, error="Division by zero")
        except Exception as e:
            return ToolResult(success=False, error=f"Invalid expression: {str(e)}")


# ═══════════════════════════════════════════════════════════════════════════════
# RANDOM NUMBER
# ═══════════════════════════════════════════════════════════════════════════════

class RandomNumberTool(SyncTool):
    """Generate random numbers."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="random_number",
            description="Generate a random number. Can generate integers in a range, floats, or pick from a list.",
            category=ToolCategory.UTILITY,
            input_schema={
                "type": "object",
                "properties": {
                    "min": {
                        "type": "number",
                        "description": "Minimum value (inclusive). Default: 1",
                        "default": 1,
                    },
                    "max": {
                        "type": "number",
                        "description": "Maximum value (inclusive for integers). Default: 100",
                        "default": 100,
                    },
                    "type": {
                        "type": "string",
                        "description": "Number type: 'integer' or 'float'",
                        "enum": ["integer", "float"],
                        "default": "integer",
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of random values to generate. Default: 1, Max: 100",
                        "default": 1,
                        "minimum": 1,
                        "maximum": 100,
                    },
                },
                "required": [],
            },
        )

    def execute_sync(self, params: dict, context: ToolContext) -> ToolResult:
        try:
            min_val = params.get("min", 1)
            max_val = params.get("max", 100)
            num_type = params.get("type", "integer")
            count = min(params.get("count", 1), 100)  # Cap at 100

            if min_val > max_val:
                return ToolResult(success=False, error="min cannot be greater than max")

            results = []
            for _ in range(count):
                if num_type == "float":
                    results.append(round(random.uniform(min_val, max_val), 6))
                else:
                    results.append(random.randint(int(min_val), int(max_val)))

            # Return single value if count=1, otherwise list
            output = results[0] if count == 1 else results

            return ToolResult(
                success=True,
                result={
                    "value": output,
                    "min": min_val,
                    "max": max_val,
                    "type": num_type,
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# COUNT WORDS
# ═══════════════════════════════════════════════════════════════════════════════

class CountWordsTool(SyncTool):
    """Analyze text and count words, characters, etc."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="count_words",
            description="Count words, characters, sentences, and paragraphs in text. "
                       "Useful for text analysis and meeting length requirements.",
            category=ToolCategory.UTILITY,
            input_schema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The text to analyze",
                    },
                },
                "required": ["text"],
            },
        )

    def execute_sync(self, params: dict, context: ToolContext) -> ToolResult:
        text = params.get("text", "")

        if not text:
            return ToolResult(
                success=True,
                result={
                    "characters": 0,
                    "characters_no_spaces": 0,
                    "words": 0,
                    "sentences": 0,
                    "paragraphs": 0,
                    "lines": 0,
                },
            )

        # Count various metrics
        characters = len(text)
        characters_no_spaces = len(text.replace(" ", "").replace("\n", "").replace("\t", ""))
        words = len(text.split())
        sentences = len([s for s in text.replace("!", ".").replace("?", ".").split(".") if s.strip()])
        paragraphs = len([p for p in text.split("\n\n") if p.strip()])
        lines = len(text.split("\n"))

        # Average word length
        avg_word_length = round(characters_no_spaces / max(words, 1), 1)

        return ToolResult(
            success=True,
            result={
                "characters": characters,
                "characters_no_spaces": characters_no_spaces,
                "words": words,
                "sentences": sentences,
                "paragraphs": paragraphs,
                "lines": lines,
                "average_word_length": avg_word_length,
            },
        )


# ═══════════════════════════════════════════════════════════════════════════════
# UUID GENERATE
# ═══════════════════════════════════════════════════════════════════════════════

class UUIDGenerateTool(SyncTool):
    """Generate unique identifiers."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="uuid_generate",
            description="Generate a universally unique identifier (UUID). "
                       "Useful for creating unique IDs for resources.",
            category=ToolCategory.UTILITY,
            input_schema={
                "type": "object",
                "properties": {
                    "version": {
                        "type": "integer",
                        "description": "UUID version: 4 (random) or 1 (time-based). Default: 4",
                        "enum": [1, 4],
                        "default": 4,
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of UUIDs to generate. Default: 1, Max: 10",
                        "default": 1,
                        "minimum": 1,
                        "maximum": 10,
                    },
                    "format": {
                        "type": "string",
                        "description": "Output format: 'standard' (with hyphens) or 'compact' (no hyphens)",
                        "enum": ["standard", "compact"],
                        "default": "standard",
                    },
                },
                "required": [],
            },
        )

    def execute_sync(self, params: dict, context: ToolContext) -> ToolResult:
        try:
            version = params.get("version", 4)
            count = min(params.get("count", 1), 10)  # Cap at 10
            fmt = params.get("format", "standard")

            results = []
            for _ in range(count):
                if version == 1:
                    new_uuid = uuid.uuid1()
                else:
                    new_uuid = uuid.uuid4()

                if fmt == "compact":
                    results.append(new_uuid.hex)
                else:
                    results.append(str(new_uuid))

            # Return single value if count=1, otherwise list
            output = results[0] if count == 1 else results

            return ToolResult(
                success=True,
                result={
                    "uuid": output,
                    "version": version,
                    "format": fmt,
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# JSON TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

class JsonFormatTool(SyncTool):
    """Format and validate JSON."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="json_format",
            description="Parse, validate, and pretty-print JSON. Can also extract specific paths.",
            category=ToolCategory.UTILITY,
            input_schema={
                "type": "object",
                "properties": {
                    "json_string": {
                        "type": "string",
                        "description": "The JSON string to parse and format",
                    },
                    "path": {
                        "type": "string",
                        "description": "Optional dot-notation path to extract (e.g., 'data.items[0].name')",
                    },
                    "indent": {
                        "type": "integer",
                        "description": "Indentation spaces for pretty-print. Default: 2",
                        "default": 2,
                    },
                },
                "required": ["json_string"],
            },
        )

    def execute_sync(self, params: dict, context: ToolContext) -> ToolResult:
        import json

        json_string = params.get("json_string", "")
        path = params.get("path")
        indent = params.get("indent", 2)

        try:
            data = json.loads(json_string)
        except json.JSONDecodeError as e:
            return ToolResult(
                success=False,
                error=f"Invalid JSON: {str(e)}",
            )

        # Extract path if specified
        if path:
            try:
                parts = path.replace("[", ".").replace("]", "").split(".")
                result = data
                for part in parts:
                    if part.isdigit():
                        result = result[int(part)]
                    else:
                        result = result[part]
                data = result
            except (KeyError, IndexError, TypeError) as e:
                return ToolResult(
                    success=False,
                    error=f"Path not found: {path} ({str(e)})",
                )

        return ToolResult(
            success=True,
            result={
                "formatted": json.dumps(data, indent=indent, default=str),
                "valid": True,
                "type": type(data).__name__,
            },
        )


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTER ALL TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

# Auto-register on module import
registry.register(GetCurrentTimeTool())
registry.register(CalculatorTool())
registry.register(RandomNumberTool())
registry.register(CountWordsTool())
registry.register(UUIDGenerateTool())
registry.register(JsonFormatTool())
