"""Tests for config parsing and schemas."""
import tempfile
from pathlib import Path

from agentflow.config.parser import parse_prompt_file, parse_prompt_string
from agentflow.config.schemas import AgentConfig, RouterConfig, RoutingRule, WorkflowConfig, WorkflowNode
from agentflow.config.loader import ConfigLoader


def test_parse_prompt_string():
    text = """---
name: test_agent
model: claude-sonnet-4-6
---
You are a test agent.
"""
    meta, body = parse_prompt_string(text)
    assert meta["name"] == "test_agent"
    assert meta["model"] == "claude-sonnet-4-6"
    assert "test agent" in body


def test_parse_prompt_file(tmp_path):
    f = tmp_path / "test.prompt.md"
    f.write_text("""---
name: file_agent
temperature: 0.5
---
Hello from file.
""")
    meta, body = parse_prompt_file(f)
    assert meta["name"] == "file_agent"
    assert meta["temperature"] == 0.5
    assert "Hello from file" in body


def test_agent_config_defaults():
    config = AgentConfig(name="test")
    assert config.provider == "anthropic"
    assert config.model == "claude-sonnet-4-6"
    assert config.temperature == 0.7
    assert config.max_tokens == 4096
    assert config.max_tool_rounds == 6
    assert config.tools == []


def test_agent_config_full():
    config = AgentConfig(
        name="research",
        provider="openai",
        model="gpt-4o",
        temperature=0.3,
        max_tokens=8192,
        tools=["web_search", "create_document"],
    )
    assert config.provider == "openai"
    assert len(config.tools) == 2


def test_router_config():
    config = RouterConfig(
        name="router",
        routingRules=[
            RoutingRule(**{"if": "intent == 'search'", "routeTo": "search_agent"}),
        ],
        fallback="default",
        llmFallback=True,
    )
    assert len(config.routing_rules) == 1
    assert config.routing_rules[0].route_to == "search_agent"


def test_workflow_config():
    config = WorkflowConfig(
        name="leadgen",
        trigger="api",
        nodes=[
            WorkflowNode(id="research", agent="researcher", next=["qualify"]),
            WorkflowNode(id="qualify", agent="qualifier", next=None),
        ],
    )
    assert len(config.nodes) == 2
    assert config.nodes[0].next_nodes() == ["qualify"]
    assert config.nodes[1].next_nodes() == []
    assert config.entry_node().id == "research"


def test_config_loader(tmp_path):
    # Create context directory structure
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()

    (agents_dir / "test.prompt.md").write_text("""---
name: test_agent
model: claude-sonnet-4-6
tools:
  - web_search
---
You are a test agent for {{user_name}}.
""")

    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir()

    (workflows_dir / "simple.workflow.md").write_text("""---
name: simple
trigger: manual
nodes:
  - id: step1
    agent: test_agent
    next: null
---
A simple one-step workflow.
""")

    loader = ConfigLoader(tmp_path)
    loader.load()

    assert "test_agent" in loader.agents
    agent_config, agent_body = loader.get_agent("test_agent")
    assert agent_config.model == "claude-sonnet-4-6"
    assert "{{user_name}}" in agent_body

    assert "simple" in loader.workflows
    wf_config, _ = loader.get_workflow("simple")
    assert len(wf_config.nodes) == 1
