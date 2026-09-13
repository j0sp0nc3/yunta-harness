"""Módulo de clasificación por intención de tareas en Yunta.

Distingue entre tareas de desarrollo de software (enforzan compuertas SDD,
hooks git pre-commit, validación atómica de sintaxis y búsqueda AST) y tareas
de investigación, consultoría o transcripción/resumen de cátedras (que
bypassean compuertas de código).
"""

from enum import Enum
import os
import re


class TaskIntent(Enum):
    SOFTWARE_IMPLEMENTATION = "software_implementation"
    RESEARCH_AND_CONSULTING = "research_and_consulting"


class ReasoningLevel(Enum):
    OFF = "off"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


SOFTWARE_KEYWORDS = [
    r"\bcode\b", r"\bcódigo\b", r"\bfix\b", r"\brefactor\b", r"\btest\b", r"\btests\b",
    r"\bpytest\b", r"\bdotnet\b", r"\bclass\b", r"\bfunction\b", r"\bfunción\b",
    r"\bdef\b", r"\bimport\b", r"\bbug\b", r"\berror\b", r"\bpatch\b", r"\bcommit\b",
    r"\brepository\b", r"\brepositorio\b", r"\bendpoint\b", r"\bapi\b", r"\bscript\b",
    r"\bfile\b", r"\barchivo\b", r"\bbuild\b", r"\bcompil\b"
]

RESEARCH_KEYWORDS = [
    r"\bcátedra\b", r"\bclase\b", r"\bmedicina\b", r"\bmedica\b", r"\bmédica\b",
    r"\bresumen\b", r"\bresumir\b", r"\btranscrib\b", r"\btranscripción\b",
    r"\b audio\b", r"\bvoz\b", r"\bvoice\b", r"\blecture\b", r"\bflashcard\b",
    r"\banki\b", r"\bglosario\b", r"\bconsultoría\b", r"\bconsulting\b",
    r"\binvestigación\b", r"\bresearch\b", r"\banálisis\b", r"\banalize\b"
]

DEEP_REASONING_KEYWORDS = [
    r"razonamiento profundo", r"piensa profundamente", r"analiza en detalle",
    r"think hard", r"deep reasoning", r"deep think", r"analiza a fondo",
    r"pensamiento profundo", r"razona profundamente", r"modo profundo",
    r"evalúa exhaustivamente", r"arquitectura", r"refactorización compleja",
    r"causa raíz", r"root cause", r"diagnóstico profundo", r"demostración"
]

FAST_KEYWORDS = [
    r"rápido", r"rapido", r"sin pensar", r"quick", r"fast", r"sencillo",
    r"solo crea", r"crea un archivo", r"dime la hora", r"hola", r"gracias"
]


class IntentClassifier:
    """Clasifica la intención de un prompt para enrutar el flujo de ejecución."""

    @staticmethod
    def classify(prompt: str) -> TaskIntent:
        if not prompt or not prompt.strip():
            return TaskIntent.RESEARCH_AND_CONSULTING

        prompt_lower = prompt.lower()

        # Si el prompt menciona explícitamente audios, cátedras o investigación médica
        research_score = sum(
            1 for kw in RESEARCH_KEYWORDS if re.search(kw, prompt_lower)
        )
        software_score = sum(
            1 for kw in SOFTWARE_KEYWORDS if re.search(kw, prompt_lower)
        )

        if research_score > software_score:
            return TaskIntent.RESEARCH_AND_CONSULTING
        elif software_score > 0:
            return TaskIntent.SOFTWARE_IMPLEMENTATION

        # Por defecto, si no hay señales claras de código, se trata como consultoría/investigación
        return TaskIntent.RESEARCH_AND_CONSULTING

    @staticmethod
    def evaluate_reasoning(prompt: str, user_override: str | None = None) -> ReasoningLevel:
        """Determina el nivel de razonamiento profundo a aplicar.
        
        Soporta forzado por usuario (overrides 'high', 'medium', 'low', 'off')
        o auto-detección inteligente basada en complejidad y palabras clave del prompt.
        """
        # 1. Override explícito configurado por usuario (CLI, REPL o ENV)
        override = user_override or os.environ.get("YUNTA_THINK")
        if override:
            clean = override.lower().strip()
            if clean in ("high", "profundo", "on", "1", "true"):
                return ReasoningLevel.HIGH
            elif clean in ("medium", "medio"):
                return ReasoningLevel.MEDIUM
            elif clean in ("low", "bajo"):
                return ReasoningLevel.LOW
            elif clean in ("off", "desactivado", "false", "0"):
                return ReasoningLevel.OFF

        if not prompt or not prompt.strip():
            return ReasoningLevel.OFF

        prompt_lower = prompt.lower()

        # 2. Búsqueda de palabras clave explícitas en el prompt de usuario
        for kw in DEEP_REASONING_KEYWORDS:
            if re.search(kw, prompt_lower):
                return ReasoningLevel.HIGH

        for kw in FAST_KEYWORDS:
            if re.search(kw, prompt_lower):
                return ReasoningLevel.OFF

        # 3. Heurística de complejidad automática
        # Preguntas analíticas, prompts de larga extensión o diagnósticos de errores
        if len(prompt) > 250 or "por qué" in prompt_lower or "why" in prompt_lower or "cómo funciona" in prompt_lower or "diagnostica" in prompt_lower:
            return ReasoningLevel.MEDIUM

        return ReasoningLevel.OFF

    @staticmethod
    def should_enforce_sdd(intent: TaskIntent) -> bool:
        """Indica si la intención requiere compuertas de desarrollo de software SDD."""
        return intent == TaskIntent.SOFTWARE_IMPLEMENTATION

