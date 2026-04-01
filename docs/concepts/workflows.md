# Workflows

Workflows in AgentFlow are directed acyclic graphs (DAGs) of agent nodes. Each node executes an agent and can pass its output to downstream nodes. Nodes support sync, parallel, and async execution modes.

## Defining a Workflow

Workflows are defined in `*.workflow.md` files with YAML front-matter:

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

Research pipeline with parallel processing.
```

## Workflow Configuration

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | *required* | Unique workflow identifier |
| `description` | `str` | `""` | Human-readable description |
| `trigger` | `str` | `"manual"` | `manual`, `api`, `cron`, `webhook` |
| `callable` | `bool` | `false` | Can be invoked by the orchestration layer |
| `nodes` | `list[Node]` | `[]` | Ordered list of DAG nodes |

## Node Configuration

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | *required* | Unique node ID within the workflow |
| `agent` | `str` | *required\** | Name of the agent to execute |
| `handler` | `str` | `null` | Registered Python function name (alternative to `agent`) |
| `next` | `str \| list[str] \| null` | `null` | Downstream node(s) |
| `mode` | `str` | `"sync"` | Execution mode |
| `inputs` | `dict[str, str]` | `{}` | Input mappings from upstream outputs |
| `foreach` | `str` | `null` | Dotted ref to a list artifact — runs the node once per item |

\* Either `agent` or `handler` is required, but not both.

## Execution Modes

### Sync (default)

Nodes execute one at a time, in the order defined by the DAG:

```yaml
nodes:
  - id: step1
    agent: agent_a
    next: step2
  - id: step2
    agent: agent_b
```

### Parallel

Sibling nodes marked as `parallel` run concurrently:

```yaml
nodes:
  - id: research
    agent: researcher
    next: [branch_a, branch_b]
  - id: branch_a
    agent: analyzer
    mode: parallel
    inputs:
      message: "research.text"
  - id: branch_b
    agent: summarizer
    mode: parallel
    inputs:
      message: "research.text"
```

Both `branch_a` and `branch_b` start executing as soon as `research` completes.

### Async

Async nodes are dispatched without waiting for completion. Useful for fire-and-forget tasks like logging or notifications:

```yaml
nodes:
  - id: main_task
    agent: worker
    next: [notify, continue]
  - id: notify
    agent: notifier
    mode: async
  - id: continue
    agent: next_worker
```

## Input Mappings

The `inputs` field controls what each node receives as its message.  There are three distinct patterns, applied in priority order.

### Pattern 1 — Single message (`message` key)

Route one upstream output directly as the message.  Use this for most linear
pipeline steps where the node has a single predecessor.

```yaml
- id: summarize
  agent: summarizer
  inputs:
    message: "research.text"      # passes research node's text output
```

### Pattern 2 — Named inputs (any keys except `message`)

When a node needs output from **multiple** upstream nodes, use named keys.
Each key is resolved in YAML-definition order and delivered as a labeled
section:

```yaml
- id: report
  agent: report_writer
  inputs:
    analysis: "analyze.text"
    summary: "summarize.text"
```

The agent receives a single message containing both inputs, clearly labeled:

```
[analysis]
<content from analyze node>

[summary]
<content from summarize node>
```

Write the agent's system prompt to reference these sections by label name —
for example: *"You receive two labeled sections: [analysis] and [summary]..."*

> **Important:** the `message` key takes priority.  If `message` is present,
> all other keys in the same `inputs` block are ignored.  Never mix `message`
> with named keys in the same node.

### Pattern 3 — No inputs defined

The node receives the workflow's initial message.  Use this only for the
**first node** in a pipeline.  Non-entry nodes with no `inputs` defined will
receive an empty message.

```yaml
- id: research        # entry node — receives the initial workflow message
  agent: researcher
  next: [analyze, summarize]
```

### Reference syntax

All input values use dot notation to reference prior node outputs:

```yaml
inputs:
  data: "research.text"            # text output from the 'research' node
  leads: "extract.artifacts.leads" # named artifact from the 'extract' node
```

Supported reference forms:

- `<node_id>.text` — the node's full text response
- `<node_id>.artifacts.<key>` — a named artifact produced by the node

The `node_id` can be **any previously completed node**, not just a direct DAG
predecessor.  The executor passes all completed outputs to each node, so you
can reference a grandparent or sibling node directly.  That said, always add
the corresponding DAG edge (`next:` entry) so the execution order is
guaranteed.

## Code Handler Nodes

Handler nodes run a registered Python function instead of an LLM call. Use them for deterministic processing steps — data transformation, validation, formatting — where an LLM is unnecessary.

### Defining a handler node

Set `handler: <name>` on the node instead of `agent: <name>`:

```yaml
nodes:
  - id: extract
    agent: extractor
    next: [normalize]
  - id: normalize
    handler: normalize_text
    inputs:
      message: "extract.text"
    next: [report]
  - id: report
    agent: reporter
    inputs:
      message: "normalize.text"
