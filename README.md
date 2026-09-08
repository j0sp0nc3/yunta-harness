# Yunta: El Harness para Spec-Driven Development (SDD)

[English](README_en.md) | **Español**

![logo](docs/logo.png)

[![PyPI version](https://img.shields.io/pypi/v/yunta-harness.svg)](https://pypi.org/project/yunta-harness/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Harness de agente de código para terminal, agnóstico al proveedor del modelo.**

*Yunta*: pareja de bueyes unidos para trabajar juntos — tú y el agente, sin importar qué modelo tire del otro lado.

## 🎯 Yunta: El Harness para Spec-Driven Development (SDD)

En la metodología **Spec-Driven Development (SDD)**, el código no se genera por intuición o prompts ad-hoc, sino a partir de especificaciones formales y contratos verificables. Yunta actúa como el **harness de ejecución y verificación**:

- 📋 **Consumo Estricto de Especificaciones**: Lee `AGENTS.md` y especificaciones del proyecto en cada ciclo como única fuente de verdad.
- 🔬 **Edición Quirúrgica (`str_replace`)**: Previene la degradación del código mediante reemplazos exactos con validación estricta de unicidad.
- 🛡️ **Aprobaciones Humanas en Tiempo Real**: Visualización interactiva de `git diff` antes de autorizar cualquier escritura o comando.
- ⚡ **Prompt Caching Agnóstico**: Permite iterar continuamente contra especificaciones y arquitecturas extensas con hasta un 90% de ahorro en costos y latencia.
- 🔄 **Bucle Cerrado de Verificación**: El agente valida autónomamente sus cambios contra la suite de pruebas (`pytest`) antes de dar por cerrada la tarea.

👉 **[Ver la Guía y Presentación Completa de Yunta + SDD](docs/sdd.md)**

Diseñado desde cero para ser independiente de cualquier proveedor de modelos: el acceso a los LLMs es 100% vía [LiteLLM](https://docs.litellm.ai/docs/), por lo que cualquier proveedor soportado funciona cambiando una variable de entorno.

---

## Características Principales

- **Agnóstico al Proveedor**: Conecta OpenAI, Anthropic Claude, Google Gemini, DeepSeek, Groq, o modelos locales vía Ollama/vLLM sin tocar una sola línea de código.
- **Minimalismo Extremo (~500 líneas)**: Sin frameworks de agentes pesados (sin LangChain ni CrewAI). Código comprensible, auditable y fácil de hackear.
- **Edición Quirúrgica de Código (`str_replace`)**: Edita fragmentos exactos de archivos validando unicidad de contexto al estilo de Anthropic Claude Code y SWE-bench.
- **Aprobaciones Humanas con Diff Unificado**: Visualiza exactamente qué líneas se agregarán o eliminarán antes de confirmar la escritura o ejecución.
- **Prompt Caching Agnóstico**: Inyección de puntos de corte de caché (`cache_control`) para Anthropic Claude y detección automática en OpenAI/DeepSeek/Gemini, ahorrando hasta 90% en tokens de entrada y reduciendo la latencia.
- **Interrupción Limpia (`Ctrl+C`)**: Cancela un turno largo o llamada a herramienta en cualquier momento sin perder la sesión del REPL ni romper el historial de la conversación.
- **Soporte Nativo de MCP (Model Context Protocol)**: Conecta servidores MCP externos vía `stdio` JSON-RPC 2.0 sin librerías adicionales.
- **Memoria Persistente y Aprendizaje Continuo**: Recuerda hechos clave entre sesiones (`.yunta/memory.json`) y acumula lecciones aprendidas (`.yunta/learnings.md`).
- **Subagentes de Investigación**: Delega tareas de lectura intensiva a subagentes secundarios sin saturar la ventana de contexto principal.

---

## Guía Rápida Paso a Paso

👉 ¿Primera vez usando Yunta? Sigue la **[Guía Paso a Paso Completa (docs/quickstart.md)](docs/quickstart.md)** para aprender desde la configuración del modelo hasta el flujo de edición con diffs y comandos del REPL.

---

## Instalación

Requiere Python 3.11 o superior.

### Desde PyPI (Recomendado):
```bash
pip install yunta-harness
```
> **💡 Nota sobre el nombre:** En PyPI el paquete se instala como `yunta-harness`, pero el comando ejecutable en tu terminal es simplemente **`yunta`** (por ejemplo: `yunta`, `yunta init .` o `yunta "tu instrucción"`). No necesitas instalarlo dentro de tu aplicación existente: funciona como herramienta global (igual que Git).

### Desde el repositorio fuente (Desarrollo):
```bash
git clone https://github.com/j0sp0nc3/yunta-harness.git
cd yunta-harness
pip install -e .
```

---

## Configuración de Modelos

Yunta **no tiene modelos por defecto**: tú eliges quién tira del carro configurando tu entorno.
Consulta la [Matriz de Proveedores Verificados](docs/PROVEEDORES.md) para ver la lista de modelos probados con el script de prueba universal (`scripts/prueba_proveedor.py`).

### Google Gemini
```bash
export LLM_MODEL=gemini/gemini-3.5-flash
export GEMINI_API_KEY=tu-api-key
```

### Anthropic Claude
```bash
export LLM_MODEL=anthropic/claude-3-7-sonnet
export ANTHROPIC_API_KEY=sk-ant-...
```

### OpenAI
```bash
export LLM_MODEL=openai/gpt-4o
export OPENAI_API_KEY=sk-...
```

### DeepSeek / OpenRouter
```bash
export LLM_MODEL=openrouter/deepseek/deepseek-chat
export LLM_API_KEY=tu-openrouter-key
```

### Modelos Locales (Ollama)
```bash
export LLM_MODEL=ollama/llama3.3
```

### Endpoints Compatibles con OpenAI (vLLM, LocalAI, etc.)
```bash
export LLM_MODEL=openai/tu-modelo-local
export LLM_API_BASE=http://localhost:8000/v1
export LLM_API_KEY=dummy
```

---

## Uso y Comandos

Inicia la sesión interactiva:

```bash
python main.py
# O si lo instalaste con pip install -e .:
yunta
```

### Comandos del REPL
- `/init [idea]`: Inicializa un proyecto SDD generando `SPEC.md`, `PLAN.md` y `AGENTS.md`.
- `/undo`: Deshace la última edición de archivos y restaura el estado inmediatamente anterior.
- `/roi`: Despliega el dashboard de retorno de inversión, acierto de caché y ahorro en USD.
- `/metrics`: Despliega la telemetría detallada de herramientas ejecutadas, errores y turnos.
- `/tokens`: Muestra el consumo acumulado de tokens y tasa de acierto de caché.
- `/help`: Muestra la lista de comandos disponibles.
- `/clear`: Limpia el historial de mensajes de la sesión actual.
- `/exit`: Guarda lecciones aprendidas en `.yunta/learnings.md` y finaliza la sesión.
- `Ctrl+C`: Interrumpe el turno en curso de forma limpia y regresa al prompt `> ` sin tumbar la sesión ni dejar `tool_use` huérfano.

---

---

## Uso como Librería en Python (API v1.0)

A partir de la versión 1.0.0, puedes importar y embeber a Yunta directamente en tus scripts o aplicaciones:

```python
from yunta import Agent, LiteLLMProvider, FeedbackStore

# Inicializa el proveedor usando la variable de entorno LLM_MODEL
provider = LiteLLMProvider(system="Eres un asistente técnico conciso.")

# Instancia el agente con aprobaciones automáticas o personalizadas
agent = Agent(provider=provider, system=provider.system, confirm=lambda name, detail: True)

# Envía un mensaje y recibe la respuesta estructurada
respuesta = agent.send("Lista los archivos en el directorio actual")
print(respuesta)
```

---

## Detalles de Implementación para el Usuario

### 1. Contexto de Proyecto (`AGENTS.md`)
Si creas un archivo `AGENTS.md` en la raíz de tu proyecto, Yunta lo leerá e inyectará automáticamente en su `system prompt`. Úsalo para definir reglas inviolables, comandos de test o convenciones de tu equipo.

### 2. Edición de Archivos y Aprobaciones
Cuando Yunta decida modificar o escribir un archivo:
- **`str_replace`**: Reemplaza fragmentos específicos. Si la cadena a reemplazar es ambigua (aparece más de una vez), fallará pidiendo más contexto.
- **Previsualización de Diffs**: Si la herramienta requiere aprobación, verás un diff unificado estilo Git en la consola antes de pulsar `y` (confirmar) o `n` (rechazar).

### 3. Memoria Persistente entre Sesiones
El agente cuenta con las herramientas `remember` y `recall` para almacenar notas, decisiones de arquitectura o preferencias en `.yunta/memory.json`.

### 4. Servidores MCP (Model Context Protocol)
Puedes conectar herramientas de servidores MCP locales (`stdio`) creando el archivo `.yunta/mcp.json`:

```json
{
  "mcpServers": {
    "weather": {
      "command": "python",
      "args": ["servidores/weather_server.py"]
    }
  }
}
```
Las herramientas descubiertas se registrarán como `mcp__weather__<nombre_tool>`.

### 5. Creación de Herramientas Propias
Para agregar herramientas al agente, crea un archivo en `yunta/tools/` y usa el decorador `@registry.register`:

```python
from . import _parse, registry

@registry.register(
    "mi_tool",
    "Descripción clara de la herramienta para el modelo.",
    {
        "type": "object",
        "properties": {
            "parametro": {"type": "string", "description": "Texto de entrada"}
        },
        "required": ["parametro"]
    },
    requires_approval=False,
)
def mi_tool(raw: str) -> str:
    args = _parse(raw)
    return f"Resultado procesado: {args['parametro']}"
```

---

## Arquitectura

Yunta está organizado de forma modular, limpia y compacta:

```
main.py            -> Punto de entrada y REPL de consola
yunta/
  api.py           -> Tipos canónicos neutrales (Message, Block, ToolDef, Response)
  provider.py      -> Capa de conexión LiteLLM (streaming, reintentos 429/503)
  agent.py         -> Bucle iterativo de turnos, approvals de diffs y Ctrl+C
  compact.py       -> Compactación de contexto (SlidingWindow)
  feedback.py      -> Auto-feedback de lecciones (.yunta/learnings.md)
  mcp.py           -> Cliente nativo JSON-RPC 2.0 stdio MCP
  tools/           -> Registro y herramientas nativas
    files.py       -> read_file, write_file, str_replace (SWE-bench style)
    bash.py        -> Ejecución de comandos en subprocess con timeout
    search.py      -> glob y grep dentro del repositorio
    memory.py      -> remember y recall (.yunta/memory.json)
    delegate.py    -> delegate_research con subagente secundario
```

Para una explicación técnica detallada del diseño, consulta la [Documentación de Arquitectura Completa](docs/architecture.md).

---

## Licencia

Este proyecto está bajo la [Licencia MIT](LICENSE) - Copyright (c) 2026 j0sp0nc3 <beroiza79@gmail.com>.
