"""
Langfuse observability handler for agentflow EventBus.

Maps agentflow events to the Langfuse trace/span/generation hierarchy:

  WORKFLOW_STARTED     → trace(name=workflow_name)
  NODE_STARTED         → trace.span(name=node_id)
  LLM_CALL_COMPLETED   → span.generation(model, usage, latency) — nested under node span
  TOOL_CALLED          → span.span(name="tool:tool_name")
  NODE_COMPLETED       → close span
  WORKFLOW_COMPLETED   → close trace
  ERROR                → mark span/trace as error

Requirements:
    pip install langfuse>=2.0   (or gittielabs-agentflow[telemetry])

Usage:
    from agentflow.telemetry import LangfuseEventHandler
    from agentflow import EventBus, WORKFLOW_STARTED, WORKFLOW_COMPLETED, ...

    bus = EventBus()
    handler = LangfuseEventHandler(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
        host=os.getenv("LANGFUSE_BASE_URL"),   # e.g. https://us.cloud.langfuse.com
    )
    for event in (WORKFLOW_STARTED, WORKFLOW_COMPLETED, NODE_STARTED, NODE_COMPLETED,
                  LLM_CALL_COMPLETED, TOOL_CALLED, ERROR):
        bus.on(event, handler)

    # On shutdown:
    handler.flush()
"""
from __future__ import annotations

import logging
from typing import Any

from agentflow.events import (
    ERROR,
    LLM_CALL_COMPLETED,
    NODE_COMPLETED,
    NODE_STARTED,
    TOOL_CALLED,
    WORKFLOW_COMPLETED,
    WORKFLOW_STARTED,
)

logger = logging.getLogger("agentflow.telemetry")


class LangfuseEventHandler:
    """EventBus subscriber that creates Langfuse traces from agentflow events.

    Span keying strategy:
    - Traces are keyed by workflow name.
    - Spans are keyed by node_id (the ``node`` value emitted by NODE_STARTED).
    - LLM generations are nested under the matching node span (looked up by ``node`` key
      from LLM_CALL_COMPLETED data). Falls back to the first active trace if no span found.

    Thread safety: not thread-safe; designed for use within a single asyncio event loop.
    All state lives in plain dicts — fine for asyncio's cooperative multitasking.
    """

    def __init__(
        self,
        public_key: str,
        secret_key: str,
        host: str | None = None,
    ) -> None:
        """
        Args:
            public_key: Langfuse public key (LANGFUSE_PUBLIC_KEY).
            secret_key: Langfuse secret key (LANGFUSE_SECRET_KEY).
            host:       Optional Langfuse instance URL. Defaults to Langfuse Cloud EU.
                        Use ``https://us.cloud.langfuse.com`` for Langfuse Cloud US.
        """
        try:
            from langfuse import Langfuse
        except ImportError:
            raise ImportError(
                "langfuse package is required. "
                "Install with: pip install langfuse  "
                "or: pip install gittielabs-agentflow[telemetry]"
            )

        kwargs: dict[str, Any] = {
            "public_key": public_key,
            "secret_key": secret_key,
        }
        if host:
            kwargs["host"] = host

        self._lf = Langfuse(**kwargs)

        # Active objects — keyed by workflow name / node_id
        self._traces: dict[str, Any] = {}
        self._spans: dict[str, Any] = {}

    async def on_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Dispatch an event to the appropriate handler. Errors are caught and logged."""
        try:
            if event_type == WORKFLOW_STARTED:
                self._handle_workflow_started(data)
            elif event_type == WORKFLOW_COMPLETED:
                self._handle_workflow_completed(data)
            elif event_type == NODE_STARTED:
                self._handle_node_started(data)
            elif event_type == NODE_COMPLETED:
                self._handle_node_completed(data)
            elif event_type == LLM_CALL_COMPLETED:
                self._handle_llm_call_completed(data)
            elif event_type == TOOL_CALLED:
                self._handle_tool_called(data)
            elif event_type == ERROR:
                self._handle_error(data)
        except Exception:
            logger.warning("LangfuseEventHandler error on event '%s'", event_type, exc_info=True)

    # ─── Event handlers ──────────────────────────────────────────────────────

    def _handle_workflow_started(self, data: dict[str, Any]) -> None:
        workflow = data.get("workflow", "unknown")
        trace = self._lf.trace(name=workflow, metadata=data)
        self._traces[workflow] = trace
        logger.debug("Langfuse trace created: %s", workflow)

    def _handle_workflow_completed(self, data: dict[str, Any]) -> None:
        workflow = data.get("workflow", "unknown")
        trace = self._traces.pop(workflow, None)
        if trace:
            trace.update(
                output=data.get("result", ""),
                metadata={"nodes_completed": data.get("nodes_completed", 0)},
            )
            logger.debug("Langfuse trace closed: %s", workflow)

    def _handle_node_started(self, data: dict[str, Any]) -> None:
        node = data.get("node", "unknown")
        # Find the most recently opened trace to attach this span to
        trace = next(iter(self._traces.values()), None) if self._traces else None
        if trace:
            span = trace.span(name=node, input=data)
            self._spans[node] = span
            logger.debug("Langfuse span created: %s", node)

    def _handle_node_completed(self, data: dict[str, Any]) -> None:
        node = data.get("node", "unknown")
        span = self._spans.pop(node, None)
        if span:
            span.end(
                output=data.get("output", ""),
                metadata={"agent": data.get("agent", "")},
            )
            logger.debug("Langfuse span closed: %s", node)

    def _handle_llm_call_completed(self, data: dict[str, Any]) -> None:
        """Nest an LLM generation under the appropriate node span.

        Uses the ``node`` key from LLM_CALL_COMPLETED (threaded from AgentExecutor
        through node_id parameter). Falls back to the first active trace.
        """
        node = data.get("node") or data.get("agent", "unknown")
        span = self._spans.get(node)
        parent = span if span is not None else next(iter(self._traces.values()), None)

        if parent is None:
            return

        input_tokens = data.get("input_tokens", 0)
        output_tokens = data.get("output_tokens", 0)

        parent.generation(
            name=f"{data.get('agent', 'llm')}/round-{data.get('round', 0)}",
            model=data.get("model"),
            usage={
                "input": input_tokens,
                "output": output_tokens,
                "total": input_tokens + output_tokens,
            },
            metadata={
                "round": data.get("round"),
                "elapsed_ms": data.get("elapsed_ms"),
                "stop_reason": data.get("stop_reason"),
                "tool_calls": data.get("tool_calls", 0),
            },
        )

    def _handle_tool_called(self, data: dict[str, Any]) -> None:
        node = data.get("node", "unknown")
        span = self._spans.get(node)
        if span:
            tool_name = data.get("tool", "unknown")
            span.span(
                name=f"tool:{tool_name}",
                input=data.get("input"),
                metadata={"round": data.get("round")},
            )

    def _handle_error(self, data: dict[str, Any]) -> None:
        node = data.get("node", "unknown")
        span = self._spans.pop(node, None)
        if span:
            span.end(
                level="ERROR",
                status_message=data.get("error", "unknown error"),
            )

    # ─── Lifecycle ───────────────────────────────────────────────────────────

    def flush(self) -> None:
        """Flush pending events to Langfuse. Call this on application shutdown."""
        try:
            self._lf.flush()
            logger.debug("Langfuse flush completed")
        except Exception:
            logger.warning("Langfuse flush error", exc_info=True)
