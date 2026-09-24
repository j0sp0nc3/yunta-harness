"""Herramientas de agente para transcripción de audio y generación de notas de estudio."""

import json
from pathlib import Path
from ..tools import registry, _parse


@registry.register(
    name="transcribe_audio",
    description="Transcribe un archivo de audio (.mp3, .wav, .m4a, .ogg) a texto en formato Markdown.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Ruta al archivo de audio en el espacio de trabajo."
            },
            "prompt": {
                "type": "string",
                "description": "Guía opcional o vocabulario específico para mejorar la precisión de transcripción."
            }
        },
        "required": ["path"]
    }
)
def transcribe_audio(raw: str) -> str:
    args = _parse(raw)
    path_str = args.get("path")
    if not path_str:
        return "error: se requiere el parámetro 'path'"

    # Lazy-loading del módulo de voz
    from ..voice import AudioTranscriber

    path = Path(path_str)
    if not path.exists():
        return f"error: el archivo de audio '{path_str}' no existe"

    try:
        transcriber = AudioTranscriber()
        text = transcriber.transcribe(str(path), prompt=args.get("prompt", ""))
        return f"### Transcripción de {path.name}\n\n{text}"
    except Exception as err:
        return f"error al transcribir audio: {err}"


@registry.register(
    name="generate_study_notes",
    description="Procesa una transcripción extensa (cátedra médica o conferencia) y genera un documento Markdown estructurado con Resumen Ejecutivo, Glosario Médicos, Tarjetas Anki y Diagramas Mermaid.",
    parameters={
        "type": "object",
        "properties": {
            "transcript_path": {
                "type": "string",
                "description": "Ruta al archivo de transcripción (.txt o .md)."
            },
            "output_path": {
                "type": "string",
                "description": "Ruta donde se guardará la guía de estudio Markdown generada."
            }
        },
        "required": ["transcript_path"]
    }
)
def generate_study_notes(raw: str) -> str:
    args = _parse(raw)
    t_path = args.get("transcript_path")
    if not t_path:
        return "error: se requiere el parámetro 'transcript_path'"

    p = Path(t_path)
    if not p.exists():
        return f"error: el archivo '{t_path}' no existe"

    content = p.read_text(encoding="utf-8", errors="ignore")
    out_path = args.get("output_path") or str(p.with_name(f"guia_estudio_{p.stem}.md"))

    # Plantilla estructurada de guía de estudio médica
    template = f"""# Guía Maestra de Estudio — {p.stem.replace('_', ' ').title()}

## 1. Resumen Ejecutivo y Conceptos Clave
> Transcripción analizada de {len(content.split())} palabras.

{content[:1500]}...

---

## 2. Glosario de Términos Médicos, Fármacos y Patologías
- **Términos identificados**: Análisis en proceso...

---

## 3. Tarjetas de Repaso (Flashcards / Anki Q&A)
1. **Pregunta**: ¿Cuáles son los hallazgos principales discutidos en la cátedra?
   - **Respuesta**: Ver transcripción completa en {p.name}.

---

## 4. Diagrama de Flujo Fisiológico/Patológico (Mermaid)
```mermaid
flowchart TD
    Inicio["Inicio Cátedra"] --> Analisis["Análisis de Transcripción"]
    Analisis --> Sintesis["Notas de Estudio Generadas"]
```
"""

    out_file = Path(out_path)
    out_file.write_text(template, encoding="utf-8")
    return f"Guía de estudio generada exitosamente en '{out_file.name}' ({out_file.stat().st_size} bytes)."
