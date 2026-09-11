import json
import pytest
from yunta.api import Block, BlockType, Response, StopReason
from yunta.tools import bash, files, search  # noqa: F401 — asegura registro de tools
from yunta.tools.delegate import delegate_batch, set_provider


class FakeProvider:
    def __init__(self, responses):
        self.responses = list(responses)

    def send(self, messages, tools, on_text=None):
        if self.responses:
            return self.responses.pop(0)
        return Response(content=[Block(type=BlockType.TEXT, text="subagente listo")], stop_reason=StopReason.END_TURN)

    def model(self):
        return "fake-model"


def test_delegate_batch_without_provider_raises():
    set_provider(None)
    with pytest.raises(RuntimeError, match="falta set_provider"):
        delegate_batch(json.dumps({"tasks": [{"task": "investiga algo"}]}))


def test_delegate_batch_invalid_input_raises():
    p = FakeProvider([])
    set_provider(p)
    with pytest.raises(ValueError, match="lista no vacía"):
        delegate_batch(json.dumps({"tasks": []}))


def test_delegate_batch_runs_tasks_concurrently():
    p = FakeProvider([
        Response(content=[Block(type=BlockType.TEXT, text="resultado subtarea 1")], stop_reason=StopReason.END_TURN),
        Response(content=[Block(type=BlockType.TEXT, text="resultado subtarea 2")], stop_reason=StopReason.END_TURN),
    ])
    set_provider(p)

    payload = json.dumps({
        "tasks": [
            {"task": "investiga modulo A"},
            {"task": "investiga modulo B"},
        ]
    })
    output = delegate_batch(payload)
    assert "investiga modulo A" in output
    assert "investiga modulo B" in output
