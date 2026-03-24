"""
Vector memory backend using Qdrant.

Implements the MemoryStore protocol with semantic search powered by
vector embeddings. Supports any embedding function — default is
Google Gemini gemini-embedding-001.

Requires:
    pip install agentflow[vector]
    QDRANT_URL and optionally QDRANT_API_KEY environment variables
    GEMINI_API_KEY for the default Gemini embedding function
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

logger = logging.getLogger("agentflow.memory.vector")

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance,
        PointStruct,
        VectorParams,
    )
except ImportError:
    QdrantClient = None  # type: ignore[assignment,misc]
    PointStruct = None  # type: ignore[assignment,misc]
    VectorParams = None  # type: ignore[assignment,misc]
    Distance = None  # type: ignore[assignment,misc]

# Type for an async embedding function: text -> vector
EmbedFn = Callable[[str], Awaitable[list[float]]]

# Gemini gemini-embedding-001 produces 3072-dimensional vectors
GEMINI_EMBEDDING_DIM = 3072


async def gemini_embed(text: str, api_key: str | None = None) -> list[float]:
    """
    Embed text using Google Gemini gemini-embedding-001.

    Uses httpx directly to avoid hard dependency on google-genai SDK.
    """
    import os
    import httpx

    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ValueError("GEMINI_API_KEY not set")

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            url,
            params={"key": key},
            json={"content": {"parts": [{"text": text}]}},
        )
        resp.raise_for_status()
        data = resp.json()
        return data["embedding"]["values"]


def make_gemini_embed_fn(api_key: str | None = None) -> EmbedFn:
    """Create a Gemini embedding function with a fixed API key."""
    async def embed(text: str) -> list[float]:
        return await gemini_embed(text, api_key=api_key)
    return embed


class VectorMemory:
    """
    MemoryStore implementation using Qdrant for semantic vector search.

    Stores text with embeddings for semantic retrieval. Each memory entry
    is a Qdrant point with:
    - vector: embedding of the content text
    - payload: {content, created_at, agent, ...metadata}
    """

    def __init__(
        self,
        qdrant_url: str = "http://localhost:6333",
        api_key: str | None = None,
        collection: str = "agentflow_memories",
        embed_fn: EmbedFn | None = None,
        embedding_dim: int = GEMINI_EMBEDDING_DIM,
        agent: str = "default",
    ) -> None:
        if QdrantClient is None:
            raise ImportError("Install qdrant-client: pip install agentflow[vector]")

        # Strip trailing slashes and protocol-less URLs
        if not qdrant_url.startswith("http"):
            qdrant_url = f"http://{qdrant_url}"

        self._client = QdrantClient(url=qdrant_url, api_key=api_key)
        self._collection = collection
        self._embed_fn = embed_fn or make_gemini_embed_fn()
        self._embedding_dim = embedding_dim
        self._agent = agent

        # Ensure collection exists
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        """Create the Qdrant collection if it doesn't exist, or recreate if dimension changed."""
        collections = [c.name for c in self._client.get_collections().collections]
        if self._collection in collections:
            # Check if existing collection has the right vector dimension
            info = self._client.get_collection(self._collection)
            existing_dim = info.config.params.vectors.size  # type: ignore[union-attr]
            if existing_dim != self._embedding_dim:
                logger.warning(
                    "Qdrant collection '%s' has dim=%d but expected dim=%d — recreating",
                    self._collection, existing_dim, self._embedding_dim,
                )
                self._client.delete_collection(self._collection)
            else:
                return  # collection exists with correct dimensions
        logger.info("Creating Qdrant collection: %s (dim=%d)", self._collection, self._embedding_dim)
        self._client.create_collection(
            collection_name=self._collection,
            vectors_config=VectorParams(
                size=self._embedding_dim,
                distance=Distance.COSINE,
            ),
        )

    async def store(self, content: str, metadata: dict[str, Any] | None = None) -> str:
        """
        Store a memory with its embedding.

        Returns the point ID as a string.
        """
        vector = await self._embed_fn(content)
        point_id = str(uuid.uuid4())

        payload = {
            "content": content,
            "agent": self._agent,
            "created_at": datetime.now(timezone.utc).isoformat(),
            **(metadata or {}),
        }

        self._client.upsert(
            collection_name=self._collection,
            points=[PointStruct(id=point_id, vector=vector, payload=payload)],
        )

        logger.debug("Stored vector memory: %s (agent=%s)", point_id, self._agent)
        return point_id

    async def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """
        Search memories by semantic similarity.

        Returns list of dicts with 'content', 'id', 'score', and any stored metadata.
        """
        query_vector = await self._embed_fn(query)

        results = self._client.query_points(
            collection_name=self._collection,
            query=query_vector,
            limit=limit,
            with_payload=True,
        )

        return [
            {
                "content": point.payload.get("content", ""),
                "id": str(point.id),
                "score": point.score,
                **{k: v for k, v in point.payload.items() if k != "content"},
            }
            for point in results.points
        ]

    async def delete(self, point_id: str) -> None:
        """Delete a specific memory by point ID."""
        self._client.delete(
            collection_name=self._collection,
            points_selector=[point_id],
        )

    @classmethod
    def from_env(cls, embed_fn: EmbedFn | None = None, agent: str = "default") -> VectorMemory:
        """Create from environment variables (QDRANT_URL, QDRANT_API_KEY, GEMINI_API_KEY)."""
        import os

        return cls(
            qdrant_url=os.environ.get("QDRANT_URL", "http://localhost:6333"),
            api_key=os.environ.get("QDRANT_API_KEY"),
            embed_fn=embed_fn or make_gemini_embed_fn(os.environ.get("GEMINI_API_KEY")),
            agent=agent,
        )
