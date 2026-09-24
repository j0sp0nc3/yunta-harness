"""Banco de pruebas y métricas del pipeline de voz de yunta.

Mide por componente para detectar regresiones y guiar mejoras:
  --fuzzy   Precisión del matcher fonético (mutaciones sintéticas) + falsos positivos
  --router  Cobertura y latencia del router de palabras clave (debe ser ~0 ms)
  --stt     WER y latencia: worker Cloudflare vs faster-whisper local (requiere audio)
  --tts     Latencia de síntesis Edge TTS (primera oración)
  --vad     Umbral calibrado y detección con micrófono real (habla ~5s tras iniciar)

Uso:
  python scripts/bench_voice.py --fuzzy --router
  python scripts/bench_voice.py --stt --audio C:\\ruta\\audio.mp3
  python scripts/bench_voice.py --all --audio C:\\ruta\\audio.mp3

Resultado: reporte en terminal + JSON en .yunta/voice_bench_<ts>.json
"""

import argparse
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from yunta.voice import normalize_voice_response, route_keyword, load_voice_keywords  # noqa: E402


# ------------------------------- helpers -------------------------------

def _wer(reference: str, hypothesis: str) -> float:
    """Word Error Rate estándar (Levenshtein a nivel de palabras, normalizado)."""
    ref_words = reference.lower().split()
    hyp_words = hypothesis.lower().split()
    if not ref_words:
        return 0.0 if not hyp_words else 1.0
    prev = list(range(len(hyp_words) + 1))
    for i, rw in enumerate(ref_words, 1):
        curr = [i]
        for j, hw in enumerate(hyp_words, 1):
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + (rw != hw)))
        prev = curr
    return prev[-1] / len(ref_words)


def _mutate(word: str, rng: random.Random) -> str:
    if len(word) < 3:
        return word + "x"
    i = rng.randrange(len(word))
    op = rng.randint(0, 2)
    if op == 0:
        return word[:i] + word[i + 1:]
    if op == 1 and i + 1 < len(word):
        return word[:i] + word[i + 1] + word[i] + word[i + 2:]
    return word[:i] + rng.choice("aeiou") + word[i + 1:]


# ------------------------------- benchmarks -------------------------------

REFERENCE_WORDS = {
    "s": ["si", "aprobado", "dale", "ok", "avanzar", "correcto", "listo", "perfecto"],
    "c": ["no", "cancelar", "rechazado", "stop", "detener", "alto"],
    "e": ["editar", "modificar", "cambiar", "corregir"],
    "siempre": ["siempre"],
}

NEGATIVE_WORDS = [
    "docker", "python", "transcribir", "analizar", "informe", "dijkstra",
    "algoritmo", "sesion", "contexto", "metrica", "escribir", "archivo",
    "servidor", "memoria", "funcion", "variable", "prueba", "test",
]


def bench_fuzzy() -> dict:
    rng = random.Random(42)
    correct = total = 0
    for expected, words in REFERENCE_WORDS.items():
        for word in words:
            for _ in range(20):
                mutated = _mutate(word, rng)
                if mutated == word:
                    continue
                total += 1
                if normalize_voice_response(mutated) == expected:
                    correct += 1
    false_positives = sum(
        1 for w in NEGATIVE_WORDS if normalize_voice_response(w) != w
    )
    return {
        "precision_mutaciones": round(correct / total, 4),
        "muestras": total,
        "falsos_positivos": false_positives,
        "vocabulario_negativo": len(NEGATIVE_WORDS),
    }


def bench_router() -> dict:
    keywords = load_voice_keywords()
    t0 = time.perf_counter()
    hits = sum(1 for phrase, cmd in keywords.items() if route_keyword(phrase, keywords) == cmd)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    long_phrases = [
        "analiza el siguiente fragmento de código por favor",
        "dime qué métricas de rendimiento tiene el servidor",
        "quiero salir de compras al mediodía",
        "escríbeme un informe detallado del análisis",
    ]
    fp = sum(1 for p in long_phrases if route_keyword(p) is not None)
    return {
        "keywords_totales": len(keywords),
        "cobertura": round(hits / len(keywords), 4),
        "latencia_media_ms": round(elapsed_ms / len(keywords), 4),
        "falsos_positivos": fp,
    }


