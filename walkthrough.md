# Walkthrough — Yunta v2.4.0: Prompts por Voz, Cátedras Largas, Adaptadores Lazy y Enrutamiento por Intención

Se completó la implementación de las capacidades de **Prompts por Voz Manos Libres, Fragmentación por Silencios (VAD) para Cátedras Largas de Medicina, Carga Bajo Demanda de Adaptadores Modales y Enrutamiento por Intención (SDD vs. Investigación & Consultoría)** para **Yunta v2.4.0**.

---

## 🛠️ Novedades e Implementaciones Realizadas

### 1. Clasificación por Intención (`yunta/intent.py`)
- **`IntentClassifier`**: Detecta automáticamente si una instrucción es de desarrollo de software o de investigación/consultoría.
- **Enrutamiento Flexible**: Si la tarea es de consulta o resumen (ej. *"Resume la cátedra de cardiología"*), activa el `RESEARCH_AND_CONSULTING` mode, **omitendo las compuertas de git pre-commit, las búsquedas AST y los verificadores del compilador**, entregando el resultado directamente en formato Markdown.

### 2. Prompts por Voz Manos Libres y Cátedras Extensas (`yunta/voice.py`)
- **`AudioTranscriber`**: Peticiones nativas HTTP `multipart/form-data` a endpoints compatibles con Whisper (Groq `whisper-large-v3`, OpenAI Whisper, Ollama Whisper) sin dependencias pesadas.
- **`AudioChunker` (Silencedetect VAD)**: Segmentación automática de audios masivos (cátedras de 2 a 4+ horas, >25 MB) basada en pausas de silencio (>0.5s) para no trocear palabras compuestas por la mitad.
- **`record_microphone`**: Captura manos libres desde micrófono local con fallback automático.

### 3. Herramientas de Estudio y Generador de Notas (`yunta/tools/voice.py`)
- `@registry.register("transcribe_audio")`: Transcripción de audios cortos o de larga duración.
- `@registry.register("generate_study_notes")`: Generación automática de resúmenes ejecutivos por temas, glosarios médicos/farmacológicos, tarjetas Anki Q&A y diagramas de flujo Mermaid.

### 4. Adaptadores Modales Carga Bajo Demanda (`yunta/adapters.py`)
- `InputAdapterRegistry`: Carga perezosa (*Lazy-Loading*) de adaptadores modales. Consumo inicial de 0 MB al iniciar Yunta; se instancian únicamente al procesar audio (`.mp3`, `.wav`) o imagen (`.png`, `.jpg`).

### 5. CLI & REPL Manos Libres (`yunta/cli.py`)
- Banderas de terminal `yunta -v` / `yunta --voice [clase.m4a]`.
- Comando interactivo `/voice [archivo.mp3]` en el REPL de Yunta.

---

## 🧪 Pruebas y Verificaciones Ejecutadas

### 1. Compilación Estática PyCompile
```bash
python -c "import py_compile, glob; [py_compile.compile(f, doraise=True) for f in glob.glob('yunta/**/*.py', recursive=True) + ['main.py']]"
```
> **Resultado**: 100% de compilación sin errores de sintaxis.

### 2. Pruebas Unitarias de Voz, Intención y Carga Lazy
```bash
python -m pytest tests/test_intent.py tests/test_voice.py tests/test_voice_lazy.py
```
> **Resultado**: `8 passed in 24.50s` (100% test pass rate).

---

## 📑 Registro de Cambios
Documentado el release `[2.4.0] — 2026-09-13` en [`CHANGELOG.md`](file:///c:/Users/HP/.zcode/workspace/default/yunta/CHANGELOG.md).
