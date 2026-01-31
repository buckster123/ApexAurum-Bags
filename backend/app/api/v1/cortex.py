"""
Neo-Cortex Dashboard API

Endpoints for the 3D Neural Space memory visualization dashboard.
"""

import json
import logging
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.auth.deps import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cortex", tags=["Neo-Cortex"])


# =============================================================================
# Schemas
# =============================================================================

class MemoryNode(BaseModel):
    """Memory for visualization."""
    id: str
    content: str
    agent_id: Optional[str] = "CLAUDE"
    visibility: str = "private"
    layer: str = "working"
    message_type: str = "observation"
    attention_weight: float = 1.0
    access_count: int = 0
    tags: List[str] = []
    responding_to: List[str] = []
    related_agents: List[str] = []
    conversation_thread: Optional[str] = None
    created_at: Optional[str] = None
    last_accessed_at: Optional[str] = None


class GraphEdge(BaseModel):
    """Relationship edge for visualization."""
    source: str
    target: str
    type: str  # "responding_to" | "thread" | "related_agent"


class GraphData(BaseModel):
    """Graph data for 3D visualization."""
    nodes: List[MemoryNode]
    edges: List[GraphEdge]


class CortexStats(BaseModel):
    """Memory statistics."""
    total: int
    by_layer: dict
    by_visibility: dict
    by_agent: dict
    by_message_type: dict


class SearchRequest(BaseModel):
    """Search request body."""
    query: str = Field(..., max_length=500)
    layers: Optional[List[str]] = None
    visibility: Optional[str] = None
    agent_id: Optional[str] = None
    limit: int = 50


class LayerUpdateRequest(BaseModel):
    """Request to change memory layer."""
    layer: str  # sensory | working | long_term | cortex


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/diagnostic")
async def diagnostic(
    db=Depends(get_db),
):
    """
    Diagnostic endpoint to check pgvector and Neural system status.
    No auth required - useful for troubleshooting.
    """
    from app.config import get_settings
    settings = get_settings()

    # Determine embedding availability based on provider
    if settings.embedding_provider == "local":
        embedding_available = True  # Local embeddings always available (no API key needed)
    elif settings.embedding_provider == "openai":
        embedding_available = bool(settings.openai_api_key)
    elif settings.embedding_provider == "voyage":
        embedding_available = bool(settings.voyage_api_key)
    else:
        embedding_available = False

    result = {
        "pgvector_extension": False,
        "user_vectors_table": False,
        "neo_cortex_columns": False,
        "vector_column": False,
        "vector_dimensions": None,
        "total_vectors": 0,
        "vectors_with_embeddings": 0,
        "embedding_provider": settings.embedding_provider,
        "embedding_model": settings.embedding_model,
        "embedding_dimensions": settings.embedding_dimensions,
        "embedding_available": embedding_available,
        "errors": [],
        "notes": [],
    }

    try:
        # Check if pgvector extension exists
        ext_check = await db.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
        )
        result["pgvector_extension"] = ext_check.scalar()

        if not result["pgvector_extension"]:
            result["notes"].append("pgvector extension not installed - try: CREATE EXTENSION vector;")

        # Check if user_vectors table exists
        table_check = await db.execute(
            text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'user_vectors')")
        )
        result["user_vectors_table"] = table_check.scalar()

        if result["user_vectors_table"]:
            # Check for vector column
            col_check = await db.execute(
                text("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'user_vectors' AND column_name = 'embedding'
                    )
                """)
            )
            result["vector_column"] = col_check.scalar()

            # Check actual vector dimension in database
            if result["vector_column"]:
                try:
                    dim_check = await db.execute(
                        text("""
                            SELECT atttypmod - 4 as dim
                            FROM pg_attribute
                            WHERE attrelid = 'user_vectors'::regclass
                              AND attname = 'embedding'
                        """)
                    )
                    db_dim = dim_check.scalar()
                    result["vector_dimensions"] = db_dim
                    if db_dim != settings.embedding_dimensions:
                        result["notes"].append(
                            f"DB vector dim ({db_dim}) != config ({settings.embedding_dimensions}). "
                            "Column will be recreated on next startup."
                        )
                except Exception:
                    pass  # Ignore if can't get dimension

            # Check for neo-cortex columns
            layer_check = await db.execute(
                text("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'user_vectors' AND column_name = 'layer'
                    )
                """)
            )
            result["neo_cortex_columns"] = layer_check.scalar()

            # Count vectors
            count_check = await db.execute(text("SELECT COUNT(*) FROM user_vectors"))
            result["total_vectors"] = count_check.scalar() or 0

            # Count vectors with embeddings
            embed_check = await db.execute(text("SELECT COUNT(*) FROM user_vectors WHERE embedding IS NOT NULL"))
            result["vectors_with_embeddings"] = embed_check.scalar() or 0

        else:
            result["notes"].append("user_vectors table not found - backend will create on next startup if pgvector is enabled")

    except Exception as e:
        result["errors"].append(str(e))

    # Overall status
    result["ready"] = (
        result["pgvector_extension"] and
        result["user_vectors_table"] and
        result["neo_cortex_columns"]
    )

    # Add note about embeddings if not available
    if not result["embedding_available"]:
        result["notes"].append(f"No {settings.embedding_provider.upper()}_API_KEY - memories will store without embeddings (semantic search disabled)")

    return result


