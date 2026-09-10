import json
import sys
from pathlib import Path

from yunta.mcp import MCPClient
from yunta.server_mcp import handle_rpc_message


def test_mcp_server_initialize():
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        },
    }
    resp = handle_rpc_message(req)
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 1
    result = resp["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert result["serverInfo"]["name"] == "yunta"
    assert result["serverInfo"]["version"] == "1.3.0"
    assert "tools" in result["capabilities"]


def test_mcp_server_initialized_notification():
    req = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
    }
    resp = handle_rpc_message(req)
    assert resp is None


def test_mcp_server_ping():
    req = {
        "jsonrpc": "2.0",
        "id": 42,
        "method": "ping",
    }
    resp = handle_rpc_message(req)
    assert resp["id"] == 42
    assert resp["result"] == {}


def test_mcp_server_tools_list():
    req = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {},
    }
    resp = handle_rpc_message(req)
    assert resp["id"] == 2
    tools = resp["result"]["tools"]
    tool_names = {t["name"] for t in tools}
    assert "read_file" in tool_names
    assert "write_file" in tool_names
    assert "str_replace" in tool_names
    assert "list_dir" in tool_names
    assert "bash" in tool_names

    # Validar que cada tool tiene inputSchema
    for t in tools:
        assert "description" in t
        assert "inputSchema" in t
        assert t["inputSchema"].get("type") == "object"


def test_mcp_server_tools_call_read_file(tmp_path):
    test_file = tmp_path / "hello.txt"
    test_file.write_text("contenido de prueba para mcp", encoding="utf-8")

    req = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "read_file",
            "arguments": {"path": str(test_file)},
        },
    }
    resp = handle_rpc_message(req)
    assert resp["id"] == 3
    result = resp["result"]
    assert result["isError"] is False
    assert len(result["content"]) == 1
    assert "contenido de prueba para mcp" in result["content"][0]["text"]


def test_mcp_server_tools_call_unknown_tool():
    req = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "herramienta_fantasma",
            "arguments": {},
        },
    }
    resp = handle_rpc_message(req)
    assert resp["id"] == 4
    result = resp["result"]
    assert result["isError"] is True
    assert "no encontrada" in result["content"][0]["text"]


def test_mcp_server_unknown_method():
    req = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "invalid/method",
        "params": {},
    }
    resp = handle_rpc_message(req)
    assert resp["id"] == 5
    assert "error" in resp
    assert resp["error"]["code"] == -32601


def test_mcp_server_permissions_and_approve():
    # List permissions
    req_list = {"jsonrpc": "2.0", "id": 10, "method": "yunta/permissions", "params": {"action": "list"}}
    resp = handle_rpc_message(req_list)
    assert resp["id"] == 10
    assert "patterns" in resp["result"]

    # Grant permission via yunta/approve
    req_approve = {"jsonrpc": "2.0", "id": 11, "method": "yunta/approve", "params": {"name": "bash", "pattern": "pytest"}}
    resp_app = handle_rpc_message(req_approve)
    assert resp_app["id"] == 11
    assert resp_app["result"]["status"] == "granted"

    # Verify granted permission is listed
    resp_list2 = handle_rpc_message(req_list)
    assert len(resp_list2["result"]["patterns"]) > 0


def test_mcp_client_server_integration():
    # Prueba end-to-end conectando MCPClient nativo de Yunta al servidor stdio
    client = MCPClient(
        name="yunta-test",
        command=sys.executable,
        args=["-m", "yunta.cli", "serve-mcp"],
    )
    try:
        # Petición tools/list a través del canal stdio real
        resp = client._send("tools/list")
        assert resp is not None
        assert "tools" in resp
        tool_names = {t["name"] for t in resp["tools"]}
        assert "read_file" in tool_names
        assert "list_dir" in tool_names

        # Petición tools/call a list_dir
        call_resp = client._send(
            "tools/call",
            {"name": "list_dir", "arguments": {"path": ".", "max_depth": 1}},
        )
        assert call_resp is not None
        assert call_resp.get("isError") is False
        assert len(call_resp.get("content", [])) > 0
    finally:
        if client.proc and client.proc.poll() is None:
            client.proc.terminate()
            client.proc.wait(timeout=5)

