import os

import litellm

from .api import Block, BlockType, Message, Response, Role, StopReason, ToolDef, Usage

_FINISH_REASONS = {
    "stop": StopReason.END_TURN,
    "tool_calls": StopReason.TOOL_USE,
    "end_turn": StopReason.END_TURN,
    "tool_use": StopReason.TOOL_USE,
}


class Provider:
    def send(self, messages: list[Message], tools: list[ToolDef]) -> Response: ...
    def model(self) -> str: ...


class LiteLLMProvider(Provider):
    def __init__(self, system: str):
        self._model = os.environ.get("LLM_MODEL", "")
        if not self._model:
            raise SystemExit(
                "LLM_MODEL no está definido. Ejemplos:\n"
                "  export LLM_MODEL=openai/gpt-4o          (OPENAI_API_KEY)\n"
                "  export LLM_MODEL=anthropic/claude-sonnet-4-5  (ANTHROPIC_API_KEY)\n"
                "  export LLM_MODEL=ollama/llama3          (local, sin API key)\n"
                "Cualquier modelo soportado por LiteLLM: https://docs.litellm.ai/docs/providers"
            )
        self._system = system
        self.total_usage = Usage()

    def model(self) -> str:
        return self._model

    def send(self, messages: list[Message], tools: list[ToolDef]) -> Response:
        kwargs = {
            "model": self._model,
            "messages": self._to_litellm(messages),
        }
        if tools:
            kwargs["tools"] = [self._tool_def(t) for t in tools]
        base_url = os.environ.get("LLM_API_BASE")
        if base_url:
            kwargs["api_base"] = base_url
        api_key = os.environ.get("LLM_API_KEY")
        if api_key:
            kwargs["api_key"] = api_key

        resp = litellm.completion(**kwargs)
        choice = resp.choices[0]

        out = Response(stop_reason=_FINISH_REASONS.get(choice.finish_reason, StopReason.OTHER))
        if choice.message.content:
            out.content.append(Block(type=BlockType.TEXT, text=choice.message.content))
        for tc in choice.message.tool_calls or []:
            out.content.append(
                Block(
                    type=BlockType.TOOL_USE,
                    tool_use_id=tc.id,
                    tool_name=tc.function.name,
                    tool_input=tc.function.arguments,
                )
            )

        u = resp.usage
        if u is not None:
            out.usage = Usage(
                input_tokens=getattr(u, "prompt_tokens", 0) or 0,
                output_tokens=getattr(u, "completion_tokens", 0) or 0,
            )
            self.total_usage = self.total_usage.add(out.usage)
        return out

    def _to_litellm(self, messages: list[Message]) -> list[dict]:
        out = [{"role": "system", "content": self._system}] if self._system else []
        for m in messages:
            if m.role == Role.ASSISTANT:
                out.append(self._assistant_msg(m))
            else:
                out.extend(self._user_msgs(m))
        return out

    def _assistant_msg(self, m: Message) -> dict:
        text_parts, tool_calls = [], []
        for b in m.content:
            if b.type == BlockType.TEXT:
                text_parts.append(b.text)
            elif b.type == BlockType.TOOL_USE:
                tool_calls.append(
                    {
                        "id": b.tool_use_id,
                        "type": "function",
                        "function": {"name": b.tool_name, "arguments": b.tool_input},
                    }
                )
        msg = {"role": "assistant", "content": "\n".join(text_parts) or None}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        return msg

    def _user_msgs(self, m: Message) -> list[dict]:
        text_parts = [b.text for b in m.content if b.type == BlockType.TEXT]
        results = [b for b in m.content if b.type == BlockType.TOOL_RESULT]
        out = []
        if text_parts:
            out.append({"role": "user", "content": "\n".join(text_parts)})
        for b in results:
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": b.tool_use_id,
                    "content": b.tool_result,
                }
            )
        return out

    @staticmethod
    def _tool_def(t: ToolDef) -> dict:
        params = dict(t.parameters)
        params.setdefault("type", "object")
        return {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": params,
            },
        }
