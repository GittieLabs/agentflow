# Context Files

AgentFlow uses Markdown files with YAML front-matter as its primary configuration format. Each file type has a specific extension and schema.

## File Types Overview

| Extension | Purpose | Location |
|-----------|---------|----------|
| `*.prompt.md` | Agent configuration + system prompt | `context/agents/` |
| `*.workflow.md` | Workflow DAG definition | `context/workflows/` |
| `*.context.md` | Shared context or conditional profiles | `context/shared/`, `context/agents/` |
| `*.memory.md` | Memory retention configuration | `context/agents/` |
| `*.domain.md` | Domain routing boundary | `context/domains/` |

All files follow the same pattern: YAML front-matter between `---` fences, followed by a Markdown body.

## Directory Layout

```
context/
  router.prompt.md              # Top-level routing rules
  agents/
    researcher.prompt.md        # Agent definitions
    formatter.prompt.md
    researcher.context.md       # Agent-specific context
    researcher.memory.md        # Memory config
  workflows/
    research.workflow.md        # Workflow DAGs
    analysis.workflow.md
  domains/
    content.domain.md           # Domain boundaries
    support.domain.md
  shared/
    guidelines.context.md       # Shared context files
    persona.context.md
```

`ConfigLoader` scans this tree and parses each file into typed Pydantic models.

---

## Agent Files (*.prompt.md)

Agent files define a single agent's configuration and system prompt.

### Front-Matter Schema

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | *required* | Unique agent identifier |
| `description` | `str` | `""` | Human-readable description |
| `provider` | `str` | `"anthropic"` | LLM provider name |
| `model` | `str` | `"claude-sonnet-4-6"` | Model identifier |
| `temperature` | `float` | `0.7` | Sampling temperature |
| `max_tokens` | `int` | `4096` | Maximum response tokens |
| `max_tool_rounds` | `int` | `6` | Maximum tool-use loops |
| `tools` | `list[str]` | `[]` | Tool names to make available |
| `tool_definitions` | `list` | `[]` | Inline tool schemas |
| `context_files` | `list[str]` | `[]` | Context files to inject |

### Example

```markdown
---
name: researcher
description: "Searches and summarizes information"
provider: anthropic
model: claude-sonnet-4-6
temperature: 0.7
max_tokens: 4096
max_tool_rounds: 6
tools: [web_search, summarize]
context_files: [shared/guidelines.context.md]
---

You are a research agent. Given a topic, search for relevant information
and provide a comprehensive summary with sources.

## Guidelines
- Always cite your sources
- Provide at least 3 different perspectives
- Use clear, concise language
```

The Markdown body becomes the system prompt. Context files listed in `context_files` are appended to the system prompt by the `ContextAssembler` at runtime.

---

## Workflow Files (*.workflow.md)

Workflow files define a DAG of agent nodes.

### Front-Matter Schema

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | *required* | Unique workflow identifier |
| `description` | `str` | `""` | Human-readable description |
| `trigger` | `str` | `"manual"` | Trigger type: `manual`, `api`, `cron`, `webhook` |
| `callable` | `bool` | `false` | Whether this workflow can be invoked by orchestration |
| `nodes` | `list[Node]` | `[]` | Ordered list of DAG nodes |

### Node Schema

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | *required* | Unique node identifier within workflow |
| `agent` | `str` | *required* | Agent name to execute |
| `next` | `str \| list[str] \| null` | `null` | Next node(s) to execute |
| `mode` | `str` | `"sync"` | Execution mode: `sync`, `parallel`, `async` |
| `inputs` | `dict[str, str]` | `{}` | Input mappings from previous node outputs |

### Example

```markdown
---
name: research_pipeline
trigger: api
nodes:
  - id: research
    agent: researcher
    next: [summarize, analyze]
  - id: summarize
    agent: summarizer
    mode: parallel
    inputs:
      message: "research.text"
  - id: analyze
    agent: analyzer
    mode: parallel
    inputs:
      message: "research.text"
  - id: format
    agent: formatter
    inputs:
      summary: "summarize.text"
      analysis: "analyze.text"
---

Multi-step research pipeline with parallel summarization and analysis.
```

### Input Mappings

The `inputs` field maps parameter names to outputs from previous nodes using dot notation:

- `"research.text"` -- the `text` field from the `research` node's `NodeOutput`
- `"analyze.artifacts.chart"` -- an artifact from the `analyze` node

---

## Context Files (*.context.md)

Context files provide reusable text that gets injected into agent system prompts. There are two types: plain context and profile context.

### Plain Context

A simple context file that provides static content:

```markdown
---
name: guidelines
---

## Output Guidelines
- Always cite sources with URLs
- Use clear, concise language
- Limit responses to 500 words
```

### Profile Context

A profile is a manifest that conditionally includes other context files based on runtime conditions:

```markdown
---
type: profile
includes:
  - shared/persona.context.md
conditionalIncludes:
  - if: "'blog' in message or 'article' in message"
    include: shared/content-guidelines.context.md
  - if: "'lead' in message"
    include:
      - shared/lead-gen-config.context.md
      - shared/email-templates.context.md
---

Context profile for dynamic content loading.
```

The `includes` list is always loaded. The `conditionalIncludes` entries are evaluated at runtime against a context dictionary containing the user `message`.

---

## Memory Files (*.memory.md)

Memory files configure how an agent retains information across sessions.

### Front-Matter Schema

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `agent` | `str` | *required* | Agent this config applies to |
| `retention` | `str` | `"permanent"` | Retention policy: `permanent`, `session`, `ttl:7d` |
| `max_entries` | `int` | `100` | Maximum stored entries |

### Example

```markdown
---
agent: researcher
retention: permanent
max_entries: 200
---

Memory configuration for the research agent.
Stores research findings for future reference.
```

---

## Domain Files (*.domain.md)

Domain files group related agents and workflows under a routing boundary. Used with the `DomainRouter` for hierarchical routing.

### Front-Matter Schema

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | *required* | Domain identifier |
| `description` | `str` | `""` | What this domain handles |
| `routerModel` | `str` | `"claude-sonnet-4-6"` | LLM model for intra-domain routing |
| `routerTemperature` | `float` | `0.0` | Temperature for routing decisions |
| `agents` | `list[str]` | `[]` | Agents in this domain |
| `workflows` | `list[str]` | `[]` | Workflows in this domain |
| `contextFiles` | `list[str]` | `[]` | Shared context for this domain |
| `fallback` | `str` | `""` | Default agent when routing is ambiguous |

### Example

```markdown
---
name: content
description: "Content research, creation, editing, and publishing"
routerModel: claude-sonnet-4-6
agents:
  - content_researcher
  - content_formatter
workflows:
  - content-research
  - content-creation
contextFiles:
  - shared/content-guidelines.context.md
fallback: content_researcher
---

Content domain: handles all content-related tasks including
research, writing, editing, and publishing workflows.
```

---

## Router File (router.prompt.md)

The top-level router lives at `context/router.prompt.md`. See [Routing](routing.md) for details.

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

## Loading Configuration

```python
from agentflow import ConfigLoader

loader = ConfigLoader("./context")
loader.load()

# Access loaded configs
config, prompt = loader.get_agent("researcher")
wf_config, wf_desc = loader.get_workflow("research_pipeline")
router_config, router_prompt = loader.router

# Access context
body = loader.get_context_body("shared/guidelines.context.md")

# Access domains
domain_config, domain_prompt = loader.get_domain("content")
```
