"""Métricas de calidad del pipeline de voz (V5-3, router de keywords).

Estos tests actúan como gate de regresión: si la precisión del fuzzy matcher
o del router baja del umbral, la suite falla y obliga a revisar antes de
commitear. Los umbrales son la línea base medida el 2026-09-18.
"""

import random

from yunta.voice import normalize_voice_response, route_keyword, load_voice_keywords

# Palabras de referencia por acción esperada
REFERENCE_WORDS = {
    "s": ["si", "aprobado", "dale", "ok", "avanzar", "correcto", "listo"],
    "c": ["no", "cancelar", "rechazado", "stop", "detener", "alto"],
    "e": ["editar", "modificar", "cambiar", "corregir"],
    "siempre": ["siempre"],
}

# Palabras que NO deben mapear a acción (frases técnicas comunes)
NEGATIVE_WORDS = [
    "docker", "python", "transcribir", "analizar", "informe", "dijkstra",
    "algoritmo", "sesión", "contexto", "métrica", "escribir", "archivo",
]


def _mutate(word: str, rng: random.Random) -> str:
    """Aplica una mutación fonética típica de Whisper: borrar, permutar o cambiar vocal."""
    if len(word) < 3:
        return word + "e"
    ops = rng.randint(0, 2)
    i = rng.randrange(len(word))
    if ops == 0:  # borrado
        return word[:i] + word[i + 1:]
    if ops == 1 and i + 1 < len(word):  # permutación adyacente
        return word[:i] + word[i + 1] + word[i] + word[i + 2:]
    return word[:i] + rng.choice("aeiou") + word[i + 1:]  # vocalización


def test_fuzzy_accuracy_over_mutations():
    """Precisión del fuzzy ≥90% sobre variantes fonéticas de una palabra (línea base: 97%)."""
    rng = random.Random(42)
    correct = total = 0
    failures = []
    for expected, words in REFERENCE_WORDS.items():
        for word in words:
            for _ in range(10):  # 10 mutaciones aleatorias por palabra
                mutated = _mutate(word, rng)
                if mutated == word:
                    continue
                total += 1
                got = normalize_voice_response(mutated)
                if got == expected:
                    correct += 1
                else:
                    failures.append(f"{word}→{mutated}: esperaba {expected}, obtuve {got!r}")
    accuracy = correct / total
    assert accuracy >= 0.90, f"Precisión fuzzy {accuracy:.1%} < 90%. Fallos: {failures[:10]}"


def test_fuzzy_no_false_positives_on_technical_words():
    """Las palabras técnicas NO se mapean a acciones (0 falsos positivos)."""
    for word in NEGATIVE_WORDS:
        got = normalize_voice_response(word)
        assert got == word, f"Falso positivo: {word!r} se mapeó a {got!r}"


def test_router_coverage_and_precision():
    """Todas las keywords por defecto rutean; frases largas nunca rutean."""
    keywords = load_voice_keywords()
    hits = 0
    for phrase, cmd in keywords.items():
        if route_keyword(phrase, keywords) == cmd:
            hits += 1
    assert hits == len(keywords), f"{len(keywords) - hits} keywords no rutean"

    long_phrases = [
        "analiza el siguiente fragmento de código por favor",
        "dime qué métricas de rendimiento tiene el servidor",
        "quiero salir de compras al mediodía con amigos",
    ]
    for phrase in long_phrases:
        assert route_keyword(phrase) is None, f"Falso positivo del router: {phrase!r}"
