import subprocess

from . import _parse, registry


@registry.register(
    "bash",
    "Ejecuta un comando en el shell del proyecto y devuelve stdout+stderr. Máximo 30 segundos.",
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
    proc = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = (proc.stdout + proc.stderr).strip()
    if proc.returncode != 0:
        output = f"[exit {proc.returncode}] {output}"
    return output[:50_000]
