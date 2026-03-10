"""Tests for core types."""
from agentflow.types import (
    AgentResponse,
    Message,
    NodeMode,
    NodeOutput,
    Role,
    ToolCall,
    ToolResult,
)


def test_role_enum():
    assert Role.USER == "user"
    assert Role.ASSISTANT == "assistant"
    assert Role.TOOL_RESULT == "tool_result"


def test_node_mode_enum():
    assert NodeMode.SYNC == "sync"
    assert NodeMode.PARALLEL == "parallel"
    assert NodeMode.ASYNC == "async"


def test_message_defaults():
    msg = Message(role=Role.USER, content="hello")
    assert msg.tool_calls == []
    assert msg.tool_results == []
    assert msg.metadata == {}


def test_tool_call():
    tc = ToolCall(id="tc_1", name="web_search", input={"query": "test"})
    assert tc.name == "web_search"
    assert tc.input["query"] == "test"


def test_agent_response_defaults():
    resp = AgentResponse(text="hello")
    assert resp.stop_reason == "end_turn"
    assert resp.tool_calls == []
    assert resp.usage == {}


def test_node_output():
    out = NodeOutput(node_id="n1", agent_id="a1", text="result")
    assert out.artifacts == {}
