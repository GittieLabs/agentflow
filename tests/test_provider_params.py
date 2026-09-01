"""0.11.0: verbatim vendor-parameter passthrough (`chat(params=...)`).

Vendors add parameters faster than any framework can name them. Rather than
model which parameter each model supports -- a thing that cannot be kept
current -- AgentFlow forwards a caller-supplied dict straight to the vendor
SDK and the caller owns correctness.

What the caller does NOT get to do is silently redirect the call. These tests
pin both halves: the forwarding, and the refusal.

They also pin the removal of the `-low`/`-medium`/`-high` model-name suffix
convention this replaced. That convention parsed effort out of the model
string with `rsplit("-", 1)`, so it truncated any legitimate model whose real
name ended in one of those words and misread the tail as an effort level.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentflow.providers._params import merge_params
from agentflow.types import Message, Role


class TestMergeParams:
    """The one implementation every provider shares."""

    def test_none_and_empty_are_no_ops(self):
        for value in (None, {}):
            kwargs = {"model": "m"}
            assert merge_params(kwargs, value, provider="p") == {"model": "m"}

    def test_new_keys_are_forwarded_verbatim(self):
        kwargs = {"model": "m"}
        merge_params(kwargs, {"reasoning_effort": "high", "seed": 7}, provider="p")
        assert kwargs == {"model": "m", "reasoning_effort": "high", "seed": 7}

    def test_a_reserved_key_is_refused_and_names_the_provider(self):
        with pytest.raises(ValueError) as e:
            merge_params({"model": "m"}, {"model": "other"}, provider="anthropic")
        assert "anthropic" in str(e.value)
        assert "model" in str(e.value)

    def test_every_offending_key_is_named_not_just_the_first(self):
        """A caller passing two bad keys should learn both in one run."""
        with pytest.raises(ValueError) as e:
            merge_params(
                {"model": "m", "messages": [], "system": "s"},
                {"model": "x", "system": "y"},
                provider="p",
            )
        msg = str(e.value)
        assert "model" in msg and "system" in msg

    def test_a_non_dict_is_a_type_error_not_a_crash_later(self):
        with pytest.raises(TypeError):
            merge_params({}, ["not", "a", "dict"], provider="p")

    def test_nothing_is_merged_when_the_call_is_refused(self):
        kwargs = {"model": "m"}
        with pytest.raises(ValueError):
            merge_params(kwargs, {"model": "x", "seed": 1}, provider="p")
        assert kwargs == {"model": "m"}, "a refused merge must not partially apply"


class TestOpenAICompatParams:
    def _make_provider(self):
        from agentflow.providers.openai_compat import OpenAICompatProvider

        with patch("agentflow.providers.openai_compat.openai") as mod:
            client = AsyncMock()
            mod.AsyncOpenAI.return_value = client
            return OpenAICompatProvider(
                api_key="k", model="gpt-4o", base_url="https://api.openai.com/v1"
            ), client

    @pytest.mark.asyncio
    async def test_reasoning_effort_reaches_the_vendor_call(self):
        """The gap that motivated all of this: openai_compat had no effort
        support at all, by any mechanism."""
        provider, client = self._make_provider()
        client.chat.completions.create = AsyncMock(return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(content="ok", tool_calls=None))],
            usage=MagicMock(prompt_tokens=1, completion_tokens=1),
            model="gpt-4o",
        ))
        await provider.chat(
            [Message(role=Role.USER, content="Hi")],
            params={"reasoning_effort": "high"},
        )
        _, kwargs = client.chat.completions.create.call_args
        assert kwargs["reasoning_effort"] == "high"

    @pytest.mark.asyncio
    async def test_params_may_not_override_the_model(self):
        provider, client = self._make_provider()
        client.chat.completions.create = AsyncMock()
        with pytest.raises(ValueError):
            await provider.chat(
                [Message(role=Role.USER, content="Hi")], params={"model": "sneaky"}
            )
        client.chat.completions.create.assert_not_called()


class TestAgentConfigParams:
    def test_params_default_to_empty_and_are_optional(self):
        from agentflow.config.schemas import AgentConfig

        assert AgentConfig(name="a").params == {}

    def test_params_round_trip_from_front_matter(self):
        from agentflow.config.schemas import AgentConfig

        cfg = AgentConfig(name="a", params={"reasoning_effort": "high"})
        assert cfg.params == {"reasoning_effort": "high"}


class TestRuntimePassesParams:
    """An agent's params must actually reach the provider. Declaring them on
    AgentConfig and never forwarding them would be the quietest possible
    failure -- everything configured, nothing applied."""

    @pytest.mark.asyncio
    async def test_configured_params_reach_the_provider(self):
        from agentflow.agent.runtime import AgentExecutor
        from agentflow.config.schemas import AgentConfig
        from agentflow.providers.mock import MockLLMProvider
        from agentflow.types import AgentResponse

        llm = MockLLMProvider([AgentResponse(text="done", stop_reason="end_turn")])
        config = AgentConfig(name="a", params={"reasoning_effort": "high"})
        executor = AgentExecutor(config=config, prompt_body="body", llm=llm)
        await executor.run(message="hello")

        assert llm.calls[0]["params"] == {"reasoning_effort": "high"}

    @pytest.mark.asyncio
    async def test_no_params_sends_none_rather_than_an_empty_dict(self):
        """`{}` and None must not become two different requests downstream."""
        from agentflow.agent.runtime import AgentExecutor
        from agentflow.config.schemas import AgentConfig
        from agentflow.providers.mock import MockLLMProvider
        from agentflow.types import AgentResponse

        llm = MockLLMProvider([AgentResponse(text="done", stop_reason="end_turn")])
        executor = AgentExecutor(config=AgentConfig(name="a"), prompt_body="body", llm=llm)
        await executor.run(message="hello")

        assert llm.calls[0]["params"] is None


class TestAnthropicTemperatureCompatibility:
    """anthropic>=1.0 removed `temperature` from `messages.create`. Sending it
    raises TypeError client-side, before any network call, which the
    BadRequestError retry cannot catch -- so every chat with a non-1.0
    temperature failed outright. Found 2026-09-01 while diagnosing a suite
    that passed only because it ran against an older SDK on a different
    interpreter.
    """

    def test_signature_without_temperature_is_detected(self):
        from agentflow.providers.anthropic import _accepts_temperature

        def new_sdk(*, model, max_tokens, messages, system=None, tools=None,
                    thinking=None, output_config=None):
            ...

        assert _accepts_temperature(new_sdk) is False

    def test_signature_with_temperature_is_detected(self):
        from agentflow.providers.anthropic import _accepts_temperature

        def old_sdk(*, model, max_tokens, messages, temperature=0.7):
            ...

        assert _accepts_temperature(old_sdk) is True

    def test_a_kwargs_callable_counts_as_accepting_it(self):
        """A callable taking **kwargs accepts anything. Reading it as a new
        SDK would quietly drop the caller's temperature -- and it is what
        every test double and blind-forwarding wrapper looks like."""
        from agentflow.providers.anthropic import _accepts_temperature

        def forwards_everything(**kwargs):
            ...

        assert _accepts_temperature(forwards_everything) is True

    def test_an_uninspectable_callable_keeps_the_old_behaviour(self):
        """Returning True when it cannot tell means an SDK this cannot read
        behaves exactly as it did before, rather than silently dropping a
        parameter the caller asked for."""
        from agentflow.providers.anthropic import _accepts_temperature

        assert _accepts_temperature(object()) is True

    @pytest.mark.asyncio
    async def test_temperature_is_omitted_when_the_sdk_rejects_it(self):
        from agentflow.providers.anthropic import AnthropicProvider

        with patch("agentflow.providers.anthropic.anthropic") as mod:
            client = AsyncMock()
            mod.AsyncAnthropic.return_value = client
            provider = AnthropicProvider(api_key="k", model="claude-sonnet-5")

        async def new_sdk_create(*, model, max_tokens, messages, system=None, tools=None):
            return MagicMock(
                content=[MagicMock(type="text", text="ok")],
                stop_reason="end_turn", usage=MagicMock(input_tokens=1, output_tokens=1),
                model="claude-sonnet-5",
            )

        client.messages.create = new_sdk_create
        # The bug: this raised TypeError before reaching the network.
        result = await provider.chat([Message(role=Role.USER, content="Hi")], temperature=0.2)
        assert result.text == "ok"
