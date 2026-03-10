"""Tests for memory: FileMemory and MemoryManager."""
import pytest

from agentflow.memory.file_memory import FileMemory
from agentflow.memory.manager import MemoryManager
from agentflow.storage.memory_storage import InMemoryStorage


# ── FileMemory ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_file_memory_store_and_search():
    storage = InMemoryStorage()
    mem = FileMemory(storage, agent="test")

    await mem.store("User prefers detailed weather forecasts.")
    await mem.store("User's favorite color is blue.")

    results = await mem.search("weather")
    assert len(results) == 1
    assert "weather forecasts" in results[0]["content"]


@pytest.mark.asyncio
async def test_file_memory_search_limit():
    storage = InMemoryStorage()
    mem = FileMemory(storage, agent="test")

    for i in range(10):
        await mem.store(f"Memory entry {i} about topic alpha.")

    results = await mem.search("alpha", limit=3)
    assert len(results) == 3


@pytest.mark.asyncio
async def test_file_memory_search_empty():
    storage = InMemoryStorage()
    mem = FileMemory(storage, agent="test")

    await mem.store("Something about cats.")
    results = await mem.search("dogs")
    assert len(results) == 0


@pytest.mark.asyncio
async def test_file_memory_with_metadata():
    storage = InMemoryStorage()
    mem = FileMemory(storage, agent="test")

    path = await mem.store(
        "Keith likes Philadelphia Eagles.",
        metadata={"tags": ["sports", "preferences"]},
    )
    assert "test_memories" in path

    results = await mem.search("Eagles")
    assert len(results) == 1
    assert "Philadelphia Eagles" in results[0]["content"]


@pytest.mark.asyncio
async def test_file_memory_list_and_delete():
    storage = InMemoryStorage()
    mem = FileMemory(storage, agent="test")

    path = await mem.store("Temporary memory.")
    entries = await mem.list_entries()
    assert len(entries) == 1

    await mem.delete(path)
    entries = await mem.list_entries()
    assert len(entries) == 0


@pytest.mark.asyncio
async def test_file_memory_extract_body():
    raw = """---
created_at: 2026-03-09T12:00:00Z
tags: [test]
---
This is the body content."""

    body = FileMemory._extract_body(raw)
    assert body == "This is the body content."
    assert "created_at" not in body


@pytest.mark.asyncio
async def test_file_memory_extract_body_no_frontmatter():
    body = FileMemory._extract_body("Just plain text.")
    assert body == "Just plain text."


# ── MemoryManager ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_memory_manager_remember_and_recall():
    storage = InMemoryStorage()
    mem = FileMemory(storage, agent="test")
    mgr = MemoryManager(long_term=mem)

    await mgr.remember("User prefers concise responses.")
    results = await mgr.recall("concise")
    assert len(results) == 1
    assert "concise responses" in results[0]["content"]


@pytest.mark.asyncio
async def test_memory_manager_no_store():
    mgr = MemoryManager()  # No long-term store
    result = await mgr.remember("This should be silently skipped.")
    assert result is None
    assert await mgr.recall("anything") == []


@pytest.mark.asyncio
async def test_memory_manager_recall_formatted():
    storage = InMemoryStorage()
    mem = FileMemory(storage, agent="test")
    mgr = MemoryManager(long_term=mem)

    await mgr.remember("User's timezone is EST.")
    await mgr.remember("User prefers dark mode.")

    formatted = await mgr.recall_formatted("timezone")
    assert "Relevant Memories" in formatted
    assert "EST" in formatted


@pytest.mark.asyncio
async def test_memory_manager_recall_formatted_empty():
    storage = InMemoryStorage()
    mem = FileMemory(storage, agent="test")
    mgr = MemoryManager(long_term=mem)

    formatted = await mgr.recall_formatted("nonexistent topic")
    assert formatted == ""
