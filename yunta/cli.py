import os
import sys
from pathlib import Path

from .agent import Agent
from .api import Block, BlockType, Message, Role
from .compact import SlidingWindow, TokenBudgetCompactor
from .feedback import FeedbackStore
from .governance import run_check
from .decompose import _FILE_PATH_RE, looks_multi_file
from .hooks import install_git_hooks, uninstall_git_hooks
from .ide import ide_init
from .init import run_init
from .resilience import QuotaExhausted
from .sandbox import cleanup_sandbox, create_sandbox
from .server_mcp import serve_stdio
from .session import clear_session, load_session
from .json_server import serve_json_stdin
from .mcp import load_mcp_servers
from .provider import LiteLLMProvider
from .tools import bash, delegate, files, memory, search, subtask, symbols, vision  # noqa: F401 — registro vía decoradores

SYSTEM_PROMPT = """Eres un ingeniero de software que programa en pareja a través del harness Yunta.
Trabajas iterando: lees archivos, ejecutas comandos y editas código usando tus tools.
Sé conciso. Si un tool falla, el error vuelve a tu contexto: ajústalo y reintenta.
Responde en el idioma del usuario.

Frontera de rol y entorno de ejecución:
- Yunta es tu banco de herramientas en terminal (read_file, str_replace, bash), NO el runtime de la aplicación.
- Tu objetivo es desarrollar el código del proyecto del usuario en este espacio de trabajo.
- NUNCA crees servicios, daemons ni plugins que corran "dentro de Yunta". El software desarrollado vivirá en su propio entorno de producción (ej. nube, contenedor, Power Automate, web, CLI propio, etc.).

Filosofía Spec-Driven Development (SDD):
- Si el proyecto contiene `SPEC.md` y `PLAN.md`, respeta la fase activa del plan y guía al usuario en la resolución paso a paso (TDD: prueba de borde -> implementación -> verificación).

Eficiencia de pruebas y contexto:
- Durante la iteración activa, ejecuta únicamente la prueba relevante para tu cambio (ej. `pytest tests/test_mi_modulo.py` o `pytest -k mi_funcion`) para mantener la sesión rápida y ágil.
- Ejecuta la suite completa (`pytest`) únicamente como paso de certificación final antes de dar por concluida la tarea.

Reglas de honestidad y verificación:
- NUNCA afirmes haber ejecutado o editado algo sin haberlo hecho con una tool
  real en esta conversación. Narrar acciones imaginarias es un fallo grave.
- Verifica tu trabajo: tras editar código, ejecuta los tests o el comando
  que demuestre el resultado antes de declararlo resuelto."""


def load_system_prompt(feedback: FeedbackStore | None = None, light: bool = False) -> str:
    env_prompt = os.environ.get("YUNTA_SYSTEM_PROMPT")
    user_prompt_file = Path.home() / ".yunta" / "system_prompt.md"
    if env_prompt:
        prompt = env_prompt
    elif user_prompt_file.exists():
        prompt = user_prompt_file.read_text(encoding="utf-8")
    else:
        prompt = SYSTEM_PROMPT

    if light:
        # W4: modo --light — solo prompt base, sin contexto extenso
        return prompt

    agents_md = Path("AGENTS.md")
    if agents_md.exists():
        prompt += "\n\n# Contexto del proyecto (AGENTS.md)\n\n" + agents_md.read_text(
            encoding="utf-8"
        )
    if feedback is not None:
        prompt += feedback.preamble()
    return prompt


def print_version():
    try:
        from importlib.metadata import version
        v = version("yunta-harness")
        print(f"yunta v{v}")
    except Exception:
        print("yunta v2.1.0")


