"""
Tier 4: Knowledge Base Tools - The Knowing Hands

Semantic search over documentation and knowledge.
"Access the accumulated wisdom"

NOTE: These tools bridge to a knowledge base service.
In cloud deployment, this could be:
- Local MCP server (dev)
- ChromaDB with pgvector (production)
- External API endpoint

For now, we implement a simple keyword-based fallback
that can be enhanced with vector search later.
"""

import logging
import httpx
from typing import Optional

from . import registry
from .base import BaseTool, ToolSchema, ToolResult, ToolContext, ToolCategory


logger = logging.getLogger(__name__)

# MCP server endpoint (for local dev) or external KB API
KB_ENDPOINT = "http://localhost:8100"  # Default MCP server port
KB_TIMEOUT = 10


# =============================================================================
# KB SEARCH
# =============================================================================

class KBSearchTool(BaseTool):
    """Semantic search across the knowledge base."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="kb_search",
            description="""Search the knowledge base for relevant documentation.

The knowledge base contains guides and documentation about:
- Railway deployment
- Vue 3 / Pinia
- FastAPI
- Stripe payments
- MCP (Model Context Protocol)
- LangGraph
- ChromaDB
- And more...

Use natural language queries. Results are ranked by relevance.""",
            category=ToolCategory.MEMORY,
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query",
                    },
                    "topic": {
                        "type": "string",
                        "description": "Filter by topic (railway, vue3, fastapi, stripe, mcp, etc.)",
                    },
                    "n_results": {
                        "type": "integer",
                        "description": "Number of results to return (default: 5, max: 10)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        query = params.get("query", "")
        topic = params.get("topic")
        n_results = min(params.get("n_results", 5), 10)

        if not query:
            return ToolResult(success=False, error="Search query is required")

        try:
            # Try MCP server first
            async with httpx.AsyncClient(timeout=KB_TIMEOUT) as client:
                payload = {
                    "query": query,
                    "n_results": n_results,
                }
                if topic:
                    payload["topic"] = topic

                response = await client.post(
                    f"{KB_ENDPOINT}/kb/search",
                    json=payload,
                )

                if response.status_code == 200:
                    data = response.json()
                    return ToolResult(
                        success=True,
                        result={
                            "query": query,
                            "topic": topic,
                            "results": data.get("results", []),
                            "result_count": len(data.get("results", [])),
                        },
                    )

        except httpx.ConnectError:
            logger.debug("KB MCP server not available, using fallback")
        except Exception as e:
            logger.warning(f"KB search error: {e}")

        # Fallback: Return helpful message about available topics
        return ToolResult(
            success=True,
            result={
                "query": query,
                "topic": topic,
                "results": [],
                "result_count": 0,
                "note": "Knowledge base search is not configured. Available when MCP server is running.",
                "available_topics": [
                    "railway", "vue3", "fastapi", "stripe", "mcp",
                    "langgraph", "chromadb", "ollama", "wokwi"
                ],
            },
        )


# =============================================================================
# KB LOOKUP
# =============================================================================

class KBLookupTool(BaseTool):
    """Quick lookup for a specific term or concept."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="kb_lookup",
            description="""Quick lookup for a specific term or concept.

Returns the most relevant definition or explanation.
Good for quick facts about frameworks, tools, or concepts.""",
            category=ToolCategory.MEMORY,
            input_schema={
                "type": "object",
                "properties": {
                    "term": {
                        "type": "string",
                        "description": "Term or concept to look up",
                    },
                },
                "required": ["term"],
            },
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        term = params.get("term", "")

        if not term:
            return ToolResult(success=False, error="Term is required")

        try:
            async with httpx.AsyncClient(timeout=KB_TIMEOUT) as client:
                response = await client.post(
                    f"{KB_ENDPOINT}/kb/quick_lookup",
                    json={"term": term},
                )

                if response.status_code == 200:
                    data = response.json()
                    return ToolResult(
                        success=True,
                        result={
                            "term": term,
                            "definition": data.get("definition"),
                            "source": data.get("source"),
                        },
                    )

        except httpx.ConnectError:
            logger.debug("KB MCP server not available")
        except Exception as e:
            logger.warning(f"KB lookup error: {e}")

        # Fallback
        return ToolResult(
            success=True,
            result={
                "term": term,
                "definition": None,
                "note": "Knowledge base not configured. Term lookup unavailable.",
            },
        )


