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
    tool_counts: dict[str, int] = field(default_factory=dict)
    tool_errors: int = 0
    turns: int = 0

    def add(self, other: "Usage") -> "Usage":
        merged_tools = dict(self.tool_counts)
        for k, v in other.tool_counts.items():
            merged_tools[k] = merged_tools.get(k, 0) + v
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cached_tokens=self.cached_tokens + other.cached_tokens,
            tool_counts=merged_tools,
            tool_errors=self.tool_errors + other.tool_errors,
            turns=self.turns + other.turns,
        )

    @property
    def cache_rate(self) -> float:
        """Porcentaje de tokens de entrada que vinieron de caché."""
        total_in = self.input_tokens + self.cached_tokens
        return (self.cached_tokens / total_in * 100.0) if total_in else 0.0

    @property
    def theoretical_raw_tokens(self) -> int:
        """Tokens de entrada brutos que habrías transferido en un chat crudo sin caching."""
        return self.input_tokens + self.cached_tokens

    @property
    def total_tool_calls(self) -> int:
        """Total acumulado de llamadas a herramientas."""
        return sum(self.tool_counts.values())

    def format_summary(self) -> str:
        """Formatea un resumen legible y comparativo en 2-3 líneas limpias."""
        total_in = self.theoretical_raw_tokens
        cached_info = f" (⚡ {self.cache_rate:.1f}% ahorro de caché)" if self.cached_tokens else ""
        lines = [
            f"Tokens: entrada={self.input_tokens:,} | cacheados={self.cached_tokens:,}{cached_info} | salida={self.output_tokens:,}",
            f"Sin Harness habrías transferido: {total_in:,} tokens de entrada",
        ]
        if self.tool_counts:
            breakdown = ", ".join(f"{k}: {v}" for k, v in sorted(self.tool_counts.items()))
            err_info = f" (errores/rechazos: {self.tool_errors})" if self.tool_errors else ""
            lines.append(f"Herramientas ({self.total_tool_calls} llamadas): {breakdown}{err_info}")
        if self.turns:
            lines.append(f"Turnos de interacción: {self.turns}")
        return "\n".join(lines)


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