@router.post("/setup")
async def setup_pgvector(
    db=Depends(get_db),
):
    """
    Attempt to set up pgvector and create tables.
    Run this after enabling pgvector extension in Railway.
    """
    results = {
        "extension": {"success": False, "message": ""},
        "table": {"success": False, "message": ""},
        "columns": {"success": False, "message": ""},
    }

    try:
        # Try to create extension
        await db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await db.commit()
        results["extension"] = {"success": True, "message": "pgvector extension enabled"}
    except Exception as e:
        results["extension"] = {"success": False, "message": str(e)}

    try:
        # Create user_vectors table with configured embedding dimension
        settings = get_settings()
        embed_dim = settings.embedding_dimensions
        await db.execute(text(f"""
            CREATE TABLE IF NOT EXISTS user_vectors (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                collection VARCHAR(100) DEFAULT 'default',
                content TEXT NOT NULL,
                metadata JSONB DEFAULT '{{}}'::jsonb,
                embedding vector({embed_dim}),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """))
        await db.commit()
        results["table"] = {"success": True, "message": f"user_vectors table created (embed_dim={embed_dim})"}
    except Exception as e:
        results["table"] = {"success": False, "message": str(e)}

    try:
        # Add Neo-Cortex columns
        columns_sql = """
            ALTER TABLE user_vectors
            ADD COLUMN IF NOT EXISTS layer VARCHAR(20) DEFAULT 'working' NOT NULL,
            ADD COLUMN IF NOT EXISTS visibility VARCHAR(20) DEFAULT 'private' NOT NULL,
            ADD COLUMN IF NOT EXISTS agent_id VARCHAR(50),
            ADD COLUMN IF NOT EXISTS message_type VARCHAR(50) DEFAULT 'observation' NOT NULL,
            ADD COLUMN IF NOT EXISTS attention_weight FLOAT DEFAULT 1.0 NOT NULL,
            ADD COLUMN IF NOT EXISTS access_count INTEGER DEFAULT 0 NOT NULL,
            ADD COLUMN IF NOT EXISTS last_accessed_at TIMESTAMP WITH TIME ZONE,
            ADD COLUMN IF NOT EXISTS responding_to JSONB DEFAULT '[]'::jsonb NOT NULL,
            ADD COLUMN IF NOT EXISTS conversation_thread VARCHAR(100),
            ADD COLUMN IF NOT EXISTS related_agents JSONB DEFAULT '[]'::jsonb NOT NULL,
            ADD COLUMN IF NOT EXISTS tags JSONB DEFAULT '[]'::jsonb NOT NULL
        """
        await db.execute(text(columns_sql))
        await db.commit()
        results["columns"] = {"success": True, "message": "Neo-Cortex columns added"}
    except Exception as e:
        results["columns"] = {"success": False, "message": str(e)}

    # Create indexes
    try:
        await db.execute(text("CREATE INDEX IF NOT EXISTS idx_vectors_user ON user_vectors(user_id)"))
        await db.execute(text("CREATE INDEX IF NOT EXISTS idx_vectors_layer ON user_vectors(layer)"))
        await db.execute(text("CREATE INDEX IF NOT EXISTS idx_vectors_visibility ON user_vectors(visibility)"))
        await db.commit()
    except Exception:
        pass  # Indexes are optional

    return results


