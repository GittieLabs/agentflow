"""Tests for workflow: WorkflowDAG, NodeRunner, WorkflowExecutor."""
import json
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


# ── Named inputs ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_node_runner_named_inputs_build_labeled_message():
    """Named inputs (no 'message' key) produce [key]\\nvalue labeled sections."""
    config = AgentConfig(name="assembler")
    mock_llm = MockLLMProvider([
        AgentResponse(text="Assembly complete.", stop_reason="end_turn"),
    ])
    executor = AgentExecutor(config=config, prompt_body="You assemble documents.", llm=mock_llm)

    node = WorkflowNode(
        id="assemble",
        agent="assembler",
        inputs={
            "outline": "outline_node.text",
            "sections": "write_node.text",
        },
    )
    runner = NodeRunner(node=node, executor=executor)

    prior = {
        "outline_node": NodeOutput(node_id="outline_node", agent_id="outliner", text="# Outline content"),
        "write_node": NodeOutput(node_id="write_node", agent_id="writer", text="## Section 1\nBody text."),
    }
    result = await runner.run(prior_outputs=prior)
    assert result.text == "Assembly complete."

    # Verify the assembled message was delivered with labeled sections
    sent_messages = mock_llm.calls[0]["messages"]
    user_content = next(m.content for m in sent_messages if m.role.value == "user")
    assert "[outline]\n# Outline content" in user_content
    assert "[sections]\n## Section 1\nBody text." in user_content


@pytest.mark.asyncio
async def test_node_runner_named_inputs_preserve_definition_order():
    """Named inputs appear in YAML-definition order, not hash order."""
    config = AgentConfig(name="merger")
    mock_llm = MockLLMProvider([
        AgentResponse(text="Merged.", stop_reason="end_turn"),
    ])
    executor = AgentExecutor(config=config, prompt_body="You merge results.", llm=mock_llm)

    # Define inputs in a deliberate order: analysis, then summary
    node = WorkflowNode(
        id="report",
        agent="merger",
        inputs={
            "analysis": "analyze.text",
            "summary": "summarize.text",
        },
    )
    runner = NodeRunner(node=node, executor=executor)

    prior = {
        "analyze": NodeOutput(node_id="analyze", agent_id="analyst", text="Deep analysis here."),
        "summarize": NodeOutput(node_id="summarize", agent_id="summarizer", text="Brief summary here."),
    }
    await runner.run(prior_outputs=prior)

    sent_messages = mock_llm.calls[0]["messages"]
    user_content = next(m.content for m in sent_messages if m.role.value == "user")

    # analysis must appear before summary
    analysis_pos = user_content.index("[analysis]")
    summary_pos = user_content.index("[summary]")
    assert analysis_pos < summary_pos


@pytest.mark.asyncio
async def test_node_runner_named_inputs_missing_upstream_node_is_empty():
    """If a referenced upstream node has no output, that section resolves to empty."""
    config = AgentConfig(name="assembler")
    mock_llm = MockLLMProvider([
        AgentResponse(text="Done.", stop_reason="end_turn"),
    ])
    executor = AgentExecutor(config=config, prompt_body="Assembler.", llm=mock_llm)

    node = WorkflowNode(
        id="assemble",
        agent="assembler",
        inputs={
            "outline": "outline_node.text",
            "sections": "missing_node.text",   # 'missing_node' not in prior_outputs
        },
    )
    runner = NodeRunner(node=node, executor=executor)

    prior = {
        "outline_node": NodeOutput(node_id="outline_node", agent_id="outliner", text="Outline here."),
        # 'missing_node' intentionally absent
    }
    result = await runner.run(prior_outputs=prior)
    assert result.text == "Done."

    sent_messages = mock_llm.calls[0]["messages"]
    user_content = next(m.content for m in sent_messages if m.role.value == "user")
    assert "[outline]\nOutline here." in user_content
    assert "[sections]\n" in user_content   # label present, value empty


