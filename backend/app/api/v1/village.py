"""
Village Endpoints

Multi-agent shared memory (Village Protocol).
"""

import logging
from typing import Optional
from uuid import UUID, uuid4
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.village import VillageKnowledge
from app.auth.deps import get_current_user_optional
from app.services.claude import ClaudeService

logger = logging.getLogger(__name__)
router = APIRouter()

# Initialize Claude service
_claude_service = None

def get_claude_service() -> ClaudeService:
    global _claude_service
    if _claude_service is None:
        _claude_service = ClaudeService()
    return _claude_service


# Schemas
class KnowledgeAddRequest(BaseModel):
    content: str
    category: Optional[str] = "general"
    visibility: str = "private"  # 'private', 'village', 'bridge'
    agent_id: Optional[str] = None
    conversation_thread: Optional[str] = None
    tags: list[str] = []


class KnowledgeResponse(BaseModel):
    id: UUID
    content: str
    category: Optional[str]
    visibility: str
    agent_id: Optional[str]
    conversation_thread: Optional[str]
    tags: list[str]
    access_count: int
    created_at: str

    class Config:
        from_attributes = True


class KnowledgeSearchResponse(BaseModel):
    results: list[KnowledgeResponse]
    total: int


class ConvergenceResponse(BaseModel):
    convergence_type: str  # 'NONE', 'HARMONY', 'CONSENSUS'
    agents: list[str]
    similarity: float
    topic: str
    evidence: list[dict]


# In-memory village store (for unauthenticated users)
_village_memory = []

