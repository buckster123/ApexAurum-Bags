"""
Memory Service - The Cortex Engine

Handles memory storage, retrieval, extraction, and formatting.
The beating heart of agent memory.
"""

import json
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.agent_memory import AgentMemory
from app.models.conversation import Conversation

logger = logging.getLogger(__name__)

# Memory type definitions
MEMORY_TYPES = ('fact', 'preference', 'context', 'relationship')

# Claude prompt for memory extraction
EXTRACTION_PROMPT = """Analyze this conversation and extract memorable information about the user.

Extract ONLY information that is clearly stated or strongly implied. Quality over quantity.

Categories:
1. FACTS - Concrete information (name, job, location, skills, interests)
2. PREFERENCES - How they like things (communication style, detail level, code vs prose)
3. CONTEXT - Current projects or ongoing topics they're working on
4. RELATIONSHIP - Notes about your interaction pattern with them

Return ONLY valid JSON in this exact format (no markdown, no explanation):
{
  "facts": [
    {"key": "name", "value": "Alex", "confidence": 0.95}
  ],
  "preferences": [
    {"key": "communication_style", "value": "Prefers concise technical answers", "confidence": 0.7}
  ],
  "context": [
    {"key": "current_project", "value": "Building a Vue.js chat application", "confidence": 0.85}
  ],
  "relationship": []
}

Rules:
- Use snake_case keys (e.g., "programming_language", not "Programming Language")
- Values should be clear, concise statements
- Confidence: 0.95 for explicit statements, 0.80 for strong implications, 0.70 for inferences
- Return empty arrays if nothing to extract for a category
- Max 5 items per category

Conversation to analyze:
"""