@router.get("/memories", response_model=List[MemoryNode])
async def list_memories(
    layer: Optional[str] = Query(None, description="Filter by layer"),
    visibility: Optional[str] = Query(None, description="Filter by visibility"),
    agent_id: Optional[str] = Query(None, description="Filter by agent"),
    message_type: Optional[str] = Query(None, description="Filter by message type"),
    limit: int = Query(100, le=500, description="Max results"),
    offset: int = Query(0, description="Offset for pagination"),
    user: User = Depends(get_current_user),
    db=Depends(get_db),
) -> List[MemoryNode]:
    """
    List memories with optional filters.
    Returns memories for the 3D visualization.
    """
    try:
        # Check if user_vectors table exists
        check_result = await db.execute(
            text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'user_vectors')")
        )
        table_exists = check_result.scalar()

        if not table_exists:
            logger.info("user_vectors table not found - returning empty list")
            return []

        # Build dynamic query
        where_clauses = ["user_id = :user_id"]
        params = {"user_id": user.id, "limit": limit, "offset": offset}

        if layer:
            where_clauses.append("layer = :layer")
            params["layer"] = layer

        if visibility:
            where_clauses.append("visibility = :visibility")
            params["visibility"] = visibility

        if agent_id:
            where_clauses.append("agent_id = :agent_id")
            params["agent_id"] = agent_id

        if message_type:
            where_clauses.append("message_type = :message_type")
            params["message_type"] = message_type

        where_sql = " AND ".join(where_clauses)

        result = await db.execute(
            text(f"""
                SELECT
                    id, content, agent_id, visibility, layer, message_type,
                    attention_weight, access_count, tags, responding_to,
                    related_agents, conversation_thread, created_at, last_accessed_at
                FROM user_vectors
                WHERE {where_sql}
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """),
            params
        )
        rows = result.fetchall()

        return [_row_to_node(row) for row in rows]
    except Exception as e:
        logger.error(f"Cortex memories error: {e}")
        return []


@router.get("/memories/{memory_id}", response_model=MemoryNode)
async def get_memory(
    memory_id: str,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
) -> MemoryNode:
    """Get a single memory by ID."""
    result = await db.execute(
        text("""
            SELECT
                id, content, agent_id, visibility, layer, message_type,
                attention_weight, access_count, tags, responding_to,
                related_agents, conversation_thread, created_at, last_accessed_at
            FROM user_vectors
            WHERE id = :id AND user_id = :user_id
        """),
        {"id": UUID(memory_id), "user_id": user.id}
    )
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Memory not found")

    return _row_to_node(row)


@router.get("/graph", response_model=GraphData)
async def get_graph_data(
    layer: Optional[str] = Query(None),
    visibility: Optional[str] = Query(None),
    limit: int = Query(200, le=1000),
    user: User = Depends(get_current_user),
    db=Depends(get_db),
) -> GraphData:
    """
    Get graph data optimized for 3D visualization.
    Returns nodes and edges for the neural space.
    """
    try:
        # Check if user_vectors table exists
        check_result = await db.execute(
            text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'user_vectors')")
        )
        table_exists = check_result.scalar()

        if not table_exists:
            logger.info("user_vectors table not found - returning empty graph")
            return GraphData(nodes=[], edges=[])

        # Build query
        where_clauses = ["user_id = :user_id"]
        params = {"user_id": user.id, "limit": limit}

        if layer:
            where_clauses.append("layer = :layer")
            params["layer"] = layer

        if visibility:
            where_clauses.append("visibility = :visibility")
            params["visibility"] = visibility

        where_sql = " AND ".join(where_clauses)

        result = await db.execute(
            text(f"""
                SELECT
                    id, content, agent_id, visibility, layer, message_type,
                    attention_weight, access_count, tags, responding_to,
                    related_agents, conversation_thread, created_at, last_accessed_at
                FROM user_vectors
                WHERE {where_sql}
                ORDER BY attention_weight DESC, created_at DESC
                LIMIT :limit
            """),
            params
        )
        rows = result.fetchall()

        nodes = [_row_to_node(row) for row in rows]
        edges = _build_edges(nodes)

        return GraphData(nodes=nodes, edges=edges)
    except Exception as e:
        logger.error(f"Cortex graph error: {e}")
        return GraphData(nodes=[], edges=[])


