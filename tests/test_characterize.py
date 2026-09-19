import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, ".")

from yunta.tools import characterize  # noqa: F401 — registro vía decorador
from yunta.tools import registry


def _call(path, function, sample_args=None):
    raw = json.dumps({"path": path, "function": function, "sample_args": sample_args or {}})
    return registry.get("characterize_function").fn(raw)


def _run_generated_test(test_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(test_path)],
        capture_output=True, text=True,
    )


def test_characterize_is_registered_with_approval():
    t = registry.get("characterize_function")
    assert t is not None
    assert t.requires_approval is True
    assert "path" in t.parameters["required"]
    assert "function" in t.parameters["required"]


def test_characterize_pure_function_generates_passing_test(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "target.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    out = _call("target.py", "add", {"a": 2, "b": 3})

    test_path = tmp_path / "tests" / "test_characterize_target_add.py"
    assert test_path.exists()
    assert "resultado capturado" in out
    assert "5" in out

    result = _run_generated_test(test_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_characterize_function_that_raises_generates_raises_test(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "target.py").write_text(
        "def divide(a, b):\n    return a / b\n", encoding="utf-8"
    )

    out = _call("target.py", "divide", {"a": 1, "b": 0})

    test_path = tmp_path / "tests" / "test_characterize_target_divide.py"
    assert test_path.exists()
    assert "ZeroDivisionError" in out

    result = _run_generated_test(test_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_characterize_rejects_function_calling_open(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "target.py").write_text(
        "def read_it(path):\n    with open(path) as f:\n        return f.read()\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="efectos secundarios"):
        _call("target.py", "read_it", {"path": "x"})


def test_characterize_rejects_function_by_name_prefix(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "target.py").write_text(
        "def write_report(x):\n    return x * 2\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="efectos secundarios"):
        _call("target.py", "write_report", {"x": 1})


def test_characterize_missing_function_raises_clear_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "target.py").write_text("def foo():\n    pass\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no se encontró"):
        _call("target.py", "bar", {})


def test_characterize_non_python_file_rejected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "target.txt").write_text("no es python", encoding="utf-8")
    with pytest.raises(ValueError, match="solo soporta archivos Python"):
        _call("target.txt", "foo", {})


def test_characterize_capture_timeout_reported_as_runtime_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(characterize, "_CAPTURE_TIMEOUT", 1)
    (tmp_path / "slow.py").write_text("def spin():\n    while True:\n        pass\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="no se pudo capturar"):
        _call("slow.py", "spin", {})
