"""Tests for routing: RuleEvaluator and RouterEngine."""
import pytest

from agentflow.config.schemas import RouterConfig, RoutingRule
from agentflow.providers.mock import MockLLMProvider
from agentflow.router.engine import RouterEngine, RoutingResult
from agentflow.router.rules import RuleEvaluator
from agentflow.types import AgentResponse


# ── RuleEvaluator ────────────────────────────────────────────────────────────


def test_rule_equality():
    evaluator = RuleEvaluator()
    rule = RoutingRule(**{"if": "intent == 'search'", "routeTo": "search_agent"})
    assert evaluator.evaluate(rule, {"intent": "search"})
    assert not evaluator.evaluate(rule, {"intent": "chat"})


def test_rule_inequality():
    evaluator = RuleEvaluator()
    rule = RoutingRule(**{"if": "channel != 'voice'", "routeTo": "text_agent"})
    assert evaluator.evaluate(rule, {"channel": "signal"})
    assert not evaluator.evaluate(rule, {"channel": "voice"})


def test_rule_in_list():
    evaluator = RuleEvaluator()
    rule = RoutingRule(**{"if": "intent in ['search', 'research']", "routeTo": "research_agent"})
    assert evaluator.evaluate(rule, {"intent": "search"})
    assert evaluator.evaluate(rule, {"intent": "research"})
    assert not evaluator.evaluate(rule, {"intent": "chat"})


def test_rule_contains():
    evaluator = RuleEvaluator()
    rule = RoutingRule(**{"if": "'calendar' in message", "routeTo": "calendar_agent"})
    assert evaluator.evaluate(rule, {"message": "What's on my calendar today?"})
    assert not evaluator.evaluate(rule, {"message": "What's the weather?"})


def test_rule_bool_true():
    evaluator = RuleEvaluator()
    rule = RoutingRule(**{"if": "is_urgent == true", "routeTo": "priority_agent"})
    assert evaluator.evaluate(rule, {"is_urgent": True})
    assert not evaluator.evaluate(rule, {"is_urgent": False})


def test_rule_bool_false():
    evaluator = RuleEvaluator()
    rule = RoutingRule(**{"if": "is_authenticated == false", "routeTo": "auth_agent"})
    assert evaluator.evaluate(rule, {"is_authenticated": False})
    assert not evaluator.evaluate(rule, {"is_authenticated": True})


def test_rule_match_first_wins():
    evaluator = RuleEvaluator()
    rules = [
        RoutingRule(**{"if": "intent == 'search'", "routeTo": "search_agent"}),
        RoutingRule(**{"if": "intent == 'search'", "routeTo": "other_agent"}),
    ]
    result = evaluator.match(rules, {"intent": "search"})
    assert result == "search_agent"


def test_rule_match_none():
    evaluator = RuleEvaluator()
    rules = [
        RoutingRule(**{"if": "intent == 'search'", "routeTo": "search_agent"}),
    ]
    result = evaluator.match(rules, {"intent": "chat"})
    assert result is None


def test_rule_missing_field():
    evaluator = RuleEvaluator()
    rule = RoutingRule(**{"if": "intent == 'search'", "routeTo": "search_agent"})
    assert not evaluator.evaluate(rule, {})  # Missing field doesn't match


# ── Compound conditions (or / and) ──────────────────────────────────────────


def test_rule_or_contains():
    """Two 'substring in field' clauses joined by 'or'."""
    evaluator = RuleEvaluator()
    rule = RoutingRule(
        **{"if": "'blog' in message or 'article' in message", "routeTo": "content_agent"}
    )
    assert evaluator.evaluate(rule, {"message": "Write a blog post about AI"})
    assert evaluator.evaluate(rule, {"message": "Draft an article on LLMs"})
    assert not evaluator.evaluate(rule, {"message": "What's the weather?"})


def test_rule_or_equality():
    """Two equality clauses joined by 'or'."""
    evaluator = RuleEvaluator()
    rule = RoutingRule(
        **{"if": "intent == 'search' or intent == 'research'", "routeTo": "research_agent"}
    )
    assert evaluator.evaluate(rule, {"intent": "search"})
    assert evaluator.evaluate(rule, {"intent": "research"})
    assert not evaluator.evaluate(rule, {"intent": "chat"})