@router.get("/stats", response_model=CortexStats)
async def get_stats(
    user: User = Depends(get_current_user),
    db=Depends(get_db),
) -> CortexStats:
    """Get memory statistics for the dashboard."""
    try:
        # Check if user_vectors table exists
        check_result = await db.execute(
            text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'user_vectors')")
        )
        table_exists = check_result.scalar()

        if not table_exists:
            # Table doesn't exist - return empty stats with helpful message
            logger.info("user_vectors table not found - Neural system not yet initialized")
            return CortexStats(
                total=0,
                by_layer={"info": "Neural system initializing..."},
                by_visibility={},
                by_agent={},
                by_message_type={},
            )

        # Total count
        total_result = await db.execute(
            text("SELECT COUNT(*) FROM user_vectors WHERE user_id = :user_id"),
            {"user_id": user.id}
        )
        total = total_result.scalar() or 0

        # By layer
        layer_result = await db.execute(
            text("""
                SELECT COALESCE(layer, 'unknown') as layer, COUNT(*) as count
                FROM user_vectors WHERE user_id = :user_id
                GROUP BY layer
            """),
            {"user_id": user.id}
        )
        by_layer = {row.layer: row.count for row in layer_result.fetchall()}

        # By visibility
        vis_result = await db.execute(
            text("""
                SELECT COALESCE(visibility, 'private') as visibility, COUNT(*) as count
                FROM user_vectors WHERE user_id = :user_id
                GROUP BY visibility
            """),
            {"user_id": user.id}
        )
        by_visibility = {row.visibility: row.count for row in vis_result.fetchall()}

        # By agent
        agent_result = await db.execute(
            text("""
                SELECT COALESCE(agent_id, 'CLAUDE') as agent_id, COUNT(*) as count
                FROM user_vectors WHERE user_id = :user_id
                GROUP BY agent_id
            """),
            {"user_id": user.id}
        )
        by_agent = {row.agent_id: row.count for row in agent_result.fetchall()}

        # By message type
        type_result = await db.execute(
            text("""
                SELECT COALESCE(message_type, 'observation') as message_type, COUNT(*) as count
                FROM user_vectors WHERE user_id = :user_id
                GROUP BY message_type
            """),
            {"user_id": user.id}
        )
        by_message_type = {row.message_type: row.count for row in type_result.fetchall()}

        return CortexStats(
            total=total,
            by_layer=by_layer,
            by_visibility=by_visibility,
            by_agent=by_agent,
            by_message_type=by_message_type,
        )
    except Exception as e:
        logger.error(f"Cortex stats error: {e}")
        # Return empty stats instead of 500
        return CortexStats(
            total=0,
            by_layer={"error": "Neural system unavailable"},
            by_visibility={},
            by_agent={},
            by_message_type={},
        )


