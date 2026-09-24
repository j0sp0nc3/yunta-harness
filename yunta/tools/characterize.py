"""Tests de Caracterización / Golden-Master (Feature 3, 2026-09-19).

Antes de refactorizar código legacy sin tests, esta tool genera un test que
CAPTURA EL COMPORTAMIENTO ACTUAL de una función (no necesariamente
correcto) para detectar regresiones durante el refactor.

Alcance MVP: solo funciones Python top-level. Ejecuta la función objetivo
en un SUBPROCESO AISLADO con timeout — nunca in-process — para que un
crash o cuelgue del código objetivo no tumbe el proceso de yunta. Filtro
heurístico best-effort de efectos secundarios (imperfecto por diseño: mejor
rechazar de más que caracterizar una función con I/O real)."""
import ast
import json
import subprocess
import sys
from pathlib import Path

from . import _parse, registry
from .files import _check_boundary

_SIDE_EFFECT_NAMES = {"open", "subprocess", "requests", "socket", "input", "urlopen"}
_SIDE_EFFECT_PREFIXES = ("write_", "save_", "delete_", "send_", "remove_", "post_", "put_")
_CAPTURE_TIMEOUT = 10


def _find_top_level_function(content: str, func_name: str) -> ast.AST | None:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None
    for node in tree.body:  # solo top-level: no anidadas ni métodos de clase
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            return node
    return None


def _side_effect_reason(func_node: ast.AST, func_name: str) -> str | None:
    """Heurística best-effort: devuelve el motivo de rechazo, o None si la
    función parece pura. Imperfecta por diseño (ver docstring del módulo)."""
    if func_name.startswith(_SIDE_EFFECT_PREFIXES):
        return f"el nombre '{func_name}' sugiere un efecto secundario (prefijo)"
    for node in ast.walk(func_node):
        if isinstance(node, ast.Call):
            callee = node.func
            name = callee.id if isinstance(callee, ast.Name) else getattr(callee, "attr", None)
            if name in _SIDE_EFFECT_NAMES:
                return f"llamada a '{name}' sugiere efecto secundario (I/O, red o proceso)"
    return None


