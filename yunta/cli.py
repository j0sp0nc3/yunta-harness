import os
import subprocess
import sys
import time
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
from .session import clear_session, load_session, save_session
from .json_server import serve_json_stdin
from .mcp import load_mcp_servers
from .provider import LiteLLMProvider
from .tools import bash, delegate, files, memory, search, subtask, symbols, vision  # noqa: F401 — registro vía decoradores

SYSTEM_PROMPT = """Eres un asistente autónomo e inteligente y compañero de trabajo a través del harness Yunta.
Trabajas iterando: analizas información, lees y editas archivos, ejecutas herramientas y redactas soluciones.
Sé extremadamente conciso y directo. Evita narrar o explicar razonamientos internos antes de invocar tools (ej. NO escribas "Voy a crear...", "Reviso...", "El usuario quiere..."). Invoca las tools directamente.
Responde e interactúa siempre en el idioma que esté utilizando el usuario (español, inglés, etc.). Tanto tus pensamientos como tus respuestas y archivos redactados deben escribirse en ese mismo idioma.

Áreas de actuación y capacidades:
- Investigación y Análisis: Síntesis de información, extracción de textos (audio/documentos/OCR), redacción de informes y documentación técnica, académica o de negocios.
- Ingeniería de Software: Desarrollo, refactorización, depuración y arquitectura de software utilizando tus herramientas en este espacio de trabajo.

Frontera de rol y entorno de ejecución:
- Yunta es tu banco de herramientas en terminal (read_file, str_replace, bash, web_search, etc.), NO el runtime de la aplicación ni el entorno de producción.
- NUNCA crees servicios, daemons ni plugins que corran "dentro de Yunta". El software u operacionalidad desarrollada vivirá en su propio entorno final (ej. producción, nube, contenedores, documentos del usuario, etc.).

Metodología de trabajo guiado por especificaciones (SDD/Plan-Driven):
- Si el proyecto contiene `SPEC.md` o `PLAN.md`, respeta la fase activa del plan y guía al usuario en la resolución paso a paso (en código: TDD / pruebas de borde; en investigación: verificación empírica y recopilación sintética).

Eficiencia de pruebas y contexto:
- Durante iteraciones activas de código, ejecuta únicamente la prueba relevante para tu cambio (`pytest -k mi_funcion`). Ejecuta la suite completa (`pytest`) solo como paso de certificación final.
- Durante tareas de investigación o análisis de datos, prioriza lecturas focalizadas y búsquedas directas sin ejecutar comandos redundantes.

Reglas de honestidad y verificación:
- NUNCA afirmes haber ejecutado, editado o verificado algo sin haberlo realizado con una tool real en esta conversación. Narrar acciones imaginarias es un fallo grave.
- Verifica tu trabajo: tras editar código, generar informes o procesar datos, ejecuta las pruebas, comandos o comprobaciones empíricas que demuestren la corrección del resultado antes de declararlo resuelto."""


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
        print("yunta v2.2.0")


def run_update():
    """Actualiza Yunta a la versión más reciente desde PyPI o repositorio git."""
    print("🔄 Actualizando yunta-harness...")
    git_dir = Path(".git")
    if git_dir.exists():
        try:
            res = subprocess.run(["git", "pull", "--rebase"], capture_output=True, text=True)
            if res.returncode == 0:
                print("✨ Repositorio git actualizado (git pull --rebase).")
                subprocess.run([sys.executable, "-m", "pip", "install", "-e", "."], capture_output=True)
                print_version()
                return
        except Exception:
            pass

    try:
        cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "yunta-harness"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            print("✨ Paquete yunta-harness actualizado exitosamente.")
            print_version()
        else:
            err = (res.stderr or res.stdout).strip()
            print(f"⚠️ Error al actualizar mediante pip: {err}")
    except Exception as e:
        print(f"⚠️ Error al ejecutar la actualización: {e}")


