# Installation

AgentFlow requires **Python 3.11** or later.

## Core Package

The core package includes config loading, routing, workflow execution, session management, and the tool registry. It does not include any LLM provider SDKs.

```bash
pip install gittielabs-agentflow
```

Core dependencies are minimal: `pydantic`, `python-frontmatter`, `pyyaml`, and `httpx`.

## Provider Extras

Install the extras for the LLM providers you plan to use:

=== "Anthropic Claude"

    ```bash
    pip install "gittielabs-agentflow[anthropic]"
    ```

    Installs `anthropic>=0.42.0`. Use with `AnthropicProvider`.

=== "OpenAI / OpenAI-Compatible"

    ```bash
    pip install "gittielabs-agentflow[openai]"
    ```

    Installs `openai>=1.0.0`. Use with `OpenAICompatProvider`. Works with any OpenAI-compatible API (OpenAI, Azure OpenAI, Ollama, vLLM, etc.).

=== "Google Gemini"

    ```bash
    pip install "gittielabs-agentflow[google]"
    ```

    Installs `google-genai>=1.0.0`. Use with `GoogleGenAIProvider`.

## Optional Extras

| Extra | Install command | What it adds |
|-------|----------------|--------------|
| `s3` | `pip install "gittielabs-agentflow[s3]"` | S3 storage backend (`boto3`) |
| `vector` | `pip install "gittielabs-agentflow[vector]"` | Vector memory with Qdrant (`qdrant-client`) |
| `orchestration` | `pip install "gittielabs-agentflow[orchestration]"` | Multi-step orchestration primitives |
| `telemetry` | `pip install "gittielabs-agentflow[telemetry]"` | Langfuse event handler (`langfuse`) |

## Install Everything

```bash
pip install "gittielabs-agentflow[all]"
```

This installs all provider SDKs and optional extras.

## Development Setup

Clone the repository and install in editable mode with dev dependencies:

```bash
git clone https://github.com/GittieLabs/agentflow.git
cd agentflow
pip install -e ".[dev]"
```

Dev dependencies include `pytest`, `pytest-asyncio`, and `ruff` for linting.

Run the test suite:

```bash
pytest
```

Run the linter:

```bash
ruff check src/ tests/
```

## Environment Variables

Each provider reads its API key from standard environment variables:

| Provider | Environment Variable |
|----------|---------------------|
| Anthropic | `ANTHROPIC_API_KEY` |
| OpenAI | `OPENAI_API_KEY` |
| Google Gemini | `GOOGLE_API_KEY` |
| Langfuse | `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` |

Set these before running your agents:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

## Verifying the Installation

```python
import agentflow
print(agentflow.__version__)
# 0.5.0
```
