# AGENTS.md — guía para agentes que trabajan en este proyecto

Instrucciones para cualquier agente de código (humano o IA) que modifique **yunta**.

## Qué es este proyecto

Un harness de agente de código para terminal, minimalista (~500 líneas) y
**agnóstico al proveedor del modelo por construcción**. Está pensado para
compartirse entre equipos, IDEs y modelos distintos: cualquier persona o agente
debe poder tomarlo, configurar su propio modelo vía variables de entorno y
trabajar.

## Reglas inviolables

1. **Ninguna importación de SDKs de proveedores** fuera de `yunta/provider.py`.
   El core (`api.py`, `agent.py`, `compact.py`, `tools/`) habla solo en los
   tipos neutrales de `yunta/api.py`.
2. **No introducir proveedores por defecto ni fallbacks ocultos**: si falta
   `LLM_MODEL`, se falla con mensaje claro. El usuario elige el modelo, siempre.
3. **Sin frameworks de agentes** (LangChain, Agents SDK, etc.). El bucle, los
   permisos y el contexto son código propio.
4. **Registro obligatorio**: toda modificación se documenta en `CHANGELOG.md`
   (qué, dónde, por qué) antes de considerar el trabajo terminado.
5. **Mantener minimalismo**: si un cambio agrega más de ~100 líneas, justificar
   por qué no puede hacerse más simple.
6. **Soberanía del Backlog y Especificaciones (Read-Only)**: Los archivos de
   planificación estratégica y backlog (`docs/PLAN.md`, especificaciones formales)
   son de **solo lectura** para el agente durante el desarrollo. El agente **NUNCA**
   debe auto-modificar el backlog, eliminar tareas pendientes ni alterar requerimientos
   para acomodarlos al código sin instrucción humana expresa. El código se adapta
   a la especificación, jamás la especificación al código.
7. **Protocolo de Relevo y Continuidad (Step 0 obligatorio)**: Este repositorio
   es colaborativo y multi-agente (ZCode, Claude Code, Antigravity, humanos)
   sobre el mismo working tree. Motivado por un incidente real (2026-09-20): un
   relevo entre sesiones dejó un test con bytes nulos literales que rompía la
   compilación, invisible para un chequeo superficial.
   - **Paso 0 — diagnóstico de entrada, antes de proponer cambios o código**:
     ```bash
     yunta check --tests
     git status
     ```
     `yunta check` sin `--tests` NO ejecuta la suite, solo detecta que existe
     — no habría atrapado el incidente que motiva esta regla. Si hay archivos
     modificados o tests rotos de una sesión anterior, **estabilizar y
     registrar ese trabajo es la prioridad #1** antes de iniciar tarea nueva.
   - **Handoff estructurado y buzón canónico**: el traspaso de estado real de sesión
     (mensajes, permisos, sandbox activo) usa `yunta handoff export`/`import`
     (`yunta/handoff.py`, spec pública en `docs/schemas/yunta-session-spec-v1.md`).
     El complemento narrativo (decisiones, prioridades, próximos pasos) debe residir
     en el buzón canónico **`.yunta/HANDOFF.md`** (evitando `scratch/`, que se reserva
     para archivos temporales u offload).
   - **Coordinación estricta sobre el working tree compartido (un agente a la vez)**:
     nunca deben operar dos agentes simultáneamente sobre el **mismo directorio de
     trabajo**. Si otro agente tiene trabajo en curso ahí, esperar a que concluya o
     formalice su relevo antes de iniciar modificaciones. Esto sigue siendo el modo
     por defecto para cambios chicos o de un solo agente a la vez.
   - **Trabajo concurrente real (git worktrees), para cuando varios agentes
     necesitan avanzar al mismo tiempo** (2026-09-22): el punto anterior evita
     pisarse, pero no permite paralelismo genuino — obliga a esperar turno incluso
     cuando las tareas no se solapan. Para eso, cada agente que vaya a trabajar en
     paralelo con otro usa su **propio `git worktree` en su propia rama**, derivada
     de la punta de la rama de integración vigente (hoy `feat/v2.5.0-voice-roi-extractors`;
     si el proyecto define una rama de integración distinta más adelante, reemplaza
     a esta como base):
     - **Nombre de rama**: `<rama-integración>--<agente>-<tarea-o-fase>` (ej.
       `feat/v2.5.0-voice-roi-extractors--antigravity-fase8-9`).
     - Cada agente trabaja, testea y commitea en su propio worktree sin tocar el
       directorio de los demás — cero riesgo de corrupción cruzada mientras ambos
       avanzan a la vez, sin importar si tocan los mismos archivos.
     - **Al terminar**, el agente abre PR contra la rama de integración (o hace
       rebase/merge si el flujo del repo no usa PRs) y corre la suite completa
       *después* de integrar, no solo antes — los conflictos de merge, si los hay,
       los resuelve git de la forma estándar, no una convención informal de "avisar
       antes de tocar tal función".
     - **`HANDOFF.md` cambia de rol**: en modo worktree deja de ser el semáforo de
       "quién tiene el control del único directorio" y pasa a listar qué rama/worktree
       tiene cada agente y en qué fase está, para evitar trabajo duplicado — ya no es
       un cuello de botella de turnos.
     - Si una tarea es chica o un solo agente está activo, seguir usando el working
       tree compartido (punto anterior) es más simple — los worktrees son para cuando
       la concurrencia real aporta valor, no un reemplazo universal del flujo actual.
   - **Prohibición de trabajo fantasma**: si una tarea queda incompleta por
     agotamiento de cuota o relevo inminente, registrar un commit `wip: <qué
     falta y qué tests están pendientes>` en vez de dejar el working tree
     modificado sin rastro.
   - **Cierre de relevo limpio**: al concluir un bloque de trabajo, dejar el
     working tree commiteado (suite en verde) o documentado en
     `CHANGELOG.md` — nunca a medias sin registro.

## Cómo extender

- **Nueva tool**: archivo en `yunta/tools/` con el decorador
  `@registry.register(name, description, parameters, requires_approval=...)`.
  La función recibe el JSON crudo y devuelve un string.
- **Nueva estrategia de compactación**: implementar `compact(messages)` en
  `yunta/compact.py` con la misma interfaz que `NoCompaction`/`SlidingWindow`.
- **Nuevo comando del REPL**: `main.py`.

## Verificación mínima antes de registrar un cambio

```bash
python -m py_compile main.py yunta/*.py yunta/tools/*.py
```

Más un smoke test del bucle con provider falso (ver `CHANGELOG.md` § 0.1.0).

## Entorno

- Python 3.11+, dependencias solo en `requirements.txt` (hoy: `litellm`).
- Variables: `LLM_MODEL` (obligatoria), `LLM_API_KEY`, `LLM_API_BASE` (opcionales,
  según proveedor — ver README para ejemplos).
