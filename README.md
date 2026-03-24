# AgentFlow

[![PyPI version](https://img.shields.io/pypi/v/gittielabs-agentflow.svg)](https://pypi.org/project/gittielabs-agentflow/)
[![Python 3.11+](https://img.shields.io/pypi/pyversions/gittielabs-agentflow.svg)](https://pypi.org/project/gittielabs-agentflow/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/GittieLabs/agentflow/actions/workflows/ci.yml/badge.svg)](https://github.com/GittieLabs/agentflow/actions/workflows/ci.yml)

**Context engineering framework for multi-agent systems.**

AgentFlow is a framework-agnostic toolkit for building multi-agent workflows using plain Markdown and YAML configuration files. Define agents, workflows, routing rules, and context -- all in version-controllable `.md` files.

**[Full Documentation](https://gittielabs.github.io/agentflow/)** | **[PyPI](https://pypi.org/project/gittielabs-agentflow/)** | **[GitHub](https://github.com/GittieLabs/agentflow)**

## Key Features

- **Markdown + YAML config files** -- Agents, workflows, and routing defined in `.prompt.md`, `.workflow.md`, `.context.md` files
- **Pluggable LLM providers** -- Anthropic Claude, OpenAI GPT, Google Gemini, or any OpenAI-compatible API
- **Hybrid routing** -- YAML rule matching with LLM fallback, plus hierarchical domain routing
- **DAG-based workflows** -- Sync, parallel, and async node execution with input mapping
- **Session management** -- Scratchpads, multi-user history, and artifact storage
- **Memory system** -- File-based and vector search (embedding-agnostic)
- **Tool registry** -- Local and HTTP tool dispatchers
- **Event-driven observability** -- EventBus with Langfuse telemetry integration

## Install

```bash
pip install gittielabs-agentflow

# With a specific LLM provider
pip install "gittielabs-agentflow[anthropic]"    # Claude
pip install "gittielabs-agentflow[google]"       # Gemini
pip install "gittielabs-agentflow[openai]"       # OpenAI / compatible

# Everything
pip install "gittielabs-agentflow[all]"
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

See the [Quick Start guide](https://gittielabs.github.io/agentflow/getting-started/quickstart/) for a complete walkthrough.

## Architecture

```
agentflow/
  agent/          # AgentExecutor, ContextAssembler, PromptTemplate
  config/         # ConfigLoader, schemas, parser, ContextResolver
  router/         # RouterEngine, DomainRouter, RuleEvaluator
  workflow/       # WorkflowExecutor, WorkflowDAG, NodeRunner
  session/        # SessionManager, Scratchpad, ArtifactStore
  memory/         # MemoryManager, FileMemory, VectorMemory
  tools/          # ToolRegistry, LocalToolDispatcher, HTTPToolDispatcher
  providers/      # Anthropic, OpenAI-compat, Google GenAI, Mock
  storage/        # FileSystem, InMemory, S3
  orchestration/  # DAGExecutor, ComplexityClassifier, Plan
  telemetry/      # LangfuseEventHandler
  events.py       # EventBus pub/sub system
  types.py        # Canonical data types (Message, AgentResponse, etc.)
  protocols.py    # Structural typing interfaces (LLMProvider, StorageBackend, etc.)
```

Learn more in the [Architecture docs](https://gittielabs.github.io/agentflow/concepts/architecture/).

## Context File Types

| Extension | Purpose | Example |
|---|---|---|
| `*.prompt.md` | Agent config + system prompt | `agents/planner.prompt.md` |
| `*.workflow.md` | DAG workflow definition | `workflows/analysis.workflow.md` |
| `*.context.md` | Shared context / conditional profiles | `shared/schema.context.md` |
| `*.memory.md` | Memory retention config | `agents/researcher.memory.md` |
| `*.domain.md` | Domain routing boundary | `domains/content.domain.md` |

See [Context Files](https://gittielabs.github.io/agentflow/concepts/context-files/) for full schema reference.

## Documentation

Full documentation is available at **[gittielabs.github.io/agentflow](https://gittielabs.github.io/agentflow/)**, including:

- [Installation & setup](https://gittielabs.github.io/agentflow/getting-started/installation/)
- [Context file reference](https://gittielabs.github.io/agentflow/concepts/context-files/)
- [Provider configuration](https://gittielabs.github.io/agentflow/concepts/providers/)
- [Routing & domain routing](https://gittielabs.github.io/agentflow/concepts/routing/)
- [Workflow execution](https://gittielabs.github.io/agentflow/concepts/workflows/)
- [Multi-agent pipeline guide](https://gittielabs.github.io/agentflow/guides/multi-agent-pipeline/)
- [Changelog](https://gittielabs.github.io/agentflow/changelog/)

## Contributing

```bash
git clone https://github.com/GittieLabs/agentflow.git
cd agentflow
pip install -e ".[dev]"
pytest
```

## License

MIT
