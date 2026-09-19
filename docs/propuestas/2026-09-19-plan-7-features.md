# Plan de Implementación — Blindaje + 7 Features Propuestas para Yunta

> Documento de propuesta (no forma parte del backlog oficial `docs/PLAN.md`).
> Generado el 2026-09-19 tras análisis de mercado + exploración exhaustiva del código.
> Requiere decisión humana antes de mover cualquier ítem al backlog oficial o empezar a implementar.
>
> **Orden ajustado 2026-09-19**: antes de construir features nuevas, primero
> se blinda lo que ya existe. Motivo: se encontraron un bug de producción
> silencioso y código huérfano durante la exploración — construir 7 features
> nuevas sobre cimientos con huecos conocidos sería repetir el mismo patrón.

## Contexto

Yunta es un harness maduro (264+ tests, v2.7.5) pero todo su diseño asume un
proceso único, una máquina, sin memoria de equipo ni portabilidad entre
harnesses/IDEs. Las 7 features de la Parte B cierran ese hueco estructural y
apuntan a diferenciación de mercado (portabilidad de sesión, adopción
brownfield, gobernanza económica de modelos). Pero primero, la Parte A cierra
las grietas ya confirmadas en el código actual.

---

## PARTE A — Fase de Blindaje (hacer primero)

### B1. Fix de `LLM_FAST_MODEL` (bug de producción confirmado)

`yunta/tools/delegate.py:53` (`delegate_research`) llama
`LiteLLMProvider(model=fast_model, system=system_prompt)`, pero
`LiteLLMProvider.__init__` (`yunta/provider.py:25`) solo acepta `system=`.
La llamada siempre lanza `TypeError`, cae al `except`, y reutiliza el
provider compartido — **`LLM_FAST_MODEL` nunca ha funcionado**, pese a estar
documentado como feature desde v2.0. Verificado por grep global: es el
**único** lugar del repo que llama `LiteLLMProvider(model=...)` — no hay
más instancias del mismo patrón de error.

- Agregar `model: str | None = None` al `__init__` de `LiteLLMProvider`; si
  viene, fija `self._models = [model]` sin leer `LLM_MODELS`/`LLM_MODEL` de
  entorno. 100% retrocompatible (parámetro opcional, default `None`).
- En `delegate.py`, mantener el `except` como red de seguridad pero
  imprimir la causa (`print(f"[delegate] fast model falló: {e}")`) en vez
  de silenciarla del todo — para que un futuro bug similar no vuelva a
  pasar 6 versiones inadvertido.
- Tests: `test_lite_llm_provider_model_override_ignores_env` (setea
  `LLM_MODEL=a`, construye con `model="b"`, verifica `.model()=="b"`);
  `test_delegate_research_uses_fast_model_when_set` (monkeypatch
  `LLM_FAST_MODEL`, confirmar que el provider interno reporta ese modelo).

### B2. Código huérfano — `yunta/budget.py`

Confirmado por grep: `SessionBudget`/`check_budget` **no se importan en
ningún lugar** salvo su propio archivo de test (`tests/test_session_budget.py`).
`cli.py` nunca importa `budget` (ver lista de imports verificada). Además,
comparando ambos módulos: `compact.py::TokenBudgetCompactor` (sí importado
en `cli.py:9`, sí usado en producción) **ya implementa el mismo propósito**
con 4 umbrales (70/80/85/99%) — de hecho `docs/PLAN.md` marca el ítem P8
como "✅ v1.2.1 — extensión de TokenBudgetCompactor", confirmando que la
funcionalidad real se construyó ahí y `budget.py` quedó como prototipo
abandonado sin borrar.

- **Acción recomendada: eliminar `yunta/budget.py` y `tests/test_session_budget.py`.**
  Mantenerlo y "wirearlo" duplicaría lógica de umbrales que ya existe y
  funciona en `compact.py`, violando la regla de minimalismo de
  `AGENTS.md`. Si en el futuro se quiere un corte duro adicional (parar la
  sesión, no solo compactar mensajes), se diseña como extensión explícita
  de `TokenBudgetCompactor`, no como un segundo sistema paralelo.