def bench_stt(audio_path: str) -> dict:
    from yunta.cli import _load_dotenv
    _load_dotenv()
    from yunta.voice import AudioTranscriber

    result: dict = {"archivo": audio_path}

    # 1) Worker Cloudflare (o el endpoint configurado)
    t = AudioTranscriber()
    t0 = time.perf_counter()
    worker_text = t.transcribe(audio_path)
    result["worker"] = {
        "segundos": round(time.perf_counter() - t0, 2),
        "chars": len(worker_text),
    }

    # 2) faster-whisper local (referencia, si está instalado)
    try:
        from faster_whisper import WhisperModel

        t0 = time.perf_counter()
        model = WhisperModel("small", device="cpu", compute_type="int8")
        segments, info = model.transcribe(audio_path, language="es", vad_filter=True)
        local_text = " ".join(s.text.strip() for s in segments)
        result["local"] = {
            "segundos": round(time.perf_counter() - t0, 2),
            "chars": len(local_text),
        }
        # Desacuerdo entre motores: WER(local→worker) — sin ground truth humano,
        # mide cuánto divergen; un valor alto en frases cortas indica problemas.
        if local_text and worker_text:
            result["wer_worker_vs_local"] = round(_wer(local_text, worker_text), 4)
    except ImportError:
        result["local"] = {"error": "faster-whisper no instalado"}

    return result


def bench_tts() -> dict:
    from yunta.cli import _load_dotenv
    _load_dotenv()
    from yunta.tts import TTSProvider, chunk_text_by_sentences

    p = TTSProvider()
    sentence = "Esta es una prueba de latencia de síntesis de voz para Yunta."
    t0 = time.perf_counter()
    audio, source = p.synthesize(sentence)
    elapsed = round(time.perf_counter() - t0, 2)
    chunks = chunk_text_by_sentences(" ".join([sentence] * 10))
    return {
        "fuente": source,
        "latencia_sintesis_s": elapsed,
        "bytes_audio": len(audio) if audio else 0,
        "chunks_por_10_frases": len(chunks),
    }


def bench_vad() -> dict:
    from yunta.cli import _load_dotenv
    _load_dotenv()
    from yunta.voice import VoiceListener

    vl = VoiceListener()
    vl.start()
    print("   🎙️ Habla hacia el micrófono durante ~5s (benchmark VAD)...")
    t0 = time.perf_counter()
    phrase = vl.get(timeout=15)
    elapsed = round(time.perf_counter() - t0, 2)
    vl.stop()
    return {
        "umbral_calibrado": vl.threshold,
        "frase_capturada": bool(phrase),
        "texto": (phrase or "")[:80],
        "segundos_hasta_frase": elapsed,
    }


# ------------------------------- main -------------------------------

def main():
    ap = argparse.ArgumentParser(description="Benchmark del pipeline de voz de yunta")
    ap.add_argument("--fuzzy", action="store_true")
    ap.add_argument("--router", action="store_true")
    ap.add_argument("--stt", action="store_true")
    ap.add_argument("--tts", action="store_true")
    ap.add_argument("--vad", action="store_true", help="requiere micrófono: habla al iniciarlo")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--audio", help="ruta a un audio corto (~30-90s) para STT")
    args = ap.parse_args()

    if args.all:
        args.fuzzy = args.router = args.tts = True
        if args.audio:
            args.stt = True

    results: dict = {"timestamp": datetime.now().isoformat(timespec="seconds")}

    if args.fuzzy:
        print("▶ Fuzzy matcher fonético...")
        results["fuzzy"] = bench_fuzzy()
        print(f"   {results['fuzzy']}")
    if args.router:
        print("▶ Router de palabras clave...")
        results["router"] = bench_router()
        print(f"   {results['router']}")
    if args.stt:
        if not args.audio:
            print("⚠️ --stt requiere --audio <ruta>")
        else:
            print(f"▶ STT (worker vs local): {args.audio}")
            results["stt"] = bench_stt(args.audio)
            print(f"   {results['stt']}")
    if args.tts:
        print("▶ TTS (Edge TTS)...")
        results["tts"] = bench_tts()
        print(f"   {results['tts']}")
    if args.vad:
        print("▶ VAD con micrófono real...")
        results["vad"] = bench_vad()
        print(f"   {results['vad']}")

    out = Path(".yunta") / f"voice_bench_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n📄 Resultados guardados en: {out}")


if __name__ == "__main__":
    main()
