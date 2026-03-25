# Changelog

All notable changes to AgentFlow are documented here.

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
