"""
AgentFlow — Context engineering framework for multi-agent systems.

A framework-agnostic toolkit for building multi-agent workflows with:
- Markdown + YAML front-matter config files (.prompt.md, .workflow.md)
- Pluggable LLM providers (Anthropic, OpenAI, Google)
- Hybrid routing (YAML rules + LLM fallback)
- DAG-based workflow execution (sync/parallel/async nodes)
- Session scratchpads and long-term memory
"""
from agentflow.types import (
    AgentResponse,
    Message,
    NodeMode,
    NodeOutput,
    Role,
    ToolCall,
    ToolResult,
)
from agentflow.protocols import (
    EventHandler,
    LLMProvider,
    MemoryStore,
    StorageBackend,
    ToolDispatcher,
)
from agentflow.agent import AgentExecutor, ContextAssembler, PromptTemplate
from agentflow.config import AgentConfig, ConfigLoader, RouterConfig, WorkflowConfig
from agentflow.events import (
    EventBus,
    LLM_CALL_STARTED,
    LLM_CALL_COMPLETED,
    NODE_STARTED,
    NODE_COMPLETED,
    TOOL_CALLED,
    TOOL_RESULT,
    WORKFLOW_STARTED,
    WORKFLOW_COMPLETED,
    ERROR,
)
from agentflow.storage import FileSystemStorage, InMemoryStorage, S3Storage
from agentflow.tools import HTTPToolDispatcher, LocalToolDispatcher, ToolRegistry
from agentflow.providers import AnthropicProvider, GoogleGenAIProvider, MockLLMProvider, OpenAICompatProvider
from agentflow.session import ArtifactStore, HistoryPersistence, MultiUserHistory, Scratchpad, Session, SessionManager
from agentflow.orchestration import ComplexityClassifier, DAGExecutor, Plan, PlanStep
from agentflow.memory import FileMemory, MemoryManager, VectorMemory
from agentflow.router import RouterEngine, RoutingResult, RuleEvaluator
from agentflow.workflow import NodeRunner, WorkflowDAG, WorkflowExecutor

__all__ = [
    # Types
    "AgentResponse",
    "Message",
    "NodeMode",
    "NodeOutput",
    "Role",
    "ToolCall",
    "ToolResult",
    # Protocols
    "EventHandler",
    "LLMProvider",
    "MemoryStore",
    "StorageBackend",
    "ToolDispatcher",
    # Agent
    "AgentExecutor",
    "ContextAssembler",
    "PromptTemplate",
    # Config
    "AgentConfig",
    "ConfigLoader",
    "RouterConfig",
    "WorkflowConfig",
    # Events
    "EventBus",
    "LLM_CALL_STARTED",
    "LLM_CALL_COMPLETED",
    "NODE_STARTED",
    "NODE_COMPLETED",
    "TOOL_CALLED",
    "TOOL_RESULT",
    "WORKFLOW_STARTED",
    "WORKFLOW_COMPLETED",
    "ERROR",
    # Storage
    "FileSystemStorage",
    "InMemoryStorage",
    "S3Storage",
    # Tools
    "HTTPToolDispatcher",
    "LocalToolDispatcher",
    "ToolRegistry",
    # Providers
    "AnthropicProvider",
    "GoogleGenAIProvider",
    "MockLLMProvider",
    "OpenAICompatProvider",
    # Session
    "ArtifactStore",
    "HistoryPersistence",
    "MultiUserHistory",
    "Scratchpad",
    "Session",
    "SessionManager",
    # Orchestration
    "ComplexityClassifier",
    "DAGExecutor",
    "Plan",
    "PlanStep",
    # Memory
    "FileMemory",
    "MemoryManager",
    "VectorMemory",
    # Router
    "RouterEngine",
    "RoutingResult",
    "RuleEvaluator",
    # Workflow
    "NodeRunner",
    "WorkflowDAG",
    "WorkflowExecutor",
]

__version__ = "0.2.0"
