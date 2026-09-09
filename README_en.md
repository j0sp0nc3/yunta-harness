# Yunta: The Spec-Driven Development (SDD) Harness

**English** | [Español](README.md)

![logo](docs/logo.png)

[![PyPI version](https://img.shields.io/pypi/v/yunta-harness.svg)](https://pypi.org/project/yunta-harness/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Terminal coding agent harness, strictly model-provider agnostic.**

*Yunta*: a team of oxen yoked together to plow the field — you and the agent, no matter which model pulls from the other side.

## 🎯 Yunta: The Spec-Driven Development (SDD) Harness

In **Spec-Driven Development (SDD)**, code is not generated through ad-hoc guessing or intuition, but derived from formal specifications and verifiable contracts. Yunta operates as the **execution and verification harness**:

- 📋 **Strict Specification Consumption**: Reads `AGENTS.md` and repository guidelines on every cycle as the single source of truth.
- 🔬 **Surgical Code Editing (`str_replace`)**: Prevents file drift and accidental rewrites through exact string matching and uniqueness checks.
- 🛡️ **Human-in-the-Loop Diff Approvals**: Interactive unified diff previews before executing or writing changes to disk.
- ⚡ **Agnostic Prompt Caching**: Maintains large specifications in active context with up to 90% savings in input tokens and lower latency.
- 🔄 **Closed-Loop Verification**: The agent autonomously verifies changes against the test suite (`pytest`) before completing tasks.

👉 **[See Full Yunta + SDD Guide and Presentation](docs/sdd_en.md)**

Designed from the ground up to be completely independent of any single model provider: all LLM connectivity is handled 100% through [LiteLLM](https://docs.litellm.ai/docs/), meaning any supported provider works simply by changing an environment variable.

---

## Key Features

- **Provider-Agnostic**: Connect OpenAI, Anthropic Claude, Google Gemini, DeepSeek, Groq, or local models via Ollama/vLLM without changing any code.
- **Ultra-Minimal Core (~500 lines)**: Zero heavy agent frameworks (no LangChain, no CrewAI). Clean, auditable, hackable code.
- **Surgical Code Editing (`str_replace`)**: Deterministically edits exact file fragments with uniqueness verification, adhering to Anthropic Claude Code and SWE-bench standards.
- **Human-in-the-Loop Unified Diffs**: Inspect exactly which lines will be added or removed before approving write operations.
- **Agnostic Prompt Caching**: Automatic injection of cache breakpoints (`cache_control`) for Anthropic Claude and automatic prefix caching support for OpenAI/DeepSeek/Gemini, cutting input token costs by up to 90% and reducing latency.
- **Graceful Interrupt Handling (`Ctrl+C`)**: Cancel a long turn or running tool call instantly without crashing your REPL session or corrupting conversation history.
- **Native MCP (Model Context Protocol) Support**: Connect local `stdio` MCP servers over JSON-RPC 2.0 without third-party agent libraries.
- **Persistent Memory & Compound Learning**: Preserve key project facts across sessions (`.yunta/memory.json`) and store learned lessons (`.yunta/learnings.md`).
- **Subagent Research Delegation**: Delegate intensive read-only exploration to secondary subagents without polluting the primary context window.

---

## Step-by-Step Quickstart

👉 First time using Yunta? Follow the **[Complete Step-by-Step Guide (docs/quickstart_en.md)](docs/quickstart_en.md)** to learn everything from setting up your model to surgical diff editing and REPL controls.

---

## Installation

Requires Python 3.11 or higher.

### From PyPI (Recommended):
```bash
pip install yunta-harness
```
> **💡 Note on the package name:** On PyPI the package is distributed as `yunta-harness`, but the command you execute in your terminal is simply **`yunta`** (e.g. `yunta`, `yunta init .`, or `yunta "your prompt"`). You do not need to install it inside your existing app: it works as a global CLI tool (just like Git).

### From source repository (Development):
```bash
git clone https://github.com/j0sp0nc3/yunta-harness.git
cd yunta-harness
pip install -e .
```

---

## Model Configuration

Yunta has **no default models**: you choose who pulls the plow by setting your environment variables.
See the [Verified Provider Matrix](docs/PROVEEDORES.md) for tested models validated with the universal test script (`scripts/prueba_proveedor.py`).

### Google Gemini
```bash
export LLM_MODEL=gemini/gemini-3.5-flash
export GEMINI_API_KEY=your-api-key
```

### Anthropic Claude
```bash
export LLM_MODEL=anthropic/claude-3-7-sonnet
export ANTHROPIC_API_KEY=sk-ant-...
```

### OpenAI
```bash
export LLM_MODEL=openai/gpt-4o
export OPENAI_API_KEY=sk-...
```

### DeepSeek / OpenRouter
```bash
export LLM_MODEL=openrouter/deepseek/deepseek-chat
export LLM_API_KEY=your-openrouter-key
```

### Local Models (Ollama)
```bash
export LLM_MODEL=ollama/llama3.3
```

### Custom OpenAI-Compatible Endpoints (vLLM, LocalAI, etc.)
```bash
export LLM_MODEL=openai/your-local-model
export LLM_API_BASE=http://localhost:8000/v1
export LLM_API_KEY=dummy
```

---

## Usage & Commands

### CLI Invocation Modes (`yunta`)

- **Interactive REPL session**:
  ```bash
  yunta
  ```
- **Direct single-shot instruction**:
  ```bash
  yunta "Explain the structure of this repository and run the test suite"
  ```
- **Initialize SDD project (`SPEC.md`, `PLAN.md`, `AGENTS.md`)**:
  ```bash
  yunta init [idea_or_name]
  ```
- **Local governance audit ($0 in tokens)**:
  ```bash
  yunta check [path] [--json] [--tests]
  ```
- **VS Code Scaffolding (`.vscode/mcp.json` and `tasks.json`)**:
  ```bash
  yunta ide-init
  ```
- **Resume latest saved session**:
  ```bash
  yunta --resume  # or yunta -r
  ```
- **Stdio MCP Server (for Claude Desktop, Cursor, Windsurf)**:
  ```bash
  yunta serve-mcp  # or yunta mcp
  ```
- **Diagnostics and Help**:
  ```bash
  yunta --version  # or yunta -v
  yunta --help     # or yunta -h
  ```

### Interactive REPL Commands (inside Yunta)
- `/init [idea]`: Initializes an SDD project generating `SPEC.md`, `PLAN.md`, and `AGENTS.md`.
- `/sandbox [merge|discard]`: Creates or manages an isolated Git Worktree environment for risky operations.
- `/context`: Displays message count, estimated context tokens, and token budget consumption percentage (`YUNTA_MAX_TOKENS`).
- `/undo`: Reverts the latest file modification and restores previous contents ("Time-Travel Undo").
- `/permissions [clear]`: Lists persistent session permissions granted via 'always' or revokes them (`/permissions clear`).
- `/roi`: Displays the ROI telemetry dashboard, cache hit rate, and estimated USD cost savings.
- `/metrics`: Displays detailed execution metrics for tools, **startup tax**, errors, and interaction turns.
- `/tokens`: Displays total token consumption and cache hit rate.
- `/help`: Lists all available interactive commands.
- `/clear`: Clears conversation history for the current session.
- `/exit`: Saves session learnings to `.yunta/learnings.md` and exits.
- `Ctrl+C`: Gracefully interrupts the current turn without leaving orphaned `tool_use` blocks.

### Key Environment Variables
- `LLM_MODEL`: Target provider/model (e.g., `openai/gpt-4o`, `anthropic/claude-3-7-sonnet`, `gemini/gemini-3.7-flash`, `ollama/llama3.3`).
- `LLM_MODELS`: Comma-separated priority list for automatic fallback router on 429/503/quota limit.
- `LLM_API_BASE`: Base URL for custom OpenAI-compatible endpoints (e.g., `http://localhost:8000/v1`).
- `LLM_API_KEY`: API Key or Bearer token.
- `YUNTA_SYSTEM_PROMPT`: Overrides default system prompt.
- `YUNTA_MAX_TOKENS`: Maximum token budget for multi-stage compaction (default: `128000`).
- `YUNTA_MAX_MESSAGES`: Sliding window history limit (default: `40`).
- `YUNTA_YES`: Enables non-interactive auto-approval for all tools (equivalent to `-y` / `--yes`).
- `YUNTA_BLOCKLIST_EXTRA`: Path to extra regex blocklist file for bash tool safety.
- `YUNTA_ALLOW_FORCE`: Set to `1` to allow `git push --force` in bash tool.


---

## Python Library Usage (API v1.0)

Starting with version 1.0.0, you can embed Yunta directly into your Python applications or automation pipelines:

```python
from yunta import Agent, LiteLLMProvider, FeedbackStore

# Initialize the provider using LLM_MODEL environment variable
provider = LiteLLMProvider(system="You are a concise engineering assistant.")

# Instantiate agent with custom or automatic approvals
agent = Agent(provider=provider, system=provider.system, confirm=lambda name, detail: True)

# Send queries and receive structured execution outputs
response = agent.send("List files in the current workspace")
print(response)
```

---

## User Implementation Details

### 1. Project Context (`AGENTS.md`)
If you place an `AGENTS.md` file in the root of your project, Yunta automatically injects its contents into its system prompt. Use it to specify team conventions, non-negotiable coding rules, and testing commands.

### 2. File Editing & Approvals
When Yunta modifies code:
- **`str_replace`**: Replaces specific chunks of text. If the target string appears more than once, it fails with an ambiguity warning requesting more surrounding context lines.
- **Unified Diff Preview**: If a tool requires user confirmation, a Git-style unified diff is printed in the terminal before you confirm with `y` or cancel with `n`.

### 3. Persistent Memory
Yunta includes `remember` and `recall` tools to store project facts, architecture choices, or personal preferences inside `.yunta/memory.json`.

### 4. Model Context Protocol (MCP)
Connect tools from local `stdio` MCP servers by adding a `.yunta/mcp.json` file:

```json
{
  "mcpServers": {
    "weather": {
      "command": "python",
      "args": ["servers/weather_server.py"]
    }
  }
}
```
Discovered tools are automatically exposed to the agent as `mcp__weather__<tool_name>`.

### 5. Building Custom Tools
To add custom tools, create a Python file under `yunta/tools/` and use the `@registry.register` decorator:

```python
from . import _parse, registry

@registry.register(
    "my_tool",
    "Clear description of the tool for the model.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Input text"}
        },
        "required": ["query"]
    },
    requires_approval=False,
)
def my_tool(raw: str) -> str:
    args = _parse(raw)
    return f"Processed query: {args['query']}"
```

---

## Architecture Overview

Yunta is organized into clean, modular, and compact components:

```
main.py            -> REPL CLI entry point
yunta/
  api.py           -> Canonical neutral types (Message, Block, ToolDef, Response)
  provider.py      -> LiteLLM isolation boundary (streaming, 429/503 auto-retries)
  agent.py         -> Multi-turn loop, diff approvals, graceful Ctrl+C interrupt
  compact.py       -> Context management (SlidingWindow)
  feedback.py      -> Cross-session self-improvement (.yunta/learnings.md)
  mcp.py           -> Native JSON-RPC 2.0 stdio MCP client
  tools/           -> Native registry and tools
    files.py       -> read_file, write_file, str_replace (SWE-bench style)
    bash.py        -> Subprocess execution with timeout
    search.py      -> glob and grep within workspace
    memory.py      -> remember and recall (.yunta/memory.json)
    delegate.py    -> delegate_research with secondary subagent
```

For a comprehensive technical breakdown of the architecture, read the full [System Architecture Document](docs/architecture_en.md).

---

## License

This project is licensed under the [MIT License](LICENSE) - Copyright (c) 2026 j0sp0nc3 <beroiza79@gmail.com>.
