# AgentFlow

Context engineering framework for multi-agent systems.

A framework-agnostic toolkit for building multi-agent workflows with:
- **Markdown + YAML front-matter config files** (`.prompt.md`, `.workflow.md`, `.context.md`)
- **Pluggable LLM providers** (Anthropic Claude, OpenAI GPT, Google Gemini, any OpenAI-compatible API)
- **Hybrid routing** (YAML rules + LLM fallback)
- **DAG-based workflow execution** (sync, parallel, async nodes)
- **Session scratchpads** and long-term memory (file-based + vector search)
- **Tool registry** with local and HTTP dispatchers

## Install

```bash
# Core only
pip install -e .

# With Claude support
pip install -e ".[anthropic]"

# With Google Gemini support
pip install -e ".[google]"

# Everything
pip install -e ".[all]"

# Development
pip install -e ".[dev]"
```

## Quick Start

### 1. Define an agent (`context/agents/researcher.prompt.md`)

```markdown
---
name: researcher
provider: anthropic
model: claude-sonnet-4-6
temperature: 0.7
max_tokens: 4096
tools: [web_search, summarize]
context_files: [shared/guidelines.context.md]
---

You are a research agent. Given a topic, search for relevant information
and provide a comprehensive summary with sources.
```

### 2. Define a workflow (`context/workflows/research.workflow.md`)

```markdown
---
name: research_pipeline
trigger: api
nodes:
  - id: research
    agent: researcher
    next: format
  - id: format
    agent: formatter
    inputs:
      message: "research.text"
---

Research pipeline: search, then format results.
```

### 3. Define routing rules (`context/router.prompt.md`)

```markdown
---
name: main_router
routing_rules:
  - if: "'research' in message or 'find' in message"
    routeTo: research_pipeline
  - if: "'analyze' in message"
    routeTo: analyzer
fallback: general_assistant
llmFallback: true
---

Route incoming messages to the appropriate agent or workflow.
```

### 4. Run

```python
from agentflow import (
    ConfigLoader, RouterEngine, WorkflowExecutor, AgentExecutor,
    ToolRegistry, SessionManager, EventBus,
    FileSystemStorage, AnthropicProvider,
)

# Load configs
loader = ConfigLoader("./context")
loader.load()

# Set up infrastructure
storage = FileSystemStorage("./data")
events = EventBus()
provider = AnthropicProvider()
tools = ToolRegistry()
sessions = SessionManager(storage)

# Route a message
router = RouterEngine(loader, provider, events)
result = await router.route("Research the latest AI safety papers")

# Execute workflow
if result.target == "research_pipeline":
    executor = WorkflowExecutor(loader, provider, tools, sessions, storage, events)
    outputs = await executor.run("Research the latest AI safety papers", session_id="s1")
```

## Architecture

```
agentflow/
  agent/       # AgentExecutor, ContextAssembler, PromptTemplate
  config/      # ConfigLoader, schemas, parser, ContextResolver
  router/      # RouterEngine, RuleEvaluator
  workflow/    # WorkflowExecutor, WorkflowDAG, NodeRunner
  session/     # SessionManager, Scratchpad, ArtifactStore
  memory/      # MemoryManager, FileMemory, VectorMemory
  tools/       # ToolRegistry, LocalToolDispatcher, HTTPToolDispatcher
  providers/   # Anthropic, OpenAI-compat, Google GenAI, Mock
  storage/     # FileSystem, InMemory, S3
  events.py    # EventBus pub/sub system
  types.py     # Canonical data types (Message, AgentResponse, etc.)
  protocols.py # Structural typing interfaces (LLMProvider, StorageBackend, etc.)
```

## Context File Types

| Extension | Purpose | Example |
|---|---|---|
| `*.prompt.md` | Agent config + system prompt | `agents/planner.prompt.md` |
| `*.workflow.md` | DAG workflow definition | `workflows/analysis.workflow.md` |
| `*.context.md` | Shared context / conditional profiles | `shared/schema.context.md` |
| `*.memory.md` | Memory retention config | `agents/researcher.memory.md` |

## Testing

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT
