"""Tests for Phase A: shared context loading and multi-agent routing."""
import pytest

from agentflow.config.loader import ConfigLoader
from agentflow.config.schemas import RouterConfig, RoutingRule
from agentflow.router.engine import RouterEngine, RoutingResult
from agentflow.providers.mock import MockLLMProvider
from agentflow.types import AgentResponse


# ── Shared context loading ────────────────────────────────────────────────────


def test_config_loader_shared_context(tmp_path):
    """ConfigLoader should load shared/*.context.md files."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    shared_dir = tmp_path / "shared"
    shared_dir.mkdir()

    (agents_dir / "test.prompt.md").write_text("""---
name: test_agent
---
Test agent.
""")

    (shared_dir / "persona.context.md").write_text("""---
description: "Test persona"
---
Keith is a tech entrepreneur.
""")

    (shared_dir / "company.context.md").write_text("""---
description: "Company info"
---
HatchWorks builds AI solutions.
""")

    loader = ConfigLoader(tmp_path)
    loader.load()

    # Shared context files are keyed with "shared/" prefix
    body = loader.get_context_body("shared/persona.context.md")
    assert body is not None
    assert "tech entrepreneur" in body

    body2 = loader.get_context_body("shared/company.context.md")
    assert body2 is not None
    assert "HatchWorks" in body2


def test_config_loader_shared_context_missing_dir(tmp_path):
    """ConfigLoader should not fail if shared/ directory doesn't exist."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()

    (agents_dir / "test.prompt.md").write_text("""---
name: test_agent
---
Test agent.
""")

    loader = ConfigLoader(tmp_path)
    loader.load()  # Should not raise

    # No shared context should be found
    assert loader.get_context_body("shared/anything.context.md") is None


def test_config_loader_agent_and_shared_context_coexist(tmp_path):
    """Agent-level and shared context files should not collide."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    shared_dir = tmp_path / "shared"
    shared_dir.mkdir()

    (agents_dir / "test.prompt.md").write_text("""---
name: test_agent
---
Test.
""")
    (agents_dir / "tools.context.md").write_text("""---
description: Agent-level context
---
Agent-level context body.
""")
    (shared_dir / "tools.context.md").write_text("""---
description: Shared context
---
Shared context body.
""")

    loader = ConfigLoader(tmp_path)
    loader.load()

    # Agent context keyed by filename only
    agent_body = loader.get_context_body("tools.context.md")
    assert "Agent-level" in agent_body

    # Shared context keyed with prefix
    shared_body = loader.get_context_body("shared/tools.context.md")
    assert "Shared context" in shared_body


# ── Router integration ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_router_rule_matching():
    """Router should match YAML rules and return the correct target."""
    config = RouterConfig(
        name="test_router",
        routingRules=[
            RoutingRule(**{"if": "'research' in message", "routeTo": "content-research"}),
            RoutingRule(**{"if": "'lead gen' in message", "routeTo": "lead-gen-pipeline"}),
        ],
        fallback="openclaw_default",
        llmFallback=False,
    )

    router = RouterEngine(config=config)

    result = await router.route("Research top AI news this week")
    assert result.target == "content-research"
    assert result.method == "rule"

    result = await router.route("Run lead gen for Hatchworks")
    assert result.target == "lead-gen-pipeline"
    assert result.method == "rule"


@pytest.mark.asyncio
async def test_router_fallback_when_no_rule_matches():
    """Router should fall back to default when no rules match."""
    config = RouterConfig(
        name="test_router",
        routingRules=[
            RoutingRule(**{"if": "'research' in message", "routeTo": "content-research"}),
        ],
        fallback="openclaw_default",
        llmFallback=False,
    )

    router = RouterEngine(config=config)
    result = await router.route("What's the weather today?")
    assert result.target == "openclaw_default"
    assert result.method == "fallback"


@pytest.mark.asyncio
async def test_router_llm_fallback():
    """Router should use LLM fallback when enabled and no rule matches."""
    config = RouterConfig(
        name="test_router",
        routingRules=[],
        fallback="openclaw_default",
        llmFallback=True,
    )

    mock_llm = MockLLMProvider(responses=[
        AgentResponse(text="content-research", stop_reason="end_turn"),
    ])

    router = RouterEngine(
        config=config,
        available_targets=["openclaw_default", "content-research", "lead-gen-pipeline"],
        llm=mock_llm,
    )

    result = await router.route("Tell me about the latest AI developments")
    assert result.target == "content-research"
    assert result.method == "llm"


# ── ConfigLoader with router ─────────────────────────────────────────────────


def test_config_loader_with_router(tmp_path):
    """ConfigLoader should load router.prompt.md."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()

    (agents_dir / "default.prompt.md").write_text("""---
name: openclaw_default
---
Default agent.
""")

    (agents_dir / "researcher.prompt.md").write_text("""---
name: content_researcher
tools:
  - web_search
---
Research agent.
""")

    (tmp_path / "router.prompt.md").write_text("""---
name: master_router
routingRules:
  - if: "'research' in message"
    routeTo: content_researcher
fallback: openclaw_default
llmFallback: true
---
Route messages to the right agent.
""")

    loader = ConfigLoader(tmp_path)
    loader.load()

    assert loader.router is not None
    router_config, router_body = loader.router
    assert router_config.fallback == "openclaw_default"
    assert len(router_config.routing_rules) == 1
    assert "Route messages" in router_body


# ── ConfigLoader with workflows ───────────────────────────────────────────────


def test_config_loader_full_context_tree(tmp_path):
    """ConfigLoader should load agents, workflows, shared context, and router."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir()
    shared_dir = tmp_path / "shared"
    shared_dir.mkdir()

    (agents_dir / "default.prompt.md").write_text("""---
name: openclaw_default
---
Default.
""")
    (agents_dir / "researcher.prompt.md").write_text("""---
name: content_researcher
tools:
  - research_topic
context_files:
  - shared/persona.context.md
---
Research agent.
""")
    (agents_dir / "validator.prompt.md").write_text("""---
name: source_validator
tools:
  - web_search
---
Validator agent.
""")
    (shared_dir / "persona.context.md").write_text("""---
description: "Keith persona"
---
Keith is a tech entrepreneur.
""")
    (workflows_dir / "content-research.workflow.md").write_text("""---
name: content-research
description: "Research and validate"
trigger: manual
callable: true
nodes:
  - id: research
    agent: content_researcher
    next: validate
  - id: validate
    agent: source_validator
    inputs:
      message: "research.text"
---
Research pipeline.
""")
    (tmp_path / "router.prompt.md").write_text("""---
name: master_router
routingRules:
  - if: "'research' in message"
    routeTo: content-research
fallback: openclaw_default
llmFallback: false
---
Route messages.
""")

    loader = ConfigLoader(tmp_path)
    loader.load()

    assert len(loader.agents) == 3
    assert len(loader.workflows) == 1
    assert loader.router is not None
    assert loader.get_context_body("shared/persona.context.md") is not None

    # Workflow has correct structure
    wf_config, _ = loader.get_workflow("content-research")
    assert wf_config.callable is True
    assert len(wf_config.nodes) == 2
    assert wf_config.nodes[0].next_nodes() == ["validate"]

    # Agent references shared context
    agent_config, _ = loader.get_agent("content_researcher")
    assert "shared/persona.context.md" in agent_config.context_files
