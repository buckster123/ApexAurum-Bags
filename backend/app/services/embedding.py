"""
Embedding Service - The Remembering Deep

Generate embeddings for semantic search.

Supports:
- Local (FastEmbed) - Private, no API key needed
- OpenAI - text-embedding-3-small
- Voyage AI - voyage-2
"""

import logging
from typing import Optional
import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

# Lazy-load FastEmbed to avoid import overhead when not using local embeddings
_local_model = None


def _get_local_model():
    """Lazy-load the local embedding model."""
    global _local_model
    if _local_model is None:
        try:
            from fastembed import TextEmbedding
            settings = get_settings()
            model_name = settings.embedding_model
            logger.info(f"Loading local embedding model: {model_name}")
            _local_model = TextEmbedding(model_name=model_name)
            logger.info(f"Local embedding model loaded successfully")
        except ImportError:
            logger.error("FastEmbed not installed. Run: pip install fastembed")
            raise
        except Exception as e:
            logger.error(f"Failed to load local embedding model: {e}")
            raise
    return _local_model


class EmbeddingService:
    """
    Generate text embeddings for vector storage.

    Supports:
    - Local via FastEmbed (BAAI/bge-small-en-v1.5, 384 dimensions)
    - OpenAI text-embedding-3-small (1536 dimensions)
    - Voyage AI voyage-2 (1024 dimensions)
    """

    def __init__(self, api_key: Optional[str] = None):
        """Initialize with optional API key override."""
        self.settings = get_settings()
        self._api_key = api_key
        self._client = httpx.AsyncClient(timeout=30.0)

    @property
    def api_key(self) -> Optional[str]:
        """Get API key from init or settings."""
        if self._api_key:
            return self._api_key
        if self.settings.embedding_provider == "openai":
            return self.settings.openai_api_key
        elif self.settings.embedding_provider == "voyage":
            return self.settings.voyage_api_key
        return None

    @property
    def provider(self) -> str:
        return self.settings.embedding_provider

    @property
    def dimensions(self) -> int:
        return self.settings.embedding_dimensions

    @property
    def is_local(self) -> bool:
        """Check if using local embeddings."""
        return self.provider == "local"

    async def embed(self, text: str) -> Optional[list[float]]:
        """
        Generate embedding for a single text.

        Returns:
            List of floats (embedding vector) or None if failed
        """
        # Local embeddings don't need API key
        if self.provider == "local":
            return await self._embed_local(text)

        if not self.api_key:
            logger.warning(f"No API key for embedding provider: {self.provider}")
            return None

        try:
            if self.provider == "openai":
                return await self._embed_openai(text)
            elif self.provider == "voyage":
                return await self._embed_voyage(text)
            else:
                logger.error(f"Unknown embedding provider: {self.provider}")
                return None
        except Exception as e:
            logger.exception(f"Embedding failed: {e}")
            return None

    async def embed_batch(self, texts: list[str]) -> list[Optional[list[float]]]:
        """
        Generate embeddings for multiple texts.

        Returns:
            List of embeddings (same order as input)
        """
        if not texts:
            return []

        # Local embeddings don't need API key
        if self.provider == "local":
            return await self._embed_local_batch(texts)

        if not self.api_key:
            return [None] * len(texts)

        try:
            if self.provider == "openai":
                return await self._embed_openai_batch(texts)
            elif self.provider == "voyage":
                return await self._embed_voyage_batch(texts)
            else:
                return [None] * len(texts)
        except Exception as e:
            logger.exception(f"Batch embedding failed: {e}")
            return [None] * len(texts)

    async def _embed_local(self, text: str) -> Optional[list[float]]:
        """Generate embedding using local FastEmbed model."""
        try:
            model = _get_local_model()
            # FastEmbed returns a generator, get first result
            embeddings = list(model.embed([text]))
            if embeddings:
                return embeddings[0].tolist()
            return None
        except Exception as e:
            logger.exception(f"Local embedding failed: {e}")
            return None

    async def _embed_local_batch(self, texts: list[str]) -> list[Optional[list[float]]]:
        """Generate embeddings for batch using local FastEmbed model."""
        try:
            model = _get_local_model()
            embeddings = list(model.embed(texts))
            return [e.tolist() for e in embeddings]
        except Exception as e:
            logger.exception(f"Local batch embedding failed: {e}")
            return [None] * len(texts)

    async def _embed_openai(self, text: str) -> Optional[list[float]]:
        """Generate embedding using OpenAI API."""
        response = await self._client.post(
            "https://api.openai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.settings.embedding_model,
                "input": text,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["data"][0]["embedding"]

    async def _embed_openai_batch(self, texts: list[str]) -> list[Optional[list[float]]]:
        """Generate embeddings for batch using OpenAI API."""
        response = await self._client.post(
            "https://api.openai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.settings.embedding_model,
                "input": texts,
            },
        )
        response.raise_for_status()
        data = response.json()
        # Sort by index to maintain order
        embeddings = sorted(data["data"], key=lambda x: x["index"])
        return [e["embedding"] for e in embeddings]

    async def _embed_voyage(self, text: str) -> Optional[list[float]]:
        """Generate embedding using Voyage AI API."""
        response = await self._client.post(
            "https://api.voyageai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "voyage-2",
                "input": text,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["data"][0]["embedding"]

    async def _embed_voyage_batch(self, texts: list[str]) -> list[Optional[list[float]]]:
        """Generate embeddings for batch using Voyage AI API."""
        response = await self._client.post(
            "https://api.voyageai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "voyage-2",
                "input": texts,
            },
        )
        response.raise_for_status()
        data = response.json()
        embeddings = sorted(data["data"], key=lambda x: x["index"])
        return [e["embedding"] for e in embeddings]

    async def close(self):
        """Close HTTP client."""
        await self._client.aclose()


# Singleton instance
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """Get or create embedding service singleton."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
