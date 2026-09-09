import difflib
import inspect
import json
import sys
import threading
import time
from pathlib import Path

from .api import Block, BlockType, Message, Response, Role, StopReason, Usage
from .session import save_session
from .tools import registry


class Spinner:
    def __init__(self, message: str = "Pensando..."):
        self.message = message
        self._thread = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if not sys.stdout.isatty():
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def _spin(self) -> None:
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        start_time = time.time()
        idx = 0
        while not self._stop_event.is_set():
            elapsed = int(time.time() - start_time)
            frame = frames[idx % len(frames)]
            sys.stdout.write(f"\r{frame} {self.message} ({elapsed}s)")
            sys.stdout.flush()
            idx += 1
            time.sleep(0.1)

    def stop(self) -> None:
        if not self._thread or not self._thread.is_alive():
            return
        self._stop_event.set()
        self._thread.join()
        if sys.stdout.isatty():
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()


class Agent:
    def __init__(
        self,
        provider,
        system: str,
        compactor=None,
        max_turns: int = 30,
        confirm=None,
        tools: list | None = None,
        auto_save: bool = True,
        initial_messages: list[Message] | None = None,
        initial_usage: Usage | None = None,
    ):
        self.provider = provider
        self.system = system
        self.compactor = compactor
        self.max_turns = max_turns
        self.confirm = confirm
        self.auto_save = auto_save
        self.messages: list[Message] = list(initial_messages) if initial_messages else []
        self._tools_subset = list(tools) if tools is not None else None
        self.usage = initial_usage if initial_usage else Usage()
        self._spinner = None
        self.snapshots: list[dict[str, str | None]] = []

    def send(self, prompt: str) -> str:
        self.usage.turns += 1
        self.messages.append(
            Message(role=Role.USER, content=[Block(type=BlockType.TEXT, text=prompt)])
        )
        return self._loop()

    def _definitions(self) -> list:
        if self._tools_subset is None:
            return registry.definitions()
        return [
            t for t in registry.definitions() if t.name in {tool.name for tool in self._tools_subset}
        ]

    def _loop(self) -> str:
        final_text = []
        current_tool_results: list[Block] = []
        try:
            for _ in range(self.max_turns):
                current_tool_results = []
                if self.compactor:
                    self.messages = self.compactor.compact(self.messages)

                try:
                    supports_stream = (
                        "on_text" in inspect.signature(self.provider.send).parameters
                    )
                except (TypeError, ValueError):
                    supports_stream = False
                self._streamed = False
                self._spinner = Spinner("Pensando...")
                self._spinner.start()
                try:
                    if supports_stream:
                        resp = self.provider.send(self.messages, self._definitions(), on_text=self._stream_text)
                    else:
                        resp = self.provider.send(self.messages, self._definitions())
                finally:
                    if self._spinner:
                        self._spinner.stop()
                        self._spinner = None

                if not hasattr(self.provider, "total_usage") and getattr(resp, "usage", None):
                    self.usage = self.usage.add(resp.usage)
                self.messages.append(Message(role=Role.ASSISTANT, content=resp.content))

                has_tool_call = False
                for b in resp.content:
                    if b.type == BlockType.TEXT and b.text:
                        if self._streamed:
                            print()
                        else:
                            print(b.text)
                        final_text.append(b.text)
                    elif b.type == BlockType.TOOL_USE:
                        has_tool_call = True
                        result, is_err = self._execute_tool(b.tool_name, b.tool_input)
                        current_tool_results.append(
                            Block(
                                type=BlockType.TOOL_RESULT,
                                tool_use_id=b.tool_use_id,
                                tool_result=result,
                                is_error=is_err,
                            )
                        )

                if resp.stop_reason != StopReason.TOOL_USE or not has_tool_call:
                    return "\n".join(final_text).strip()

                self.messages.append(Message(role=Role.USER, content=current_tool_results))
        except KeyboardInterrupt:
            print("\n(interrumpido por el usuario)")
            if self.messages:
                last_msg = self.messages[-1]
                if last_msg.role == Role.ASSISTANT:
                    # P1: Garantizar que ningun tool_use quede huerfano ante Ctrl+C
                    pending_ids = [
                        b.tool_use_id for b in last_msg.content if b.type == BlockType.TOOL_USE
                    ]
                    done_ids = {b.tool_use_id for b in current_tool_results}
                    for tid in pending_ids:
                        if tid not in done_ids:
                            current_tool_results.append(
                                Block(
                                    type=BlockType.TOOL_RESULT,
                                    tool_use_id=tid,
                                    tool_result="[operación cancelada por el usuario (Ctrl+C)]",
                                    is_error=True,
                                )
                            )
                    if current_tool_results:
                        self.messages.append(Message(role=Role.USER, content=current_tool_results))
                elif last_msg.role == Role.USER:
                    self.messages.append(
                        Message(
                            role=Role.ASSISTANT,
                            content=[Block(type=BlockType.TEXT, text="[interrumpido por el usuario]")],
                        )
                    )
            if self.auto_save:
                self._save_session_state()
            return "\n".join(final_text).strip() or "[interrumpido por el usuario]"

        if self.auto_save:
            self._save_session_state()
        return "\n".join(final_text).strip()

    def _save_session_state(self) -> None:
        try:
            model_name = getattr(self.provider, "model", lambda: "")()
            save_session(self.messages, self.usage, model=model_name)
        except Exception:
            pass

    def _stream_text(self, delta: str) -> None:
        if self._spinner:
            self._spinner.stop()
            self._spinner = None
        print(delta, end="", flush=True)
        self._streamed = True

    def _take_snapshot(self, name: str, raw_input: str) -> None:
        try:
            args = json.loads(raw_input or "{}")
            path = args.get("path", "")
            if path:
                p = Path(path)
                old_content = p.read_text(encoding="utf-8", errors="replace") if p.exists() else None
                self.snapshots.append({path: old_content})
        except Exception:
            pass

    def undo(self) -> list[str]:
        """Restaura los archivos modificados en la última operación de escritura/edición."""
        if not self.snapshots:
            return []
        last = self.snapshots.pop()
        restored = []
        for path_str, old_content in last.items():
            p = Path(path_str)
            if old_content is None:
                if p.exists():
                    p.unlink()
                    restored.append(f"{path_str} (eliminado)")
            else:
                p.write_text(old_content, encoding="utf-8")
                restored.append(f"{path_str} (restaurado)")
        return restored

    def _execute_tool(self, name: str, raw_input: str) -> tuple[str, bool]:
        self.usage.tool_counts[name] = self.usage.tool_counts.get(name, 0) + 1
        tool = registry.get(name)
        if tool is None:
            self.usage.tool_errors += 1
            return f"unknown tool: {name}", True

        # E13: Guardar snapshot previo antes de modificar archivos
        if name in ("write_file", "str_replace"):
            self._take_snapshot(name, raw_input)

        detail = self._tool_detail(name, raw_input)
        print(f"[tool] {name} {raw_input}")
        if tool.requires_approval and not self._approve(name, detail):
            self.usage.tool_errors += 1
            return "user denied this tool call", True

        # E11: Pre-notificación en terminal
        if sys.stdout.isatty():
            sys.stdout.write(f"[tool] {name} en ejecución...\r")
            sys.stdout.flush()

        start_time = time.time()
        try:
            res = tool.fn(raw_input)
            elapsed = time.time() - start_time
            if sys.stdout.isatty():
                sys.stdout.write("\033[K")
            print(f"[tool] {name} completado en {elapsed:.2f}s")
            return res, False
        except Exception as e:
            elapsed = time.time() - start_time
            if sys.stdout.isatty():
                sys.stdout.write("\033[K")
            print(f"[tool] {name} falló en {elapsed:.2f}s")
            self.usage.tool_errors += 1
            return f"{type(e).__name__}: {e}", True

    @staticmethod
    def _tool_detail(name: str, raw_input: str) -> str:
        if name not in ("write_file", "str_replace"):
            return ""
        try:
            args = json.loads(raw_input or "{}")
        except json.JSONDecodeError:
            return ""

        path = args.get("path", "")
        if not path:
            return ""

        p = Path(path)
        old = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""

        if name == "write_file":
            new_content = args.get("content", "")
        elif name == "str_replace":
            old_str = args.get("old_str", "")
            new_str = args.get("new_str", "")
            if not old_str or old.count(old_str) != 1:
                return ""
            new_content = old.replace(old_str, new_str, 1)
        else:
            return ""

        diff = difflib.unified_diff(
            old.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
        return "".join(diff)

    def _approve(self, name: str, detail: str = "") -> bool:
        if self.confirm is not None:
            return self.confirm(name, detail)

        if detail:
            print(detail, end="")

        while True:
            ans = input(f"Aprobar {name}? [s/n]: ").strip().lower()
            if ans in ("s", "si", "y", "yes"):
                return True
            if ans in ("n", "no"):
                return False

    @property
    def total_usage(self) -> Usage:
        p_usage = getattr(self.provider, "total_usage", None)
        in_tok = p_usage.input_tokens if p_usage else self.usage.input_tokens
        out_tok = p_usage.output_tokens if p_usage else self.usage.output_tokens
        cached_tok = p_usage.cached_tokens if p_usage else self.usage.cached_tokens
        return Usage(
            input_tokens=in_tok,
            output_tokens=out_tok,
            cached_tokens=cached_tok,
            tool_counts=dict(self.usage.tool_counts),
            tool_errors=self.usage.tool_errors,
            turns=self.usage.turns,
        )
