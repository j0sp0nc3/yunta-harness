import json
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
    def send(self, messages: list[Message], tools: list[ToolDef], on_text=None, reasoning_effort: str | None = None) -> Response: ...
    def model(self) -> str: ...
    @property
    def startup_tax(self) -> int:
        return 0


class LiteLLMProvider(Provider):
    def __init__(self, system: str = ""):
        models_str = os.environ.get("LLM_MODELS") or os.environ.get("LLM_MODEL", "")
        self._models = [m.strip() for m in models_str.split(",") if m.strip()]
        if not self._models:
            raise SystemExit(
                "LLM_MODEL no está definido. Define la variable LLM_MODEL con el modelo elegido (ej. LLM_MODEL=gemini/gemini-3.6-flash, LLM_MODEL=openai/gpt-4o, etc.)."
            )
        self._model_idx = 0
        self._system = system
        self.total_usage = Usage()
        # Proveedor secundario opcional (endpoint + credencial propios):
        # se activa solo si todos los modelos primarios fallan.
        self._n_primary = len(self._models)
        fallback_model = os.environ.get("LLM_FALLBACK_MODEL", "").strip()
        if fallback_model:
            self._models.append(fallback_model)
            self._fallback_base = os.environ.get("LLM_FALLBACK_API_BASE", "").strip()
            self._fallback_key = os.environ.get("LLM_FALLBACK_API_KEY", "")

    def _is_fallback_active(self) -> bool:
        return self._model_idx >= self._n_primary

    @property
    def system(self) -> str:
        return self._system

    def model(self) -> str:
        return self._models[self._model_idx]

    def estimate_startup_tax(self, tools: list[ToolDef] | None = None) -> int:
        """Calcula los tokens aproximados del payload inicial (system prompt + schemas de herramientas)."""
        if tools is None:
            from .tools import registry
            tools = registry.definitions()
        payload_text = self._system or ""
        for t in tools:
            def_dict = self._tool_def(t)
            payload_text += "\n" + json.dumps(def_dict)
        try:
            return litellm.token_counter(model=self.model(), text=payload_text)
        except Exception:
            return len(payload_text) // 4

    @property
    def startup_tax(self) -> int:
        return self.estimate_startup_tax()


    def send(self, messages: list[Message], tools: list[ToolDef], on_text=None, reasoning_effort: str | None = None) -> Response:
        while True:
            current_model = self.model()
            kwargs = {
                "model": current_model,
                "messages": self._to_litellm(messages),
            }
            if tools:
                kwargs["tools"] = [self._tool_def(t) for t in tools]
            if self._is_fallback_active():
                base_url = self._fallback_base
            else:
                base_url = os.environ.get("LLM_API_BASE", "").strip()
            if base_url:
                kwargs["api_base"] = base_url
                litellm.api_base = base_url
            else:
                kwargs.pop("api_base", None)
                litellm.api_base = None
                os.environ.pop("OPENAI_BASE_URL", None)
                os.environ.pop("OPENAI_API_BASE", None)
            api_key = self._fallback_key if self._is_fallback_active() else os.environ.get("LLM_API_KEY")
            if api_key:
                kwargs["api_key"] = api_key
            session_id = os.environ.get("YUNTA_SESSION_ID")
            if session_id:
                kwargs["user"] = session_id
                kwargs["metadata"] = {"session_id": session_id}

            effort = reasoning_effort or os.environ.get("LLM_REASONING_EFFORT")
            if effort:
                clean_effort = effort.lower().strip()
                if clean_effort in ("high", "profundo", "on", "1", "true"):
                    kwargs["reasoning_effort"] = "high"
                    thinking_budget = int(os.environ.get("LLM_THINKING_BUDGET", "8192"))
                    kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}
                elif clean_effort in ("medium", "medio"):
                    kwargs["reasoning_effort"] = "medium"
                    thinking_budget = int(os.environ.get("LLM_THINKING_BUDGET", "4096"))
                    kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}
                elif clean_effort in ("low", "bajo"):
                    kwargs["reasoning_effort"] = "low"
                    thinking_budget = int(os.environ.get("LLM_THINKING_BUDGET", "1024"))
                    kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}
                elif clean_effort in ("off", "desactivado", "false", "0"):
                    kwargs.pop("reasoning_effort", None)
                    kwargs.pop("thinking", None)
                else:
                    kwargs["reasoning_effort"] = effort

            try:
                if on_text is not None:
                    kwargs["stream"] = True
                    kwargs["stream_options"] = {"include_usage": True}
                    import time
                    for attempt in range(5):
                        try:
                            return self._consume_stream(litellm.completion(**kwargs), on_text)
                        except Exception as e:
                            err_str = str(e).lower()
                            err_name = type(e).__name__
                            # P2: Si el endpoint rechaza stream_options (400 Bad Request), reintentar sin el kwarg
                            if "stream_options" in err_str or "stream_options" in str(e):
                                kwargs.pop("stream_options", None)
                                try:
                                    return self._consume_stream(litellm.completion(**kwargs), on_text)
                                except Exception as inner_e:
                                    err_str = str(inner_e).lower()
                                    err_name = type(inner_e).__name__
                            is_retryable = any(
                                x in err_str or x in err_name.lower()
                                for x in ["429", "503", "unavailable", "exhausted", "ratelimit", "quota", "serviceunavailable", "midstreamfallback"]
                            )
                            if is_retryable and (self._model_idx + 1 < len(self._models)):
                                raise
                            if is_retryable and attempt < 4:
                                print(f"\n[Retrying API in {(attempt+1)*5}s due to: {err_name}]")
                                time.sleep((attempt + 1) * 5)
                                continue
                            raise

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
                    cached = (
                        getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0)
                        or getattr(u, "cache_read_input_tokens", 0)
                        or getattr(u, "prompt_cache_hit_tokens", 0)
                        or 0
                    )
                    out.usage = Usage(
                        input_tokens=getattr(u, "prompt_tokens", 0) or 0,
                        output_tokens=getattr(u, "completion_tokens", 0) or 0,
                        cached_tokens=cached or 0,
                    )
                    self.total_usage = self.total_usage.add(out.usage)
                return out

            except Exception as e:
                err_str = str(e).lower()
                err_name = type(e).__name__
                is_fallback_candidate = any(
                    x in err_str or x in err_name.lower()
                    for x in ["429", "503", "401", "400", "unauthorized", "authentication", "badrequest", "unknown model", "unavailable", "exhausted", "ratelimit", "quota", "serviceunavailable", "midstreamfallback"]
                )
                if is_fallback_candidate and (self._model_idx + 1 < len(self._models)):
                    old_m = self.model()
                    self._model_idx += 1
                    new_m = self.model()
                    print(f"\n[Fallback Router: error en {old_m} ({err_name}), conmutando automáticamente a: {new_m}]")
                    continue
                raise

    def _consume_stream(self, stream, on_text) -> Response:
        text: list[str] = []
        calls: dict = {}
        finish_reason = None
        usage = None
        for chunk in stream:
            if getattr(chunk, "usage", None) is not None:
                u = chunk.usage
                cached = (
                    getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0)
                    or getattr(u, "cache_read_input_tokens", 0)
                    or getattr(u, "prompt_cache_hit_tokens", 0)
                    or 0
                )
                usage = Usage(
                    input_tokens=getattr(u, "prompt_tokens", 0) or 0,
                    output_tokens=getattr(u, "completion_tokens", 0) or 0,
                    cached_tokens=cached or 0,
                )
            for choice in chunk.choices or []:
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
                delta = getattr(choice, "delta", None)
                if delta is None:
                    continue
                # E11: Soporte para streaming de tokens de razonamiento (Thinking/Reasoning)
                reasoning = getattr(delta, "reasoning_content", None) or getattr(delta, "thought", None)
                if reasoning:
                    on_text(reasoning)
                if delta.content:
                    on_text(delta.content)
                    text.append(delta.content)
                for tc in delta.tool_calls or []:
                    slot = calls.setdefault(tc.index, {"id": "", "name": "", "args": []})
                    if tc.id:
                        slot["id"] = tc.id
                    fn = getattr(tc, "function", None)
                    if fn is None:
                        continue
                    if fn.name and not slot["name"]:
                        slot["name"] = fn.name
                    if fn.arguments:
                        slot["args"].append(fn.arguments)

        stop_reason = _FINISH_REASONS.get(finish_reason, StopReason.OTHER)
        if calls and stop_reason != StopReason.TOOL_USE:
            stop_reason = StopReason.TOOL_USE
        out = Response(stop_reason=stop_reason)
        if text:
            out.content.append(Block(type=BlockType.TEXT, text="".join(text)))
        for idx in sorted(calls):
            c = calls[idx]
            out.content.append(
                Block(
                    type=BlockType.TOOL_USE,
                    tool_use_id=c["id"],
                    tool_name=c["name"],
                    tool_input="".join(c["args"]),
                )
            )
        if usage is not None:
            out.usage = usage
            self.total_usage = self.total_usage.add(out.usage)
        return out

    def _to_litellm(self, messages: list[Message]) -> list[dict]:
        out = [
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": self._system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
            }
        ] if self._system else []
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
        images = [b for b in m.content if b.type == BlockType.IMAGE]
        results = [b for b in m.content if b.type == BlockType.TOOL_RESULT]
        out = []
        if text_parts or images:
            if not images:
                out.append({"role": "user", "content": "\n".join(text_parts)})
            else:
                content_list = []
                if text_parts:
                    content_list.append({"type": "text", "text": "\n".join(text_parts)})
                for img in images:
                    content_list.append({"type": "image_url", "image_url": {"url": img.image_url}})
                out.append({"role": "user", "content": content_list})
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
