# Custom LLM Provider

AgentFlow's provider system is protocol-based. Any class that implements the `LLMProvider` protocol works as a provider -- no subclassing or registration required.

## The LLMProvider Protocol

```python
from agentflow.types import AgentResponse, Message

class LLMProvider(Protocol):
    async def chat(
        self,
        messages: list[Message],
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AgentResponse: ...
```

Your provider must:

1. Accept a list of `Message` objects and a system prompt
2. Optionally handle tool definitions
3. Return an `AgentResponse`

## Example: Ollama Provider

Here is a complete provider for a local Ollama instance:

```python
from typing import Any

import httpx

from agentflow.types import AgentResponse, Message, Role


class OllamaProvider:
    """LLM provider for local Ollama models."""

    def __init__(
        self,
        model: str = "llama3",
        base_url: str = "http://localhost:11434",
    ) -> None:
        self._model = model
        self._base_url = base_url
        self._client = httpx.AsyncClient(base_url=base_url, timeout=120)

    async def chat(
        self,
        messages: list[Message],
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AgentResponse:
        # Convert AgentFlow messages to Ollama format
        ollama_messages = []
        if system:
            ollama_messages.append({"role": "system", "content": system})

        for msg in messages:
            ollama_messages.append({
                "role": msg.role.value,
                "content": msg.content,
            })

        # Call Ollama API
        response = await self._client.post(
            "/api/chat",
            json={
                "model": self._model,
                "messages": ollama_messages,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
                "stream": False,
            },
        )
        response.raise_for_status()
        data = response.json()

        return AgentResponse(
            text=data["message"]["content"],
            tool_calls=[],
            stop_reason="end_turn",
            usage={
                "input_tokens": data.get("prompt_eval_count", 0),
                "output_tokens": data.get("eval_count", 0),
            },
            raw=data,
        )
```

## Using Your Provider

```python
from agentflow import ConfigLoader, AgentExecutor

provider = OllamaProvider(model="llama3")

# Use it anywhere an LLMProvider is expected
loader = ConfigLoader("./context")
loader.load()

config, system_prompt = loader.get_agent("researcher")
```

## Supporting Tool Calls

If your LLM supports tool calling (function calling), translate the tool definitions and parse tool call responses:

```python
async def chat(
    self,
    messages: list[Message],
    system: str = "",
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> AgentResponse:
    # Convert tools to provider format
    provider_tools = None
    if tools:
        provider_tools = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {}),
                },
            }
            for t in tools
        ]

    # Make API call with tools...
    # ...

    # Parse tool calls from response
    tool_calls = []
    if raw_tool_calls := data.get("tool_calls"):
        for tc in raw_tool_calls:
            tool_calls.append(ToolCall(
                id=tc["id"],
                name=tc["function"]["name"],
                input=tc["function"]["arguments"],
            ))

    return AgentResponse(
        text=data.get("content", ""),
        tool_calls=tool_calls,
        stop_reason="tool_use" if tool_calls else "end_turn",
        usage=usage,
        raw=data,
    )
```

## Key Types

### Message

```python
@dataclass
class Message:
    role: Role          # SYSTEM, USER, ASSISTANT, TOOL_RESULT
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
```

### AgentResponse

```python
@dataclass
class AgentResponse:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"  # "end_turn" | "tool_use" | "max_tokens"
    usage: dict[str, int] = field(default_factory=dict)
    raw: Any = None                # Original provider response
    metadata: dict[str, Any] = field(default_factory=dict)
```

### ToolCall

```python
@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]
```

## Using OpenAICompatProvider as a Shortcut

If your provider offers an OpenAI-compatible API (many do), you can use `OpenAICompatProvider` directly instead of writing a custom class:

```python
from agentflow import OpenAICompatProvider

# vLLM, Ollama (with OpenAI compat), Azure, etc.
provider = OpenAICompatProvider(
    base_url="http://localhost:8000/v1",
    api_key="not-needed",
)
```

## Testing Your Provider

Use the protocol's runtime checkability to verify:

```python
from agentflow import LLMProvider

provider = OllamaProvider()
assert isinstance(provider, LLMProvider)  # Works thanks to @runtime_checkable
```

Test with the `MockLLMProvider` pattern -- write unit tests that verify your provider returns valid `AgentResponse` objects:

```python
import asyncio
from agentflow.types import Message, Role

async def test_provider():
    provider = OllamaProvider(model="llama3")
    response = await provider.chat(
        messages=[Message(role=Role.USER, content="Hello")],
        system="You are a helpful assistant.",
    )
    assert isinstance(response.text, str)
    assert response.stop_reason in ("end_turn", "tool_use", "max_tokens")

asyncio.run(test_provider())
```