def test_rule_and_conditions():
    """Two conditions joined by 'and' — both must match."""
    evaluator = RuleEvaluator()
    rule = RoutingRule(
        **{"if": "channel == 'voice' and 'urgent' in message", "routeTo": "priority_agent"}
    )
    assert evaluator.evaluate(rule, {"channel": "voice", "message": "urgent appointment"})
    assert not evaluator.evaluate(rule, {"channel": "voice", "message": "normal question"})
    assert not evaluator.evaluate(rule, {"channel": "signal", "message": "urgent request"})


def test_rule_or_three_clauses():
    """Three clauses joined by 'or'."""
    evaluator = RuleEvaluator()
    rule = RoutingRule(
        **{
            "if": "'lead' in message or 'prospect' in message or 'outreach' in message",
            "routeTo": "lead_gen",
        }
    )
    assert evaluator.evaluate(rule, {"message": "Find new leads"})
    assert evaluator.evaluate(rule, {"message": "Research prospects"})
    assert evaluator.evaluate(rule, {"message": "Start outreach campaign"})
    assert not evaluator.evaluate(rule, {"message": "What time is it?"})


def test_rule_or_with_quoted_or():
    """Value containing 'or' in a quoted string doesn't split incorrectly."""
    evaluator = RuleEvaluator()
    # This tests that 'or' inside a quoted value like 'sports' doesn't break
    rule = RoutingRule(
        **{"if": "'sports' in message or 'news' in message", "routeTo": "news_agent"}
    )
    assert evaluator.evaluate(rule, {"message": "Latest sports scores"})
    assert evaluator.evaluate(rule, {"message": "Breaking news today"})


def test_eval_expr_standalone():
    """Test eval_expr directly (not through a RoutingRule)."""
    evaluator = RuleEvaluator()
    ctx = {"message": "research AI agents", "channel": "signal"}

    assert evaluator.eval_expr("'research' in message", ctx)
    assert evaluator.eval_expr("'research' in message or 'search' in message", ctx)
    assert evaluator.eval_expr("'research' in message and channel == 'signal'", ctx)
    assert not evaluator.eval_expr("'research' in message and channel == 'voice'", ctx)


# ── RouterEngine ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_router_rule_match():
    config = RouterConfig(
        name="router",
        routingRules=[
            RoutingRule(**{"if": "'weather' in message", "routeTo": "search_agent"}),
            RoutingRule(**{"if": "'email' in message", "routeTo": "email_agent"}),
        ],
        fallback="default",
    )
    engine = RouterEngine(config=config)

    result = await engine.route("What's the weather today?")
    assert result.target == "search_agent"
    assert result.method == "rule"


@pytest.mark.asyncio
async def test_router_fallback():
    config = RouterConfig(
        name="router",
        routingRules=[
            RoutingRule(**{"if": "'weather' in message", "routeTo": "search_agent"}),
        ],
        fallback="default_agent",
        llmFallback=False,
    )
    engine = RouterEngine(config=config)

    result = await engine.route("Tell me a joke")
    assert result.target == "default_agent"
    assert result.method == "fallback"


@pytest.mark.asyncio
async def test_router_llm_fallback():
    config = RouterConfig(
        name="router",
        routingRules=[],
        fallback="default",
        llmFallback=True,
    )

    mock_llm = MockLLMProvider([
        AgentResponse(text="email_agent", stop_reason="end_turn"),
    ])

    engine = RouterEngine(
        config=config,
        llm=mock_llm,
        available_targets=["search_agent", "email_agent", "default"],
    )

    result = await engine.route("Send an email to John")
    assert result.target == "email_agent"
    assert result.method == "llm"


@pytest.mark.asyncio
async def test_router_llm_fallback_invalid_response():
    """LLM returns a target not in the available list → falls back to static."""
    config = RouterConfig(
        name="router",
        routingRules=[],
        fallback="default",
        llmFallback=True,
    )

    mock_llm = MockLLMProvider([
        AgentResponse(text="nonexistent_agent", stop_reason="end_turn"),
    ])

    engine = RouterEngine(
        config=config,
        llm=mock_llm,
        available_targets=["search_agent", "email_agent"],
    )

    result = await engine.route("Do something weird")
    assert result.target == "default"
    assert result.method == "fallback"


@pytest.mark.asyncio
async def test_router_with_context():
    config = RouterConfig(
        name="router",
        routingRules=[
            RoutingRule(**{"if": "channel == 'voice'", "routeTo": "voice_agent"}),
            RoutingRule(**{"if": "channel == 'signal'", "routeTo": "text_agent"}),
        ],
        fallback="default",
    )
    engine = RouterEngine(config=config)

    result = await engine.route("Hello", context={"channel": "voice"})
    assert result.target == "voice_agent"