@pytest.mark.asyncio
async def test_workflow_executor_named_inputs_multi_node():
    """
    Integration test: fan-out -> two parallel workers -> merge node with named inputs.

    Verifies that the merge node receives labeled [analysis] and [summary]
    sections in definition order when the workflow uses named inputs.
    """
    wf_config = WorkflowConfig(
        name="named_inputs_pipeline",
        nodes=[
            WorkflowNode(id="research", agent="researcher", next=["analyze", "summarize"]),
            WorkflowNode(
                id="analyze",
                agent="analyst",
                mode="parallel",
                inputs={"message": "research.text"},
                next=["report"],
            ),
            WorkflowNode(
                id="summarize",
                agent="summarizer",
                mode="parallel",
                inputs={"message": "research.text"},
                next=["report"],
            ),
            WorkflowNode(
                id="report",
                agent="reporter",
                inputs={
                    "analysis": "analyze.text",
                    "summary": "summarize.text",
                },
            ),
        ],
    )

    node_map = {n.id: n for n in wf_config.nodes}
    responses = {
        "research": [AgentResponse(text="Raw findings.", stop_reason="end_turn")],
        "analyze": [AgentResponse(text="Key insights.", stop_reason="end_turn")],
        "summarize": [AgentResponse(text="Brief overview.", stop_reason="end_turn")],
        "report": [AgentResponse(text="Final report.", stop_reason="end_turn")],
    }
    captured: dict[str, str] = {}

    def runner_factory(node_id: str) -> NodeRunner:
        node = node_map[node_id]
        agent_config = AgentConfig(name=node.agent)
        mock_llm = MockLLMProvider(responses[node_id])
        executor = AgentExecutor(config=agent_config, prompt_body=f"You are {node.agent}.", llm=mock_llm)
        runner = NodeRunner(node=node, executor=executor)

        if node_id == "report":
            original_resolve = runner._resolve_message

            def capturing_resolve(prior_outputs):
                msg = original_resolve(prior_outputs)
                captured["report_message"] = msg
                return msg

            runner._resolve_message = capturing_resolve

        return runner

    wf_executor = WorkflowExecutor(config=wf_config, runner_factory=runner_factory)
    outputs = await wf_executor.run(initial_message="Research AI trends")

    assert outputs["report"].text == "Final report."

    report_msg = captured["report_message"]
    assert "[analysis]\nKey insights." in report_msg
    assert "[summary]\nBrief overview." in report_msg
    # analysis defined first — must appear before summary
    assert report_msg.index("[analysis]") < report_msg.index("[summary]")


# ── Schema validation ────────────────────────────────────────────────────────


def test_schema_agent_or_handler_required():
    """Node must have either agent or handler, not both, not neither."""
    with pytest.raises(ValueError, match="must set 'agent' or 'handler'"):
        WorkflowNode(id="bad", agent=None, handler=None)

    with pytest.raises(ValueError, match="set either 'agent' or 'handler', not both"):
        WorkflowNode(id="bad", agent="some_agent", handler="some_handler")


def test_schema_handler_node_valid():
    """A handler node (no agent) is valid."""
    node = WorkflowNode(id="code", handler="my_handler")
    assert node.handler == "my_handler"
    assert node.agent is None


def test_schema_foreach_field():
    """foreach is an optional string field."""
    node = WorkflowNode(id="loop", agent="writer", foreach="toc.artifacts.sections")
    assert node.foreach == "toc.artifacts.sections"


# ── DAG validation: foreach refs ─────────────────────────────────────────────


def test_dag_validate_foreach_bad_ref():
    """foreach referencing a non-existent node produces a validation error."""
    config = WorkflowConfig(
        name="test",
        nodes=[
            WorkflowNode(
                id="loop",
                agent="writer",
                foreach="nonexistent.artifacts.items",
            ),
        ],
    )
    dag = WorkflowDAG(config)
    errors = dag.validate()
    assert any("nonexistent" in e for e in errors)


def test_dag_validate_foreach_valid_ref():
    """foreach referencing an existing node passes validation."""
    config = WorkflowConfig(
        name="test",
        nodes=[
            WorkflowNode(id="source", agent="producer", next=["loop"]),
            WorkflowNode(
                id="loop",
                agent="writer",
                foreach="source.artifacts.items",
            ),
        ],
    )
    dag = WorkflowDAG(config)
    assert dag.validate() == []


