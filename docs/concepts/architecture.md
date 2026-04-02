# Architecture

AgentFlow is organized into focused modules with clear boundaries. Each module communicates through typed protocols, making components interchangeable.

## Module Map

```
agentflow/
  types.py          # Canonical data types (Message, AgentResponse, etc.)
  protocols.py      # Structural typing interfaces (PEP 544)
  events.py         # EventBus pub/sub system
  config/           # ConfigLoader, schemas, parser
  agent/            # AgentExecutor, ContextAssembler, PromptTemplate
  router/           # RouterEngine, DomainRouter, RuleEvaluator
  workflow/         # WorkflowExecutor, WorkflowDAG, NodeRunner
  session/          # SessionManager, Scratchpad, ArtifactStore
  memory/           # MemoryManager, FileMemory, VectorMemory
  tools/            # ToolRegistry, LocalToolDispatcher, HTTPToolDispatcher
  providers/        # Anthropic, OpenAI-compat, Google GenAI, Mock
  storage/          # FileSystem, InMemory, S3
  orchestration/    # DAGExecutor, ComplexityClassifier, Plan
  telemetry/        # LangfuseEventHandler
```

## Core Data Types

All modules share a common set of data types defined in `types.py`. These are provider-agnostic -- each LLM provider adapter translates to and from these types.

| Type | Purpose |
|------|---------|
| `Role` | Enum: `SYSTEM`, `USER`, `ASSISTANT`, `TOOL_RESULT` |
| `NodeMode` | Enum: `SYNC`, `PARALLEL`, `ASYNC` |
| `Message` | A conversation message with role, content, tool calls/results, metadata |
| `AgentResponse` | Unified LLM response: text, tool calls, stop reason, usage stats |
| `ToolCall` | A tool invocation request: id, name, input dict |
| `ToolResult` | Tool execution result: tool_call_id, content, is_error flag |
| `NodeOutput` | Output from a workflow node: node_id, agent_id, text, artifacts |

## Protocols

AgentFlow uses Python's structural typing (PEP 544 `Protocol` classes) to define contracts for pluggable backends. Any class implementing the right methods works -- no inheritance required.

| Protocol | Methods | Used By |
|----------|---------|---------|
| `LLMProvider` | `chat(messages, system, tools, max_tokens, temperature)` | All agent execution |
| `StorageBackend` | `read`, `write`, `exists`, `list`, `delete` | Sessions, memory, artifacts |
| `ToolDispatcher` | `dispatch(tool_name, tool_input)`, `list_tools()` | Tool registry |
| `MemoryStore` | `search(query, limit)`, `store(content, metadata)` | Memory system |
| `EventHandler` | `on_event(event_type, data)` | EventBus observers |

All protocol classes are `@runtime_checkable`, so you can use `isinstance()` checks.

## Request Flow

A typical request flows through these stages:

```
User Message
    |
    v
RouterEngine          -- YAML rules, then LLM fallback
    |
    v
WorkflowExecutor      -- resolves DAG, runs nodes in order
    |
    v
NodeRunner            -- per-node: assembles context, calls agent
    |
    v
AgentExecutor         -- tool loop: LLM call -> tool dispatch -> repeat
    |
    v
LLMProvider           -- Anthropic / OpenAI / Google / Mock
    |
    v
NodeOutput            -- text + artifacts from each node
```

### With Domain Routing

When using hierarchical domains, the flow adds a tier:

```
User Message
    |
    v
DomainRouter          -- top-level: classifies into domain
    |
    v
Domain RouterEngine   -- intra-domain: picks specific agent/workflow
    |
    v
WorkflowExecutor / AgentExecutor
    |
    v
NodeOutput
```

## Advanced Orchestration

While standard `WorkflowExecutor` flows are defined via static YAML DAGs, some tasks require dynamic planning because the execution graph cannot be predicted ahead of time. This is where the `orchestration` module comes into play.

The orchestration flow goes a step beyond DAG static paths:
1. `ComplexityClassifier` intercepts the user request and determines if it requires a sequence of tool calls or specific agents to be orchestrated dynamically.
2. If multi-step planning is needed, an autonomous `plan` agent formulates a sequence of steps (as a typed `PlanStep` array).
3. `DAGExecutor` parses this dynamic plan into an ad-hoc dependency graph and executes the disjointed steps.

**When to use Orchestration:**
- The task is highly variable and depends on iterative tool results (e.g. general internet search workflows where finding X dictates whether to search for Y or Z).
- You want an autonomous planner agent to route directly to multiple tools without requiring you to map out every single permutations in a `*.workflow.md` file.

**When to use Static Workflows:**
- The task is predictable, operational, and linear (e.g., standard Resume Conversions, daily batch reports, parsing a static PDF structure).

## Key Design Decisions

**Configuration as Markdown.** Agent definitions, workflows, routing rules, and context all live in `.md` files with YAML front-matter. This keeps configuration human-readable, version-controllable, and easy to review in PRs.

**Protocol-based pluggability.** The framework never imports provider-specific code at the top level. Provider SDKs are optional extras. The `LLMProvider` protocol means any backend that implements `async chat(...)` works.

**Event-driven observability.** The `EventBus` decouples logging, metrics, and telemetry from core execution. Handlers subscribe to specific event types. Handler errors are caught and logged, never breaking execution flow.

**DAG-first workflows.** Workflows are directed acyclic graphs, not simple chains. Nodes can fan out to parallel branches and converge. The `WorkflowDAG` validates the graph structure before execution.

**Session isolation.** Each session gets its own scratchpad files and history. Multi-user history keeps conversations separate while sharing the same agent infrastructure.
