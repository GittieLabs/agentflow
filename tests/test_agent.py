"""Tests for agent executor, context assembler, and prompt template."""
import pytest

from agentflow.agent.prompt import PromptTemplate
from agentflow.agent.context import ContextAssembler
from agentflow.agent.runtime import AgentExecutor
from agentflow.config.schemas import AgentConfig
from agentflow.providers.mock import MockLLMProvider
from agentflow.storage.memory_storage import InMemoryStorage
from agentflow.tools.registry import ToolRegistry
from agentflow.types import AgentResponse, ToolCall


# ── Prompt Template ───────────────────────────────────────────────────────────


def test_prompt_render():
    tpl = PromptTemplate("Hello {{name}}, today is {{date}}.")
    result = tpl.render({"name": "Keith", "date": "2026-03-09"})
    assert result == "Hello Keith, today is 2026-03-09."


def test_prompt_render_missing_key():
    tpl = PromptTemplate("Hello {{name}}, user {{user_id}}.")
    result = tpl.render({"name": "Keith"})
    assert result == "Hello Keith, user {{user_id}}."


def test_prompt_variables():
    tpl = PromptTemplate("{{name}} on {{date}}")
    assert set(tpl.variables()) == {"name", "date"}


# ── Context Assembler ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_context_assembler_basic():
    config = AgentConfig(name="test")
    assembler = ContextAssembler()
    result = await assembler.assemble(
        config=config,
        prompt_body="You are a test agent. Date: {{date}}",
        variables={"date": "2026-03-09"},
    )
    assert "You are a test agent" in result
    assert "2026-03-09" in result


@pytest.mark.asyncio
async def test_context_assembler_with_context_files():
    storage = InMemoryStorage()
    await storage.write("agents/guidelines.context.md", "## Guidelines\nAlways be helpful.")

    config = AgentConfig(name="test", context_files=["guidelines.context.md"])
    assembler = ContextAssembler(storage=storage)
    result = await assembler.assemble(config=config, prompt_body="Base prompt.")
    assert "Guidelines" in result
    assert "Always be helpful" in result


# ── Agent Executor ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_executor_simple_chat():
    """Test basic chat without tools."""
    config = AgentConfig(name="test", max_tool_rounds=6)
    mock_llm = MockLLMProvider([
        AgentResponse(text="Hello! I'm a test agent.", stop_reason="end_turn"),
    ])

    executor = AgentExecutor(config=config, prompt_body="You are a test agent.", llm=mock_llm)
    result = await executor.run(message="Hi there")

    assert result.text == "Hello! I'm a test agent."
    assert result.agent_id == "test"
    assert len(mock_llm.calls) == 1


@pytest.mark.asyncio
async def test_executor_with_tool_use():
    """Test tool use loop — LLM calls a tool, gets result, then responds."""
    config = AgentConfig(name="test", max_tool_rounds=6)

    # First response: LLM wants to call a tool
    # Second response: LLM gives final answer
    mock_llm = MockLLMProvider([
        AgentResponse(
            text="",
            tool_calls=[ToolCall(id="tc_1", name="web_search", input={"query": "weather"})],
            stop_reason="tool_use",
        ),
        AgentResponse(
            text="It's sunny today!",
            stop_reason="end_turn",
        ),
    ])

    # Mock tool dispatcher
    async def mock_dispatch(tool_name, tool_input):
        return "Current weather: sunny, 72F"

    tools = ToolRegistry()
    tools.add_tool("web_search", mock_dispatch, description="Search the web")

    executor = AgentExecutor(config=config, prompt_body="You are helpful.", llm=mock_llm, tools=tools)
    result = await executor.run(message="What's the weather?")

    assert result.text == "It's sunny today!"
    assert len(mock_llm.calls) == 2  # Initial call + after tool result
    assert result.metadata.get("rounds") == 2


@pytest.mark.asyncio
async def test_executor_exhausted_rounds():
    """Test that agent returns gracefully when tool rounds are exhausted."""
    config = AgentConfig(name="test", max_tool_rounds=2)

    # LLM keeps requesting tools forever
    mock_llm = MockLLMProvider([
        AgentResponse(
            text="",
            tool_calls=[ToolCall(id="tc_1", name="search", input={})],
            stop_reason="tool_use",
        ),
        AgentResponse(
            text="",
            tool_calls=[ToolCall(id="tc_2", name="search", input={})],
            stop_reason="tool_use",
        ),
    ])

    async def mock_dispatch(tool_name, tool_input):
        return "result"

    tools = ToolRegistry()
    tools.add_tool("search", mock_dispatch)

    executor = AgentExecutor(config=config, prompt_body="Agent", llm=mock_llm, tools=tools)
    result = await executor.run(message="loop")

    assert result.metadata.get("exhausted_rounds") is True


@pytest.mark.asyncio
async def test_executor_with_variables():
    """Test that template variables are rendered in the system prompt."""
    config = AgentConfig(name="test")
    mock_llm = MockLLMProvider([
        AgentResponse(text="ok", stop_reason="end_turn"),
    ])

    executor = AgentExecutor(
        config=config,
        prompt_body="Date: {{date}}, User: {{user_name}}",
        llm=mock_llm,
    )
    await executor.run(message="hi", variables={"date": "2026-03-09", "user_name": "Keith"})

    # Check the system prompt that was sent to the LLM
    system = mock_llm.calls[0]["system"]
    assert "2026-03-09" in system
    assert "Keith" in system
