import json
import os
import sys
from pathlib import Path
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yunta.mcp import MCPClient, load_mcp_servers
from yunta.tools import registry

MOCK_SERVER_CODE = """import sys, json\n\ndef main():\n    for line in sys.stdin:\n        line = line.strip()\n        if not line:\n            continue\n        try:\n            req = json.loads(line)\n        except Exception:\n            continue\n        method = req.get('method')\n        req_id = req.get('id')\n\n        if method == 'initialize':\n            resp = {\n                'jsonrpc': '2.0',\n                'id': req_id,\n                'result': {\n                    'protocolVersion': '2024-11-05',\n                    'capabilities': {'tools': {}},\n                    'serverInfo': {'name': 'mock-mcp', 'version': '1.0'},\n                },\n            }\n            sys.stdout.write(json.dumps(resp) + chr(10))\n            sys.stdout.flush()\n        elif method == 'notifications/initialized':\n            pass\n        elif method == 'tools/list':\n            resp = {\n                'jsonrpc': '2.0',\n                'id': req_id,\n                'result': {\n                    'tools': [\n                        {\n                            'name': 'eco',\n                            'description': 'Devuelve eco del mensaje',\n                            'inputSchema': {\n                                'type': 'object',\n                                'properties': {'texto': {'type': 'string'}},\n                                'required': ['texto'],\n                            },\n                        },\n                        {\n                            'name': 'falla',\n                            'description': 'Tool que simula error',\n                            'inputSchema': {'type': 'object'},\n                        },\n                    ]\n                },\n            }\n            sys.stdout.write(json.dumps(resp) + chr(10))\n            sys.stdout.flush()\n        elif method == 'tools/call':\n            params = req.get('params', {})\n            tool_name = params.get('name')\n            args = params.get('arguments', {})\n            if tool_name == 'falla':\n                resp = {\n                    'jsonrpc': '2.0',\n                    'id': req_id,\n                    'error': {'code': -32000, 'message': 'error simulado en MCP'},\n                }\n            else:\n                t = args.get('texto', '')\n                resp = {\n                    'jsonrpc': '2.0',\n                    'id': req_id,\n                    'result': {'content': [{'type': 'text', 'text': f'ECO: {t}'}]},\n                }\n            sys.stdout.write(json.dumps(resp) + chr(10))\n            sys.stdout.flush()\n\nif __name__ == '__main__':\n    main()"""


@pytest.fixture
def mock_server_file(tmp_path):
    server_file = tmp_path / "mock_mcp_server.py"
    server_file.write_text(MOCK_SERVER_CODE, encoding="utf-8")
    return str(server_file)


def test_mcp_client_handshake_and_tools(mock_server_file):
    client = MCPClient(
        name="test_srv",
        command=sys.executable,
        args=[mock_server_file],
    )
    try:
        tools = client.list_tools()
        assert len(tools) == 2
        names = [t["name"] for t in tools]
        assert "eco" in names
        assert "falla" in names

        # Llamar a tool eco
        res = client.call_tool("eco", {"texto": "hola yunta"})
        assert res == "ECO: hola yunta"

        # Llamar a tool que falla
        with pytest.raises(RuntimeError, match="error simulado en MCP"):
            client.call_tool("falla", {})
    finally:
        client.close()


def test_load_mcp_servers_integration(tmp_path, mock_server_file):
    cfg_file = tmp_path / "mcp.json"
    cfg = {
        "mcpServers": {
            "local_test": {
                "command": sys.executable,
                "args": [mock_server_file],
                "requires_approval": True,
            }
        }
    }
    cfg_file.write_text(json.dumps(cfg), encoding="utf-8")

    clients = load_mcp_servers(str(cfg_file))
    try:
        assert len(clients) == 1
        tool = registry.get("mcp__local_test__eco")
        assert tool is not None
        assert tool.requires_approval is True
        assert "[MCP:local_test]" in tool.description

        # Ejecución a través del registro de Yunta
        out = tool.fn('{"texto": "desde registry"}')
        assert out == "ECO: desde registry"
    finally:
        for c in clients:
            c.close()


def test_missing_config_returns_empty():
    clients = load_mcp_servers("non_existent_config_12345.json")
    assert clients == []
