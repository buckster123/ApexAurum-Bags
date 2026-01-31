"""
Neural Memory Service - The Remembering Deep

Stores chat messages as vector embeddings in user_vectors table
for the Neo-Cortex 3D visualization dashboard.
"""

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.embedding import get_embedding_service

logger = logging.getLogger(__name__)


class NeuralMemoryService:
    """
    Service for storing chat messages as vector memories.

    Each message becomes a node in the Neural visualization:
    - User messages: "dialogue" type, "private" visibility
    - Assistant responses: "observation" type, "private" visibility
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.embedding_service = get_embedding_service()

    async def store_message(
        self,
        user_id: UUID,
        content: str,
        agent_id: str = "AZOTH",
        role: str = "user",  # "user" or "assistant"
        conversation_thread: Optional[str] = None,
        responding_to: Optional[list[str]] = None,
        visibility: str = "private",  # "private" or "village"
        collection: str = "chat",  # "chat" or "council"
    ) -> Optional[UUID]:
        """
        Store a chat message as a vector memory.

        Args:
            user_id: The user's ID
            content: Message text content
            agent_id: Agent ID (AZOTH, ELYSIAN, etc.)
            role: "user" or "assistant"
            conversation_thread: Optional conversation ID for threading
            responding_to: Optional list of memory IDs this responds to
            visibility: "private" (user only) or "village" (shared with all agents)
            collection: "chat" for regular chat, "council" for deliberations

        Returns:
            UUID of created memory, or None if failed
        """
        # Skip very short messages
        if len(content.strip()) < 10:
            logger.debug(f"Skipping short message: {len(content)} chars")
            return None

        # Truncate very long messages for embedding
        embed_content = content[:8000] if len(content) > 8000 else content

        try:
            # Generate embedding
            embedding = await self.embedding_service.embed(embed_content)

            if embedding is None:
                logger.warning("Failed to generate embedding - no API key or service error")
                # Still store without embedding (allows manual embedding later)
                embedding = None

            # Determine memory properties based on role
            if role == "user":
                message_type = "dialogue"
                layer = "sensory"  # User input starts in sensory layer
            else:
                message_type = "observation"
                layer = "working"  # Assistant responses go to working memory

            # Prepare metadata
            memory_id = uuid4()
            responding_to_json = responding_to if responding_to else []

            # Build SQL based on whether we have an embedding
            if embedding:
                embedding_str = f"[{','.join(str(x) for x in embedding)}]"
                await self.db.execute(
                    text("""
                        INSERT INTO user_vectors (
                            id, user_id, collection, content, metadata, embedding,
                            layer, visibility, agent_id, message_type,
                            attention_weight, access_count, responding_to,
                            conversation_thread, related_agents, tags, created_at
                        ) VALUES (
                            :id, :user_id, :collection, :content, '{}', :embedding,
                            :layer, :visibility, :agent_id, :message_type,
                            1.0, 0, :responding_to,
                            :conversation_thread, '[]', '[]', NOW()
                        )
                    """),
                    {
                        "id": memory_id,
                        "user_id": user_id,
                        "collection": collection,
                        "content": content[:2000],  # Truncate stored content
                        "embedding": embedding_str,
                        "layer": layer,
                        "visibility": visibility,
                        "agent_id": agent_id,
                        "message_type": message_type,
                        "responding_to": str(responding_to_json).replace("'", '"'),
                        "conversation_thread": conversation_thread,
                    }
                )
            else:
                # Store without embedding (embedding column allows NULL)
                await self.db.execute(
                    text("""
                        INSERT INTO user_vectors (
                            id, user_id, collection, content, metadata,
                            layer, visibility, agent_id, message_type,
                            attention_weight, access_count, responding_to,
                            conversation_thread, related_agents, tags, created_at
                        ) VALUES (
                            :id, :user_id, :collection, :content, '{}',
                            :layer, :visibility, :agent_id, :message_type,
                            1.0, 0, :responding_to,
                            :conversation_thread, '[]', '[]', NOW()
                        )
                    """),
                    {
                        "id": memory_id,
                        "user_id": user_id,
                        "collection": collection,
                        "visibility": visibility,
                        "content": content[:2000],
                        "layer": layer,
                        "agent_id": agent_id,
                        "message_type": message_type,
                        "responding_to": str(responding_to_json).replace("'", '"'),
                        "conversation_thread": conversation_thread,
                    }
                )

            logger.debug(f"Stored neural memory: {memory_id} ({role}/{agent_id})")
            return memory_id

        except Exception as e:
            logger.error(f"Failed to store neural memory: {e}")
            return None

    async def store_conversation_exchange(
        self,
        user_id: UUID,
        user_message: str,
        assistant_response: str,
        agent_id: str = "CLAUDE",
        conversation_id: Optional[UUID] = None,
    ) -> dict:
        """
        Store both user message and assistant response as linked memories.

        Args:
            user_id: The user's ID
            user_message: What the user said
            assistant_response: What the assistant replied
            agent_id: Agent ID
            conversation_id: Optional conversation UUID for threading

        Returns:
            Dict with user_memory_id and assistant_memory_id (may be None if failed)
        """
        thread = str(conversation_id) if conversation_id else None

        # Store user message first
        user_memory_id = await self.store_message(
            user_id=user_id,
            content=user_message,
            agent_id=agent_id,
            role="user",
            conversation_thread=thread,
        )

        # Store assistant response, linking to user message
        responding_to = [str(user_memory_id)] if user_memory_id else []
        assistant_memory_id = await self.store_message(
            user_id=user_id,
            content=assistant_response,
            agent_id=agent_id,
            role="assistant",
            conversation_thread=thread,
            responding_to=responding_to,
        )

        return {
            "user_memory_id": str(user_memory_id) if user_memory_id else None,
            "assistant_memory_id": str(assistant_memory_id) if assistant_memory_id else None,
        }


    async def get_village_memories(
        self,
        user_id: UUID,
        topic: Optional[str] = None,
        limit: int = 10,
        collection: str = "council",
    ) -> list[dict]:
        """
        Retrieve Village-level memories (visibility='village') for context injection.

        These are shared memories from past council discussions and other agents.
        Can optionally do semantic search if topic is provided and embeddings exist.

        Args:
            user_id: The user's ID (memories are still user-scoped)
            topic: Optional topic for semantic search
            limit: Max memories to return
            collection: Filter by collection (default: council)

        Returns:
            List of memory dicts with content, agent_id, created_at
        """
        try:
            # If topic provided and embedding service available, do semantic search
            if topic and self.embedding_service:
                try:
                    topic_embedding = await self.embedding_service.embed(topic)
                    if topic_embedding:
                        embedding_str = f"[{','.join(str(x) for x in topic_embedding)}]"
                        result = await self.db.execute(
                            text("""
                                SELECT id, content, agent_id, created_at, message_type,
                                       1 - (embedding <=> CAST(:topic_embedding AS vector)) as similarity
                                FROM user_vectors
                                WHERE user_id = :user_id
                                  AND visibility = 'village'
                                  AND collection = :collection
                                  AND embedding IS NOT NULL
                                ORDER BY embedding <=> CAST(:topic_embedding AS vector)
                                LIMIT :limit
                            """),
                            {
                                "user_id": user_id,
                                "collection": collection,
                                "topic_embedding": embedding_str,
                                "limit": limit,
                            }
                        )
                        rows = result.fetchall()
                        return [
                            {
                                "id": str(row[0]),
                                "content": row[1],
                                "agent_id": row[2],
                                "created_at": row[3].isoformat() if row[3] else None,
                                "message_type": row[4],
                                "similarity": float(row[5]) if row[5] else None,
                            }
                            for row in rows
                        ]
                except Exception as e:
                    logger.warning(f"Semantic search failed, falling back to recency: {e}")

            # Fallback: get most recent Village memories
            result = await self.db.execute(
                text("""
                    SELECT id, content, agent_id, created_at, message_type
                    FROM user_vectors
                    WHERE user_id = :user_id
                      AND visibility = 'village'
                      AND collection = :collection
                    ORDER BY created_at DESC
                    LIMIT :limit
                """),
                {
                    "user_id": user_id,
                    "collection": collection,
                    "limit": limit,
                }
            )
            rows = result.fetchall()
            return [
                {
                    "id": str(row[0]),
                    "content": row[1],
                    "agent_id": row[2],
                    "created_at": row[3].isoformat() if row[3] else None,
                    "message_type": row[4],
                }
                for row in rows
            ]

        except Exception as e:
            logger.error(f"Failed to get village memories: {e}")
            return []

    def format_village_memories_for_prompt(
        self,
        memories: list[dict],
        max_chars: int = 2000,
    ) -> str:
        """
        Format Village memories into a prompt injection block.

        Args:
            memories: List of memory dicts from get_village_memories
            max_chars: Maximum characters for the block

        Returns:
            Formatted string to append to system prompt
        """
        if not memories:
            return ""

        lines = [
            "\n\n═══ THE VILLAGE MEMORY ═══",
            "Shared wisdom from past deliberations and fellow agents:\n"
        ]

        total_chars = sum(len(l) for l in lines)

        for mem in memories:
            agent = mem.get("agent_id", "Unknown")
            content = mem.get("content", "")[:500]  # Truncate individual memories
            line = f"[{agent}]: {content}\n"

            if total_chars + len(line) > max_chars:
                lines.append("... (more memories available)")
                break

            lines.append(line)
            total_chars += len(line)

        lines.append("═══════════════════════════\n")

        return "\n".join(lines)


# Convenience function for use in chat.py
async def store_chat_memory(
    db: AsyncSession,
    user_id: UUID,
    user_message: str,
    assistant_response: str,
    agent_id: str = "CLAUDE",
    conversation_id: Optional[UUID] = None,
) -> dict:
    """
    Convenience function to store a chat exchange as neural memories.

    Call this after generating a response to populate the Neural visualization.
    """
    service = NeuralMemoryService(db)
    return await service.store_conversation_exchange(
        user_id=user_id,
        user_message=user_message,
        assistant_response=assistant_response,
        agent_id=agent_id,
        conversation_id=conversation_id,
    )
