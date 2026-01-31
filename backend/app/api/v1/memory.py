"""
Memory API Endpoints - The Cortex Interface

CRUD operations for agent memories, export, and amnesia controls.
"""

import json
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.agent_memory import AgentMemory
from app.auth.deps import get_current_user
from app.services.memory import MemoryService, extract_memories_from_conversation, MEMORY_TYPES
from app.services.claude import create_claude_service
from app.api.v1.user import get_user_api_key

logger = logging.getLogger(__name__)
router = APIRouter()


# === Schemas ===

class MemoryCreate(BaseModel):
    """Schema for creating a new memory."""
    memory_type: str = Field(..., description="Type: fact, preference, context, relationship")
    key: str = Field(..., min_length=1, max_length=255, description="Memory key (snake_case)")
    value: str = Field(..., min_length=1, description="Memory value")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Confidence score 0-1")


class MemoryUpdate(BaseModel):
    """Schema for updating a memory."""
    value: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    memory_type: Optional[str] = None


# === Endpoints ===

@router.get("/stats")
async def get_memory_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get memory statistics for the current user.

    Returns counts grouped by agent.
    """
    service = MemoryService(db)
    stats = await service.get_memory_stats(user.id)
    return stats


@router.get("/agents")
async def list_agents_with_memories(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List all agents that have memories for this user.

    Includes memory count and latest update time per agent.
    """
    service = MemoryService(db)
    grouped = await service.get_all_memories_for_user(user.id)

    result = []
    for agent_id, memories in grouped.items():
        result.append({
            'agent_id': agent_id,
            'count': len(memories),
            'latest_update': max(m.updated_at for m in memories).isoformat() if memories else None,
            'memory_types': list(set(m.memory_type for m in memories)),
        })

    return {'agents': result}


@router.get("/{agent_id}")
async def get_agent_memories(
    agent_id: str,
    memory_type: Optional[str] = None,
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all memories for a specific agent.

    Can filter by memory_type (fact, preference, context, relationship).
    """
    service = MemoryService(db)

    memory_types = [memory_type] if memory_type else None
    memories = await service.get_memories_for_agent(
        user_id=user.id,
        agent_id=agent_id,
        limit=limit,
        memory_types=memory_types,
        min_confidence=0.0,  # Include all for viewing
    )

    return {
        'agent_id': agent_id,
        'count': len(memories),
        'memories': [m.to_dict() for m in memories]
    }


@router.post("/{agent_id}")
async def add_memory(
    agent_id: str,
    memory: MemoryCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Manually add a memory for an agent.

    Memory types: fact, preference, context, relationship
    """
    if memory.memory_type not in MEMORY_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid memory_type. Use: {', '.join(MEMORY_TYPES)}"
        )

    service = MemoryService(db)
    saved = await service.save_memory(
        user_id=user.id,
        agent_id=agent_id,
        memory_type=memory.memory_type,
        key=memory.key,
        value=memory.value,
        confidence=memory.confidence,
    )
    await db.commit()

    return {
        'id': str(saved.id),
        'message': 'Memory saved',
        'key': saved.key,
    }


@router.patch("/{agent_id}/{memory_id}")
async def update_memory(
    agent_id: str,
    memory_id: UUID,
    updates: MemoryUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a specific memory."""
    result = await db.execute(
        select(AgentMemory)
        .where(AgentMemory.id == memory_id)
        .where(AgentMemory.user_id == user.id)
        .where(AgentMemory.agent_id == agent_id)
    )
    memory = result.scalar_one_or_none()

    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    if updates.value is not None:
        memory.value = updates.value
    if updates.confidence is not None:
        memory.confidence = max(0.0, min(1.0, updates.confidence))
    if updates.memory_type is not None:
        if updates.memory_type in MEMORY_TYPES:
            memory.memory_type = updates.memory_type
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid memory_type. Use: {', '.join(MEMORY_TYPES)}"
            )

    memory.updated_at = datetime.utcnow()
    await db.commit()

    return {'message': 'Memory updated', 'id': str(memory.id)}


@router.delete("/{agent_id}/{memory_id}")
async def delete_memory(
    agent_id: str,
    memory_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a specific memory."""
    service = MemoryService(db)
    deleted = await service.delete_memory(user.id, memory_id)
    await db.commit()

    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")

    return {'message': 'Memory deleted'}


@router.delete("/{agent_id}")
async def clear_agent_memories(
    agent_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Clear all memories for a specific agent (per-agent amnesia).

    This cannot be undone.
    """
    service = MemoryService(db)
    count = await service.clear_agent_memories(user.id, agent_id)
    await db.commit()

    return {'message': f'Cleared {count} memories for {agent_id}', 'deleted': count}


@router.delete("/")
async def clear_all_memories(
    confirm: bool = False,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Clear ALL memories for the user (full amnesia).

    Requires confirm=true query parameter. This cannot be undone.
    """
    if not confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must pass confirm=true to clear all memories"
        )

    service = MemoryService(db)
    count = await service.clear_all_memories(user.id)
    await db.commit()

    return {'message': f'Cleared all {count} memories', 'deleted': count}


@router.get("/export/all")
async def export_all_memories(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Export all memories in JSON format (GDPR compliance).

    Returns a downloadable JSON file with all user memories.
    """
    service = MemoryService(db)
    grouped = await service.get_all_memories_for_user(user.id)

    export_data = {
        'exported_at': datetime.utcnow().isoformat(),
        'user_id': str(user.id),
        'email': user.email,
        'total_memories': sum(len(m) for m in grouped.values()),
        'memories_by_agent': {}
    }

    for agent_id, memories in grouped.items():
        export_data['memories_by_agent'][agent_id] = [
            {
                'memory_type': m.memory_type,
                'key': m.key,
                'value': m.value,
                'confidence': m.confidence,
                'created_at': m.created_at.isoformat() if m.created_at else None,
                'updated_at': m.updated_at.isoformat() if m.updated_at else None,
                'access_count': m.access_count,
            }
            for m in memories
        ]

    filename = f"apexaurum-memories-{datetime.utcnow().strftime('%Y%m%d')}.json"

    return Response(
        content=json.dumps(export_data, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.post("/{agent_id}/extract/{conversation_id}")
async def trigger_memory_extraction(
    agent_id: str,
    conversation_id: UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Trigger memory extraction from a specific conversation.

    Uses Claude to analyze the conversation and extract memories.
    Note: This consumes API tokens from your API key.
    """
    # Verify user has API key (needed for extraction)
    user_api_key = get_user_api_key(user)
    if not user_api_key:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="API key required for memory extraction"
        )

    # Run extraction (not in background for now - want immediate feedback)
    claude = create_claude_service(user_api_key)
    result = await extract_memories_from_conversation(
        db=db,
        conversation_id=conversation_id,
        user_id=user.id,
        agent_id=agent_id,
        claude_service=claude,
    )

    if result['errors']:
        return {
            'message': 'Extraction completed with errors',
            'extracted': result['extracted'],
            'errors': result['errors'],
        }

    return {
        'message': f"Extracted {result['extracted']} memories",
        'extracted': result['extracted'],
        'conversation_id': str(conversation_id),
    }