```

### Implementing a handler function

A handler is an async function with signature `(message: str, prior_outputs: dict) -> NodeOutput`:

```python
from agentflow.types import NodeOutput

async def normalize_text(message: str, prior_outputs: dict) -> NodeOutput:
    cleaned = message.strip().lower()
    return NodeOutput(
        node_id="normalize",
        agent_id="normalize_text",
        text=cleaned,
    )
```

### Registering handlers with WorkflowExecutor

Pass a `handlers` dict to `WorkflowExecutor`:

```python
executor = WorkflowExecutor(
    config=wf_config,
    runner_factory=runner_factory,
    handlers={"normalize_text": normalize_text},
)
```

Handler nodes support all the same `inputs` patterns as agent nodes, including named inputs with labeled sections.

Handler nodes emit a `HANDLER_RESULT` event after execution so observers (e.g. asset collectors) can react to handler outputs the same way they react to `TOOL_RESULT` events.

## Foreach Iteration

A node with `foreach` set runs its body once per item in a list artifact from a prior node. Results are collected into `artifacts["results"]` on the node's output.

### Defining a foreach node

```yaml
nodes:
  - id: extract
    handler: produce_list
    next: [process]
  - id: process
    agent: item_processor
    foreach: "extract.artifacts.items"
```

### Loop variables

Each iteration receives these variables injected into its message:

| Variable | Description |
|----------|-------------|
| `loop_item` | The current item value |
| `loop_index` | Zero-based iteration index |
| `loop_total` | Total number of items |
| `loop_prior_results` | Results accumulated so far in this foreach run |

### Combining handler and foreach

A handler node can also use `foreach` — the handler function is called once per item:

```yaml
- id: batch_transform
  handler: transform_item
  foreach: "source.artifacts.items"
```

```python
async def transform_item(message: str, prior_outputs: dict) -> NodeOutput:
    # message contains the loop variables for this iteration
    return NodeOutput(node_id="batch_transform", agent_id="transform_item", text=message.upper())
```

If the foreach reference resolves to `None` or an empty list, the node is skipped and returns an empty result rather than raising an error.

## WorkflowDAG

`WorkflowDAG` validates and provides traversal over the node graph:

```python
from agentflow import WorkflowDAG, ConfigLoader

loader = ConfigLoader("./context")
loader.load()
config, _ = loader.get_workflow("research_pipeline")

dag = WorkflowDAG(config)
entry = dag.entry_node()  # First node in the workflow
```

## WorkflowExecutor

`WorkflowExecutor` runs a complete workflow from start to finish:

```python
from agentflow import (
    WorkflowExecutor, ConfigLoader, AnthropicProvider,
    ToolRegistry, SessionManager, FileSystemStorage, EventBus,
)

loader = ConfigLoader("./context")
loader.load()

executor = WorkflowExecutor(
    loader=loader,
    llm=AnthropicProvider(),
    tools=ToolRegistry(),
    sessions=SessionManager(FileSystemStorage("./data")),
    storage=FileSystemStorage("./data"),
    events=EventBus(),
)

outputs = await executor.run(
    message="Research quantum computing advances",
    session_id="session-123",
)

for output in outputs:
    print(f"Node: {output.node_id}")
    print(f"Agent: {output.agent_id}")
    print(f"Text: {output.text[:200]}")
```

`outputs` is a list of `NodeOutput` objects, one per node executed.

## NodeRunner

`NodeRunner` handles execution of a single node. It:

1. Loads the agent configuration
2. Assembles the context (system prompt + shared context files + upstream summaries)
3. Runs the agent with the tool loop
4. Writes scratchpad and summary files
5. Returns a `NodeOutput`

## Events

Workflow execution emits events through the `EventBus`:

| Event | When |
|-------|------|
| `WORKFLOW_STARTED` | Workflow execution begins |
| `WORKFLOW_COMPLETED` | Workflow execution finishes |
| `NODE_STARTED` | A node begins execution |
| `NODE_COMPLETED` | A node finishes execution |

## Orchestration

For complex tasks that require dynamic planning, the orchestration layer builds on workflows:

- `ComplexityClassifier` -- determines whether a request needs a single agent or a multi-step plan
- `Plan` / `PlanStep` -- typed representations of multi-step execution plans
- `DAGExecutor` -- executes plans by resolving inter-step dependencies and running independent steps concurrently

```python
from agentflow import ComplexityClassifier, DAGExecutor, Plan

classifier = ComplexityClassifier(llm=provider)
plan = await classifier.classify(message)

executor = DAGExecutor(workflow_executor=workflow_executor)
results = await executor.execute(plan)
```
