"""
Anthropic Claude LLM provider.

Translates between agentflow's canonical types and the Anthropic SDK's
message format, including tool use.
"""
from __future__ import annotations

import logging
from typing import Any

from agentflow.types import AgentResponse, Message, Role, ToolCall

logger = logging.getLogger("agentflow.providers.anthropic")

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment]


# Anthropic's newest reasoning model lines (first hit: claude-sonnet-5)
# reject `temperature` outright once thinking is active and use a newer
# adaptive-thinking + effort interface instead of the older, fixed
# `budget_tokens` one. Selected via a `-low`/`-medium`/`-high` model-name
# suffix -- mirroring GoogleGenAIProvider's identical convention for
# Gemini thinking models exactly, one pattern across providers instead
# of two different ones.
_THINKING_EFFORT_SUFFIXES = ("-low", "-medium", "-high")


class AnthropicProvider:
    """LLMProvider implementation for Anthropic Claude models."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-5",
    ):
        if anthropic is None:
            raise ImportError("Install anthropic: pip install agentflow[anthropic]")
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def chat(
        self,
        messages: list[Message],
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AgentResponse:
        """Send messages to Claude and return an AgentResponse."""
        api_messages = self._to_api_messages(messages)

        model = self._model
        effort = None
        if model.endswith(_THINKING_EFFORT_SUFFIXES):
            model, effort = model.rsplit("-", 1)

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": api_messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools
        if effort:
            # Adaptive thinking requires temperature to be entirely absent
            # from the request, not merely set to 1.
            kwargs["thinking"] = {"type": "adaptive"}
            kwargs["output_config"] = {"effort": effort}
        elif temperature != 1.0:
            kwargs["temperature"] = temperature

        try:
            response = await self._client.messages.create(**kwargs)
        except anthropic.BadRequestError as e:
            # Some Claude model lines reject `temperature` outright even
            # with no explicit thinking suffix (first hit: bare
            # `claude-sonnet-5`, thinking on by default) -- retry once
            # without it rather than hardcoding a model-name allowlist
            # that would need updating for every future model release,
            # the exact problem this fix exists to get away from.
            body = e.body if isinstance(e.body, dict) else {}
            error_message = body.get("error", {}).get("message", "")
            if "temperature" in kwargs and "temperature" in error_message and "deprecated" in error_message:
                del kwargs["temperature"]
                response = await self._client.messages.create(**kwargs)
            else:
                raise

        return self._from_api_response(response)

    def _to_api_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        """Convert agentflow Messages to Anthropic API format."""
        api_msgs: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == Role.SYSTEM:
                continue  # System is passed separately
            if msg.role == Role.TOOL_RESULT:
                # Tool results are sent as "user" role with tool_result content blocks
                content = [
                    {
                        "type": "tool_result",
                        "tool_use_id": tr.tool_call_id,
                        "content": tr.content,
                        **({"is_error": True} if tr.is_error else {}),
                    }
                    for tr in msg.tool_results
                ]
                api_msgs.append({"role": "user", "content": content})
            elif msg.tool_calls:
                # Assistant message with tool use — reconstruct content blocks
                content: list[dict[str, Any]] = []
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    content.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.input,
                    })
                api_msgs.append({"role": "assistant", "content": content})
            else:
                api_msgs.append({"role": msg.role.value, "content": msg.content})
        return api_msgs

    def _from_api_response(self, response: Any) -> AgentResponse:
        """Convert Anthropic API response to AgentResponse."""
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(id=block.id, name=block.name, input=block.input)
                )

        return AgentResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            stop_reason="tool_use" if response.stop_reason == "tool_use" else "end_turn",
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
            raw=response,
        )
