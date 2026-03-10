"""
Workflow node runner.

Wraps an AgentExecutor as a DAG node, resolving input mappings from
prior node outputs and writing results to session scratchpads.
"""
from __future__ import annotations

import logging
from typing import Any

from agentflow.agent.runtime import AgentExecutor
from agentflow.config.schemas import WorkflowNode
from agentflow.session.scratchpad import Scratchpad
from agentflow.types import NodeOutput

logger = logging.getLogger("agentflow.workflow.node")


class NodeRunner:
    """
    Executes a single node within a workflow.

    Resolves input mappings (e.g., {message: "research.text"}) from prior
    node outputs, runs the agent, and writes the result to the scratchpad.
    """

    def __init__(
        self,
        node: WorkflowNode,
        executor: AgentExecutor,
        scratchpad: Scratchpad | None = None,
    ) -> None:
        self._node = node
        self._executor = executor
        self._scratchpad = scratchpad

    @property
    def node_id(self) -> str:
        return self._node.id

    @property
    def mode(self) -> str:
        return self._node.mode

    async def run(
        self,
        prior_outputs: dict[str, NodeOutput],
        session_id: str | None = None,
        variables: dict[str, Any] | None = None,
    ) -> NodeOutput:
        """
        Execute this node.

        Args:
            prior_outputs: Outputs from upstream nodes, keyed by node_id
            session_id: Current session ID
            variables: Template variables for prompt rendering

        Returns:
            NodeOutput from the agent execution
        """
        # Resolve input message from prior node outputs
        message = self._resolve_message(prior_outputs)

        # Write incoming context to scratchpad
        if self._scratchpad and prior_outputs:
            context_parts = []
            for nid, output in prior_outputs.items():
                if nid in self._predecessors():
                    context_parts.append(f"## From {nid}\n{output.text}")
            if context_parts:
                await self._scratchpad.write_scratch("\n\n".join(context_parts))

        # Run the agent
        result = await self._executor.run(
            message=message,
            session_id=session_id,
            node_id=self._node.id,
            variables=variables,
        )

        # Write output summary to scratchpad
        if self._scratchpad:
            await self._scratchpad.write_summary(result.text)

        return result

    def _resolve_message(self, prior_outputs: dict[str, NodeOutput]) -> str:
        """
        Build the message for this node from input mappings or prior outputs.

        Input mappings in the workflow config look like:
            inputs:
                message: "research.text"    # Use text from the 'research' node
                data: "extract.artifacts.leads"  # Use an artifact

        If no explicit 'message' input, concatenate all predecessor outputs.
        """
        inputs = self._node.inputs

        if "message" in inputs:
            ref = inputs["message"]
            return self._resolve_ref(ref, prior_outputs)

        # Default: concatenate all predecessor outputs
        preds = self._predecessors()
        if not preds:
            # Entry node — use the initial message injected by the executor
            initial = prior_outputs.get("__initial__")
            return initial.text if initial else ""

        parts = []
        for nid in preds:
            if nid in prior_outputs:
                parts.append(prior_outputs[nid].text)
        return "\n\n".join(parts)

    def _resolve_ref(self, ref: str, prior_outputs: dict[str, NodeOutput]) -> str:
        """Resolve a dotted reference like 'research.text' or 'extract.artifacts.leads'."""
        parts = ref.split(".")
        if len(parts) < 2:
            return ref

        node_id = parts[0]
        output = prior_outputs.get(node_id)
        if not output:
            return ""

        if parts[1] == "text":
            return output.text
        elif parts[1] == "artifacts" and len(parts) >= 3:
            return str(output.artifacts.get(parts[2], ""))

        return output.text

    def _predecessors(self) -> list[str]:
        """Get the node IDs that this node explicitly depends on via inputs."""
        preds = set()
        for ref in self._node.inputs.values():
            node_id = ref.split(".")[0]
            preds.add(node_id)
        return list(preds)
