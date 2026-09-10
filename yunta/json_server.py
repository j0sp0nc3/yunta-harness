"""Modo servidor JSON-Lines (JSONL) para integración ligera de CLI (V3-11).

Canaliza eventos de ejecución del agente en tiempo real por stdout en formato JSONL,
permitiendo integraciones con IDEs, extensiones y scripts externos sin montar MCP.
"""

import json
import sys
from typing import Callable

from .agent import Agent
from .api import BlockType, Role, Usage
from .provider import LiteLLMProvider
from .tools import bash, files, registry, subtask, delegate  # noqa: F401


def serve_json_stream(prompt: str, provider=None, confirm_callback: Callable = None) -> None:
    """Ejecuta una instrucción y emite cada evento en formato JSON-Lines (JSONL) a stdout."""
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if provider is None:
        try:
            provider = LiteLLMProvider()
        except Exception as e:
            err_evt = {"type": "error", "message": f"Error de inicialización del proveedor: {e}"}
            sys.stdout.write(json.dumps(err_evt, ensure_ascii=False) + "\n")
            sys.stdout.flush()
            return

    def emit(data: dict) -> None:
        sys.stdout.write(json.dumps(data, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    model_name = getattr(provider, "model", lambda: "unknown")()
    emit({"type": "system", "event": "start", "model": model_name})

    def on_text(delta: str) -> None:
        emit({"type": "text_delta", "text": delta})

    agent = Agent(
        provider=provider,
        system="Eres el harness Yunta en modo servidor JSONL.",
        confirm=confirm_callback if confirm_callback else (lambda name, detail: True),
        on_text=on_text,
    )

    try:
        res = agent.send(prompt)
        emit({"type": "done", "status": "success", "final_text": res})
        u: Usage = agent.total_usage
        emit({
            "type": "usage",
            "input_tokens": u.input_tokens,
            "output_tokens": u.output_tokens,
            "cached_tokens": u.cached_tokens,
            "turns": u.turns,
            "tool_errors": u.tool_errors,
        })
    except Exception as e:
        emit({"type": "error", "message": str(e)})


def serve_json_stdin(provider=None) -> None:
    """Escucha prompts en formato JSONL desde stdin y responde con streaming de eventos."""
    if sys.platform == "win32":
        try:
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    sys.stderr.write("[yunta-json] Servidor JSONL de Yunta iniciado en stdio\n")
    sys.stderr.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            prompt = req.get("prompt", "")
            if not prompt:
                continue
            serve_json_stream(prompt, provider=provider)
        except json.JSONDecodeError as e:
            err_evt = {"type": "error", "message": f"JSON inválido en stdin: {e}"}
            sys.stdout.write(json.dumps(err_evt, ensure_ascii=False) + "\n")
            sys.stdout.flush()
