# Especificación Técnica (SPEC) — Yunta Harness

## 1. Visión y Propósito
Yunta es un **harness de desarrollo de agentes de código** diseñado para trabajar en pareja con desarrolladores bajo la filosofía de **Spec-Driven Development (SDD)** y **Zero-Vibe Coding**.

A diferencia de extensiones o chats que reescriben archivos ciegamente, Yunta proporciona un entorno determinista con:
- Gobernanza estricta basada en especificaciones (`SPEC.md`, `PLAN.md`, `AGENTS.md`).
- Herramientas atómicas de edición segura (`str_replace`, `read_file` paginado, `list_dir` con presupuesto de tokens).
- Micro-checkpoints reversibles en memoria (`/undo`).
- Transparencia económica y control de contexto (`/roi`, `/tokens`, compactador `SlidingWindow`).
- Diagnóstico local de gobernanza (`yunta check`) con costo $0 en tokens de LLM.

## 2. Requerimientos Funcionales
1. **Agnóstico al Proveedor**: Conexión vía LiteLLM y endpoints compatibles con OpenAI con soporte de streaming (`stream_options`), reintentos y cascada de respaldo (`LLM_MODELS`).
2. **Gobernanza SDD**:
   - Inicialización asistida con `yunta init [idea]`.
   - Auditoría estática y local con `yunta check [ruta] [--json] [--tests]`.
   - Protocolo canónico de interoperabilidad para IDEs externos (Claude Code, Cursor, Copilot, Antigravity).
3. **Resiliencia Operativa**:
   - Persistencia continua de sesión (`.yunta/session_state.json`) y recuperación con `yunta --resume`.
   - Prevención de llamadas huérfanas ante interrupciones de usuario (`Ctrl+C`).
   - Blindaje de codificación UTF-8 / CP1252 para Windows.
4. **Herramientas Blindadas**:
   - `read_file`: paginación transparente con límite seguro (2.000 líneas).
   - `str_replace`: reemplazo unívoco con validación de ocurrencias.
   - `list_dir`: árbol ASCII estructurado con control de profundidad y número de archivos.
   - `bash`: ejecución de comandos con timeout y filtrado de salida.

## 3. Arquitectura del Sistema
- **CLI & Dispatcher (`yunta/cli.py`)**: Punto de entrada para REPL, single-shot (`yunta "tarea"`), comandos de gobernanza (`check`, `init`) y flags globales (`--help`, `--version`, `--resume`).
- **Núcleo del Agente (`yunta/agent.py`)**: Bucle de razonamiento iterativo, ejecución de tools, manejo de streaming y snapshots para `/undo`.
- **Gobernanza (`yunta/governance.py`)**: Linter determinista de repositorios SDD con salida en texto y JSON.
- **Sesión (`yunta/session.py`)**: Serialización atómica de mensajes y métricas.
- **Herramientas (`yunta/tools/`)**: Registro de tools desacopladas del modelo.
- **Abstracción de Modelos (`yunta/provider.py`)**: Capa de llamada a LLMs con soporte de streaming, reintentos y tokens cacheados.

## 4. Criterios de Aceptación y Calidad
- 100% de pruebas unitarias pasando en `pytest`.
- Cero dependencias externas pesadas fuera de las declaradas en `pyproject.toml`.
- Salida ASCII universal compatible con cualquier terminal Windows y POSIX.
