"""P8: presupuesto de sesión visible.

Las sesiones quemaban cientos de miles de tokens sin aviso (evidencia del
dogfooding). Este módulo expone SessionBudget: acumula el consumo de la
sesión, avisa UNA vez al superar el 70% y al 90% dispara el guardado de
estado (P7) para cierre ordenado en vez de morir por cuota a ciegas."""


class SessionBudget:
    def __init__(self, max_session_tokens: int = 200_000):
        self.max_session_tokens = max_session_tokens
        self.used = 0
        self._warned_70 = False
        self._critical_90 = False

    def add(self, tokens: int) -> None:
        self.used += max(0, int(tokens))

    def _pct(self) -> float:
        return self.used / self.max_session_tokens if self.max_session_tokens else 0.0

    def level(self) -> str:
        pct = self._pct()
        if pct >= 0.9:
            return "critical"
        if pct >= 0.7:
            return "warn"
        return "ok"

    def warn_at_70(self) -> bool:
        return self._pct() >= 0.7


def check_budget(budget: SessionBudget, save_state=None) -> None:
    """Efectos del presupuesto: imprime avisos (una vez por umbral) y al 90%
    invoca save_state() para el cierre ordenado (P7)."""
    pct = budget._pct()
    if pct >= 0.9 and not budget._critical_90:
        budget._critical_90 = True
        print(
            "\n[presupuesto] UMBRAL 90% alcanzado ("
            + f"{pct:.0%} consumado, {budget.used:,}/{budget.max_session_tokens:,} tokens). "
            + "Guardando estado para cierre ordenado..."
        )
        if save_state is not None:
            save_state()
    elif pct >= 0.7 and not budget._warned_70:
        budget._warned_70 = True
        print(
            "\n[presupuesto] UMBRAL 70% alcanzado ("
            + f"{pct:.0%} consumado, {budget.used:,}/{budget.max_session_tokens:,} tokens). "
            + "Considera cerrar la tarea o particionarla."
        )
