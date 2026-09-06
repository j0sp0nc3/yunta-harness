import sys

import pytest

sys.path.insert(0, ".")

from yunta.agent import Agent
from yunta.api import Block, BlockType, Response, StopReason
from yunta.tools import bash, delegate, files, memory, search  # noqa: F401 — registro
from yunta.tools import registry


class FakeProvider:
    """Provider falso programable: cola de respuestas + registro de lo recibido."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.received = []

    def send(self, messages, tools):
        self.received.append((list(messages), tools))
        return self.responses.pop(0)

    def tool_names(self, call=0):
        return [d.name for d in self.received[call][1]]


def tool_use(id, name, input):
    return Block(
        type=BlockType.TOOL_USE, tool_use_id=id, tool_name=name, tool_input=input
    )


def text(t):
    return Response(
        content=[Block(type=BlockType.TEXT, text=t)], stop_reason=StopReason.END_TURN
    )


def read_file_then(final):
    """Dos turnos: llama read_file sobre README.md y luego responde `final`."""
    return [
        Response(
            content=[tool_use("1", "read_file", '{"path":"README.md"}')],
            stop_reason=StopReason.TOOL_USE,
        ),
        text(final),
    ]


@pytest.fixture(autouse=True)
def reset_delegate_provider():
    delegate.set_provider(None)
    yield
    delegate.set_provider(None)


ALL_NAMES = set(registry.definitions() and [d.name for d in registry.definitions()])


def test_subset_sends_only_subset_definitions():
    p = FakeProvider(read_file_then("listo"))
    a = Agent(
        provider=p,
        system="s",
        confirm=lambda n, d: True,
        tools=[registry.get("read_file"), registry.get("grep")],
    )
    a.send("x")
    assert set(p.tool_names()) == {"read_file", "grep"}


def test_subset_accepts_names_of_registered_tools():
    p = FakeProvider(read_file_then("listo"))
    Agent(
        provider=p,
        system="s",
        tools=[registry.get("glob")],
    ).send("x")
    assert p.tool_names() == ["glob"]


def test_no_subset_sends_all_definitions():
    p = FakeProvider(read_file_then("listo"))
    a = Agent(provider=p, system="s", confirm=lambda n, d: True)
    a.send("x")
    assert set(p.tool_names()) == ALL_NAMES


def test_subset_only_filters_definitions_not_execution():
    """La ejecución sigue siendo registry.get: una tool fuera del subset
    no se anuncia pero sí se ejecuta si el modelo la invoca."""
    p = FakeProvider(read_file_then("ok"))
    a = Agent(provider=p, system="s", confirm=lambda n, d: True, tools=[registry.get("read_file")])
    a.send("x")
    results = [b for b in a.messages[2].content if b.type == BlockType.TOOL_RESULT]
    assert results[0].is_error is False
    assert "yunta" in results[0].tool_result


def test_delegate_research_runs_subagent_and_returns_final_text():
    sub = FakeProvider(read_file_then("hallazgo: la lógica está en yunta/agent.py"))
    delegate.set_provider(sub)
    out = registry.get("delegate_research").fn('{"task":"¿dónde está el bucle?"}')
    assert out == "hallazgo: la lógica está en yunta/agent.py"
    # El subagente solo recibió las tools de lectura y la tarea como prompt
    assert set(sub.tool_names()) == {"read_file", "grep", "glob"}
    first_user = sub.received[0][0][0].content[0].text
    assert first_user == "¿dónde está el bucle?"


def test_delegate_research_without_provider_raises():
    with pytest.raises(RuntimeError, match="delegate no configurado"):
        registry.get("delegate_research").fn('{"task":"x"}')


def test_delegate_research_requires_task():
    delegate.set_provider(FakeProvider([]))
    with pytest.raises(ValueError, match="task es obligatorio"):
        registry.get("delegate_research").fn("{}")
    with pytest.raises(ValueError, match="task es obligatorio"):
        registry.get("delegate_research").fn('{"task":""}')


def test_delegate_research_is_registered_without_approval():
    t = registry.get("delegate_research")
    assert t is not None
    assert t.requires_approval is False
    assert "task" in t.parameters["required"]


def test_subagent_nested_tool_loop_completes():
    """El subagente encadena dos tool_use antes de responder."""
    p = FakeProvider(
        [
            Response(
                content=[tool_use("1", "glob", '{"pattern":"*.py"}')],
                stop_reason=StopReason.TOOL_USE,
            ),
            Response(
                content=[tool_use("2", "grep", '{"pattern":"_loop"}')],
                stop_reason=StopReason.TOOL_USE,
            ),
            text("está en yunta/agent.py"),
        ]
    )
    delegate.set_provider(p)
    out = registry.get("delegate_research").fn('{"task":"localiza _loop"}')
    assert out == "está en yunta/agent.py"
    assert len(p.received) == 3
