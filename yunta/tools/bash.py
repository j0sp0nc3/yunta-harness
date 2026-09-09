import os
import re
import subprocess

from . import _parse, registry

# --- Blocklist de seguridad (V3-7, docs/PLAN.md O1-b) ---
# Patrones peligrosos rechazados ANTES de ejecutar, con error claro y accionable.
# Extensible vía YUNTA_BLOCKLIST_EXTRA=path-a-archivo (una regex Python por línea).

MSG_SUFFIX = (
    "Si confirmas que es intencional, ejecútalo manualmente en tu terminal "
    "o ajusta el comando a algo menos destructivo."
)


def _block_extra_patterns(command: str) -> str | None:
    """Devuelve mensaje de bloqueo si `command` matchea una regex del archivo
    apuntado por YUNTA_BLOCKLIST_EXTRA (una regex por línea, sintaxis Python)."""
    extra_path = os.environ.get("YUNTA_BLOCKLIST_EXTRA")
    if not extra_path:
        return None
    try:
        with open(extra_path, encoding="utf-8") as fh:
            patterns = [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]
    except OSError:
        return None
    for pat in patterns:
        try:
            if re.search(pat, command):
                return (
                    f"patrón bloqueado por seguridad: el comando matchea la regex "
                    f"extra '{pat}' definida en YUNTA_BLOCKLIST_EXTRA."
                )
        except re.error:
            continue  # regex inválida en el archivo: se ignora, no bloquea
    return None


def _is_destructive_rm_rf(command: str) -> bool:
    """Detecta `rm` con flags recursivas cuyo target queda FUERA del cwd
    (o es la raíz '/'). `rm -rf` dentro del proyecto se permite."""
    if not re.match(r"\brm\b", command):
        return False
    parts = command.split()
    if not parts or parts[0] != "rm":
        return False
    recursive = False
    for arg in parts[1:]:
        if arg.startswith("--"):
            continue
        if arg == "-r" or arg == "-rf" or arg == "-fr" or (arg.startswith("-") and "r" in arg):
            recursive = True
    if not recursive:
        return False
    cwd = os.getcwd()
    for token in parts[1:]:
        if token.startswith("-"):
            continue
        target = os.path.abspath(os.path.expanduser(token))
        if target == os.path.abspath(os.sep) or target == cwd:
            return True  # borrar la raíz o el cwd completo: siempre bloqueado
        if not (target == cwd or target.startswith(cwd + os.sep)):
            return True  # fuera del cwd
    return False


def _check_blocklist(command: str) -> str | None:
    """Devuelve el motivo de bloqueo, o None si el comando es aceptable."""
    # 1) rm -rf fuera de cwd o sobre la raíz
    if _is_destructive_rm_rf(command):
        return (
            "patrón bloqueado por seguridad: rm recursivo fuera del directorio "
            "del proyecto (o sobre la raíz). Si necesitas limpiar algo fuera "
            "del proyecto, hazlo manualmente en tu terminal."
        )
    # 2) curl/wget piped a sh/sh/bash/zsh
    if re.search(r"\b(curl|wget)\b[^|;&]*\|\s*(sudo\s+)?(ba|z|da)?sh\b", command):
        return (
            "patrón bloqueado por seguridad: curl/wget piped a un shell "
            "(ejecución remota de código no verificada). Descarga el script, "
            "revísalo y ejecútalo como paso separado si confías en él."
        )
    # 3) git push --force (salvo YUNTA_ALLOW_FORCE=1)
    if re.search(r"\bgit\b.*\bpush\b.*--force", command) and os.environ.get("YUNTA_ALLOW_FORCE") != "1":
        return (
            "patrón bloqueado por seguridad: 'git push --force' puede reescribir "
            "historial remoto. Si es intencional, define la variable de entorno "
            "YUNTA_ALLOW_FORCE=1 (o usa --force-with-lease)."
        )
    # 4) mkfs (formateo de sistemas de archivos)
    if re.search(r"\bmkfs(\.\w+)?\b", command):
        return (
            "patrón bloqueado por seguridad: mkfs formatea sistemas de archivos "
            "y es irreversibile. Esta herramienta no ejecuta formateos."
        )
    # 5) dd of=/dev/... (escritura directa a dispositivos)
    if re.search(r"\bdd\b[^|;&]*\bof=/dev/", command):
        return (
            "patrón bloqueado por seguridad: 'dd of=/dev/...' escribe directamente "
            "en un dispositivo (riesgo de destrucción de disco/partición). "
            "Hazlo manualmente en tu terminal si sabes lo que haces."
        )
    # 6) patrones extra del usuario
    return _block_extra_patterns(command)


def _compact_output(output: str, exit_code: int) -> str:
    """Compacta salidas extensas para proteger la ventana de contexto del LLM."""
    if not output:
        return output

    lines = output.splitlines()

    # Si es pytest exitoso, preservar solo líneas esenciales de resumen
    if exit_code == 0 and any("passed in" in line for line in lines):
        summary_lines = [l for l in lines if "passed" in l or "test session starts" in l or "rootdir:" in l]
        if summary_lines:
            return "\n".join(summary_lines)

    # Si la salida supera 30 líneas y el comando fue exitoso, recortar el centro
    if exit_code == 0 and len(lines) > 30:
        omitted = len(lines) - 20
        compacted = lines[:10] + [f"... [{omitted} líneas intermedias omitidas por brevedad] ..."] + lines[-10:]
        return "\n".join(compacted)

    # Si el comando falló pero supera 60 líneas, conservar inicio y final (donde está el traceback)
    if exit_code != 0 and len(lines) > 60:
        omitted = len(lines) - 40
        compacted = lines[:15] + [f"... [{omitted} líneas intermedias omitidas] ..."] + lines[-25:]
        return "\n".join(compacted)

    return output[:20_000]


@registry.register(
    "bash",
    "Ejecuta un comando en el shell del proyecto y devuelve stdout+stderr. Máximo 60 segundos.",
    {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Comando a ejecutar"}
        },
        "required": ["command"],
    },
    requires_approval=True,
)
def bash(raw: str) -> str:
    command = _parse(raw).get("command", "")
    if not command:
        raise ValueError("command es obligatorio")
    blocked = _check_blocklist(command)
    if blocked:
        raise ValueError(f"{blocked} {MSG_SUFFIX}")
    proc = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    output = (proc.stdout + proc.stderr).strip()
    if proc.returncode != 0:
        output = f"[exit {proc.returncode}] {output}"
    return _compact_output(output, proc.returncode)
