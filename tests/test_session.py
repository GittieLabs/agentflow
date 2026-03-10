"""Tests for session management: SessionManager, Scratchpad, ArtifactStore."""
import json
import pytest

from agentflow.session.manager import Session, SessionManager
from agentflow.session.scratchpad import Scratchpad
from agentflow.session.artifacts import ArtifactStore
from agentflow.storage.memory_storage import InMemoryStorage


# ── SessionManager ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_session_create():
    storage = InMemoryStorage()
    mgr = SessionManager(storage)
    session = await mgr.create(agent="test_agent", workflow="pipeline")

    assert session.id  # UUID should be set
    assert session.agent == "test_agent"
    assert session.workflow == "pipeline"
    assert session.status == "active"
    assert session.created_at  # timestamp should be set


@pytest.mark.asyncio
async def test_session_get():
    storage = InMemoryStorage()
    mgr = SessionManager(storage)
    created = await mgr.create(agent="test")

    loaded = await mgr.get(created.id)
    assert loaded is not None
    assert loaded.id == created.id
    assert loaded.agent == "test"


@pytest.mark.asyncio
async def test_session_get_missing():
    storage = InMemoryStorage()
    mgr = SessionManager(storage)
    assert await mgr.get("nonexistent-id") is None


@pytest.mark.asyncio
async def test_session_update_status():
    storage = InMemoryStorage()
    mgr = SessionManager(storage)
    session = await mgr.create()

    await mgr.update_status(session.id, "completed")
    loaded = await mgr.get(session.id)
    assert loaded.status == "completed"


@pytest.mark.asyncio
async def test_session_list():
    storage = InMemoryStorage()
    mgr = SessionManager(storage)
    s1 = await mgr.create()
    s2 = await mgr.create()

    ids = await mgr.list_sessions()
    assert s1.id in ids
    assert s2.id in ids


@pytest.mark.asyncio
async def test_session_metadata():
    storage = InMemoryStorage()
    mgr = SessionManager(storage)
    session = await mgr.create(metadata={"channel": "signal", "user": "keith"})

    loaded = await mgr.get(session.id)
    assert loaded.metadata["channel"] == "signal"
    assert loaded.metadata["user"] == "keith"


@pytest.mark.asyncio
async def test_session_to_from_dict():
    session = Session(
        id="abc-123",
        created_at="2026-03-09T00:00:00Z",
        agent="test",
        status="active",
    )
    d = session.to_dict()
    restored = Session.from_dict(d)
    assert restored.id == "abc-123"
    assert restored.agent == "test"


# ── Scratchpad ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scratchpad_write_read():
    storage = InMemoryStorage()
    pad = Scratchpad(storage, session_id="sess1", node_id="research")

    await pad.write_scratch("## Research notes\nFound relevant data.")
    content = await pad.read_scratch()
    assert "Research notes" in content
    assert "relevant data" in content


@pytest.mark.asyncio
async def test_scratchpad_append():
    storage = InMemoryStorage()
    pad = Scratchpad(storage, session_id="sess1", node_id="research")

    await pad.write_scratch("Note 1")
    await pad.append_scratch("Note 2")
    content = await pad.read_scratch()
    assert "Note 1" in content
    assert "Note 2" in content


@pytest.mark.asyncio
async def test_scratchpad_summary():
    storage = InMemoryStorage()
    pad = Scratchpad(storage, session_id="sess1", node_id="research")

    await pad.write_summary("Research found 3 relevant sources.")
    summary = await pad.read_summary()
    assert "3 relevant sources" in summary


@pytest.mark.asyncio
async def test_scratchpad_paths():
    storage = InMemoryStorage()
    pad = Scratchpad(storage, session_id="sess1", node_id="qualify", workflow="leadgen")

    assert pad.scratch_path == "sessions/sess1/leadgen/qualify_scratch.md"
    assert pad.summary_path == "sessions/sess1/leadgen/qualify_summary.md"


@pytest.mark.asyncio
async def test_scratchpad_empty_read():
    storage = InMemoryStorage()
    pad = Scratchpad(storage, session_id="sess1", node_id="missing")

    assert await pad.read_scratch() is None
    assert await pad.read_summary() is None


# ── ArtifactStore ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_artifact_store_text():
    storage = InMemoryStorage()
    artifacts = ArtifactStore(storage, session_id="sess1")

    path = await artifacts.store("report.md", "# Report\nAll good.")
    assert "artifacts/report.md" in path

    content = await artifacts.load("report.md")
    assert "All good" in content


@pytest.mark.asyncio
async def test_artifact_store_json():
    storage = InMemoryStorage()
    artifacts = ArtifactStore(storage, session_id="sess1")

    data = {"leads": [{"name": "Acme", "score": 0.9}]}
    await artifacts.store_json("leads.json", data)

    loaded = await artifacts.load_json("leads.json")
    assert loaded["leads"][0]["name"] == "Acme"
    assert loaded["leads"][0]["score"] == 0.9


@pytest.mark.asyncio
async def test_artifact_exists_and_delete():
    storage = InMemoryStorage()
    artifacts = ArtifactStore(storage, session_id="sess1")

    await artifacts.store("temp.txt", "temporary")
    assert await artifacts.exists("temp.txt")

    await artifacts.delete("temp.txt")
    assert not await artifacts.exists("temp.txt")


@pytest.mark.asyncio
async def test_artifact_list():
    storage = InMemoryStorage()
    artifacts = ArtifactStore(storage, session_id="sess1")

    await artifacts.store("a.txt", "a")
    await artifacts.store("b.txt", "b")

    names = await artifacts.list_artifacts()
    assert sorted(names) == ["a.txt", "b.txt"]


@pytest.mark.asyncio
async def test_artifact_load_missing():
    storage = InMemoryStorage()
    artifacts = ArtifactStore(storage, session_id="sess1")
    assert await artifacts.load("nope.txt") is None
    assert await artifacts.load_json("nope.json") is None
