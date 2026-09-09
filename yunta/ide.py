import json
from pathlib import Path

MCP_JSON = {
    "servers": {
        "yunta": {"command": "yunta", "args": ["serve-mcp"]}
    }
}

TASKS_JSON = {
    "version": "2.0.0",
    "tasks": [
        {"label": "yunta: run", "type": "shell", "command": "yunta"},
        {"label": "yunta: check", "type": "shell", "command": "yunta check"},
        {"label": "yunta: init", "type": "shell", "command": "yunta init"},
    ],
}

MCP_PATH = ".vscode/mcp.json"
TASKS_PATH = ".vscode/tasks.json"

def ide_init(target_dir: str | Path = ".") -> list[str]:
    """Genera .vscode/mcp.json y .vscode/tasks.json sin sobrescribir existentes (aviso por archivo)."""
    base = Path(target_dir)
    created = []
    for rel, payload in ((MCP_PATH, MCP_JSON), (TASKS_PATH, TASKS_JSON)):
        path = base / rel
        if path.exists():
            print(f"[yunta ide-init] AVISO: {rel} ya existe; no se sobrescribe.")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        created.append(rel)
    return created
