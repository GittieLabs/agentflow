# Configuration Schemas

AgentFlow relies heavily on Pydantic models to validate the YAML front-matter found in your `.md` context, agent, router, workflow, and memory files.
Below are the definitions and properties mapped out.

## Agent Config (`*.prompt.md`)

```yaml
name: researcher
description: Extract data
provider: anthropic
model: claude-sonnet-4-6
temperature: 0.7
max_tokens: 4096
max_tool_rounds: 6
tools:
  - web_search
context_files:
  - rules.md
```

- **name** (`str`): Identifier of the agent
- **description** (`str`): Short functionality description
- **provider** (`str`): Valid LLM provider (e.g. `anthropic`, `google`)
- **model** (`str`): Full identifier for model router strings
- **temperature** (`float`): Generation unpredictability
- **max_tokens** (`int`): Text generation limit
- **max_tool_rounds** (`int`): Maximum times the LLM can recursively invoke tools (default: `6`)
- **tools** (`list[str]`): List of tools referenced by name present in the `ToolRegistry`
- **tool_definitions** (`list[ToolDefinition]`): Inline JSON Schema tool definitions
- **context_files** (`list[str]`): Sub-configs or rules linked directly into the prompt

## Router Config (`router.prompt.md`)

Handles conditional fallbacks before domain distribution.

- **name** (`str`): Defaults to `"router"`
- **routingRules** (`list[RoutingRule]`): Uses `if` evaluation strings to map dynamically to a `routeTo` target.
- **fallback** (`str`): Default routing target.
- **llmFallback** (`bool`): Determines if LLM is queried when rules fail.

## Workflow Config (`*.workflow.md`)

Directed acyclic graph definitions mapping out sequences.

- **name** (`str`): Unique identifier of the DAG.
- **trigger** (`str`): How it boots — `manual`, `api`, `cron`, or `webhook`.
- **callable** (`bool`): Toggle allowing planners to inject the DAG as a single large tool call.
- **nodes** (`list[WorkflowNode]`): Ordered array of operations.

### `WorkflowNode`
- **id** (`str`): Unique node ID
- **agent** (`str | None`): An agent definition file to route this node towards
- **handler** (`str | None`): A local python async function inside `WorkflowExecutor` handlers map
- **foreach** (`str | None`): Dot-notation pointer to an upstream list artifact (triggers mapping multiple executes of this node)
- **next** (`str | list[str] | None`): Next node IDs
- **mode** (`str`): Execution method (`sync`, `parallel`, `async`)
- **inputs** (`dict[str, str]`): Mappings dict from upstream outputs. Example: `{ message: "upstream_node.text" }`

## Domain Config (`*.domain.md`)

Groups related logic under structural boundaries suitable for hierarchical routers.

- **name** (`str`)
- **routerModel** (`str`)
- **routerTemperature** (`float`)
- **agents** (`list[str]`): Array of string agent names exposed
- **workflows** (`list[str]`): Array of DAG names exposed
- **contextFiles** (`list[str]`): Domain-level rule injections
- **fallback** (`str`)
