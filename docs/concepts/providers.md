# LLM Providers

AgentFlow ships with adapters for major LLM providers. All providers implement the `LLMProvider` protocol and translate between AgentFlow's canonical types (`Message`, `AgentResponse`, `ToolCall`) and each provider's native SDK.

## Available Providers

| Class | Provider | Install Extra | SDK |
|-------|----------|--------------|-----|
| `AnthropicProvider` | Anthropic Claude | `anthropic` | `anthropic>=0.42.0` |
| `OpenAICompatProvider` | OpenAI, Azure, Ollama, vLLM | `openai` | `openai>=1.0.0` |
| `GoogleGenAIProvider` | Google Gemini | `google` | `google-genai>=1.0.0` |
| `MockLLMProvider` | Testing / development | *(core)* | None |

## The LLMProvider Protocol

Every provider implements this async interface:

```python
class LLMProvider(Protocol):
    async def chat(
        self,
        messages: list[Message],
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        params: dict[str, Any] | None = None,
    ) -> AgentResponse: ...
```

This means you can use any object with a matching `chat` method as a provider -- no subclassing needed.

## Vendor Parameters (`params`)

Vendors add parameters faster than any framework can name them -- reasoning effort, thinking
budgets, and whatever ships next. AgentFlow does not model which parameter each model supports,
because that cannot be kept current. Instead `params` is forwarded **verbatim** to the underlying
SDK call, and the caller owns correctness.

```python
# Anthropic: adaptive thinking with an effort level
await provider.chat(messages, params={
    "thinking": {"type": "adaptive"},
    "output_config": {"effort": "high"},
})

# OpenAI and compatible servers
await provider.chat(messages, params={"reasoning_effort": "high"})

# Gemini -- merged into GenerateContentConfig
await provider.chat(messages, params={"thinking_config": {"thinking_level": "high"}})
```

Per agent, declare them in front matter:

```yaml
---
name: board_advisor
model: claude-sonnet-5
params:
  thinking: {type: adaptive}
  output_config: {effort: high}
---
```

Two rules are worth knowing:

- **A parameter the model ignores is your business, not an error.** An OpenAI-compatible endpoint
  such as a local Ollama will happily accept `reasoning_effort` and do nothing with it. AgentFlow
  does not try to predict that.
- **A parameter that would override AgentFlow's own arguments is refused**, loudly, naming every
  offending key. `params` changes *how* a call is made, never *what* is asked -- so it cannot
  rewrite `model`, `messages`, `system` or `tools`. Set those where they belong.

!!! warning "Changed in 0.11.0"
    Earlier versions selected Anthropic and Gemini reasoning effort by appending `-low`,
    `-medium` or `-high` to the **model name**, parsed with `rsplit("-", 1)`. That convention is
    removed. It silently truncated any legitimate model whose real name ended in one of those
    words, was invisible to callers, and had no equivalent on `openai_compat`. Move any such model
    name back to its real value and pass the effort through `params` instead.

## Provider Setup

### Anthropic Claude

```bash
pip install "gittielabs-agentflow[anthropic]"
export ANTHROPIC_API_KEY="sk-ant-..."
```

```python
from agentflow import AnthropicProvider

provider = AnthropicProvider()
```

Reference the provider in agent config files:

```yaml
provider: anthropic
model: claude-sonnet-4-6
```

### OpenAI / OpenAI-Compatible

```bash
pip install "gittielabs-agentflow[openai]"
export OPENAI_API_KEY="sk-..."
```

```python
from agentflow import OpenAICompatProvider

# Standard OpenAI
provider = OpenAICompatProvider()

# Azure OpenAI, Ollama, or any compatible endpoint
provider = OpenAICompatProvider(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
)
```

In agent config:

```yaml
provider: openai
model: gpt-4o
```

### Google Gemini

```bash
pip install "gittielabs-agentflow[google]"
export GOOGLE_API_KEY="..."
```

```python
from agentflow import GoogleGenAIProvider

provider = GoogleGenAIProvider()
```

In agent config:

```yaml
provider: google
model: gemini-2.0-flash
```

### Mock Provider (Testing)

The `MockLLMProvider` returns configurable responses without making API calls. Useful for testing workflows and routing logic.

```python
from agentflow import MockLLMProvider

provider = MockLLMProvider(default_response="This is a test response.")
```

## Using Multiple Providers

Different agents can use different providers. The provider is determined by the `provider` field in each agent's `.prompt.md` file:

```markdown
---
name: fast_classifier
provider: google
model: gemini-2.0-flash
temperature: 0.0
---
```

```markdown
---
name: deep_researcher
provider: anthropic
model: claude-sonnet-4-6
temperature: 0.7
---
```

When setting up execution, create a provider instance for each backend your agents need.

## Building a Custom Provider

Any class that implements the `LLMProvider` protocol works as a provider. See the [Custom Provider guide](../guides/custom-provider.md) for a complete walkthrough.
