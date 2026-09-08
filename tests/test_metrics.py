import sys
sys.path.insert(0, ".")

from yunta.api import Block, BlockType, Response, StopReason, Usage
from yunta.agent import Agent
from yunta.tools import files, bash  # noqa: F401


class DummyProvider:
    def __init__(self, responses, total_usage=None):
        self.responses = list(responses)
        self.total_usage = total_usage or Usage()

    def send(self, messages, tools):
        resp = self.responses.pop(0)
        self.total_usage = self.total_usage.add(resp.usage)
        return resp


def test_usage_math_and_caching():
    u1 = Usage(input_tokens=100, output_tokens=50, cached_tokens=400, tool_counts={"read_file": 2}, turns=1)
    assert u1.theoretical_raw_tokens == 500
    assert u1.cache_rate == 80.0
    assert u1.total_tool_calls == 2

    u2 = Usage(input_tokens=200, output_tokens=100, cached_tokens=100, tool_counts={"str_replace": 1}, tool_errors=1, turns=1)
    combined = u1.add(u2)

    assert combined.input_tokens == 300
    assert combined.output_tokens == 150
    assert combined.cached_tokens == 500
    assert combined.tool_counts == {"read_file": 2, "str_replace": 1}
    assert combined.total_tool_calls == 3
    assert combined.tool_errors == 1
    assert combined.turns == 2
    assert combined.cache_rate == 62.5
    assert combined.theoretical_raw_tokens == 800


def test_usage_zero_division_safety():
    u = Usage(input_tokens=0, output_tokens=0, cached_tokens=0)
    assert u.cache_rate == 0.0
    assert u.theoretical_raw_tokens == 0
    assert u.total_tool_calls == 0
    summary = u.format_summary()
    assert "Tokens: entrada=0" in summary
    assert "Sin Harness habrías transferido: 0" in summary


def test_usage_format_summary_contents():
    u = Usage(
        input_tokens=5000,
        output_tokens=1200,
        cached_tokens=20000,
        tool_counts={"read_file": 4, "str_replace": 2},
        tool_errors=1,
        turns=3,
    )
    summary = u.format_summary()
    assert "entrada=5,000" in summary
    assert "cacheados=20,000" in summary
    assert "⚡ 80.0% ahorro de caché" in summary
    assert "salida=1,200" in summary
    assert "Sin Harness habrías transferido: 25,000 tokens de entrada" in summary
    assert "Herramientas (6 llamadas): read_file: 4, str_replace: 2 (errores/rechazos: 1)" in summary
    assert "Turnos de interacción: 3" in summary


def test_agent_metrics_tracking():
    p = DummyProvider(
        [
            Response(
                content=[
                    Block(
                        type=BlockType.TOOL_USE,
                        tool_use_id="t1",
                        tool_name="read_file",
                        tool_input='{"path":"README.md"}',
                    )
                ],
                stop_reason=StopReason.TOOL_USE,
                usage=Usage(input_tokens=1000, output_tokens=50, cached_tokens=4000),
            ),
            Response(
                content=[Block(type=BlockType.TEXT, text="contenido leído")],
                stop_reason=StopReason.END_TURN,
                usage=Usage(input_tokens=1200, output_tokens=80, cached_tokens=4000),
            ),
        ]
    )

    agent = Agent(provider=p, system="s", confirm=lambda n, d: True)
    agent.send("lee el archivo")

    usage = agent.total_usage
    assert usage.turns == 1
    assert usage.tool_counts.get("read_file") == 1
    assert usage.total_tool_calls == 1
    assert usage.input_tokens == 2200
    assert usage.output_tokens == 130
    assert usage.cached_tokens == 8000
    assert usage.theoretical_raw_tokens == 10200
    assert usage.cache_rate > 78.0


def test_agent_metrics_records_tool_rejection():
    p = DummyProvider(
        [
            Response(
                content=[
                    Block(
                        type=BlockType.TOOL_USE,
                        tool_use_id="t1",
                        tool_name="bash",
                        tool_input='{"command":"rm -rf /"}',
                    )
                ],
                stop_reason=StopReason.TOOL_USE,
            ),
            Response(content=[Block(type=BlockType.TEXT, text="rechazado")], stop_reason=StopReason.END_TURN),
        ]
    )

    agent = Agent(provider=p, system="s", confirm=lambda n, d: False)
    agent.send("corre comando")

    assert agent.total_usage.tool_counts.get("bash") == 1
    assert agent.total_usage.tool_errors == 1


def test_roi_calculation_telemetry():
    from yunta.api import Usage

    u = Usage(
        input_tokens=1500,
        output_tokens=300,
        cached_tokens=4500,
        turns=5,
        tool_counts={"bash": 4, "str_replace": 2},
        tool_errors=0,
    )
    assert u.cache_rate == 75.0
    tokens_saved = max(0, u.theoretical_raw_tokens - (u.input_tokens + u.cached_tokens))
    savings = (u.cached_tokens * 0.00000095) + (tokens_saved * 0.00000125)
    assert savings > 0
    assert u.total_tool_calls == 6
