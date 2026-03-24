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
| `agent` | `str` | *required* | Name of the agent to execute |
| `next` | `str \| list[str] \| null` | `null` | Downstream node(s) |
| `mode` | `str` | `"sync"` | Execution mode |
| `inputs` | `dict[str, str]` | `{}` | Input mappings from upstream outputs |

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

The `inputs` field maps parameter names to outputs from upstream nodes using dot notation:

```yaml
inputs:
  message: "research.text"        # text output from research node
  data: "analyze.artifacts.chart" # artifact from analyze node
```

The referenced values come from `NodeOutput` objects:

- `<node_id>.text` -- the node's text response
- `<node_id>.artifacts.<key>` -- named artifacts produced by the node

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
