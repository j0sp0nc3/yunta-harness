# Yunta Session Handoff — Spec v1

Formato abierto para portar el estado de una sesión de agente de código
entre procesos, máquinas o harnesses/IDEs distintos (ej. ZCode → Antigravity
→ terminal). No es propietario de yunta: cualquier harness puede implementar
lectura/escritura de este formato sin depender del código de yunta.

Schema formal: [`yunta-session-spec-v1.schema.json`](yunta-session-spec-v1.schema.json)
(JSON Schema draft 2020-12).

## Por qué existe

MCP estandarizó cómo un agente descubre *herramientas*. Nada estandariza
cómo una *sesión* — mensajes, permisos otorgados, contexto de repo — viaja
entre dos harnesses distintos. Hoy, cambiar de herramienta a mitad de tarea
significa perder todo el contexto acumulado.

## Contrato mínimo para un implementador externo

Un harness que quiera **exportar** un bundle compatible debe escribir un
JSON con, como mínimo, `schema_version` (entero, `1` en esta versión),
`session_id` (string opaco), `created_at` (timestamp Unix) y `messages`
(lista de turnos `{role, content}`, con `content` una lista de bloques
`{type, ...}` donde `type` ∈ `text | tool_use | tool_result | image`).

Un harness que quiera **importar** un bundle debe:

1. Verificar `schema_version` y **rechazar** (no adivinar) versiones que no
   reconozca.
2. Tratar `session_permissions` y `active_sandbox` como **opcionales** — si
   no los soporta, puede ignorarlos con seguridad (el peor caso es volver a
   pedir aprobaciones que ya se habían otorgado, no una falla).
3. Tratar `git_commit`/`git_branch` como informativos: si el commit
   exportado difiere del commit actual del repo, reportar un aviso de
   "drift" — **nunca** bloquear el import por esto.

## Límite de alcance explícito

Yunta puede publicar y leer este schema. No puede forzar que otro harness
lo adopte — es un estándar candidato, no una imposición. La implementación
de referencia vive en [`yunta/handoff.py`](../../yunta/handoff.py)
(`export_handoff()` / `import_handoff()`), validada contra el schema en
[`tests/test_handoff_schema.py`](../../tests/test_handoff_schema.py).

## Versionado

Un cambio que agregue campos opcionales no incrementa `schema_version`. Un
cambio que agregue campos requeridos, cambie el significado de un campo
existente, o remueva uno, requiere `schema_version: 2` y un nuevo archivo
`yunta-session-spec-v2.schema.json` — la v1 se mantiene sin cambios para
compatibilidad retroactiva.