def print_help():
    print("""Uso: yunta [opciones] [comando | "instrucción"]

Harness de agente de código para Spec-Driven Development (SDD), agnóstico al modelo.

Comandos de Terminal (CLI):
  yunta                        Inicia la sesión interactiva REPL
  yunta voice, --voice [audio] Activa el micrófono o transcribe un archivo de audio (manos libres)
  yunta update, --update       Actualiza Yunta a la versión más reciente (vía pip o git)
  yunta ide-init              Genera .vscode/mcp.json y tasks.json sin sobrescribir
  yunta serve-mcp, mcp         Inicia el servidor MCP local en stdio (para Claude Desktop, Cursor)
  yunta serve-json, json       Inicia el servidor NDJSON en stdio para extensiones IDE
  yunta --resume, -r           Reanuda la sesión previa guardada en .yunta/session_state.json
  yunta check [ruta] [--json]  Auditoría local de gobernanza SDD ($0 en tokens, instantáneo)
  yunta reverse-sdd [ruta] [--apply]  Genera SPEC.md/AGENTS.md candidatos desde código sin specs
  yunta handoff export [ruta]  Empaqueta la sesión guardada en un bundle portable (handoff)
  yunta handoff import <ruta>  Reanuda una sesión desde un bundle de handoff exportado
  yunta "tu instrucción"       Ejecución directa single-shot (ej. yunta "revisa los tests")
  yunta init [idea]            Inicializa el proyecto con SPEC.md, PLAN.md y AGENTS.md (SDD)
  yunta --version, -v          Muestra la versión instalada de Yunta
  yunta --help, -h, help       Muestra esta pantalla de ayuda

Comandos Interactivos del REPL (dentro de Yunta):
  /help                        Muestra los comandos interactivos disponibles
  /voice, /listen [audio.mp3]  Graba micrófono o transcribe audio en la sesión activa
  /init [idea]                 Inicializa o andamia el proyecto con metodología SDD
  /sandbox [merge|discard]     Crea o gestiona un entorno aislado en git worktree
  /undo                        Deshace la última edición de archivos y restaura el estado previo
  /permissions [clear]         Muestra o revoca los permisos persistentes otorgados en la sesión
  /handoff export|import       Exporta/importa la sesión activa como bundle portable entre harnesses
  /context                     Muestra el estado del historial y porcentaje del presupuesto de tokens
  /roi                         Muestra el dashboard de eficiencia económica y tokens evitados
  /metrics                     Muestra la telemetría detallada de herramientas, startup tax y turnos
  /tokens                      Muestra el consumo de tokens y tasa de acierto de caché
  /clear                       Limpia el historial de la conversación actual
  /exit                        Guarda lecciones aprendidas en .yunta/learnings.md y sale

Variables de Entorno Principales:
  LLM_MODEL                    Proveedor/modelo a utilizar (ej. gemini/gemini-2.5-flash, openai/gpt-4o)
  LLM_MODELS                   Cascada de respaldo separada por comas (ante 429/503/cuota agotada)
  LLM_FALLBACK_MODEL           Proveedor secundario con endpoint propio (ej. openai/glm-5.3)
  LLM_FALLBACK_API_BASE        URL base del proveedor secundario
  LLM_FALLBACK_API_KEY         Credencial del proveedor secundario
  LLM_API_BASE                 URL base para endpoints OpenAI-compatibles (ej. http://localhost:8000/v1)
  LLM_API_KEY                  API Key o token Bearer para el endpoint
  VOICE_MODEL                  Modelo STT de voz Whisper (default: whisper-1)
  VOICE_API_BASE               URL base para servidor STT Whisper (cloud o Docker local)
  YUNTA_VERBOSE                Establecer en 1 para activar salida detallada de razonamiento
  YUNTA_MAX_MESSAGES           Ventana máxima de mensajes en el historial (default: 40)
  YUNTA_BLOCKLIST_EXTRA        Ruta a archivo con patrones regex adicionales para bloquear en bash
  YUNTA_ALLOW_FORCE            Permite comandos 'git push --force' si se establece en 1

Documentación: https://github.com/j0sp0nc3/yunta-harness
""")


def run_roi():
    session_data = load_session()
    u = session_data.get("usage") if session_data else None
    if not u:
        from .api import Usage
        u = Usage()
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


