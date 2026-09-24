"""Módulo de decisiones rápidas System One / JEV para Yunta.

Agnóstico al proveedor por construcción (Regla 1 y 2 de AGENTS.md):
- Puede conectarse a endpoints nativos de JEV (TypeSafe AI u otros).
- Puede usar cualquier modelo local o remoto de inferencia rápida
  (ej. Ollama, Groq, OpenAI, Gemini Flash Lite) vía JEV_MODEL / JEV_API_BASE.
- Emite micro-decisiones tipadas (Noul/booleano, Choice/categórico, Score/numérico)
  para evaluar riesgo de herramientas sin acoplarse a un vendor específico.
"""

from dataclasses import dataclass
import json
import os
import urllib.error
import urllib.request


@dataclass
class JevAssessment:
    """Evaluación estructurada emitida para una llamada de herramienta."""
    is_destructive: bool
    destructive_prob: float
    risk_score: int
    action: str  # "allow", "ask_user", "block"
    confidence: float
    raw: dict


class JevClient:
    """Cliente neutral y agnóstico para decisiones rápidas de System One."""

    DEFAULT_TIMEOUT = 3.0

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        api_base: str | None = None,
        timeout: float | None = None,
        provider=None,
    ):
        self.model = (
            model
            or os.environ.get("JEV_MODEL", "")
        ).strip()
        self.api_key = (
            api_key
            or os.environ.get("JEV_API_KEY", "")
        ).strip()
        self.api_base = (
            api_base
            or os.environ.get("JEV_API_BASE", "")
        ).strip()
        self.timeout = (
            timeout
            if timeout is not None
            else float(os.environ.get("JEV_TIMEOUT", str(self.DEFAULT_TIMEOUT)))
        )
        self._provider = provider

    @property
    def is_configured(self) -> bool:
        """Configurado si se define una clave, un endpoint o un modelo de decisión."""
        return bool(self.api_key or self.api_base or self.model or self._provider)

    def evaluate(self, state: dict, questions: dict) -> dict:
        """Evalúa el estado contra preguntas tipadas usando el backend configurado.

        Soporta:
        1. Endpoints HTTP dedicados a System One / micro-decisiones (vía JEV_API_BASE).
        2. Modelos LLM/SLM rápidos neutrales (vía JEV_MODEL o el Provider de Yunta).
        """
        if not self.is_configured:
            raise ValueError(
                "JEV no está configurado. Especifica JEV_MODEL (ej. ollama/qwen2.5:0.5b) "
                "o JEV_API_BASE para tu endpoint de decisiones."
            )

        # Modo 1: Endpoint HTTP dedicado (si api_base está definido y apunta a un servicio de decisiones)
        if self.api_base and not self.model:
            return self._evaluate_native(state, questions)

        # Modo 2: Modelo rápido agnóstico (a través del Provider neutral de Yunta)
        return self._evaluate_llm(state, questions)

    def _evaluate_native(self, state: dict, questions: dict) -> dict:
        """Despacho a endpoint HTTP de micro-decisiones."""
        if not self.api_base:
            raise ValueError("JEV_API_BASE no está configurado.")

        payload = json.dumps({"state": state, "questions": questions}).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "yunta-harness/jev",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(
            self.api_base,
            data=payload,
            headers=headers,
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict) and "decisions" in data:
                return data["decisions"]
            return data

    def _evaluate_llm(self, state: dict, questions: dict) -> dict:
        """Evaluación agnóstica usando el Provider neutral de Yunta (sin SDKs externos)."""
        from .api import Block, BlockType, Message, Role
        from .provider import LiteLLMProvider

        provider = self._provider
        if provider is None:
            chosen_model = self.model or os.environ.get("LLM_MODEL", "")
            if not chosen_model:
                raise ValueError("No hay modelo configurado para JEV (define JEV_MODEL o LLM_MODEL).")
            provider = LiteLLMProvider(model=chosen_model)

        prompt = (
            "Eres un evaluador de decisiones rápidas tipo System One. "
            "Analiza el siguiente contexto de herramienta y responde ÚNICAMENTE con un JSON válido "
            "con las decisiones exactas solicitadas sin explicaciones ni markdown:\n\n"
            f"ESTADO: {json.dumps(state, ensure_ascii=False)}\n"
            f"PREGUNTAS: {json.dumps(questions, ensure_ascii=False)}\n\n"
            "Formato de respuesta obligatorio:\n"
            "{\n"
            '  "destructive": {"value": true/false, "probability": 0.0-1.0},\n'
            '  "risk": {"value": 1-5, "confidence": 0.0-1.0},\n'
            '  "action": {"value": "allow"|"ask_user"|"block", "confidence": 0.0-1.0}\n'
            "}"
        )

        resp = provider.send(
            messages=[Message(role=Role.USER, content=[Block(type=BlockType.TEXT, text=prompt)])],
            tools=[],
        )
        content = ""
        for b in resp.content:
            if b.type == BlockType.TEXT and b.text:
                content += b.text

        clean_json = content.strip().strip("```json").strip("```").strip()
        try:
            return json.loads(clean_json)
        except Exception:
            return {
                "destructive": {"value": False, "probability": 0.0},
                "risk": {"value": 2, "confidence": 0.5},
                "action": {"value": "allow", "confidence": 0.5},
            }


