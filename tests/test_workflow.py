"""Tests for workflow: WorkflowDAG, NodeRunner, WorkflowExecutor."""
import pytest

from agentflow.config.schemas import AgentConfig, WorkflowConfig, WorkflowNode
from agentflow.providers.mock import MockLLMProvider
from agentflow.agent.runtime import AgentExecutor
from agentflow.types import AgentResponse, NodeOutput
from agentflow.workflow.dag import WorkflowDAG
from agentflow.workflow.executor import WorkflowExecutor
from agentflow.workflow.node import NodeRunner


# ── WorkflowDAG ──────────────────────────────────────────────────────────────


def test_dag_entry_and_terminal():
    config = WorkflowConfig(
        name="test",
        nodes=[
            WorkflowNode(id="a", agent="agent_a", next=["b"]),
            WorkflowNode(id="b", agent="agent_b", next=["c"]),
            WorkflowNode(id="c", agent="agent_c"),
        ],
    )
    dag = WorkflowDAG(config)
    assert dag.entry_nodes() == ["a"]
    assert dag.terminal_nodes() == ["c"]


def test_dag_topological_order():
    config = WorkflowConfig(
        name="test",
        nodes=[
            WorkflowNode(id="a", agent="a", next=["b", "c"]),
            WorkflowNode(id="b", agent="b", next=["d"]),
            WorkflowNode(id="c", agent="c", next=["d"]),
            WorkflowNode(id="d", agent="d"),
        ],
    )
    dag = WorkflowDAG(config)
    order = dag.topological_order()
    assert order.index("a") < order.index("b")
    assert order.index("a") < order.index("c")
    assert order.index("b") < order.index("d")
    assert order.index("c") < order.index("d")


def test_dag_ready_nodes():
    config = WorkflowConfig(
        name="test",
        nodes=[
            WorkflowNode(id="a", agent="a", next=["c"]),
            WorkflowNode(id="b", agent="b", next=["c"]),
            WorkflowNode(id="c", agent="c"),
        ],
    )
    dag = WorkflowDAG(config)

    # Initially, a and b are ready (no predecessors)
    assert dag.ready_nodes(set()) == ["a", "b"]

    # After a completes, b is still ready but c is not (needs b too)
    assert dag.ready_nodes({"a"}) == ["b"]

    # After both a and b complete, c is ready
    assert dag.ready_nodes({"a", "b"}) == ["c"]


def test_dag_predecessors_and_successors():
    config = WorkflowConfig(
        name="test",
        nodes=[
            WorkflowNode(id="a", agent="a", next=["b"]),
            WorkflowNode(id="b", agent="b"),
        ],
    )
    dag = WorkflowDAG(config)
    assert dag.successors("a") == ["b"]
    assert dag.predecessors("b") == ["a"]


def test_dag_validate_valid():
    config = WorkflowConfig(
        name="test",
        nodes=[
            WorkflowNode(id="a", agent="a", next=["b"]),
            WorkflowNode(id="b", agent="b"),
        ],
    )
    dag = WorkflowDAG(config)
    assert dag.validate() == []


def test_dag_validate_bad_reference():
    config = WorkflowConfig(
        name="test",
        nodes=[
            WorkflowNode(id="a", agent="a", next=["nonexistent"]),
        ],
    )
    dag = WorkflowDAG(config)
    errors = dag.validate()
    assert any("nonexistent" in e for e in errors)


def test_dag_diamond_shape():
    """Diamond: a -> b,c -> d (classic parallel-merge pattern)."""
    config = WorkflowConfig(
        name="diamond",
        nodes=[
            WorkflowNode(id="a", agent="a", next=["b", "c"]),
            WorkflowNode(id="b", agent="b", next=["d"]),
            WorkflowNode(id="c", agent="c", next=["d"]),
            WorkflowNode(id="d", agent="d"),
        ],
    )
    dag = WorkflowDAG(config)
    assert dag.entry_nodes() == ["a"]
    assert dag.terminal_nodes() == ["d"]
    assert sorted(dag.predecessors("d")) == ["b", "c"]


# ── NodeRunner ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_node_runner_basic():
    config = AgentConfig(name="test_agent")
    mock_llm = MockLLMProvider([
        AgentResponse(text="Research complete.", stop_reason="end_turn"),
    ])
    executor = AgentExecutor(config=config, prompt_body="You are a researcher.", llm=mock_llm)

    node = WorkflowNode(id="research", agent="test_agent")
    runner = NodeRunner(node=node, executor=executor)

    result = await runner.run(prior_outputs={})
    assert result.text == "Research complete."


@pytest.mark.asyncio
async def test_node_runner_with_prior_output():
    config = AgentConfig(name="qualifier")
    mock_llm = MockLLMProvider([
        AgentResponse(text="Lead is qualified.", stop_reason="end_turn"),
    ])
    executor = AgentExecutor(config=config, prompt_body="You qualify leads.", llm=mock_llm)

    node = WorkflowNode(
        id="qualify",
        agent="qualifier",
        inputs={"message": "research.text"},
    )
    runner = NodeRunner(node=node, executor=executor)

    prior = {
        "research": NodeOutput(node_id="research", agent_id="researcher", text="Found 3 leads."),
    }
    result = await runner.run(prior_outputs=prior)
    assert result.text == "Lead is qualified."

    # Verify the resolved message was passed (from research.text)
    sent_messages = mock_llm.calls[0]["messages"]
    assert any("Found 3 leads" in m.content for m in sent_messages)


