"""Tests for Phase 5: production backends and additional providers.

Tests mock the external SDKs (boto3, qdrant-client, openai, google-genai)
to verify the translation/conversion logic without real API calls.

Key mocking strategy:
- Optional dependencies may not be installed in the test environment
- We patch module-level references (e.g., agentflow.storage.s3.boto3)
- For exception classes, we use the module's own fallback reference
- For data classes (PointStruct, VectorParams), we mock them as callables
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from agentflow.types import AgentResponse, Message, Role, ToolCall, ToolResult


# ── Helpers ──────────────────────────────────────────────────────────────────


class FakeClientError(Exception):
    """Mimics botocore.exceptions.ClientError for tests without botocore installed."""

    def __init__(self, error_response: dict, operation_name: str):
        self.response = error_response
        super().__init__(f"{operation_name}: {error_response}")


# ── S3Storage ────────────────────────────────────────────────────────────────


class TestS3Storage:
    """Test S3Storage with mocked boto3 client."""

    def _make_storage(self):
        """Create S3Storage with a mocked boto3 client."""
        from agentflow.storage.s3 import S3Storage

        with (
            patch("agentflow.storage.s3.boto3") as mock_boto3,
            patch("agentflow.storage.s3.ClientError", FakeClientError),
        ):
            mock_client = MagicMock()
            mock_boto3.client.return_value = mock_client
            mock_client.head_bucket.return_value = {}

            storage = S3Storage(
                endpoint_url="https://test.storageapi.dev",
                access_key_id="test_key",
                secret_access_key="test_secret",
                bucket="test-bucket",
            )
            # Patch the module-level ClientError on the storage class too
            import agentflow.storage.s3 as s3_mod
            s3_mod.ClientError = FakeClientError

            return storage, mock_client

    @pytest.mark.asyncio
    async def test_read_existing_key(self):
        storage, mock_client = self._make_storage()
        mock_body = MagicMock()
        mock_body.read.return_value = b"hello world"
        mock_client.get_object.return_value = {"Body": mock_body}

        result = await storage.read("path/to/file.txt")
        assert result == "hello world"
        mock_client.get_object.assert_called_once_with(
            Bucket="test-bucket", Key="path/to/file.txt"
        )

    @pytest.mark.asyncio
    async def test_read_missing_key(self):
        storage, mock_client = self._make_storage()
        mock_client.get_object.side_effect = FakeClientError(
            {"Error": {"Code": "NoSuchKey"}}, "GetObject"
        )
        result = await storage.read("nonexistent.txt")
        assert result is None

    @pytest.mark.asyncio
    async def test_write(self):
        storage, mock_client = self._make_storage()
        await storage.write("data/output.txt", "content here")
        mock_client.put_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="data/output.txt",
            Body=b"content here",
            ContentType="text/plain; charset=utf-8",
        )

    @pytest.mark.asyncio
    async def test_exists_true(self):
        storage, mock_client = self._make_storage()
        mock_client.head_object.return_value = {}
        assert await storage.exists("some/key") is True

    @pytest.mark.asyncio
    async def test_exists_false(self):
        storage, mock_client = self._make_storage()
        mock_client.head_object.side_effect = FakeClientError(
            {"Error": {"Code": "404"}}, "HeadObject"
        )
        assert await storage.exists("missing/key") is False

    @pytest.mark.asyncio
    async def test_list_prefix(self):
        storage, mock_client = self._make_storage()
        mock_paginator = MagicMock()
        mock_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {"Contents": [{"Key": "data/a.txt"}, {"Key": "data/b.txt"}]},
            {"Contents": [{"Key": "data/c.txt"}]},
        ]

        result = await storage.list("data/")
        assert result == ["data/a.txt", "data/b.txt", "data/c.txt"]

    @pytest.mark.asyncio
    async def test_delete(self):
        storage, mock_client = self._make_storage()
        await storage.delete("path/to/remove.txt")
        mock_client.delete_object.assert_called_once_with(
            Bucket="test-bucket", Key="path/to/remove.txt"
        )

    def test_from_env(self):
        import os

        with (
            patch("agentflow.storage.s3.boto3") as mock_boto3,
            patch("agentflow.storage.s3.ClientError", FakeClientError),
            patch.dict(os.environ, {
                "S3_ENDPOINT": "https://t3.storageapi.dev",
                "S3_ACCESS_KEY_ID": "key123",
                "S3_SECRET_ACCESS_KEY": "secret456",
                "S3_BUCKET": "mybucket",
            }),
        ):
            mock_client = MagicMock()
            mock_boto3.client.return_value = mock_client
            mock_client.head_bucket.return_value = {}

            from agentflow.storage.s3 import S3Storage
            storage = S3Storage.from_env()
            assert storage._bucket == "mybucket"


# ── VectorMemory (backend-agnostic) ─────────────────────────────────────────


class TestVectorMemory:
    """Test VectorMemory with a mock VectorBackend — no Qdrant patching needed."""

    def _make_memory(self):
        from agentflow.memory.vector_memory import VectorMemory

        mock_embed = AsyncMock(return_value=[0.1] * 768)
        mock_backend = MagicMock()

        memory = VectorMemory(
            embed_fn=mock_embed,
            embedding_dim=768,
            backend=mock_backend,
            collection="agentflow_memories",
            agent="test_agent",
        )
        return memory, mock_backend, mock_embed

    @pytest.mark.asyncio
    async def test_store(self):
        memory, mock_backend, mock_embed = self._make_memory()

        point_id = await memory.store("Remember this fact.", metadata={"source": "test"})
        assert isinstance(point_id, str)
        assert len(point_id) == 36  # UUID format

        mock_embed.assert_called_once_with("Remember this fact.")
        mock_backend.upsert.assert_called_once()
        call_args = mock_backend.upsert.call_args
        assert call_args[0][0] == "agentflow_memories"  # collection
        assert call_args[0][1] == point_id  # point_id
        assert call_args[0][2] == [0.1] * 768  # vector
        payload = call_args[0][3]
        assert payload["content"] == "Remember this fact."
        assert payload["agent"] == "test_agent"
        assert payload["source"] == "test"

    @pytest.mark.asyncio
    async def test_search(self):
        memory, mock_backend, mock_embed = self._make_memory()

        mock_backend.query.return_value = [
            {
                "id": "point-123",
                "score": 0.95,
                "payload": {
                    "content": "User likes blue.",
                    "agent": "test_agent",
                    "created_at": "2026-03-09T00:00:00Z",
                },
            }
        ]

        results = await memory.search("favorite color", limit=3)
        assert len(results) == 1
        assert results[0]["content"] == "User likes blue."
        assert results[0]["score"] == 0.95
        assert results[0]["id"] == "point-123"

        mock_embed.assert_called_once_with("favorite color")
        mock_backend.query.assert_called_once_with(
            "agentflow_memories", [0.1] * 768, 3
        )

    @pytest.mark.asyncio
    async def test_delete(self):
        memory, mock_backend, _ = self._make_memory()
        await memory.delete("point-456")
        mock_backend.delete_points.assert_called_once_with(
            "agentflow_memories", ["point-456"]
        )

    def test_ensure_collection_called_on_init(self):
        from agentflow.memory.vector_memory import VectorMemory

        mock_backend = MagicMock()
        VectorMemory(
            embed_fn=AsyncMock(return_value=[0.1] * 768),
            embedding_dim=768,
            backend=mock_backend,
            collection="new_collection",
        )
        mock_backend.ensure_collection.assert_called_once_with("new_collection", 768)


# ── QdrantBackend ───────────────────────────────────────────────────────────


class TestQdrantBackend:
    """Test QdrantBackend with mocked qdrant-client."""

    def _make_backend(self):
        from agentflow.memory.backends.qdrant_backend import QdrantBackend

        with (
            patch("agentflow.memory.backends.qdrant_backend.QdrantClient") as MockQdrant,
        ):
            mock_qdrant = MagicMock()
            MockQdrant.return_value = mock_qdrant
            backend = QdrantBackend(url="http://localhost:6333")
            return backend, mock_qdrant

    def test_ensure_collection_creates_when_missing(self):
        from agentflow.memory.backends.qdrant_backend import QdrantBackend

        with (
            patch("agentflow.memory.backends.qdrant_backend.QdrantClient") as MockQdrant,
            patch("agentflow.memory.backends.qdrant_backend.VectorParams") as MockVP,
            patch("agentflow.memory.backends.qdrant_backend.Distance") as MockDist,
        ):
            mock_qdrant = MagicMock()
            MockQdrant.return_value = mock_qdrant
            backend = QdrantBackend(url="http://localhost:6333")

            mock_collections_resp = MagicMock()
            mock_collections_resp.collections = []
            mock_qdrant.get_collections.return_value = mock_collections_resp

            backend.ensure_collection("my_coll", 768)
            mock_qdrant.create_collection.assert_called_once()
            call_kwargs = mock_qdrant.create_collection.call_args.kwargs
            assert call_kwargs["collection_name"] == "my_coll"

    def test_ensure_collection_skips_when_exists(self):
        backend, mock_qdrant = self._make_backend()
        mock_coll = MagicMock()
        mock_coll.name = "my_coll"
        mock_collections_resp = MagicMock()
        mock_collections_resp.collections = [mock_coll]
        mock_qdrant.get_collections.return_value = mock_collections_resp
        mock_info = MagicMock()
        mock_info.config.params.vectors.size = 768
        mock_qdrant.get_collection.return_value = mock_info

        backend.ensure_collection("my_coll", 768)
        mock_qdrant.create_collection.assert_not_called()

    def test_upsert(self):
        from agentflow.memory.backends.qdrant_backend import QdrantBackend

        with (
            patch("agentflow.memory.backends.qdrant_backend.QdrantClient") as MockQdrant,
            patch("agentflow.memory.backends.qdrant_backend.PointStruct") as MockPS,
        ):
            mock_qdrant = MagicMock()
            MockQdrant.return_value = mock_qdrant
            backend = QdrantBackend(url="http://localhost:6333")

            backend.upsert("coll", "id-1", [0.1, 0.2], {"content": "hello"})
            mock_qdrant.upsert.assert_called_once()
            MockPS.assert_called_once_with(id="id-1", vector=[0.1, 0.2], payload={"content": "hello"})

    def test_query(self):
        backend, mock_qdrant = self._make_backend()
        mock_point = MagicMock()
        mock_point.id = "p-1"
        mock_point.score = 0.9
        mock_point.payload = {"content": "test"}
        mock_results = MagicMock()
        mock_results.points = [mock_point]
        mock_qdrant.query_points.return_value = mock_results

        results = backend.query("coll", [0.1], 5)
        assert len(results) == 1
        assert results[0]["id"] == "p-1"
        assert results[0]["score"] == 0.9
        assert results[0]["payload"] == {"content": "test"}

    def test_delete_points(self):
        backend, mock_qdrant = self._make_backend()
        backend.delete_points("coll", ["p-1", "p-2"])
        mock_qdrant.delete.assert_called_once_with(
            collection_name="coll", points_selector=["p-1", "p-2"]
        )


# ── LanceDBBackend ──────────────────────────────────────────────────────────


class TestLanceDBBackend:
    """Test LanceDBBackend with mocked lancedb."""

    def _make_backend(self):
        from agentflow.memory.backends.lancedb_backend import LanceDBBackend

        mock_db = MagicMock()
        with patch("agentflow.memory.backends.lancedb_backend._lancedb") as mock_lancedb:
            mock_lancedb.connect.return_value = mock_db
            backend = LanceDBBackend(path="/tmp/test-lance")
        backend._db = mock_db
        return backend, mock_db

    def test_ensure_collection_creates_when_missing(self):
        backend, mock_db = self._make_backend()
        mock_db.table_names.return_value = []
        mock_table = MagicMock()
        mock_db.create_table.return_value = mock_table

        with patch("agentflow.memory.backends.lancedb_backend.pa") as mock_pa:
            backend.ensure_collection("my_table", 768)

        mock_db.create_table.assert_called_once()
        assert backend._tables["my_table"] is mock_table

    def test_ensure_collection_opens_existing(self):
        backend, mock_db = self._make_backend()
        mock_db.table_names.return_value = ["my_table"]
        mock_table = MagicMock()
        mock_db.open_table.return_value = mock_table

        backend.ensure_collection("my_table", 768)
        mock_db.open_table.assert_called_once_with("my_table")
        assert backend._tables["my_table"] is mock_table

    def test_upsert(self):
        backend, mock_db = self._make_backend()
        mock_table = MagicMock()
        backend._tables["coll"] = mock_table

        backend.upsert("coll", "id-1", [0.1, 0.2], {"content": "hello"})
        mock_table.add.assert_called_once()
        row = mock_table.add.call_args[0][0][0]
        assert row["id"] == "id-1"
        assert row["vector"] == [0.1, 0.2]

    def test_query(self):
        import json
        backend, mock_db = self._make_backend()
        mock_table = MagicMock()
        backend._tables["coll"] = mock_table

        mock_table.search.return_value.limit.return_value.to_list.return_value = [
            {"id": "id-1", "vector": [0.1], "payload": json.dumps({"content": "test"}), "_distance": 0.1}
        ]

        results = backend.query("coll", [0.1], 5)
        assert len(results) == 1
        assert results[0]["id"] == "id-1"
        assert results[0]["score"] == pytest.approx(0.9)
        assert results[0]["payload"]["content"] == "test"

    def test_delete_points(self):
        backend, mock_db = self._make_backend()
        mock_table = MagicMock()
        backend._tables["coll"] = mock_table

        backend.delete_points("coll", ["id-1", "id-2"])
        mock_table.delete.assert_called_once_with("id IN ('id-1', 'id-2')")


# ── ChromaBackend ───────────────────────────────────────────────────────────


class TestChromaBackend:
    """Test ChromaBackend with mocked chromadb."""

    def _make_backend(self):
        from agentflow.memory.backends.chroma_backend import ChromaBackend

        mock_client = MagicMock()
        with patch("agentflow.memory.backends.chroma_backend._chromadb") as mock_chromadb:
            mock_chromadb.PersistentClient.return_value = mock_client
            backend = ChromaBackend(path="/tmp/test-chroma")
        backend._client = mock_client
        return backend, mock_client

    def test_ensure_collection(self):
        backend, mock_client = self._make_backend()
        mock_coll = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_coll

        backend.ensure_collection("my_coll", 768)
        mock_client.get_or_create_collection.assert_called_once_with(
            name="my_coll", metadata={"hnsw:space": "cosine"}
        )
        assert backend._collections["my_coll"] is mock_coll

    def test_upsert(self):
        backend, mock_client = self._make_backend()
        mock_coll = MagicMock()
        backend._collections["coll"] = mock_coll

        backend.upsert("coll", "id-1", [0.1, 0.2], {"content": "hello", "agent": "test"})
        mock_coll.upsert.assert_called_once_with(
            ids=["id-1"],
            embeddings=[[0.1, 0.2]],
            documents=["hello"],
            metadatas=[{"content": "hello", "agent": "test"}],
        )

    def test_query(self):
        backend, mock_client = self._make_backend()
        mock_coll = MagicMock()
        backend._collections["coll"] = mock_coll

        mock_coll.query.return_value = {
            "ids": [["id-1"]],
            "metadatas": [[{"content": "test", "agent": "a"}]],
            "distances": [[0.15]],
        }

        results = backend.query("coll", [0.1], 5)
        assert len(results) == 1
        assert results[0]["id"] == "id-1"
        assert results[0]["score"] == pytest.approx(0.85)
        assert results[0]["payload"]["content"] == "test"

    def test_delete_points(self):
        backend, mock_client = self._make_backend()
        mock_coll = MagicMock()
        backend._collections["coll"] = mock_coll

        backend.delete_points("coll", ["id-1", "id-2"])
        mock_coll.delete.assert_called_once_with(ids=["id-1", "id-2"])


# ── OpenAICompatProvider ─────────────────────────────────────────────────────


class TestOpenAICompatProvider:
    """Test OpenAI-compatible provider message/tool translation."""

    def _make_provider(self):
        from agentflow.providers.openai_compat import OpenAICompatProvider

        with patch("agentflow.providers.openai_compat.openai") as mock_openai_mod:
            mock_client = AsyncMock()
            mock_openai_mod.AsyncOpenAI.return_value = mock_client
            provider = OpenAICompatProvider(
                api_key="test-key",
                model="gpt-4o",
                base_url="https://api.openai.com/v1",
            )
            return provider, mock_client

    def test_to_api_messages_basic(self):
        provider, _ = self._make_provider()
        messages = [
            Message(role=Role.USER, content="Hello"),
            Message(role=Role.ASSISTANT, content="Hi there"),
        ]
        result = provider._to_api_messages(messages, system="You are helpful.")
        assert result[0] == {"role": "system", "content": "You are helpful."}
        assert result[1] == {"role": "user", "content": "Hello"}
        assert result[2] == {"role": "assistant", "content": "Hi there"}

    def test_to_api_messages_tool_result(self):
        provider, _ = self._make_provider()
        messages = [
            Message(
                role=Role.TOOL_RESULT,
                content="",
                tool_results=[
                    ToolResult(tool_call_id="call_123", content="Search result here"),
                ],
            ),
        ]
        result = provider._to_api_messages(messages, system="")
        assert result[0]["role"] == "tool"
        assert result[0]["tool_call_id"] == "call_123"
        assert result[0]["content"] == "Search result here"

    def test_to_api_messages_with_tool_calls(self):
        provider, _ = self._make_provider()
        messages = [
            Message(
                role=Role.ASSISTANT,
                content="Let me search.",
                tool_calls=[
                    ToolCall(id="call_abc", name="web_search", input={"query": "test"}),
                ],
            ),
        ]
        result = provider._to_api_messages(messages, system="")
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == "Let me search."
        assert len(result[0]["tool_calls"]) == 1
        tc = result[0]["tool_calls"][0]
        assert tc["id"] == "call_abc"
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "web_search"
        assert json.loads(tc["function"]["arguments"]) == {"query": "test"}

    def test_to_api_tools(self):
        provider, _ = self._make_provider()
        tools = [
            {
                "name": "web_search",
                "description": "Search the web",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                },
            }
        ]
        result = provider._to_api_tools(tools)
        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "web_search"

    def test_from_api_response_text(self):
        provider, _ = self._make_provider()

        mock_msg = MagicMock()
        mock_msg.content = "Hello!"
        mock_msg.tool_calls = None

        mock_choice = MagicMock()
        mock_choice.message = mock_msg
        mock_choice.finish_reason = "stop"

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 10
        mock_usage.completion_tokens = 5

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        result = provider._from_api_response(mock_response)
        assert isinstance(result, AgentResponse)
        assert result.text == "Hello!"
        assert result.tool_calls == []
        assert result.stop_reason == "end_turn"
        assert result.usage == {"input_tokens": 10, "output_tokens": 5}

    def test_from_api_response_tool_calls(self):
        provider, _ = self._make_provider()

        mock_tc = MagicMock()
        mock_tc.id = "call_xyz"
        mock_tc.function.name = "web_search"
        mock_tc.function.arguments = '{"query": "python"}'

        mock_msg = MagicMock()
        mock_msg.content = None
        mock_msg.tool_calls = [mock_tc]

        mock_choice = MagicMock()
        mock_choice.message = mock_msg
        mock_choice.finish_reason = "tool_calls"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = None

        result = provider._from_api_response(mock_response)
        assert result.text == ""
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "web_search"
        assert result.tool_calls[0].input == {"query": "python"}
        assert result.stop_reason == "tool_use"

    @pytest.mark.asyncio
    async def test_chat_integration(self):
        """End-to-end: chat() should translate messages, call API, translate response."""
        provider, mock_client = self._make_provider()

        mock_tc = MagicMock()
        mock_tc.id = "call_1"
        mock_tc.function.name = "search"
        mock_tc.function.arguments = '{"q": "hello"}'

        mock_msg = MagicMock()
        mock_msg.content = "Searching..."
        mock_msg.tool_calls = [mock_tc]

        mock_choice = MagicMock()
        mock_choice.message = mock_msg
        mock_choice.finish_reason = "tool_calls"

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 50
        mock_usage.completion_tokens = 20

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        messages = [Message(role=Role.USER, content="Search for hello")]
        result = await provider.chat(messages, system="Helper", tools=[
            {"name": "search", "description": "Search", "input_schema": {}}
        ])

        assert result.text == "Searching..."
        assert len(result.tool_calls) == 1
        assert result.stop_reason == "tool_use"


# ── GoogleGenAIProvider ──────────────────────────────────────────────────────


class TestGoogleGenAIProvider:
    """Test Google GenAI provider message/tool translation."""

    def _make_provider(self):
        from agentflow.providers.google_genai import GoogleGenAIProvider

        # Must mock both genai and genai_types since both are module-level
        with (
            patch("agentflow.providers.google_genai.genai") as mock_genai,
            patch("agentflow.providers.google_genai.genai_types") as mock_genai_types,
        ):
            mock_client = MagicMock()
            mock_genai.Client.return_value = mock_client
            provider = GoogleGenAIProvider(
                api_key="test-key",
                model="gemini-2.5-flash-preview",
            )
            return provider, mock_client, mock_genai, mock_genai_types

    def test_to_api_contents_user(self):
        provider, _, _, _ = self._make_provider()
        messages = [Message(role=Role.USER, content="Hello Gemini")]
        result = provider._to_api_contents(messages)
        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert result[0]["parts"] == [{"text": "Hello Gemini"}]

    def test_to_api_contents_assistant(self):
        provider, _, _, _ = self._make_provider()
        messages = [Message(role=Role.ASSISTANT, content="Hi there")]
        result = provider._to_api_contents(messages)
        assert len(result) == 1
        assert result[0]["role"] == "model"  # Gemini uses "model" not "assistant"
        assert result[0]["parts"] == [{"text": "Hi there"}]

    def test_to_api_contents_tool_result(self):
        provider, _, _, _ = self._make_provider()
        messages = [
            Message(
                role=Role.TOOL_RESULT,
                content="",
                tool_results=[
                    ToolResult(tool_call_id="web_search", content="Search result"),
                ],
            ),
        ]
        result = provider._to_api_contents(messages)
        assert len(result) == 1
        assert result[0]["role"] == "user"
        part = result[0]["parts"][0]
        assert "function_response" in part
        assert part["function_response"]["name"] == "web_search"
        assert part["function_response"]["response"] == {"result": "Search result"}

    def test_to_api_contents_assistant_with_tool_calls(self):
        provider, _, _, _ = self._make_provider()
        messages = [
            Message(
                role=Role.ASSISTANT,
                content="Let me search.",
                tool_calls=[
                    ToolCall(id="web_search", name="web_search", input={"query": "test"}),
                ],
            ),
        ]
        result = provider._to_api_contents(messages)
        assert len(result) == 1
        parts = result[0]["parts"]
        assert len(parts) == 2  # text + function_call
        assert parts[0] == {"text": "Let me search."}
        assert parts[1]["function_call"]["name"] == "web_search"
        assert parts[1]["function_call"]["args"] == {"query": "test"}

    def test_to_api_contents_skips_system(self):
        provider, _, _, _ = self._make_provider()
        messages = [
            Message(role=Role.SYSTEM, content="System prompt"),
            Message(role=Role.USER, content="Hello"),
        ]
        result = provider._to_api_contents(messages)
        assert len(result) == 1  # Only user, system skipped
        assert result[0]["role"] == "user"

    def test_to_api_tools(self):
        provider, _, _, _ = self._make_provider()
        tools = [
            {
                "name": "web_search",
                "description": "Search the web",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                },
            }
        ]
        result = provider._to_api_tools(tools)
        assert "function_declarations" in result
        decls = result["function_declarations"]
        assert len(decls) == 1
        assert decls[0]["name"] == "web_search"
        assert decls[0]["description"] == "Search the web"
        assert "parameters" in decls[0]

    def test_from_api_response_text(self):
        provider, _, _, _ = self._make_provider()

        mock_part = MagicMock()
        mock_part.text = "Hello from Gemini!"
        mock_part.function_call = None

        mock_content = MagicMock()
        mock_content.parts = [mock_part]

        mock_candidate = MagicMock()
        mock_candidate.content = mock_content

        mock_usage = MagicMock()
        mock_usage.prompt_token_count = 15
        mock_usage.candidates_token_count = 8

        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]
        mock_response.usage_metadata = mock_usage

        result = provider._from_api_response(mock_response)
        assert isinstance(result, AgentResponse)
        assert result.text == "Hello from Gemini!"
        assert result.tool_calls == []
        assert result.stop_reason == "end_turn"
        assert result.usage == {"input_tokens": 15, "output_tokens": 8}

    def test_from_api_response_function_call(self):
        provider, _, _, _ = self._make_provider()

        mock_fc = MagicMock()
        mock_fc.name = "web_search"
        mock_fc.args = {"query": "python docs"}

        mock_part = MagicMock()
        mock_part.text = None
        mock_part.function_call = mock_fc
        type(mock_part).text = PropertyMock(return_value=None)

        mock_content = MagicMock()
        mock_content.parts = [mock_part]

        mock_candidate = MagicMock()
        mock_candidate.content = mock_content

        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]
        mock_response.usage_metadata = None

        result = provider._from_api_response(mock_response)
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "web_search"
        assert result.tool_calls[0].input == {"query": "python docs"}
        assert result.stop_reason == "tool_use"

    def test_from_api_response_empty(self):
        provider, _, _, _ = self._make_provider()

        mock_response = MagicMock()
        mock_response.candidates = []
        mock_response.usage_metadata = None

        result = provider._from_api_response(mock_response)
        assert result.text == ""
        assert result.tool_calls == []
        assert result.stop_reason == "end_turn"

    @pytest.mark.asyncio
    async def test_chat_integration(self):
        """End-to-end: chat() translates messages and returns AgentResponse."""
        from agentflow.providers.google_genai import GoogleGenAIProvider

        with (
            patch("agentflow.providers.google_genai.genai") as mock_genai,
            patch("agentflow.providers.google_genai.genai_types") as mock_genai_types,
        ):
            mock_client = MagicMock()
            mock_genai.Client.return_value = mock_client
            provider = GoogleGenAIProvider(api_key="test-key", model="gemini-2.5-flash-preview")

            # Mock API response
            mock_part = MagicMock()
            mock_part.text = "Gemini response"
            mock_part.function_call = None

            mock_content = MagicMock()
            mock_content.parts = [mock_part]

            mock_candidate = MagicMock()
            mock_candidate.content = mock_content

            mock_usage = MagicMock()
            mock_usage.prompt_token_count = 20
            mock_usage.candidates_token_count = 10

            mock_response = MagicMock()
            mock_response.candidates = [mock_candidate]
            mock_response.usage_metadata = mock_usage

            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

            messages = [Message(role=Role.USER, content="Hello")]
            result = await provider.chat(messages, system="Be helpful", max_tokens=1024)

            assert result.text == "Gemini response"
            assert result.stop_reason == "end_turn"
            mock_client.aio.models.generate_content.assert_called_once()

    def test_to_api_contents_multi_turn(self):
        """Test a realistic multi-turn conversation with tool use."""
        provider, _, _, _ = self._make_provider()
        messages = [
            Message(role=Role.USER, content="Search for Python tutorials"),
            Message(
                role=Role.ASSISTANT,
                content="",
                tool_calls=[
                    ToolCall(id="web_search", name="web_search", input={"query": "Python tutorials"}),
                ],
            ),
            Message(
                role=Role.TOOL_RESULT,
                content="",
                tool_results=[
                    ToolResult(tool_call_id="web_search", content="Found 10 tutorials"),
                ],
            ),
            Message(role=Role.ASSISTANT, content="I found 10 Python tutorials for you."),
        ]
        result = provider._to_api_contents(messages)
        assert len(result) == 4
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "model"
        assert result[2]["role"] == "user"  # Tool results go as user
        assert result[3]["role"] == "model"