class JevGatekeeper:
    """Gatekeeper de seguridad agnóstico para llamadas de herramientas."""

    def __init__(self, client: JevClient | None = None, provider=None):
        self.client = client or JevClient(provider=provider)

    @classmethod
    def is_available(cls) -> bool:
        """Disponible si el usuario configuró JEV_MODEL, JEV_API_BASE, JEV_API_KEY o JEV_GATEKEEPER=1."""
        enabled_flag = os.environ.get("JEV_GATEKEEPER", "").strip().lower()
        if enabled_flag in ("0", "false", "off", "no"):
            return False
        return bool(
            os.environ.get("JEV_MODEL")
            or os.environ.get("JEV_API_KEY")
            or os.environ.get("JEV_API_BASE")
            or enabled_flag in ("1", "true", "on", "yes")
        )

    def assess_tool(self, tool_name: str, raw_input: str, task_context: str = "") -> JevAssessment | None:
        """Evalúa el nivel de riesgo y potencial destructivo de una herramienta."""
        if not self.client.is_configured:
            return None

        state = {
            "tool": tool_name,
            "arguments": raw_input[:2000],
            "task_context": task_context[:1000],
        }

        questions = {
            "destructive": {
                "type": "noul",
                "instructions": (
                    "Does this command or file modification delete, overwrite, drop, "
                    "reset, or cause irreversible loss of critical data or repository state?"
                ),
            },
            "risk": {
                "type": "score",
                "instructions": (
                    "Rate the risk of this tool invocation from 1 (completely benign/read-only) "
                    "to 5 (critical/destructive/dangerous system command)."
                ),
                "min": 1,
                "max": 5,
            },
            "action": {
                "type": "choice",
                "instructions": "Recommended gatekeeper enforcement action",
                "options": ["allow", "ask_user", "block"],
            },
        }

        try:
            decisions = self.client.evaluate(state, questions)
        except Exception:
            # Fallback seguro: ante fallo de red o timeout, degradar limpiamente
            return None

        dest_data = decisions.get("destructive", {})
        risk_data = decisions.get("risk", {})
        action_data = decisions.get("action", {})

        is_dest = bool(dest_data.get("value", False))
        dest_prob = float(dest_data.get("probability", 1.0 if is_dest else 0.0))
        risk_val = int(risk_data.get("value", 3))
        action_val = str(action_data.get("value", "ask_user"))
        conf = float(action_data.get("confidence", 0.8))

        return JevAssessment(
            is_destructive=is_dest,
            destructive_prob=dest_prob,
            risk_score=risk_val,
            action=action_val,
            confidence=conf,
            raw=decisions,
        )

    def inspect_and_filter(
        self,
        tool_name: str,
        raw_input: str,
        default_requires_approval: bool,
        auto_confirm: bool = False,
    ) -> tuple[bool, str]:
        """Determina si se debe forzar confirmación humana o permitir ejecución.

        Retorna:
            (must_prompt_user: bool, warning_message: str)
        """
        assessment = self.assess_tool(tool_name, raw_input)
        if assessment is None:
            return default_requires_approval and not auto_confirm, ""

        if assessment.is_destructive or assessment.risk_score >= 4 or assessment.action == "block":
            prob_pct = int(assessment.destructive_prob * 100)
            warning = (
                f"[JEV Gatekeeper] ⚠️ Acción de alto riesgo detectada "
                f"(nivel: {assessment.risk_score}/5, probabilidad destructiva: {prob_pct}%). "
                f"Recomendación: {assessment.action.upper()}."
            )
            return True, warning

        if assessment.risk_score <= 1 and not assessment.is_destructive and assessment.action == "allow":
            return False, "[JEV Gatekeeper] ✅ Acción evaluada como segura (nivel 1/5)."

        if auto_confirm:
            return False, ""
        return default_requires_approval, ""
