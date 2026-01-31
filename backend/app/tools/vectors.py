"""
Tier 8: Vector Tools - The Remembering Deep

Semantic memory using pgvector for similarity search.
"The mind that remembers everything"

Enables:
- Store memories with semantic embeddings
- Search by meaning, not just keywords
- Build RAG-style retrieval
"""

import logging
import json
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from . import registry
from .base import BaseTool, ToolSchema, ToolResult, ToolContext, ToolCategory


logger = logging.getLogger(__name__)


# =============================================================================
# VECTOR STORE
# =============================================================================

class VectorStoreTool(BaseTool):
    """Store text with semantic embedding."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="vector_store",
            description="""Store text in the user's semantic memory.

Use to:
- Remember important facts, preferences, or context
- Store information for later retrieval
- Build a knowledge base the agent can search

The text is embedded and stored for semantic search.
Add metadata tags for better organization.""",
            category=ToolCategory.MEMORY,
            input_schema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Text content to store and remember",
                    },
                    "collection": {
                        "type": "string",
                        "description": "Collection name (default: 'default')",
                        "default": "default",
                    },
                    "metadata": {
                        "type": "object",
                        "description": "Optional metadata (tags, source, etc.)",
                    },
                },
                "required": ["content"],
            },
            requires_auth=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required")

        content = params.get("content", "").strip()
        collection = params.get("collection", "default")[:100]
        metadata = params.get("metadata", {})

        if not content:
            return ToolResult(success=False, error="Content is required")

        if len(content) > 50000:  # 50KB limit
            return ToolResult(success=False, error="Content exceeds 50KB limit")

        try:
            from app.services.embedding import get_embedding_service
            from app.database import async_session
            from uuid import uuid4

            # Generate embedding
            embed_service = get_embedding_service()
            embedding = await embed_service.embed(content)

            if embedding is None:
                return ToolResult(
                    success=False,
                    error="Embedding service not configured. Set OPENAI_API_KEY in environment."
                )

            async with async_session() as db:
                user_uuid = UUID(context.user_id) if isinstance(context.user_id, str) else context.user_id
                vector_id = uuid4()

                # Insert with raw SQL for pgvector
                await db.execute(
                    text("""
                        INSERT INTO user_vectors (id, user_id, collection, content, metadata, embedding)
                        VALUES (:id, :user_id, :collection, :content, :metadata, :embedding)
                    """),
                    {
                        "id": vector_id,
                        "user_id": user_uuid,
                        "collection": collection,
                        "content": content,
                        "metadata": json.dumps(metadata),
                        "embedding": f"[{','.join(str(x) for x in embedding)}]",
                    }
                )
                await db.commit()

                return ToolResult(
                    success=True,
                    result={
                        "id": str(vector_id),
                        "collection": collection,
                        "content_preview": content[:100] + ("..." if len(content) > 100 else ""),
                        "metadata": metadata,
                        "message": "Memory stored successfully",
                    },
                )

        except Exception as e:
            logger.exception("Vector store error")
            return ToolResult(success=False, error=f"Failed to store: {str(e)}")


# =============================================================================
# VECTOR SEARCH
# =============================================================================

class VectorSearchTool(BaseTool):
    """Search vectors by semantic similarity."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="vector_search",
            description="""Search the user's semantic memory by meaning.

Use to:
- Find related memories or information
- Recall context about a topic
- Answer questions using stored knowledge

Returns the most similar items ranked by relevance.""",
            category=ToolCategory.MEMORY,
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (semantic)",
                    },
                    "collection": {
                        "type": "string",
                        "description": "Collection to search (omit for all)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default: 5)",
                        "default": 5,
                    },
                    "min_similarity": {
                        "type": "number",
                        "description": "Minimum similarity score 0-1 (default: 0.5)",
                        "default": 0.5,
                    },
                },
                "required": ["query"],
            },
            requires_auth=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required")

        query = params.get("query", "").strip()
        collection = params.get("collection")
        limit = min(params.get("limit", 5), 20)
        min_similarity = max(0, min(1, params.get("min_similarity", 0.5)))

        if not query:
            return ToolResult(success=False, error="Query is required")

        try:
            from app.services.embedding import get_embedding_service
            from app.database import async_session

            # Generate query embedding
            embed_service = get_embedding_service()
            query_embedding = await embed_service.embed(query)

            if query_embedding is None:
                return ToolResult(
                    success=False,
                    error="Embedding service not configured"
                )

            async with async_session() as db:
                user_uuid = UUID(context.user_id) if isinstance(context.user_id, str) else context.user_id
                embedding_str = f"[{','.join(str(x) for x in query_embedding)}]"

                # Build query with optional collection filter
                if collection:
                    sql = text("""
                        SELECT id, collection, content, metadata, created_at,
                               1 - (embedding <=> :embedding) as similarity
                        FROM user_vectors
                        WHERE user_id = :user_id
                          AND collection = :collection
                          AND 1 - (embedding <=> :embedding) >= :min_sim
                        ORDER BY embedding <=> :embedding
                        LIMIT :limit
                    """)
                    params_dict = {
                        "user_id": user_uuid,
                        "collection": collection,
                        "embedding": embedding_str,
                        "min_sim": min_similarity,
                        "limit": limit,
                    }
                else:
                    sql = text("""
                        SELECT id, collection, content, metadata, created_at,
                               1 - (embedding <=> :embedding) as similarity
                        FROM user_vectors
                        WHERE user_id = :user_id
                          AND 1 - (embedding <=> :embedding) >= :min_sim
                        ORDER BY embedding <=> :embedding
                        LIMIT :limit
                    """)
                    params_dict = {
                        "user_id": user_uuid,
                        "embedding": embedding_str,
                        "min_sim": min_similarity,
                        "limit": limit,
                    }

                result = await db.execute(sql, params_dict)
                rows = result.fetchall()

                results = []
                for row in rows:
                    results.append({
                        "id": str(row.id),
                        "collection": row.collection,
                        "content": row.content[:500] + ("..." if len(row.content) > 500 else ""),
                        "metadata": row.metadata if isinstance(row.metadata, dict) else json.loads(row.metadata or "{}"),
                        "similarity": round(float(row.similarity), 4),
                        "created_at": row.created_at.isoformat() if row.created_at else None,
                    })

                return ToolResult(
                    success=True,
                    result={
                        "query": query,
                        "collection": collection,
                        "count": len(results),
                        "results": results,
                    },
                )

        except Exception as e:
            logger.exception("Vector search error")
            return ToolResult(success=False, error=f"Search failed: {str(e)}")


