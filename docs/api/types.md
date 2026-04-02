# Core Data Types

The canonical data structures shared across all modules of AgentFlow are defined in `agentflow.types`. These are provider-agnostic, meaning each LLM provider adapter translates directly to and from these core types.

## Enums

### `Role`
Message role in a conversation.
- `SYSTEM`
- `USER`
- `ASSISTANT`
- `TOOL_RESULT`

### `NodeMode`
Execution mode for workflow nodes.
- `SYNC`
- `PARALLEL`
- `ASYNC`

## Dataclasses

### `ToolCall`
A request from the LLM to invoke a tool.
- **id** (`str`): The unique identifier for the tool call.
- **name** (`str`): The registered name of the tool to invoke.
- **input** (`dict[str, Any]`): The parsed JSON arguments provided by the LLM.

### `ToolResult`
The result of executing a local or HTTP tool call.
- **tool_call_id** (`str`): The ID linking back to the original `ToolCall`.
- **content** (`str`): The stringified output or JSON result from the tool.
- **is_error** (`bool`, default `False`): Flag set to True if the tool execution raised an exception.

### `Message`
A single message in a conversation.
- **role** (`Role`): The role of the sender.
- **content** (`str`): The content of the message.
- **tool_calls** (`list[ToolCall]`): List of tools the LLM requested.
- **tool_results** (`list[ToolResult]`): Output results returned back to the LLM.
- **metadata** (`dict[str, Any]`): Optional dictionary for tracing or provider-specific metrics.

### `AgentResponse`
Unified response from any LLM provider adapter.
- **text** (`str`): The generated text response.
- **tool_calls** (`list[ToolCall]`): Any tool requests parsed from the generation.
- **stop_reason** (`str`): Why generation stopped (e.g., `"end_turn"`, `"tool_use"`, `"max_tokens"`).
- **usage** (`dict[str, int]`): Token usage metrics (e.g., input vs output tokens).
- **raw** (`Any`): Original provider network response for debugging.
- **metadata** (`dict[str, Any]`): Provider-specific extra metadata (e.g., thinking text).

### `NodeOutput`
Output produced directly from a single workflow node execution.
- **node_id** (`str`): The ID of the node in the DAG.
- **agent_id** (`str`): The identifier of the agent / handler that executed.
- **text** (`str`): Processed textual output.
- **artifacts** (`dict[str, Any]`): Structured extracted components or binary data identifiers passed into the `ArtifactStore`.
- **metadata** (`dict[str, Any]`): Node-level trace metrics.
