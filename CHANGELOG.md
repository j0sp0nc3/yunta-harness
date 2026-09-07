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

## [0.2.3] — 2026-09-06

### Modificado
- **Logo oficial reemplazado**: `docs/logo.png` (1024×559, generado con
  modelo de imagen y curado por el autor) pasa a ser el logo del proyecto
  en el README. El boceto vectorial previo queda como `docs/logo.svg`
  (referencia de paleta y composición).

---

## [0.2.4] — 2026-09-06

### Agregado
- `scripts/prueba_glm.py` — prueba de integración de bucle completo
  (write_file con diff + read_file + respuesta) contra un modelo real.
- `Provider.system` — propiedad pública (antes `._system`).

### Validación real (Fase 8)
- **ZCode + GLM-4.7 (Z.ai, vía Coding Plan)**: prueba completa OK.
  Config: `LLM_MODEL=openai/glm-4.7`,
  `LLM_API_BASE=https://api.z.ai/api/coding/paas/v4`, `LLM_API_KEY`.
  Resultado: archivo creado y leído por el modelo, 3192/137 tokens.
- Nota: el prefijo nativo `zai/` requiere saldo API por consumo; el
  Coding Plan funciona por el endpoint OpenAI-compatible de arriba.

---

## [0.3.0] — 2026-09-06

### Agregado
- **Capa de auto-feedback** (`yunta/feedback.py`): el harness se mejora a
  sí mismo entre sesiones.
  - Al salir (`/exit`), el modelo auto-evalúa la sesión (TAREA /
    RESULTADO / LECCION) y se persiste en `.yunta/learnings.md`.
  - Al arrancar, las últimas 5 lecciones se inyectan en el system
    prompt ("Lecciones de sesiones anteriores — aprendidas por ti mismo").
  - Best-effort: fallos de red o formato se ignoran sin romper el cierre.
- **Guardas de honestidad** en `SYSTEM_PROMPT` (derivadas del incidente
  de alucinación detectado en la demo): prohibido narrar acciones no
  ejecutadas con tools reales; verificación obligatoria tras editar.
- `tests/test_feedback.py` (6 tests).

### Motivo
Durante la demo real, un prompt mínimo indujo al modelo a fabricar una
transcripción entera de acciones nunca ejecutadas. Dos conclusiones que
esta versión materializa: (1) el prompt debe exigir verificación y
honestidad sobre tools; (2) las lecciones de cada sesión deben volver al
agente en la siguiente — auto-mejora sin infraestructura pesada.

### Validación
- Circuito real con GLM-4.7 (Z.ai Coding Plan): historial de sesión →
  auto-evaluación → lección persistida → inyección verificada en el
  system prompt del arranque siguiente.
- `pytest` → 24 passed.

---

## [0.4.0] — 2026-09-06

### Agregado
- **Tools de búsqueda** (`yunta/tools/search.py`):
  - `grep`: regex recursivo sobre directorio, salida `ruta:linea: texto`,
    `max_results` (default 50), regex inválido → `ValueError`.
  - `glob`: patrones tipo `**/*.py` vía `Path.glob`, rutas POSIX ordenadas.
- `tests/test_search.py` (5 tests).

### Proceso — primer dogfooding del harness
- Implementado por **yunta mismo** (GLM-4.7 vía Coding Plan): leyó las
  convenciones del repo (AGENTS.md + files.py), escribió tool + tests,
  verificó con pytest y respetó el alcance (solo 2 archivos nuevos).
- Revisión humana posterior encontró 1 hueco de integración: `cli.py`
  no importaba `search`, por lo que el REPL real no registraba las tools
  (los tests del agente las importaban directamente y lo enmascaraban).
  Corregido agregando el import.

### Modificado
- `yunta/cli.py`: importa `search` junto a `bash`/`files`.

### Verificación
- `pytest` → 29 passed. Registro de tools del REPL verificado.

---

