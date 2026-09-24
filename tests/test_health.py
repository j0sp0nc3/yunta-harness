import json

from yunta.api import Usage
from yunta.health import aggregate, record_snapshot


def test_record_snapshot_appends_jsonl(tmp_path):
    path = tmp_path / "health.jsonl"
    usage = Usage(input_tokens=100, output_tokens=50, turns=3, tool_errors=1, cached_tokens=10)
    usage.tool_counts = {"read_file": 4}

    record_snapshot(usage, doom_loop_triggers=0, model="openai/gpt-4o", path=path)
    record_snapshot(usage, doom_loop_triggers=1, model="openai/gpt-4o", path=path)

    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["turns"] == 3
    assert first["model"] == "openai/gpt-4o"
    assert first["doom_loop_triggers"] == 0
    assert json.loads(lines[1])["doom_loop_triggers"] == 1


def test_aggregate_empty_returns_zero_sessions(tmp_path):
    assert aggregate(tmp_path / "no-existe.jsonl") == {"sessions": 0}


def test_aggregate_computes_arithmetic_correctly(tmp_path):
    path = tmp_path / "health.jsonl"
    u1 = Usage(turns=2, tool_errors=1, cached_tokens=0)
    u1.tool_counts = {"read_file": 9}  # total_tool_calls == 9
    u2 = Usage(turns=1, tool_errors=0, cached_tokens=0)
    u2.tool_counts = {"bash": 1}  # total_tool_calls == 1

    record_snapshot(u1, doom_loop_triggers=1, path=path)
    record_snapshot(u2, doom_loop_triggers=0, path=path)

    stats = aggregate(path)
    assert stats["sessions"] == 2
    assert stats["total_turns"] == 3
    assert stats["total_tool_calls"] == 10
    assert stats["total_tool_errors"] == 1
    assert stats["error_rate"] == 0.1  # 1/10
    assert stats["total_doom_loop_triggers"] == 1
    assert 0 <= stats["health_score"] <= 100


def test_aggregate_respects_limit(tmp_path):
    path = tmp_path / "health.jsonl"
    for i in range(5):
        record_snapshot(Usage(turns=1), doom_loop_triggers=0, path=path)
    stats = aggregate(path, limit=2)
    assert stats["sessions"] == 2


def test_aggregate_perfect_session_scores_100(tmp_path):
    path = tmp_path / "health.jsonl"
    u = Usage(turns=1, tool_errors=0, cached_tokens=0)
    u.tool_counts = {"read_file": 5}
    record_snapshot(u, doom_loop_triggers=0, path=path)
    stats = aggregate(path)
    assert stats["health_score"] == 100.0
