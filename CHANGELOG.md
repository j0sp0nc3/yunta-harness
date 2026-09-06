# Changelog — yunta

Registro de avance del proyecto. Cada modificación al harness se documenta aquí
para que cualquiera —persona, IDE u otro agente/modelo— pueda retomar el contexto
sin historial previo.

Formato: fecha, cambios agregados/modificados/eliminados, y motivo.

---

## [0.1.0] — 2026-09-06

### Agregado
- **Núcleo del harness** (v1, núcleo mínimo):
  - `yunta/api.py` — tipos neutrales de conversación: `Message`, `Block`,
    `ToolDef`, `Response`, `Usage`, `StopReason`. Ningún tipo de SDK externo
    cruza esta frontera; es el idioma común de todo el harness.
  - `yunta/provider.py` — `LiteLLMProvider`: única capa que habla con modelos.
    Traduce los tipos neutrales al formato unificado de LiteLLM y viceversa
    (incluye el split de tool_results a mensajes `role:"tool"`).
  - `yunta/agent.py` — bucle del agente: agrega mensaje user → consulta
    provider → ejecuta tool calls (con aprobación) → agrega resultados → repite
    hasta `stop_reason ≠ tool_use` o `max_turns`. Los errores de tools vuelven
    al contexto como `tool_result` con `is_error=True` para que el modelo
    reintente.
  - `yunta/compact.py` — estrategias `NoCompaction` y `SlidingWindow`
    (recorte en límites seguros: antes de un mensaje user sin tool_results).
  - `yunta/tools/` — registro de tools con decorador `@registry.register`;
    auto-registro al importar el paquete.
  - `yunta/tools/bash.py` — tool `bash` con timeout de 30s y aprobación.
  - `yunta/tools/files.py` — tools `read_file` y `write_file` (write con
    aprobación).
  - `main.py` — REPL con comandos `/clear`, `/tokens`, `/exit`.
  - `requirements.txt`, `README.md`.

### Decisiones de diseño
- **Agnóstico al proveedor por construcción**: `LLM_MODEL` es obligatorio y no
  existe fallback ni proveedor por defecto; sin esa variable el proceso termina
  con un error que muestra ejemplos de configuración para varios proveedores.
  Variables soportadas: `LLM_MODEL`, `LLM_API_KEY`, `LLM_API_BASE`.
- **Sin dependencias de SDKs de proveedores**: LiteLLM es la única capa de
  acceso, por lo que OpenAI, Anthropic, Gemini, Ollama, OpenRouter, vLLM, Groq,
  DeepSeek, etc. funcionan sin cambios de código.
- **Sin frameworks de agentes**: el bucle, los permisos y el contexto son
  propios; nada de LangChain/Agents SDK.

### Verificación
- Compilación sin errores de los 9 archivos Python.
- Smoke test del bucle completo con provider falso: tool call `write_file`
  aprobada, archivo escrito, conversación con estructura correcta
  (user → assistant/tool_use → user/tool_result → assistant/text).
- Total: ~500 líneas.

### Documentación de gobernanza (mismo día, post-lanzamiento)
- `AGENTS.md` — reglas para cualquier agente/IDE que modifique el proyecto:
  aislamiento del SDK, sin proveedor default, sin frameworks, registro
  obligatorio en changelog, minimalismo. Es la convención multi-IDE que la
  mayoría de los agentes leen automáticamente.
- `docs/PLAN.md` — plan de la iniciativa compartible: decisiones fundacionales,
  tabla de fases con estado (1-6 completadas; 7 validación multi-proveedor y
  8 difusión pendientes) y backlog no comprometido.
- Motivo: el plan solo existía en conversación y se perdería al compartir la
  carpeta; ahora plan + avance + reglas viajan con el código.

---

## [0.1.1] — 2026-09-06

### Agregado
- `tests/test_provider.py` — suite pytest (4 tests) que valida el
  agnosticismo del provider interceptando `litellm.completion`:
  1. Traducción OpenAI: system prompt, assistant con tool_calls,
     tool_results como mensajes `role:"tool"`, schemas con envelope,
     acumulación de usage.
  2. Mismo core para Anthropic: solo cambia `LLM_MODEL`.
  3. Endpoint custom vía `LLM_API_BASE` (Ollama/vLLM/OpenRouter).
  4. Ausencia de `LLM_MODEL` → error de arranque con mensaje claro.

