import sys
import pytest

sys.path.insert(0, ".")

from yunta.api import Block, BlockType, Response, StopReason
from yunta.tools import subtask
from yunta.tools import registry


class FakeProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.received = []

    def send(self, messages, tools):
        self.received.append((list(messages), tools))
        return self.responses.pop(0)

    def tool_names(self, call=0):
        return [d.name for d in self.received[call][1]]


def text(t):
    return Response(
        content=[Block(type=BlockType.TEXT, text=t)], stop_reason=StopReason.END_TURN
    )


@pytest.fixture(autouse=True)
def reset_subtask_provider():
    subtask.set_provider(None)
    yield
    subtask.set_provider(None)


def test_delegate_subtask_is_registered_with_approval():
    t = registry.get("delegate_subtask")
    assert t is not None
    assert t.requires_approval is True
    assert "task" in t.parameters["required"]
    assert "target_files" in t.parameters["required"]


def test_delegate_subtask_without_provider_raises():
    with pytest.raises(RuntimeError, match="delegate_subtask no configurado"):
        registry.get("delegate_subtask").fn('{"task":"fix bug", "target_files":["a.py"]}')


def test_delegate_subtask_validates_args():
    subtask.set_provider(FakeProvider([]))
    # Missing task
    with pytest.raises(ValueError, match="task es obligatorio"):
        registry.get("delegate_subtask").fn('{"target_files":["a.py"]}')
    # Empty target_files
    with pytest.raises(ValueError, match="target_files debe ser una lista"):
        registry.get("delegate_subtask").fn('{"task":"test", "target_files":[]}')
    # More than 2 files
    with pytest.raises(ValueError, match="máximo 2 archivos"):
        registry.get("delegate_subtask").fn('{"task":"test", "target_files":["a.py", "b.py", "c.py"]}')


def test_delegate_subtask_runs_subagent_and_returns_text():
    p = FakeProvider([text("Subtarea completada exitosamente")])
    subtask.set_provider(p)
    out = registry.get("delegate_subtask").fn(
        '{"task": "Actualizar función helper", "target_files": ["yunta/utils.py"]}'
    )
    assert out == "Subtarea completada exitosamente"
    assert "yunta/utils.py" in p.received[0][0][0].content[0].text
    names = set(p.tool_names())
    assert "read_file" in names
    assert "write_file" in names
    assert "str_replace" in names
