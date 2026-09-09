"""Módulo de clasificación y sugerencia de recuperación de errores de herramientas (V3-6)."""

def classify_tool_error(tool_name: str, error_msg: str) -> str:
    """Analiza el mensaje de error y retorna una sugerencia de recuperación accionable de acuerdo a 6 categorías."""
    err_lower = error_msg.lower()

    if any(k in err_lower for k in ("filenotfounderror", "no such file", "does not exist", "cannot find", "errno 2")):
        category = "FILE_NOT_FOUND"
        advice = "El archivo o directorio no existe. Usa 'list_dir' o 'tree' para verificar la ruta exacta antes de reintentar."
    elif any(k in err_lower for k in ("permissionerror", "access is denied", "permission denied", "errno 13")):
        category = "PERMISSION_DENIED"
        advice = "Permiso denegado por el sistema o por políticas del harness. Revisa los permisos o elige una ruta permitida."
    elif any(k in err_lower for k in ("timeouterror", "timed out", "timeout", "exceeded time limit")):
        category = "TIMEOUT"
        advice = "La ejecución de la herramienta excedió el tiempo límite. Divide la tarea en pasos más pequeños o simplifica los argumentos."
    elif any(k in err_lower for k in ("jsondecodeerror", "syntaxerror", "invalid json", "unexpected token", "keyerror")):
        category = "PARSE_OR_SYNTAX"
        advice = "Error de formato JSON o sintaxis en los argumentos de la herramienta. Revisa la estructura requerida por el esquema."
    elif any(k in err_lower for k in ("merge conflict", "git error", "uncommitted changes", "rebase in progress")):
        category = "GIT_CONFLICT"
        advice = "Estado inconsistente o conflicto en Git. Ejecuta 'git status' o revierte cambios temporales antes de reintentar."
    else:
        category = "UNKNOWN"
        advice = "Analiza el mensaje de error completo, inspecciona el estado con herramientas de lectura y ajusta la estrategia."

    return f"\n\n[RECUPERACIÓN DE ERROR ({category}): {advice}]"
