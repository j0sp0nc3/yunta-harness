# Plan — yunta

Plan de la iniciativa y su estado. Se comparte junto con el código para que
cualquier persona, IDE o modelo sepa hacia dónde va el proyecto y qué falta.

Estado actual: **v1.1.0 — Backlog v2 Cerrado al 100%** (fases 1-8, backlog fundacional y roadmap E1-E8, E10, E12 completados). Actualizar este archivo al
cambiar de fase, junto con `CHANGELOG.md`.

## Roadmap de evolución (post-backlog)

| # | Item | Estado |
|---|------|--------|
| E1 | CI con GitHub Actions (tests Python 3.11-3.13 en cada push/PR) | ✅ v1.0.0 |
| E2 | Congelar API pública (superficie estable en `yunta/__init__.py`) | ✅ v1.0.0 |
| E3 | Matriz de proveedores (`docs/PROVEEDORES.md` + `scripts/prueba_proveedor.py`) | ✅ v1.0.0 — GLM y Gemini verificados; resto pendiente comunitario |
| E4 | Publicación en PyPI (`pip install yunta-harness`) | ✅ v1.0.2 — empaquetado como `yunta-harness`, workflow `.github/workflows/publish.yml` y guía `docs/pypi_release.md` |
| E5 | Métricas livianas de eficiencia de recursos (`Usage` in-memory, telemetría de herramientas y ahorro frente a chat crudo) | ✅ v1.0.1 — in-memory en `api.py`/`agent.py`, `/tokens` y `/metrics` enriquecidos, 5 tests unitarios |
| E6 | Guardrail ontológico y frontera de ejecución (harness vs. runtime) | ✅ v1.0.1 — `SYSTEM_PROMPT` blindado, Paso 0 en quickstart, plantilla `AGENTS.md` y test de regresión |
| E7 | Modularización y jerarquía del System Prompt (separación de prompt base + override global `~/.yunta/system_prompt.md`) | ✅ v1.0.2 — implementado vía Dogfooding autónomo con Yunta |
| E8 | Indicador de actividad y estado en tiempo real (`Spinner` interactivo y telemetría de duración de tools) | ✅ v1.0.3 — implementado vía Dogfooding autónomo con Yunta |
| E9 | Cascada de respaldo de modelos (`ModelFallbackRouter` ante 429/503/cuota agotada) | ✅ v1.0.6 |
| E10 | Bucle TDD/SDD nativo con contrato formal de especificación (`yunta init` / `/init`) | ✅ v1.0.4 — scaffolding de ideas y ciclo de vida de proyectos SDD |
| E11 | Streaming de tokens de pensamiento (`Reasoning`) y pre-notificación de herramientas | ✅ v1.0.6 |
| E12 | Compactación semántica de salidas verbosas de terminal (reducción de tokens en tests/builds) | ✅ v1.0.5 — compactación en `bash.py` y timeout de 60s |
| E13 | Micro-checkpoints por tool-call e historial de restauración (`/undo` en memoria) | ✅ v1.0.6 |
| E14 | Dashboard de ROI económico y tokens evitados (`/roi`) | ✅ v1.0.6 |

---

## Objetivo de la iniciativa

Un harness de agente de código minimalista, independiente de cualquier ejemplo
o proveedor, pensado para **compartirse entre equipos, IDEs y modelos
distintos**: cada quien conecta su propio modelo vía variables de entorno y
trabaja con el mismo harness.

## Decisiones fundacionales (cerradas)

| Decisión | Elección | Motivo |
|---|---|---|
| Lenguaje | Python 3.11+ | Alcance multi-IDE/multi-modelo, ecosistema |
| Acceso a modelos | LiteLLM | 100+ proveedores con una sola interfaz, tool calling unificado, validado en producción |
| Alcance v1 | Núcleo mínimo | Loop + tools + permisos + compactación; nada más |
| Estilo | ~500 líneas, comentarios mínimos | Legibilidad y facilidad de adopción |
| Nombre | yunta | Pareja de bueyes que trabaja junta — tú y el agente, sin importar el modelo |

## Fases