# Endpoints
@router.post("/knowledge", response_model=KnowledgeResponse)
async def add_knowledge(
    request: KnowledgeAddRequest,
    user: User = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    Add knowledge to the village.

    Visibility levels:
    - private: Only visible to the creating user
    - village: Visible to all agents in the village
    - bridge: Cross-agent connection point
    """
    knowledge_id = uuid4()
    created_at = datetime.utcnow()

    if user:
        # Save to database if authenticated
        knowledge = VillageKnowledge(
            id=knowledge_id,
            user_id=user.id,
            content=request.content,
            category=request.category,
            visibility=request.visibility,
            agent_id=request.agent_id,
            conversation_thread=request.conversation_thread,
            tags=request.tags,
        )
        db.add(knowledge)
        await db.commit()
    else:
        # Store in memory for session
        _village_memory.append({
            "id": knowledge_id,
            "content": request.content,
            "category": request.category,
            "visibility": request.visibility,
            "agent_id": request.agent_id,
            "conversation_thread": request.conversation_thread,
            "tags": request.tags,
            "access_count": 0,
            "created_at": created_at,
        })

    return KnowledgeResponse(
        id=knowledge_id,
        content=request.content,
        category=request.category,
        visibility=request.visibility,
        agent_id=request.agent_id,
        conversation_thread=request.conversation_thread,
        tags=request.tags,
        access_count=0,
        created_at=created_at.isoformat(),
    )


@router.get("/knowledge", response_model=KnowledgeSearchResponse)
async def search_knowledge(
    query: str,
    visibility: Optional[str] = None,
    agent_id: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 10,
    user: User = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    Search village knowledge using keyword matching.
    """
    results = []

    if user:
        # Search database
        base_query = select(VillageKnowledge).where(VillageKnowledge.user_id == user.id)

        if visibility:
            base_query = base_query.where(VillageKnowledge.visibility == visibility)
        if agent_id:
            base_query = base_query.where(VillageKnowledge.agent_id == agent_id)
        if category:
            base_query = base_query.where(VillageKnowledge.category == category)

        base_query = base_query.where(
            VillageKnowledge.content.ilike(f"%{query}%")
        ).limit(limit)

        result = await db.execute(base_query)
        knowledge_items = result.scalars().all()

        results = [
            KnowledgeResponse(
                id=k.id,
                content=k.content,
                category=k.category,
                visibility=k.visibility,
                agent_id=k.agent_id,
                conversation_thread=k.conversation_thread,
                tags=k.tags,
                access_count=k.access_count,
                created_at=k.created_at.isoformat(),
            )
            for k in knowledge_items
        ]
    else:
        # Search in-memory store
        query_lower = query.lower()
        for k in _village_memory:
            if query_lower in k["content"].lower():
                if visibility and k["visibility"] != visibility:
                    continue
                if agent_id and k["agent_id"] != agent_id:
                    continue
                if category and k["category"] != category:
                    continue

                results.append(KnowledgeResponse(
                    id=k["id"],
                    content=k["content"],
                    category=k["category"],
                    visibility=k["visibility"],
                    agent_id=k["agent_id"],
                    conversation_thread=k["conversation_thread"],
                    tags=k["tags"],
                    access_count=k["access_count"],
                    created_at=k["created_at"].isoformat(),
                ))

                if len(results) >= limit:
                    break

    return KnowledgeSearchResponse(results=results, total=len(results))


@router.get("/convergence", response_model=ConvergenceResponse)
async def detect_convergence(
    topic: Optional[str] = None,
    user: User = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    Detect convergence across agents using AI analysis.

    Convergence types:
    - HARMONY: 2 agents agree on a topic
    - CONSENSUS: 3+ agents agree on a topic
    """
    # Gather recent knowledge entries
    knowledge_items = []

    if user:
        result = await db.execute(
            select(VillageKnowledge)
            .where(VillageKnowledge.user_id == user.id)
            .order_by(VillageKnowledge.created_at.desc())
            .limit(20)
        )
        db_items = result.scalars().all()
        for k in db_items:
            knowledge_items.append({
                "agent": k.agent_id or "Unknown",
                "content": k.content,
                "category": k.category,
            })
    else:
        # Use in-memory store
        for k in _village_memory[-20:]:
            knowledge_items.append({
                "agent": k["agent_id"] or "Unknown",
                "content": k["content"],
                "category": k["category"],
            })

    if len(knowledge_items) < 2:
        return ConvergenceResponse(
            convergence_type="NONE",
            agents=[],
            similarity=0.0,
            topic=topic or "No data",
            evidence=[],
        )

    # Use Claude to analyze for convergence
    try:
        claude = get_claude_service()

        knowledge_text = "\n".join([
            f"- {k['agent']}: {k['content'][:200]}"
            for k in knowledge_items
        ])

        analysis_prompt = f"""Analyze these knowledge entries from different AI agents for convergence (agreement/alignment):

{knowledge_text}

Respond in this exact format:
CONVERGENCE: [NONE, HARMONY, or CONSENSUS]
AGENTS: [comma-separated list of agreeing agents, or "none"]
SIMILARITY: [0.0 to 1.0 score]
TOPIC: [the topic they converge on, or "none"]
EVIDENCE: [brief explanation]"""

        response = await claude.chat(
            messages=[{"role": "user", "content": analysis_prompt}],
            model="claude-3-haiku-20240307",
            system="You are an analyst detecting convergence patterns. Be precise and follow the format exactly.",
        )

        content = ""
        for block in response.get("content", []):
            if block.get("text"):
                content += block["text"]

        # Parse response
        convergence_type = "NONE"
        agents = []
        similarity = 0.0
        detected_topic = topic or ""
        evidence = []

        for line in content.split("\n"):
            if line.startswith("CONVERGENCE:"):
                val = line.split(":", 1)[1].strip().upper()
                if val in ["HARMONY", "CONSENSUS"]:
                    convergence_type = val
            elif line.startswith("AGENTS:"):
                val = line.split(":", 1)[1].strip()
                if val.lower() != "none":
                    agents = [a.strip() for a in val.split(",")]
            elif line.startswith("SIMILARITY:"):
                try:
                    similarity = float(line.split(":", 1)[1].strip())
                except:
                    pass
            elif line.startswith("TOPIC:"):
                val = line.split(":", 1)[1].strip()
                if val.lower() != "none":
                    detected_topic = val
            elif line.startswith("EVIDENCE:"):
                evidence.append({"text": line.split(":", 1)[1].strip()})

        return ConvergenceResponse(
            convergence_type=convergence_type,
            agents=agents,
            similarity=similarity,
            topic=detected_topic,
            evidence=evidence,
        )

    except Exception as e:
        logger.error(f"Convergence detection failed: {e}")
        return ConvergenceResponse(
            convergence_type="NONE",
            agents=[],
            similarity=0.0,
            topic=topic or "",
            evidence=[{"text": f"Analysis error: {str(e)}"}],
        )


@router.get("/threads")
async def list_threads(
    limit: int = 20,
    user: User = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """List conversation threads in the village."""
    threads = []

    if user:
        from sqlalchemy import distinct
        result = await db.execute(
            select(distinct(VillageKnowledge.conversation_thread))
            .where(VillageKnowledge.user_id == user.id)
            .where(VillageKnowledge.conversation_thread.isnot(None))
            .limit(limit)
        )
        threads = [r for r in result.scalars().all() if r]
    else:
        # From in-memory store
        seen = set()
        for k in _village_memory:
            if k["conversation_thread"] and k["conversation_thread"] not in seen:
                threads.append(k["conversation_thread"])
                seen.add(k["conversation_thread"])
                if len(threads) >= limit:
                    break

    return {"threads": threads, "total": len(threads)}


@router.delete("/knowledge/{knowledge_id}")
async def delete_knowledge(
    knowledge_id: UUID,
    user: User = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """Delete a knowledge entry."""
    if user:
        result = await db.execute(
            select(VillageKnowledge)
            .where(VillageKnowledge.id == knowledge_id)
            .where(VillageKnowledge.user_id == user.id)
        )
        knowledge = result.scalar_one_or_none()

        if not knowledge:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Knowledge not found"
            )

        await db.delete(knowledge)
    else:
        # Remove from in-memory store
        global _village_memory
        _village_memory = [k for k in _village_memory if k["id"] != knowledge_id]

    return {"message": "Knowledge deleted"}


@router.get("/all", response_model=KnowledgeSearchResponse)
async def list_all_knowledge(
    limit: int = 50,
    user: User = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """List all knowledge in the village (for browsing)."""
    results = []

    if user:
        result = await db.execute(
            select(VillageKnowledge)
            .where(VillageKnowledge.user_id == user.id)
            .order_by(VillageKnowledge.created_at.desc())
            .limit(limit)
        )
        knowledge_items = result.scalars().all()
        results = [
            KnowledgeResponse(
                id=k.id,
                content=k.content,
                category=k.category,
                visibility=k.visibility,
                agent_id=k.agent_id,
                conversation_thread=k.conversation_thread,
                tags=k.tags,
                access_count=k.access_count,
                created_at=k.created_at.isoformat(),
            )
            for k in knowledge_items
        ]
    else:
        for k in _village_memory[-limit:]:
            results.append(KnowledgeResponse(
                id=k["id"],
                content=k["content"],
                category=k["category"],
                visibility=k["visibility"],
                agent_id=k["agent_id"],
                conversation_thread=k["conversation_thread"],
                tags=k["tags"],
                access_count=k["access_count"],
                created_at=k["created_at"].isoformat(),
            ))

    return KnowledgeSearchResponse(results=results, total=len(results))
