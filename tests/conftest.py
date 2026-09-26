"""Aislamiento común para toda la suite (auditoría de integridad, 2026-09-25).

Motivación medida instrumentando cada test de la suite completa:

- 26 tests escribían en el cwd: `.yunta/session_state.json` (el estado que usa
  `yunta --resume`) y `.yunta/scratch/`. Corriendo `pytest` en la raíz del repo
  —y en el hook de cada commit— se pisaba el estado real del usuario.
- 12 tests dejaban variables de entorno cambiadas (LLM_MODEL, OPENAI_API_KEY,
  LLM_REASONING_EFFORT...), algunas escritas por el propio código de producción.
- 17 tests dejaban `litellm.completion` / `litellm.api_base` reemplazados.
- Los tests que lanzan `python` como subproceso importaban el `yunta` instalado
  en modo editable (que apunta al repo principal), no el código bajo prueba.

Ninguna fuga cambiaba un resultado hoy (la suite da lo mismo en orden inverso),
pero eran acoples invisibles entre tests y efectos sobre el repo real.
"""
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True, scope="session")
def _subprocesses_import_this_checkout():
    """Un `python -c "from yunta..."` lanzado desde un directorio sin `yunta/`
    resuelve el paquete instalado en modo editable, que apunta al repo
    principal. En un worktree o una rama, esos tests verificaban OTRO código:
    `test_missing_model_fails_clearly` seguía pasando con la regla 2 rota a
    propósito. Con PYTHONPATH apuntando a este checkout, todo subproceso
    importa el código que se está probando."""
    old = os.environ.get("PYTHONPATH")
    os.environ["PYTHONPATH"] = str(REPO_ROOT) + (os.pathsep + old if old else "")
    yield
    if old is None:
        os.environ.pop("PYTHONPATH", None)
    else:
        os.environ["PYTHONPATH"] = old


@pytest.fixture(autouse=True)
def _isolate_cwd(tmp_path, monkeypatch):
    """Todo test corre en su propio directorio temporal: el código de yunta
    resuelve su estado (`.yunta/...`) relativo al cwd, así que ningún test
    puede tocar el repo real ni el estado del usuario. Un test que necesite un
    archivo lo crea en `tmp_path` (es el mismo directorio)."""
    monkeypatch.chdir(tmp_path)


@pytest.fixture(autouse=True)
def _restore_environ():
    """Restaura el entorno completo tras cada test, incluidas las variables
    que escribe el código de producción (no solo las del test)."""
    saved = dict(os.environ)
    yield
    if dict(os.environ) != saved:
        os.environ.clear()
        os.environ.update(saved)


@pytest.fixture(autouse=True)
def _restore_litellm_globals():
    """El provider escribe `litellm.api_base` en producción y varios tests
    reemplazan `litellm.completion`; ninguno de los dos se restauraba."""
    mod = sys.modules.get("litellm")
    saved = {a: getattr(mod, a) for a in ("completion", "api_base") if mod is not None and hasattr(mod, a)}
    yield
    for attr, value in saved.items():
        setattr(mod, attr, value)