- Registrar la eliminación en `CHANGELOG.md` con la justificación (código
  muerto, funcionalidad ya cubierta por `TokenBudgetCompactor`).

### B3. Colisión de timestamp en `create_sandbox` (bug latente, no solo para Feature 7)

`yunta/sandbox.py:16` usa `ts = int(time.time())` para nombrar el
worktree/rama. Dos llamadas en el mismo segundo (posible incluso hoy, sin
esperar a la feature de best-of-N — ej. un usuario que hace `/sandbox` dos
veces seguidas tras un `discard` rápido) generan el mismo nombre → colisión
de carpeta/rama.

- Cambiar a `time.time_ns()` o añadir sufijo `uuid.uuid4().hex[:6]`.
- Test: 5 llamadas a `create_sandbox()` en la misma ejecución → 5
  directorios y ramas distintas (hoy fallaría con `ts` en segundos si se
  ejecutan rápido).

### B4. Test de "wiring" para rutas de subagentes (prevención de esta clase de bug)

La causa raíz de B1 es que los tests existentes de `delegate_research`
usan mocks a un nivel tan bajo que nunca ejercitan la construcción real del
`LiteLLMProvider` con los kwargs reales — por eso 264 tests en verde no
detectaron un bug de producción. Se agrega una categoría de test explícita
que si vuelve a fallar, es una señal clara del mismo patrón:

- `tests/test_wiring_smoke.py`: para cada punto que construye un
  sub-`Agent`/`Provider` (`delegate_research`, `delegate_batch`,
  `delegate_subtask`, `run_chunks`), un test que instancia las clases
  reales (con un `FakeProvider`/env de prueba, sin red) y solo verifica que
  **no lance `TypeError`/`AttributeError`** por firmas desalineadas — no
  vuelve a probar lógica de negocio (eso ya está cubierto), solo la
  integración entre módulos.

**Verificación de la Parte A completa**: `python -m py_compile main.py
yunta/*.py yunta/tools/*.py` → `pytest -q` (debe seguir en 260+ tests
verdes, con 2 menos por B2 y 4-6 más por B1/B3/B4) → entrada en
`CHANGELOG.md` → commit único o por ítem (a decidir).

---

## PARTE B — Las 7 Features (después de la Parte A)

## Orden de implementación (cada fase termina con suite verde + CHANGELOG)

### 1. Protocolo de Portabilidad de Sesión ("Handoff")
La más independiente, máxima prioridad de negocio (resuelve compartir
sesión entre ZCode/Antigravity).

- Nuevo `yunta/handoff.py`: `export_handoff()` / `import_handoff()`
  reutilizando `serialize_messages`/`serialize_usage` de `yunta/session.py`.
- Bundle JSON versionado (`schema_version`) con: `session_id, cwd,
  git_commit, model, messages, usage, session_permissions, active_sandbox`.
- Requiere `to_list()`/`from_list()` en `SessionPermissions`
  (`yunta/agent.py:54-88`).
- Comandos: `yunta handoff export/import <ruta>` + `/handoff` en REPL.
- Límite honesto: solo se puede publicar el schema, no forzar que otro
  harness lo lea — se documenta como estándar abierto candidato.

### 2. Reverse-SDD
Genera `SPEC.md`/`AGENTS.md` candidatos desde código sin specs (abre
adopción brownfield).

- Nuevo `yunta/reverse_sdd.py`, reutiliza
  `adapter_registry.get_adapter(path).get_outline()/.find_symbols()` de
  `yunta/adapters.py` (ya expuesto por `tools/symbols.py`).
- Extraer regex inline de `yunta/governance.py` a constantes de módulo
  (~10 líneas) para que lo generado pase `yunta check` de inmediato.
- Solo escribe `*.candidate`; nunca pisa specs reales sin `--apply`
  explícito y solo si no existen ya (respeta AGENTS.md regla 6).

### 3. Tests de Caracterización (Golden-Master)
Mayor riesgo técnico del roadmap (ejecuta código del repo objetivo).