# ── Handler nodes ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handler_node_basic():
    """A handler node runs a registered Python function instead of an LLM."""
    async def my_handler(message: str, prior_outputs: dict) -> NodeOutput:
        return NodeOutput(
            node_id="transform",
            agent_id="my_handler",
            text=f"Transformed: {message}",
        )

    wf_config = WorkflowConfig(
        name="handler_test",
        nodes=[
            WorkflowNode(id="source", agent="source_agent", next=["transform"]),
            WorkflowNode(
                id="transform",
                handler="my_handler",
                inputs={"message": "source.text"},
            ),
        ],
    )

    node_map = {n.id: n for n in wf_config.nodes}

    def runner_factory(node_id: str) -> NodeRunner:
        node = node_map[node_id]
        config = AgentConfig(name=node.agent or "")
        mock_llm = MockLLMProvider([
            AgentResponse(text="Source output.", stop_reason="end_turn"),
        ])
        return NodeRunner(
            node=node,
            executor=AgentExecutor(config=config, prompt_body="Source.", llm=mock_llm),
        )

    executor = WorkflowExecutor(
        config=wf_config,
        runner_factory=runner_factory,
        handlers={"my_handler": my_handler},
    )
    outputs = await executor.run(initial_message="Input")

    assert outputs["source"].text == "Source output."
    assert outputs["transform"].text == "Transformed: Source output."


@pytest.mark.asyncio
async def test_handler_node_with_named_inputs():
    """Handler nodes receive labeled sections from named inputs."""
    received_messages: list[str] = []

    async def capture_handler(message: str, prior_outputs: dict) -> NodeOutput:
        received_messages.append(message)
        return NodeOutput(node_id="merge", agent_id="capture", text="merged")

    wf_config = WorkflowConfig(
        name="handler_inputs",
        nodes=[
            WorkflowNode(id="a", agent="a_agent", next=["b", "merge"]),
            WorkflowNode(id="b", agent="b_agent", inputs={"message": "a.text"}, next=["merge"]),
            WorkflowNode(
                id="merge",
                handler="capture",
                inputs={"first": "a.text", "second": "b.text"},
            ),
        ],
    )

    node_map = {n.id: n for n in wf_config.nodes}
    responses = {
        "a": [AgentResponse(text="Alpha", stop_reason="end_turn")],
        "b": [AgentResponse(text="Beta", stop_reason="end_turn")],
    }

    def runner_factory(node_id: str) -> NodeRunner:
        node = node_map[node_id]
        config = AgentConfig(name=node.agent or "")
        mock_llm = MockLLMProvider(responses.get(node_id, []))
        return NodeRunner(
            node=node,
            executor=AgentExecutor(config=config, prompt_body=".", llm=mock_llm),
        )

    executor = WorkflowExecutor(
        config=wf_config,
        runner_factory=runner_factory,
        handlers={"capture": capture_handler},
    )
    await executor.run(initial_message="Go")

    assert len(received_messages) == 1
    msg = received_messages[0]
    assert "[first]\nAlpha" in msg
    assert "[second]\nBeta" in msg


@pytest.mark.asyncio
async def test_handler_not_registered_raises():
    """Referencing an unregistered handler raises ValueError."""
    wf_config = WorkflowConfig(
        name="test",
        nodes=[
            WorkflowNode(id="code", handler="nonexistent"),
        ],
    )

    executor = WorkflowExecutor(
        config=wf_config,
        runner_factory=lambda nid: None,  # never called
        handlers={},
    )
    outputs = await executor.run(initial_message="Go")
    # Node fails with an error message
    assert "error" in outputs["code"].metadata
    assert "nonexistent" in outputs["code"].text