class MemoryService:
    """Service for managing agent memories."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_memories_for_agent(
        self,
        user_id: UUID,
        agent_id: str,
        limit: int = 10,
        memory_types: Optional[list[str]] = None,
        min_confidence: float = 0.5,
    ) -> list[AgentMemory]:
        """
        Retrieve relevant memories for an agent-user pair.

        Prioritizes by:
        1. Confidence score (higher = more reliable)
        2. Recency of last access
        3. Access count (frequently used = more relevant)
        """
        query = (
            select(AgentMemory)
            .where(AgentMemory.user_id == user_id)
            .where(AgentMemory.agent_id == agent_id)
            .where(AgentMemory.confidence >= min_confidence)
        )

        if memory_types:
            query = query.where(AgentMemory.memory_type.in_(memory_types))

        # Order by confidence, then by last access, then by access count
        query = query.order_by(
            AgentMemory.confidence.desc(),
            AgentMemory.last_accessed.desc(),
            AgentMemory.access_count.desc(),
        ).limit(limit)

        result = await self.db.execute(query)
        memories = list(result.scalars().all())

        # Update access timestamps and counts for retrieved memories
        if memories:
            memory_ids = [m.id for m in memories]
            await self.db.execute(
                update(AgentMemory)
                .where(AgentMemory.id.in_(memory_ids))
                .values(
                    last_accessed=datetime.utcnow(),
                    access_count=AgentMemory.access_count + 1,
                )
            )

        return memories

    async def get_all_memories_for_user(
        self,
        user_id: UUID,
        agent_id: Optional[str] = None,
    ) -> dict[str, list[AgentMemory]]:
        """Get all memories for a user, optionally filtered by agent, grouped by agent."""
        query = select(AgentMemory).where(AgentMemory.user_id == user_id)

        if agent_id:
            query = query.where(AgentMemory.agent_id == agent_id)

        query = query.order_by(AgentMemory.agent_id, AgentMemory.confidence.desc())

        result = await self.db.execute(query)
        memories = result.scalars().all()

        # Group by agent
        grouped = {}
        for memory in memories:
            if memory.agent_id not in grouped:
                grouped[memory.agent_id] = []
            grouped[memory.agent_id].append(memory)

        return grouped

    async def save_memory(
        self,
        user_id: UUID,
        agent_id: str,
        memory_type: str,
        key: str,
        value: str,
        confidence: float = 0.8,
        source_conversation_id: Optional[UUID] = None,
    ) -> AgentMemory:
        """
        Save or update a memory.

        If a memory with the same user/agent/key exists, updates it.
        Confidence increases slightly with reconfirmation.
        """
        if memory_type not in MEMORY_TYPES:
            raise ValueError(f"Invalid memory_type. Use: {MEMORY_TYPES}")

        # Check for existing memory with same key
        result = await self.db.execute(
            select(AgentMemory)
            .where(AgentMemory.user_id == user_id)
            .where(AgentMemory.agent_id == agent_id)
            .where(AgentMemory.key == key)
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing memory
            # Increase confidence slightly if being reconfirmed (max 1.0)
            new_confidence = min(1.0, (existing.confidence + confidence) / 2 + 0.05)

            existing.value = value
            existing.confidence = new_confidence
            existing.memory_type = memory_type
            existing.updated_at = datetime.utcnow()
            if source_conversation_id:
                existing.source_conversation_id = source_conversation_id

            return existing

        # Create new memory
        memory = AgentMemory(
            user_id=user_id,
            agent_id=agent_id,
            memory_type=memory_type,
            key=key,
            value=value,
            confidence=confidence,
            source_conversation_id=source_conversation_id,
        )
        self.db.add(memory)

        return memory

    async def delete_memory(
        self,
        user_id: UUID,
        memory_id: UUID,
    ) -> bool:
        """Delete a specific memory."""
        result = await self.db.execute(
            delete(AgentMemory)
            .where(AgentMemory.id == memory_id)
            .where(AgentMemory.user_id == user_id)
        )
        return result.rowcount > 0

    async def clear_agent_memories(
        self,
        user_id: UUID,
        agent_id: str,
    ) -> int:
        """Clear all memories for a specific agent (per-agent amnesia)."""
        result = await self.db.execute(
            delete(AgentMemory)
            .where(AgentMemory.user_id == user_id)
            .where(AgentMemory.agent_id == agent_id)
        )
        return result.rowcount

    async def clear_all_memories(self, user_id: UUID) -> int:
        """Clear all memories for a user (full amnesia)."""
        result = await self.db.execute(
            delete(AgentMemory).where(AgentMemory.user_id == user_id)
        )
        return result.rowcount

    async def get_memory_stats(self, user_id: UUID) -> dict:
        """Get memory statistics for a user."""
        result = await self.db.execute(
            select(
                AgentMemory.agent_id,
                func.count(AgentMemory.id).label('count'),
            )
            .where(AgentMemory.user_id == user_id)
            .group_by(AgentMemory.agent_id)
        )

        stats = {}
        total = 0
        for row in result:
            stats[row.agent_id] = row.count
            total += row.count

        return {'by_agent': stats, 'total': total}

    def format_memories_for_prompt(
        self,
        memories: list[AgentMemory],
    ) -> str:
        """
        Format memories into a prompt block for injection into system prompt.

        Returns a structured block that helps the agent recall user context.
        """
        if not memories:
            return ""

        # Group by type
        by_type = {
            'fact': [],
            'preference': [],
            'context': [],
            'relationship': [],
        }

        for memory in memories:
            mtype = memory.memory_type
            if mtype in by_type:
                # Format key nicely: snake_case -> Title Case
                nice_key = memory.key.replace('_', ' ').title()
                by_type[mtype].append(f"- {nice_key}: {memory.value}")

        lines = ["\n## What You Remember About This User\n"]

        if by_type['fact']:
            lines.append("**Known Facts:**")
            lines.extend(by_type['fact'])
            lines.append("")

        if by_type['preference']:
            lines.append("**User Preferences:**")
            lines.extend(by_type['preference'])
            lines.append("")

        if by_type['context']:
            lines.append("**Current Context:**")
            lines.extend(by_type['context'])
            lines.append("")

        if by_type['relationship']:
            lines.append("**Interaction Notes:**")
            lines.extend(by_type['relationship'])
            lines.append("")

        lines.append("Use these memories naturally in conversation. Don't explicitly say 'I remember' unless asked.\n")

        return "\n".join(lines)


async def extract_memories_from_conversation(
    db: AsyncSession,
    conversation_id: UUID,
    user_id: UUID,
    agent_id: str,
    claude_service,  # ClaudeService instance
) -> dict:
    """
    Extract memories from a conversation using Claude analysis.

    Called after a conversation ends or on-demand.
    Returns dict with 'extracted' count and 'errors' list.
    """
    # Load conversation with messages
    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id)
        .where(Conversation.user_id == user_id)
    )
    conversation = result.scalar_one_or_none()

    if not conversation or not conversation.messages:
        return {'extracted': 0, 'errors': ['Conversation not found or empty']}

    # Format messages for analysis (limit context)
    message_text = []
    for msg in sorted(conversation.messages, key=lambda m: m.created_at):
        role = "User" if msg.role == "user" else "Assistant"
        content = msg.content[:1000] if msg.content else ""  # Limit per message
        message_text.append(f"{role}: {content}")

    # Limit to last 20 messages and 8000 chars total
    full_text = "\n".join(message_text[-20:])
    if len(full_text) > 8000:
        full_text = full_text[:8000] + "\n[Truncated]"

    try:
        # Call Claude for extraction (use fast model)
        response = await claude_service.chat(
            messages=[{
                "role": "user",
                "content": EXTRACTION_PROMPT + full_text
            }],
            model="claude-3-haiku-20240307",
            max_tokens=1000,
        )

        # Parse response
        response_text = ""
        for block in response.get("content", []):
            if block.get("text"):
                response_text += block["text"]

        # Extract JSON from response
        try:
            # Find JSON in response (handle potential markdown wrapping)
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                extracted = json.loads(response_text[json_start:json_end])
            else:
                logger.warning(f"No JSON found in extraction response: {response_text[:200]}")
                return {'extracted': 0, 'errors': ['No JSON found in response']}
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse extraction response: {e}")
            return {'extracted': 0, 'errors': [f'JSON parse error: {str(e)}']}

        # Save extracted memories
        memory_service = MemoryService(db)
        saved_count = 0

        for memory_type in ['facts', 'preferences', 'context', 'relationship']:
            # Map plural to singular type
            singular_type = memory_type.rstrip('s') if memory_type.endswith('s') else memory_type
            items = extracted.get(memory_type, [])

            for item in items:
                if isinstance(item, dict) and 'key' in item and 'value' in item:
                    try:
                        await memory_service.save_memory(
                            user_id=user_id,
                            agent_id=agent_id,
                            memory_type=singular_type,
                            key=str(item['key']),
                            value=str(item['value']),
                            confidence=float(item.get('confidence', 0.7)),
                            source_conversation_id=conversation_id,
                        )
                        saved_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to save memory {item}: {e}")

        await db.commit()
        logger.info(f"Extracted {saved_count} memories from conversation {conversation_id}")
        return {'extracted': saved_count, 'errors': []}

    except Exception as e:
        logger.error(f"Memory extraction failed: {e}")
        return {'extracted': 0, 'errors': [str(e)]}
