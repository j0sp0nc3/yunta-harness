"""Tests para yunta/llm_call_telemetry.py (Fase 10, V7-5, 2026-09-22)."""
import json

from yunta.llm_call_telemetry import aggregate_llm_calls, record_llm_call


def test_record_and_aggregate_llm_call_roundtrip(tmp_path):
    path = tmp_path / "llm_calls.jsonl"
    record_llm_call(
        model="openai/glm-4.7", input_tokens=1000, output_tokens=100,
        elapsed_secs=10.0, finish_reason_raw="stop", streaming=False, path=path,
    )
    record_llm_call(
        model="openai/glm-4.7", input_tokens=2000, output_tokens=200,
        elapsed_secs=20.0, finish_reason_raw="length", streaming=True, tool_calls=2, path=path,
    )

    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["model"] == "openai/glm-4.7"
    assert first["finish_reason_raw"] == "stop"
    second = json.loads(lines[1])
    assert second["tool_calls"] == 2
    assert second["streaming"] is True


def test_aggregate_llm_calls_empty_returns_zero(tmp_path):
    assert aggregate_llm_calls(tmp_path / "no-existe.jsonl") == {"calls": 0}


def test_aggregate_llm_calls_computes_tokens_per_sec_and_truncation_ratio(tmp_path):
    path = tmp_path / "llm_calls.jsonl"
    record_llm_call(
        model="m", input_tokens=100, output_tokens=100,
        elapsed_secs=10.0, finish_reason_raw="stop", path=path,
    )
    record_llm_call(
        model="m", input_tokens=100, output_tokens=200,
        elapsed_secs=10.0, finish_reason_raw="length", path=path,
    )
    stats = aggregate_llm_calls(path)
    assert stats["calls"] == 2
    assert stats["total_output_tokens"] == 300
    assert stats["avg_tokens_per_sec"] == 15.0  # 300 tokens / 20s totales
    assert stats["length_truncated_calls"] == 1
    assert stats["length_truncated_ratio"] == 0.5
