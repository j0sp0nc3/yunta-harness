import difflib
import json
from pathlib import Path

from .api import Block, BlockType, Message, Response, Role, StopReason
from .tools import registry


class Agent:
    def __init__(
        self,
        provider,
        system: str,
        compactor=None,
        max_turns: int = 30,
        confirm=None,
    ):
        self.provider = provider
        self.system = system
        self.compactor = compactor
        self.max_turns = max_turns
        self.confirm = confirm
        self.messages: list[Message] = []

    def send(self, prompt: str) -> str:
        self.messages.append(
            Message(role=Role.USER, content=[Block(type=BlockType.TEXT, text=prompt)])
        )
        return self._loop()

    def _loop(self) -> str:
        final_text = []
        for _ in range(self.max_turns):
            if self.compactor:
                self.messages = self.compactor.compact(self.messages)

            resp = self.provider.send(self.messages, registry.definitions())
            self.messages.append(Message(role=Role.ASSISTANT, content=resp.content))

            tool_results = []
            has_tool_call = False
            for b in resp.content:
                if b.type == BlockType.TEXT and b.text:
                    print(b.text)
                    final_text.append(b.text)
                elif b.type == BlockType.TOOL_USE:
                    has_tool_call = True
                    result, is_err = self._execute_tool(b.tool_name, b.tool_input)
                    tool_results.append(
                        Block(
                            type=BlockType.TOOL_RESULT,
                            tool_use_id=b.tool_use_id,
                            tool_result=result,
                            is_error=is_err,
                        )
                    )

            if resp.stop_reason != StopReason.TOOL_USE or not has_tool_call:
                return "\n".join(final_text).strip()

            self.messages.append(Message(role=Role.USER, content=tool_results))

        return "\n".join(final_text).strip()

    def _execute_tool(self, name: str, raw_input: str) -> tuple[str, bool]:
        tool = registry.get(name)
        if tool is None:
            return f"unknown tool: {name}", True

        detail = self._tool_detail(name, raw_input)
        print(f"[tool] {name} {raw_input}")
        if tool.requires_approval and not self._approve(name, detail):
            return "user denied this tool call", True

        try:
            return tool.fn(raw_input), False
        except Exception as e:
            return f"{type(e).__name__}: {e}", True

    @staticmethod
    def _tool_detail(name: str, raw_input: str) -> str:
        if name != "write_file":
            return ""
        try:
            args = json.loads(raw_input or "{}")
            path, content = args.get("path", ""), args.get("content", "")
        except json.JSONDecodeError:
            return ""
        if not path:
            return ""
        p = Path(path)
        old = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
        diff = difflib.unified_diff(
            old.splitlines(keepends=True),
            content.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
        return "".join(diff)

    def _approve(self, name: str, detail: str) -> bool:
        if self.confirm is not None:
            return self.confirm(name, detail)
        if detail:
            print(detail)
        answer = input(f"¿Ejecutar {name}? [y/N] ").strip().lower()
        return answer == "y"
