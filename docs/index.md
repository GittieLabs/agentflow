# AgentFlow

**Context engineering framework for multi-agent systems.**

AgentFlow is a framework-agnostic toolkit for building multi-agent workflows where configuration lives in Markdown files with YAML front-matter. Define agents, workflows, routing rules, and memory -- all as readable `.prompt.md`, `.workflow.md`, `.context.md`, and `.memory.md` files.

---

## Key Features

- **Markdown + YAML config files** -- Define agents, workflows, and routing rules as human-readable Markdown with YAML front-matter. No JSON sprawl, no framework lock-in.

- **Pluggable LLM providers** -- First-class support for Anthropic Claude, OpenAI GPT, Google Gemini, and any OpenAI-compatible API. Swap providers by changing one line of config.

- **Hybrid routing** -- Combine deterministic YAML rules with LLM-based intent classification. Hierarchical domain routing groups agents under logical boundaries.

- **DAG-based workflows** -- Compose agents into directed acyclic graphs with sync, parallel, and async execution modes. Pass outputs between nodes.

- **Sessions and memory** -- Per-node scratchpads, session history, multi-user support, file-based memory, and vector search via Qdrant.

- **Tool registry** -- Register tools with local Python handlers or HTTP endpoints. Agents call tools automatically during execution.

- **Event-driven observability** -- Pub/sub event bus with built-in support for Langfuse telemetry. Hook into every framework event without coupling.

---

## Quick Install

```bash
pip install gittielabs-agentflow
```

With LLM provider extras:

```bash
# Anthropic Claude
pip install "gittielabs-agentflow[anthropic]"

# OpenAI / OpenAI-compatible
pip install "gittielabs-agentflow[openai]"

# Google Gemini
pip install "gittielabs-agentflow[google]"

# Everything
pip install "gittielabs-agentflow[all]"
```

---

## Minimal Example

**1. Define an agent** (`context/agents/researcher.prompt.md`):

```markdown
---
name: researcher
provider: anthropic
model: claude-sonnet-4-6
temperature: 0.7
max_tokens: 4096
tools: [web_search, summarize]
---

You are a research agent. Given a topic, search for relevant information
and provide a comprehensive summary with sources.
```

**2. Run it**:

```python
from agentflow import (
    ConfigLoader, AgentExecutor, ToolRegistry,
    SessionManager, EventBus, FileSystemStorage,
    AnthropicProvider,
)

# Load configs from the context/ directory
loader = ConfigLoader("./context")
loader.load()

# Set up infrastructure
storage = FileSystemStorage("./data")
events = EventBus()
provider = AnthropicProvider()
tools = ToolRegistry()
sessions = SessionManager(storage)

# Get agent config and execute
config, system_prompt = loader.get_agent("researcher")
```

---

## Project Status

AgentFlow is in **alpha** (v0.5.0). The core APIs are stabilizing but may still change between minor versions. Production use should pin to a specific version.

- **License**: MIT
- **Python**: 3.11+
- **PyPI**: [gittielabs-agentflow](https://pypi.org/project/gittielabs-agentflow/)
- **Source**: [GittieLabs/agentflow](https://github.com/GittieLabs/agentflow)
