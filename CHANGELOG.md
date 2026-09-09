# Changelog — yunta

Registro de avance del proyecto. Cada modificación al harness se documenta aquí
para que cualquiera —persona, IDE u otro agente/modelo— pueda retomar el contexto
sin historial previo.

Formato: fecha, cambios agregados/modificados/eliminados, y motivo.

---

## [1.1.1] — 2026-09-09

### Agregado
- **V3-8 / O1-d — Presupuesto de arranque medible (`startup_tax`)**:
  - `yunta/provider.py`: cálculo e inspección de tokens de arranque aproximados (`provider.startup_tax` y `estimate_startup_tax()`) contando payload inicial de system prompt y schemas de herramientas con `litellm.token_counter` (y fallback `len//4`).
  - `yunta/api.py` & `yunta/cli.py`: reporte de `Startup tax (payload inicial)` en `/metrics` y `/tokens` con objetivo `<5,000` tokens.
  - `tests/test_provider.py`: prueba unitaria `test_startup_tax_calculation` (123 tests 100% verde).
- **Resiliencia en consolas Windows (`check_endpoints.py`)**:
  - Reconfiguración automática de `stdout` y `stderr` a UTF-8 (`errors="replace"`) en `scripts/check_endpoints.py` al ejecutarse en Windows.

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

---

---

## [1.1.0] — 2026-09-08

### Agregado
- **V2-5 — Modo Servidor MCP de Yunta (`yunta serve-mcp`, `yunta mcp`) (`server_mcp.py`, `cli.py`)**:
  - Implementación completa del protocolo estándar Model Context Protocol (versión `2024-11-05`) sobre `stdio` mediante JSON-RPC 2.0.
  - Exposición de todo el catálogo blindado de herramientas de Yunta (`read_file`, `write_file`, `str_replace`, `list_dir`, `bash`) con sus correspondientes esquemas JSON Schema (`inputSchema`).
  - Permite a IDEs y clientes MCP modernos (Claude Desktop, Cursor, Windsurf, Claude Code, Antigravity) conectarse a Yunta directamente vía `stdio` para ejecutar herramientas deterministas con control de presupuesto y paginación.
  - Redirección estricta de telemetría y logs a `sys.stderr` para garantizar pureza en el canal de mensajes `sys.stdout`.
  - Despacho CLI ultrarrápido desde `yunta serve-mcp` o el alias `yunta mcp` sin requerir clave de API.
  - 8 nuevas pruebas unitarias y de integración end-to-end (`MCPClient` conectándose a `yunta serve-mcp`) en `tests/test_server_mcp.py`.
  - **Cierre formal del Backlog v2 al 100%**: Suite ampliada a **99 pruebas pasando (100% PASS)**.

## [1.0.9] — 2026-09-08

### Agregado
- **V2-1 — Modo Gobernanza `yunta check` (`governance.py`, `cli.py`)**:
  - Comando CLI ligero y 100% local para auditar la salud SDD de cualquier proyecto sin costo de tokens ($0 API calls, ejecución instantánea).
  - Inspección exhaustiva de la tríada SDD (`SPEC.md`, `PLAN.md`, `AGENTS.md`), configuración `.yunta/config.json`, estado de Git y suite de tests.
  - Detección automática del protocolo de interoperabilidad en `AGENTS.md` (delegación canónica a Yunta).
  - Ejecución opcional de tests unitarios del proyecto con flag `--tests` (timeout de seguridad de 60s).
  - Salida dual: tabla visual con formato de consola o salida estructurada con flag `--json` para que IDEs externos (Claude Code, Cursor, Antigravity) o scripts de CI/CD verifiquen la gobernanza programáticamente.
  - Retorna código de salida estándar: `0` si el proyecto es saludable o `1` si faltan especificaciones críticas o fallan los tests.
- **V2-2 — Sesiones Resumibles `yunta --resume` (`session.py`, `agent.py`, `cli.py`)**:
  - Persistencia atómica de mensajes, bloques y telemetría de tokens (`Usage`) en `.yunta/session_state.json`.
  - Auto-guardado continuo tras cada turno completado y al interrumpir con `Ctrl+C`.
  - Reanudación instantánea del contexto y métricas mediante flag `yunta --resume` o `yunta -r`.
  - Limpieza automática del archivo de sesión al ejecutar `/clear` en el REPL.
- **Especificación Canónica del Harness (`docs/SPEC.md`)**:
  - Creación formal de la especificación técnica SDD para el desarrollo del propio harness Yunta (visión, frontera ontológica, requerimientos, arquitectura y criterios de calidad).
- **Tests Unitarios**:
  - `tests/test_governance.py`: 5 tests unitarios verificando directorio vacío, repositorio SDD completo, fallback a `docs/`, salida JSON y salida de consola.
  - `tests/test_session.py`: 4 tests unitarios verificando serialización de bloques/mensajes, telemetría de uso, guardado/carga/limpieza atómica y manejo de archivos corruptos.
  - Suite total de Yunta ampliada a **91 tests pasando (100% PASS)**.

## [1.0.8] — 2026-09-08

