# 📖 Guía Paso a Paso de Uso de Yunta CLI y Análisis Arquitectónico

---

## 🚀 Parte 1: Guía Paso a Paso del Uso de Yunta CLI

### Paso 1: Configuración de Variables de Entorno
Yunta es un harness agnóstico al modelo. Define tu modelo y claves en la terminal:
```bash
export LLM_MODEL="openai/gpt-4o"
export LLM_API_KEY="tu-api-key"
# Opcional para modelo ultrarrápido en investigaciones read-only:
export LLM_FAST_MODEL="openai/gpt-4o-mini"
```

### Paso 2: Inicialización de Proyectos con SDD (`yunta init`)
Para arrancar cualquier idea desde cero bajo **Spec-Driven Development (SDD)**:
```bash
yunta init "Nombre o Descripción de la Idea"
```
* **Efecto**: Genera automáticamente la tríada de gobernanza en el directorio:
  * `SPEC.md`: Especificación formal de requerimientos y casos de uso.
  * `PLAN.md`: Hoja de ruta por fases iterativas con criterio de aceptación TDD.
  * `AGENTS.md`: Manual de reglas de convivencia y protocolo de delegación a Yunta.

### Paso 3: Auditoría de Gobernanza y Tests (`yunta check`)
Para auditar la salud del repositorio sin gasto de tokens ($0 en API calls):
```bash
yunta check
# O para auditar incluyendo la ejecución de la suite de pruebas:
yunta check --tests
# O en formato JSON para herramientas e IDEs:
yunta check --json
```

### Paso 4: Instalación de Git Pre-Commit Hooks (`yunta hooks`)
Para garantizar que nunca se realice un commit con pruebas rotas o reglas SDD desobedecidas:
```bash
yunta hooks
```
* **Efecto**: Crea el script `.git/hooks/pre-commit` que ejecuta `yunta check --tests` previo a cada `git commit`. Para desinstalarlo: `yunta uninstall-hooks`.

### Paso 5: Conexión con IDEs vía Servidor MCP (`yunta serve-mcp`)
Para conectar Yunta a Claude Desktop, Cursor, Antigravity o VS Code mediante el estándar MCP (stdio):
```bash
yunta serve-mcp
```
* **Efecto**: Expone el catálogo de herramientas deterministas (`read_file`, `write_file`, `str_replace`, `list_dir`, `bash`, `delegate_subtask`), los recursos de especificación (`resource://yunta/spec`) y la gestión de permisos (`yunta/permissions`, `yunta/approve`).

### Paso 6: Integración Ligera vía JSON-Lines (`yunta serve-json`)
Para transmitir eventos de ejecución en tiempo real (`JSONL`) a extensiones de IDE o scripts externos:
```bash
yunta serve-json
```

### Paso 7: Ejecución Interactiva REPL y Comandos Slash
Al ejecutar `yunta` en la terminal sin argumentos, ingresas al REPL interactivo:
* `/roi`: Muestra el panel de retorno de inversión, ahorro monetario en USD y tokens cacheados.
* `/metrics`: Reporta la telemetría de tokens, turnos y el startup tax (<5.000 tokens).
* `/undo`: Revierte inmediatamente las últimas ediciones de archivos en memoria.
* `/sandbox`: Crea un espacio de trabajo aislado en Git Worktree (`.yunta/sandboxes/`).
* `/permissions`: Lista o limpia los patrones de permisos concedidos en la sesión.

---

## 🏛️ Parte 2: Análisis Arquitectónico de Yunta Harness (v2.0)

### 1. El Principio de Soberanía del Harness (CLI vs Biblioteca)
> ⚠️ **Regla Fundamental de Arquitectura**: Yunta es un harness ejecutable por línea de comandos (CLI), NO una biblioteca de código para ser importada (`import yunta`).

* **Razonamiento**: Si un agente de IA importara a Yunta dentro del proceso del código en desarrollo, se crearía una dependencia circular destructiva donde el entorno de prueba alteraría el entorno de producción.
* **Solución**: Toda interacción con Yunta ocurre desde el límite externo del proceso (CLI, stdio JSON-RPC MCP o streaming JSONL), garantizando aislamiento absoluto.

### 2. Análisis de Resiliencia (Resolución de Defectos P1 a P9)
Las rondas de dogfooding demostraron que un harness debe tolerar fallos catastróficos del entorno sin perder trabajo:
* **Escritura Atómica (P6)**: Previene la corrupción de archivos mediante el patrón `.tmp` + validación sintáctica (`py_compile`).
* **Degradación ante Cuotas (P7)**: Ante `RateLimitError` o `QuotaExhausted`, persiste `.yunta/estado-de-tarea.md` y sincroniza `.yunta/session_state.json`, permitiendo reanudar con `yunta --resume`.
* **Presupuesto Defensivo (P8)**: Detiene sesiones descontroladas al 90% del presupuesto de tokens.
* **Subagentes por Lote (P9)**: Evita la saturación de contexto al acotar ediciones a 1-2 archivos por subtarea.

### 3. Estrategia de Desacoplamiento de Extensiones de IDE
Para construir interfaces de usuario gráficas (como `yunta-vscode-extension`):
* **Independencia de Repositorio**: El harness central en Python permanece minimalista y sin dependencias UI.
* **Canal de Transporte**: La extensión de VS Code actúa exclusivamente como cliente gráfico TypeScript que inicia `yunta serve-mcp` o `yunta serve-json` por subproceso stdio.

---

*Registrado en el repositorio Yunta Harness v2.0.0 — Documento oficial de arquitectura y uso.*
