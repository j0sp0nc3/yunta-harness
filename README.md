# yunta

Agente de código para terminal, agnóstico al proveedor del modelo.

*Yunta*: pareja de bueyes unidos para trabajar juntos — tú y el agente, sin importar
qué modelo tire del otro lado.

Diseñado desde cero para ser independiente de cualquier proveedor de modelos:
el acceso a los LLMs es 100% vía [LiteLLM](https://docs.litellm.ai/docs/), por lo
que cualquier proveedor soportado funciona cambiando una variable de entorno.

## Uso

```bash
pip install -r requirements.txt
```

Elige tu modelo (no hay default — tú decides quién tira):

```bash
# OpenAI
export LLM_MODEL=openai/gpt-4o
export OPENAI_API_KEY=sk-...

# Anthropic
export LLM_MODEL=anthropic/claude-sonnet-4-5
export ANTHROPIC_API_KEY=sk-ant-...

# Local (Ollama)
export LLM_MODEL=ollama/llama3

# Cualquier endpoint compatible: OpenRouter, vLLM, Groq, DeepSeek...
export LLM_MODEL=openrouter/deepseek/deepseek-chat
export LLM_API_KEY=...
# o bien:
export LLM_API_BASE=https://tu-endpoint/v1
```

```bash
python main.py
```

## Comandos

- `/clear` — limpia el historial de conversación
- `/tokens` — consumo acumulado de la sesión
- `/exit` — salir

## Arquitectura

```
main.py            wiring + REPL
yunta/
  api.py           tipos neutrales (Message, Block, ToolDef, Response)
  provider.py      Provider sobre LiteLLM — única capa que toca modelos
  agent.py         bucle del agente (hasta stop_reason ≠ tool_use o max_turns)
  compact.py       NoCompaction / SlidingWindow
  tools/           tools auto-registradas con decorador
    bash.py        bash (requiere aprobación)
    files.py       read_file / write_file (write requiere aprobación)
```

Reglas de diseño:

- Ningún tipo de SDK cruza `provider.py`; el core habla solo en tipos de `api.py`.
- Los errores de tools vuelven al contexto como resultados — el modelo reintenta.
- Sin frameworks: el bucle, los permisos y el contexto son tuyos.

## Extender

Nueva tool: crea un archivo en `yunta/tools/` y usa el decorador.

```python
from . import _parse, registry

@registry.register(
    "mi_tool",
    "Descripción clara para el modelo.",
    {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
    requires_approval=False,
)
def mi_tool(raw: str) -> str:
    return _parse(raw)["x"]
```

## Licencia

MIT
