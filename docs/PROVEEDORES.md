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

---

## Matriz de Proveedores de Transcripción de Voz (STT - Speech to Text)

Yunta mantiene **agnosticismo total a modelos de voz STT**. Soporta cualquier endpoint en línea compatible con el estándar OpenAI `/v1/audio/transcriptions`, con fallback automático transparente al motor local offline en ausencia de internet o credenciales.

| Proveedor de Voz | Configuración de Variables | Modo | Rendimiento & Precisión | Casos de Uso & Notas |
|---|---|---|---|---|
| **Cloudflare Workers AI** | `VOICE_API_BASE=https://<worker>.workers.dev/v1`<br>`VOICE_MODEL=@cf/openai/whisper` | 🌐 Online (Serverless) | ⚡ ~300ms <br> ⭐⭐⭐⭐⭐ Inmune a ruido | **Recomendado Cloud ($0/mes)**: 10,000 transcripciones/día gratis en el Edge. |
| **Groq Cloud API** | `VOICE_API_BASE=https://api.groq.com/openai/v1`<br>`VOICE_API_KEY=<key>`<br>`VOICE_MODEL=whisper-large-v3` | 🌐 Online (Cloud API) | 🚀 ~150ms (Ultra rápido) <br> ⭐⭐⭐⭐⭐ Inmune a ruido | 7,200 req/día gratis. Transcripción instantánea en hardware LPU. |
| **Whisper en Docker (Local)** | `VOICE_API_BASE=http://localhost:8000/v1`<br>`VOICE_MODEL=base` | 🔌 Offline Local (Docker) | 🚀 ~100-200ms <br> ⭐⭐⭐⭐⭐ Inmune a ruido | **Recomendado Local (0 Cloud)**: Contenedor `fedirz/faster-whisper-server` en localhost:8000. |
| **OpenAI Whisper API** | `VOICE_API_BASE=https://api.openai.com/v1`<br>`VOICE_API_KEY=<key>`<br>`VOICE_MODEL=whisper-1` | 🌐 Online (Cloud API) | 🚗 ~1s <br> ⭐⭐⭐⭐⭐ Alta precisión | Estándar comercial de OpenAI ($0.006 / minuto). |
| **Ollama / Local HTTP** | `VOICE_API_BASE=http://localhost:11434/v1`<br>`VOICE_MODEL=whisper` | 🌐 Local HTTP (Privacy) | 🏎️ Varía según CPU/GPU <br> ⭐⭐⭐⭐ Inmune a ruido | 100% privado en red local, requiere servidor Ollama en ejecución. |

