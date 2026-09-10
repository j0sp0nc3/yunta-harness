"""Instalador y gestor de Git Pre-Commit Hooks para gobernanza SDD (v2.0).

Permite instalar un hook `.git/hooks/pre-commit` que ejecuta `yunta check --tests`
automáticamente previo a cada commit para prevenir la introducción de código roto o desobediente.
"""

import os
import sys
from pathlib import Path

PRE_COMMIT_HOOK_CONTENT = """#!/bin/sh
# Hook de pre-commit generado por Yunta Harness SDD
echo "[yunta-hook] Auditando repositorio con yunta check --tests..."
python -m yunta.cli check --tests
if [ $? -ne 0 ]; then
    echo "[yunta-hook] ❌ Auditoría o tests fallidos. Commit abortado."
    exit 1
fi
echo "[yunta-hook] ✅ Auditoría aprobada."
exit 0
"""


def install_git_hooks(target_dir: str = ".") -> bool:
    """Instala el pre-commit hook de Yunta en .git/hooks/pre-commit."""
    git_dir = Path(target_dir) / ".git"
    if not git_dir.exists() or not git_dir.is_dir():
        print("❌ Error: No se encontró el directorio .git. Ejecuta este comando en la raíz de un repositorio Git.")
        return False

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_file = hooks_dir / "pre-commit"

    try:
        hook_file.write_text(PRE_COMMIT_HOOK_CONTENT, encoding="utf-8")
        if sys.platform != "win32":
            os.chmod(hook_file, 0o755)
        print(f"✅ Git pre-commit hook instalado exitosamente en {hook_file.as_posix()}")
        return True
    except Exception as e:
        print(f"❌ Error al escribir el pre-commit hook: {e}")
        return False


def uninstall_git_hooks(target_dir: str = ".") -> bool:
    """Remueve el pre-commit hook de Yunta si existe."""
    git_dir = Path(target_dir) / ".git"
    hook_file = git_dir / "hooks" / "pre-commit"

    if hook_file.exists():
        try:
            hook_file.unlink()
            print("✅ Git pre-commit hook desinstalado exitosamente.")
            return True
        except Exception as e:
            print(f"❌ Error al remover el pre-commit hook: {e}")
            return False
    else:
        print("ℹ️ No se encontró ningún pre-commit hook instalado por Yunta.")
        return True