# ── Foreach nodes ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_foreach_basic():
    """A foreach node runs once per item in the referenced list artifact."""
    wf_config = WorkflowConfig(
        name="foreach_test",
        nodes=[
            WorkflowNode(id="source", handler="produce_list", next=["process"]),
            WorkflowNode(
                id="process",
                agent="processor",
                foreach="source.artifacts.items",
            ),
        ],
    )

    async def produce_list(message: str, prior_outputs: dict) -> NodeOutput:
        return NodeOutput(
            node_id="source",
            agent_id="produce_list",
            text="Items ready.",
            artifacts={"items": ["apple", "banana", "cherry"]},
        )

    node_map = {n.id: n for n in wf_config.nodes}
    # Need 3 responses — one per foreach iteration
    call_count = 0

    def runner_factory(node_id: str) -> NodeRunner:
        nonlocal call_count
        node = node_map[node_id]
        config = AgentConfig(name=node.agent or "")
        mock_llm = MockLLMProvider([
            AgentResponse(text=f"Processed item", stop_reason="end_turn"),
        ])
        return NodeRunner(
            node=node,
            executor=AgentExecutor(config=config, prompt_body="Process each item.", llm=mock_llm),
        )

    executor = WorkflowExecutor(
        config=wf_config,
        runner_factory=runner_factory,
        handlers={"produce_list": produce_list},
    )
    outputs = await executor.run(initial_message="Go")

    assert outputs["source"].text == "Items ready."
    assert "results" in outputs["process"].artifacts
    assert len(outputs["process"].artifacts["results"]) == 3
    assert outputs["process"].metadata.get("foreach") is True
    assert outputs["process"].metadata.get("iterations") == 3


@pytest.mark.asyncio
async def test_foreach_accumulation():
    """Each foreach iteration can access prior results via loop variables."""
    captured_vars: list[dict] = []

    wf_config = WorkflowConfig(
        name="accumulation",
        nodes=[
            WorkflowNode(id="source", handler="list_maker", next=["writer"]),
            WorkflowNode(
                id="writer",
                agent="writer_agent",
                foreach="source.artifacts.items",
            ),
        ],
    )

    async def list_maker(message: str, prior_outputs: dict) -> NodeOutput:
        return NodeOutput(
            node_id="source", agent_id="list_maker", text="Ready.",
            artifacts={"items": ["sec1", "sec2", "sec3"]},
        )

    node_map = {n.id: n for n in wf_config.nodes}

    def runner_factory(node_id: str) -> NodeRunner:
        node = node_map[node_id]
        config = AgentConfig(name=node.agent or "")
        mock_llm = MockLLMProvider([
            AgentResponse(text="Written.", stop_reason="end_turn"),
        ])
        executor = AgentExecutor(config=config, prompt_body="Write.", llm=mock_llm)
        runner = NodeRunner(node=node, executor=executor)

        original_run = runner.run

        async def capturing_run(prior_outputs, session_id=None, variables=None):
            if variables:
                captured_vars.append(dict(variables))
            return await original_run(prior_outputs=prior_outputs, session_id=session_id, variables=variables)

        runner.run = capturing_run
        return runner

    executor = WorkflowExecutor(
        config=wf_config,
        runner_factory=runner_factory,
        handlers={"list_maker": list_maker},
    )
    outputs = await executor.run(initial_message="Go")

    assert len(captured_vars) == 3

    # First iteration: no prior results
    assert captured_vars[0]["loop_index"] == "0"
    assert captured_vars[0]["loop_total"] == "3"
    assert captured_vars[0]["loop_prior_results"] == ""

    # Second iteration: has first result
    assert captured_vars[1]["loop_index"] == "1"
    assert "Written." in captured_vars[1]["loop_prior_results"]

    # Third iteration: has first two results
    assert captured_vars[2]["loop_index"] == "2"


@pytest.mark.asyncio
async def test_foreach_empty_list():
    """Foreach with an empty list produces empty results, no error."""
    wf_config = WorkflowConfig(
        name="empty",
        nodes=[
            WorkflowNode(id="source", handler="empty_list", next=["process"]),
            WorkflowNode(id="process", agent="proc", foreach="source.artifacts.items"),
        ],
    )

    async def empty_list(message: str, prior_outputs: dict) -> NodeOutput:
        return NodeOutput(
            node_id="source", agent_id="empty_list", text="Empty.",
            artifacts={"items": []},
        )

    executor = WorkflowExecutor(
        config=wf_config,
        runner_factory=lambda nid: None,
        handlers={"empty_list": empty_list},
    )
    outputs = await executor.run(initial_message="Go")

    assert outputs["process"].artifacts["results"] == []
    assert outputs["process"].metadata["iterations"] == 0