# =============================================================================
# VECTOR DELETE
# =============================================================================

class VectorDeleteTool(BaseTool):
    """Delete a vector by ID."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="vector_delete",
            description="""Delete a memory from the user's semantic storage.

Use to:
- Remove outdated or incorrect information
- Clear specific memories
- Clean up collections""",
            category=ToolCategory.MEMORY,
            input_schema={
                "type": "object",
                "properties": {
                    "vector_id": {
                        "type": "string",
                        "description": "Vector UUID to delete",
                    },
                },
                "required": ["vector_id"],
            },
            requires_auth=True,
            requires_confirmation=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required")

        vector_id = params.get("vector_id", "")

        if not vector_id:
            return ToolResult(success=False, error="Vector ID is required")

        try:
            from app.database import async_session

            async with async_session() as db:
                user_uuid = UUID(context.user_id) if isinstance(context.user_id, str) else context.user_id
                vector_uuid = UUID(vector_id)

                result = await db.execute(
                    text("""
                        DELETE FROM user_vectors
                        WHERE id = :id AND user_id = :user_id
                        RETURNING id
                    """),
                    {"id": vector_uuid, "user_id": user_uuid}
                )
                deleted = result.fetchone()
                await db.commit()

                if deleted:
                    return ToolResult(
                        success=True,
                        result={"deleted": str(vector_id), "message": "Memory deleted"},
                    )
                else:
                    return ToolResult(success=False, error="Vector not found")

        except Exception as e:
            logger.exception("Vector delete error")
            return ToolResult(success=False, error=f"Delete failed: {str(e)}")


# =============================================================================
# VECTOR LIST
# =============================================================================

class VectorListTool(BaseTool):
    """List vectors in a collection."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="vector_list",
            description="""List memories in a collection.

Use to:
- Browse stored memories
- See what's in a collection
- Get IDs for deletion""",
            category=ToolCategory.MEMORY,
            input_schema={
                "type": "object",
                "properties": {
                    "collection": {
                        "type": "string",
                        "description": "Collection name (omit for all)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default: 20)",
                        "default": 20,
                    },
                },
                "required": [],
            },
            requires_auth=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required")

        collection = params.get("collection")
        limit = min(params.get("limit", 20), 100)

        try:
            from app.database import async_session

            async with async_session() as db:
                user_uuid = UUID(context.user_id) if isinstance(context.user_id, str) else context.user_id

                if collection:
                    sql = text("""
                        SELECT id, collection, content, metadata, created_at
                        FROM user_vectors
                        WHERE user_id = :user_id AND collection = :collection
                        ORDER BY created_at DESC
                        LIMIT :limit
                    """)
                    params_dict = {"user_id": user_uuid, "collection": collection, "limit": limit}
                else:
                    sql = text("""
                        SELECT id, collection, content, metadata, created_at
                        FROM user_vectors
                        WHERE user_id = :user_id
                        ORDER BY created_at DESC
                        LIMIT :limit
                    """)
                    params_dict = {"user_id": user_uuid, "limit": limit}

                result = await db.execute(sql, params_dict)
                rows = result.fetchall()

                items = []
                for row in rows:
                    items.append({
                        "id": str(row.id),
                        "collection": row.collection,
                        "content_preview": row.content[:100] + ("..." if len(row.content) > 100 else ""),
                        "metadata": row.metadata if isinstance(row.metadata, dict) else json.loads(row.metadata or "{}"),
                        "created_at": row.created_at.isoformat() if row.created_at else None,
                    })

                return ToolResult(
                    success=True,
                    result={
                        "collection": collection,
                        "count": len(items),
                        "items": items,
                    },
                )

        except Exception as e:
            logger.exception("Vector list error")
            return ToolResult(success=False, error=f"List failed: {str(e)}")