# ── WorkflowExecutor ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_workflow_executor_linear():
    """Test a simple 3-step linear workflow: research -> qualify -> outreach."""
    wf_config = WorkflowConfig(
        name="leadgen",
        nodes=[
            WorkflowNode(id="research", agent="researcher", next=["qualify"]),
            WorkflowNode(id="qualify", agent="qualifier", next=["outreach"]),
            WorkflowNode(id="outreach", agent="writer"),
        ],
    )

    # Each node's agent returns a distinct response
    responses = {
        "research": [AgentResponse(text="Found Acme Corp.", stop_reason="end_turn")],
        "qualify": [AgentResponse(text="Acme is a good fit.", stop_reason="end_turn")],
        "outreach": [AgentResponse(text="Email drafted.", stop_reason="end_turn")],
    }

    def runner_factory(node_id: str) -> NodeRunner:
        node = wf_config.nodes[["research", "qualify", "outreach"].index(node_id)]
        agent_config = AgentConfig(name=node.agent)
        mock_llm = MockLLMProvider(responses[node_id])
        executor = AgentExecutor(config=agent_config, prompt_body=f"You are {node.agent}.", llm=mock_llm)
        return NodeRunner(node=node, executor=executor)

    wf_executor = WorkflowExecutor(config=wf_config, runner_factory=runner_factory)
    outputs = await wf_executor.run(initial_message="Find leads in fintech")

    assert len(outputs) == 3
    assert outputs["research"].text == "Found Acme Corp."
    assert outputs["qualify"].text == "Acme is a good fit."
    assert outputs["outreach"].text == "Email drafted."


@pytest.mark.asyncio
async def test_workflow_executor_parallel():
    """Test parallel execution: a -> (b || c) -> d."""
    wf_config = WorkflowConfig(
        name="parallel_test",
        nodes=[
            WorkflowNode(id="a", agent="starter", next=["b", "c"]),
            WorkflowNode(id="b", agent="worker_b", mode="parallel", next=["d"]),
            WorkflowNode(id="c", agent="worker_c", mode="parallel", next=["d"]),
            WorkflowNode(id="d", agent="merger"),
        ],
    )

    node_map = {n.id: n for n in wf_config.nodes}
    responses = {
        "a": [AgentResponse(text="Start", stop_reason="end_turn")],
        "b": [AgentResponse(text="B done", stop_reason="end_turn")],
        "c": [AgentResponse(text="C done", stop_reason="end_turn")],
        "d": [AgentResponse(text="Merged", stop_reason="end_turn")],
    }

    def runner_factory(node_id: str) -> NodeRunner:
        node = node_map[node_id]
        agent_config = AgentConfig(name=node.agent)
        mock_llm = MockLLMProvider(responses[node_id])
        executor = AgentExecutor(config=agent_config, prompt_body=f"You are {node.agent}.", llm=mock_llm)
        return NodeRunner(node=node, executor=executor)

    wf_executor = WorkflowExecutor(config=wf_config, runner_factory=runner_factory)
    outputs = await wf_executor.run(initial_message="Go")

    assert len(outputs) == 4
    assert outputs["b"].text == "B done"
    assert outputs["c"].text == "C done"
    assert outputs["d"].text == "Merged"


@pytest.mark.asyncio
async def test_entry_node_receives_initial_message():
    """Entry nodes without explicit inputs should receive the initial message."""
    wf_config = WorkflowConfig(
        name="test",
        nodes=[
            WorkflowNode(id="research", agent="researcher", next=["format"]),
            WorkflowNode(id="format", agent="formatter"),
        ],
    )

    # Track what message the entry node actually receives
    captured_messages: list[str] = []

    node_map = {n.id: n for n in wf_config.nodes}
    responses = {
        "research": [AgentResponse(text="Found results.", stop_reason="end_turn")],
        "format": [AgentResponse(text="Formatted.", stop_reason="end_turn")],
    }

    def runner_factory(node_id: str) -> NodeRunner:
        node = node_map[node_id]
        config = AgentConfig(name=node.agent)
        mock_llm = MockLLMProvider(responses[node_id])
        executor = AgentExecutor(config=config, prompt_body=f"You are {node.agent}.", llm=mock_llm)
        runner = NodeRunner(node=node, executor=executor)
        if node_id == "research":
            # Capture the messages sent to the LLM for the entry node
            original_run = runner.run

            async def patched_run(*args, **kwargs):
                result = await original_run(*args, **kwargs)
                # Check what was sent to the LLM
                sent = mock_llm.calls[0]["messages"]
                user_msgs = [m.content for m in sent if m.role.value == "user"]
                captured_messages.extend(user_msgs)
                return result

            runner.run = patched_run
        return runner

    wf_executor = WorkflowExecutor(config=wf_config, runner_factory=runner_factory)
    outputs = await wf_executor.run(initial_message="research AI trends in 2026")

    assert outputs["research"].text == "Found results."
    # The entry node must have received the initial message, not an empty string
    assert len(captured_messages) == 1
    assert "research AI trends in 2026" in captured_messages[0]


@pytest.mark.asyncio
async def test_workflow_executor_single_node():
    """A workflow with just one node."""
    wf_config = WorkflowConfig(
        name="simple",
        nodes=[WorkflowNode(id="only", agent="agent")],
    )

    def runner_factory(node_id: str) -> NodeRunner:
        node = wf_config.nodes[0]
        config = AgentConfig(name="agent")
        mock_llm = MockLLMProvider([AgentResponse(text="Done.", stop_reason="end_turn")])
        return NodeRunner(node=node, executor=AgentExecutor(config=config, prompt_body="Agent.", llm=mock_llm))

    wf_executor = WorkflowExecutor(config=wf_config, runner_factory=runner_factory)
    outputs = await wf_executor.run(initial_message="Do it")

    assert len(outputs) == 1
    assert outputs["only"].text == "Done."
