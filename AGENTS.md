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

- Python 3.10+, dependencias solo en `requirements.txt` (hoy: `litellm`).
- Variables: `LLM_MODEL` (obligatoria), `LLM_API_KEY`, `LLM_API_BASE` (opcionales,
  según proveedor — ver README para ejemplos).
