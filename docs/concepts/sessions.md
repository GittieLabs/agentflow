# Sessions & Scratchpads

AgentFlow provides a session system for managing conversation state, per-node working memory, artifact storage, and multi-user history.

## Sessions

A `Session` represents a single conversation or task execution. It tracks messages, metadata, and provides access to scratchpads and artifacts.

```python
from agentflow import SessionManager, FileSystemStorage

storage = FileSystemStorage("./data")
sessions = SessionManager(storage)

# Create or retrieve a session
session = await sessions.get_or_create("session-123")
```

## SessionManager

`SessionManager` handles session lifecycle:

```python
from agentflow import SessionManager, FileSystemStorage

storage = FileSystemStorage("./data")
sessions = SessionManager(storage)

# Get or create
session = await sessions.get_or_create("my-session")

# Sessions are backed by the storage backend
# Data persists across restarts when using FileSystemStorage or S3Storage
```

## Scratchpads

Each node in a workflow gets two files managed by the `Scratchpad`:

- **`*_scratch.md`** -- Working notes the agent reads and writes during execution
- **`*_summary.md`** -- A distilled summary written at the end of the node

Downstream agents automatically receive upstream summaries as part of their context, enabling information flow between nodes without passing raw outputs.

### File Convention

```
sessions/<session_id>/<workflow>/<node_id>_scratch.md
sessions/<session_id>/<workflow>/<node_id>_summary.md
```

### Using Scratchpads

```python
from agentflow import Scratchpad, FileSystemStorage

storage = FileSystemStorage("./data")

pad = Scratchpad(
    storage=storage,
    session_id="session-123",
    node_id="research",
    workflow="research_pipeline",
)

# Write working notes
await pad.write_scratch("Found 3 relevant papers on AI safety...")

# Append to existing notes
await pad.append_scratch("Paper #4: Constitutional AI approach")

# Read back
notes = await pad.read_scratch()

# Write summary (typically done at end of node execution)
await pad.write_summary("Summarized 4 key papers on AI safety approaches.")

# Read summary (downstream nodes use this)
summary = await pad.read_summary()
```

### How Scratchpads Connect Nodes

The `ContextAssembler` automatically loads summary files from upstream nodes and injects them into the downstream agent's context. This means:

1. Node A runs and writes a summary
2. Node B's system prompt includes Node A's summary
3. Node B has context from Node A without receiving the full raw output

## ArtifactStore

`ArtifactStore` manages named artifacts (files, structured data, JSON blobs, etc.) produced during agent execution. While `Scratchpads` are designed explicitly for unstructured "thinking notes" sent back to the LLM context, `ArtifactStore` is geared towards persistent structured data and raw files.

```python
from agentflow import ArtifactStore, FileSystemStorage

storage = FileSystemStorage("./data")
artifacts = ArtifactStore(storage=storage, session_id="session-123")

# Store a structured JSON artifact
await artifacts.write_json("extracted_resume_data", {"name": "Jane", "skills": ["Python"]})

# Store a raw file artifact
await artifacts.write_binary("original_document.pdf", pdf_bytes)
```

Artifacts are referenced in `NodeOutput.artifacts` and can be passed between nodes via input mappings (such as loops using the `foreach` keyword).

### When to use Artifacts vs Scratchpads?

1. **Structured Data Sharing:** Use artifacts when a node outputs highly structured data (like JSON or lists) that must be iterated over by a downstream `foreach` node, or digested by an API. Use scratchpads when you just want downstream agents to read conversational summaries.
2. **File Persistence:** Artifacts should be used to persist binary files, pdfs, images, or exportable final reports (like DOCX files).
3. **Preventing Context Window Bloat:** If a tool output is 1MB of raw JSON data, injecting that into a scratchpad will bloat the LLM context and likely cause token limit errors. Save it as an artifact and only provide the LLM with the artifact's metadata or subset.

## Multi-User History

`MultiUserHistory` keeps conversation histories separate per user while sharing the same agent infrastructure:

```python
from agentflow import MultiUserHistory, FileSystemStorage

storage = FileSystemStorage("./data")
history = MultiUserHistory(storage=storage)
```

### HistoryPersistence

`HistoryPersistence` handles reading and writing conversation history to the storage backend:

```python
from agentflow import HistoryPersistence, FileSystemStorage

storage = FileSystemStorage("./data")
persistence = HistoryPersistence(storage=storage)
```

## Storage Backends

Sessions, scratchpads, and artifacts all use the `StorageBackend` protocol. AgentFlow includes three implementations:

| Backend | Use Case | Install |
|---------|----------|---------|
| `FileSystemStorage` | Local development, single-server | Core |
| `InMemoryStorage` | Testing, ephemeral data | Core |
| `S3Storage` | Production, distributed systems | `pip install "gittielabs-agentflow[s3]"` |

```python
from agentflow import FileSystemStorage, InMemoryStorage, S3Storage

# Local filesystem
storage = FileSystemStorage("./data")

# In-memory (lost on restart)
storage = InMemoryStorage()

# S3
storage = S3Storage(bucket="my-agentflow-data", prefix="sessions/")
```

All three implement the same protocol:

```python
class StorageBackend(Protocol):
    async def read(self, path: str) -> str | None: ...
    async def write(self, path: str, content: str) -> None: ...
    async def exists(self, path: str) -> bool: ...
    async def list(self, prefix: str) -> list[str]: ...
    async def delete(self, path: str) -> None: ...
```
