# Step-by-Step Guide: How to Use Yunta Harness

Welcome to **Yunta**, the minimalist, provider-agnostic, specification-first terminal coding agent harness.

This guide walks you step-by-step from initial setup to mastering pair-programming workflows with Yunta directly in your terminal.

---

## Step 1: Prerequisites & Installation

Yunta requires **Python 3.11 or higher**.

1. **Clone the repository**:
   ```bash
   git clone https://github.com/j0sp0nc3/yunta.git
   cd yunta
   ```

2. **Create and activate a virtual environment (recommended)**:
   ```bash
   # Linux / macOS:
   python3 -m venv .venv
   source .venv/bin/activate

   # Windows (PowerShell):
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

3. **Install dependencies**:
   ```bash
   # Standard installation:
   pip install -r requirements.txt

   # Or editable install with dev tools:
   pip install -e .[dev]
   ```

---

## Step 2: Choose & Configure Your LLM Model

Yunta has **no default models and no hidden fallbacks**: you choose who pulls the plow via environment variables. Any provider supported by [LiteLLM](https://docs.litellm.ai/docs/providers) works out of the box.

Pick one of the following configurations:

### Option A: Google Gemini (Recommended for Getting Started)
```bash
# Linux / macOS:
export LLM_MODEL=gemini/gemini-3.7-flash
export GEMINI_API_KEY="your-google-ai-studio-key"

# Windows (PowerShell):
$env:LLM_MODEL="gemini/gemini-3.7-flash"
$env:GEMINI_API_KEY="your-google-ai-studio-key"
```

### Option B: Anthropic Claude (With Native Prompt Caching at 90% savings)
```bash
# Linux / macOS:
export LLM_MODEL=anthropic/claude-3-7-sonnet
export ANTHROPIC_API_KEY="sk-ant-..."

# Windows (PowerShell):
$env:LLM_MODEL="anthropic/claude-3-7-sonnet"
$env:ANTHROPIC_API_KEY="sk-ant-..."
```

### Option C: OpenAI (GPT-4o)
```bash
# Linux / macOS:
export LLM_MODEL=openai/gpt-4o
export OPENAI_API_KEY="sk-..."

# Windows (PowerShell):
$env:LLM_MODEL="openai/gpt-4o"
$env:OPENAI_API_KEY="sk-..."
```

### Option D: Free Local Models with Ollama (Zero API Keys)
1. Start Ollama (`ollama serve`).
2. Pull your favorite coding model: `ollama run qwen2.5-coder` or `ollama run llama3.3`.
3. Configure Yunta:
   ```bash
   export LLM_MODEL=ollama/qwen2.5-coder
   ```

### Option E: DeepSeek / OpenRouter or Custom OpenAI-Compatible Endpoints
```bash
export LLM_MODEL=openrouter/deepseek/deepseek-chat
export LLM_API_KEY="your-key"
# Or for vLLM / LM Studio / LocalAI:
export LLM_MODEL=openai/your-model
export LLM_API_BASE=http://localhost:8000/v1
```

---

## Step 3: Validate Connection with the Universal Provider Test

Before starting work, verify in 5 seconds that your configured model responds and executes real tool calls properly:

```bash
python scripts/prueba_proveedor.py
```

The script runs a real round-trip task where the LLM writes a test file, inspects it, and verifies its contents:
```text
proveedor/modelo: gemini/gemini-3.7-flash
[tool] write_file {"path": "prueba_proveedor.txt", "content": "verificado por yunta"}
[tool] read_file {"path": "prueba_proveedor.txt"}
--- tokens: in=5213 out=173 ---
RESULTADO: OK
```
If you see `RESULTADO: OK`, your environment is 100% operational!

---

## Step 4: Launch the Interactive REPL

Run Yunta in your terminal:

```bash
# If installed via pip install -e .:
yunta

# Or directly:
python main.py
```

You will see the welcome banner and prompt:
```text
yunta – modelo: gemini/gemini-3.7-flash
Escribe tu consulta, /clear para limpiar, /exit para salir.

> 
```

---

## Step 5: Your First Turn (Exploration & Reading)

Ask the agent to inspect your project. Yunta streams text in **real-time** and calls native tools (`glob`, `grep`, `read_file`):

```text
> Explore the codebase structure and summarize key modules in a table.
```

Watch Yunta invoke tools cleanly:
```text
[tool] glob {"pattern": "*"}
[tool] read_file {"path": "pyproject.toml"}
Here is the project structure overview...
```

---

## Step 6: Surgical Code Editing & Diff Approvals

When you ask Yunta to make code modifications:
```text
> Add a `calculate_hash(text: str) -> str` helper using hashlib sha256 in utils.py
```

1. **Surgical Editing (`str_replace` or `write_file`)**: Yunta prepares the exact edit without blind file overwrites.
2. **Unified Diff Preview**: A Git-style diff is printed directly in your terminal:
   ```diff
   --- /dev/null
   +++ utils.py
   @@ -0,0 +1,5 @@
   +import hashlib
   +
   +def calculate_hash(text: str) -> str:
   +    return hashlib.sha256(text.encode("utf-8")).hexdigest()
   ```
3. **Human-in-the-Loop Confirmation**: The agent asks for your confirmation:
   ```text
   ¿Aprobar write_file en utils.py? (y/n): 
   ```
   - Press `y` (or Enter) to approve.
   - Press `n` to reject or request modifications.

---

## Step 7: REPL Commands & Session Control

At any point during your session, use these control commands:

| Command / Shortcut | Action | Description |
| :--- | :--- | :--- |
| **`/tokens`** | Token Telemetry | Displays cumulative prompt and completion tokens, highlighting tokens saved by **Prompt Caching**: `in=14200 (cached=11800) out=650`. |
| **`Ctrl+C`** | Graceful Interrupt | If the model is in a lengthy turn or executing a command and you want to stop it, press `Ctrl+C`. The turn cancels immediately and returns to the `> ` prompt without crashing the session or corrupting conversation history. |
| **`/clear`** | Reset Context | Clears message history for the current session to start fresh. |
| **`/exit`** | Exit & Learn | Analyzes session patterns, saves learned operational lessons to `.yunta/learnings.md`, and exits. |

---

## Step 8: Advanced Best Practices

### 1. Enforce Project Rules with `AGENTS.md`
Place an `AGENTS.md` file in the root of your project:
```markdown
# AGENTS.md
- Style: Strict PEP 8.
- Testing: Always run `python -m pytest` after editing code.
- Database: Exclusively SQLAlchemy 2.0 with asyncpg.
```
Yunta reads and injects this file automatically into its System Prompt on every run.

### 2. Connect External Tools with MCP (Model Context Protocol)
Connect local MCP servers by creating `.yunta/mcp.json`:
```json
{
  "mcpServers": {
    "db": {
      "command": "python",
      "args": ["servers/db_server.py"]
    }
  }
}
```
Yunta registers discovered tools automatically as `mcp__db__<tool_name>`.

### 3. Embed Yunta as a Python Library
Embed Yunta programmatically into custom automation pipelines:
```python
from yunta import Agent, LiteLLMProvider

provider = LiteLLMProvider(system="You are a concise code refactoring assistant.")
agent = Agent(provider=provider, system=provider.system)

output = agent.send("Review and format code in src/main.py")
print(output)
```

---

You are now fully equipped to build verified, high-quality software with **Yunta** under the **Spec-Driven Development** paradigm!