# =============================================================================
# VECTOR STATS
# =============================================================================

class VectorStatsTool(BaseTool):
    """Get vector storage statistics."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="vector_stats",
            description="""Get statistics about the user's semantic memory.

Returns:
- Total vectors stored
- Collections and their sizes
- Memory usage""",
            category=ToolCategory.MEMORY,
            input_schema={
                "type": "object",
                "properties": {},
                "required": [],
            },
            requires_auth=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required")

        try:
            from app.database import async_session

            async with async_session() as db:
                user_uuid = UUID(context.user_id) if isinstance(context.user_id, str) else context.user_id

                # Get total count and collections
                result = await db.execute(
                    text("""
                        SELECT collection, COUNT(*) as count
                        FROM user_vectors
                        WHERE user_id = :user_id
                        GROUP BY collection
                        ORDER BY count DESC
                    """),
                    {"user_id": user_uuid}
                )
                collections = result.fetchall()

                total = sum(row.count for row in collections)
                collections_info = [
                    {"name": row.collection, "count": row.count}
                    for row in collections
                ]

                return ToolResult(
                    success=True,
                    result={
                        "total_vectors": total,
                        "collection_count": len(collections_info),
                        "collections": collections_info,
                    },
                )

        except Exception as e:
            logger.exception("Vector stats error")
            return ToolResult(success=False, error=f"Stats failed: {str(e)}")


# =============================================================================
# REGISTER TOOLS
# =============================================================================

registry.register(VectorStoreTool())
registry.register(VectorSearchTool())
registry.register(VectorDeleteTool())
registry.register(VectorListTool())
registry.register(VectorStatsTool())
