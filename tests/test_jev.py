from io import BytesIO
import json
import os
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

import yunta.tools.bash  # noqa: F401
import yunta.tools.files  # noqa: F401
from yunta.agent import Agent
from yunta.api import Block, BlockType, Message, Response, Role, StopReason
from yunta.jev import JevAssessment, JevClient, JevGatekeeper
from yunta.tools import registry


class FakeProvider:
    def __init__(self, responses=None):
        self.responses = list(responses or [])

    def send(self, messages, tools, **kwargs):
        if self.responses:
            return self.responses.pop(0)
        return Response(stop_reason=StopReason.END_TURN, content=[Block(type=BlockType.TEXT, text="ok")])

    def model(self):
        return "fake-model"


def test_jev_client_config(monkeypatch):
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    monkeypatch.delenv("JEV_MODEL", raising=False)
    monkeypatch.delenv("JEV_API_BASE", raising=False)
    client = JevClient()
    assert not client.is_configured

    monkeypatch.setenv("JEV_API_KEY", "jev-test-key-123")
    monkeypatch.setenv("JEV_API_BASE", "https://api.example.com/v1/decisions")
    client2 = JevClient()
    assert client2.is_configured
    assert client2.api_key == "jev-test-key-123"
    assert client2.api_base == "https://api.example.com/v1/decisions"

    # Soporte a modelo agnóstico (ej. Ollama local o cualquier LLM)
    client3 = JevClient(model="ollama/qwen2.5:0.5b")
    assert client3.is_configured
    assert client3.model == "ollama/qwen2.5:0.5b"


def test_jev_client_evaluate_success(monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "test-key")
    monkeypatch.setenv("JEV_API_BASE", "https://api.example.com/v1/decisions")
    client = JevClient()

    mock_resp = MagicMock()
    mock_payload = {
        "decisions": {
            "destructive": {"type": "noul", "value": True, "probability": 0.95},
            "risk": {"type": "score", "value": 5, "confidence": 0.9},
            "action": {"type": "choice", "value": "block", "confidence": 0.92},
        }
    }
    mock_resp.read.return_value = json.dumps(mock_payload).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        result = client.evaluate({"tool": "bash"}, {"risk": {}})
        assert "destructive" in result
        assert result["destructive"]["value"] is True
        assert result["risk"]["value"] == 5
        assert result["action"]["value"] == "block"
        mock_urlopen.assert_called_once()


def test_jev_client_evaluate_agnostic_llm(monkeypatch):
    """Verifica que JevClient puede usar cualquier modelo estándar vía Provider neutral."""
    resp_text = json.dumps({
        "destructive": {"value": False, "probability": 0.05},
        "risk": {"value": 1, "confidence": 0.95},
        "action": {"value": "allow", "confidence": 0.98},
    })
    fake_provider = FakeProvider(responses=[
        Response(stop_reason=StopReason.END_TURN, content=[Block(type=BlockType.TEXT, text=resp_text)])
    ])
    client = JevClient(model="ollama/qwen2.5:0.5b", provider=fake_provider)
    result = client.evaluate({"tool": "list_dir"}, {})
    assert result["action"]["value"] == "allow"
    assert result["risk"]["value"] == 1


def test_jev_gatekeeper_availability(monkeypatch):
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    monkeypatch.delenv("JEV_MODEL", raising=False)
    monkeypatch.delenv("JEV_API_BASE", raising=False)
    monkeypatch.delenv("JEV_GATEKEEPER", raising=False)
    assert not JevGatekeeper.is_available()

    monkeypatch.setenv("JEV_API_KEY", "key")
    assert JevGatekeeper.is_available()

    monkeypatch.setenv("JEV_GATEKEEPER", "0")
    assert not JevGatekeeper.is_available()


def test_jev_gatekeeper_assess_destructive(monkeypatch):
    client = JevClient(api_key="dummy")
    gatekeeper = JevGatekeeper(client=client)

    decisions = {
        "destructive": {"value": True, "probability": 0.98},
        "risk": {"value": 5, "confidence": 0.95},
        "action": {"value": "ask_user", "confidence": 0.9},
    }

    with patch.object(client, "evaluate", return_value=decisions):
        assessment = gatekeeper.assess_tool("bash", '{"command": "rm -rf /"}')
        assert assessment is not None
        assert assessment.is_destructive is True
        assert assessment.destructive_prob == 0.98
        assert assessment.risk_score == 5
        assert assessment.action == "ask_user"

        must_prompt, warn = gatekeeper.inspect_and_filter("bash", "rm -rf /", default_requires_approval=False)
        assert must_prompt is True
        assert "alto riesgo" in warn.lower()


