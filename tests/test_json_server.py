import io
import json
import sys
import pytest

sys.path.insert(0, ".")

from yunta.api import Block, BlockType, Response, StopReason
from yunta.json_server import serve_json_stream, serve_json_stdin


class FakeProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.received = []

    def model(self):
        return "fake-model"

    def send(self, messages, tools, on_text=None):
        self.received.append((list(messages), tools))
        r = self.responses.pop(0)
        if on_text:
            for b in r.content:
                if b.type == BlockType.TEXT:
                    on_text(b.text)
        return r


def text(t):
    return Response(
        content=[Block(type=BlockType.TEXT, text=t)], stop_reason=StopReason.END_TURN
    )


def test_serve_json_stream_emits_jsonl_events(capsys):
    p = FakeProvider([text("Hola desde Yunta")])
    serve_json_stream("Hola", provider=p)
    captured = capsys.readouterr().out
    lines = [json.loads(l) for l in captured.strip().split("\n") if l.strip()]

    events = [l["type"] for l in lines]
    assert "system" in events
    assert "text_delta" in events
    assert "done" in events
    assert "usage" in events

    done_evt = next(l for l in lines if l["type"] == "done")
    assert done_evt["final_text"] == "Hola desde Yunta"


def test_serve_json_stdin_processes_prompt(monkeypatch, capsys):
    p = FakeProvider([text("Respuesta stdin")])
    input_data = json.dumps({"prompt": "Test prompt"}) + "\n"
    monkeypatch.setattr("sys.stdin", io.StringIO(input_data))

    serve_json_stdin(provider=p)
    captured = capsys.readouterr().out
    lines = [json.loads(l) for l in captured.strip().split("\n") if l.strip()]
    events = [l["type"] for l in lines]
    assert "done" in events