def print_roi_footer(usage, turn_usage=None):
    tokens_in = usage.input_tokens
    tokens_cached = usage.cached_tokens
    raw_tokens = usage.theoretical_raw_tokens
    tokens_saved = max(0, raw_tokens - (tokens_in + tokens_cached))
    savings = (tokens_cached * 0.00000095) + (tokens_saved * 0.00000125)

    parts = []
    if turn_usage:
        t_tools = f", {turn_usage.total_tool_calls} tools" if turn_usage.total_tool_calls else ""
        parts.append(f"Turno: +{turn_usage.input_tokens:,} in, +{turn_usage.output_tokens:,} out{t_tools}")

    parts.append(f"Sesión: {tokens_in + tokens_cached:,} tokens")
    if tokens_cached > 0 or usage.cache_rate > 0:
        parts.append(f"⚡ {usage.cache_rate:.1f}% caché")
    parts.append(f"💰 Ahorro API: ~${savings:.4f} USD")

    print("\n📊 [ROI & Telemetría] " + " │ ".join(parts))


def run_tokens():
    session_data = load_session()
    u = session_data.get("usage") if session_data else None
    if not u:
        from .api import Usage
        u = Usage()
    print(u.format_summary() + "\n")


def run_context():
    session_data = load_session()
    messages = session_data.get("messages", []) if session_data else []
    max_tok = int(os.environ.get("YUNTA_MAX_TOKENS", "128000"))
    tb_compactor = TokenBudgetCompactor(max_tokens=max_tok)
    est_tok = tb_compactor.estimate_tokens(messages)
    ratio = tb_compactor.usage_ratio(messages)
    print("┌────────────────────────────────────────────────────────┐")
    print("│ YUNTA — ESTADO Y PRESUPUESTO DE CONTEXTO               │")
    print("├────────────────────────────────────────────────────────┤")
    print(f"│ 📜 Mensajes en Historial:               {len(messages):>6}               │")
    print(f"│ 🧮 Tokens Estimados en Contexto:       {est_tok:>10,} tokens  │")
    print(f"│ 🎯 Presupuesto Máximo de Tokens:       {max_tok:>10,} tokens  │")
    print(f"│ 📊 Uso del Presupuesto (Token Budget): {ratio:>6.1%}              │")
    print("└────────────────────────────────────────────────────────┘\n")


def run_handoff_export(path_arg: str | None = None) -> None:
    """CLI single-shot: solo tiene acceso a la última sesión guardada en
    disco (sin permisos/sandbox vivos de un proceso en curso)."""
    from .api import Usage
    from .handoff import export_handoff

    session_data = load_session()
    if not session_data:
        print("No hay sesión guardada (.yunta/session_state.json) para exportar.")
        return
    out_path = export_handoff(
        session_data.get("messages", []),
        session_data.get("usage") or Usage(),
        model=session_data.get("model", ""),
        path=path_arg,
    )
    print(f"✅ Handoff exportado: {out_path}")


def run_handoff_import(path_arg: str | None) -> None:
    from .handoff import import_handoff

    if not path_arg:
        print("Uso: yunta handoff import <ruta-al-bundle.json>")
        return
    try:
        result = import_handoff(path_arg)
    except ValueError as err:
        print(f"⚠️ {err}")
        return
    if result is None:
        print(f"No se pudo leer el bundle de handoff: {path_arg}")
        return
    save_session(result["messages"], result["usage"], model=result.get("model", ""))
    print(f"✅ Handoff importado desde {path_arg} (session_id={result['session_id']}).")
    print(f"   Modelo original: {result.get('model') or '(no especificado)'}")
    if result.get("drift_warning"):
        print(f"   ⚠️ {result['drift_warning']}")
    print("   Ejecuta `yunta --resume` para continuar la sesión.")


def _open_voice_listener():
    """Abre y calibra el micrófono en escucha continua; None si no hay soporte."""
    from .voice import VoiceListener

    try:
        listener = VoiceListener()
        listener.start()
        return listener
    except NotImplementedError as err:
        print(f"⚠️ {err}\n   Continuando con entrada por teclado.\n")
        return None


def _start_voice_approval(agent):
    """Activa la escucha continua y la aprobación de tools por voz sobre un Agent.

    Retorna el VoiceListener activo, o None si no hay hardware/dependencias
    (en cuyo caso se continúa con teclado y nada se rompe). Compartido por el
    REPL interactivo y el modo single-shot nacido de voz (yunta voice archivo.mp3)."""
    from .voice import load_voice_keywords, make_voice_approval

    listener = _open_voice_listener()
    if listener is None:
        return None
    agent.voice_keywords = load_voice_keywords()
    agent.voice_approval = make_voice_approval(agent, listener)
    return listener