def test_jev_gatekeeper_assess_safe(monkeypatch):
    client = JevClient(api_key="dummy")
    gatekeeper = JevGatekeeper(client=client)

    decisions = {
        "destructive": {"value": False, "probability": 0.01},
        "risk": {"value": 1, "confidence": 0.99},
        "action": {"value": "allow", "confidence": 0.98},
    }

    with patch.object(client, "evaluate", return_value=decisions):
        assessment = gatekeeper.assess_tool("bash", '{"command": "git status"}')
        assert assessment is not None
        assert assessment.is_destructive is False
        assert assessment.risk_score == 1
        assert assessment.action == "allow"

        must_prompt, msg = gatekeeper.inspect_and_filter("bash", "git status", default_requires_approval=True)
        assert must_prompt is False
        assert "segura" in msg.lower()


def test_jev_gatekeeper_offline_fallback():
    client = JevClient(api_key="dummy")
    gatekeeper = JevGatekeeper(client=client)

    with patch.object(client, "evaluate", side_effect=urllib.error.URLError("Network down")):
        assessment = gatekeeper.assess_tool("bash", "some command")
        assert assessment is None

        must_prompt, warn = gatekeeper.inspect_and_filter("bash", "cmd", default_requires_approval=True)
        assert must_prompt is True
        assert warn == ""


def test_agent_integration_with_jev_safe_auto_approval():
    client = JevClient(api_key="dummy")
    gatekeeper = JevGatekeeper(client=client)

    decisions = {
        "destructive": {"value": False, "probability": 0.0},
        "risk": {"value": 1, "confidence": 0.99},
        "action": {"value": "allow", "confidence": 0.98},
    }

    from yunta.api import Response, StopReason
    tool_resp = Response(
        stop_reason=StopReason.TOOL_USE,
        content=[
            Block(
                type=BlockType.TOOL_USE,
                tool_use_id="t1",
                tool_name="list_dir",
                tool_input='{"path": "."}',
            )
        ],
    )
    final_resp = Response(
        stop_reason=StopReason.END_TURN,
        content=[Block(type=BlockType.TEXT, text="listado completado")],
    )

    provider = FakeProvider([tool_resp, final_resp])
    agent = Agent(provider=provider, system="test", confirm=None)
    agent.jev_gatekeeper = gatekeeper

    with patch.object(client, "evaluate", return_value=decisions):
        # list_dir requires_approval is False anyway, but JEV marks it safe
        res = agent.send("lista archivos")
        assert "listado completado" in res


def test_agent_integration_with_jev_destructive_forced_prompt(monkeypatch):
    client = JevClient(api_key="dummy")
    gatekeeper = JevGatekeeper(client=client)

    decisions = {
        "destructive": {"value": True, "probability": 0.99},
        "risk": {"value": 5, "confidence": 0.99},
        "action": {"value": "ask_user", "confidence": 0.95},
    }

    from yunta.api import Response, StopReason
    tool_resp = Response(
        stop_reason=StopReason.TOOL_USE,
        content=[
            Block(
                type=BlockType.TOOL_USE,
                tool_use_id="t1",
                tool_name="bash",
                tool_input='{"command": "rm -rf test"}',
            )
        ],
    )

    provider = FakeProvider([tool_resp])
    agent = Agent(provider=provider, system="test", confirm=None)
    agent.jev_gatekeeper = gatekeeper

    # With JEV detecting destructive risk, force_prompt is enabled and terminal input is asked.
    # We simulate user declining ("n").
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")

    with patch.object(client, "evaluate", return_value=decisions):
        res = agent.send("borra test")
        tool_res = [b.tool_result for m in agent.messages for b in m.content if b.type == BlockType.TOOL_RESULT]
        assert len(tool_res) == 1
        assert "user denied this tool call" in tool_res[0]
        assert "JEV high-risk flag" in tool_res[0]
