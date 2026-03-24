# Domain Routing

Hierarchical domain routing organizes agents and workflows into logical groups, each with its own routing boundary. This is useful for large systems where a flat list of agents becomes unwieldy.

## How It Works

Domain routing uses a two-tier architecture:

```
User Message
    |
    v
Top-Level Router         -- cheap/fast LLM classifies into domain
    |
    +---> "content"       -- DomainRouter delegates to content domain
    |       |
    |       v
    |     Content Router  -- domain-specific LLM picks agent/workflow
    |       |
    |       +---> content_researcher
    |       +---> content_formatter
    |       +---> content-creation workflow
    |
    +---> "support"       -- DomainRouter delegates to support domain
    |       |
    |       v
    |     Support Router
    |       +---> ticket_handler
    |       +---> faq_agent
    |
    +---> "direct"        -- bypass domain routing, use default agent
```

## Step 1: Define Domains

Create domain files in `context/domains/`:

**`context/domains/content.domain.md`**:

```markdown
---
name: content
description: "Content research, creation, editing, and publishing"
routerModel: claude-sonnet-4-6
routerTemperature: 0.0
agents:
  - content_researcher
  - content_formatter
workflows:
  - content-research
  - content-creation
contextFiles:
  - shared/content-guidelines.context.md
fallback: content_researcher
---

Content domain: handles all content-related requests including
research, writing, editing, and publishing workflows.
```

**`context/domains/support.domain.md`**:

```markdown
---
name: support
description: "Customer support, FAQ, and ticket management"
routerModel: claude-sonnet-4-6
routerTemperature: 0.0
agents:
  - ticket_handler
  - faq_agent
workflows:
  - escalation-workflow
fallback: faq_agent
---

Support domain: handles customer inquiries, FAQ responses,
and support ticket management.
```

### Domain Config Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | *required* | Domain identifier |
| `description` | `str` | `""` | What this domain handles (used by the router LLM) |
| `routerModel` | `str` | `"claude-sonnet-4-6"` | LLM model for intra-domain routing |
| `routerTemperature` | `float` | `0.0` | Temperature for routing (low = deterministic) |
| `agents` | `list[str]` | `[]` | Agents belonging to this domain |
| `workflows` | `list[str]` | `[]` | Workflows belonging to this domain |
| `contextFiles` | `list[str]` | `[]` | Shared context for all agents in the domain |
| `fallback` | `str` | `""` | Default agent when intra-domain routing is ambiguous |

## Step 2: Configure the Top-Level Router

The top-level router's targets are domain names (plus `"direct"` for pass-through):

**`context/router.prompt.md`**:

```markdown
---
name: main_router
routing_rules:
  - if: "'content' in message or 'write' in message or 'blog' in message"
    routeTo: content
  - if: "'support' in message or 'help' in message or 'ticket' in message"
    routeTo: support
fallback: direct
llmFallback: true
---

Classify the user's message into one of these categories:
- content: Content creation, research, editing, or publishing
- support: Customer support, FAQ, or ticket management
- direct: General requests that don't fit a specific domain

Respond with just the category name.
```

## Step 3: Set Up the DomainRouter

```python
import asyncio
from agentflow import (
    ConfigLoader,
    DomainRouter,
    RouterEngine,
    AnthropicProvider,
    EventBus,
)


async def main():
    # Load configs (including domains)
    loader = ConfigLoader("./context")
    loader.load()

    events = EventBus()

    # Create a factory that produces LLM providers for different models
    def llm_factory(model: str) -> AnthropicProvider:
        return AnthropicProvider(model=model)

    # Set up top-level router
    router_config, router_prompt = loader.router
    domain_names = list(loader.domains.keys()) + ["direct"]

    top_router = RouterEngine(
        config=router_config,
        router_prompt=router_prompt,
        available_targets=domain_names,
        llm=AnthropicProvider(),
        event_bus=events,
    )

    # Create domain router
    domain_router = DomainRouter(
        top_router=top_router,
        loader=loader,
        llm_factory=llm_factory,
        direct_target="general_assistant",
        event_bus=events,
    )

    # Route messages
    result = await domain_router.route("Write a blog post about AI safety")
    print(f"Target: {result.target}")   # "content_researcher" or similar
    print(f"Domain: {result.domain}")   # "content"
    print(f"Method: {result.method}")   # "domain:content"

    result = await domain_router.route("I need help with my order")
    print(f"Target: {result.target}")   # "faq_agent" or "ticket_handler"
    print(f"Domain: {result.domain}")   # "support"


asyncio.run(main())
```

## How DomainRouter Works

1. The top-level `RouterEngine` classifies the message into a domain name (e.g., `"content"`) or `"direct"`.

2. If `"direct"` (or the static fallback), the `DomainRouter` returns immediately with the `direct_target` agent.

3. Otherwise, it looks up the `DomainConfig` for that domain, creates (and caches) a domain-level `RouterEngine` using the domain's `routerModel`, and routes to a specific agent or workflow within the domain.

4. The `RoutingResult` includes a `domain` field so callers can track which domain handled the request.

## LLM Factory

The `llm_factory` parameter is a callable that creates an `LLMProvider` for a given model name. Each domain can specify its own `routerModel`, and the factory creates the appropriate provider:

```python
def llm_factory(model: str) -> LLMProvider:
    # Could use different providers for different models
    if "gemini" in model:
        return GoogleGenAIProvider(model=model)
    return AnthropicProvider(model=model)
```

## Events

Domain routing emits `DOMAIN_ROUTED` events:

```python
from agentflow import EventBus, DOMAIN_ROUTED

events = EventBus()

class DomainTracker:
    async def on_event(self, event_type: str, data: dict) -> None:
        print(f"Domain: {data.get('domain')}")
        print(f"Target: {data.get('target')}")
        print(f"Method: {data.get('method')}")

events.on(DOMAIN_ROUTED, DomainTracker())
```

## When to Use Domain Routing

**Use domains when:**

- You have 10+ agents and flat routing becomes unclear
- Different areas of your system need different routing models or temperatures
- You want to scope memory, context, and telemetry by domain
- Teams own different domains independently

**Use flat routing when:**

- You have a small number of agents (< 10)
- Simple YAML rules are sufficient
- You want minimal latency (domain routing adds one LLM call)
