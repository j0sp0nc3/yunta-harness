from .api import BlockType, Message, Role


class NoCompaction:
    def compact(self, messages: list[Message]) -> list[Message]:
        return messages


class SlidingWindow:
    """Descarta los mensajes más viejos, cortando solo en límites seguros:
    justo antes de un mensaje user que no contiene tool_results."""

    def __init__(self, max_messages: int = 40):
        self.max_messages = max_messages

    def compact(self, messages: list[Message]) -> list[Message]:
        if len(messages) <= self.max_messages:
            return messages
        excess = len(messages) - self.max_messages
        cut = 0
        for i, m in enumerate(messages[:excess + 10]):
            if m.role == Role.USER and not m.has_tool_result():
                cut = i + 1
                if cut >= excess:
                    break
        return messages[cut:] if cut else messages[excess:]
