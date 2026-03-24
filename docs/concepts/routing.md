# Routing

AgentFlow's routing system directs incoming messages to the right agent or workflow. It supports deterministic YAML rules, LLM-based intent classification, and hierarchical domain routing.

## Routing Flow

```
Message arrives
    |
    v
1. YAML rules evaluated in order (first match wins)
    |
    v  (no match)
2. LLM fallback classifies intent (if enabled)
    |
    v  (no match or disabled)
3. Static fallback agent
```

## RouterEngine

`RouterEngine` is the core routing component. It combines rule-based matching with optional LLM classification.

```python
from agentflow import ConfigLoader, RouterEngine, AnthropicProvider, EventBus

loader = ConfigLoader("./context")
loader.load()

router_config, router_prompt = loader.router
available_targets = list(loader.agents.keys()) + list(loader.workflows.keys())

router = RouterEngine(
    config=router_config,
    router_prompt=router_prompt,
    available_targets=available_targets,
    llm=AnthropicProvider(),
    event_bus=EventBus(),
)

result = await router.route("Research the latest AI papers")
print(result.target)      # "research_pipeline"
print(result.method)      # "rule" | "llm" | "fallback"
print(result.confidence)  # 1.0 for rules, 0.8 for LLM
```

## RoutingResult

Every routing decision returns a `RoutingResult`:

| Field | Type | Description |
|-------|------|-------------|
| `target` | `str` | Agent or workflow name to execute |
| `method` | `str` | How the decision was made: `"rule"`, `"llm"`, `"fallback"`, or `"domain:*"` |
| `confidence` | `float` | Confidence score (1.0 for rules, 0.8 for LLM) |
| `domain` | `str \| None` | Domain that handled routing (for hierarchical routing) |

## YAML Routing Rules

Rules are defined in `router.prompt.md` front-matter. Each rule has an `if` condition (a Python expression) and a `routeTo` target:

```yaml
routing_rules:
  - if: "'research' in message or 'find' in message"
    routeTo: research_pipeline
  - if: "'analyze' in message"
    routeTo: analyzer
  - if: "'help' in message and 'code' in message"
    routeTo: code_assistant
```

### Rule Evaluation

The `RuleEvaluator` evaluates each rule's `if` condition as a Python expression against a context dictionary. The context always includes:

- `message` -- the user's message text

You can pass additional context variables:

```python
result = await router.route(
    "Help me with billing",
    context={"channel": "support", "user_tier": "premium"},
)
```

Then use them in rules:

```yaml
- if: "'billing' in message and user_tier == 'premium'"
  routeTo: premium_support
```

Rules are evaluated in order. The first match wins.

## LLM Fallback

When no YAML rule matches and `llmFallback: true`, the router asks an LLM to classify the message into one of the available targets:

```yaml
fallback: general_assistant
llmFallback: true
```

The LLM receives a system prompt instructing it to respond with just the target name from the available list. The router validates that the LLM's choice is a known target.

The Markdown body of `router.prompt.md` is used as the LLM's system prompt. If empty, a default classification prompt is used.

## Static Fallback

If both rules and LLM classification fail (or LLM fallback is disabled), the `fallback` target is used.

## Hierarchical Domain Routing

For larger systems, `DomainRouter` adds a two-tier routing structure. See the [Domain Routing guide](../guides/domain-routing.md) for setup details.

The top-level router classifies messages into domains (e.g., "content", "support", "direct"). Each domain has its own `RouterEngine` that routes to specific agents or workflows within that domain.

```python
from agentflow import DomainRouter

domain_router = DomainRouter(
    top_router=top_router_engine,
    loader=loader,
    llm_factory=lambda model: AnthropicProvider(model=model),
    direct_target="default_agent",
    event_bus=events,
)

result = await domain_router.route("Write a blog post about AI")
print(result.target)  # "content_writer"
print(result.domain)  # "content"
```

## Events

Routing decisions emit `ROUTER_DECISION` and `DOMAIN_ROUTED` events through the `EventBus`:

```python
from agentflow import EventBus, DOMAIN_ROUTED

events = EventBus()

class RoutingLogger:
    async def on_event(self, event_type, data):
        print(f"Routed to {data['target']} via {data['method']}")

events.on(DOMAIN_ROUTED, RoutingLogger())
```