def _load_dotenv():
    """Carga automáticamente variables de entorno desde un archivo .env si existe."""
    if os.environ.get("YUNTA_NO_DOTENV"):
        return
    project_root = Path(__file__).resolve().parent.parent
    possible_paths = [
        project_root / ".env",
        Path.cwd() / ".env",
        Path.home() / ".yunta" / ".env",
    ]
    for env_path in possible_paths:
        if env_path.exists() and env_path.is_file():
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key:
                        os.environ[key] = val
            except Exception:
                pass



def main():
    _load_dotenv()
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
        if arg_lower in ("update", "--update"):
            run_update()
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

    # Despacho de comando `yunta reverse-sdd [ruta] [--apply]`
    if len(sys.argv) > 1 and sys.argv[1].lower() == "reverse-sdd":
        from .reverse_sdd import run_reverse_sdd
        apply_flag = "--apply" in sys.argv
        target_dir = "."
        for arg in sys.argv[2:]:
            if not arg.startswith("-"):
                target_dir = arg
                break
        result = run_reverse_sdd(target_dir=target_dir, apply=apply_flag)
        if result["files_scanned"] == 0:
            print("No se encontraron archivos de código soportados para analizar.")
        else:
            print(f"📄 Reverse-SDD: {result['files_scanned']} archivo(s) analizado(s).")
            for w in result["written"]:
                print(f"  → {w}")
            if not apply_flag:
                print("Usa --apply para escribir SPEC.md/AGENTS.md reales (solo si no existen ya).")
        return

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

    # Despacho de comando `yunta roi` / `yunta --roi`
    if len(sys.argv) > 1 and sys.argv[1].lower() in ("roi", "--roi"):
        run_roi()
        return

    # Despacho de comando `yunta tokens` / `yunta --tokens` / `yunta metrics` / `yunta --metrics`
    if len(sys.argv) > 1 and sys.argv[1].lower() in ("tokens", "--tokens", "metrics", "--metrics"):
        run_tokens()
        return

    # Despacho de comando `yunta context` / `yunta --context`
    if len(sys.argv) > 1 and sys.argv[1].lower() in ("context", "--context"):
        run_context()
        return

    # Despacho de comando `yunta handoff export|import [ruta]`
    if len(sys.argv) > 1 and sys.argv[1].lower() == "handoff":
        sub = sys.argv[2].lower() if len(sys.argv) > 2 else ""
        arg_path = sys.argv[3] if len(sys.argv) > 3 else None
        if sub == "export":
            run_handoff_export(arg_path)
        elif sub == "import":
            run_handoff_import(arg_path)
        else:
            print("Uso: yunta handoff export [ruta] | yunta handoff import <ruta>")
        return

    # Despacho de comando `yunta voice` / `yunta --voice` / `yunta -v`
    resume = False
    auto_confirm = False
    chunks = False
    light = False
    think_flag = None
    voice_input_file = None
    is_voice_mode = False
    speak_mode = False
    args_cleaned = []
    for arg in sys.argv[1:]:
        if arg in ("--resume", "-r"):
            resume = True
        elif arg in ("--speak", "-s"):
            speak_mode = True
        elif arg in ("--yes", "-y"):
            auto_confirm = True
        elif arg == "--chunks":
            chunks = True
        elif arg == "--light":
            light = True
        elif arg.startswith("--think=") or arg.startswith("--reason="):
            think_flag = arg.split("=")[1].strip()
        elif arg in ("--think", "--deep", "-t"):
            think_flag = "high"
        elif arg in ("--voice", "voice"):
            is_voice_mode = True
        elif is_voice_mode and voice_input_file is None and not arg.startswith("-"):
            voice_input_file = arg
        else:
            args_cleaned.append(arg)

    if is_voice_mode:
        from .voice import AudioTranscriber, normalize_voice_response, offload_transcript
        transcriber = AudioTranscriber()
        if voice_input_file:
            # Transcripción de archivo + single-shot (comportamiento clásico)
            try:
                print(f"🎙️ Transcribiendo audio: {voice_input_file} (Ctrl+C para detener)...")
                prompt = transcriber.transcribe(voice_input_file)
            except KeyboardInterrupt:
                print("\n⏹️ Transcripción cancelada por el usuario.")
                return
        else:
            # V5-1: sin archivo, la escucha continua del REPL toma el control
            prompt = None
        if prompt is not None and not prompt.strip() and voice_input_file:
            print("⚠️ No se pudo obtener transcripción de audio.")
            return
        if prompt and prompt.strip():
            print(f"\n🗣️ Transcripción capturada ({len(prompt)} caracteres):\n   \"{prompt[:300]}{'...' if len(prompt) > 300 else ''}\"\n")
            prompt = offload_transcript(prompt)
            if not auto_confirm:
                print("Opciones: [ENTER/s] Enviar al agente | [e] Editar texto | [c] Cancelar")
                try:
                    raw_act = input("> ").strip()
                except (EOFError, KeyboardInterrupt):
                    raw_act = "c"
                action = normalize_voice_response(raw_act) if raw_act else "s"
                if action in ("c", "cancelar"):
                    print("🚫 Operación cancelada por el usuario.")
                    return
                elif action in ("e", "editar"):
                    try:
                        edited = input("✏️ Edita el texto: ").strip()
                        if edited:
                            prompt = edited
                        else:
                            print("🚫 Texto vacío. Operación cancelada.")
                            return
                    except (EOFError, KeyboardInterrupt):
                        print("🚫 Operación cancelada.")
                        return
            args_cleaned.append(prompt)

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
            # SDD por voz: aprobación hablada en cada lote si la tarea nació de voz
            chunks_listener = _open_voice_listener() if (is_voice_mode and not auto_confirm) else None
            if chunks_listener is not None:
                summaries = run_chunks(provider, subtasks, system, confirm=confirm_cb, voice_listener=chunks_listener)
                chunks_listener.stop()
            else:
                summaries = run_chunks(provider, subtasks, system, confirm=confirm_cb)
            print("\n[P9] " + str(len(summaries)) + " lotes completados.")
            if speak_mode:
                try:
                    from .tts import TTSProvider, speak, wait_until_done
                    speak(TTSProvider(), f"{len(summaries)} lotes completados.")
                    wait_until_done()
                except Exception:
                    pass
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

        from .intent import IntentClassifier, TaskIntent
        intent = IntentClassifier.classify(prompt)
        if intent == TaskIntent.RESEARCH_AND_CONSULTING:
            print("🔬 [Modo Investigación & Consultoría Activo] Analizando información con contexto persistente...\n")

        confirm_cb = (lambda n, desc: True) if auto_confirm else None
        agent = Agent(
            provider=provider,
            system=system,
            compactor=compactor,
            initial_messages=initial_messages,
            initial_usage=initial_usage,
            confirm=confirm_cb,
        )
        ss_listener = _start_voice_approval(agent) if (is_voice_mode and not auto_confirm) else None
        try:
            try:
                prev_u = agent.total_usage
                res_text = agent.send(prompt)
                curr_u = agent.total_usage
                print_roi_footer(curr_u, curr_u.delta(prev_u))
            except KeyboardInterrupt:
                print()
                res_text = None
            except QuotaExhausted as e:
                print(f"\n⚠️ {e}\n(puedes reanudar en cualquier momento con `yunta --resume` cuando se restablezca la cuota del proveedor)\n")
                res_text = None

            # Persistencia de memoria conversacional de sesión
            if agent.messages:
                try:
                    save_session(agent.messages, agent.total_usage, model=provider.model())
                except Exception:
                    pass
                try:
                    feedback.summarize(provider, agent.messages)
                except Exception:
                    pass
            # --speak también en single-shot: leer el resultado final en voz alta
            if speak_mode and res_text:
                try:
                    from .tts import TTSProvider, speak, wait_until_done
                    speak(TTSProvider(), res_text)
                    wait_until_done()
                except Exception:
                    pass
        finally:
            if ss_listener is not None:
                ss_listener.stop()
        return


    mcp_clients = load_mcp_servers()
    active_sandbox: dict | None = None
    agent = Agent(
        provider=provider,
        system=system,
        compactor=compactor,
        initial_messages=initial_messages,
        initial_usage=initial_usage,
        confirm=(lambda n, desc: True) if auto_confirm else None,
    )
    if think_flag:
        agent.think_override = think_flag

    # V5-1: escucha continua si se pidió `yunta --voice` (sin archivo) en el REPL
    voice_listener = None
    if is_voice_mode and not voice_input_file and not auto_confirm:
        voice_listener = _start_voice_approval(agent)

    print(f"yunta — modelo: {provider.model()}")
    if agent.think_override:
        print(f"🧠 Modo Razonamiento Profundo: FORZADO EN {agent.think_override.upper()}")
    if voice_listener is not None:
        print("🎙️ MODO VOZ CONTINUA — ciclo de cada turno:")
        print("   🟢 en espera  →  🔴 escuchando (al detectar tu voz)")
        print("   →  🟠 transcribiendo (tras 1.5s de silencio)  →  🤖 el agente responde")
        print("   (micrófono en silencio mientras el agente trabaja o el TTS habla)")
        print(f"   Umbral VAD: {voice_listener.threshold} — habla fuerte y claro; di \"salir\" para terminar")
        print("   (Ctrl+C también sale. Si no detecta tu voz: YUNTA_VAD_DEBUG=1 para diagnosticar)\n")
    else:
        print("Escribe tu consulta, /help para ver comandos, o /exit para salir.\n")

    last_interrupt_time = 0.0
    try:
        while True:
            if voice_listener is not None:
                try:
                    prompt = (voice_listener.get(timeout=0.5) or "").strip()
                except (KeyboardInterrupt, EOFError):
                    print("\n⏹️ Saliendo del modo voz (Ctrl+C).")
                    break
                if not prompt:
                    continue
                # Router local: palabras clave → comando REPL sin consultar al LLM (0 tokens)
                routed = route_keyword(prompt, getattr(agent, "voice_keywords", None))
                if routed:
                    print(f'🗣️ "{prompt}" → ⚡ {routed} (palabra clave local, 0 consultas LLM)\n')
                    prompt = routed
                else:
                    print(f'🗣️ "{prompt}"\n')
            else:
                try:
                    prompt = input("> ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n⏹️ Salida por usuario.")
                    break

            # Un input nuevo corta la locución TTS en curso (no encimar audio)
            try:
                from .tts import stop_speaking
                stop_speaking()
            except Exception:
                pass

            if not prompt:
                continue
            if prompt in ("/stop", "stop"):
                print("⏹️ Detenido.\n")
                continue
            if prompt == "/exit":
                if active_sandbox:
                    cleanup_sandbox(active_sandbox["dir"], active_sandbox["branch"], merge=False)
                try:
                    if agent.messages:
                        feedback.summarize(provider, agent.messages)
                except (KeyboardInterrupt, SystemExit):
                    break
                except Exception:
                    pass
                break
            if prompt == "/help":
                print("Comandos disponibles:")
                print("  /init [idea]         - Inicializa el proyecto con SPEC.md, PLAN.md y AGENTS.md (SDD)")
                print("  /voice [archivo.mp3] - Activa el micrófono o transcribe un archivo de audio (manos libres)")
                print("  /stop                - Detiene la locución TTS en curso (por voz: \"parar\", \"basta\")")
                print("  /think [high|med|off] - Configura o muestra el modo de Razonamiento Profundo (Thinking)")
                print("  /sandbox [merge|discard] - Crea o gestiona un entorno aislado en git worktree (V3-9)")
                print("  /undo                - Deshace la última edición de archivos y restaura su estado anterior")
                print("  /permissions [clear] - Muestra o revoca los permisos persistentes otorgados en la sesión")
                print("  /handoff export|import - Exporta/importa la sesión activa como bundle portable")
                print("  /context             - Muestra el estado del historial y porcentaje del presupuesto de tokens")
                print("  /roi                 - Muestra el dashboard de valor y ahorro económico de API")
                print("  /tokens              - Muestra el consumo de tokens y tasa de acierto de caché")
                print("  /metrics             - Muestra la telemetría detallada de uso, startup tax y herramientas")
                print("  /clear               - Limpia el historial de la conversación actual")
                print("  /exit                - Guarda lecciones de sesión y sale de Yunta\n")
                continue

            if prompt.startswith("/think") or prompt.startswith("/reason"):
                parts = prompt.split()
                if len(parts) > 1:
                    level = parts[1].lower().strip()
                    if level in ("auto", "reset", "clear"):
                        agent.think_override = None
                        print("🧠 Modo Razonamiento: AUTO (Detecta automáticamente según la complejidad del prompt).\n")
                    elif level in ("high", "profundo", "on", "1", "true"):
                        agent.think_override = "high"
                        print("🧠 Modo Razonamiento: FORZADO EN HIGH (Razonamiento Profundo activado para todos los turnos).\n")
                    elif level in ("medium", "medio", "med"):
                        agent.think_override = "medium"
                        print("🧠 Modo Razonamiento: FORZADO EN MEDIUM (Razonamiento Medio activado).\n")
                    elif level in ("low", "bajo"):
                        agent.think_override = "low"
                        print("🧠 Modo Razonamiento: FORZADO EN LOW (Razonamiento Rápido/Bajo).\n")
                    elif level in ("off", "desactivado", "0", "false"):
                        agent.think_override = "off"
                        print("🧠 Modo Razonamiento: FORZADO EN OFF (Ejecución rápida activada).\n")
                    else:
                        print(f"⚠️ Nivel no reconocido: '{level}'. Opciones: high, medium, low, off, auto.\n")
                else:
                    curr = (agent.think_override or "auto (detección inteligente por prompt)").upper()
                    print(f"🧠 Modo Razonamiento actual: {curr}")
                    print("  Sintaxis: /think [high | medium | low | off | auto]\n")
                continue

            if prompt.startswith("/voice") or prompt.startswith("/listen"):
                target_audio = prompt.split(maxsplit=1)[1].strip() if " " in prompt else None
                from .voice import AudioTranscriber, record_microphone, offload_transcript
                transcriber = AudioTranscriber()
                try:
                    if target_audio:
                        print(f"🎙️ Transcribiendo audio: {target_audio} (Ctrl+C para detener)...")
                        prompt = transcriber.transcribe(target_audio)
                    else:
                        print("🎙️ Grabando micrófono en vivo... Presiona [ENTER] en la terminal cuando termines de hablar.")
                        try:
                            temp_wav = record_microphone(duration=None)
                            prompt = transcriber.transcribe(temp_wav)
                            try:
                                os.remove(temp_wav)
                            except OSError:
                                pass
                        except NotImplementedError as err:
                            print(f"⚠️ {err}")
                            prompt = input("Ruta al archivo de audio (.wav, .mp3, .m4a): ").strip()
                            if prompt:
                                prompt = transcriber.transcribe(prompt)
                except KeyboardInterrupt:
                    print("\n⏹️ Transcripción cancelada por el usuario.\n")
                    continue

                if not prompt:
                    print("⚠️ No se obtuvo transcripción de audio.\n")
                    continue

                from .voice import normalize_voice_response
                print(f"\n🗣️ Transcripción capturada ({len(prompt)} caracteres):\n   \"{prompt[:300]}{'...' if len(prompt) > 300 else ''}\"\n")
                prompt = offload_transcript(prompt)
                print("Opciones: [ENTER/s] Enviar al agente | [e] Editar texto | [c] Cancelar")
                try:
                    raw_act = input("> ").strip()
                except (EOFError, KeyboardInterrupt):
                    raw_act = "c"
                action = normalize_voice_response(raw_act) if raw_act else "s"
                if action in ("c", "cancelar"):
                    print("🚫 Transcripción cancelada.\n")
                    continue
                elif action in ("e", "editar"):
                    try:
                        edited = input("✏️ Edita el texto: ").strip()
                        if edited:
                            prompt = edited
                        else:
                            print("🚫 Texto vacío. Transcripción cancelada.\n")
                            continue
                    except (EOFError, KeyboardInterrupt):
                        print("🚫 Transcripción cancelada.\n")
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
            if prompt in ("/resume", "--resume", "-r"):
                sess = load_session()
                if sess and sess.get("messages"):
                    agent.messages = sess["messages"]
                    if sess.get("usage"):
                        agent.total_usage = sess["usage"]
                    print(f"✨ Sesión reanudada ({len(agent.messages)} mensajes cargados en contexto).\n")
                else:
                    print("(no hay ninguna sesión previa guardada para reanudar)\n")
                continue

            if prompt.startswith("/handoff"):
                parts = prompt.split(maxsplit=2)
                sub = parts[1].lower() if len(parts) > 1 else ""
                if sub == "export":
                    from .handoff import export_handoff
                    out_path = parts[2] if len(parts) > 2 else None
                    path = export_handoff(
                        agent.messages,
                        agent.total_usage,
                        session_permissions=agent.session_permissions,
                        active_sandbox=active_sandbox,
                        model=provider.model(),
                        path=out_path,
                    )
                    print(f"✅ Handoff exportado: {path}")
                    print(f"   Reanúdalo en otro harness con: yunta handoff import {path}\n")
                elif sub == "import":
                    if len(parts) < 3:
                        print("Uso: /handoff import <ruta-al-bundle.json>\n")
                    else:
                        from .handoff import import_handoff
                        try:
                            result = import_handoff(parts[2])
                        except ValueError as err:
                            print(f"⚠️ {err}\n")
                            result = None
                        if result is None:
                            print(f"No se pudo leer el bundle: {parts[2]}\n")
                        else:
                            agent.messages = result["messages"]
                            agent.total_usage = result["usage"]
                            agent.session_permissions = result["session_permissions"]
                            print(f"✨ Handoff importado ({len(agent.messages)} mensajes). Modelo original: {result.get('model') or '(no especificado)'}")
                            if result.get("drift_warning"):
                                print(f"   ⚠️ {result['drift_warning']}")
                            print()
                else:
                    print("Uso: /handoff export [ruta] | /handoff import <ruta>\n")
                continue

            if prompt in ("/speak", "--speak", "-s") or prompt.startswith("/speak "):
                sub = prompt[7:].strip().lower() if prompt.startswith("/speak ") else ""
                if sub in ("off", "desactivar", "0", "false"):
                    speak_mode = False
                    print("🔊 Modo de lectura hablada (TTS) desactivado.\n")
                else:
                    speak_mode = True
                    print("🔊 Modo de lectura hablada (TTS) activado.\n")
                continue

            if prompt == "/stop":
                # Corta la locución TTS en curso (palabra clave de voz: "parar"/"stop"/"basta")
                try:
                    from .tts import stop_speaking
                    stop_speaking()
                    print("⏹️ Locución detenida. (Para un turno en generación usa Ctrl+C)\n")
                except Exception:
                    pass
                continue

            if prompt.startswith("/") and not prompt.startswith("//"):
                print(f"Comando desconocido: '{prompt}'. Escribe /help para ver los comandos disponibles.\n")
                continue

            from .intent import IntentClassifier, TaskIntent
            intent = IntentClassifier.classify(prompt)
            if intent == TaskIntent.RESEARCH_AND_CONSULTING:
                print("🔬 [Modo Investigación & Consultoría Activo] Analizando información con contexto persistente...\n")

            try:
                # Gate de eco: micrófono silenciado mientras el agente genera y
                # mientras el TTS habla (voice_approval lo reabre si pide confirmar)
                if voice_listener is not None:
                    voice_listener.pause()
                try:
                    prev_u = agent.total_usage
                    res_text = agent.send(prompt)
                    curr_u = agent.total_usage
                    print_roi_footer(curr_u, curr_u.delta(prev_u))
                    if agent.messages:
                        try:
                            save_session(agent.messages, curr_u, model=provider.model())
                        except Exception:
                            pass
                    if speak_mode and res_text:
                        try:
                            from .tts import TTSProvider, speak, wait_until_done
                            speak(TTSProvider(), res_text)
                            if voice_listener is not None:
                                wait_until_done()  # no reabrir el micrófono mientras habla
                        except (KeyboardInterrupt, SystemExit):
                            from .tts import stop_speaking
                            stop_speaking()
                            raise
                        except Exception:
                            pass
                finally:
                    if voice_listener is not None:
                        voice_listener.resume()
            except KeyboardInterrupt:
                try:
                    from .tts import stop_speaking
                    stop_speaking()
                except Exception:
                    pass
                now = time.monotonic()
                if now - last_interrupt_time < 1.5:
                    print("\n⏹️ Cierre forzado por el usuario (Ctrl+C).")
                    break
                last_interrupt_time = now
                print("\n⏹️ Acción detenida (Ctrl+C). Presiona Ctrl+C otra vez para salir.")
            except QuotaExhausted as e:
                print(f"\n⚠️ {e}\n(puedes reanudar en cualquier momento con `yunta --resume` cuando se restablezca la cuota del proveedor)\n")
            except SystemExit:
                raise
            except Exception as e:
                print(f"error: {e}", file=sys.stderr)
            print()
    finally:
        try:
            from .tts import stop_speaking
            stop_speaking()
        except Exception:
            pass
        if voice_listener is not None:
            try:
                voice_listener.stop()
            except Exception:
                pass
        for c in mcp_clients:
            try:
                c.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
