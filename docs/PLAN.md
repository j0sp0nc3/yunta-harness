# Plan — yunta

Plan de la iniciativa y su estado. Se comparte junto con el código para que
cualquier persona, IDE o modelo sepa hacia dónde va el proyecto y qué falta.

Estado actual: **v1.0.5 — Publicado en PyPI** (fases 1-8, backlog fundacional y roadmap E1-E8, E10, E12 completados). Actualizar este archivo al
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


## Backlog v2 (candidatos, derivados del feedback de Antigravity 2026-09-08)

- **V2-1 Modo gobernanza (`yunta check`)**: comando que audita un repo contra su
  SPEC.md/PLAN.md/AGENTS.md (tests verdes, alcance respetado, fases cerradas)
  sin ejecutar código — permite usar yunta como capa de verificación desde
  cualquier IDE. Origen: feedback híbrido Antigravity (metodología yunta,
  ejecución IDE).
- **V2-2 Sesiones resumibles ante 429/cuota**: snapshot persistente del
  historial + reanudación con resumen automático cuando el proveedor agota
  cuota, en vez de perder la sesión. Complementa el fallback router (E9).
- **V2-3 UTF-8 a prueba de cp1252 en tools de archivo**: write_file,
  str_replace y read_file con encoding explícito y fallback verificado en
  Windows (v1.0.0 cubrió solo stdout).
- **V2-4 Tool tree/list_dir con presupuesto de tokens**: vista estructurada
  del árbol (nombres, tamaños, ignorando binarios) para no leer archivos uno
  a uno — reduce el costo de contexto que el feedback señala.
- **V2-5 Modo servidor (MCP de yunta misma)**: exponer el harness como
  servidor MCP para que IDEs/agents usen sus tools y guardas vía protocolo,
  cerrando el círculo híbrido sin perder aprobación/diff/undo.
- **V2-6 Caps de contexto (de auditoría v1.0.6)**: read_file con límite
  head/tail + compactor activo por defecto en el CLI (mejoras #4/#5 de la
  auditoría dogfooding, aún sin aplicar).

## Reglas que gobiernan el plan

Ver `AGENTS.md` (reglas inviolables) y la sección "Convenciones" de
`CHANGELOG.md`. Resumen: sin SDKs fuera de `provider.py`, sin proveedor por
defecto, sin frameworks, todo cambio registrado en `CHANGELOG.md`.