### Agregado
- **V2-4 — Herramienta Nativa `list_dir` con Presupuesto de Tokens (`files.py`)**:
  - Inspección estructurada de directorios en árbol compacto con tamaños legibles (`B`, `KB`, `MB`).
  - Filtrado automático de directorios pesados (`.git`, `node_modules`, `__pycache__`, `.venv`, `.pytest_cache`, `.gemini`, `.zcode`).
  - Control de recursión (`max_depth`, default: 2) y truncamiento inteligente de presupuesto (`max_files`, default: 80).
  - Formato de conectores ASCII universal (`|-- `, `\-- `) a prueba de terminales Windows cp1252.
- **V2-7 — Protocolo Canónico de Interoperabilidad en `AGENTS.md` (`init.py`)**:
  - Incorporación formal de la regla de interoperabilidad para IDEs externos (Claude, Cursor, Copilot) en la plantilla `generate_agents()`.
  - Establece a `yunta` CLI como el único ejecutor y oráculo oficial del repositorio, priorizándolo sobre el LLM interno del IDE y habilitando consultas de solo lectura (Q&A) sin forzar modificaciones.

---

## [1.0.7] — 2026-09-08

### Corregido & Mejorado (Auditoría Dogfooding P1-P5)
- **P1 — Prevención de `tool_use` huérfano ante `Ctrl+C` (`agent.py`)**:
  - Al interrumpir con `KeyboardInterrupt` durante la ejecución de herramientas, ahora se cierran todas las llamadas a herramientas pendientes agregando bloques `TOOL_RESULT` con estado cancelado, evitando que el proveedor lance `400 Bad Request` en el siguiente turno.
- **P2 — Resiliencia ante rechazo de `stream_options` (`provider.py`)**:
  - Detección automática de errores en endpoints OpenAI-compatibles estrictos (vLLM, LocalAI) que no soportan `stream_options`, reintentando de inmediato sin el kwarg.
- **P3 — Inicialización segura de `mcp_clients` (`cli.py`)**:
  - `mcp_clients` inicializado como lista vacía al inicio de `main()` previniendo `UnboundLocalError` en bloques `finally`.
- **P4 — Compactador `SlidingWindow` activo en CLI (`cli.py`)**:
  - Integración nativa del compactador por ventana deslizante en el REPL y modo single-shot (configurable vía `YUNTA_MAX_MESSAGES`, default: 40).
- **P5 & V2-3 — Cap de tamaño y seguridad UTF-8 en `read_file` (`files.py`)**:
  - Límite por defecto a 2000 líneas con mensaje de truncamiento y soporte opcional para `offset` y `limit`. Lectura y escritura con `errors="replace"` protegiendo contra errores de codificación en Windows (cp1252).
- **Documentación**:
  - `README.md` y `README_en.md` actualizados con todos los comandos interactivos (`/init`, `/undo`, `/roi`, `/metrics`, `/tokens`, `/help`).

---

## [1.0.6] — 2026-09-07

### Agregado
- **E9 — Cascada de Respaldo de Modelos (`ModelFallbackRouter`)**:
  - Soporte para variable de entorno `LLM_MODELS` con lista separada por comas de proveedores/modelos prioritarios.
  - Conmutación en caliente automática ante errores transitorios de API, saturación o cuotas agotadas (`429`, `503`, `RESOURCE_EXHAUSTED`, `ratelimit`, `quota`) sin abortar la sesión ni perder el contexto del turno.
- **E11 — Streaming de Pensamiento y Pre-Notificación de Herramientas**:
  - Soporte de streaming para tokens de razonamiento (`reasoning_content` / `thought`) en modelos de razonamiento (ej. DeepSeek-R1, Claude 3.7 Thinking).
  - Pre-notificación en terminal (`[tool] {name} en ejecución...`) previo a la invocación de herramientas para retroalimentación visual inmediata.
- **E13 — Micro-Checkpoints y Time-Travel en Memoria (`/undo`)**:
  - Captura instantánea de snapshots en memoria de archivos afectados antes de cualquier ejecución destructiva o de reemplazo (`write_file`, `str_replace`).
  - Comando interactivo `/undo` en el REPL de `yunta` para revertir al estado inmediatamente anterior y eliminar archivos creados accidentalmente.
- **E14 — Dashboard de Retorno de Inversión y Eficiencia Económica (`/roi`)**:
  - Comando `/roi` que despliega métricas visuales consolidadas: porcentaje de acierto de caché, tokens cacheados, tokens evitados frente a chats crudos y estimación de ahorro monetario en USD.
- **Suite de Pruebas Automatizadas**:
  - Pruebas unitarias para conmutación por fallback ante 429, streaming de razonamiento, checkpoints y restauración vía `/undo`, y cálculo de métricas ROI (total: 75 tests 100% pasando).

---

## [1.0.5] — 2026-09-07

