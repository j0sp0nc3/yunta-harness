# Guía Paso a Paso: Cómo Usar Yunta Harness

Bienvenido a **Yunta**, el harness de agente de código para terminal minimalista, agnóstico al modelo y guiado por especificaciones.

Esta guía te llevará paso a paso desde la instalación inicial hasta dominar el flujo completo de pair-programming con el agente en tu terminal.

---

## Paso 0: Modelo Mental — ¿Qué es y qué NO es Yunta?

Antes de tocar código, es fundamental entender la frontera entre tu herramienta y tu software:

| Concepto | Lo que ES Yunta | Lo que NO ES Yunta |
| :--- | :--- | :--- |
| **Naturaleza** | Arnés/Harness de desarrollo asistido (CLI) | Framework de runtime (como LangChain, AutoGen o CrewAI) |
| **Ubicación** | Tu terminal de trabajo (el banco del carpintero) | El servidor donde corre tu producto final (el mueble) |
| **Acción** | `view_file`, `str_replace`, `bash`, `pytest` | Servidor web, daemon de producción o bot en la nube |
| **Entregable** | Código limpio, testeado y comiteado para tu repo | Una aplicación que depende de Yunta para funcionar |

> 💡 **La Regla de Oro**:  
> *"Si estás pensando en cómo corre esto en producción, estás antes de usar Yunta. Si estás pensando en qué código necesitas escribir, es momento de abrir Yunta."*

### Metodología de 5 Fases para Proyectos Nuevos

1. **Fase 0: Definición de Frontera (en `AGENTS.md`)**:
   - ¿Qué problema resuelve? (1 párrafo claro).
   - ¿Cuál es el deliverable final? (código, librería, módulos).
   - ¿Dónde se ejecuta en producción? (ej. Power Automate, AWS Lambda, Docker, React) — *NO en Yunta*.
   - ¿Qué está fuera de alcance (*Out of Scope*)? (no crear daemons locales para Yunta).
2. **Fase 1: Estructura Mínima**:
   - Crear carpetas `src/`, `tests/` y `AGENTS.md`.
3. **Fase 2: Definir Contratos (sin implementar lógica)**:
   - Crear `src/api.py` con las `dataclasses` y tipos canónicos.
4. **Fase 3: Primera Tarea de Desarrollo con Yunta**:
   - Abrir `yunta` en la terminal y dar la instrucción acotada al contrato.
5. **Fase 4: Verificación y Documentación**:
   - Correr la suite de pruebas del proyecto y documentar el deploy a producción.

### Plantilla Base: `AGENTS.md` para tus Proyectos

Copia y pega este bloque en la raíz de cualquier proyecto que vayas a desarrollar con Yunta:

```markdown
# AGENTS.md — [Nombre del Proyecto]

## 1. Misión y Entorno de Ejecución (Runtime Boundary)
- **Propósito**: [Descripción concisa en 1 párrafo]
- **Runtime de Producción**: [Ej. Power Automate + Dataverse / AWS Lambda / Docker / FastAPI] (NO en Yunta).
- **Rol de Yunta**: Harness de desarrollo (herramientas de lectura, edición quirúrgica y pruebas).

## 2. Entregables (Deliverables)
- Código fuente en `src/`
- Suite de pruebas unitarias en `tests/`
- Tipos y contratos en `src/api.py`

## 3. Fuera de Alcance (Out of Scope)
- NUNCA crear servicios daemon ni daemons de terminal para Yunta.
- No asumir autenticaciones locales que corresponden al runtime de producción.
```

---

## Paso 1: Instalación y Distinción del Nombre (`yunta-harness` vs `yunta`)

Yunta requiere **Python 3.11 o superior**.

### 💡 ¿Por qué el paquete se llama `yunta-harness` pero el comando es `yunta`?
- **En PyPI (descarga con pip):** El paquete se llama **`yunta-harness`** porque en el registro oficial `pypi.org` el nombre `yunta` ya estaba ocupado por una librería histórica de bioinformática.
- **En tu terminal (comando CLI):** El comando que ejecutas es simplemente **`yunta`** (o `yunta init`) para que sea corto, intuitivo y cómodo de tipear.

### Instalación en tu Sistema:

#### Opción A: Desde PyPI (Recomendado)
Instala Yunta una sola vez de forma global en tu máquina (como Git o Docker):
```bash
pip install yunta-harness
```
*(O mediante `pipx install yunta-harness` / `uv tool install yunta-harness` si prefieres aislar herramientas CLI).*

