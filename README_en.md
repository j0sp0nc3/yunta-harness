# yunta

**English** | [Español](README.md)

![logo](docs/logo.png)

Terminal coding agent harness, strictly model-provider agnostic.

*Yunta*: a team of oxen yoked together to plow the field — you and the agent, no matter which model pulls from the other side.

> 🎯 **Spec-Driven Development (SDD)**: Yunta is purpose-built to turn formal specifications (`AGENTS.md`) into verified software through surgical editing (`str_replace`), test oracles (`pytest`), and Prompt Caching. [Read the full SDD Architecture & Presentation](docs/sdd_en.md).

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

## Installation

Requires Python 3.10 or higher.

```bash
git clone https://github.com/j0sp0nc3/yunta.git
cd yunta
pip install -r requirements.txt
```

Or install in editable mode:

```bash
pip install -e .
```

---

## Model Configuration

Yunta has **no default models**: you choose who pulls the plow by setting your environment variables.

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

Launch the interactive REPL:

```bash
python main.py
# Or if installed via pip install -e .:
yunta
```

### REPL Commands
- `/clear`: Clears conversation history for the current session.
- `/tokens`: Displays total token consumption (prompt and completion) for the session.
- `/exit`: Saves session learnings to `.yunta/learnings.md` and exits.
- `Ctrl+C`: Gracefully interrupts the current turn and returns to the `> ` prompt without closing the session.

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
