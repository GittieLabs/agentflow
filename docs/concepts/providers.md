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
    ) -> AgentResponse: ...
```

This means you can use any object with a matching `chat` method as a provider -- no subclassing needed.

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
