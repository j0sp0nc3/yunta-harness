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

## Paso 1: Requisitos Previos e Instalación

Yunta requiere **Python 3.11 o superior**.

1. **Clonar el repositorio**:
   ```bash
   git clone https://github.com/j0sp0nc3/yunta.git
   cd yunta
   ```

2. **Crear y activar un entorno virtual (recomendado)**:
   ```bash
   # En Linux / macOS:
   python3 -m venv .venv
   source .venv/bin/activate

   # En Windows (PowerShell):
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

3. **Instalar dependencias**:
   ```bash
   # Instalación estándar:
   pip install -r requirements.txt

   # O instalación en modo editable con herramientas de desarrollo:
   pip install -e .[dev]
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

## Paso 7: Comandos de Sesión y Control en el REPL

Durante cualquier momento de tu sesión puedes utilizar los comandos de control:

| Comando / Atajo | Acción | Descripción |
| :--- | :--- | :--- |
| **`/tokens`** | Telemetría de tokens | Muestra el consumo acumulado de entrada y salida, destacando los tokens ahorrados por **Prompt Caching**: `in=14200 (cached=11800) out=650`. |
| **`Ctrl+C`** | Interrupción limpia | Si el modelo está en medio de un turno largo o ejecutando un comando y deseas detenerlo, pulsa `Ctrl+C`. El turno se cancela de inmediato y regresas al prompt `> ` sin tumbar la sesión ni perder el historial. |
| **`/clear`** | Limpiar contexto | Borra el historial de mensajes de la sesión actual si deseas iniciar un tema nuevo. |
| **`/exit`** | Salir y aprender | Guarda automáticamente las lecciones y patrones aprendidos en `.yunta/learnings.md` para mejorar en tu próxima sesión y cierra el programa. |

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