- Nueva tool `characterize_function` en `yunta/tools/characterize.py`,
  `requires_approval=True`.
- Ejecución **en subproceso aislado con timeout** (nunca in-process) — un
  crash no debe tumbar yunta.
- Alcance MVP: solo funciones Python top-level, filtro heurístico de
  side-effects (`open`, `subprocess`, `requests`, prefijos
  `write_/save_/delete_/send_`).
- Cabecera obligatoria en el test generado: "captura comportamiento
  ACTUAL, no necesariamente correcto".

### 4. Memoria de Equipo
Dos partes:

- **Formato**: migrar `yunta/tools/memory.py` de JSON-array-reescrito a
  **JSONL append-only**, con shim de migración automática desde el
  formato viejo.
- **Transporte**: comando `yunta memory init-sync` que pide confirmación
  explícita antes de tocar `.gitignore` (excepciones para
  `learnings.md`/`memory.jsonl`). Nuevo `yunta/team_memory.py` con
  `dedup_learnings`/`dedup_memory`/`sync_report`.

### 5. Agent Health Score
Reutiliza la convención JSONL de la feature 4.

- Nuevo `yunta/health.py`: `record_snapshot()` a `.yunta/health.jsonl`,
  `aggregate()`.
- Un contador nuevo de una línea en `yunta/agent.py`
  (`self._doom_loop_triggers`), incrementado donde ya se calcula
  `force_prompt`.
- Comando `yunta health` con el mismo estilo visual que `/roi`.

### 6. Enrutamiento Económico Dinámico
Usa `Agent._recent_tool_calls`, que **ya existe** para doom-loop
detection — sin duplicar estado.

- `set_model_override()` en `LiteLLMProvider`.
- `evaluate_triviality()` en `yunta/intent.py` con **regla dura, no
  heurística blanda**: nunca modelo barato si hubo `write_file`/
  `str_replace`/`bash` reciente.
- Nueva env var `LLM_CHEAP_MODEL`.

### 7. Undo como Árbol (Best-of-N)
La más pesada arquitectónicamente. El fix de colisión de `create_sandbox`
que necesitaba ya se resolvió en **B3** (Parte A) — aquí solo se construye
encima.

- **Decisión de alcance explícita**: ejecución **secuencial**, no
  paralela real — `os.chdir()` es global al proceso y N hilos pisándose
  entre sandboxes es una condición de carrera real. Paralelismo real vía
  subprocesos queda fuera de este roadmap (v2 futura).
- Nuevo `yunta/bestof.py`, comando `/bestof <n> <prompt>` **separado**
  del `/sandbox` existente (no arriesgar código que ya funciona).

## Reglas que gobiernan toda la ejecución

- Ninguna fase toca la superficie pública congelada de `yunta/__init__.py`.
- Todo es aditivo (módulos/tools/comandos nuevos).
- Verificación por fase: `python -m py_compile main.py yunta/*.py
  yunta/tools/*.py` → `pytest -q` en verde → entrada en `CHANGELOG.md` →
  commit.
- No se toca `docs/PLAN.md` ni `docs/SPEC.md` directamente (regla 6 de
  AGENTS.md) — este roadmap vive como propuesta separada hasta que un
  humano decida incorporarlo al backlog oficial.

## Estado

✅ Parte A (Blindaje: B1-B4) — commit `bc2e1d8`, `CHANGELOG.md` [2.7.6].
✅ Feature 1 (Handoff) — `CHANGELOG.md` [2.8.0], suite verde (271/271).
✅ Feature 2 (Reverse-SDD) — `CHANGELOG.md` [2.9.0], suite verde (294/294).
✅ Feature 3 (Caracterización/Golden-Master) — `CHANGELOG.md` [2.10.0], suite verde (302/302).
✅ Feature 4 (Memoria de Equipo) — `CHANGELOG.md` [2.11.0], suite verde (313/313).
✅ Feature 5 (Agent Health Score) — `CHANGELOG.md` [2.12.0], suite verde (319/319).
⬜ Features 6-7 — pendientes.
