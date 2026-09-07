# Matriz de proveedores

El harness es agnóstico: cualquier modelo soportado por
[LiteLLM](https://docs.litellm.ai/docs/providers) funciona cambiando variables
de entorno, sin tocar código. Esta matriz documenta qué se ha verificado con
la prueba completa (`scripts/prueba_proveedor.py`: tool call real de
escritura + lectura + respuesta).

| Proveedor | Config | Estado | Notas |
|---|---|---|---|
| **Z.ai GLM** | `LLM_MODEL=openai/glm-4.7`<br>`LLM_API_BASE=https://api.z.ai/api/coding/paas/v4`<br>`LLM_API_KEY=<key>` | ✅ verificado (ZCode, v0.2.4+) | Vía Coding Plan; el prefijo nativo `zai/` requiere saldo API por consumo |
| **Google Gemini** | `LLM_MODEL=gemini/gemini-3.6-flash`<br>`GEMINI_API_KEY=<key>` | ✅ verificado (Antigravity, v0.7+) | Streaming y tools OK |
| OpenAI | `LLM_MODEL=openai/gpt-4o`<br>`OPENAI_API_KEY=<key>` | ⬜ pendiente de verificación comunitaria | Config estándar LiteLLM |
| Anthropic | `LLM_MODEL=anthropic/claude-sonnet-4-5`<br>`ANTHROPIC_API_KEY=<key>` | ⬜ pendiente | Prompt caching activo desde v0.11 |
| Ollama (local) | `LLM_MODEL=ollama/llama3` | ⬜ pendiente | Sin API key; requiere Ollama en localhost:11434 |
| OpenRouter | `LLM_MODEL=openrouter/<vendor>/<model>`<br>`OPENROUTER_API_KEY=<key>` | ⬜ pendiente | Agrega ~400 modelos |
| vLLM / LM Studio | `LLM_MODEL=openai/<model>`<br>`LLM_API_BASE=http://localhost:8000/v1` | ⬜ pendiente | Endpoint OpenAI-compatible local |

## Cómo verificar un proveedor nuevo

```bash
export LLM_MODEL=...   # según tabla o docs de LiteLLM
export LLM_API_KEY=... # si aplica
python scripts/prueba_proveedor.py
```

Si sale `RESULTADO: OK`, agrega la fila a la tabla con ✅ y registra la
verificación en `CHANGELOG.md`. Si falla, documenta el error exacto en la
columna Notas — es tan útil como el éxito.
