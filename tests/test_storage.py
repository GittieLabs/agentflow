"""Tests for storage backends."""
import pytest

from agentflow.storage.filesystem import FileSystemStorage
from agentflow.storage.memory_storage import InMemoryStorage


# ── InMemoryStorage ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_memory_storage_write_read():
    storage = InMemoryStorage()
    await storage.write("test.txt", "hello")
    assert await storage.read("test.txt") == "hello"


@pytest.mark.asyncio
async def test_memory_storage_missing():
    storage = InMemoryStorage()
    assert await storage.read("missing.txt") is None


@pytest.mark.asyncio
async def test_memory_storage_exists():
    storage = InMemoryStorage()
    assert not await storage.exists("test.txt")
    await storage.write("test.txt", "data")
    assert await storage.exists("test.txt")


@pytest.mark.asyncio
async def test_memory_storage_list():
    storage = InMemoryStorage()
    await storage.write("dir/a.txt", "a")
    await storage.write("dir/b.txt", "b")
    await storage.write("other/c.txt", "c")
    assert await storage.list("dir/") == ["dir/a.txt", "dir/b.txt"]


@pytest.mark.asyncio
async def test_memory_storage_delete():
    storage = InMemoryStorage()
    await storage.write("test.txt", "data")
    await storage.delete("test.txt")
    assert await storage.read("test.txt") is None


# ── FileSystemStorage ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fs_storage_write_read(tmp_path):
    storage = FileSystemStorage(tmp_path)
    await storage.write("subdir/test.txt", "hello world")
    assert await storage.read("subdir/test.txt") == "hello world"


@pytest.mark.asyncio
async def test_fs_storage_list(tmp_path):
    storage = FileSystemStorage(tmp_path)
    await storage.write("data/a.md", "a")
    await storage.write("data/b.md", "b")
    files = await storage.list("data")
    assert sorted(files) == ["data/a.md", "data/b.md"]


@pytest.mark.asyncio
async def test_fs_storage_delete(tmp_path):
    storage = FileSystemStorage(tmp_path)
    await storage.write("rm_me.txt", "bye")
    await storage.delete("rm_me.txt")
    assert not await storage.exists("rm_me.txt")
