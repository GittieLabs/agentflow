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
from agentflow.events import EventBus
from agentflow.storage import FileSystemStorage, InMemoryStorage, S3Storage
from agentflow.tools import HTTPToolDispatcher, LocalToolDispatcher, ToolRegistry
from agentflow.providers import AnthropicProvider, GoogleGenAIProvider, MockLLMProvider, OpenAICompatProvider
from agentflow.session import ArtifactStore, Scratchpad, Session, SessionManager
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
    "Scratchpad",
    "Session",
    "SessionManager",
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

__version__ = "0.1.0"