@router.post("/search", response_model=List[MemoryNode])
async def search_memories(
    request: SearchRequest,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
) -> List[MemoryNode]:
    """
    Semantic search for memories.
    Uses vector similarity to find related memories.
    """
    from app.services.embedding import get_embedding_service

    # Generate query embedding
    embed_service = get_embedding_service()
    query_embedding = await embed_service.embed(request.query)

    if query_embedding is None:
        raise HTTPException(status_code=503, detail="Embedding service unavailable")

    # Build filters
    where_clauses = ["user_id = :user_id"]
    params = {
        "user_id": user.id,
        "embedding": f"[{','.join(str(x) for x in query_embedding)}]",
        "limit": request.limit,
    }

    if request.layers:
        where_clauses.append("layer = ANY(:layers)")
        params["layers"] = request.layers

    if request.visibility:
        where_clauses.append("visibility = :visibility")
        params["visibility"] = request.visibility

    if request.agent_id:
        where_clauses.append("agent_id = :agent_id")
        params["agent_id"] = request.agent_id

    where_sql = " AND ".join(where_clauses)

    result = await db.execute(
        text(f"""
            SELECT
                id, content, agent_id, visibility, layer, message_type,
                attention_weight, access_count, tags, responding_to,
                related_agents, conversation_thread, created_at, last_accessed_at,
                1 - (embedding <=> :embedding) as similarity
            FROM user_vectors
            WHERE {where_sql}
            ORDER BY embedding <=> :embedding
            LIMIT :limit
        """),
        params
    )
    rows = result.fetchall()

    return [_row_to_node(row) for row in rows]


@router.patch("/memories/{memory_id}/layer")
async def update_memory_layer(
    memory_id: str,
    request: LayerUpdateRequest,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Promote or demote a memory's layer.
    Valid layers: sensory, working, long_term, cortex
    """
    valid_layers = ["sensory", "working", "long_term", "cortex"]
    if request.layer not in valid_layers:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid layer. Must be one of: {valid_layers}"
        )

    result = await db.execute(
        text("""
            UPDATE user_vectors
            SET layer = :layer
            WHERE id = :id AND user_id = :user_id
            RETURNING id
        """),
        {"id": UUID(memory_id), "user_id": user.id, "layer": request.layer}
    )
    await db.commit()

    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Memory not found")

    return {"success": True, "layer": request.layer}


@router.delete("/memories/{memory_id}")
async def delete_memory(
    memory_id: str,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Delete a memory."""
    result = await db.execute(
        text("""
            DELETE FROM user_vectors
            WHERE id = :id AND user_id = :user_id
            RETURNING id
        """),
        {"id": UUID(memory_id), "user_id": user.id}
    )
    await db.commit()

    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Memory not found")

    return {"success": True, "deleted": memory_id}


# =============================================================================
# Helpers
# =============================================================================

def _row_to_node(row) -> MemoryNode:
    """Convert database row to MemoryNode."""
    # Handle JSONB fields
    tags = row.tags if isinstance(row.tags, list) else json.loads(row.tags or "[]")
    responding_to = row.responding_to if isinstance(row.responding_to, list) else json.loads(row.responding_to or "[]")
    related_agents = row.related_agents if isinstance(row.related_agents, list) else json.loads(row.related_agents or "[]")

    return MemoryNode(
        id=str(row.id),
        content=row.content[:500] if row.content else "",  # Truncate for visualization
        agent_id=row.agent_id or "CLAUDE",
        visibility=row.visibility or "private",
        layer=row.layer or "working",
        message_type=row.message_type or "observation",
        attention_weight=float(row.attention_weight) if row.attention_weight else 1.0,
        access_count=row.access_count or 0,
        tags=tags,
        responding_to=[str(r) for r in responding_to] if responding_to else [],
        related_agents=related_agents,
        conversation_thread=row.conversation_thread,
        created_at=row.created_at.isoformat() if row.created_at else None,
        last_accessed_at=row.last_accessed_at.isoformat() if row.last_accessed_at else None,
    )


def _build_edges(nodes: List[MemoryNode]) -> List[GraphEdge]:
    """Build edges from node relationships."""
    edges = []
    node_ids = {n.id for n in nodes}

    for node in nodes:
        # responding_to relationships
        for target_id in node.responding_to:
            if target_id in node_ids:
                edges.append(GraphEdge(
                    source=node.id,
                    target=target_id,
                    type="responding_to"
                ))

    # Thread relationships (nodes in same thread)
    threads = {}
    for node in nodes:
        if node.conversation_thread:
            if node.conversation_thread not in threads:
                threads[node.conversation_thread] = []
            threads[node.conversation_thread].append(node.id)

    for thread_id, thread_nodes in threads.items():
        for i in range(len(thread_nodes) - 1):
            edges.append(GraphEdge(
                source=thread_nodes[i],
                target=thread_nodes[i + 1],
                type="thread"
            ))

    return edges