| # | Fase | Estado |
|---|------|--------|
| 1 | Tipos neutrales (`api.py`) | ✅ v0.1.0 |
| 2 | Provider agnóstico vía LiteLLM (`provider.py`) | ✅ v0.1.0 |
| 3 | Agent loop con max_turns y reintento de tools (`agent.py`) | ✅ v0.1.0 |
| 4 | Tools con registry por decorador + aprobación (`tools/`) | ✅ v0.1.0 |
| 5 | Compactación sliding window (`compact.py`) | ✅ v0.1.0 |
| 6 | REPL + README + verificación | ✅ v0.1.0 |
| 7 | Validación multi-proveedor | ✅ v0.1.1 — 4 tests: traducción openai, mismo core anthropic, endpoint custom (Ollama/vLLM/OpenRouter), error claro sin `LLM_MODEL`. Nota: validado hasta la capa de traducción; falta smoke con API real (requiere credenciales) |
| 8 | Difusión: empaquetar y compartir con otros IDEs/equipos | ✓ v0.7.0 — publicado en github.com/j0sp0nc3/yunta-harness. **Validado en ZCode + GLM-4.7** ✓ y en **Antigravity + Gemini 3.6 Flash** ✓ |

## Backlog (candidatos, no comprometidos)

- ~~Diff unificado en la aprobación de `write_file`~~ ✅ v0.2.0
- ~~Carga de contexto de proyecto estilo `AGENTS.md` en el system prompt~~ ✅ v0.2.0
- ~~Suite de tests con pytest~~ ✅ v0.2.0 (18 tests: provider, agent loop, tools, compactación)
- ~~Auto-feedback del harness (lecciones entre sesiones)~~ ✅ v0.3.0 (`.yunta/learnings.md` + guardas de honestidad)
- ~~Memoria persistente entre sesiones~~ ✅ v0.5.0 (tools `remember`/`recall` en `.yunta/memory.json`, vía dogfooding)
- ~~Subagentes con contexto propio~~ ✅ v0.6.0 (`delegate_research` read-only, vía dogfooding incluyendo primer cambio al core)
- ~~Streaming de respuestas~~ ✓ v0.7.0
- ~~Soporte MCP~~ ✓ v0.8.0
- ~~Edición quirúrgica str_replace (Dogfooding Gemini)~~ ✓ v0.9.0
- ~~Interrupción limpia de turnos (Ctrl+C / KeyboardInterrupt)~~ – v0.10.0
- ~~Prompt Caching agnóstico al LLM (Anthropic/OpenAI/DeepSeek/Gemini)~~ – v0.11.0
- ~~Métricas livianas de eficiencia de recursos~~ ✅ v1.0.1 (in-memory en `yunta/api.py`, comandos `/tokens` y `/metrics` en `yunta/cli.py`, 5 tests en `tests/test_metrics.py`)
- ~~Workflow de proyectos y guardrail ontológico~~ ✅ v1.0.1 (guardrail en `yunta/cli.py`, Paso 0 en `docs/quickstart.md`, plantilla `AGENTS.md` y test en `tests/test_agent.py`)
- ~~Modularización del System Prompt~~ ✅ v1.0.2 (implementado autónomamente por Yunta vía Dogfooding)
- ~~Indicador de actividad y estado en tiempo real (Spinner y cronómetro de herramientas)~~ ✅ v1.0.3 (implementado vía Dogfooding autónomo con Yunta)
- ~~Cascada de respaldo inteligente de modelos (Model Fallback Router)~~ ✅ v1.0.6 (conmutación automática transparente entre lista priorizada de modelos cuando el principal retorna 429 (límite de cuota/rate limit) o 503 (saturación), sin abortar la sesión ni perder el contexto de la tarea acumulado.
- ~~Bucle TDD/SDD con Contrato Inviolable (`yunta init` / `/init`)~~ ✅ v1.0.4 (scaffolding automático de SPEC.md, PLAN.md y AGENTS.md para iterar ideas desde cero)
- ~~Streaming de tokens de razonamiento (`Reasoning/Thinking`) y pre-notificación de tools~~ ✅ v1.0.6 (visualización en vivo y atenuada de la cadena de pensamiento antes de emitir texto, y aviso previo al arranque de herramientas de larga duración.
- ~~Compactación semántica de salidas de terminal~~ ✅ v1.0.5 (compresión en `yunta/tools/bash.py` y regla de tests focalizados en system prompt)
- ~~Micro-checkpoints por tool call ("Time-Travel Undo")~~ ✅ v1.0.6 (snapshots livianos automáticos antes de cada invocación destructiva (`write_file`, `str_replace`, `bash`), permitiendo comando `/undo` inmediato sin ensuciar el árbol ni el historial de Git del usuario.
- ~~Dashboard de ROI y valor económico (`/roi`)~~ ✅ v1.0.6 (visualización resumida del dinero real ahorrado en APIs gracias al prompt caching, tiempo humano ganado y tokens evitados.



## Prioridades inmediatas (de la auditoría dogfooding v1.0.6 — verificar antes que nada)

- **P1 ✅ (v1.0.7) Ctrl+C durante tool deja `tool_use` huérfano** (`yunta/agent.py:113-142`):
  el handler guarda el mensaje solo si el último es USER (condición nunca
  verdadera ahí) → el proveedor rechaza el request siguiente y la sesión muere.
  Fix: append de tool_results de error siempre. Test de regresión primero.
- **P2 ✅ (v1.0.7) `stream_options={"include_usage"}` incondicional** (`yunta/provider.py`):
  endpoints OpenAI-compatibles estrictos (vLLM, LocalAI, gateways) lo rechazan
  con 400. Fix: envío condicional o reintento sin el kwarg ante error.
- **P3 ✅ (v1.0.7) `mcp_clients` sin inicializar antes del dispatch** (`yunta/cli.py`):
  hoy sin NameError alcanzable (returns tempranos lo protegen) pero
  UnboundLocalError latente. Fix: `mcp_clients: list = []` al inicio de main().
- **P4 ✅ (v1.0.7) Compactor activo por defecto en el CLI (`SlidingWindow`)**: SlidingWindow existe y pasa
  tests pero ningún Agent de producción la usa → historial sin límite. (≡ V2-6)
- **P5 ✅ (v1.0.7) `read_file` con cap de tamaño y soporte offset/limit**
  (≡ V2-6). Un archivo grande entra entero y se re-paga cada turno.

Orden recomendado: P1 → P3 → P2 (bugs reales primero, TDD), luego P4/P5.
Inconsistencias docs detectadas en la misma auditoría (README sin /undo y
/roi, AGENTS.md desactualizado en env vars, orden CHANGELOG) se corrigen en
la misma ronda.


## BUGS P6-P9 — defectos del harness detectados en dogfooding (RESOLVER, no evolutivos)

Origen: fallos reales observados en las rondas de dogfooding (archivos
truncados, sesiones perdidas por cuota, specs grandes inmanejables).
Un harness que pierde trabajo o deja archivos a medias no cumple su función.

- **P6 🔴 write_file no atómico ni validado**: una sesión que muere a mitad
  de escritura deja archivos truncados (ocurrió 3 veces). Fix: escribir a
  .tmp, validar (py_compile para .py, balance de comillas/paréntesis en
  general), confirmar bytes, y rename solo si todo pasó. Archivo original
  intacto ante fallo. *Estado: ✅ v1.2.1 (6 tests)*
- **P7 🔴 sin degradación progresiva ante cuota**: RateLimitError pierde la
  sesión completa incluida la tarea pendiente (ocurrió 2 veces). Fix: al
  capturar RateLimit/Authentication persistir .yunta/estado-de-tarea.md
  (hecho/pendiente/próximos pasos) + lección de feedback, cerrar ordenado.
  *Estado: ✅ v1.2.1 (5 tests)*
- **P8 🟡 presupuesto de sesión invisible**: sesiones quemaron 200-270k
  tokens sin aviso. Fix: umbrales 70%/90% del presupuesto (extensión de
  TokenBudgetCompactor): aviso y cierre ordenado (P7) respectivamente.
  *Estado: ✅ v1.2.1 (6 tests)*
- **P9 🟡 specs de >2 archivos inmanejables en un loop**: 2 sesiones
  descontroladas. Fix: descomposición en subtareas de 1-2 archivos con
  subagente por lote (contexto limpio por subtarea). *Estado: ⬜*

Orden: P6 → P7 → P8 → P9.


## BUGS W1-W5 — casos de borde del binario CLI (feedback de uso real en Windows/IDEs)

Regla fundamental del feedback: yunta es un CLI, no una biblioteca — toda
interacción externa vía `yunta "instrucción"`, nunca `import yunta`.

- **W1 UTF-8 en consolas Windows**: crash UnicodeEncodeError con emojis en
  PowerShell/CMD (cp1252). Fix: reconfigure de stdout/stderr a UTF-8 al
  arranque del CLI. *Estado: ⬜* (verificar: partial de v1.0.7 cubre stdout
  del REPL; faltan rutas del single-shot). *Estado: ⬜*
- **W2 Modo headless `--headless/-y`**: la CLI se bloquea esperando y/n en
  pipelines/scripts. Fix: flag de auto-aprobación + salida determinista. *Estado: ✅ preexistente (`--yes/-y` en single-shot, confirmado en uso)*
- **W3 `&&` no válido en PowerShell**: normalizar `&&`→`;` al detectar
  PowerShell en bash tool. *Estado: ✅ v1.2.2 vía yunta CLI single-shot (detección PSModulePath, 3 tests)*
- **W4 startup tax en cada invocación CLI**: flag `--light` que omite
  contexto extenso (AGENTS/SPEC/PLAN) para tareas simples. *Estado: ⬜*
  (parcial: V3-8 ya lo mide)
- **W5 aislamiento de rutas (workspace boundary)**: validar que toda ruta
  de tools resuelva dentro de cwd. *Estado: ⬜* (parcial: blocklist cubre
  rm -rf fuera de cwd)

## Backlog v2 (Estado post-sesión 2026-09-08)

### ✅ Completado en la sesión de hoy (v1.0.6 & v1.0.7):
- **E9 — Cascada de Respaldo (`ModelFallbackRouter`)**: Conmutación automática en caliente ante 429/503/cuotas (`✅ v1.0.6`).
- **E11 — Streaming de Pensamiento & Pre-notificación**: Extracción de tokens `reasoning_content` y aviso visual de tools (`✅ v1.0.6`).
- **E13 — Micro-Checkpoints & Time-Travel (`/undo`)**: Snapshots en memoria antes de editar y rollback instantáneo (`✅ v1.0.6`).
- **E14 — Dashboard de Retorno Económico (`/roi`)**: Cálculo de tokens cacheados, evitados y ahorro monetario en USD (`✅ v1.0.6`).
- **P1 — Prevención de `tool_use` huérfano ante `Ctrl+C`**: Cierre garantizado con `TOOL_RESULT` cancelado (`✅ v1.0.7`).
- **P2 — Resiliencia ante `stream_options`**: Reintento transparente si el endpoint compatible lo rechaza (`✅ v1.0.7`).
- **P3 — Inicialización temprana de `mcp_clients`**: Eliminación del riesgo de `UnboundLocalError` (`✅ v1.0.7`).
- **P4 / V2-6 — Compactador `SlidingWindow` en CLI**: Acotamiento automático del historial (default: 40 msgs) (`✅ v1.0.7`).
- **P5 / V2-6 — Cap de 2.000 líneas en `read_file`**: Paginación con `offset` y `limit` (`✅ v1.0.7`).
- **V2-3 — Blindaje UTF-8 (cp1252)**: Manejo de errores de codificación en herramientas de archivo para Windows (`✅ v1.0.7`).
- **CLI Discovery**: Flags `yunta --help`, `-h`, `--version` sin requerir API key, y guarda contra comandos slash erróneos en REPL (`✅ v1.0.7`).
- **Diagnóstico de Endpoints & JWT**: Script `scripts/check_endpoints.py` con validación de expiración de tokens y mapeo de errores HTTP (`✅ v1.0.7`).

---

### ✅ Iniciativas de Backlog v2 (100% Completadas):

- **V2-1 ✅ (v1.0.9) Modo gobernanza (`yunta check`)**: Comando CLI ligero y determinista ($0 en tokens) que audita un repositorio contra su `SPEC.md`, `PLAN.md` y `AGENTS.md`, estado de Git y suite de tests. Soporta salida `--json` para IDEs externos y CI/CD.
- **V2-2 ✅ (v1.0.9) Sesiones resumibles (`yunta --resume` / `-r`)**: Persistencia atómica de mensajes y telemetría en `.yunta/session_state.json` con auto-guardado continuo para tolerar interrupciones por cuota o cortes de red.
- **V2-4 ✅ (v1.0.8) Tool `tree` / `list_dir` con presupuesto de tokens**: Herramienta nativa para inspección estructurada del árbol de directorios (respetando `.gitignore`, reportando tamaños y omitiendo binarios) para que los agentes exploren repositorios sin gastar turnos leyendo archivos ciegamente.
- **V2-7 ✅ (v1.0.8) Regla canónica de interoperabilidad en `AGENTS.md`**: Plantilla formal de regla vinculante para que IDEs externos deleguen consultas y tareas en `yunta` CLI antes de generar código con sus propios LLMs.
- **V2-5 ✅ (v1.1.0) Modo servidor MCP de Yunta (`yunta serve-mcp`, `mcp`)**: Exposición nativa del catálogo de herramientas de Yunta como servidor MCP stdio (JSON-RPC 2.0) compatible con Claude Desktop, Cursor y Windsurf.


## Backlog v3 (mejoras comprobables, basadas en experiencias del ecosistema — 2026-09-09)

Fuentes: paper OpenDev (arXiv 2603.05344), benchmark de costos de harness
(The New Stack), Addy Osmani "Agent Harness Engineering", codecentric
(loops sin verificación). Cada item indica cómo verificarlo.

- ~~**V3-1 Detección de doom-loops** ✅ v1.2.0~~ ~~** (OpenDev): fingerprint de (tool+args) en
  ventana de 20 llamadas; 3 repeticiones → advertencia, 5 → pausa con
  aprobación. Reemplaza contadores toscos. *Verificar: test con provider
  falso repitiendo la misma llamada N veces; assert de advertencia y pausa.*
- ~~**V3-2 Permisos persistentes** ✅ v1.2.0~~ ~~ por sesión** (OpenDev, capa 3): 'siempre' al
  aprobar un comando/patrón evita fatiga de aprobación sin ceder control.
  *Verificar: test de confirm callback que registra que no se re-pregunta
  tras 'siempre'; /permissions para listar y revocar.*
- ~~**V3-3 Offloading de salidas largas** ✅ v1.2.0~~ ~~ a scratch files** (OpenDev): resultados
  >8.000 chars van a .yunta/scratch/ con preview de 500 chars al contexto.
  *Verificar: test con tool que devuelve 10k chars; assert de archivo scratch
  creado y preview en tool_result; métrica de tokens en /roi.*
- ~~**V3-4 Compactación por etapas** ✅ v1.2.0~~ ~~ basada en tokens** (OpenDev): aviso al 70%
  del presupuesto, enmascaramiento 80%, pruning 85%, resumen LLM solo al 99%.
  Hoy SlidingWindow es por conteo de mensajes. *Verificar: tests por umbral
  con historial sintético; /context muestra % del presupuesto.*
- ~~**V3-5 Recordatorios como role:user** ✅ v1.2.0~~ ~~ en punto de decisión** (OpenDev):
  re-inyectar reglas críticas (verificar antes de declarar, no repetir
  lecturas) tras ~15 tool calls. *Verificar: test de que el mensaje usuario
  aparece en el payload tras N calls.*
- ~~**V3-6 Recuperación de errores clasificada** ✅ v1.2.0~~ ~~**: 6 categorías con plantilla
  accionable ('re-lee el archivo' vs 'reintenta' genérico). *Verificar: test
  unitario de clasificador; assert de plantilla en tool_result.*
- ~~**V3-7 Blocklist de patrones peligrosos** ✅ v1.2.0~~ ~~ en bash** (OpenDev, capa 4):
  rm -rf fuera de cwd, git push --force, curl | sh, etc. *Verificar: test
  por patrón bloqueado con mensaje claro; documentado en README.*
- ~~**V3-8 Presupuesto de arranque medible** ✅ v1.2.0~~ ~~** (benchmark de costos): medir y
  reportar el 'startup tax' (prompt+schemas por turno) en /metrics; objetivo
  <5.000 tokens. El estudio muestra R²=0.99 entre este suelo y el costo total.
  *Verificar: test que calcula tokens del payload inicial; badge en README.*
- ~~**V3-9 Aislamiento en git worktree** ✅ v1.2.0~~ ~~ para tareas destructivas**: /sandbox
  que crea worktree desechable y merge opcional al terminar. *Verificar:
  test de creación/limpieza de worktree; smoke end-to-end.*

Prioridad sugerida por impacto/esfuerzo: V3-1, V3-2, V3-7 (seguridad y
control, esfuerzo bajo) → V3-8, V3-3 (medición y eficiencia) → V3-4, V3-6
→ V3-5 → V3-9.


## Oleada 1 — especificación ejecutable (retomable sin contexto previo)

Ejecutar de menor a mayor costo, un item por rama o rama única
`feature/oleada-1`. Cada item: TDD (test primero), suite completa verde,
entrada en CHANGELOG. Cualquier agente/IDE puede retomar donde esté.

### O1-a) V3-12 `yunta ide-init` (~30 líneas) — Estado: ✅ v1.2.0
- Comando `yunta ide-init` (despacho en cli.py igual que serve-mcp): crea
  `.vscode/mcp.json` con {"servers":{"yunta":{"command":"yunta","args":["serve-mcp"]}}}
  y `.vscode/tasks.json` con tasks 'yunta: run', 'yunta: check', 'yunta: init'
  (shell, command 'yunta' / 'yunta check' / 'yunta init'). No sobrescribir
  existentes: merge o aviso. Tests: creación, no-sobrescritura, JSON válido.

### O1-b) V3-7 blocklist bash (~50 líneas) — Estado: ✅ v1.2.0
- En yunta/tools/bash.py: patrones peligrosos rechazados ANTES de ejecutar:
  rm -rf con ruta fuera de cwd o /, 'curl ...| sh', 'wget ...| sh',
  'git push --force' (salvo YUNTA_ALLOW_FORCE=1), mkfs, dd of=/dev/.
  Error claro y accionable ('patrón bloqueado por seguridad: ...').
  Config: YUNTA_BLOCKLIST_EXTRA=path-a-archivo-con-patrones-regex.
  Tests: un test por patrón + uno de allow-force opcional.

### O1-c) V3-2 permisos persistentes (~80 líneas) — Estado: ✅ v1.2.0
- En agent.py/_approve: respuesta 's' o 'siempre' → registrar patrón
  (tool + primer token del comando o path) en dict en memoria de sesión.
  Consulta del patrón antes de confirmar. Comando /permissions: lista,
  /permissions clear revoca. NO persistir a disco en v1 (solo sesión).
  Tests: tras 'siempre' no se re-pregunta mismo patrón; patrón distinto sí;
  /permissions clear restaura pregunta.

### O1-d) V3-8 startup tax medible (~40 líneas) — Estado: ✅ v1.2.0
- En provider.py: contar tokens aproximados del primer payload
  (system + schemas) — litellm token_counter o len//4 como fallback.
  Exponer provider.startup_tax: int. /metrics lo muestra con objetivo <5000.
  Test: provider falso con payload conocido → valor >0 y estable.

### OLEADA 2 (siguiente): V3-10 aprobaciones vía MCP → V3-1 doom-loop.
### OLEADA 3: V3-11 serve-json → V3-13 extensión VS Code (repo aparte).

## Reglas que gobiernan el plan

Ver `AGENTS.md` (reglas inviolables) y la sección "Convenciones" de
`CHANGELOG.md`. Resumen: sin SDKs fuera de `provider.py`, sin proveedor por
defecto, sin frameworks, todo cambio registrado en `CHANGELOG.md`.
