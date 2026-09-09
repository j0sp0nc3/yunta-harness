import json
import os
import time
from pathlib import Path

from .api import Block, BlockType, Message, Role, Usage

DEFAULT_SESSION_FILE = Path(".yunta") / "session_state.json"


def serialize_messages(messages: list[Message]) -> list[dict]:
    serialized = []
    for msg in messages:
        content_data = []
        for b in msg.content:
            content_data.append({
                "type": b.type.value,
                "text": b.text,
                "tool_use_id": b.tool_use_id,
                "tool_name": b.tool_name,
                "tool_input": b.tool_input,
                "tool_result": b.tool_result,
                "is_error": b.is_error,
            })
        serialized.append({
            "role": msg.role.value,
            "content": content_data,
        })
    return serialized


def deserialize_messages(data: list[dict]) -> list[Message]:
    messages = []
    for item in data:
        blocks = []
        for b in item.get("content", []):
            try:
                b_type = BlockType(b.get("type", "text"))
            except ValueError:
                b_type = BlockType.TEXT
            blocks.append(
                Block(
                    type=b_type,
                    text=b.get("text", ""),
                    tool_use_id=b.get("tool_use_id", ""),
                    tool_name=b.get("tool_name", ""),
                    tool_input=b.get("tool_input", ""),
                    tool_result=b.get("tool_result", ""),
                    is_error=b.get("is_error", False),
                )
            )
        try:
            role = Role(item.get("role", "user"))
        except ValueError:
            role = Role.USER
        messages.append(Message(role=role, content=blocks))
    return messages


def serialize_usage(usage: Usage) -> dict:
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cached_tokens": usage.cached_tokens,
        "tool_counts": dict(usage.tool_counts),
        "tool_errors": usage.tool_errors,
        "turns": usage.turns,
    }


def deserialize_usage(data: dict) -> Usage:
    return Usage(
        input_tokens=data.get("input_tokens", 0),
        output_tokens=data.get("output_tokens", 0),
        cached_tokens=data.get("cached_tokens", 0),
        tool_counts=dict(data.get("tool_counts", {})),
        tool_errors=data.get("tool_errors", 0),
        turns=data.get("turns", 0),
    )


def save_session(
    messages: list[Message],
    usage: Usage,
    model: str = "",
    session_file: Path | str = DEFAULT_SESSION_FILE,
) -> None:
    path = Path(session_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": time.time(),
        "model": model,
        "messages": serialize_messages(messages),
        "usage": serialize_usage(usage),
    }
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    if tmp_path.exists():
        tmp_path.replace(path)


def load_session(
    session_file: Path | str = DEFAULT_SESSION_FILE,
) -> dict | None:
    path = Path(session_file)
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        messages = deserialize_messages(data.get("messages", []))
        usage = deserialize_usage(data.get("usage", {}))
        return {
            "timestamp": data.get("timestamp", 0.0),
            "model": data.get("model", ""),
            "messages": messages,
            "usage": usage,
        }
    except Exception:
        return None


def clear_session(session_file: Path | str = DEFAULT_SESSION_FILE) -> bool:
    path = Path(session_file)
    if path.exists():
        try:
            path.unlink()
            return True
        except OSError:
            return False
    return False
