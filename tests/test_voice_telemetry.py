"""Tests para yunta/voice_telemetry.py (Fase 3, 2026-09-20)."""
import json
from pathlib import Path
from unittest.mock import MagicMock

from yunta.voice_telemetry import aggregate_voice, percentile, record_voice_snapshot


# ==================== V7-2: percentiles y desglose red/procesamiento ====================

def test_percentile_empty_list_returns_zero():
    assert percentile([], 50) == 0.0


def test_percentile_single_value():
    assert percentile([7.5], 50) == 7.5
    assert percentile([7.5], 95) == 7.5


def test_percentile_known_values():
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    assert percentile(values, 50) == 5.5
    assert percentile(values, 0) == 1.0
    assert percentile(values, 100) == 10.0


def test_record_voice_snapshot_includes_network_percentiles(tmp_path):
    path = tmp_path / "voice_health.jsonl"
    record_voice_snapshot(
        total_fragments=5, cloud_fragments=5, local_fragments=0,
        errors_handled=0, breaker_trips=0, elapsed_secs=50.0,
        audio_duration_secs=100.0, outcome="completed",
        network_wait_p50=2.0, network_wait_p95=4.0, network_wait_max=5.0,
        processing_p50=0.5, processing_p95=1.0, processing_max=1.5,
        workers_used=3, path=path,
    )
    entry = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert entry["network_wait_p50"] == 2.0
    assert entry["network_wait_p95"] == 4.0
    assert entry["network_wait_max"] == 5.0
    assert entry["processing_p50"] == 0.5
    assert entry["workers_used"] == 3


def test_record_voice_snapshot_network_fields_default_to_zero(tmp_path):
    """Llamador que no pasa los campos nuevos (compatibilidad hacia atrás)."""
    path = tmp_path / "voice_health.jsonl"
    record_voice_snapshot(
        total_fragments=1, cloud_fragments=1, local_fragments=0,
        errors_handled=0, breaker_trips=0, elapsed_secs=10.0,
        audio_duration_secs=10.0, path=path,
    )
    entry = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert entry["network_wait_p50"] == 0.0
    assert entry["workers_used"] == 1


def test_aggregate_voice_averages_network_percentiles_across_sessions(tmp_path):
    path = tmp_path / "voice_health.jsonl"
    record_voice_snapshot(
        total_fragments=1, cloud_fragments=1, local_fragments=0,
        errors_handled=0, breaker_trips=0, elapsed_secs=10.0, audio_duration_secs=10.0,
        network_wait_p50=2.0, network_wait_p95=3.0, network_wait_max=4.0, path=path,
    )
    record_voice_snapshot(
        total_fragments=1, cloud_fragments=1, local_fragments=0,
        errors_handled=0, breaker_trips=0, elapsed_secs=10.0, audio_duration_secs=10.0,
        network_wait_p50=6.0, network_wait_p95=7.0, network_wait_max=8.0, path=path,
    )
    stats = aggregate_voice(path)
    assert stats["avg_network_wait_p50"] == 4.0
    assert stats["avg_network_wait_p95"] == 5.0
    assert stats["max_network_wait"] == 8.0


def test_record_and_aggregate_hallucinations_filtered(tmp_path):
    path = tmp_path / "voice_health.jsonl"
    record_voice_snapshot(
        total_fragments=10, cloud_fragments=10, local_fragments=0,
        errors_handled=0, breaker_trips=0, elapsed_secs=10.0, audio_duration_secs=10.0,
        hallucinations_filtered=3, path=path,
    )
    record_voice_snapshot(
        total_fragments=10, cloud_fragments=10, local_fragments=0,
        errors_handled=0, breaker_trips=0, elapsed_secs=10.0, audio_duration_secs=10.0,
        hallucinations_filtered=1, path=path,
    )
    entry = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert entry["hallucinations_filtered"] == 3

    stats = aggregate_voice(path)
    assert stats["total_hallucinations_filtered"] == 4
    assert stats["hallucinations_per_fragment"] == round(4 / 20, 4)


def test_aggregate_voice_tolerates_old_snapshots_without_new_fields(tmp_path):
    """Snapshots grabados antes de V7-2 no tienen los campos nuevos — el
    agregado no debe romperse, deben aportar 0.0."""
    path = tmp_path / "voice_health.jsonl"
    old_snapshot = {
        "timestamp": 1.0, "total_fragments": 1, "cloud_fragments": 1,
        "local_fragments": 0, "errors_handled": 0, "breaker_trips": 0,
        "elapsed_secs": 10.0, "audio_duration_secs": 10.0, "rtf": 1.0, "outcome": "completed",
    }
    path.write_text(json.dumps(old_snapshot) + "\n", encoding="utf-8")
    stats = aggregate_voice(path)
    assert stats["avg_network_wait_p50"] == 0.0
    assert stats["total_hallucinations_filtered"] == 0
    assert stats["sessions"] == 1


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
    monkeypatch.chdir(tmp_path)  # aisla los checkpoints de V6-3 (.yunta/scratch)
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
    monkeypatch.chdir(tmp_path)  # aisla los checkpoints de V6-3 (.yunta/scratch)
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