#### Opción B: Desde el Repositorio Fuente (Desarrollo local)
```bash
git clone https://github.com/j0sp0nc3/yunta-harness.git
cd yunta-harness
pip install -e .
```

---

## ❓ ¿Debo instalar Yunta dentro de mi aplicación existente?

**No, en absoluto.** Yunta es una herramienta externa a tu aplicación (el banco del carpintero, no el mueble). No debes instalarla dentro de tu proyecto ni agregarla como dependencia en tu `package.json`, `requirements.txt` ni `pom.xml`.

Cualquiera sea la tecnología de tu aplicación (JavaScript, Python, Go, Rust, React, etc.), solo necesitas abrir la terminal en su carpeta:

```bash
# 1. Navegar a tu proyecto existente
cd /ruta/a/tu/aplicacion-existente

# 2. Inicializar el contexto ontológico (genera AGENTS.md, SPEC.md y PLAN.md sin tocar tu código)
yunta init .

# 3. Empezar a iterar con Yunta
yunta "Explica la estructura de este proyecto y ejecuta los tests existentes"
```

---

## Paso 2: Elegir y Configurar tu Modelo LLM

Yunta **no tiene modelos por defecto ni fallbacks ocultos**: tú eliges quién tira del carro mediante variables de entorno. Puedes usar cualquier proveedor soportado por [LiteLLM](https://docs.litellm.ai/docs/providers).

Elige una de las siguientes opciones:

### Opción A: Google Gemini (Recomendado para empezar)
```bash
# Linux / macOS:
export LLM_MODEL=gemini/gemini-3.7-flash
export GEMINI_API_KEY="tu-api-key-de-google-ai-studio"

# Windows (PowerShell):
$env:LLM_MODEL="gemini/gemini-3.7-flash"
$env:GEMINI_API_KEY="tu-api-key-de-google-ai-studio"
```

### Opción B: Anthropic Claude (Con Prompt Caching nativo al 90% de ahorro)
```bash
# Linux / macOS:
export LLM_MODEL=anthropic/claude-3-7-sonnet
export ANTHROPIC_API_KEY="sk-ant-..."

# Windows (PowerShell):
$env:LLM_MODEL="anthropic/claude-3-7-sonnet"
$env:ANTHROPIC_API_KEY="sk-ant-..."
```

### Opción C: OpenAI (GPT-4o)
```bash
# Linux / macOS:
export LLM_MODEL=openai/gpt-4o
export OPENAI_API_KEY="sk-..."

# Windows (PowerShell):
$env:LLM_MODEL="openai/gpt-4o"
$env:OPENAI_API_KEY="sk-..."
```

### Opción D: Modelos Locales Gratuitos con Ollama (Sin API Keys)
1. Inicia Ollama en tu máquina (`ollama serve`).
2. Descarga tu modelo de código preferido: `ollama run qwen2.5-coder` o `ollama run llama3.3`.
3. Configura Yunta:
   ```bash
   export LLM_MODEL=ollama/qwen2.5-coder
   ```

### Opción E: DeepSeek / OpenRouter o Endpoints OpenAI-Compatibles
```bash
export LLM_MODEL=openrouter/deepseek/deepseek-chat
export LLM_API_KEY="tu-clave"
# O para vLLM / LM Studio / LocalAI:
export LLM_MODEL=openai/tu-modelo
export LLM_API_BASE=http://localhost:8000/v1
```

---

## Paso 3: Validar la Conexión con la Prueba Universal

Antes de comenzar a trabajar, puedes certificar en 5 segundos que tu modelo responde y que su capacidad de *Tool Calling* funciona al 100%:

```bash
python scripts/prueba_proveedor.py
```

El script ejecutará una tarea real donde el modelo crea un archivo temporal, lo lee y valida su contenido:
```text
proveedor/modelo: gemini/gemini-3.7-flash
[tool] write_file {"path": "prueba_proveedor.txt", "content": "verificado por yunta"}
[tool] read_file {"path": "prueba_proveedor.txt"}
--- tokens: in=5213 out=173 ---
RESULTADO: OK
```
Si ves `RESULTADO: OK`, ¡tu entorno está completamente listo!

---

## Paso 4: Iniciar la Sesión Interactiva de Yunta

Ejecuta el comando en tu terminal:

```bash
# Si instalaste con pip install -e .:
yunta

# O ejecutando directamente:
python main.py
```

Verás el mensaje de bienvenida y el prompt listo para interactuar:
```text
yunta – modelo: gemini/gemini-3.7-flash
Escribe tu consulta, /clear para limpiar, /exit para salir.

> 
```

---

## Paso 5: Tu Primer Turno de Trabajo (Lectura y Exploración)

Pídele al agente que examine tu proyecto. Yunta responderá con **streaming en tiempo real** y llamará a sus herramientas nativas (`glob`, `grep`, `read_file`):

```text
> Explora la estructura de este proyecto y enumera los módulos principales en una tabla.
```

Observarás cómo Yunta invoca herramientas de exploración:
```text
[tool] glob {"pattern": "*"}
[tool] read_file {"path": "pyproject.toml"}
Aquí tienes el resumen de la estructura del proyecto...
```

---

## Paso 6: Edición Quirúrgica y Aprobación de Diffs

Cuando le pidas a Yunta realizar un cambio en el código:
```text
> Agrega una función `calcular_hash(texto: str) -> str` usando hashlib sha256 en un archivo utils.py
```

1. **Edición Quirúrgica (`str_replace` o `write_file`)**: Yunta preparará la edición exacta sin sobreescribir archivos a ciegas.
2. **Previsualización de Diff Unificado**: En tu terminal verás un diff estilo Git coloreado:
   ```diff
   --- /dev/null
   +++ utils.py
   @@ -0,0 +1,5 @@
   +import hashlib
   +
   +def calcular_hash(texto: str) -> str:
   +    return hashlib.sha256(texto.encode("utf-8")).hexdigest()
   ```
3. **Control Humano**: El agente solicitará confirmación:
   ```text
   ¿Aprobar write_file en utils.py? (y/n): 
   ```
   - Pulsa `y` (o Enter) para autorizar.
   - Pulsa `n` para rechazar o pedir ajustes.

---

## Paso 6: Prompts por Voz, Dictado Manos Libres y Respuestas Rápidas

Yunta incluye soporte nativo y agnóstico para **dictado por voz y procesamiento de audio** basado en la arquitectura neural **Whisper**.

### 1. Modos de Operación por Voz

#### A. Modo CLI Directo (`yunta voice` o `yunta --voice [archivo.mp3]`)
- **Grabación en Vivo**: Ejecuta `yunta voice` y habla por el micrófono. Presiona `[ENTER]` cuando termines de hablar.
- **Filtro Anti-Ruido Espectral (`trim_initial_noise_and_silence`)**: Elimina automáticamente chasquidos de teclado (150ms) y silencios iniciales antes de transcribir.
- **Previsualización Interactiva**: Tras transcribir, Yunta muestra el texto capturado para su revisión:
  ```text
  🗣️ Transcripción capturada:
     "Revisa los tests del proyecto yunta"

  Opciones: [ENTER/s] Enviar al agente | [e] Editar texto | [c] Cancelar
  > 
  ```

#### B. Modo REPL Interactivo (`/voice` o `/listen`)
- **En la sesión interactiva**: Escribe `/voice` en el prompt `> ` para grabar una ráfaga de 5 segundos sin tocar teclas, o `/voice mi_clase.mp3` para transcribir un archivo.
- **Despacho Inmediato**: La transcripción capturada se envía directamente al contexto conversacional activo para seguir iterando.

---

### 2. Normalizador de Respuestas Rápidas por Voz/Texto (`normalize_voice_response`)

No necesitas escribir o pronunciar letras exactas (`s`, `c`, `e`). Yunta incluye un comparador determinista que traduce modismos fonéticos y coloquiales al instante:

| Acción Deseada | Palabras / Modismos Soportados (Voz o Teclado) | Acción Canónica |
| :--- | :--- | :--- |
| **Aprobar / Enviar** | `"sí"`, `"si"`, `"aprobado"`, `"avanzar"`, `"abanzau"`, `"abanzau ok"`, `"ok"`, `"dale"`, `"listo"`, `"de acuerdo"` | **`s`** (Enviar) |
| **Rechazar / Cancelar** | `"no"`, `"rechazado"`, `"cancelar"`, `"alto"`, `"stop"`, `"detener"`, `"abortar"` | **`c`** / **`n`** (Cancelar) |
| **Editar Texto** | `"editar"`, `"modificar"`, `"cambiar"`, `"corregir"`, `"reescribir"` | **`e`** (Editar) |
| **Aprobación Total** | `"sí a todo"`, `"siempre"`, `"para siempre"`, `"siempre si"`, `"aprobado a todo"` | **`siempre`** (Persistir) |

> 💡 **Protección de Instrucciones**: Las tareas completas o frases largas (ej. *"Quiero que generes un archivo de prueba.txt"*) son detectadas como instrucciones de desarrollo y se envían intactas sin ser alteradas.

---

### 3. Configuración de Proveedores STT (Whisper Agnóstico)

Yunta soporta cualquier servicio o contenedor compatible con la API HTTP de Whisper (`/v1/audio/transcriptions`):

- **Cloudflare Workers AI (Serverless)**:
  ```bash
  export VOICE_API_BASE="https://tu-worker.workers.dev/v1"
  export VOICE_MODEL="@cf/openai/whisper"
  ```
- **Groq Cloud (Súper Rápido)**:
  ```bash
  export VOICE_API_BASE="https://api.groq.com/openai/v1"
  export VOICE_MODEL="groq/whisper-large-v3"
  export VOICE_API_KEY="gsk_..."
  ```
- **Docker Local 100% Offline (0-Cloud / Privacidad)**:
  Corre el contenedor `fedirz/faster-whisper-server` en tu puerto 8000. Yunta lo utilizará automáticamente como servidor local offline si falla la conexión en la nube.

---

## Paso 7: Comandos de Sesión y Control en el REPL

Durante cualquier momento de tu sesión puedes utilizar los comandos de control:

| Comando / Atajo | Acción | Descripción |
| :--- | :--- | :--- |
| **`/init [idea]`** | Scaffolding SDD | Inicializa o andamia el proyecto generando `SPEC.md`, `PLAN.md` y `AGENTS.md`. |
| **`/sandbox [merge|discard]`** | Git Worktree Sandbox | Crea o gestiona un entorno aislado en Git Worktree para operaciones experimentales. |
| **`/context`** | Estado de tokens | Muestra los mensajes, tokens estimados en contexto y el uso % del presupuesto (`YUNTA_MAX_TOKENS`). |
| **`/undo`** | Time-Travel Undo | Restaura instantáneamente los archivos a su estado anterior a la última edición. |
| **`/permissions [clear]`** | Permisos de sesión | Muestra los patrones autorizados con 'siempre' o los revoca (`/permissions clear`). |
| **`/roi`** | Dashboard de valor | Muestra porcentaje de caché, tokens evitados y estimación de ahorro en USD. |
| **`/metrics`** | Telemetría detallada | Muestra llamadas a herramientas, **startup tax**, errores y turnos consumidos. |
| **`/tokens`** | Telemetría de tokens | Muestra el consumo acumulado de entrada, salida y tokens cacheados. |
| **`Ctrl+C`** | Interrupción limpia | Cancela el turno en curso o comando bash sin tumbar la sesión del REPL. |
| **`/clear`** | Limpiar contexto | Borra el historial de mensajes y la sesión guardada actual. |
| **`/exit`** | Salir y aprender | Guarda lecciones en `.yunta/learnings.md` para futuras sesiones y sale. |


---

## Paso 8: Buenas Prácticas Avanzadas

### 1. Define las Reglas de tu Proyecto con `AGENTS.md`
Coloca un archivo `AGENTS.md` en la raíz de tu repositorio con tus directivas de arquitectura:
```markdown
# AGENTS.md
- Convención de estilo: PEP 8 estricto.
- Suite de pruebas: Ejecutar siempre `python -m pytest` tras cada edición.
- Librería de base de datos: SQLAlchemy 2.0 con asyncpg exclusivamente.
```
Yunta leerá e inyectará este archivo automáticamente en su System Prompt en cada sesión.

### 2. Conectar Herramientas Externas con MCP (Model Context Protocol)
Si tienes servidores MCP locales (como servidores de base de datos, GitHub, clima o APIs internas), crea `.yunta/mcp.json`:
```json
{
  "mcpServers": {
    "db": {
      "command": "python",
      "args": ["servidores/db_server.py"]
    }
  }
}
```
Yunta registrará las herramientas automáticamente como `mcp__db__<nombre_tool>`.

### 3. Usar Yunta como Librería Python en tus Propios Scripts
Puedes integrar a Yunta programáticamente en tus pipelines de automatización:
```python
from yunta import Agent, LiteLLMProvider

# Inicializa usando el modelo configurado en tu entorno
provider = LiteLLMProvider(system="Eres un asistente de refactorización.")
agent = Agent(provider=provider, system=provider.system)

# Envía instrucciones directas
salida = agent.send("Revisa y formatea el código en src/main.py")
print(salida)
```

---

¡Listo! Ya tienes todas las herramientas para construir software robusto y verificado con **Yunta** bajo el paradigma de **Spec-Driven Development**.
