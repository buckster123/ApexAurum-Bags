"""
Tier 6: Code Execution Tools - The Making Hands

Execute code safely in sandboxed environments.
"Create and execute to bring ideas to life"

Supports Python execution with restricted builtins.
Integrates with Cortex Diver's execution backend.
"""

import logging
import asyncio
import sys
import io
import traceback
from typing import Optional
from contextlib import redirect_stdout, redirect_stderr

from . import registry
from .base import BaseTool, ToolSchema, ToolResult, ToolContext, ToolCategory


logger = logging.getLogger(__name__)

# Execution limits
MAX_EXECUTION_TIME = 10  # seconds
MAX_OUTPUT_SIZE = 100 * 1024  # 100KB

# Safe builtins for Python execution
SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bin": bin,
    "bool": bool,
    "chr": chr,
    "dict": dict,
    "divmod": divmod,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "format": format,
    "frozenset": frozenset,
    "hex": hex,
    "int": int,
    "isinstance": isinstance,
    "issubclass": issubclass,
    "iter": iter,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "next": next,
    "oct": oct,
    "ord": ord,
    "pow": pow,
    "print": print,
    "range": range,
    "repr": repr,
    "reversed": reversed,
    "round": round,
    "set": set,
    "slice": slice,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "type": type,
    "zip": zip,
    # Math functions
    "__import__": lambda name, *args: __safe_import(name),
}

# Safe modules that can be imported
SAFE_MODULES = {
    "math", "random", "datetime", "json", "re",
    "itertools", "functools", "collections", "string",
    "decimal", "fractions", "statistics",
}


def __safe_import(name: str, *args):
    """Safe import that only allows whitelisted modules."""
    if name in SAFE_MODULES:
        return __import__(name)
    raise ImportError(f"Import of '{name}' is not allowed")


async def execute_python_code(code: str, timeout: int = MAX_EXECUTION_TIME) -> dict:
    """
    Execute Python code in a restricted environment.

    Returns dict with:
    - success: bool
    - output: stdout + stderr
    - result: last expression value (if any)
    - error: error message (if failed)
    """
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()

    # Create restricted globals
    restricted_globals = {
        "__builtins__": SAFE_BUILTINS,
        "__name__": "__main__",
    }

    # Add safe modules
    for module_name in SAFE_MODULES:
        try:
            restricted_globals[module_name] = __import__(module_name)
        except ImportError:
            pass

    result_value = None
    error_msg = None

    def run_code():
        nonlocal result_value, error_msg
        try:
            with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                # Try to evaluate as expression first
                try:
                    result_value = eval(code, restricted_globals)
                except SyntaxError:
                    # Not an expression, execute as statements
                    exec(code, restricted_globals)
                    result_value = restricted_globals.get("result")
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"

    try:
        # Run with timeout
        loop = asyncio.get_event_loop()
        await asyncio.wait_for(
            loop.run_in_executor(None, run_code),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        return {
            "success": False,
            "output": "",
            "result": None,
            "error": f"Execution timed out after {timeout}s",
        }

    output = stdout_buffer.getvalue() + stderr_buffer.getvalue()

    # Truncate output if too large
    if len(output) > MAX_OUTPUT_SIZE:
        output = output[:MAX_OUTPUT_SIZE] + f"\n\n[Output truncated at {MAX_OUTPUT_SIZE // 1024}KB]"

    if error_msg:
        return {
            "success": False,
            "output": output,
            "result": None,
            "error": error_msg[:5000],  # Limit error message
        }

    return {
        "success": True,
        "output": output,
        "result": repr(result_value) if result_value is not None else None,
    }


# =============================================================================
# CODE RUN
# =============================================================================

class CodeRunTool(BaseTool):
    """Execute Python code in a sandboxed environment."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="code_run",
            description="""Execute Python code in a safe sandboxed environment.

Use for:
- Running calculations and data processing
- Testing code snippets
- Generating outputs programmatically

Available modules: math, random, datetime, json, re, itertools,
functools, collections, string, decimal, fractions, statistics

Limits: 10 second timeout, 100KB output
Note: File I/O and network access are disabled for security.""",
            category=ToolCategory.AGENT,
            input_schema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to execute",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Execution timeout in seconds (max 10)",
                        "default": 5,
                    },
                },
                "required": ["code"],
            },
            requires_confirmation=True,  # Code execution should be confirmed
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        code = params.get("code", "")
        timeout = min(params.get("timeout", 5), MAX_EXECUTION_TIME)

        if not code:
            return ToolResult(success=False, error="Code is required")

        if len(code) > 50000:
            return ToolResult(success=False, error="Code exceeds 50KB limit")

        try:
            result = await execute_python_code(code, timeout)

            if result["success"]:
                return ToolResult(
                    success=True,
                    result={
                        "executed": True,
                        "output": result["output"],
                        "result": result["result"],
                    },
                )
            else:
                return ToolResult(
                    success=False,
                    error=result["error"],
                    result={
                        "output": result["output"],
                    },
                )

        except Exception as e:
            logger.exception("Code execution error")
            return ToolResult(success=False, error=f"Execution failed: {str(e)}")


# =============================================================================
# CODE EVAL
# =============================================================================

class CodeEvalTool(BaseTool):
    """Evaluate a Python expression and return the result."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="code_eval",
            description="""Evaluate a Python expression and return the result.

Simpler than code_run - for single expressions only.
Good for quick calculations, data transformations, or formatting.

Examples:
- "2 ** 10" -> 1024
- "[x*2 for x in range(5)]" -> [0, 2, 4, 6, 8]
- "math.sqrt(144)" -> 12.0""",
            category=ToolCategory.AGENT,
            input_schema={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Python expression to evaluate",
                    },
                },
                "required": ["expression"],
            },
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        expression = params.get("expression", "")

        if not expression:
            return ToolResult(success=False, error="Expression is required")

        if len(expression) > 10000:
            return ToolResult(success=False, error="Expression exceeds 10KB limit")

        # Create restricted environment
        restricted_globals = {
            "__builtins__": SAFE_BUILTINS,
        }

        # Add safe modules
        for module_name in SAFE_MODULES:
            try:
                restricted_globals[module_name] = __import__(module_name)
            except ImportError:
                pass

        try:
            result = eval(expression, restricted_globals)

            return ToolResult(
                success=True,
                result={
                    "expression": expression,
                    "result": result,
                    "type": type(result).__name__,
                },
            )

        except SyntaxError as e:
            return ToolResult(
                success=False,
                error=f"Syntax error: {str(e)}",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"{type(e).__name__}: {str(e)}",
            )


# =============================================================================
# REGISTER TOOLS
# =============================================================================

registry.register(CodeRunTool())
registry.register(CodeEvalTool())
