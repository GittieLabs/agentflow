# Multi-Agent Pipeline

This guide walks through building a complete multi-agent pipeline that researches a topic, analyzes findings, generates a report, and performs quality review -- all as a DAG workflow with parallel execution.

## Overview

We will build a content pipeline with four agents:

1. **Researcher** -- searches for information on a topic
2. **Analyst** -- extracts key insights (runs in parallel with Summarizer)
3. **Summarizer** -- creates a concise summary (runs in parallel with Analyst)
4. **Report Writer** -- combines analysis and summary into a final report

```
researcher
    |
    +---> analyst    (parallel)
    |
    +---> summarizer (parallel)
    |
    v
report_writer (waits for both)
```

## Step 1: Define the Agents

**`context/agents/researcher.prompt.md`**:

```markdown
---
name: researcher
provider: anthropic
model: claude-sonnet-4-6
temperature: 0.7
max_tokens: 4096
tools: [web_search]
---

You are a research agent. Given a topic, conduct thorough research
and compile your findings with sources. Include key facts, recent
developments, and different perspectives.
```

**`context/agents/analyst.prompt.md`**:

```markdown
---
name: analyst
provider: anthropic
model: claude-sonnet-4-6
temperature: 0.3
max_tokens: 2048
---

You are an analysis agent. Given research findings, extract the key
insights, identify trends, and highlight the most important takeaways.
Structure your analysis with clear sections.
```

**`context/agents/summarizer.prompt.md`**:

```markdown
---
name: summarizer
provider: anthropic
model: claude-sonnet-4-6
temperature: 0.3
max_tokens: 1024
---

You are a summarization agent. Condense research findings into a
clear, concise executive summary. Focus on the most important points.
Keep it under 300 words.
```

**`context/agents/report_writer.prompt.md`**:

```markdown
---
name: report_writer
provider: anthropic
model: claude-sonnet-4-6
temperature: 0.5
max_tokens: 4096
context_files: [shared/report-format.context.md]
---

You are a report writer. You receive two labeled sections:

[analysis]
Key insights and trends extracted from the research.

[summary]
A concise executive summary of the same research.

Combine them into a polished, well-structured report using the provided
format guidelines.
```

