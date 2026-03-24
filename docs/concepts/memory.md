# Memory

AgentFlow's memory system gives agents the ability to retain and recall information across sessions. It supports two backends: file-based memory for simple use cases and vector memory for semantic search at scale.

## Memory Architecture

```
MemoryManager
    |
    +-- FileMemory    (substring search, markdown files)
    |
    +-- VectorMemory  (semantic search, Qdrant + embeddings)
```

Both backends implement the `MemoryStore` protocol:

```python
class MemoryStore(Protocol):
    async def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]: ...
    async def store(self, content: str, metadata: dict[str, Any] | None = None) -> str: ...
```

## FileMemory

`FileMemory` stores each memory entry as an individual Markdown file with YAML front-matter metadata. It searches via substring matching.

**Best for**: Low-volume use, simple retrieval, development.

### Storage Format

Each entry is a timestamped file under `agents/<agent>_memories/`:

```
agents/researcher_memories/20260315_120000_000001.md
```

File contents:

```markdown
---
created_at: 2026-03-15T12:00:00+00:00
tags: [ai, safety, research]
---
User prefers research summaries with cited sources and
structured as bullet points. Focus on recent publications.
```

### Usage

```python
from agentflow import FileMemory, FileSystemStorage

storage = FileSystemStorage("./data")
memory = FileMemory(storage=storage, agent="researcher")

# Store a memory
path = await memory.store(
    content="User prefers bullet-point summaries with citations.",
    metadata={"tags": ["preferences", "formatting"]},
)

# Search memories (substring match)
results = await memory.search("bullet-point", limit=5)
for result in results:
    print(result["content"])
    print(result["score"])  # 1.0 for matches

# List all entries
entries = await memory.list_entries()

# Delete a specific entry
await memory.delete(path)
```

## VectorMemory

`VectorMemory` uses Qdrant for semantic vector search. It is embedding-agnostic -- you provide your own embedding function and dimension.

**Best for**: Large-scale semantic retrieval, production systems.

### Installation

```bash
pip install "gittielabs-agentflow[vector]"
```

This installs `qdrant-client`. You also need a running Qdrant instance (local or cloud).

### Usage

```python
from agentflow import VectorMemory

# Define your embedding function (any provider works)
async def embed(text: str) -> list[float]:
    # Use your preferred embedding API
    response = await embedding_client.embed(text)
    return response.embedding

memory = VectorMemory(
    collection_name="researcher_memories",
    embed_fn=embed,
    embedding_dim=768,  # Must match your embedding model's output
    qdrant_url="http://localhost:6333",
)

# Store with metadata
entry_id = await memory.store(
    content="User is interested in AI safety research, specifically alignment.",
    metadata={"tags": ["interest", "ai-safety"], "agent": "researcher"},
)

# Semantic search
results = await memory.search("alignment research", limit=5)
for result in results:
    print(result["content"])
    print(result["score"])  # Cosine similarity
```

### Embedding Agnostic Design

`VectorMemory` does not depend on any specific embedding provider. You supply:

- `embed_fn` -- an async function `str -> list[float]` that produces embeddings
- `embedding_dim` -- the vector dimension your function outputs

This means you can use any embedding API: OpenAI, Google, Cohere, local models, etc.

## MemoryManager

`MemoryManager` coordinates memory operations and provides a unified interface:

```python
from agentflow import MemoryManager

manager = MemoryManager(memory_store=memory)
```

## Memory Configuration

Memory behavior is configured per-agent via `*.memory.md` files:

```markdown
---
agent: researcher
retention: permanent
max_entries: 200
---

Memory configuration for the research agent.
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `agent` | `str` | *required* | Agent this config applies to |
| `retention` | `str` | `"permanent"` | `permanent`, `session`, or `ttl:7d` |
| `max_entries` | `int` | `100` | Maximum stored entries |

### Retention Policies

- **`permanent`** -- Entries persist indefinitely
- **`session`** -- Entries are scoped to the current session and cleared afterward
- **`ttl:7d`** -- Entries expire after the specified duration (e.g., 7 days)

## Events

Memory operations emit `MEMORY_STORED` events through the `EventBus`:

```python
from agentflow import EventBus

events = EventBus()

class MemoryLogger:
    async def on_event(self, event_type, data):
        print(f"Memory stored: {data}")

events.on("memory_stored", MemoryLogger())
```