def print_help():
    print("""Uso: yunta [opciones] [comando | "instrucción"]

Harness de agente de código para Spec-Driven Development (SDD), agnóstico al modelo.

Comandos de Terminal (CLI):
  yunta                        Inicia la sesión interactiva REPL
  yunta ide-init              Genera .vscode/mcp.json y tasks.json sin sobrescribir
  yunta serve-mcp, mcp         Inicia el servidor MCP local en stdio (para Claude Desktop, Cursor)
  yunta --resume, -r           Reanuda la sesión previa guardada en .yunta/session_state.json
  yunta check [ruta] [--json]  Auditoría local de gobernanza SDD ($0 en tokens, instantáneo)
  yunta "tu instrucción"       Ejecución directa single-shot (ej. yunta "revisa los tests")
  yunta init [idea]            Inicializa el proyecto con SPEC.md, PLAN.md y AGENTS.md (SDD)
  yunta --version, -v          Muestra la versión instalada de Yunta
  yunta --help, -h, help       Muestra esta pantalla de ayuda

Comandos Interactivos del REPL (dentro de Yunta):
  /help                        Muestra los comandos interactivos disponibles
  /init [idea]                 Inicializa o andamia el proyecto con metodología SDD
  /undo                        Deshace la última edición de archivos y restaura el estado previo
  /permissions [clear]         Muestra o revoca los permisos persistentes otorgados en la sesión
  /roi                         Muestra el dashboard de eficiencia económica y tokens evitados
  /metrics                     Muestra la telemetría detallada de herramientas, startup tax y turnos
  /tokens                      Muestra el consumo de tokens y tasa de acierto de caché
  /clear                       Limpia el historial de la conversación actual
  /exit                        Guarda lecciones aprendidas en .yunta/learnings.md y sale

Variables de Entorno Principales:
  LLM_MODEL                    Proveedor/modelo a utilizar (ej. gemini/gemini-2.5-flash, openai/gpt-4o)
  LLM_MODELS                   Cascada de respaldo separada por comas (ante 429/503/cuota agotada)
  LLM_API_BASE                 URL base para endpoints OpenAI-compatibles (ej. http://localhost:8000/v1)
  LLM_API_KEY                  API Key o token Bearer para el endpoint
  YUNTA_SYSTEM_PROMPT          Sobrescribe el System Prompt base del harness
  YUNTA_MAX_MESSAGES           Ventana máxima de mensajes en el historial (default: 40)
  YUNTA_BLOCKLIST_EXTRA        Ruta a archivo con patrones regex adicionales para bloquear en bash
  YUNTA_ALLOW_FORCE            Permite comandos 'git push --force' si se establece en 1

Documentación: https://github.com/j0sp0nc3/yunta-harness
""")

