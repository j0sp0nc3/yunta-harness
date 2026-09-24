"""Módulo de integración con JEV (System One de TypeSafe AI) para Yunta.

Implementa un gatekeeper de decisiones rápidas, probabilísticas y tipadas
(Noul, Choice, Score) para evaluar el riesgo de ejecución de herramientas
y proteger la integridad del entorno sin depender de frameworks externos.
"""

from dataclasses import dataclass
import json
import os
import urllib.error
import urllib.request


@dataclass
class JevAssessment:
    """Evaluación estructurada emitida por JEV para una llamada de herramienta."""
    is_destructive: bool
    destructive_prob: float
    risk_score: int
    action: str  # "allow", "ask_user", "block"
    confidence: float
    raw: dict


class JevClient:
    """Cliente neutral y minimalista para la API de JEV (TypeSafe AI)."""

    DEFAULT_API_BASE = "https://api.typesafe.ai/v1/systemone"
    DEFAULT_TIMEOUT = 3.0

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        timeout: float | None = None,
    ):
        self.api_key = (
            api_key
            or os.environ.get("JEV_API_KEY")
            or os.environ.get("TYPESAFE_API_KEY")
            or ""
        ).strip()
        self.api_base = (
            api_base
            or os.environ.get("JEV_API_BASE")
            or self.DEFAULT_API_BASE
        ).strip()
        self.timeout = (
            timeout
            if timeout is not None
            else float(os.environ.get("JEV_TIMEOUT", str(self.DEFAULT_TIMEOUT)))
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def evaluate(self, state: dict, questions: dict) -> dict:
        """Envía un estado y preguntas tipadas a JEV y retorna las decisiones."""
        if not self.is_configured:
            raise ValueError("JEV_API_KEY no configurada.")

        payload = json.dumps({"state": state, "questions": questions}).encode("utf-8")
        req = urllib.request.Request(
            self.api_base,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "yunta-harness/jev",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict) and "decisions" in data:
                return data["decisions"]
            return data


class JevGatekeeper:
    """Gatekeeper de seguridad para llamadas de herramientas usando JEV."""

    def __init__(self, client: JevClient | None = None):
        self.client = client or JevClient()

    @classmethod
    def is_available(cls) -> bool:
        """Retorna True si JEV está habilitado explícitamente o tiene clave configurada."""
        enabled_flag = os.environ.get("JEV_GATEKEEPER", "").strip().lower()
        if enabled_flag in ("0", "false", "off", "no"):
            return False
        return bool(
            os.environ.get("JEV_API_KEY")
            or os.environ.get("TYPESAFE_API_KEY")
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
            # Fallback seguro: ante fallo de red o timeout de JEV, degradar limpiamente
            return None

        # Parsear respuestas tolerando variaciones de esquema de JEV
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
            # Si JEV no está disponible o falló, se respeta el comportamiento estándar
            return default_requires_approval and not auto_confirm, ""

        # 1. Acciones destructivas o de riesgo crítico (Score >= 4 o destructive)
        # INCLUSO en modo auto_confirm, JEV actúa como salvaguarda dura.
        if assessment.is_destructive or assessment.risk_score >= 4 or assessment.action == "block":
            prob_pct = int(assessment.destructive_prob * 100)
            warning = (
                f"[JEV Gatekeeper] ⚠️ Acción de alto riesgo detectada "
                f"(nivel: {assessment.risk_score}/5, probabilidad destructiva: {prob_pct}%). "
                f"Recomendación: {assessment.action.upper()}."
            )
            return True, warning

        # 2. Acciones clasificadas con certeza como seguras (Score 1 y no destructivo)
        if assessment.risk_score <= 1 and not assessment.is_destructive and assessment.action == "allow":
            # Auto-aprobable con confianza
            return False, "[JEV Gatekeeper] ✅ Acción evaluada como segura (nivel 1/5)."

        # 3. Caso intermedio (Score 2 o 3): mantener la política por defecto
        if auto_confirm:
            return False, ""
        return default_requires_approval, ""
