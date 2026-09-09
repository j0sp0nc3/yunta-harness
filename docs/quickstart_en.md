# Step-by-Step Guide: How to Use Yunta Harness

Welcome to **Yunta**, the minimalist, provider-agnostic, specification-first terminal coding agent harness.

This guide walks you step-by-step from initial setup to mastering pair-programming workflows with Yunta directly in your terminal.

---

## Step 0: Mental Model — What Yunta Is and What It Is Not

Before touching any code, it is critical to understand the boundary between your tooling and your target software:

| Concept | What Yunta IS | What Yunta IS NOT |
| :--- | :--- | :--- |
| **Nature** | Assisted development CLI harness | Runtime application framework (like LangChain, AutoGen, or CrewAI) |
| **Location** | Your local developer terminal (the workbench) | The server where your final product runs (the furniture) |
| **Action** | `view_file`, `str_replace`, `bash`, `pytest` | Web server, production daemon, or cloud agent bot |
| **Deliverable** | Clean, tested, committed code in your repo | An application that depends on Yunta to run |

> 💡 **The Golden Rule**:  
> *"If you are thinking about how this runs in production, you are before using Yunta. If you are thinking about what code you need to write, it is time to open Yunta."*

### 5-Phase Methodology for New Projects

1. **Phase 0: Boundary Definition (in `AGENTS.md`)**:
   - What problem does it solve? (1 clear paragraph).
   - What is the final deliverable? (code, library, modules).
   - Where does it run in production? (e.g. Power Automate, AWS Lambda, Docker, React) — *NOT in Yunta*.
   - What is out of scope? (do not create local daemons for Yunta).
2. **Phase 1: Minimal Structure**:
   - Create directories `src/`, `tests/`, and `AGENTS.md`.
3. **Phase 2: Define Contracts (without implementing logic yet)**:
   - Create `src/api.py` with canonical `dataclasses` and types.
4. **Phase 3: First Surgical Task with Yunta**:
   - Launch `yunta` in the terminal and issue a focused prompt bound to the contract.
5. **Phase 4: Verification and Documentation**:
   - Run the project's test suite and document production deployment.

### Starter Template: `AGENTS.md` for Your Projects

Copy and paste this template into the root of any repository you plan to build with Yunta:

```markdown
# AGENTS.md — [Project Name]

## 1. Mission and Target Runtime (Runtime Boundary)
- **Purpose**: [Concise 1-paragraph summary]
- **Production Runtime**: [e.g. Power Automate + Dataverse / AWS Lambda / Docker / FastAPI] (NOT in Yunta).
- **Role of Yunta**: Development harness (reading tools, surgical editing, test execution).

## 2. Deliverables
- Source code in `src/`
- Unit test suite in `tests/`
- Types and contracts in `src/api.py`

## 3. Out of Scope
- NEVER create daemon services or terminal bots running inside Yunta.
- Do not assume local auth credentials that belong to the production runtime.
```

---

## Step 1: Installation & Name Distinction (`yunta-harness` vs `yunta`)

Yunta requires **Python 3.11 or higher**.

### 💡 Why is the package named `yunta-harness` while the command is `yunta`?
- **On PyPI (pip install):** The package is named **`yunta-harness`** because on `pypi.org` the short name `yunta` was historically registered by a bioinformatics project.
- **In your terminal (CLI command):** The command you execute is simply **`yunta`** (or `yunta init`) to keep it concise, intuitive, and easy to type.

### Installation Options:

#### Option A: From PyPI (Recommended)
Install Yunta once globally on your machine (just like Git or Docker):
```bash
pip install yunta-harness
```
*(Or use `pipx install yunta-harness` / `uv tool install yunta-harness` for isolated CLI tools).*

#### Option B: From Source Repository (Local development)
```bash
git clone https://github.com/j0sp0nc3/yunta-harness.git
cd yunta-harness
pip install -e .
```

---

## ❓ Should Yunta be installed inside my existing application?

**No, not at all.** Yunta is an external tool for your environment (the carpenter's workbench, not the furniture). You should never install it inside your project nor add it to `package.json`, `requirements.txt`, or `pom.xml`.

Whatever tech stack your application uses (JavaScript, Node.js, Python, Go, Rust, React, etc.), simply open a terminal in its directory:

```bash
# 1. Navigate to your existing application
cd /path/to/your/existing-app

# 2. Initialize project context (generates AGENTS.md, SPEC.md, and PLAN.md without touching your code)
yunta init .

# 3. Start iterating with Yunta
yunta "Explain the structure of this project and run existing tests"
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
| **`/init [idea]`** | SDD Scaffolding | Initializes or scaffolds the project generating `SPEC.md`, `PLAN.md`, and `AGENTS.md`. |
| **`/undo`** | Time-Travel Undo | Instantly restores modified or created files to their state prior to the last edit. |
| **`/permissions [clear]`** | Session Permissions | Lists persistent permissions granted via 'always' or revokes them (`/permissions clear`). |
| **`/roi`** | Value Dashboard | Displays cache hit percentage, avoided tokens, and estimated USD savings. |
| **`/metrics`** | Detailed Telemetry | Displays tool execution calls, **startup tax**, error counts, and interaction turns. |
| **`/tokens`** | Token Telemetry | Displays cumulative input, output, and cached tokens. |
| **`Ctrl+C`** | Graceful Interrupt | Cancels the active turn or bash command without exiting the REPL session. |
| **`/clear`** | Reset Context | Clears message history and current saved session state. |
| **`/exit`** | Exit & Learn | Saves session operational learnings to `.yunta/learnings.md` and exits. |


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
