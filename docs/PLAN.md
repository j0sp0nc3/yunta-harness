# Plan — yunta

Plan de la iniciativa y su estado. Se comparte junto con el código para que
cualquier persona, IDE o modelo sepa hacia dónde va el proyecto y qué falta.

Estado actual: **v1.0.4 — Publicado en PyPI** (fases 1-8, backlog fundacional y roadmap E1-E8, E10 completados). Actualizar este archivo al
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
| E9 | Cascada de respaldo de modelos (`ModelFallbackRouter` ante 429/503/cuota agotada) | ⏳ Pendiente |
| E10 | Bucle TDD/SDD nativo con contrato formal de especificación (`yunta init` / `/init`) | ✅ v1.0.4 — scaffolding de ideas y ciclo de vida de proyectos SDD |
| E11 | Streaming de tokens de pensamiento (`Reasoning`) y pre-notificación de herramientas | ⏳ Pendiente |
| E12 | Compactación semántica de salidas verbosas de terminal (reducción de tokens en tests/builds) | ⏳ Pendiente |
| E13 | Micro-checkpoints por tool-call e historial de restauración (`/undo` en memoria) | ⏳ Pendiente |
| E14 | Dashboard de ROI económico y tokens evitados (`/roi`) | ⏳ Pendiente |

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
- **Cascada de respaldo inteligente de modelos (Model Fallback Router)**: Conmutación automática transparente entre lista priorizada de modelos cuando el principal retorna 429 (límite de cuota/rate limit) o 503 (saturación), sin abortar la sesión ni perder el contexto de la tarea acumulado.
- ~~Bucle TDD/SDD con Contrato Inviolable (`yunta init` / `/init`)~~ ✅ v1.0.4 (scaffolding automático de SPEC.md, PLAN.md y AGENTS.md para iterar ideas desde cero)
- **Streaming de tokens de razonamiento (`Reasoning/Thinking`) y pre-notificación de tools**: Visualización en vivo y atenuada de la cadena de pensamiento antes de emitir texto, y aviso previo al arranque de herramientas de larga duración.
- **Compactación semántica de salidas de terminal**: Detección y compresión inteligente de logs extensos (ej. suites de pytest o builds grandes), reteniendo solo resúmenes o fallos para ahorrar entre 60% y 80% de tokens de contexto.
- **Micro-checkpoints por tool call ("Time-Travel Undo")**: Snapshots livianos automáticos antes de cada invocación destructiva (`write_file`, `str_replace`, `bash`), permitiendo comando `/undo` inmediato sin ensuciar el árbol ni el historial de Git del usuario.
- **Dashboard de ROI y valor económico (`/roi`)**: Visualización resumida del dinero real ahorrado en APIs gracias al prompt caching, tiempo humano ganado y tokens evitados.

## Reglas que gobiernan el plan

Ver `AGENTS.md` (reglas inviolables) y la sección "Convenciones" de
`CHANGELOG.md`. Resumen: sin SDKs fuera de `provider.py`, sin proveedor por
defecto, sin frameworks, todo cambio registrado en `CHANGELOG.md`.