def main():
    mcp_clients: list = []
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    # Despacho de ayuda y versión (sin requerir LLM_MODEL configurado)
    if len(sys.argv) > 1:
        arg_lower = sys.argv[1].lower()
        if arg_lower in ("--help", "-h", "help"):
            print_help()
            return
        if arg_lower in ("--version", "-v", "version"):
            print_version()
            return

    # Despacho de servidor MCP: `yunta serve-mcp` o `yunta mcp`
    if len(sys.argv) > 1 and sys.argv[1].lower() in ("serve-mcp", "mcp"):
        serve_stdio()
        return

    # Despacho de servidor JSONL: `yunta serve-json` o `yunta json`
    if len(sys.argv) > 1 and sys.argv[1].lower() in ("serve-json", "json"):
        serve_json_stdin()
        return

    # Despacho de comando `yunta check [ruta] [--json] [--tests]`
    if len(sys.argv) > 1 and sys.argv[1].lower() == "check":
        as_json = "--json" in sys.argv
        run_tests = "--tests" in sys.argv or "--run-tests" in sys.argv
        target_dir = "."
        for arg in sys.argv[2:]:
            if not arg.startswith("-"):
                target_dir = arg
                break
        code = run_check(target_dir=target_dir, as_json=as_json, run_tests=run_tests)
        sys.exit(code)

    # Despacho de comando `yunta ide-init`
    if len(sys.argv) > 1 and sys.argv[1].lower() == "ide-init":
        ide_init()
        return

    # Despacho de comando `yunta init [idea]`
    if len(sys.argv) > 1 and sys.argv[1].lower() == "init":
        idea = " ".join(sys.argv[2:]).strip()
        run_init(idea)
        return

    # Despacho de comando `yunta hooks` / `yunta install-hooks` / `yunta uninstall-hooks`
    if len(sys.argv) > 1 and sys.argv[1].lower() in ("hooks", "install-hooks", "uninstall-hooks"):
        if sys.argv[1].lower() == "uninstall-hooks":
            uninstall_git_hooks()
        else:
            install_git_hooks()
        return

    # Detección de flags --resume / -r, --yes / -y y --light (W4)
    resume = False
    chunks = os.environ.get("YUNTA_CHUNKS", "").lower() in ("1", "true", "yes")
    light = os.environ.get("YUNTA_LIGHT", "").lower() in ("1", "true", "yes")
    auto_confirm = os.environ.get("YUNTA_YES", "").lower() in ("1", "true", "yes")
    args_cleaned = []
    for arg in sys.argv[1:]:
        if arg in ("--resume", "-r"):
            resume = True
        elif arg in ("--yes", "-y"):
            auto_confirm = True
        elif arg == "--chunks":
            chunks = True
        elif arg == "--light":
            light = True
        else:
            args_cleaned.append(arg)

    feedback = FeedbackStore()
    system = load_system_prompt(feedback, light=light)
    provider = LiteLLMProvider(system=system)
    delegate.set_provider(provider)
    subtask.set_provider(provider)

    max_messages = int(os.environ.get("YUNTA_MAX_MESSAGES", "40"))
    compactor = SlidingWindow(max_messages=max_messages)

    initial_messages = None
    initial_usage = None
    if resume:
        session_data = load_session()
        if session_data:
            initial_messages = session_data["messages"]
            initial_usage = session_data["usage"]
            print(f"yunta — sesión reanudada ({len(initial_messages)} mensajes previos, {initial_usage.turns} turnos)")
        else:
            print("yunta — aviso: no se encontró sesión previa guardada para reanudar")

    # Despacho single-shot: `yunta "mi tarea directa"`
    # (P9: --chunks por lotes; M-B: auto-trigger por heurística de archivos)
    if args_cleaned:
        prompt = " ".join(args_cleaned).strip()
        # M-B: si la tarea menciona 3+ archivos distintos y no se pidió
        # --chunks explícitamente, degradar a modo por lotes (P9).
        if not chunks and looks_multi_file(prompt):
            print(
                f"[M-B] la tarea menciona {len(set(_FILE_PATH_RE.findall(prompt)))} archivos; "
                "activando modo por lotes (--chunks)"
            )
            chunks = True
        if chunks:
            from .decompose import decompose_task, run_chunks
            confirm_cb = (lambda n, d: True) if auto_confirm else None
            subtasks = decompose_task(provider, prompt)
            print(f"[P9] spec descompuesta en {len(subtasks)} lotes:")
            for i, t in enumerate(subtasks, 1):
                print(f"  {i}. {t.goal} — archivos: {', '.join(t.files)}")
            summaries = run_chunks(provider, subtasks, system, confirm=confirm_cb)
            print("\n[P9] " + str(len(summaries)) + " lotes completados.")
            # M-A: auto-feedback también en el comentario del despacho --chunks.
            try:
                transcript = [
                    Message(role=Role.USER, content=[Block(type=BlockType.TEXT, text=prompt)])
                ] + [
                    Message(role=Role.ASSISTANT, content=[Block(type=BlockType.TEXT, text=str(s))])
                    for s in summaries
                ]
                feedback.summarize(provider, transcript)
            except Exception:
                pass
            for c in mcp_clients:
                c.close()
            return

        confirm_cb = (lambda n, desc: True) if auto_confirm else None
        agent = Agent(
            provider=provider,
            system=system,
            compactor=compactor,
            initial_messages=initial_messages,
            initial_usage=initial_usage,
            confirm=confirm_cb,
        )
        try:
            agent.send(prompt)
        except KeyboardInterrupt:
            print()
        except QuotaExhausted as e:
            print(f"\n⚠️ {e}\n(puedes reanudar en cualquier momento con `yunta --resume` cuando se restablezca la cuota del proveedor)\n")
        # M-A: auto-feedback también en single-shot (best-effort)
        if agent.messages:
            try:
                feedback.summarize(provider, agent.messages)
            except Exception:
                pass
        return


    mcp_clients = load_mcp_servers()
    active_sandbox: dict | None = None
    agent = Agent(
        provider=provider,
        system=system,
        compactor=compactor,
        initial_messages=initial_messages,
        initial_usage=initial_usage,
    )

    print(f"yunta — modelo: {provider.model()}")
    print("Escribe tu consulta, /help para ver comandos, o /exit para salir.\n")

    try:
        while True:
            try:
                prompt = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not prompt:
                continue
            if prompt == "/exit":
                if active_sandbox:
                    cleanup_sandbox(active_sandbox["dir"], active_sandbox["branch"], merge=False)
                if agent.messages:
                    feedback.summarize(provider, agent.messages)
                break
            if prompt == "/help":
                print("Comandos disponibles:")
                print("  /init [idea]         - Inicializa el proyecto con SPEC.md, PLAN.md y AGENTS.md (SDD)")
                print("  /sandbox [merge|discard] - Crea o gestiona un entorno aislado en git worktree (V3-9)")
                print("  /undo                - Deshace la última edición de archivos y restaura su estado anterior")
                print("  /permissions [clear] - Muestra o revoca los permisos persistentes otorgados en la sesión")
                print("  /context             - Muestra el estado del historial y porcentaje del presupuesto de tokens")
                print("  /roi                 - Muestra el dashboard de valor y ahorro económico de API")
                print("  /tokens              - Muestra el consumo de tokens y tasa de acierto de caché")
                print("  /metrics             - Muestra la telemetría detallada de uso, startup tax y herramientas")
                print("  /clear               - Limpia el historial de la conversación actual")
                print("  /exit                - Guarda lecciones de sesión y sale de Yunta\n")
                continue

            if prompt.startswith("/sandbox"):
                sub = prompt[8:].strip()
                if not sub:
                    if active_sandbox:
                        print(f"Sandbox activo: {active_sandbox['dir']} (rama: {active_sandbox['branch']})")
                        print("Usa /sandbox merge para integrar cambios o /sandbox discard para eliminar sin guardar.\n")
                    else:
                        try:
                            sb_dir, sb_branch = create_sandbox()
                            active_sandbox = {"dir": sb_dir, "branch": sb_branch}
                            print(f"🧪 Sandbox creado exitosamente en {sb_dir} (rama: {sb_branch})")
                            print("Las operaciones destructivas pueden aislarse en este directorio.\n")
                        except Exception as err:
                            print(f"Error al crear sandbox: {err}\n")
                elif sub in ("merge", "integrate"):
                    if not active_sandbox:
                        print("No hay ningún sandbox activo para integrar.\n")
                    else:
                        msg = cleanup_sandbox(active_sandbox["dir"], active_sandbox["branch"], merge=True)
                        print(f"✨ {msg}\n")
                        active_sandbox = None
                elif sub in ("discard", "clean", "cleanup"):
                    if not active_sandbox:
                        print("No hay ningún sandbox activo para descartar.\n")
                    else:
                        msg = cleanup_sandbox(active_sandbox["dir"], active_sandbox["branch"], merge=False)
                        print(f"🗑️ {msg}\n")
                        active_sandbox = None
                else:
                    print("Subcomando sandbox desconocido. Usa /sandbox, /sandbox merge o /sandbox discard.\n")
                continue

            if prompt == "/context":
                max_tok = int(os.environ.get("YUNTA_MAX_TOKENS", "128000"))
                tb_compactor = TokenBudgetCompactor(max_tokens=max_tok)
                est_tok = tb_compactor.estimate_tokens(agent.messages)
                ratio = tb_compactor.usage_ratio(agent.messages)
                print("┌────────────────────────────────────────────────────────┐")
                print("│ YUNTA — ESTADO Y PRESUPUESTO DE CONTEXTO               │")
                print("├────────────────────────────────────────────────────────┤")
                print(f"│ 📜 Mensajes en Historial:               {len(agent.messages):>6}               │")
                print(f"│ 🧮 Tokens Estimados en Contexto:       {est_tok:>10,} tokens  │")
                print(f"│ 🎯 Presupuesto Máximo de Tokens:       {max_tok:>10,} tokens  │")
                print(f"│ 📊 Uso del Presupuesto (Token Budget): {ratio:>6.1%}              │")
                print("└────────────────────────────────────────────────────────┘\n")
                continue

            if prompt == "/clear":
                agent.messages.clear()
                clear_session()
                print("(historial y sesión guardada limpios)\n")
                continue
            if prompt == "/undo":
                restored = agent.undo()
                if restored:
                    for r in restored:
                        print(f"✨ Archivo {r}")
                else:
                    print("(no hay cambios previos para deshacer)")
                print()
                continue
            if prompt == "/permissions" or prompt.startswith("/permissions "):
                args = prompt.split(maxsplit=1)
                if len(args) > 1 and args[1].strip() == "clear":
                    agent.session_permissions.revoke_all()
                    print("(permisos de sesión revocados)")
                else:
                    items = agent.session_permissions.items()
                    if not items:
                        print("no hay permisos persistentes en esta sesión")
                    else:
                        for tool, token in items:
                            print(f"  {tool}: {token}*")
                        print("(usa /permissions clear para revocar)")
                print()
                continue
            if prompt == "/roi":
                u = agent.total_usage
                tokens_in = u.input_tokens
                tokens_cached = u.cached_tokens
                raw_tokens = u.theoretical_raw_tokens
                tokens_saved = max(0, raw_tokens - (tokens_in + tokens_cached))
                savings = (tokens_cached * 0.00000095) + (tokens_saved * 0.00000125)
                print("┌────────────────────────────────────────────────────────┐")
                print("│ YUNTA — DASHBOARD DE TELEMETRÍA Y RETORNO (ROI)        │")
                print("├────────────────────────────────────────────────────────┤")
                print(f"│ ⚡ Acierto de Caché (Hit Rate):        {u.cache_rate:>6.1f}%          │")
                print(f"│ 🛡️ Tokens Cacheados (Ahorro de API):   {tokens_cached:>10,} tokens  │")
                print(f"│ 📦 Tokens Evitados vs Chat Crudo:      {tokens_saved:>10,} tokens  │")
                print(f"│ 💰 Ahorro Estimado de Costo API:     ~${savings:>9.4f} USD     │")
                print(f"│ 🔧 Herramientas Ejecutadas:            {u.total_tool_calls:>6} ({u.tool_errors} err)     │")
                print(f"│ 💬 Turnos de Interacción:              {u.turns:>6}               │")
                print("└────────────────────────────────────────────────────────┘\n")
                continue
            if prompt.startswith("/init"):
                idea = prompt[5:].strip()
                run_init(idea)
                continue
            if prompt in ("/tokens", "/metrics"):
                u = agent.total_usage
                st = provider.startup_tax
                print(u.format_summary(startup_tax=st) + "\n")
                continue

            if prompt.startswith("/") and not prompt.startswith("//"):
                print(f"Comando desconocido: '{prompt}'. Escribe /help para ver los comandos disponibles.\n")
                continue

            try:
                agent.send(prompt)
            except KeyboardInterrupt:
                print()
            except QuotaExhausted as e:
                print(f"\n⚠️ {e}\n(puedes reanudar en cualquier momento con `yunta --resume` cuando se restablezca la cuota del proveedor)\n")
            except SystemExit:
                raise
            except Exception as e:
                print(f"error: {e}", file=sys.stderr)
            print()
    finally:
        for c in mcp_clients:
            c.close()


if __name__ == "__main__":
    main()
