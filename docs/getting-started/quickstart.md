# Quick Start

This tutorial walks you through creating your first agent, defining a workflow, setting up routing, and executing everything with AgentFlow.

## Prerequisites

```bash
pip install "gittielabs-agentflow[anthropic]"
export ANTHROPIC_API_KEY="sk-ant-..."
```

## Step 1: Create the Context Directory

AgentFlow loads configuration from a `context/` directory. Create the following structure:

```
context/
  router.prompt.md
  agents/
    researcher.prompt.md
    formatter.prompt.md
  workflows/
    research.workflow.md
  shared/
    guidelines.context.md
```

## Step 2: Define Your Agents

**`context/agents/researcher.prompt.md`**:

```markdown
---
name: researcher
provider: anthropic
model: claude-sonnet-4-6
temperature: 0.7
max_tokens: 4096
tools: [web_search]
context_files: [shared/guidelines.context.md]
---

You are a research agent. Given a topic, search for relevant information
and provide a comprehensive summary with sources.
```

**`context/agents/formatter.prompt.md`**:

```markdown
---
name: formatter
provider: anthropic
model: claude-sonnet-4-6
temperature: 0.3
max_tokens: 2048
---

You are a formatting agent. Take raw research text and rewrite it
as a clean, well-structured report with sections and bullet points.
```

The YAML front-matter configures the agent. The Markdown body below the `---` becomes the system prompt.

## Step 3: Define Shared Context

**`context/shared/guidelines.context.md`**:

```markdown
---
name: guidelines
---

## Output Guidelines

- Always cite sources with URLs
- Use clear, concise language
- Structure output with headings and bullet points
- Limit responses to 500 words unless asked for more
```

Agents reference shared context files via the `context_files` list in their front-matter. The `ContextAssembler` injects these into the system prompt at runtime.

## Step 4: Define a Workflow

**`context/workflows/research.workflow.md`**:

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

Research pipeline: search for information, then format the results.
```

This defines a two-node DAG. The `research` node runs first, then its output text is passed as input to the `format` node.

## Step 5: Define Routing Rules

**`context/router.prompt.md`**:

```markdown
---
name: main_router
routing_rules:
  - if: "'research' in message or 'find' in message"
    routeTo: research_pipeline
  - if: "'format' in message"
    routeTo: formatter
fallback: researcher
llmFallback: true
---

Route incoming messages to the appropriate agent or workflow.
```

Routing rules are Python expressions evaluated against a context dict containing the user `message`. The first matching rule wins. If no rule matches and `llmFallback` is enabled, the LLM classifies the intent.

## Step 6: Run It

```python
import asyncio
from agentflow import (
    ConfigLoader,
    RouterEngine,
    WorkflowExecutor,
    AgentExecutor,
    ToolRegistry,
    SessionManager,
    EventBus,
    FileSystemStorage,
    AnthropicProvider,
)


async def main():
    # Load all config files
    loader = ConfigLoader("./context")
    loader.load()

    # Set up infrastructure
    storage = FileSystemStorage("./data")
    events = EventBus()
    provider = AnthropicProvider()
    tools = ToolRegistry()
    sessions = SessionManager(storage)

    # Set up router
    router_config, router_prompt = loader.router
    available_targets = list(loader.agents.keys()) + list(loader.workflows.keys())
    router = RouterEngine(
        config=router_config,
        router_prompt=router_prompt,
        available_targets=available_targets,
        llm=provider,
        event_bus=events,
    )

    # Route a message
    message = "Research the latest developments in AI safety"
    result = await router.route(message)
    print(f"Routed to: {result.target} (method: {result.method})")

    # Execute based on routing result
    if result.target in loader.workflows:
        executor = WorkflowExecutor(
            loader=loader,
            llm=provider,
            tools=tools,
            sessions=sessions,
            storage=storage,
            events=events,
        )
        outputs = await executor.run(message, session_id="demo-session")
        for output in outputs:
            print(f"\n--- {output.node_id} ---")
            print(output.text)


asyncio.run(main())
```

## What Happens

1. `ConfigLoader` scans `context/` and parses all `.prompt.md`, `.workflow.md`, and `.context.md` files into typed Pydantic models.
2. `RouterEngine` evaluates the message against YAML rules. Since the message contains "research", it matches `research_pipeline`.
3. `WorkflowExecutor` resolves the workflow DAG and runs each node in order:
    - The `research` node runs the `researcher` agent with the user message.
    - The `format` node receives the research output and reformats it.
4. Each node's output is returned as a `NodeOutput` with the agent's response text.

## Next Steps

- Learn about [context file formats](../concepts/context-files.md) in depth
- Set up [multiple LLM providers](../concepts/providers.md)
- Build a [multi-agent pipeline](../guides/multi-agent-pipeline.md)
- Configure [hierarchical domain routing](../guides/domain-routing.md)