@pytest.mark.asyncio
async def test_foreach_with_handler():
    """A foreach node can use a handler instead of an LLM agent."""
    wf_config = WorkflowConfig(
        name="foreach_handler",
        nodes=[
            WorkflowNode(id="source", handler="make_items", next=["transform"]),
            WorkflowNode(
                id="transform",
                handler="process_item",
                foreach="source.artifacts.items",
            ),
        ],
    )

    async def make_items(message: str, prior_outputs: dict) -> NodeOutput:
        return NodeOutput(
            node_id="source", agent_id="make_items", text="Ready.",
            artifacts={"items": [1, 2, 3]},
        )

    async def process_item(message: str, prior_outputs: dict) -> NodeOutput:
        # __loop__ should be in prior_outputs
        loop = prior_outputs.get("__loop__")
        item = loop.artifacts["item"] if loop else "?"
        return NodeOutput(
            node_id="transform", agent_id="process_item",
            text=f"Doubled: {item * 2}",
        )

    executor = WorkflowExecutor(
        config=wf_config,
        runner_factory=lambda nid: None,
        handlers={"make_items": make_items, "process_item": process_item},
    )
    outputs = await executor.run(initial_message="Go")

    results = outputs["transform"].artifacts["results"]
    assert results == ["Doubled: 2", "Doubled: 4", "Doubled: 6"]


@pytest.mark.asyncio
async def test_foreach_mid_loop_failure():
    """If an iteration fails, the node returns partial results + error metadata."""
    call_count = 0

    wf_config = WorkflowConfig(
        name="fail_test",
        nodes=[
            WorkflowNode(id="source", handler="items", next=["process"]),
            WorkflowNode(id="process", handler="fail_on_2", foreach="source.artifacts.items"),
        ],
    )

    async def items(message: str, prior_outputs: dict) -> NodeOutput:
        return NodeOutput(
            node_id="source", agent_id="items", text="Ready.",
            artifacts={"items": ["a", "b", "c"]},
        )

    async def fail_on_2(message: str, prior_outputs: dict) -> NodeOutput:
        nonlocal call_count
        call_count += 1
        loop = prior_outputs.get("__loop__")
        idx = loop.artifacts["index"] if loop else 0
        if idx == 1:
            raise RuntimeError("Deliberate failure on item 2")
        return NodeOutput(
            node_id="process", agent_id="fail_on_2",
            text=f"OK: {loop.artifacts['item']}",
        )

    executor = WorkflowExecutor(
        config=wf_config,
        runner_factory=lambda nid: None,
        handlers={"items": items, "fail_on_2": fail_on_2},
    )
    outputs = await executor.run(initial_message="Go")

    result = outputs["process"]
    assert result.metadata.get("error") is True
    assert result.metadata.get("failed_index") == 1
    # First iteration succeeded
    assert result.artifacts["results"] == ["OK: a"]


@pytest.mark.asyncio
async def test_backward_compat_existing_workflows():
    """Existing workflows (agent-only, no foreach/handler) still work."""
    wf_config = WorkflowConfig(
        name="legacy",
        nodes=[
            WorkflowNode(id="a", agent="agent_a", next=["b"]),
            WorkflowNode(id="b", agent="agent_b"),
        ],
    )

    node_map = {n.id: n for n in wf_config.nodes}
    responses = {
        "a": [AgentResponse(text="A done.", stop_reason="end_turn")],
        "b": [AgentResponse(text="B done.", stop_reason="end_turn")],
    }

    def runner_factory(node_id: str) -> NodeRunner:
        node = node_map[node_id]
        config = AgentConfig(name=node.agent)
        mock_llm = MockLLMProvider(responses[node_id])
        return NodeRunner(
            node=node,
            executor=AgentExecutor(config=config, prompt_body=".", llm=mock_llm),
        )

    executor = WorkflowExecutor(config=wf_config, runner_factory=runner_factory)
    outputs = await executor.run(initial_message="Start")

    assert outputs["a"].text == "A done."
    assert outputs["b"].text == "B done."