## [0.5.0] — 2026-09-06

### Agregado
- **Memoria persistente entre sesiones** (`yunta/tools/memory.py`):
  - `remember(content, kind?, tags?)`: guarda en `.yunta/memory.json`
    (configurable vía `MEMORY_PATH`); kind: fact/preference/decision.
  - `recall(query)`: búsqueda case-insensitive por palabras en content y
    tags, máximo 10 más recientes, formato `[fecha] (kind) content [tags]`.
- `tests/test_memory.py` (5 tests).

### Proceso — segunda ronda de dogfooding
- Implementado por **yunta mismo** (GLM-4.7): leyó convenciones, escribió
  tool + tests, detectó por sí solo que faltaba el import en `cli.py`
  (la lección de v0.4.0 se aplicó sin que se lo pidiera explícitamente),
  lo corrigió por la vía autorizada y verificó las 7 tools registradas.
- Desviación de alcance detectada en revisión humana: el agente también
  subió `version` en `pyproject.toml` a 0.5.0 (no autorizado; la intención
  era correcta según convención y se conserva). Sin otros cambios fuera
  de alcance; sin archivos temporales residuales.
- El agente además auto-limpió una línea confusa en su propio test antes
  de cerrar.

### Modificado
- `yunta/cli.py`: importa `memory`.
- `pyproject.toml`: versión 0.5.0.

### Verificación
- `pytest` → 34 passed. Registro de 7 tools en el REPL verificado.
- Prueba funcional real: remember→persistencia en JSON→recall con match,
  case-insensitive y sin resultados. CHANGELOG y docs actualizados a mano.

---

## [0.6.0] — 2026-09-06

### Agregado
- **Subagente de investigación read-only** (`yunta/tools/delegate.py`):
  - Tool `delegate_research(task)`: crea un `Agent` interno restringido a
    `read_file`/`grep`/`glob`, max_turns 15, y devuelve sus hallazgos.
  - Provider inyectado vía `set_provider()` desde el CLI (sin providers
    por defecto: sin configurar, error claro).
- `Agent(tools=...)`: parámetro opcional de subconjunto de tools — primer
  cambio al core vía dogfooding. Sin el parámetro, comportamiento idéntico.
- `tests/test_delegate.py` (9 tests: subset, global, ejecución del
  subagente, entradas inválidas, sin configurar).

### Proceso — tercera ronda de dogfooding
- Implementado por **yunta mismo** (GLM-4.7), esta vez tocando el core
  (`agent.py`). Mitigaciones: especificación exacta + restricción dura de
  no romper los 34 tests existentes (cumplida: pasaron sin modificarse).
- El agente pasó por un borrador defectuoso de `agent.py` que se
  autocorrigió en el turno siguiente; el diff final es quirúrgico.
- Registró solo read-only tools en el subagente; wiring del CLI correcto.
- Validación end-to-end real con GLM-4.7: la raíz delegó y el subagente
  investigó usando exclusivamente glob/grep/read_file (sin bash ni
  writes), devolviendo hallazgos exactos sobre el propio repo.

### Modificado
- `yunta/agent.py`: `__init__` acepta `tools` opcional; `_definitions()`.
- `yunta/cli.py`: importa `delegate` y llama `set_provider(provider)`.

### Verificación
- `pytest` → 43 passed. 8 tools registradas en el REPL.

---

## [0.7.0] — 2026-09-06

### Agregado
- **Streaming de respuestas y reensamblado de tool calls** (`yunta/provider.py`, `yunta/agent.py`):
  - `Provider.send(..., on_text=None)`: soporte opcional de streaming en la interfaz neutral.
  - `LiteLLMProvider._consume_stream()`: procesa stream de tokens en tiempo real invocando `on_text`.
  - Reensamblado robusto de tool calls fragmentados: agrupa chunks por `index`, reconstruyendo `tool_name` y concatenando fragmentos de `tool_input` (`function.arguments`) hasta finalizar la llamada.
  - Soporte de `stream_options={"include_usage": True}` para acumulación exacta de métricas de tokens en streams.
  - Salvaguarda de `StopReason.TOOL_USE` si el proveedor emite finish_reason no específico cuando hay tool calls presentes.
