import json
import subprocess
from pathlib import Path

from yunta.governance import audit_repository, run_check


def test_audit_empty_directory(tmp_path):
    audit = audit_repository(tmp_path)
    assert audit["healthy"] is False
    assert audit["summary"]["failures"] >= 3  # Falta spec, plan, agents
    assert audit["checks"]["spec"]["status"] == "FAIL"
    assert audit["checks"]["plan"]["status"] == "FAIL"
    assert audit["checks"]["agents"]["status"] == "FAIL"


def test_audit_complete_sdd_repository(tmp_path):
    # Simular estructura completa SDD
    (tmp_path / "SPEC.md").write_text("# Especificación de Requerimientos\nObjetivo general y alcance técnico del sistema.", encoding="utf-8")
    (tmp_path / "PLAN.md").write_text("# Plan de Desarrollo\n## Fase 1: MVP\n- [ ] Tarea 1 y entregables", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# Reglas del Proyecto\nProtocolo: usa el CLI de yunta para tools.", encoding="utf-8")
    yunta_dir = tmp_path / ".yunta"
    yunta_dir.mkdir()
    (yunta_dir / "config.json").write_text("{}", encoding="utf-8")

    audit = audit_repository(tmp_path)
    assert audit["healthy"] is True
    assert audit["summary"]["failures"] == 0
    assert audit["checks"]["config"]["status"] == "OK"
    assert audit["checks"]["spec"]["status"] == "OK"
    assert audit["checks"]["plan"]["status"] == "OK"
    assert audit["checks"]["agents"]["status"] == "OK"
    assert audit["checks"]["agents"]["has_yunta_protocol"] is True


def test_audit_docs_folder_fallback(tmp_path):
    # SDD ubicado dentro de docs/
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "SPEC.md").write_text("# Visión del Proyecto\nAlcance completo y visión del producto.", encoding="utf-8")
    (docs / "PLAN.md").write_text("# Plan de Fases\n## Fase 1: Core de herramientas", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# Reglas\nProtocolo Yunta activado para el agente.", encoding="utf-8")

    audit = audit_repository(tmp_path)
    assert audit["healthy"] is True
    assert audit["checks"]["spec"]["status"] == "OK"
    assert audit["checks"]["spec"]["path"] == "docs/SPEC.md"
    assert audit["checks"]["plan"]["status"] == "OK"
    assert audit["checks"]["plan"]["path"] == "docs/PLAN.md"


def test_run_check_json_output(tmp_path, capsys):
    (tmp_path / "SPEC.md").write_text("# Visión General del Proyecto\nRequerimientos y diseño.", encoding="utf-8")
    (tmp_path / "PLAN.md").write_text("# Plan de Fases y Tareas\nFase 1: Implementación.", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# Reglas\nUsa yunta como harness de gobernanza.", encoding="utf-8")

    code = run_check(target_dir=tmp_path, as_json=True)
    assert code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["healthy"] is True
    assert "checks" in data
    assert data["summary"]["passed"] >= 3


def test_run_check_console_output(tmp_path, capsys):
    (tmp_path / "SPEC.md").write_text("# Visión General del Proyecto\nRequerimientos y diseño.", encoding="utf-8")
    (tmp_path / "PLAN.md").write_text("# Plan de Fases y Tareas\nFase 1: Implementación.", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# Reglas\nUsa yunta como harness de gobernanza.", encoding="utf-8")

    code = run_check(target_dir=tmp_path, as_json=False)
    assert code == 0
    captured = capsys.readouterr()
    assert "YUNTA — AUDITORIA DE GOBERNANZA SDD" in captured.out
    assert "GOBERNANZA SALUDABLE" in captured.out
