# Changelog

All notable changes to AgentFlow are documented here.

## 0.10.0

### Added

- **`NodeOutput.metadata["tool_calls"]` on `AgentExecutor.run()`.** Every tool call made during a
  run — across all tool-use rounds, on both the normal-completion and exhausted-tool-rounds return
  paths — is now included as `[{"name": str, "input": dict, "result": str, "is_error": bool}, ...]`.
  Previously the only way to observe an agent's tool calls was subscribing an `EventBus` to
  `TOOL_CALLED`/`TOOL_RESULT` before calling `run()`; that's still supported, but callers who just
  want "what tools did this run use and what did they return" no longer need to set up event
  plumbing for it.
- **`onError: abort` on workflow nodes.** By default, a node that raises still doesn't abort its
  workflow — the failure is captured into that node's `NodeOutput` (`metadata={"error": True}`)
  and the DAG keeps running, same as before. Set `onError: abort` on a specific node to opt out of
  that: its exception now propagates out of `WorkflowExecutor.run()` as `WorkflowNodeError`
  (carrying `.node_id` and `.original`) instead of being swallowed. Applies uniformly across
  `sync`, `parallel`, `async`, and `foreach` nodes.

### Fixed

- **`mode: async` now actually does what the docs always said it did.** Nodes marked `mode: async`
  were accepted by the workflow schema but silently executed identically to `sync` — only
  `parallel` was ever branched on in `WorkflowExecutor`. Async nodes are now genuinely
  fire-and-forget: dispatched without the wave loop waiting on them, so a sibling with no
  dependency on the async node doesn't get blocked behind it. `WorkflowExecutor.run()` still waits
  for and captures every async node's result (or error) before returning, so nothing is silently
  dropped even when nothing in the DAG depends on it.
- **`WorkflowNode.mode` and the new `onError` field are now validated.** A typo like
  `mode: asnyc` used to be silently accepted and treated as `sync`; it's now a `ValueError` at
  config-parse time. Same for an unrecognized `onError` value.
- **`RuleEvaluator` conditions fail loudly on unrecognized syntax instead of silently evaluating
  false.** A condition matching none of the supported patterns — e.g. a typo, or (previously)
  a double-quoted string literal — used to return `False` and let the caller fall through to the
  next rule or the router's fallback target, indistinguishable from a legitimate non-match. It now
  raises `RuleConditionError`. Also: string literals accept double quotes as well as single quotes
  (`area == "schematic"`, not just `area == 'schematic'`) — previously only single quotes worked
  for `==`, `!=`, and `'substring' in field`; `field in [...]` already accepted either.

## 0.9.0

### Changed

