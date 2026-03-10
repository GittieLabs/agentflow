"""
Workflow executor.

Walks a WorkflowDAG, executing nodes in topological order. Supports
parallel execution of independent nodes via asyncio.TaskGroup.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Awaitable

from agentflow.config.schemas import WorkflowConfig
from agentflow.events import EventBus, WORKFLOW_STARTED, WORKFLOW_COMPLETED, NODE_STARTED, NODE_COMPLETED, ERROR
from agentflow.types import NodeOutput
from agentflow.workflow.dag import WorkflowDAG
from agentflow.workflow.node import NodeRunner

logger = logging.getLogger("agentflow.workflow")

# Type for a factory that creates NodeRunner for a given node_id
NodeRunnerFactory = Callable[[str], Awaitable[NodeRunner] | NodeRunner]


class WorkflowExecutor:
    """
    Executes a workflow DAG by walking nodes in dependency order.

    Parallel nodes (those with no dependency between them) are executed
    concurrently using asyncio.gather. Sequential nodes run one at a time.
    """

    def __init__(
        self,
        config: WorkflowConfig,
        runner_factory: NodeRunnerFactory,
        event_bus: EventBus | None = None,
    ) -> None:
        self._dag = WorkflowDAG(config)
        self._factory = runner_factory
        self._events = event_bus

    @property
    def dag(self) -> WorkflowDAG:
        return self._dag

    async def run(
        self,
        initial_message: str = "",
        session_id: str | None = None,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, NodeOutput]:
        """
        Execute the full workflow.

        Args:
            initial_message: Message to pass to entry nodes
            session_id: Session ID for scratchpad/artifact storage
            variables: Template variables for prompt rendering

        Returns:
            Dict of node_id -> NodeOutput for all executed nodes
        """
        if self._events:
            await self._events.emit(WORKFLOW_STARTED, {"workflow": self._dag.name})

        # Validate DAG
        errors = self._dag.validate()
        if errors:
            raise ValueError(f"Invalid workflow: {'; '.join(errors)}")

        outputs: dict[str, NodeOutput] = {}
        completed: set[str] = set()

        # Seed entry nodes with the initial message
        entry_nodes = set(self._dag.entry_nodes())

        # Process nodes in waves until all are complete
        while True:
            ready = self._dag.ready_nodes(completed)
            if not ready:
                break

            # Group ready nodes by execution mode
            parallel_batch: list[str] = []
            sequential_batch: list[str] = []

            for nid in ready:
                node = self._dag.nodes[nid]
                if node.mode == "parallel":
                    parallel_batch.append(nid)
                else:
                    sequential_batch.append(nid)

            # Execute parallel nodes concurrently
            if parallel_batch:
                tasks = []
                for nid in parallel_batch:
                    tasks.append(self._run_node(
                        nid, outputs, entry_nodes, initial_message, session_id, variables
                    ))
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for nid, result in zip(parallel_batch, results):
                    if isinstance(result, Exception):
                        logger.error("Node %s failed: %s", nid, result)
                        if self._events:
                            await self._events.emit(ERROR, {"node": nid, "error": str(result)})
                        outputs[nid] = NodeOutput(
                            node_id=nid,
                            agent_id="",
                            text=f"Error: {result}",
                            metadata={"error": True},
                        )
                    else:
                        outputs[nid] = result
                    completed.add(nid)

            # Execute sequential nodes one at a time
            for nid in sequential_batch:
                try:
                    result = await self._run_node(
                        nid, outputs, entry_nodes, initial_message, session_id, variables
                    )
                    outputs[nid] = result
                except Exception as exc:
                    logger.error("Node %s failed: %s", nid, exc)
                    if self._events:
                        await self._events.emit(ERROR, {"node": nid, "error": str(exc)})
                    outputs[nid] = NodeOutput(
                        node_id=nid,
                        agent_id="",
                        text=f"Error: {exc}",
                        metadata={"error": True},
                    )
                completed.add(nid)

        if self._events:
            await self._events.emit(WORKFLOW_COMPLETED, {
                "workflow": self._dag.name,
                "nodes_completed": len(completed),
            })

        return outputs

    async def _run_node(
        self,
        node_id: str,
        prior_outputs: dict[str, NodeOutput],
        entry_nodes: set[str],
        initial_message: str,
        session_id: str | None,
        variables: dict[str, Any] | None,
    ) -> NodeOutput:
        """Execute a single node, resolving its runner from the factory."""
        if self._events:
            await self._events.emit(NODE_STARTED, {"node": node_id})

        runner = self._factory(node_id)
        if asyncio.iscoroutine(runner):
            runner = await runner

        # For entry nodes with no prior outputs, inject the initial message
        effective_outputs = dict(prior_outputs)
        if node_id in entry_nodes and not prior_outputs:
            effective_outputs["__initial__"] = NodeOutput(
                node_id="__initial__",
                agent_id="",
                text=initial_message,
            )

        result = await runner.run(
            prior_outputs=effective_outputs,
            session_id=session_id,
            variables=variables,
        )

        if self._events:
            await self._events.emit(NODE_COMPLETED, {
                "node": node_id,
                "agent": result.agent_id,
            })

        return result
