# API Reference

All public exports are available from the top-level `agentflow` package:

```python
from agentflow import ConfigLoader, AgentExecutor, EventBus
```

## Types

Core data types shared across all modules. Defined in `agentflow.types`.

| Class | Description |
|-------|-------------|
| `Role` | Enum: `SYSTEM`, `USER`, `ASSISTANT`, `TOOL_RESULT` |
| `NodeMode` | Enum: `SYNC`, `PARALLEL`, `ASYNC` |
| `Message` | Conversation message with role, content, tool calls/results, metadata |
| `AgentResponse` | Unified LLM response: text, tool_calls, stop_reason, usage, raw, metadata |
| `ToolCall` | Tool invocation request: id, name, input dict |
| `ToolResult` | Tool execution result: tool_call_id, content, is_error |
| `NodeOutput` | Workflow node output: node_id, agent_id, text, artifacts, metadata |

## Protocols

Structural typing interfaces (PEP 544). Defined in `agentflow.protocols`. All are `@runtime_checkable`.

| Protocol | Key Methods |
|----------|-------------|
| `LLMProvider` | `async chat(messages, system, tools, max_tokens, temperature) -> AgentResponse` |
| `StorageBackend` | `async read(path)`, `async write(path, content)`, `async exists(path)`, `async list(prefix)`, `async delete(path)` |
| `ToolDispatcher` | `async dispatch(tool_name, tool_input) -> str`, `list_tools() -> list[dict]` |
| `MemoryStore` | `async search(query, limit) -> list[dict]`, `async store(content, metadata) -> str` |
| `EventHandler` | `async on_event(event_type, data) -> None` |

## Agent

Agent execution and context assembly. Defined in `agentflow.agent`.

| Class | Description |
|-------|-------------|
| `AgentExecutor` | Runs an agent with tool loop (LLM call -> tool dispatch -> repeat) |
| `ContextAssembler` | Builds system prompts from agent config + context files + upstream summaries |
| `PromptTemplate` | Template rendering for system prompts |

## Config

Configuration loading and schemas. Defined in `agentflow.config`.

| Class | Description |
|-------|-------------|
| `ConfigLoader` | Scans a context directory and loads all config files into typed models |
| `AgentConfig` | Pydantic model for `*.prompt.md` front-matter |
| `WorkflowConfig` | Pydantic model for `*.workflow.md` front-matter |
| `RouterConfig` | Pydantic model for `router.prompt.md` front-matter |
| `DomainConfig` | Pydantic model for `*.domain.md` front-matter |

### ConfigLoader Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `load()` | `None` | Scan and parse all config files |
| `get_agent(name)` | `tuple[AgentConfig, str]` | Agent config + system prompt body |
| `get_workflow(name)` | `tuple[WorkflowConfig, str]` | Workflow config + description body |
| `get_domain(name)` | `tuple[DomainConfig, str]` | Domain config + prompt body |
| `get_context_body(filename)` | `str \| None` | Raw body of a context file |
| `get_profile(filename)` | `ContextProfile \| None` | Profile manifest, if applicable |

### ConfigLoader Properties

| Property | Type | Description |
|----------|------|-------------|
| `agents` | `dict[str, tuple[AgentConfig, str]]` | All loaded agents |
| `workflows` | `dict[str, tuple[WorkflowConfig, str]]` | All loaded workflows |
| `domains` | `dict[str, tuple[DomainConfig, str]]` | All loaded domains |
| `router` | `tuple[RouterConfig, str] \| None` | Router config, if present |
| `profiles` | `dict[str, ContextProfile]` | All loaded context profiles |

## Events

Event bus and standard event constants. Defined in `agentflow.events`.

| Export | Type | Description |
|--------|------|-------------|
| `EventBus` | class | Pub/sub event system |
| `WORKFLOW_STARTED` | `str` | `"workflow_started"` |
| `WORKFLOW_COMPLETED` | `str` | `"workflow_completed"` |
| `NODE_STARTED` | `str` | `"node_started"` |
| `NODE_COMPLETED` | `str` | `"node_completed"` |
| `TOOL_CALLED` | `str` | `"tool_called"` |
| `TOOL_RESULT` | `str` | `"tool_result"` |
| `LLM_CALL_STARTED` | `str` | `"llm_call_started"` |
| `LLM_CALL_COMPLETED` | `str` | `"llm_call_completed"` |
| `DOMAIN_ROUTED` | `str` | `"domain_routed"` |
| `ERROR` | `str` | `"error"` |

### EventBus Methods

| Method | Description |
|--------|-------------|
| `on(event_type, handler)` | Register a handler |
| `off(event_type, handler)` | Remove a handler |
| `async emit(event_type, data)` | Emit an event to all handlers (errors logged, never raised) |

## Storage

Storage backend implementations. Defined in `agentflow.storage`.

