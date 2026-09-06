# yunta

[English](README_en.md) | **Español**

![logo](docs/logo.png)

Agente de código para terminal, agnóstico al proveedor del modelo.

*Yunta*: pareja de bueyes unidos para trabajar juntos — tú y el agente, sin importar qué modelo tire del otro lado.

Diseñado desde cero para ser independiente de cualquier proveedor de modelos: el acceso a los LLMs es 100% vía [LiteLLM](https://docs.litellm.ai/docs/), por lo que cualquier proveedor soportado funciona cambiando una variable de entorno.

---

## Características Principales

- **Agnóstico al Proveedor**: Conecta OpenAI, Anthropic Claude, Google Gemini, DeepSeek, Groq, o modelos locales vía Ollama/vLLM sin tocar una sola línea de código.
- **Minimalismo Extremo (~500 líneas)**: Sin frameworks de agentes pesados (sin LangChain ni CrewAI). Código comprensible, auditable y fácil de hackear.
- **Edición Quirúrgica de Código (`str_replace`)**: Edita fragmentos exactos de archivos validando unicidad de contexto al estilo de Anthropic Claude Code y SWE-bench.
- **Aprobaciones Humanas con Diff Unificado**: Visualiza exactamente qué líneas se agregarán o eliminarán antes de confirmar la escritura o ejecución.
- **Interrupción Limpia (`Ctrl+C`)**: Cancela un turno largo o llamada a herramienta en cualquier momento sin perder la sesión del REPL ni romper el historial de la conversación.
- **Soporte Nativo de MCP (Model Context Protocol)**: Conecta servidores MCP externos vía `stdio` JSON-RPC 2.0 sin librerías adicionales.
- **Memoria Persistente y Aprendizaje Continuo**: Recuerda hechos clave entre sesiones (`.yunta/memory.json`) y acumula lecciones aprendidas (`.yunta/learnings.md`).
- **Subagentes de Investigación**: Delega tareas de lectura intensiva a subagentes secundarios sin saturar la ventana de contexto principal.

---

## Instalación

Requiere Python 3.10 o superior.

```bash
git clone https://github.com/j0sp0nc3/yunta.git
cd yunta
pip install -r requirements.txt
```

O instala en modo editable:

```bash
pip install -e .
```

---

## Configuración de Modelos

Yunta **no tiene modelos por defecto**: tú eliges quién tira del carro configurando tu entorno.

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
- `/clear`: Limpia el historial de mensajes de la sesión actual.
- `/tokens`: Muestra el consumo acumulado de tokens (entrada y salida) de la sesión.
- `/exit`: Guarda lecciones aprendidas en `.yunta/learnings.md` y finaliza la sesión.
- `Ctrl+C`: Interrumpe el turno en curso de forma limpia y regresa al prompt `> ` sin tumbar la sesión.

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