- **Relicensed from MIT to Apache License 2.0.** Releases 0.8.2 and earlier remain available
  under the MIT License; those rights are not revoked by this change. See
  [LICENSE](https://github.com/GittieLabs/agentflow/blob/main/LICENSE) and
  [NOTICE](https://github.com/GittieLabs/agentflow/blob/main/NOTICE).

## 0.8.2

### Fixed

- **`AnthropicProvider` support for Claude's newest reasoning model lines (first hit: `claude-sonnet-5`).** These models reject an explicit `temperature` outright ("`temperature` is deprecated for this model") and use a newer adaptive-thinking + effort interface (`thinking: {"type": "adaptive"}` + `output_config: {"effort": ...}`) instead of the older, fixed `budget_tokens` one. `chat()` now: (1) recognizes a `-low`/`-medium`/`-high` model-name suffix to opt into adaptive thinking at that effort level, mirroring `GoogleGenAIProvider`'s identical convention for Gemini thinking models rather than inventing a second, different one; (2) retries once without `temperature` on the specific "temperature is deprecated" 400, rather than hardcoding a model-name allowlist that would need updating for every future release.
- **Stale default models.** `AnthropicProvider`'s default is now `claude-sonnet-5` (was `claude-sonnet-4-6`). `GoogleGenAIProvider`'s default is now `gemini-flash-latest` (was `gemini-2.5-flash-preview`, which 404s — it no longer exists on Google's real model list). `gemini-flash-latest` is Google's own stable rolling alias, chosen over a dated snapshot so this default doesn't itself go stale the same way.

## 0.7.4

### Added

- **`HANDLER_RESULT` event from code handler nodes.** Handler nodes (registered Python functions) now emit a `HANDLER_RESULT` event after execution, carrying the full `NodeOutput` (text, artifacts, metadata). Observers — such as asset collectors — can react to handler outputs the same way they react to `TOOL_RESULT` events from agent nodes, without parsing text.

## 0.7.3

### Added

- **`raw_result` in `TOOL_RESULT` for local tools.** `LocalToolDispatcher` now parses JSON results and sets `last_raw_tool_result` (the same `ContextVar` used by `HTTPToolDispatcher`). `TOOL_RESULT` events for locally dispatched tools now include `raw_result` with the structured dict output, enabling asset collectors to capture document URLs and other structured data from local tools.

## 0.7.2

### Added

- **Enriched `TOOL_RESULT` events.** `HTTPToolDispatcher` stashes the pre-formatted tool result dict in an asyncio-safe `ContextVar`. `AgentExecutor` reads it and includes `input`, `result` (formatted string), and `raw_result` (raw dict) in every `TOOL_RESULT` event. Downstream consumers can now capture structured tool output at call time without regex-parsing the agent's final response.

## 0.7.1

### Fixed

- **Langfuse SDK compatibility.** `LangfuseEventHandler` now wraps `resource_attributes` initialization in a `try/except TypeError`. Langfuse SDK 4.0.x does not support the `resource_attributes` parameter; older SDK versions skip it gracefully rather than raising at startup.

## 0.7.0

### Added

- **Langfuse session and trace context.** New `set_trace_context()` method on `LangfuseEventHandler` lets callers inject per-request conversation context — `session_id`, `trace_name`, `user_id`, `tags`, and `metadata` — before each workflow execution. Context is consumed once when `WORKFLOW_STARTED` fires, then cleared.
- **`resource_attributes` parameter.** `LangfuseEventHandler.__init__` now accepts `resource_attributes: dict[str, str]` for attaching static service metadata (e.g. `service.name`, `service.version`) to the Langfuse client instance.
- **`DOMAIN_ROUTED` span.** `LangfuseEventHandler` now handles the `DOMAIN_ROUTED` event, recording the routing decision as a child span on the root trace with `domain`, `target`, `confidence`, and `router` metadata.

## 0.6.0

### Added

- **Code handler nodes.** Workflow nodes can now specify `handler: <name>` instead of `agent: <name>`. Handlers are registered Python async functions (`async def fn(message: str, prior_outputs: dict) -> NodeOutput`) passed to `WorkflowExecutor(handlers={...})`. Use handler nodes for deterministic processing steps that don't need an LLM call.

  ```yaml
  nodes:
    - id: transform
      handler: normalize_text
      inputs:
        message: "extract.text"
  ```

  ```python
  async def normalize_text(message: str, prior_outputs: dict) -> NodeOutput:
      return NodeOutput(node_id="transform", agent_id="normalize_text", text=message.lower())

  executor = WorkflowExecutor(
      config=wf_config,
      runner_factory=runner_factory,
      handlers={"normalize_text": normalize_text},
  )
  ```

- **Foreach iteration.** Workflow nodes can specify `foreach: <dotted-ref>` pointing to a list artifact from a prior node. The node body executes once per item; each iteration receives `loop_item`, `loop_index`, `loop_total`, and `loop_prior_results` injected into the message. Results are collected into `artifacts["results"]` on the synthetic `__loop__` output.

  ```yaml
  nodes:
    - id: extract
      handler: extract_items
      next: [process]
    - id: process
      agent: item_processor
      foreach: "extract.artifacts.items"
  ```

  Handler nodes and foreach can be combined: a handler node with `foreach` iterates the handler function over the list.

- **`HANDLER_RESULT` event constant.** Importable from `agentflow`.

## 0.5.2

### Changed

- **Named inputs deliver labeled sections to agents.** When a workflow node
  defines `inputs` with keys other than `message`, each key is now resolved
  in YAML-definition order and delivered as a labeled `[key]\nvalue` section.
  Previously, non-`message` keys were processed through `_predecessors()` and
  concatenated without labels in non-deterministic (set iteration) order.

  Before (0.5.1 behavior — unlabeled, unordered):

  ```
  ## Section 1
  Body text.

  # Outline content
  ```

  After (0.5.2 behavior — labeled, definition order):

  ```
  [outline]
  # Outline content

  [sections]
  ## Section 1
  Body text.
  ```

  **Migration:** Agent system prompts that receive named inputs should be
  updated to reference the labeled sections by key name.  The `message` key
  pattern is unchanged.

### Fixed

- `NodeRunner._predecessors()` renamed to `_input_node_ids()` with corrected
  docstring.  The method is used only for scratchpad context filtering; it is
  no longer involved in message resolution.

### Added

- Four new tests covering named inputs: labeled section format, definition
  order preservation, missing upstream node handling, and end-to-end workflow
  integration.

## 0.5.1

### Fixed

- Release workflow: no longer fails if a GitHub release already exists for
  the current tag.

## 0.5.0 (alpha)

### Breaking Changes

- **VectorMemory is now embedding-agnostic.** The constructor requires `embed_fn` (an async `str -> list[float]` callable) and `embedding_dim` instead of using a hardcoded embedding model. This decouples VectorMemory from any specific embedding provider.

### Changed

- Migrated embedding from deprecated `text-embedding-004` to `gemini-embedding-001` in examples and tests.

## 0.4.0 (alpha)

### Added

- **Hierarchical domain routing.** New `DomainRouter` class implements two-tier routing: a top-level router classifies messages into domains, then per-domain routers pick specific agents or workflows.
- New `DomainConfig` schema for `*.domain.md` files.
- `ConfigLoader` now scans `context/domains/` for domain definitions.
- `DOMAIN_ROUTED` event constant for domain routing telemetry.
- `RoutingResult` now includes a `domain` field.

## 0.3.3

### Fixed

- Subdirectory context loading: `ConfigLoader` now correctly loads `*.context.md` files from arbitrary subdirectories (not just `shared/`).

## 0.3.0

### Added

- Context profiles (`*.context.md` with `type: profile`) for conditional context loading.
- `ContextProfile` and `ConditionalInclude` schemas.
- `ConfigLoader.get_profile()` and `ConfigLoader.is_profile()` methods.
- Shared context files loaded from all subdirectories, not just `agents/`.

## 0.2.0

### Added

- `WorkflowExecutor` with DAG-based execution.
- `NodeRunner` for per-node agent execution.
- `Scratchpad` for per-node working memory and summaries.
- `ArtifactStore` for named artifact storage.
- `MultiUserHistory` and `HistoryPersistence` for multi-user session support.
- `FileMemory` and `VectorMemory` backends.
- `MemoryManager` for coordinating memory operations.
- `ComplexityClassifier`, `DAGExecutor`, `Plan`, `PlanStep` orchestration primitives.
- `LangfuseEventHandler` for Langfuse telemetry integration.
- `GoogleGenAIProvider` for Google Gemini models.

## 0.1.0

### Added

- Initial release.
- `ConfigLoader` with `.prompt.md`, `.workflow.md`, `.context.md` parsing.
- `RouterEngine` with YAML rules and LLM fallback.
- `RuleEvaluator` for Python expression-based routing rules.
- `AgentExecutor` with tool loop support.
- `ContextAssembler` and `PromptTemplate`.
- `EventBus` pub/sub event system.
- `ToolRegistry`, `LocalToolDispatcher`, `HTTPToolDispatcher`.
- `AnthropicProvider`, `OpenAICompatProvider`, `MockLLMProvider`.
- `FileSystemStorage`, `InMemoryStorage`, `S3Storage` backends.
- `SessionManager` and `Session`.
- Core types: `Message`, `AgentResponse`, `ToolCall`, `ToolResult`, `NodeOutput`.
- Protocols: `LLMProvider`, `StorageBackend`, `ToolDispatcher`, `MemoryStore`, `EventHandler`.
