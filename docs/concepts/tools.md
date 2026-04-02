# Tools

AgentFlow provides a tool system that lets agents call external functions during execution. Tools can be local Python functions or HTTP endpoints, all managed through a central `ToolRegistry`.

## ToolRegistry

The `ToolRegistry` aggregates multiple tool dispatchers under a single interface:

```python
from agentflow import ToolRegistry

tools = ToolRegistry()
```

### Registering Inline Tools

Register Python functions directly as tools:

```python
async def web_search(query: str) -> str:
    # Your search implementation
    return f"Results for: {query}"

tools.add_tool(
    name="web_search",
    handler=web_search,
    description="Search the web for information",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"}
        },
        "required": ["query"],
    },
)
```

### Registering Dispatchers

For groups of tools served by the same backend, register a dispatcher:

```python
from agentflow import HTTPToolDispatcher

http_tools = HTTPToolDispatcher(base_url="https://api.example.com/tools")
tools.add_dispatcher(
    tool_names={"weather", "stock_price", "news"},
    dispatcher=http_tools,
)
```

### Tool Dispatch

When an agent requests a tool call, the registry routes it:

1. Inline handlers are checked first
2. Then registered dispatchers (by tool name)
3. Unknown tools return an error string

```python
result = await tools.dispatch("web_search", {"query": "AI safety"})
```

### Listing Tools

Get all tool definitions for passing to the LLM:

```python
tool_defs = tools.list_tools()
# Returns list of dicts with name, description, input_schema
```

## ToolDispatcher Protocol

Both `LocalToolDispatcher` and `HTTPToolDispatcher` implement the `ToolDispatcher` protocol:

```python
class ToolDispatcher(Protocol):
    async def dispatch(self, tool_name: str, tool_input: dict[str, Any]) -> str: ...
    def list_tools(self) -> list[dict[str, Any]]: ...
```

## LocalToolDispatcher

Dispatches tool calls to local Python functions:

```python
from agentflow import LocalToolDispatcher

dispatcher = LocalToolDispatcher()

async def calculate(expression: str) -> str:
    result = eval(expression)
    return str(result)

dispatcher.register("calculate", calculate, {
    "name": "calculate",
    "description": "Evaluate a math expression",
    "input_schema": {
        "type": "object",
        "properties": {
            "expression": {"type": "string"}
        },
        "required": ["expression"],
    },
})
```

## HTTPToolDispatcher

Dispatches tool calls as HTTP POST requests to a remote API:

```python
from agentflow import HTTPToolDispatcher

dispatcher = HTTPToolDispatcher(base_url="https://api.example.com")
```

The dispatcher sends POST requests to `{base_url}/{tool_name}` with the tool input as JSON body. This is ideal for distributed architectures where tools are hosted on separate microservices or serverless functions (like AWS Lambda). 

### When to choose Local vs HTTP Dispatcher?

- **Use `LocalToolDispatcher`** when you want zero-network latency overhead, need tools to directly manipulate your local database or state map in memory, or when running everything in a monolithic deployment.
- **Use `HTTPToolDispatcher`** when your tools require heavy isolated compute, are written in languages other than Python (e.g. Node.js microservices), or if you want strict security boundaries around what arbitrary code your LLM agents can trigger.

## Referencing Tools in Agent Config

Agent `.prompt.md` files reference tools by name:

```markdown
---
name: researcher
tools: [web_search, summarize, calculate]
---
```

The `AgentExecutor` uses the `ToolRegistry` to resolve these names to actual tool definitions and handlers at runtime.

### Inline Tool Definitions

You can also define tool schemas directly in the agent config:

```markdown
---
name: data_agent
tool_definitions:
  - name: query_database
    description: "Run a SQL query against the analytics database"
    input_schema:
      type: object
      properties:
        sql:
          type: string
          description: "SQL query to execute"
      required: [sql]
---
```

## Tool Execution Loop

During agent execution, the `AgentExecutor` runs a tool loop:

1. Send messages to the LLM with available tool definitions
2. If the LLM returns `ToolCall` objects, dispatch each one via the registry
3. Collect `ToolResult` objects and append to the conversation
4. Repeat until the LLM responds without tool calls or `max_tool_rounds` is reached

The `max_tool_rounds` setting in agent config (default: 6) prevents infinite tool loops.

### How Tool Results Drive Reasoning

Tool results are appended into the session history using the `TOOL_RESULT` role. As iterations continue, agents reason over past tool outputs to formulate their next step. 

For instance, an agent might first call a `list_documents` tool. The registry dispatches the call and returns a JSON string of available document paths. During the next iteration of the loop, the agent reads this `ToolResult` and logically decides to call a `read_document` tool loop multiple times based on the parsed list.

Because `ToolResult` outputs can sometimes be very long and consume your token window, it is highly recommended to summarize outputs within your local handler function before returning them (e.g. truncating a web search).

## Tool Types

| Type | Description |
|------|-------------|
| `ToolCall` | Request from the LLM: `id`, `name`, `input` dict |
| `ToolResult` | Execution result: `tool_call_id`, `content`, `is_error` flag |

```python
from agentflow import ToolCall, ToolResult

# These are created automatically during execution
call = ToolCall(id="tc_1", name="web_search", input={"query": "AI safety"})
result = ToolResult(tool_call_id="tc_1", content="Found 10 results...", is_error=False)
```

## Events

Tool calls emit events through the `EventBus`:

| Event | Data |
|-------|------|
| `TOOL_CALLED` | Tool name and input |
| `TOOL_RESULT` | Tool name, result content, error status |
