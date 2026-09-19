import sys

sys.path.insert(0, ".")

from yunta.api import Block, BlockType, Response, StopReason
from yunta.governance import audit_repository
from yunta.reverse_sdd import (
    generate_agents_candidate,
    generate_spec_candidate,
    run_reverse_sdd,
    scan_repository,
)


class FakeProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.received = []

    def send(self, messages, tools):
        self.received.append((list(messages), tools))
        return self.responses.pop(0)


def text(t):
    return Response(content=[Block(type=BlockType.TEXT, text=t)], stop_reason=StopReason.END_TURN)


SPEC_TEXT = "# SPEC.md candidato\n\n## Objetivo\n\nProcesa pedidos de usuarios."
AGENTS_TEXT = "# AGENTS.md candidato\n\nDelega tareas a yunta antes de generar codigo."


def _make_pyfile(root, name, content):
    p = root / name
    p.write_text(content, encoding="utf-8")
    return p


def test_scan_repository_finds_python_symbols(tmp_path):
    _make_pyfile(tmp_path, "core.py", "class Widget:\n    def build(self):\n        pass\n")
    inventory = scan_repository(tmp_path)
    assert "core.py" in inventory
    assert inventory["core.py"]["language"] == ".py"
    assert any("Widget" in line for line in inventory["core.py"]["outline"])


def test_scan_repository_ignores_venv_and_git_dirs(tmp_path):
    (tmp_path / ".git").mkdir()
    _make_pyfile(tmp_path / ".git", "hooks.py", "def x(): pass")
    (tmp_path / "venv").mkdir()
    _make_pyfile(tmp_path / "venv", "lib.py", "def y(): pass")
    _make_pyfile(tmp_path, "real.py", "def z(): pass")

    inventory = scan_repository(tmp_path)
    assert list(inventory.keys()) == ["real.py"]


def test_scan_repository_empty_dir_returns_empty_dict(tmp_path):
    assert scan_repository(tmp_path) == {}


def test_generate_spec_candidate_returns_provider_text():
    fake = FakeProvider([text(SPEC_TEXT)])
    inventory = {"a.py": {"language": ".py", "outline": ["def f()"], "symbols": []}}
    out = generate_spec_candidate(fake, inventory)
    assert out == SPEC_TEXT
    # El prompt enviado incluye el inventario condensado, no contenido crudo
    sent_prompt = fake.received[0][0][0].content[0].text
    assert "a.py" in sent_prompt
    assert fake.received[0][1] == []  # sin tools: es generación de texto puro


def test_run_reverse_sdd_writes_candidates_by_default(tmp_path):
    _make_pyfile(tmp_path, "app.py", "def main(): pass")
    fake = FakeProvider([text(SPEC_TEXT), text(AGENTS_TEXT)])

    result = run_reverse_sdd(target_dir=tmp_path, apply=False, provider=fake)

    assert result["files_scanned"] == 1
    spec_candidate = tmp_path / "SPEC.md.candidate"
    agents_candidate = tmp_path / "AGENTS.md.candidate"
    assert spec_candidate.read_text(encoding="utf-8") == SPEC_TEXT
    assert agents_candidate.read_text(encoding="utf-8") == AGENTS_TEXT
    assert not (tmp_path / "SPEC.md").exists()
    assert not (tmp_path / "AGENTS.md").exists()


def test_run_reverse_sdd_apply_writes_real_files_when_absent(tmp_path):
    _make_pyfile(tmp_path, "app.py", "def main(): pass")
    fake = FakeProvider([text(SPEC_TEXT), text(AGENTS_TEXT)])

    result = run_reverse_sdd(target_dir=tmp_path, apply=True, provider=fake)

    assert str(tmp_path / "SPEC.md") in result["written"]
    assert (tmp_path / "SPEC.md").read_text(encoding="utf-8") == SPEC_TEXT
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == AGENTS_TEXT


def test_run_reverse_sdd_apply_never_overwrites_existing_spec(tmp_path):
    _make_pyfile(tmp_path, "app.py", "def main(): pass")
    original = "# SPEC.md humano, no tocar\n"
    (tmp_path / "SPEC.md").write_text(original, encoding="utf-8")
    fake = FakeProvider([text(SPEC_TEXT), text(AGENTS_TEXT)])

    result = run_reverse_sdd(target_dir=tmp_path, apply=True, provider=fake)

    assert (tmp_path / "SPEC.md").read_text(encoding="utf-8") == original
    assert (tmp_path / "SPEC.md.candidate").read_text(encoding="utf-8") == SPEC_TEXT
    assert str(tmp_path / "SPEC.md.candidate") in result["written"]


def test_run_reverse_sdd_no_files_returns_zero_scanned(tmp_path):
    result = run_reverse_sdd(target_dir=tmp_path, apply=False, provider=FakeProvider([]))
    assert result == {"root": str(tmp_path.resolve()), "files_scanned": 0, "written": []}


def test_generated_candidates_pass_governance_structure_checks(tmp_path, monkeypatch):
    """Integración: lo generado por reverse-sdd debe pasar los mismos regex
    de gobernanza que yunta check usa (constantes compartidas)."""
    _make_pyfile(tmp_path, "app.py", "def main(): pass")
    fake = FakeProvider([text(SPEC_TEXT), text(AGENTS_TEXT)])
    run_reverse_sdd(target_dir=tmp_path, apply=True, provider=fake)

    audit = audit_repository(target_dir=tmp_path)
    assert audit["checks"]["spec"]["has_structure"] is True
    assert audit["checks"]["agents"]["has_yunta_protocol"] is True
