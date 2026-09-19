from datetime import date
from pathlib import Path

from .api import Block, BlockType, Message, Role

LESSON_PROMPT = """Auto-evalúa la sesión que termina. Responde EXACTAMENTE en tres líneas:

TAREA: <la tarea principal, en una frase>
RESULTADO: <logrado / parcial / fallido, con una palabra de por qué>
LECCION: <una regla concreta y accionable para futuras sesiones; si todo
salió bien, una práctica que ayudó>

Sin más texto."""

HEADER = "# Lecciones de sesiones anteriores (auto-feedback del harness)\n\n"


class FeedbackStore:
    """Registro persistente de auto-evaluaciones. Las últimas lecciones se
    inyectan en el system prompt al arrancar: el agente aprende de sí mismo."""

    def __init__(self, path: str = ".yunta/learnings.md"):
        self.path = Path(path)

    def append(self, task: str, outcome: str, lesson: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(HEADER, encoding="utf-8")
        line = f"- [{date.today().isoformat()}] {task} → {outcome}. Lección: {lesson}\n"
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line)

    def lessons(self, limit: int = 5) -> list[str]:
        if not self.path.exists():
            return []
        lines = [
            l.strip("- \n")
            for l in self.path.read_text(encoding="utf-8").splitlines()
            if l.startswith("- ")
        ]
        return lines[-limit:]

    def preamble(self, limit: int = 5) -> str:
        lessons = self.lessons(limit)
        if not lessons:
            return ""
        body = "\n".join(f"- {l}" for l in lessons)
        return (
            "\n\n# Lecciones de sesiones anteriores (aprendidas por ti mismo)\n\n"
            f"{body}\n"
        )

    def summarize(self, provider, messages: list[Message]) -> None:
        """Pide al modelo la auto-evaluación de la sesión y la persiste.
        Best-effort: cualquier fallo se ignora silenciosamente."""
        try:
            resp = provider.send(
                [Message(role=Role.USER, content=[Block(type=BlockType.TEXT, text=LESSON_PROMPT)])]
                + messages,
                [],
            )
            text = {b.type: b.text for b in resp.content if b.type == BlockType.TEXT}
            parts = {}
            for line in text.get(BlockType.TEXT, "").splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    parts[k.strip().upper()] = v.strip()
            task = parts.get("TAREA", "(sin registrar)")
            outcome = parts.get("RESULTADO", "desconocido")
            lesson = parts.get("LECCION", "")
            if lesson:
                self.append(task, outcome, lesson)
        except Exception:
            pass
