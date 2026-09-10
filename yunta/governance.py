import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def _find_candidate_file(root: Path, names: list[str]) -> Path | None:
    for name in names:
        p = root / name
        if p.exists() and p.is_file() and p.stat().st_size > 5:
            return p
    return None


def audit_repository(target_dir: Path | str = ".", run_tests: bool = False) -> dict:
    root = Path(target_dir).resolve()
    result = {
        "root": str(root),
        "healthy": True,
        "checks": {},
        "summary": {"passed": 0, "warnings": 0, "failures": 0},
    }

    # 1. Configuración de Yunta
    config_path = root / ".yunta" / "config.json"
    if config_path.exists():
        result["checks"]["config"] = {
            "status": "OK",
            "detail": ".yunta/config.json presente",
        }
        result["summary"]["passed"] += 1
    else:
        result["checks"]["config"] = {
            "status": "WARN",
            "detail": "No se encontró .yunta/config.json (usa 'yunta init' para inicializar)",
        }
        result["summary"]["warnings"] += 1

    # 2. Tríada SDD: SPEC.md
    spec_path = _find_candidate_file(root, ["SPEC.md", "docs/SPEC.md", "spec.md", "docs/spec.md"])
    if spec_path:
        content = spec_path.read_text(encoding="utf-8", errors="replace")
        has_reqs = bool(re.search(r"(#|##)\s+(Requerimientos|Objetivo|Vision|Especificaci|Problema|Scope|Overview)", content, re.I))
        rel_name = spec_path.relative_to(root).as_posix()
        result["checks"]["spec"] = {
            "status": "OK",
            "detail": f"{rel_name} presente ({len(content.splitlines())} líneas)",
            "has_structure": has_reqs,
            "path": rel_name,
        }
        result["summary"]["passed"] += 1
    else:
        result["checks"]["spec"] = {
            "status": "FAIL",
            "detail": "Falta SPEC.md (especificación de requerimientos requerida en SDD)",
        }
        result["summary"]["failures"] += 1
        result["healthy"] = False

    # 3. Tríada SDD: PLAN.md
    plan_path = _find_candidate_file(root, ["PLAN.md", "docs/PLAN.md", "plan.md", "docs/plan.md"])
    if plan_path:
        content = plan_path.read_text(encoding="utf-8", errors="replace")
        has_phases = bool(re.search(r"(Fase|Phase|Hito|Milestone|Backlog|Todo)", content, re.I))
        rel_name = plan_path.relative_to(root).as_posix()
        result["checks"]["plan"] = {
            "status": "OK",
            "detail": f"{rel_name} presente ({len(content.splitlines())} líneas)",
            "has_phases": has_phases,
            "path": rel_name,
        }
        result["summary"]["passed"] += 1
    else:
        result["checks"]["plan"] = {
            "status": "FAIL",
            "detail": "Falta PLAN.md (plan de fases requerido en SDD)",
        }
        result["summary"]["failures"] += 1
        result["healthy"] = False

    # 4. Tríada SDD: AGENTS.md y regla de interoperabilidad
    agents_path = _find_candidate_file(root, ["AGENTS.md", "docs/AGENTS.md", "agents.md", "docs/agents.md"])
    if agents_path:
        content = agents_path.read_text(encoding="utf-8", errors="replace")
        has_yunta_rule = "yunta" in content.lower()
        rel_name = agents_path.relative_to(root).as_posix()
        if has_yunta_rule:
            result["checks"]["agents"] = {
                "status": "OK",
                "detail": f"{rel_name} presente con protocolo de delegación a Yunta",
                "has_yunta_protocol": True,
                "path": rel_name,
            }
            result["summary"]["passed"] += 1
        else:
            result["checks"]["agents"] = {
                "status": "WARN",
                "detail": f"{rel_name} presente pero sin protocolo explícito de 'yunta'",
                "has_yunta_protocol": False,
                "path": rel_name,
            }
            result["summary"]["warnings"] += 1
    else:
        result["checks"]["agents"] = {
            "status": "FAIL",
            "detail": "Falta AGENTS.md (reglas de gobernanza del agente requeridas)",
        }
        result["summary"]["failures"] += 1
        result["healthy"] = False

    # 5. Estado de Git
    git_dir = root / ".git"
    if git_dir.exists():
        try:
            p = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            changes = [line for line in p.stdout.splitlines() if line.strip()]
            if not changes:
                result["checks"]["git"] = {
                    "status": "OK",
                    "detail": "Repositorio git limpio (sin cambios pendientes)",
                }
                result["summary"]["passed"] += 1
            else:
                result["checks"]["git"] = {
                    "status": "WARN",
                    "detail": f"Git con {len(changes)} archivo(s) modificado(s) o sin seguir",
                    "uncommitted_count": len(changes),
                }
                result["summary"]["warnings"] += 1
        except Exception as e:
            result["checks"]["git"] = {
                "status": "WARN",
                "detail": f"No se pudo consultar git status: {e}",
            }
            result["summary"]["warnings"] += 1
    else:
        result["checks"]["git"] = {
            "status": "WARN",
            "detail": "No es un repositorio git inicializado",
        }
        result["summary"]["warnings"] += 1

    # 6. Detección y ejecución de suite de pruebas
    test_runner = None
    test_cmd = None
    if (root / "pytest.ini").exists() or (root / "tests").exists() or (root / "pyproject.toml").exists():
        test_runner = "pytest"
        test_cmd = [sys.executable, "-m", "pytest", "-q"]
    elif (root / "package.json").exists():
        test_runner = "npm test"
        test_cmd = ["npm", "test"]
    elif (root / "Cargo.toml").exists():
        test_runner = "cargo test"
        test_cmd = ["cargo", "test"]

    if test_runner:
        if run_tests:
            try:
                p = subprocess.run(
                    test_cmd,
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=int(os.environ.get("YUNTA_CHECK_TIMEOUT", "300")),
                )
                if p.returncode == 0:
                    result["checks"]["tests"] = {
                        "status": "OK",
                        "detail": f"Tests ejecutados con éxito ({test_runner})",
                        "runner": test_runner,
                    }
                    result["summary"]["passed"] += 1
                else:
                    failed_names = [
                        line for line in (p.stdout + p.stderr).splitlines()
                        if line.startswith("FAILED")
                    ][:5]
                    result["checks"]["tests"] = {
                        "status": "FAIL",
                        "detail": f"Fallo en tests ({test_runner}) — código {p.returncode}"
                        + (f" — {', '.join(failed_names)}" if failed_names else ""),
                        "runner": test_runner,
                        "output": (p.stdout + p.stderr)[-500:],
                    }
                    result["summary"]["failures"] += 1
                    result["healthy"] = False
            except subprocess.TimeoutExpired:
                result["checks"]["tests"] = {
                    "status": "WARN",
                    "detail": f"Timeout al ejecutar tests ({test_runner}) — ajustable vía YUNTA_CHECK_TIMEOUT",
                }
                result["summary"]["warnings"] += 1
            except Exception as e:
                result["checks"]["tests"] = {
                    "status": "WARN",
                    "detail": f"No se pudo ejecutar {test_runner}: {e}",
                }
                result["summary"]["warnings"] += 1
        else:
            result["checks"]["tests"] = {
                "status": "OK",
                "detail": f"Suite de pruebas detectada: {test_runner} (usa --tests para ejecutar)",
                "runner": test_runner,
            }
            result["summary"]["passed"] += 1
    else:
        result["checks"]["tests"] = {
            "status": "WARN",
            "detail": "No se detectó suite de pruebas estándar (pytest, npm, cargo)",
        }
        result["summary"]["warnings"] += 1

    return result