- `tests/test_provider.py`: tests unitarios de streaming de texto puro y streaming de tool calls fragmentados (45 tests totales en la suite).

### Modificado
- `yunta/agent.py`:
  - Detección dinámica de soporte de streaming (`on_text` en firma del provider) manteniendo estricta compatibilidad con providers síncronos/mocks (`FakeProvider`).
  - Reseteo adecuado de `_streamed` antes de la llamada para evitar salida duplicada en consola.

### Verificación
- `pytest` → 45 passed (100% verde).
- Compilación sin errores (`py_compile` en los 14 archivos Python).
- Smoke test end-to-end con `gemini/gemini-3.6-flash` en Antigravity completando llamada a `write_file` y `read_file` con streaming en tiempo real.

---

## [0.8.0] — 2026-09-06

### Agregado
- **Soporte MCP (Model Context Protocol) sobre stdio** (`yunta/mcp.py`):
  - Cliente `MCPClient` minimalista (~100 líneas) implementado exclusivamente con la librería estándar de Python (`subprocess`, `json`), sin dependencias externas ni SDKs pesados.
  - Handshake de inicialización JSON-RPC 2.0 (`initialize` y `notifications/initialized`).
  - Auto-descubrimiento de herramientas vía `tools/list` desde configuración `.yunta/mcp.json`.
  - Integración transparente en el `registry` de Yunta con prefijo de espacio de nombres `mcp__<servidor>__<tool>`.
  - Ejecución de llamadas a herramientas (`tools/call`) canalizadas a través del bucle con los permisos de Yunta.
  - Ciclo de vida y cierre limpio de subprocesos (`close()`) al finalizar la sesión del CLI.
  - Formato estándar de configuración compatible con el ecosistema MCP (Claude Desktop / Cursor / VS Code).
- `tests/test_mcp.py`: 3 tests unitarios cubriendo handshake, auto-descubrimiento, ejecución de tools, manejo de errores JSON-RPC y degradación silenciosa sin configuración (48 tests totales en la suite).

### Modificado
- `yunta/cli.py`: integra `load_mcp_servers()` al inicio y limpieza en bloque `finally`.
- `README.md`: documentación de configuración de servidores MCP.
- `docs/PLAN.md`: ítem de Soporte MCP completado en el backlog.
- `.gitignore`: exclusión de `.yunta/`.

### Verificación
- `pytest` → 48 passed (100% verde).
- Compilación de los 15 archivos Python (`py_compile`).
- Smoke test end-to-end con servidor MCP real ejecutando `consultar_clima` y respuesta del modelo Gemini 3.6 Flash vía Yunta en Antigravity.

---

## [0.9.0] — 2026-09-06

### Agregado
- **Edición quirúrgica de archivos `str_replace`** (`yunta/tools/files.py`):
  - Tool `str_replace(path, old_str, new_str)` inspirada en el estándar de Anthropic (SWE-bench / Claude Code).
  - Validación determinista de unicidad:
    - Falla con error descriptivo si `old_str` no existe en el archivo.
    - Falla con advertencia de ambigüedad si `old_str` aparece múltiples veces, solicitando más líneas de contexto circundante.
    - Reemplazo exacto preservando indentación y codificación UTF-8 cuando hay una coincidencia única.
  - Soporte de previsualización de diffs unificados en `Agent._tool_detail` (`yunta/agent.py`) antes de la aprobación del usuario.
- `tests/test_tools.py` y `tests/test_agent.py`: 5 nuevos tests unitarios (éxito, no encontrado, ambigüedad, archivo inexistente y visualización de diff en el agente). 53 tests totales en la suite.

