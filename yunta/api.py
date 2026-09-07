from dataclasses import dataclass, field
from enum import Enum


class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class BlockType(str, Enum):
    TEXT = "text"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"


class StopReason(str, Enum):
    END_TURN = "end_turn"
    TOOL_USE = "tool_use"
    OTHER = "other"


@dataclass
class Block:
    type: BlockType
    text: str = ""
    tool_use_id: str = ""
    tool_name: str = ""
    tool_input: str = ""
    tool_result: str = ""
    is_error: bool = False


@dataclass
class Message:
    role: Role
    content: list[Block] = field(default_factory=list)

    def has_tool_result(self) -> bool:
        return any(b.type == BlockType.TOOL_RESULT for b in self.content)


@dataclass
class ToolDef:
    name: str
    description: str
    parameters: dict


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0

    def add(self, other: "Usage") -> "Usage":
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cached_tokens=self.cached_tokens + other.cached_tokens,
        )


@dataclass
class Response:
    content: list[Block] = field(default_factory=list)
    stop_reason: StopReason = StopReason.OTHER
    usage: Usage = field(default_factory=Usage)


def render_transcript(messages: list[Message]) -> str:
    lines = []
    for m in messages:
        parts = []
        for b in m.content:
            if b.type == BlockType.TEXT:
                parts.append(b.text)
            elif b.type == BlockType.TOOL_USE:
                parts.append(f"[called {b.tool_name} with {b.tool_input}]")
            else:
                parts.append(f"[tool result: {b.tool_result}]")
        lines.append(f"{m.role.value}: " + "\n".join(parts))
    return "\n".join(lines)
