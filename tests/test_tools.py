"""Tests for tool registry and dispatchers."""
import pytest

from agentflow.tools.registry import ToolRegistry
from agentflow.tools.local_dispatcher import LocalToolDispatcher


@pytest.mark.asyncio
async def test_inline_tool():
    """Test registering and dispatching an inline tool."""
    registry = ToolRegistry()

    async def my_tool(query: str = "") -> str:
        return f"result for {query}"

    registry.add_tool("my_tool", my_tool, description="A test tool")

    result = await registry.dispatch("my_tool", {"query": "hello"})
    assert result == "result for hello"


@pytest.mark.asyncio
async def test_tool_list():
    """Test that list_tools returns definitions from all sources."""
    registry = ToolRegistry()

    async def noop() -> str:
        return ""

    registry.add_tool("tool_a", noop, description="Tool A")
    registry.add_tool("tool_b", noop, description="Tool B")

    tools = registry.list_tools()
    names = {t["name"] for t in tools}
    assert names == {"tool_a", "tool_b"}


@pytest.mark.asyncio
async def test_unknown_tool():
    registry = ToolRegistry()
    result = await registry.dispatch("nonexistent", {})
    assert "Unknown tool" in result


@pytest.mark.asyncio
async def test_local_dispatcher():
    dispatcher = LocalToolDispatcher()

    async def greet(name: str = "world") -> str:
        return f"Hello, {name}!"

    dispatcher.register("greet", greet, description="Say hello")

    result = await dispatcher.dispatch("greet", {"name": "Keith"})
    assert result == "Hello, Keith!"

    tools = dispatcher.list_tools()
    assert len(tools) == 1
    assert tools[0]["name"] == "greet"


@pytest.mark.asyncio
async def test_local_dispatcher_error():
    dispatcher = LocalToolDispatcher()

    async def fail(**kwargs) -> str:
        raise ValueError("boom")

    dispatcher.register("fail", fail)
    result = await dispatcher.dispatch("fail", {})
    assert "Tool error" in result


@pytest.mark.asyncio
async def test_registry_with_dispatcher():
    """Test routing to a registered dispatcher."""
    local = LocalToolDispatcher()

    async def ping() -> str:
        return "pong"

    local.register("ping", ping, description="Ping")

    registry = ToolRegistry()
    registry.add_dispatcher({"ping"}, local)

    result = await registry.dispatch("ping", {})
    assert result == "pong"