### Proceso — cuarta ronda de dogfooding
- Implementado por **yunta mismo** (Gemini 3.6 Flash vía Antigravity):
  - El agente inspeccionó `yunta/tools/files.py` y `yunta/agent.py`.
  - Creó la implementación completa de `str_replace` y su integración de diffs.
  - Escribió la suite de pruebas unitarias y ejecutó la verificación.

### Verificación
- `pytest` → 53 passed (100% verde).
- Compilación de los 15 archivos Python (`py_compile`).

---

## [0.10.0] – 2026-09-06

### Agregado
- **Licencia MIT formal** (`LICENSE`): Incorporación formal del archivo de licencia MIT al repositorio.
- **Interrupción limpia de turnos con KeyboardInterrupt (`Ctrl+C`)** (`yunta/agent.py`):
  - Captura controlada de `KeyboardInterrupt` en el bucle principal de ejecución de turnos `_loop()`.
  - Preservación estricta de la invariante de roles alternados de la conversación: si el turno se interrumpe después de un mensaje de usuario o tool results, se añade un mensaje con rol `ASSISTANT` y contenido `"[interrumpido por el usuario]"`.
  - Retorno limpio de la respuesta acumulada hasta el momento de la interrupción.
- **REPL interactivo resiliente** (`yunta/cli.py`):
  - Manejo de `KeyboardInterrupt` alrededor de `agent.send(prompt)` en el bucle de interacción para regresar inmediatamente al prompt `> ` sin abortar el proceso ni perder el historial previo.
  - Reconfiguración automática de `stdout` y `stderr` a UTF-8 en consolas Windows (`sys.stdout.reconfigure(encoding="utf-8", errors="replace")`) para evitar fallos por caracteres especiales en diffs o tool calls.
- **Resiliencia de conectividad y reintentos automáticos** (`yunta/provider.py`):
  - Manejo de backoff con reintentos para errores transitorios de rate limit (`429`) y congestión del servidor (`503`, `MidStreamFallbackError`).
- **Tests unitarios** (`tests/test_agent.py`):
  - Test `test_keyboard_interrupt_in_loop_preserves_assistant_message` validando la captura no destructiva, mensaje final de asistente y conservación de roles.

### Modificado
- `yunta/agent.py`: soporte de interrupción limpia y preservación de mensajes en `_loop()`.
- `yunta/cli.py`: soporte de `Ctrl+C` en el REPL y codificación UTF-8 en Windows.
- `yunta/provider.py`: reintentos automáticos ante 429 y 503.
- `docs/PLAN.md`: actualización de estado a v0.10.0.
- `docs/architecture.md` y `docs/architecture_en.md`: especificación técnica de arquitectura bilingüe (ES/EN) con diagrama Mermaid y desglose de capas.
- `README.md` y `README_en.md`: guía de usuario bilingüe completa con detalles de configuración de modelos, comandos, aprobaciones con diff unificado, memoria y MCP.

### Verificación
- 54 tests pasando al 100% en `pytest` (`tests/test_agent.py`, `tests/test_tools.py`, `tests/test_mcp.py`, `tests/test_provider.py`, etc.).
- Compilación sintáctica verificada con `py_compile`.
- Implementación realizada mediante dogfooding utilizando la herramienta `str_replace` recientemente creada.


## [0.11.0] – 2026-09-06

### Agregado
- **Prompt Caching nativo y agnóstico al LLM** (`yunta/provider.py` y `yunta/api.py`):
  - Inyección de punto de corte de caché estructurado (`cache_control: {"type": "ephemeral"}`) en el system prompt dentro de `_to_litellm()`.
  - Activación automática de Prompt Caching en Anthropic Claude (reducción de hasta 90% en costo de tokens cacheados y aceleración de latencia TTFT del 50-80%).
  - Compatibilidad transparente sin errores en OpenAI, DeepSeek, Google Gemini y proveedores locales (Ollama/vLLM), aprovechando su caching automático a nivel de prefijo.
  - Normalización de métricas de telemetría de caché en `yunta/api.py` (`Usage.cached_tokens`).
  - Extracción unificada de tokens cacheados desde LiteLLM soportando `prompt_tokens_details.cached_tokens`, `cache_read_input_tokens` y `prompt_cache_hit_tokens` tanto en respuestas síncronas como en streaming.
