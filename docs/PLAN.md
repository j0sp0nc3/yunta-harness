# Plan — yunta

Plan de la iniciativa y su estado. Se comparte junto con el código para que
cualquier persona, IDE o modelo sepa hacia dónde va el proyecto y qué falta.

Estado actual: **v1.0.1 — API pública congelada** (fases 1-8, backlog fundacional y roadmap E1-E3 completados). Actualizar este archivo al
cambiar de fase, junto con `CHANGELOG.md`.

## Roadmap de evolución (post-backlog)

| # | Item | Estado |
|---|------|--------|
| E1 | CI con GitHub Actions (tests Python 3.11-3.13 en cada push/PR) | ✅ v1.0.0 |
| E2 | Congelar API pública (superficie estable en `yunta/__init__.py`) | ✅ v1.0.0 |
| E3 | Matriz de proveedores (`docs/PROVEEDORES.md` + `scripts/prueba_proveedor.py`) | ✅ v1.0.0 — GLM y Gemini verificados; resto pendiente comunitario |
| E4 | Publicación en PyPI (`pip install yunta`) | ⬜ pendiente — último del roadmap: requiere decidir cuenta/nombres de publicación; los endpoints de pago para prueba quedan a discreción del publicador |

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

## Reglas que gobiernan el plan

Ver `AGENTS.md` (reglas inviolables) y la sección "Convenciones" de
`CHANGELOG.md`. Resumen: sin SDKs fuera de `provider.py`, sin proveedor por
defecto, sin frameworks, todo cambio registrado en `CHANGELOG.md`.