# =============================================================================
# KB TOPICS
# =============================================================================

class KBTopicsTool(BaseTool):
    """List available topics in the knowledge base."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="kb_topics",
            description="""List all available topics in the knowledge base.

Returns the list of documentation categories that can be searched.""",
            category=ToolCategory.MEMORY,
            input_schema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        try:
            async with httpx.AsyncClient(timeout=KB_TIMEOUT) as client:
                response = await client.get(f"{KB_ENDPOINT}/kb/topics")

                if response.status_code == 200:
                    data = response.json()
                    return ToolResult(
                        success=True,
                        result={
                            "topics": data.get("topics", []),
                            "count": len(data.get("topics", [])),
                        },
                    )

        except httpx.ConnectError:
            logger.debug("KB MCP server not available")
        except Exception as e:
            logger.warning(f"KB topics error: {e}")

        # Fallback with known topics
        known_topics = [
            {"name": "railway", "description": "Railway deployment platform"},
            {"name": "vue3", "description": "Vue 3 framework and Pinia"},
            {"name": "fastapi", "description": "FastAPI Python framework"},
            {"name": "stripe", "description": "Stripe payments integration"},
            {"name": "mcp", "description": "Model Context Protocol"},
            {"name": "langgraph", "description": "LangGraph agent framework"},
            {"name": "chromadb", "description": "ChromaDB vector database"},
            {"name": "ollama", "description": "Ollama local LLM runner"},
            {"name": "wokwi", "description": "Wokwi IoT simulator"},
        ]

        return ToolResult(
            success=True,
            result={
                "topics": known_topics,
                "count": len(known_topics),
                "note": "Showing known topics. Full list available when KB server is running.",
            },
        )


# =============================================================================
# KB ANSWER
# =============================================================================

class KBAnswerTool(BaseTool):
    """Get context to answer a question from the knowledge base."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="kb_answer",
            description="""Get relevant context to answer a question.

Searches the knowledge base and returns combined text from
multiple relevant sources. Use this when you need comprehensive
context to answer a user's question about supported topics.""",
            category=ToolCategory.MEMORY,
            input_schema={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The question to find context for",
                    },
                    "context_chunks": {
                        "type": "integer",
                        "description": "Number of context chunks to retrieve (default: 3)",
                        "default": 3,
                    },
                },
                "required": ["question"],
            },
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        question = params.get("question", "")
        context_chunks = min(params.get("context_chunks", 3), 5)

        if not question:
            return ToolResult(success=False, error="Question is required")

        try:
            async with httpx.AsyncClient(timeout=KB_TIMEOUT) as client:
                response = await client.post(
                    f"{KB_ENDPOINT}/kb/answer",
                    json={
                        "question": question,
                        "context_chunks": context_chunks,
                    },
                )

                if response.status_code == 200:
                    data = response.json()
                    return ToolResult(
                        success=True,
                        result={
                            "question": question,
                            "context": data.get("context"),
                            "sources": data.get("sources", []),
                        },
                    )

        except httpx.ConnectError:
            logger.debug("KB MCP server not available")
        except Exception as e:
            logger.warning(f"KB answer error: {e}")

        # Fallback
        return ToolResult(
            success=True,
            result={
                "question": question,
                "context": None,
                "sources": [],
                "note": "Knowledge base not configured. Use web_search as alternative.",
            },
        )


# =============================================================================
# REGISTER TOOLS
# =============================================================================

registry.register(KBSearchTool())
registry.register(KBLookupTool())
registry.register(KBTopicsTool())
registry.register(KBAnswerTool())