- **Visibilidad de ahorro en el REPL** (`yunta/cli.py`):
  - El comando `/tokens` ahora desglosa el ahorro de caché: `in=<tokens> (cached=<cached_tokens>) out=<output_tokens>`.
- **Tests unitarios** (`tests/test_provider.py`):
  - `test_system_prompt_includes_cache_control`: valida la presencia de `cache_control` en el system prompt.
  - `test_usage_accumulates_cached_tokens`: valida la acumulación en el método `Usage.add()`.
  - `test_provider_tracks_cached_tokens`: valida la extracción y suma en `provider.total_usage`.

### Modificado
- `pyproject.toml`: versión actualizada a `0.11.0`.
- `docs/PLAN.md`: actualizado estado a v0.11.0.

### Verificación
- 57 tests pasando al 100% en `pytest` (54 existentes + 3 nuevos tests unitarios).
- Compilación y verificación sintáctica con `py_compile` y `compileall`.
- Implementado de forma autónoma mediante dogfooding con Yunta.

---

## [1.0.0] — 2026-09-07

### Agregado
- **Documentación y Presentación SDD (Spec-Driven Development)**: Creación de `docs/sdd.md` y `docs/sdd_en.md`, cruzando la arquitectura del harness con el desarrollo guiado por especificaciones (los 6 pilares: contratos en `AGENTS.md`, esquemas JSON-Schema/MCP, edición quirúrgica con `str_replace`, oráculo ejecutable con `pytest`, Prompt Caching económico y anti-regresión con `learnings.md`).
- **CI (GitHub Actions)**: `.github/workflows/ci.yml` — tests en Python
  3.10-3.13 en cada push/PR. La suite no requiere credenciales (LiteLLM
  se intercepta en tests).
- **Documentación v1.0.0 unificada**: `docs/architecture.md` y `docs/architecture_en.md` actualizados con la especificación de API pública congelada, pipeline de CI y sección de Spec-Driven Development. `README.md` y `README_en.md` actualizados con guía de uso como librería Python embebible y enlace a matriz de proveedores.
- **Matriz de proveedores**: `docs/PROVEEDORES.md` +
  `scripts/prueba_proveedor.py` (prueba universal: tool call real +
  lectura + verificación). GLM-4.7 (Z.ai Coding Plan) re-verificado con
  el script universal: RESULTADO OK.
- Congelación de API: exports estables en `yunta/__init__.py` (núcleo,
  compactación, provider, FeedbackStore; `Response`/`Usage` añadidos).

### Declaración de estabilidad (1.0)
Superficie pública estable: `Agent(provider, system, compactor,
max_turns, confirm, tools)`, `Provider.send(messages, tools, on_text)`,
`LiteLLMProvider`, tipos de `api.py`, `FeedbackStore`,
`@registry.register`, estrategias de compactación. Cambios que rompan
esta interfaz requieren versión mayor (2.0).

### Roadmap de evolución
E1 CI ✅ · E2 API congelada ✅ · E3 matriz ✅ (GLM+Gemini verificados,
resto comunitario) · E4 PyPI pendiente (último, por decidir cuenta de
publicación).

### Verificación
- `pytest` → 57 passed. Prueba universal GLM-4.7 → OK.
- El push de esta versión dispara el primer run del CI.

---

## [1.0.2] — 2026-09-07

