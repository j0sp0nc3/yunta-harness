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
        # límite seguro: el índice del primer mensaje user (sin tool_results)
        # que esté en o después del exceso; nunca deja un assistant o
        # tool_result huérfano al inicio de lo que queda.
        cut = excess
        for i in range(excess, len(messages)):
            if messages[i].role == Role.USER and not messages[i].has_tool_result():
                cut = i
                break
        return messages[cut:]
