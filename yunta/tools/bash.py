import subprocess

from . import _parse, registry


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
