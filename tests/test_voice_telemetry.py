"""Tests para yunta/voice_telemetry.py (Fase 3, 2026-09-20)."""
import json
from pathlib import Path
from unittest.mock import MagicMock

from yunta.voice_telemetry import aggregate_voice, record_voice_snapshot


def test_record_and_aggregate_voice_snapshot_roundtrip(tmp_path):
    path = tmp_path / "voice_health.jsonl"
    record_voice_snapshot(
        total_fragments=10, cloud_fragments=8, local_fragments=2,
        errors_handled=3, breaker_trips=1, elapsed_secs=60.0,
        audio_duration_secs=120.0, outcome="completed", path=path,
    )
    record_voice_snapshot(
        total_fragments=20, cloud_fragments=20, local_fragments=0,
        errors_handled=0, breaker_trips=0, elapsed_secs=30.0,
        audio_duration_secs=60.0, outcome="completed", path=path,
    )

    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["total_fragments"] == 10
    assert first["rtf"] == 2.0  # 120/60

    stats = aggregate_voice(path)
    assert stats["sessions"] == 2
    assert stats["total_fragments"] == 30
    assert stats["total_cloud_fragments"] == 28
    assert stats["cloud_ratio"] == round(28 / 30, 4)
    assert stats["total_breaker_trips"] == 1


def test_aggregate_voice_empty_returns_zero_sessions(tmp_path):
    assert aggregate_voice(tmp_path / "no-existe.jsonl") == {"sessions": 0}


def test_record_voice_snapshot_zero_elapsed_does_not_crash(tmp_path):
    path = tmp_path / "voice_health.jsonl"
    record_voice_snapshot(
        total_fragments=1, cloud_fragments=1, local_fragments=0,
        errors_handled=0, breaker_trips=0, elapsed_secs=0.0,
        audio_duration_secs=5.0, path=path,
    )
    entries = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert entries["rtf"] == 0.0


def test_transcribe_large_audio_records_telemetry_on_completion(tmp_path, monkeypatch):
    from yunta.voice import AudioChunker, AudioTranscriber

    class FakeTranscriber(AudioTranscriber):
        def transcribe_with_meta(self, file_path, prompt="", skip_cloud=False):
            return "texto", {"source": "cloud", "cloud_attempted": True, "cloud_failed": False}

    chunker = AudioChunker(FakeTranscriber())
    chunks = [str(tmp_path / f"c{i}.mp3") for i in range(3)]
    for c in chunks:
        Path(c).write_bytes(b"\xff\xfb\x90\x00" + b"x" * 512)
    chunker.split_audio_by_silence = lambda fp, *a, **k: chunks

    recorded = MagicMock()
    monkeypatch.setattr("yunta.voice_telemetry.record_voice_snapshot", recorded)

    chunker.transcribe_large_audio(str(tmp_path / "audio.mp3"))

    recorded.assert_called_once()
    _, kwargs = recorded.call_args
    assert kwargs["total_fragments"] == 3
    assert kwargs["cloud_fragments"] == 3
    assert kwargs["outcome"] == "completed"


def test_telemetry_recording_failure_does_not_break_transcription(tmp_path, monkeypatch):
    from yunta.voice import AudioChunker, AudioTranscriber

    class FakeTranscriber(AudioTranscriber):
        def transcribe_with_meta(self, file_path, prompt="", skip_cloud=False):
            return "texto ok", {"source": "cloud", "cloud_attempted": True, "cloud_failed": False}

    chunker = AudioChunker(FakeTranscriber())
    chunks = [str(tmp_path / "c0.mp3")]
    Path(chunks[0]).write_bytes(b"\xff\xfb\x90\x00" + b"x" * 512)
    chunker.split_audio_by_silence = lambda fp, *a, **k: chunks

    monkeypatch.setattr(
        "yunta.voice_telemetry.record_voice_snapshot",
        MagicMock(side_effect=Exception("disco lleno")),
    )

    result = chunker.transcribe_large_audio(str(tmp_path / "audio.mp3"))
    assert "texto ok" in result
