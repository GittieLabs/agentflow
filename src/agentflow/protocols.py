"""
AgentFlow protocols.

Structural typing interfaces (PEP 544) that define the contracts for pluggable
backends. Any class implementing these methods works — no inheritance required.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from agentflow.types import AgentResponse, Message


@runtime_checkable
class LLMProvider(Protocol):
    """Contract for LLM backends (Anthropic, OpenAI, Google, etc.)."""

    async def chat(
        self,
        messages: list[Message],
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AgentResponse: ...


@runtime_checkable
class StorageBackend(Protocol):
    """Contract for reading/writing files (filesystem, S3, in-memory)."""

    async def read(self, path: str) -> str | None: ...
    async def write(self, path: str, content: str) -> None: ...
    async def exists(self, path: str) -> bool: ...
    async def list(self, prefix: str) -> list[str]: ...
    async def delete(self, path: str) -> None: ...


@runtime_checkable
class ToolDispatcher(Protocol):
    """Contract for dispatching tool calls."""

    async def dispatch(self, tool_name: str, tool_input: dict[str, Any]) -> str: ...
    def list_tools(self) -> list[dict[str, Any]]: ...


@runtime_checkable
class MemoryStore(Protocol):
    """Contract for semantic memory (vector search, file-based, etc.)."""

    async def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]: ...
    async def store(self, content: str, metadata: dict[str, Any] | None = None) -> str: ...


@runtime_checkable
class EventHandler(Protocol):
    """Contract for observability event handlers."""

    async def on_event(self, event_type: str, data: dict[str, Any]) -> None: ...