def _capture_golden(module_path: Path, func_name: str, sample_args: dict) -> dict:
    """Ejecuta la función en un subproceso aislado y captura repr(resultado)
    o el tipo/mensaje de la excepción levantada. Nunca in-process."""
    script = (
        "import importlib.util, json, sys\n"
        f"spec = importlib.util.spec_from_file_location('_char_target', {str(module_path.resolve())!r})\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
        f"func = getattr(mod, {func_name!r})\n"
        f"kwargs = json.loads({json.dumps(sample_args)!r})\n"
        "try:\n"
        "    result = func(**kwargs)\n"
        "    print(json.dumps({'ok': True, 'repr': repr(result)}))\n"
        "except Exception as e:\n"
        "    print(json.dumps({'ok': False, 'error_type': type(e).__name__, 'error_msg': str(e)}))\n"
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, timeout=_CAPTURE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error_type": "TimeoutExpired", "error_msg": f"excedió {_CAPTURE_TIMEOUT}s"}
    if proc.returncode != 0 or not proc.stdout.strip():
        return {"ok": False, "error_type": "SubprocessError", "error_msg": (proc.stderr or proc.stdout)[-500:]}
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except json.JSONDecodeError:
        return {"ok": False, "error_type": "SubprocessError", "error_msg": proc.stdout[-500:]}


def _write_characterization_test(module_path: Path, func_name: str, sample_args: dict, golden: dict) -> Path:
    tests_dir = Path("tests")
    tests_dir.mkdir(exist_ok=True)
    test_path = tests_dir / f"test_characterize_{module_path.stem}_{func_name}.py"

    lines = [
        '"""Test de caracterizacion (golden-master) generado automaticamente por yunta.',
        "",
        "ADVERTENCIA: captura el comportamiento ACTUAL de la funcion, no",
        "necesariamente correcto. Sirve para detectar regresiones durante un",
        "refactor, no como prueba de correccion funcional.",
        '"""',
        "import importlib.util",
        "import json",
        "import pytest",
        "",
        f"_MODULE_PATH = {str(module_path.resolve())!r}",
        f"_FUNC_NAME = {func_name!r}",
        "",
        "",
        "def _load_func():",
        "    spec = importlib.util.spec_from_file_location('_char_target', _MODULE_PATH)",
        "    mod = importlib.util.module_from_spec(spec)",
        "    spec.loader.exec_module(mod)",
        "    return getattr(mod, _FUNC_NAME)",
        "",
        "",
    ]

    kwargs_literal = json.dumps(json.dumps(sample_args))
    if golden.get("ok"):
        lines += [
            f"def test_{func_name}_characterization():",
            "    func = _load_func()",
            f"    kwargs = json.loads({kwargs_literal})",
            "    result = func(**kwargs)",
            f"    assert repr(result) == {golden['repr']!r}",
            "",
        ]
    else:
        lines += [
            f"def test_{func_name}_characterization_raises():",
            "    func = _load_func()",
            f"    kwargs = json.loads({kwargs_literal})",
            "    with pytest.raises(Exception) as exc_info:",
            "        func(**kwargs)",
            f"    assert type(exc_info.value).__name__ == {golden['error_type']!r}",
            "",
        ]

    test_path.write_text("\n".join(lines), encoding="utf-8")
    return test_path


@registry.register(
    "characterize_function",
    "Genera un test de caracterización (golden-master) que captura el comportamiento "
    "ACTUAL de una función Python top-level ANTES de refactorizarla, ejecutándola en un "
    "subproceso aislado con los argumentos de ejemplo dados. No garantiza que el "
    "comportamiento sea correcto, solo lo fija para detectar regresiones durante el refactor.",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Ruta al archivo .py con la función"},
            "function": {"type": "string", "description": "Nombre de la función top-level a caracterizar"},
            "sample_args": {
                "type": "object",
                "description": "Argumentos de ejemplo (kwargs) serializables a JSON para invocar la función",
            },
        },
        "required": ["path", "function"],
    },
    requires_approval=True,
)
def characterize_function(raw: str) -> str:
    args = _parse(raw)
    path_str = args.get("path", "")
    func_name = args.get("function", "")
    sample_args = args.get("sample_args") or {}
    if not path_str or not func_name:
        raise ValueError("path y function son obligatorios")
    if not isinstance(sample_args, dict):
        raise ValueError("sample_args debe ser un objeto JSON")

    module_path = _check_boundary(path_str)
    if not module_path.exists():
        raise FileNotFoundError(f"el archivo '{path_str}' no existe")
    if module_path.suffix != ".py":
        raise ValueError("characterize_function solo soporta archivos Python (.py) en esta versión")

    content = module_path.read_text(encoding="utf-8", errors="replace")
    func_node = _find_top_level_function(content, func_name)
    if func_node is None:
        raise ValueError(f"no se encontró la función top-level '{func_name}' en {path_str}")

    reason = _side_effect_reason(func_node, func_name)
    if reason:
        raise ValueError(
            f"'{func_name}' fue rechazada por el filtro de efectos secundarios: {reason}. "
            "characterize_function solo caracteriza funciones aparentemente puras."
        )

    golden = _capture_golden(module_path, func_name, sample_args)
    if golden.get("error_type") in ("TimeoutExpired", "SubprocessError"):
        raise RuntimeError(f"no se pudo capturar el comportamiento de '{func_name}': {golden.get('error_msg')}")

    test_path = _write_characterization_test(module_path, func_name, sample_args, golden)
    if golden.get("ok"):
        preview = golden["repr"][:200]
        return f"Test de caracterización escrito en {test_path} (resultado capturado: {preview})"
    return f"Test de caracterización escrito en {test_path} (la función lanza {golden['error_type']} con estos argumentos)"
