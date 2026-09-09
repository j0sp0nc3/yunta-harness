import json
import sys
from .tools import bash, files, registry  # noqa: F401 — asegura registro de herramientas


def handle_rpc_message(msg: dict) -> dict | None:
    req_id = msg.get("id")
    method = msg.get("method")
    params = msg.get("params", {})

    # Notificaciones no requieren respuesta
    if req_id is None:
        if method == "notifications/initialized":
            sys.stderr.write("[yunta-mcp] Cliente inicializado correctamente\n")
            sys.stderr.flush()
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "yunta",
                    "version": "1.1.0"
                }
            }
        }

    elif method == "ping":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {}
        }

    elif method == "tools/list":
        tools_list = []
        for t in registry.definitions():
            tools_list.append({
                "name": t.name,
                "description": t.description,
                "inputSchema": t.parameters
            })
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": tools_list
            }
        }

    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        tool = registry.get(tool_name)
        if tool is None:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Herramienta '{tool_name}' no encontrada en el harness Yunta"
                        }
                    ],
                    "isError": True
                }
            }

        raw_input = json.dumps(arguments) if isinstance(arguments, dict) else (arguments or "{}")
        try:
            res = tool.fn(raw_input)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": str(res)
                        }
                    ],
                    "isError": False
                }
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Error ejecutando {tool_name}: {e}"
                        }
                    ],
                    "isError": True
                }
            }

    else:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": f"Método desconocido: {method}"
            }
        }


def serve_stdio():
    if sys.platform == "win32":
        try:
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    sys.stderr.write("[yunta-mcp] Servidor MCP Yunta v1.1.0 iniciado en stdio\n")
    sys.stderr.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as e:
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": f"Error de parseo JSON: {e}"
                }
            }
            sys.stdout.write(json.dumps(err_resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
            continue

        resp = handle_rpc_message(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    serve_stdio()