> **Why the labeled sections?**  The `report` node uses named inputs
> (`analysis:` and `summary:`).  AgentFlow delivers these as labeled
> `[analysis]` and `[summary]` sections in the message.  The system prompt
> should explicitly describe these labels so the agent knows what to expect.
> See [Input Mappings](../concepts/workflows.md#input-mappings) for details.

## Step 2: Define Shared Context

**`context/shared/report-format.context.md`**:

```markdown
---
name: report-format
---

## Report Format Guidelines

Structure every report as follows:

1. **Executive Summary** -- 2-3 paragraph overview
2. **Key Findings** -- Bulleted list of insights
3. **Detailed Analysis** -- Section for each major theme
4. **Conclusions** -- Actionable recommendations
5. **Sources** -- Cited references with URLs
```

## Step 3: Define the Workflow

**`context/workflows/content-pipeline.workflow.md`**:

```markdown
---
name: content_pipeline
trigger: api
callable: true
nodes:
  - id: research
    agent: researcher
    next: [analyze, summarize]
  - id: analyze
    agent: analyst
    mode: parallel
    inputs:
      message: "research.text"
  - id: summarize
    agent: summarizer
    mode: parallel
    inputs:
      message: "research.text"
  - id: report
    agent: report_writer
    inputs:
      analysis: "analyze.text"
      summary: "summarize.text"
---

Content research and report generation pipeline.
Research -> parallel analysis + summarization -> final report.
```

Key points:

- The `research` node fans out to both `analyze` and `summarize` via `next: [analyze, summarize]`
- Both downstream nodes use `mode: parallel` to run concurrently
- The `report` node uses **named inputs** — `analysis:` and `summary:` — to receive output from both parallel branches as labeled sections
- `callable: true` allows this workflow to be invoked by the orchestration layer

**How the `report` node receives its inputs:**

Because `report` uses named inputs (no `message` key), AgentFlow delivers the
resolved values as labeled sections in definition order:

```
[analysis]
Key insights and trends... (output of the 'analyze' node)

[summary]
Brief overview... (output of the 'summarize' node)
```

The `report_writer` system prompt should reference `[analysis]` and `[summary]`
by name.  See the agent definition in Step 1 above.

## Step 4: Define Routing

**`context/router.prompt.md`**:

```markdown
---
name: main_router
routing_rules:
  - if: "'research' in message or 'report' in message or 'analyze' in message"
    routeTo: content_pipeline
fallback: researcher
llmFallback: true
---

Route messages to the content pipeline or individual agents.
```

## Step 5: Register Tools

```python
from agentflow import ToolRegistry

tools = ToolRegistry()

async def web_search(query: str) -> str:
    """Replace with your actual search implementation."""
    # Example: call a search API
    return f"Search results for: {query}\n1. Result one\n2. Result two"

tools.add_tool(
    name="web_search",
    handler=web_search,
    description="Search the web for information on a topic",
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query",
            }
        },
        "required": ["query"],
    },
)
```

## Step 6: Execute the Pipeline

```python
import asyncio
from agentflow import (
    ConfigLoader,
    RouterEngine,
    WorkflowExecutor,
    ToolRegistry,
    SessionManager,
    EventBus,
    FileSystemStorage,
    AnthropicProvider,
)


async def run_pipeline():
    # Load configs
    loader = ConfigLoader("./context")
    loader.load()

    # Infrastructure
    storage = FileSystemStorage("./data")
    events = EventBus()
    provider = AnthropicProvider()
    sessions = SessionManager(storage)

    # Tools
    tools = ToolRegistry()

    async def web_search(query: str) -> str:
        return f"Search results for: {query}"

    tools.add_tool(
        name="web_search",
        handler=web_search,
        description="Search the web",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )

    # Route
    router_config, router_prompt = loader.router
    targets = list(loader.agents.keys()) + list(loader.workflows.keys())
    router = RouterEngine(
        config=router_config,
        router_prompt=router_prompt,
        available_targets=targets,
        llm=provider,
        event_bus=events,
    )

    message = "Research and write a report on the state of AI safety in 2026"
    result = await router.route(message)
    print(f"Routed to: {result.target}")

    # Execute workflow
    executor = WorkflowExecutor(
        loader=loader,
        llm=provider,
        tools=tools,
        sessions=sessions,
        storage=storage,
        events=events,
    )

    outputs = await executor.run(message, session_id="pipeline-demo")

    # Print results
    for output in outputs:
        print(f"\n{'='*60}")
        print(f"Node: {output.node_id} (Agent: {output.agent_id})")
        print(f"{'='*60}")
        print(output.text[:500])


asyncio.run(run_pipeline())
```

## Step 7: Add Observability

Track execution with event handlers:

```python
from agentflow import (
    EventBus,
    NODE_STARTED, NODE_COMPLETED,
    WORKFLOW_STARTED, WORKFLOW_COMPLETED,
)

events = EventBus()

class PipelineMonitor:
    async def on_event(self, event_type: str, data: dict) -> None:
        if event_type == "workflow_started":
            print(f"Pipeline started")
        elif event_type == "node_started":
            print(f"  Running node: {data.get('node_id')}")
        elif event_type == "node_completed":
            print(f"  Completed: {data.get('node_id')}")
        elif event_type == "workflow_completed":
            print(f"Pipeline finished")

monitor = PipelineMonitor()
for event in [WORKFLOW_STARTED, WORKFLOW_COMPLETED, NODE_STARTED, NODE_COMPLETED]:
    events.on(event, monitor)
```

## Step 8: Add Memory

Give the researcher agent memory to learn from past sessions:

**`context/agents/researcher.memory.md`**:

```markdown
---
agent: researcher
retention: permanent
max_entries: 200
---

Researcher memory: stores research findings and user preferences.
```

```python
from agentflow import FileMemory

memory = FileMemory(storage=storage, agent="researcher")

# After execution, store useful findings
await memory.store(
    content="User is interested in AI safety, specifically alignment research.",
    metadata={"tags": ["interest", "ai-safety"]},
)

# Future sessions can retrieve this
results = await memory.search("AI safety")
```

## What You Built

- A four-agent pipeline with parallel execution branches
- YAML-driven routing that directs messages to the right workflow
- Shared context files for consistent output formatting
- Tool integration for the research agent
- Event-based monitoring of the pipeline
- Persistent memory for learning across sessions