def run_check(target_dir: Path | str = ".", as_json: bool = False, run_tests: bool = False) -> int:
    audit = audit_repository(target_dir=target_dir, run_tests=run_tests)

    if as_json:
        print(json.dumps(audit, indent=2, ensure_ascii=False))
        return 0 if audit["healthy"] else 1

    # Formato visual de consola
    print("============================================================")
    print("           YUNTA — AUDITORIA DE GOBERNANZA SDD              ")
    print("============================================================")
    print(f"Proyecto: {audit['root']}")
    print("------------------------------------------------------------")

    labels = {
        "config": "Configuración Yunta",
        "spec": "Especificación (SPEC.md)",
        "plan": "Plan de Fases (PLAN.md)",
        "agents": "Reglas de Agentes (AGENTS.md)",
        "git": "Control de Versiones (Git)",
        "tests": "Suite de Verificación",
    }

    status_tags = {
        "OK": "[ OK ]",
        "WARN": "[WARN]",
        "FAIL": "[FAIL]",
    }

    for key in ("config", "spec", "plan", "agents", "git", "tests"):
        check = audit["checks"].get(key)
        if not check:
            continue
        tag = status_tags.get(check["status"], "[ ?? ]")
        label = labels.get(key, key).ljust(30)
        print(f"{tag} {label} : {check['detail']}")

    print("------------------------------------------------------------")
    summary = audit["summary"]
    print(f"Resultado: {summary['passed']} OK | {summary['warnings']} Alertas | {summary['failures']} Fallos")
    if audit["healthy"]:
        print("Estado: GOBERNANZA SALUDABLE (Apto para iterar y ejecutar)")
        print("============================================================")
        return 0
    else:
        print("Estado: REGLAS SDD INCOMPLETAS (Inicializa con 'yunta init' o corrige fallos)")
        print("============================================================")
        return 1