| Class | Description |
|-------|-------------|
| `FileSystemStorage` | Local filesystem backend |
| `InMemoryStorage` | Ephemeral in-memory backend (testing) |
| `S3Storage` | AWS S3 backend (requires `[s3]` extra) |

## Tools

Tool registry and dispatchers. Defined in `agentflow.tools`.

| Class | Description |
|-------|-------------|
| `ToolRegistry` | Aggregates dispatchers, routes tool calls, lists definitions |
| `LocalToolDispatcher` | Dispatches to local Python async functions |
| `HTTPToolDispatcher` | Dispatches as HTTP POST requests |

### ToolRegistry Methods

| Method | Description |
|--------|-------------|
| `add_tool(name, handler, description, input_schema)` | Register an inline tool |
| `add_dispatcher(tool_names, dispatcher)` | Register a dispatcher for a set of tools |
| `async dispatch(tool_name, tool_input) -> str` | Route a tool call |
| `list_tools() -> list[dict]` | Get all tool definitions |

## Providers

LLM provider implementations. Defined in `agentflow.providers`.

| Class | Provider | Extra |
|-------|----------|-------|
| `AnthropicProvider` | Anthropic Claude | `[anthropic]` |
| `OpenAICompatProvider` | OpenAI / compatible APIs | `[openai]` |
| `GoogleGenAIProvider` | Google Gemini | `[google]` |
| `MockLLMProvider` | Testing mock | *(core)* |

## Session

Session management. Defined in `agentflow.session`.

| Class | Description |
|-------|-------------|
| `Session` | Single conversation/task session |
| `SessionManager` | Session lifecycle management |
| `Scratchpad` | Per-node working notes and summaries |
| `ArtifactStore` | Named artifact storage |
| `MultiUserHistory` | Per-user conversation history |
| `HistoryPersistence` | History read/write to storage |

### Scratchpad Methods

| Method | Description |
|--------|-------------|
| `async read_scratch()` | Read working notes |
| `async write_scratch(content)` | Write/overwrite working notes |
| `async append_scratch(content)` | Append to working notes |
| `async read_summary()` | Read node summary |
| `async write_summary(content)` | Write node summary |

## Orchestration

Multi-step planning and execution. Defined in `agentflow.orchestration`.

| Class | Description |
|-------|-------------|
| `ComplexityClassifier` | Determines if a request needs single agent or multi-step plan |
| `DAGExecutor` | Executes plans with dependency resolution and concurrency |
| `Plan` | TypedDict: `{"steps": list[PlanStep]}` |
| `PlanStep` | TypedDict: `{"id", "workflow", "message", "output_key"}` |

## Memory

Memory backends. Defined in `agentflow.memory`.

| Class | Description |
|-------|-------------|
| `MemoryManager` | Coordinates memory operations |
| `FileMemory` | Markdown file-based memory with substring search |
| `VectorMemory` | Qdrant-backed semantic search (requires `[vector]` extra) |

### FileMemory Methods

| Method | Description |
|--------|-------------|
| `async store(content, metadata) -> str` | Store a memory entry, returns path |
| `async search(query, limit) -> list[dict]` | Substring search |
| `async list_entries() -> list[str]` | List all entry paths |
| `async delete(path)` | Delete an entry |

### VectorMemory Constructor

| Parameter | Type | Description |
|-----------|------|-------------|
| `collection_name` | `str` | Qdrant collection name |
| `embed_fn` | `Callable[[str], Awaitable[list[float]]]` | Async embedding function |
| `embedding_dim` | `int` | Vector dimension |
| `qdrant_url` | `str` | Qdrant server URL |

## Router

Routing system. Defined in `agentflow.router`.

| Class | Description |
|-------|-------------|
| `RouterEngine` | YAML rules + LLM fallback routing |
| `DomainRouter` | Two-tier hierarchical domain routing |
| `RoutingResult` | Routing decision: target, method, confidence, domain |
| `RuleEvaluator` | Evaluates YAML rule conditions |

### RoutingResult Fields

| Field | Type | Description |
|-------|------|-------------|
| `target` | `str` | Agent or workflow name |
| `method` | `str` | `"rule"`, `"llm"`, `"fallback"`, or `"domain:*"` |
| `confidence` | `float` | 1.0 for rules, 0.8 for LLM |
| `domain` | `str \| None` | Domain name (hierarchical routing only) |

## Workflow

Workflow execution. Defined in `agentflow.workflow`.

| Class | Description |
|-------|-------------|
| `WorkflowExecutor` | Runs a complete workflow DAG |
| `WorkflowDAG` | Validates and traverses the node graph |
| `NodeRunner` | Executes a single workflow node |

## Telemetry

Observability integrations. Defined in `agentflow.telemetry`.

| Class | Description |
|-------|-------------|
| `LangfuseEventHandler` | EventHandler implementation for Langfuse (requires `[telemetry]` extra) |

!!! note "Lazy Import"
    `LangfuseEventHandler` is lazily imported to avoid requiring the `langfuse` package at module load time. It is only loaded when accessed.