### Agregado
- **Modularización y jerarquía de System Prompt (E7)** (`yunta/cli.py`):
  - Jerarquía de resolución para el system prompt base:
    1. Variable de entorno `YUNTA_SYSTEM_PROMPT` si está definida.
    2. Archivo de usuario `~/.yunta/system_prompt.md` si existe.
    3. `SYSTEM_PROMPT` por defecto (fallback inmutable con frontera ontológica y reglas de honestidad).
  - Concatena `AGENTS.md` si existe en el workspace del proyecto y el preámbulo de lecciones de `FeedbackStore`.
- **Tests unitarios** (`tests/test_agent.py`):
  - `test_load_system_prompt_custom_override`: valida la sobreescritura vía variable de entorno `YUNTA_SYSTEM_PROMPT` y fallback a `~/.yunta/system_prompt.md`.

### Verificación
- `pytest` → 64 passed (100% verde).
- Compilación `compileall` sin errores.

---

## [1.0.1] — 2026-09-07

### Agregado
- **Métricas livianas de eficiencia de recursos**: Telemetría 100% en memoria en `yunta/api.py` (`Usage`), cálculo de Cache Hit Rate, cálculo de tokens brutos transferidos frente a chat crudo sin harness, desglose por tipo de herramienta y errores en `yunta/agent.py`, comandos `/tokens` y `/metrics` enriquecidos en `yunta/cli.py`, y 5 tests unitarios en `tests/test_metrics.py`. Cero llamadas adicionales a APIs, cero latencia y cero dependencias.
- **Guardrail ontológico y flujo de 5 fases**:
  - `yunta/cli.py`: refuerzo de `SYSTEM_PROMPT` con frontera explícita entre el harness de desarrollo y el runtime de producción (evita que el modelo cree daemons o servicios locales para Yunta).
  - `tests/test_agent.py`: test unitario de regresión `test_system_prompt_ontological_boundary()`.
  - `docs/quickstart.md` y `docs/quickstart_en.md`: adición del **Paso 0** con la tabla *Lo que ES vs Lo que NO ES Yunta*, la *Regla de Oro*, metodología de 5 fases y plantilla `AGENTS.md` para proyectos de clientes.
- **Harness para SDD en portadas**: Actualización del título principal y adición de sección destacada en `README.md` y `README_en.md` posicionando formalmente a Yunta como el Harness de Agente de Código para Spec-Driven Development (SDD), vinculándolo con la arquitectura y guías de `docs/sdd.md`.
- **Guía paso a paso bilingüe**: Creación de `docs/quickstart.md` y `docs/quickstart_en.md`, tutorial detallado desde la instalación y configuración de modelos (Gemini, Claude, GPT-4o, Ollama, DeepSeek) hasta la verificación con `scripts/prueba_proveedor.py`, flujo de turnos interactivo, aprobaciones con diff unificado, comandos del REPL (`/tokens`, `Ctrl+C`, `/clear`, `/exit`) y uso avanzado con `AGENTS.md` y MCP.

### Corregido
- **CI fallaba en Python 3.10**: bug upstream en litellm 1.100.0 —
  `llms/anthropic/experimental_pass_through/context_management/editors/compact.py`
  importa `typing.NotRequired`, inexistente en 3.10, pese a que litellm
  declara `requires-python >=3.10`.

### Modificado
- Piso de Python subido a **3.11**: `pyproject.toml` (`requires-python`),
  matriz del CI (3.11/3.12/3.13) y README/AGENTS.
- Nota: si litellm corrige el bug upstream, se puede restaurar 3.10.

### Verificación
- El push de esta versión dispara el CI; verde en 3.11-3.13 confirma.

---

## Convenciones para futuros cambios

1. Toda modificación se registra en este archivo: qué cambió, en qué archivo y por qué.
2. Los números de versión siguen SemVer: `mayor.minor.parche`.
3. El harness no debe ganar dependencias de proveedores específicos: si un cambio
   requiere importar un SDK concreto fuera de un adaptador, el diseño se revisa.
4. Verificación mínima antes de registrar un cambio: compilar + smoke test del
   bucle con provider falso.
