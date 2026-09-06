import json
import os
import subprocess
from pathlib import Path
from .tools import Tool, _parse, registry


class MCPClient:
    def __init__(self, name: str, command: str, args: list[str] | None = None, env: dict | None = None):
        self.name = name
        full_env = {**os.environ, **(env or {})}
        cmd = [command] + (args or [])
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=full_env,
        )
        self._req_id = 0
        self._init_server()

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def _send(self, method: str, params: dict | None = None, is_notification: bool = False) -> dict | None:
        req_id = None if is_notification else self._next_id()
        msg = {"jsonrpc": "2.0", "method": method}
        if req_id is not None:
            msg["id"] = req_id
        if params is not None:
            msg["params"] = params
        line = json.dumps(msg) + "\n"
        if not self.proc.stdin:
            raise RuntimeError(f"MCP server '{self.name}' stdin is closed")
        self.proc.stdin.write(line)
        self.proc.stdin.flush()
        if is_notification:
            return None

        while True:
            resp_line = self.proc.stdout.readline()
            if not resp_line:
                err = self.proc.stderr.read() if self.proc.stderr else ""
                raise RuntimeError(f"MCP server '{self.name}' terminated unexpectedly: {err}")
            resp_line = resp_line.strip()
            if not resp_line:
                continue
            try:
                data = json.loads(resp_line)
                if data.get("id") == req_id:
                    if "error" in data:
                        err_msg = data["error"].get("message", str(data["error"]))
                        raise RuntimeError(f"MCP error: {err_msg}")
                    return data.get("result", {})
            except json.JSONDecodeError:
                continue

    def _init_server(self):
        self._send(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "yunta", "version": "0.8.0"},
            },
        )
        self._send("notifications/initialized", is_notification=True)

    def list_tools(self) -> list[dict]:
        res = self._send("tools/list", {}) or {}
        return res.get("tools", [])

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        res = self._send("tools/call", {"name": tool_name, "arguments": arguments}) or {}
        contents = res.get("content", [])
        parts = []
        for c in contents:
            if isinstance(c, dict):
                parts.append(c.get("text", json.dumps(c)))
            else:
                parts.append(str(c))
        return "\n".join(parts) if parts else json.dumps(res)

    def close(self):
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
            self.proc.terminate()
            self.proc.wait(timeout=2)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


def load_mcp_servers(config_path: str = ".yunta/mcp.json") -> list[MCPClient]:
    path = Path(config_path)
    if not path.exists():
        return []
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"advertencia: fallo al leer {config_path}: {e}")
        return []

    servers = cfg.get("mcpServers", {})
    clients = []
    for s_name, s_cfg in servers.items():
        cmd = s_cfg.get("command")
        if not cmd:
            continue
        try:
            client = MCPClient(
                name=s_name,
                command=cmd,
                args=s_cfg.get("args"),
                env=s_cfg.get("env"),
            )
            for t in client.list_tools():
                original_name = t.get("name", "")
                tool_name = f"mcp__{s_name}__{original_name}"
                desc = t.get("description", "")
                schema = t.get("inputSchema", {"type": "object", "properties": {}})

                def make_handler(c: MCPClient, orig_n: str):
                    def handler(raw: str) -> str:
                        args = _parse(raw)
                        return c.call_tool(orig_n, args)
                    return handler

                registry._tools[tool_name] = Tool(
                    name=tool_name,
                    description=f"[MCP:{s_name}] {desc}",
                    parameters=schema,
                    fn=make_handler(client, original_name),
                    requires_approval=s_cfg.get("requires_approval", False),
                )
            clients.append(client)
        except Exception as e:
            print(f"advertencia: no se pudo iniciar servidor MCP '{s_name}': {e}")
    return clients