### Modificado
- `docs/PLAN.md` — Fase 7 marcada ✅ con nota; backlog de tests marcado parcial.

### Limitación registrada
- Sin credenciales ni Ollama local en el entorno de desarrollo: la
  validación llega hasta la capa de traducción (kwargs que recibe LiteLLM).
  El enrutado real contra APIs vivas queda como smoke manual del usuario
  final con su propio modelo.

### Verificación
- `python -m pytest tests/ -q` → 4 passed.

---

## [0.1.1 — difusión] — 2026-09-06

### Agregado
- `pyproject.toml` — paquete instalable (`pip install -e .`) con entry point
  `yunta` y extra `dev` (pytest).
- `yunta/cli.py` — REPL movido a módulo instalable; `main.py` queda como
  wrapper fino.
- `.gitignore`.
- Repo git inicializado; commit base `584a8ae`.

### Modificado
- `docs/PLAN.md` — Fase 8 en progreso con estado de empaquetado.

### Integración multi-IDE (verificada contra documentación oficial)
- **ZCode**: lee `AGENTS.md` de la raíz — ya presente.
- **Antigravity**: soporta `AGENTS.md`/`GEMINI.md` en la raíz del workspace
  (además de `.agents/rules/`) — ya compatible sin cambios.

### Verificación
- `pip install -e .` OK; `from yunta.cli import main` OK; entry point
  responde con error claro sin `LLM_MODEL`; `pytest` → 4 passed.

---

## [0.2.0] — 2026-09-06

### Agregado
- **Diff unificado en la aprobación de `write_file`**: `agent.py` calcula el
  diff (difflib) contra el contenido actual del archivo y lo muestra antes
  del y/n. `confirm` ahora recibe `(name, detail)`.
- **Carga de `AGENTS.md` del proyecto** en el system prompt (`cli.py`):
  si existe `AGENTS.md` en el directorio de trabajo, se adjunta como
  contexto del proyecto.
- `tests/test_agent.py` (6), `tests/test_tools.py` (5), `tests/test_compact.py` (3).

### Corregido
- **Bug en `SlidingWindow.compact`**: cortaba *después* del mensaje user
  seguro, dejando un mensaje assistant (o tool_result huérfano) al inicio
  del historial restante. Ahora corta *en* el primer user seguro desde el
  exceso. Detectado por `test_sliding_window_cuts_at_safe_boundary`.

### Modificado
- `pyproject.toml` → versión 0.2.0.

### Verificación
- `pytest` → 18 passed (provider 4, agent 6, tools 5, compact 3).
- Compilación sin errores.

---

## [0.2.1 — publicación] — 2026-09-06

### Publicado
- Repo público: **https://github.com/j0sp0nc3/yunta-harness**
- Rama `master`, historial completo (v0.1.1 → v0.2.0) con autoría real.
- Autenticación GitHub CLI configurada para futuras operaciones.

### Verificación
- `gh repo view` confirma: PUBLIC, rama master, commits `945a049` y `1ae1d8f`.

---

## [0.2.2] — 2026-09-06

### Agregado
- `docs/logo.svg` — identidad gráfica: dos cabezas de buey en silueta
  (estilo grabado, inspirado en la estética de mascotas de proyectos
  libres) unidas por una yunta de madera curva con anillo central.
  Paleta: pizarra oscura `#1f2937`, crema `#f5eeda`, madera `#b45309`.
- Logo integrado en la cabecera de `README.md`.

---

## Convenciones para futuros cambios

1. Toda modificación se registra en este archivo: qué cambió, en qué archivo y por qué.
2. Los números de versión siguen SemVer: `mayor.minor.parche`.
3. El harness no debe ganar dependencias de proveedores específicos: si un cambio
   requiere importar un SDK concreto fuera de un adaptador, el diseño se revisa.
4. Verificación mínima antes de registrar un cambio: compilar + smoke test del
   bucle con provider falso.