### Agregado
- **Compactación semántica de salidas de terminal (E12)** (`yunta/tools/bash.py`):
  - Función `_compact_output` que previene la inflación innecesaria de contexto en turnos largos:
    - En ejecuciones exitosas de `pytest`, retiene únicamente los encabezados y la línea de resumen final (ej. `=== 70 passed in ... ===`), eliminando decenas de líneas redundantes y ahorrando hasta un 95% de tokens de contexto.
    - En comandos largos exitosos (> 30 líneas), preserva el inicio y final del log intercalando un resumen explícito de líneas omitidas.
    - En comandos con fallo, preserva las partes iniciales y el bloque de traceback/error final para diagnóstico preciso.
  - Aumento de timeout de comandos bash de 30s a 60s en `yunta/tools/bash.py` para prevenir falsos timeouts en entornos con alta carga de CPU en Windows.
- **Directiva de eficiencia de pruebas en el System Prompt** (`yunta/cli.py`):
  - Regla explícita para que el agente ejecute pruebas focalizadas (`pytest tests/test_modulo.py`) durante la iteración activa, reservando la suite completa para la certificación final.
- **Tests unitarios** (`tests/test_tools.py`):
  - Nuevo test `test_bash_compact_output` verificando la compresión de pytest y comandos extensos. Suite total: 70 tests al 100% verde.

---

## [1.0.4] — 2026-09-07

### Agregado
- **Comando de Ideación y Scaffolding SDD (`yunta init` / `/init`)** (`yunta/init.py`, `yunta/cli.py`):
  - Nuevo módulo `yunta/init.py` para inicializar cualquier idea desde cero guiada por Spec-Driven Development (SDD).
  - Generación automática de los 3 artefactos maestros fundacionales en el directorio destino:
    - `SPEC.md`: Especificación formal de la idea (visión, problema, actores, casos de uso del MVP, arquitectura, flujos de datos y anti-alcance).
    - `PLAN.md`: Hoja de ruta iterativa estructurada por fases verificables (Fase 1: Mínimo Núcleo Viable con criterio de aceptación TDD).
    - `AGENTS.md`: Manual de convivencia y guardrails para cualquier agente de IA (stack, comandos de ejecución/tests y reglas inviolables).
  - Integración en CLI: `yunta init [nombre_o_idea]` para ejecutar la inicialización de forma directa y offline sin requerir credenciales ni modelos configurados.
  - Integración en REPL: comando interactivo `/init [idea]` para inicializar proyectos desde la sesión de terminal activa.
  - Ejecución de comando único (single-shot): `yunta "instrucción"` para despachar tareas directas sin entrar al REPL interactivo.
- **Tests unitarios** (`tests/test_init.py`):
  - Cobertura completa de generación de artefactos, respeto a archivos existentes, asignación de nombre por defecto y despacho CLI (`main()`). 4 nuevos tests (69 tests en total al 100% verde).

---

## [1.0.3] — 2026-09-07

### Agregado
- **Indicador de actividad y estado en tiempo real (Spinner / Activity Status)** (`yunta/agent.py`):
  - Clase auxiliar `Spinner` ultra-liviana implementada únicamente con la biblioteca estándar (`threading`, `time`, `sys`).
  - Animación con caracteres Unicode (`⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏`) y contador de tiempo transcurrido en segundos.
  - Salvaguarda `sys.stdout.isatty()` para ejecutarse exclusivamente en terminales interactivas sin alterar entornos no interactivos ni ejecuciones de pruebas.
  - Integración en `_loop()` y `_stream_text()`: inicio antes de `self.provider.send()` con el mensaje `'Pensando...'` y detención limpia al recibir el primer delta de texto o al finalizar la llamada.
  - Telemetría de duración de herramientas en `_execute_tool()`: medición con `time.time()` e impresión del tiempo transcurrido (`[tool] {name} completado en {elapsed:.2f}s` o `falló en ...` si ocurre una excepción).
- **Tests unitarios** (`tests/test_agent.py`):
  - `test_spinner_start_and_stop`: valida que `Spinner` arranca y se detiene de forma limpia, liberando el hilo sin dejar colgadas ejecuciones ni lanzar excepciones.

### Verificación
- `pytest` → 65 passed (100% verde).
- Compilación de todos los archivos Python verificada.

---

## [1.0.2] — 2026-09-07

### Agregado
- **Lanzamiento Oficial en PyPI**: Publicación del paquete en el registro global de Python como [`yunta-harness`](https://pypi.org/project/yunta-harness/) (instalable con `pip install yunta-harness`).
- **Empaquetado y Publicación en PyPI (E4)**: Metadatos completos en `pyproject.toml` bajo el nombre `yunta-harness` (con comando CLI `yunta`), pipeline de publicación automatizada en `.github/workflows/publish.yml` y guías bilingües de release en `docs/pypi_release.md` y `docs/pypi_release_en.md`.
- **Gobernanza del Backlog (Regla Inviolable 6 en AGENTS.md)**: Formalizada la regla de soberanía de especificaciones: los archivos de planificación y backlog (`docs/PLAN.md`) son estrictamente de solo lectura durante tareas de desarrollo; el agente nunca debe auto-modificar el backlog ni alterar requerimientos sin instrucción humana explícita.
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
