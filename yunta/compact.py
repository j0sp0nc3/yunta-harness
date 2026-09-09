from .api import Block, BlockType, Message, Role


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
        cut = excess
        for i in range(excess, len(messages)):
            if messages[i].role == Role.USER and not messages[i].has_tool_result():
                cut = i
                break
        return messages[cut:]


class TokenBudgetCompactor:
    """Compactación por etapas basada en presupuesto de tokens (V3-4, OpenDev):
    - 70%: aviso en el contexto
    - 80%: enmascaramiento de tool_results extensos
    - 85%: pruning de mensajes intermedios más antiguos (respetando límites seguros)
    - 99%: resumen sintético defensivo
    """

    def __init__(self, max_tokens: int = 128000):
        self.max_tokens = max_tokens

    @staticmethod
    def estimate_tokens(messages: list[Message]) -> int:
        total_chars = 0
        for m in messages:
            for b in m.content:
                if b.type == BlockType.TEXT:
                    total_chars += len(b.text or "")
                elif b.type == BlockType.TOOL_USE:
                    total_chars += len(b.tool_name or "") + len(b.tool_input or "")
                elif b.type == BlockType.TOOL_RESULT:
                    total_chars += len(b.tool_result or "")
        return total_chars // 4

    def usage_ratio(self, messages: list[Message]) -> float:
        return self.estimate_tokens(messages) / self.max_tokens

    def compact(self, messages: list[Message]) -> list[Message]:
        if not messages:
            return messages

        tokens = self.estimate_tokens(messages)
        ratio = tokens / self.max_tokens

        if ratio < 0.70:
            return messages

        result = list(messages)

        # 99%: Resumen sintético defensivo
        if ratio >= 0.99 and len(result) > 6:
            first = result[0]
            last_few = result[-4:]
            summary_msg = Message(
                role=Role.USER,
                content=[
                    Block(
                        type=BlockType.TEXT,
                        text=f"[RESUMEN DE HISTORIAL (99% de presupuesto: {tokens:,}/{self.max_tokens:,} tokens): Se han descartado mensajes intermedios para liberar memoria. Continúa respondiendo al objetivo del usuario].",
                    )
                ],
            )
            return [first, summary_msg] + last_few

        # 85%: Pruning de mensajes más antiguos respetando límites seguros
        if ratio >= 0.85 and len(result) > 10:
            cut = len(result) // 2
            for i in range(cut, len(result)):
                if result[i].role == Role.USER and not result[i].has_tool_result():
                    cut = i
                    break
            first = result[0]
            result = [first] + result[cut:]

        # 80%: Enmascaramiento de tool_results extensos (>500 chars)
        if ratio >= 0.80:
            masked_messages = []
            for m in result:
                new_blocks = []
                for b in m.content:
                    if b.type == BlockType.TOOL_RESULT and b.tool_result and len(b.tool_result) > 500:
                        masked_text = (
                            b.tool_result[:150]
                            + "\n\n[... contenido enmascarado por 80% de presupuesto de tokens ...]\n\n"
                            + b.tool_result[-150:]
                        )
                        new_blocks.append(
                            Block(
                                type=BlockType.TOOL_RESULT,
                                tool_use_id=b.tool_use_id,
                                tool_result=masked_text,
                                is_error=b.is_error,
                            )
                        )
                    else:
                        new_blocks.append(b)
                masked_messages.append(Message(role=m.role, content=new_blocks))
            result = masked_messages

        # 70%: Aviso de token budget si no está ya presente
        if ratio >= 0.70:
            has_warning = any(
                any(b.type == BlockType.TEXT and "[AVISO COMPACTACIÓN (70%)]" in (b.text or "") for b in m.content)
                for m in result
            )
            if not has_warning and len(result) > 1:
                warn_msg = Message(
                    role=Role.USER,
                    content=[
                        Block(
                            type=BlockType.TEXT,
                            text=f"[AVISO COMPACTACIÓN (70%): El historial ha alcanzado {tokens:,} tokens ({ratio:.0%} del presupuesto de {self.max_tokens:,})].",
                        )
                    ],
                )
                result.insert(1, warn_msg)

        return result
