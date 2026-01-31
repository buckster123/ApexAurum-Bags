"""
Tier 11: Neo-Cortex Tools - Unified Memory System

Advanced memory operations with layers, visibility realms, and agent identity.
Builds on Tier 8 (Vectors) with Neo-Cortex unified memory architecture.

"The mind that remembers across lifetimes"
"""

import json
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from . import registry
from .base import BaseTool, ToolSchema, ToolResult, ToolContext, ToolCategory

logger = logging.getLogger(__name__)


# =============================================================================
# CORTEX REMEMBER - Store with layers and visibility
# =============================================================================

class CortexRememberTool(BaseTool):
    """Store memory with layer and visibility control."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="cortex_remember",
            description="""Store a memory in the Neo-Cortex unified memory system.

Unlike basic vector_store, this supports:
- **Layers**: sensory (hours), working (days), long_term (weeks), cortex (permanent)
- **Visibility**: private (agent only), village (all agents), bridge (specific agents)
- **Agent Identity**: Track which agent stored the memory
- **Attention Tracking**: Automatic access counting and decay

Use for:
- Personal observations that may fade (sensory)
- Active context for current conversation (working)
- Important facts to remember long-term (long_term)
- Crystallized insights to never forget (cortex)

Example: cortex_remember(content="User prefers dark mode", layer="long_term")""",
            category=ToolCategory.MEMORY,
            input_schema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The memory content to store",
                    },
                    "layer": {
                        "type": "string",
                        "enum": ["sensory", "working", "long_term", "cortex"],
                        "description": "Memory layer (default: working)",
                        "default": "working",
                    },
                    "visibility": {
                        "type": "string",
                        "enum": ["private", "village", "bridge"],
                        "description": "Who can see this memory (default: private)",
                        "default": "private",
                    },
                    "message_type": {
                        "type": "string",
                        "enum": ["fact", "dialogue", "observation", "question", "discovery", "task"],
                        "description": "Type of memory (default: observation)",
                        "default": "observation",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional tags for organization",
                    },
                    "related_agents": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Agents involved (for bridge visibility)",
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
        layer = params.get("layer", "working")
        visibility = params.get("visibility", "private")
        message_type = params.get("message_type", "observation")
        tags = params.get("tags", [])
        related_agents = params.get("related_agents", [])

        if not content:
            return ToolResult(success=False, error="Content is required")

        if len(content) > 50000:
            return ToolResult(success=False, error="Content exceeds 50KB limit")

        try:
            from app.services.embedding import get_embedding_service
            from app.database import async_session
            from uuid import uuid4
            from sqlalchemy import text

            # Generate embedding
            embed_service = get_embedding_service()
            embedding = await embed_service.embed(content)

            if embedding is None:
                return ToolResult(
                    success=False,
                    error="Embedding service not configured. Set OPENAI_API_KEY."
                )

            async with async_session() as db:
                user_uuid = UUID(context.user_id) if isinstance(context.user_id, str) else context.user_id
                vector_id = uuid4()

                # Map visibility to collection name
                collection_map = {
                    "private": "cortex_private",
                    "village": "cortex_village",
                    "bridge": "cortex_bridges",
                }
                collection = collection_map.get(visibility, "cortex_private")

                # Get agent ID from context or default
                agent_id = context.metadata.get("agent_id", "CLAUDE") if context.metadata else "CLAUDE"

                await db.execute(
                    text("""
                        INSERT INTO user_vectors (
                            id, user_id, collection, content, metadata,
                            layer, visibility, agent_id, message_type,
                            attention_weight, access_count,
                            responding_to, related_agents, tags,
                            embedding, created_at
                        ) VALUES (
                            :id, :user_id, :collection, :content, :metadata,
                            :layer, :visibility, :agent_id, :message_type,
                            :attention_weight, :access_count,
                            :responding_to, :related_agents, :tags,
                            :embedding, :created_at
                        )
                    """),
                    {
                        "id": vector_id,
                        "user_id": user_uuid,
                        "collection": collection,
                        "content": content,
                        "metadata": json.dumps({}),
                        "layer": layer,
                        "visibility": visibility,
                        "agent_id": agent_id,
                        "message_type": message_type,
                        "attention_weight": 1.0,
                        "access_count": 0,
                        "responding_to": json.dumps([]),
                        "related_agents": json.dumps(related_agents),
                        "tags": json.dumps(tags),
                        "embedding": f"[{','.join(str(x) for x in embedding)}]",
                        "created_at": datetime.utcnow(),
                    }
                )
                await db.commit()

                return ToolResult(
                    success=True,
                    result={
                        "id": str(vector_id),
                        "layer": layer,
                        "visibility": visibility,
                        "agent_id": agent_id,
                        "message_type": message_type,
                        "content_preview": content[:100] + ("..." if len(content) > 100 else ""),
                        "message": f"Memory stored in {layer} layer",
                    },
                )

        except Exception as e:
            logger.exception("Cortex remember error")
            return ToolResult(success=False, error=f"Failed to store: {str(e)}")


# =============================================================================
# CORTEX RECALL - Search with layer and visibility filters
# =============================================================================

class CortexRecallTool(BaseTool):
    """Search memory with layer and visibility awareness."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="cortex_recall",
            description="""Search the Neo-Cortex unified memory system.

Searches across memory layers with attention tracking.
Each recall boosts the memory's attention weight (more recalled = more important).

Filters:
- **layers**: Which layers to search (default: all)
- **visibility**: Search private, village, or all memories
- **min_attention**: Filter by attention weight (0.0-2.0)

Returns memories ranked by semantic similarity with layer and visibility info.

Example: cortex_recall(query="user preferences", layers=["long_term", "cortex"])""",
            category=ToolCategory.MEMORY,
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Semantic search query",
                    },
                    "layers": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["sensory", "working", "long_term", "cortex"],
                        },
                        "description": "Layers to search (default: all)",
                    },
                    "visibility": {
                        "type": "string",
                        "enum": ["private", "village", "all"],
                        "description": "Visibility filter (default: all)",
                        "default": "all",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default: 5)",
                        "default": 5,
                    },
                    "min_attention": {
                        "type": "number",
                        "description": "Minimum attention weight (default: 0.0)",
                        "default": 0.0,
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
        layers = params.get("layers")  # None means all
        visibility = params.get("visibility", "all")
        limit = min(params.get("limit", 5), 20)
        min_attention = params.get("min_attention", 0.0)

        if not query:
            return ToolResult(success=False, error="Query is required")

        try:
            from app.services.embedding import get_embedding_service
            from app.database import async_session
            from sqlalchemy import text

            # Generate query embedding
            embed_service = get_embedding_service()
            query_embedding = await embed_service.embed(query)

            if query_embedding is None:
                return ToolResult(success=False, error="Embedding service not configured")

            async with async_session() as db:
                user_uuid = UUID(context.user_id) if isinstance(context.user_id, str) else context.user_id
                embedding_str = f"[{','.join(str(x) for x in query_embedding)}]"

                # Build dynamic WHERE clause
                where_clauses = ["user_id = :user_id"]
                params_dict = {
                    "user_id": user_uuid,
                    "embedding": embedding_str,
                    "limit": limit,
                }

                if layers:
                    where_clauses.append("layer = ANY(:layers)")
                    params_dict["layers"] = layers

                if visibility != "all":
                    where_clauses.append("visibility = :visibility")
                    params_dict["visibility"] = visibility

                if min_attention > 0:
                    where_clauses.append("attention_weight >= :min_attention")
                    params_dict["min_attention"] = min_attention

                where_clauses.append("embedding IS NOT NULL")
                where_sql = " AND ".join(where_clauses)

                result = await db.execute(
                    text(f"""
                        SELECT
                            id, collection, content, layer, visibility, agent_id,
                            message_type, tags, attention_weight, access_count, created_at,
                            1 - (embedding <=> :embedding) as similarity
                        FROM user_vectors
                        WHERE {where_sql}
                        ORDER BY embedding <=> :embedding
                        LIMIT :limit
                    """),
                    params_dict
                )
                rows = result.fetchall()

                # Track access (async, non-blocking)
                if rows:
                    ids = [str(row.id) for row in rows]
                    await db.execute(
                        text("""
                            UPDATE user_vectors
                            SET access_count = access_count + 1,
                                last_accessed_at = :now,
                                attention_weight = LEAST(attention_weight + 0.1, 2.0)
                            WHERE id = ANY(:ids)
                        """),
                        {"ids": [UUID(id) for id in ids], "now": datetime.utcnow()}
                    )
                    await db.commit()

                results = []
                for row in rows:
                    tags = row.tags if isinstance(row.tags, list) else json.loads(row.tags or "[]")
                    results.append({
                        "id": str(row.id),
                        "content": row.content[:500] + ("..." if len(row.content) > 500 else ""),
                        "layer": row.layer,
                        "visibility": row.visibility,
                        "agent_id": row.agent_id,
                        "message_type": row.message_type,
                        "tags": tags,
                        "attention_weight": round(float(row.attention_weight), 2) if row.attention_weight is not None else 1.0,
                        "access_count": row.access_count,
                        "similarity": round(float(row.similarity), 4) if row.similarity is not None else 0.0,
                        "created_at": row.created_at.isoformat() if row.created_at else None,
                    })

                return ToolResult(
                    success=True,
                    result={
                        "query": query,
                        "layers_searched": layers or ["all"],
                        "visibility": visibility,
                        "count": len(results),
                        "results": results,
                    },
                )

        except Exception as e:
            logger.exception("Cortex recall error")
            return ToolResult(success=False, error=f"Search failed: {str(e)}")


# =============================================================================
# CORTEX VILLAGE - Post to shared knowledge square
# =============================================================================

class CortexVillageTool(BaseTool):
    """Post to the village square (shared agent memory)."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="cortex_village",
            description="""Post a message to the Village Square - shared memory visible to all agents.

The Village is where agents share:
- Discoveries and insights
- Questions for collective wisdom
- Cultural knowledge and traditions
- Dialogue between agents

Messages are stored in the 'village' visibility realm and can be searched by all agents.

Example: cortex_village(content="Discovered that user prefers concise responses", message_type="discovery")""",
            category=ToolCategory.MEMORY,
            input_schema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Message to post to the village",
                    },
                    "message_type": {
                        "type": "string",
                        "enum": ["fact", "dialogue", "observation", "question", "discovery", "cultural"],
                        "description": "Type of message (default: dialogue)",
                        "default": "dialogue",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional tags",
                    },
                },
                "required": ["content"],
            },
            requires_auth=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        # Delegate to cortex_remember with village visibility
        params["visibility"] = "village"
        params["layer"] = "working"
        if "message_type" not in params:
            params["message_type"] = "dialogue"

        remember_tool = CortexRememberTool()
        result = await remember_tool.execute(params, context)

        if result.success:
            result.result["message"] = "Posted to Village Square"

        return result


# =============================================================================
# CORTEX STATS - Memory system statistics
# =============================================================================

class CortexStatsTool(BaseTool):
    """Get Neo-Cortex memory statistics."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="cortex_stats",
            description="""Get statistics about the Neo-Cortex memory system.

Returns:
- Total memories across all layers
- Breakdown by layer (sensory, working, long_term, cortex)
- Breakdown by visibility (private, village, bridge)
- Top tags and attention distribution""",
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
            from sqlalchemy import text

            async with async_session() as db:
                user_uuid = UUID(context.user_id) if isinstance(context.user_id, str) else context.user_id

                # Get counts by layer
                layer_result = await db.execute(
                    text("""
                        SELECT layer, COUNT(*) as count
                        FROM user_vectors
                        WHERE user_id = :user_id
                        GROUP BY layer
                    """),
                    {"user_id": user_uuid}
                )
                layers = {row.layer or "unknown": row.count for row in layer_result.fetchall()}

                # Get counts by visibility
                vis_result = await db.execute(
                    text("""
                        SELECT visibility, COUNT(*) as count
                        FROM user_vectors
                        WHERE user_id = :user_id
                        GROUP BY visibility
                    """),
                    {"user_id": user_uuid}
                )
                visibility = {row.visibility or "unknown": row.count for row in vis_result.fetchall()}

                # Get total
                total = sum(layers.values())

                return ToolResult(
                    success=True,
                    result={
                        "total_memories": total,
                        "by_layer": {
                            "sensory": layers.get("sensory", 0),
                            "working": layers.get("working", 0),
                            "long_term": layers.get("long_term", 0),
                            "cortex": layers.get("cortex", 0),
                        },
                        "by_visibility": {
                            "private": visibility.get("private", 0),
                            "village": visibility.get("village", 0),
                            "bridge": visibility.get("bridge", 0),
                        },
                    },
                )

        except Exception as e:
            logger.exception("Cortex stats error")
            return ToolResult(success=False, error=f"Stats failed: {str(e)}")


# =============================================================================
# CORTEX EXPORT - Export memory core for transfer
# =============================================================================

class CortexExportTool(BaseTool):
    """Export memory core for transfer between systems."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="cortex_export",
            description="""Export a MemoryCore - portable snapshot of agent memories.

MemoryCores can be transferred between:
- Local (ChromaDB) and Cloud (pgvector) deployments
- Different users or accounts
- Backup and restore

The export includes all memories for the specified agent across all layers.
Embeddings are NOT included (regenerated on import for compatibility).

Returns JSON that can be saved to a file.

Example: cortex_export(agent_id="AZOTH")""",
            category=ToolCategory.MEMORY,
            input_schema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Export memories for this agent (default: all agents)",
                    },
                    "layers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Layers to export (default: all)",
                    },
                },
                "required": [],
            },
            requires_auth=True,
            requires_confirmation=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required")

        agent_id = params.get("agent_id")
        layers = params.get("layers")

        try:
            from app.database import async_session
            from sqlalchemy import text

            async with async_session() as db:
                user_uuid = UUID(context.user_id) if isinstance(context.user_id, str) else context.user_id

                where_clauses = ["user_id = :user_id"]
                params_dict = {"user_id": user_uuid}

                if agent_id:
                    where_clauses.append("agent_id = :agent_id")
                    params_dict["agent_id"] = agent_id

                if layers:
                    where_clauses.append("layer = ANY(:layers)")
                    params_dict["layers"] = layers

                where_sql = " AND ".join(where_clauses)

                result = await db.execute(
                    text(f"""
                        SELECT
                            id, content, layer, visibility, agent_id, message_type,
                            responding_to, conversation_thread, related_agents, tags,
                            attention_weight, access_count, created_at
                        FROM user_vectors
                        WHERE {where_sql}
                        ORDER BY created_at DESC
                    """),
                    params_dict
                )
                rows = result.fetchall()

                # Build MemoryCore format
                memories = []
                for row in rows:
                    memories.append({
                        "id": str(row.id),
                        "content": row.content,
                        "layer": row.layer,
                        "visibility": row.visibility,
                        "agent_id": row.agent_id,
                        "message_type": row.message_type,
                        "responding_to": row.responding_to if isinstance(row.responding_to, list) else json.loads(row.responding_to or "[]"),
                        "conversation_thread": row.conversation_thread,
                        "related_agents": row.related_agents if isinstance(row.related_agents, list) else json.loads(row.related_agents or "[]"),
                        "tags": row.tags if isinstance(row.tags, list) else json.loads(row.tags or "[]"),
                        "attention_weight": float(row.attention_weight) if row.attention_weight else 1.0,
                        "access_count": row.access_count or 0,
                        "created_at": row.created_at.isoformat() if row.created_at else None,
                    })

                memory_core = {
                    "format_version": "1.0",
                    "agent_id": agent_id or "ALL",
                    "exported_at": datetime.utcnow().isoformat(),
                    "collections": {
                        "cortex_memories": memories,
                    },
                    "metadata": {
                        "source_backend": "pgvector",
                        "embedding_dimension": 1536,
                        "total_memories": len(memories),
                    },
                }

                return ToolResult(
                    success=True,
                    result={
                        "memory_core": memory_core,
                        "total_exported": len(memories),
                        "message": f"Exported {len(memories)} memories",
                    },
                )

        except Exception as e:
            logger.exception("Cortex export error")
            return ToolResult(success=False, error=f"Export failed: {str(e)}")


# =============================================================================
# CORTEX IMPORT - Import memory core from transfer
# =============================================================================

class CortexImportTool(BaseTool):
    """Import memory core from another system."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="cortex_import",
            description="""Import a MemoryCore - restore or transfer agent memories.

Imports memories from a JSON MemoryCore format.
Embeddings are regenerated during import for compatibility.

Use to:
- Restore from backup
- Transfer memories from local to cloud
- Import another agent's knowledge

Example: cortex_import(memory_core={...})""",
            category=ToolCategory.MEMORY,
            input_schema={
                "type": "object",
                "properties": {
                    "memory_core": {
                        "type": "object",
                        "description": "MemoryCore JSON object to import",
                    },
                },
                "required": ["memory_core"],
            },
            requires_auth=True,
            requires_confirmation=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required")

        memory_core = params.get("memory_core")
        if not memory_core:
            return ToolResult(success=False, error="memory_core is required")

        if not isinstance(memory_core, dict):
            return ToolResult(success=False, error="memory_core must be a JSON object")

        try:
            from app.services.embedding import get_embedding_service
            from app.database import async_session
            from sqlalchemy import text
            from uuid import uuid4

            embed_service = get_embedding_service()
            if not embed_service.api_key:
                return ToolResult(success=False, error="Embedding service not configured")

            collections = memory_core.get("collections", {})
            imported_count = 0
            errors = []

            async with async_session() as db:
                user_uuid = UUID(context.user_id) if isinstance(context.user_id, str) else context.user_id

                for coll_name, memories in collections.items():
                    for memory in memories:
                        try:
                            content = memory.get("content", "")
                            if not content:
                                continue

                            # Generate embedding
                            embedding = await embed_service.embed(content)
                            if embedding is None:
                                errors.append(f"Failed to embed: {content[:50]}...")
                                continue

                            await db.execute(
                                text("""
                                    INSERT INTO user_vectors (
                                        id, user_id, collection, content, metadata,
                                        layer, visibility, agent_id, message_type,
                                        attention_weight, access_count,
                                        responding_to, related_agents, tags,
                                        embedding, created_at
                                    ) VALUES (
                                        :id, :user_id, :collection, :content, :metadata,
                                        :layer, :visibility, :agent_id, :message_type,
                                        :attention_weight, :access_count,
                                        :responding_to, :related_agents, :tags,
                                        :embedding, :created_at
                                    )
                                """),
                                {
                                    "id": uuid4(),  # New ID for imported memory
                                    "user_id": user_uuid,
                                    "collection": coll_name,
                                    "content": content,
                                    "metadata": json.dumps({}),
                                    "layer": memory.get("layer", "working"),
                                    "visibility": memory.get("visibility", "private"),
                                    "agent_id": memory.get("agent_id", "CLAUDE"),
                                    "message_type": memory.get("message_type", "observation"),
                                    "attention_weight": memory.get("attention_weight", 1.0),
                                    "access_count": memory.get("access_count", 0),
                                    "responding_to": json.dumps(memory.get("responding_to", [])),
                                    "related_agents": json.dumps(memory.get("related_agents", [])),
                                    "tags": json.dumps(memory.get("tags", [])),
                                    "embedding": f"[{','.join(str(x) for x in embedding)}]",
                                    "created_at": datetime.utcnow(),
                                }
                            )
                            imported_count += 1

                        except Exception as e:
                            errors.append(f"Error: {str(e)[:50]}")

                await db.commit()

            result = {
                "imported_count": imported_count,
                "source_agent": memory_core.get("agent_id", "unknown"),
                "source_backend": memory_core.get("metadata", {}).get("source_backend", "unknown"),
                "message": f"Imported {imported_count} memories",
            }

            if errors:
                result["errors"] = errors[:5]  # First 5 errors
                result["error_count"] = len(errors)

            return ToolResult(success=True, result=result)

        except Exception as e:
            logger.exception("Cortex import error")
            return ToolResult(success=False, error=f"Import failed: {str(e)}")


# =============================================================================
# REGISTER TOOLS
# =============================================================================

registry.register(CortexRememberTool())
registry.register(CortexRecallTool())
registry.register(CortexVillageTool())
registry.register(CortexStatsTool())
registry.register(CortexExportTool())
registry.register(CortexImportTool())
