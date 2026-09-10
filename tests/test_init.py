import os
import sys
from pathlib import Path

import pytest
from yunta import cli
from yunta.init import generate_agents, generate_plan, generate_spec, run_init


def test_run_init_generates_sdd_files(tmp_path):
    created = run_init("asistente-de-lecturas", target_dir=tmp_path)
    assert len(created) == 3
    assert "SPEC.md" in created
    assert "PLAN.md" in created
    assert "AGENTS.md" in created

    spec = (tmp_path / "SPEC.md").read_text(encoding="utf-8")
    assert "# Especificación de Producto — asistente-de-lecturas" in spec
    assert "## 1. Visión y Propósito" in spec
    assert "## 4. Casos de Uso Core (MVP)" in spec
    assert "## 6. Fuera de Alcance" in spec

    plan = (tmp_path / "PLAN.md").read_text(encoding="utf-8")
    assert "# Plan de Desarrollo — asistente-de-lecturas" in plan
    assert "Fase 1: Mínimo Núcleo Viable" in plan

    agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "Contexto del Proyecto y Reglas para Agentes — asistente-de-lecturas" in agents
    assert "Soberanía de las Especificaciones" in agents


def test_run_init_respects_existing_files(tmp_path):
    spec_path = tmp_path / "SPEC.md"
    spec_path.write_text("contenido existente", encoding="utf-8")

    created = run_init("mi-idea", target_dir=tmp_path)
    assert "SPEC.md" not in created
    assert "PLAN.md" in created
    assert "AGENTS.md" in created
    assert spec_path.read_text(encoding="utf-8") == "contenido existente"


def test_run_init_default_project_name(tmp_path):
    run_init("", target_dir=tmp_path)
    spec = (tmp_path / "SPEC.md").read_text(encoding="utf-8")
    assert f"# Especificación de Producto — {tmp_path.name}" in spec


def test_cli_init_dispatch(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["yunta", "init", "app-de-pruebas"])

    cli.main()

    assert (tmp_path / "SPEC.md").exists()
    assert (tmp_path / "PLAN.md").exists()
    assert (tmp_path / "AGENTS.md").exists()
    spec = (tmp_path / "SPEC.md").read_text(encoding="utf-8")
    assert "app-de-pruebas" in spec


def test_cli_help_flag_without_llm_model(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["yunta", "--help"])
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_MODELS", raising=False)

    cli.main()

    captured = capsys.readouterr().out
    assert "Comandos de Terminal (CLI):" in captured
    assert "Comandos Interactivos del REPL" in captured
    assert "/help" in captured
    assert "/undo" in captured
    assert "/roi" in captured


def test_cli_version_flag(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["yunta", "--version"])
    cli.main()

    captured = capsys.readouterr().out
    assert "yunta v2.0.0" in captured
