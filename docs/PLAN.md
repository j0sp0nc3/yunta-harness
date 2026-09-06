# Plan — yunta

Plan de la iniciativa y su estado. Se comparte junto con el código para que
cualquier persona, IDE o modelo sepa hacia dónde va el proyecto y qué falta.

Estado actual: **Fase 1-6 completadas (v0.1.0)**. Actualizar este archivo al
cambiar de fase, junto con `CHANGELOG.md`.

---

## Objetivo de la iniciativa

Un harness de agente de código minimalista, independiente de cualquier ejemplo
o proveedor, pensado para **compartirse entre equipos, IDEs y modelos
distintos**: cada quien conecta su propio modelo vía variables de entorno y
trabaja con el mismo harness.

## Decisiones fundacionales (cerradas)

| Decisión | Elección | Motivo |
|---|---|---|
| Lenguaje | Python 3.10+ | Alcance multi-IDE/multi-modelo, ecosistema |
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
| 8 | Difusión: empaquetar y compartir con otros IDEs/equipos | 🔨 en progreso — **publicado en https://github.com/j0sp0nc3/yunta-harness** (público, v0.2.0). Pendiente: probar en ZCode y Antigravity con modelos reales |

## Backlog (candidatos, no comprometidos)

- ~~Diff unificado en la aprobación de `write_file`~~ ✅ v0.2.0
- ~~Carga de contexto de proyecto estilo `AGENTS.md` en el system prompt~~ ✅ v0.2.0
- ~~Suite de tests con pytest~~ ✅ v0.2.0 (18 tests: provider, agent loop, tools, compactación)
- Memoria persistente entre sesiones.
- Subagentes con contexto propio.
- Streaming de respuestas.
- Soporte MCP.

## Reglas que gobiernan el plan

Ver `AGENTS.md` (reglas inviolables) y la sección "Convenciones" de
`CHANGELOG.md`. Resumen: sin SDKs fuera de `provider.py`, sin proveedor por
defecto, sin frameworks, todo cambio registrado en `CHANGELOG.md`.
