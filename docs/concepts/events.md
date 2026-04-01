# Events & Telemetry

AgentFlow uses a pub/sub event system for observability. The `EventBus` lets you hook into every stage of framework execution without coupling to any specific logging or metrics system.

## EventBus

The `EventBus` manages event subscriptions and dispatches events to handlers. Handler errors are caught and logged -- they never break execution flow.

```python
from agentflow import EventBus

events = EventBus()
```

### Subscribing to Events

Register a handler for a specific event type:

```python
class MyHandler:
    async def on_event(self, event_type: str, data: dict) -> None:
        print(f"[{event_type}] {data}")

handler = MyHandler()
events.on("node_started", handler)
events.on("node_completed", handler)
```

### Unsubscribing

```python
events.off("node_started", handler)
```

### Emitting Events

Framework components emit events automatically. You can also emit custom events:

```python
await events.emit("custom_event", {"key": "value"})
```

## Standard Event Types

AgentFlow defines these event type constants:

| Constant | Event Type | Emitted When |
|----------|-----------|--------------|
| `WORKFLOW_STARTED` | `"workflow_started"` | Workflow execution begins |
| `WORKFLOW_COMPLETED` | `"workflow_completed"` | Workflow execution finishes |
| `NODE_STARTED` | `"node_started"` | A workflow node begins execution |
| `NODE_COMPLETED` | `"node_completed"` | A workflow node finishes |
| `TOOL_CALLED` | `"tool_called"` | An agent invokes a tool |
| `TOOL_RESULT` | `"tool_result"` | A tool returns its result (includes `raw_result`) |
| `HANDLER_RESULT` | `"handler_result"` | A code handler node finishes execution |
| `LLM_CALL_STARTED` | `"llm_call_started"` | An LLM API call begins |
| `LLM_CALL_COMPLETED` | `"llm_call_completed"` | An LLM API call finishes |
| `ROUTER_DECISION` | `"router_decision"` | Router makes a routing decision |
| `DOMAIN_ROUTED` | `"domain_routed"` | Domain router classifies a message |
| `SESSION_CREATED` | `"session_created"` | A new session is created |
| `MEMORY_STORED` | `"memory_stored"` | A memory entry is stored |
| `ERROR` | `"error"` | An error occurs during execution |

Import constants directly:

```python
from agentflow import (
    WORKFLOW_STARTED, WORKFLOW_COMPLETED,
    NODE_STARTED, NODE_COMPLETED,
    TOOL_CALLED, TOOL_RESULT, HANDLER_RESULT,
    LLM_CALL_STARTED, LLM_CALL_COMPLETED,
    DOMAIN_ROUTED, ERROR,
)
```

## EventHandler Protocol

Any class implementing the `EventHandler` protocol can be registered as a handler:

```python
class EventHandler(Protocol):
    async def on_event(self, event_type: str, data: dict[str, Any]) -> None: ...
```

No inheritance required -- just implement the method.

## Built-in Handlers

### LoggingEventHandler

Logs all events at INFO level using Python's standard logging:

```python
from agentflow.events import LoggingEventHandler

handler = LoggingEventHandler()
events.on("node_started", handler)
events.on("node_completed", handler)
events.on("error", handler)
```

## Langfuse Telemetry

AgentFlow includes a `LangfuseEventHandler` for production observability via [Langfuse](https://langfuse.com/).

### Installation

```bash
pip install "gittielabs-agentflow[telemetry]"
```

### Setup

```bash
export LANGFUSE_PUBLIC_KEY="pk-..."
export LANGFUSE_SECRET_KEY="sk-..."
```

```python
from agentflow import (
    LangfuseEventHandler, EventBus,
    WORKFLOW_STARTED, WORKFLOW_COMPLETED,
    NODE_STARTED, NODE_COMPLETED,
    LLM_CALL_COMPLETED, TOOL_CALLED, DOMAIN_ROUTED, ERROR,
)

events = EventBus()
langfuse_handler = LangfuseEventHandler(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
    # Optional: tag the service in Langfuse
    resource_attributes={"service.name": "my-app", "service.version": "1.0.0"},
)

for event_type in (WORKFLOW_STARTED, WORKFLOW_COMPLETED, NODE_STARTED, NODE_COMPLETED,
                   LLM_CALL_COMPLETED, TOOL_CALLED, DOMAIN_ROUTED, ERROR):
    events.on(event_type, langfuse_handler)

# On shutdown, flush buffered events:
langfuse_handler.flush()
```

### Per-request trace context

Call `set_trace_context()` before each workflow execution to attach conversation-level metadata to the Langfuse trace:

```python
langfuse_handler.set_trace_context(
    session_id="signal:default-pipeline",   # groups traces into a session
    trace_name="signal:default-pipeline",   # overrides the root trace name
    user_id="+14155550100",                 # Langfuse user identifier
    tags=["signal", "production"],
    metadata={"channel": "signal", "git_sha": "abc123"},
)

# Now run the workflow — context is consumed on WORKFLOW_STARTED and cleared
outputs = await executor.run(message, session_id=session_id)
```

Context is **one-shot**: it is applied to the next `WORKFLOW_STARTED` event, then cleared. Call `set_trace_context()` again before the next workflow if needed.

### Langfuse span hierarchy

| Langfuse observation | Created by |
|----------------------|------------|
| Root span (trace) | `WORKFLOW_STARTED` |
| Node span | `NODE_STARTED` |
| LLM generation | `LLM_CALL_COMPLETED` |
| Tool span | `TOOL_CALLED` |
| Routing span | `DOMAIN_ROUTED` |

The `LangfuseEventHandler` is lazily imported to avoid requiring the `langfuse` package at import time. It is only loaded when accessed.

### SDK compatibility

`resource_attributes` requires Langfuse SDK ≥ 4.1. On older SDK versions the parameter is silently ignored — no error is raised.

## Custom Event Handler Example

Build a handler that tracks LLM costs:

```python
from agentflow import EventBus, LLM_CALL_COMPLETED

class CostTracker:
    def __init__(self):
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    async def on_event(self, event_type: str, data: dict) -> None:
        usage = data.get("usage", {})
        self.total_input_tokens += usage.get("input_tokens", 0)
        self.total_output_tokens += usage.get("output_tokens", 0)

    @property
    def summary(self):
        return {
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
        }

tracker = CostTracker()
events = EventBus()
events.on(LLM_CALL_COMPLETED, tracker)

# After running workflows...
print(tracker.summary)
```

## Error Handling

Handler errors never propagate to the calling code. If a handler raises an exception, it is logged and execution continues:

```python
class FlakyHandler:
    async def on_event(self, event_type, data):
        raise RuntimeError("oops")

# This handler will log the error but won't break workflow execution
events.on("node_started", FlakyHandler())
```

This design ensures observability code cannot break production workflows.
