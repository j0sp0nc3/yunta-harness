import sys

sys.path.insert(0, ".")

from yunta.api import Block, BlockType, Message, Response, Role, StopReason
from yunta.feedback import FeedbackStore
from yunta.cli import load_system_prompt


class FakeProvider:
    def __init__(self, text):
        self.text = text

    def send(self, messages, tools):
        return Response(
            content=[Block(type=BlockType.TEXT, text=self.text)],
            stop_reason=StopReason.END_TURN,
        )


def test_append_and_lessons(tmp_path):
    store = FeedbackStore(str(tmp_path / "learnings.md"))
    store.append("arreglar bugs", "logrado", "correr tests antes de declarar fix")
    store.append("crear script", "fallido", "verificar sintaxis antes de escribir")
    lessons = store.lessons()
    assert len(lessons) == 2
    assert "correr tests" in lessons[0]
    # las más recientes al final
    assert "verificar sintaxis" in lessons[-1]


def test_preamble_empty_when_no_file(tmp_path):
    store = FeedbackStore(str(tmp_path / "learnings.md"))
    assert store.preamble() == ""


def test_preamble_includes_recent_lessons(tmp_path):
    store = FeedbackStore(str(tmp_path / "learnings.md"))
    for i in range(7):
        store.append(f"tarea {i}", "logrado", f"lección número {i}")
    pre = store.preamble(limit=5)
    assert "lecciones de sesiones anteriores" in pre.lower()
    assert "lección número 6" in pre
    assert "lección número 0" not in pre  # límite respetado


def test_summarize_persists_parsed_lesson(tmp_path):
    store = FeedbackStore(str(tmp_path / "learnings.md"))
    provider = FakeProvider(
        "TAREA: corregir calculadora.py\n"
        "RESULTADO: logrado, tests en verde\n"
        "LECCION: leer el archivo antes de editar\n"
    )
    msgs = [Message(role=Role.USER, content=[Block(type=BlockType.TEXT, text="x")])]
    store.summarize(provider, msgs)
    lessons = store.lessons()
    assert len(lessons) == 1
    assert "corregir calculadora.py" in lessons[0]
    assert "leer el archivo antes de editar" in lessons[0]


def test_summarize_swallows_errors(tmp_path):
    class Boom:
        def send(self, *a, **k):
            raise RuntimeError("sin red")

    store = FeedbackStore(str(tmp_path / "learnings.md"))
    store.summarize(Boom(), [])  # no debe lanzar
    assert store.lessons() == []


def test_system_prompt_includes_feedback_and_honesty():
    prompt = load_system_prompt()  # sin store
    assert "NUNCA afirmes" in prompt
    assert "Verifica tu trabajo" in prompt
