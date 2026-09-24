import json
import os
import time

import litellm

# Descartar parámetros opcionales que el modelo/proveedor seleccionado no soporte (ej. thinking/reasoning_effort)
litellm.drop_params = True

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
    def __init__(self, system: str = "", model: str | None = None):
        if model:
            self._models = [model]
        else:
            models_str = os.environ.get("LLM_MODELS") or os.environ.get("LLM_MODEL", "")
            self._models = [m.strip() for m in models_str.split(",") if m.strip()]
        if not self._models:
            raise SystemExit(
                "LLM_MODEL no está definido. Define la variable LLM_MODEL con el modelo elegido (ej. LLM_MODEL=gemini/gemini-3.6-flash, LLM_MODEL=openai/gpt-4o, etc.)."
            )
        self._model_idx = 0
        self._system = system
        self.total_usage = Usage()
        self._override_model: str | None = None  # Feature 6: enrutamiento económico dinámico
        # V7-10 (2026-09-24): algunos tiers rechazan el almacenamiento de
        # contexto cacheado por completo (Gemini free tier responde HTTP 429
        # `TotalCachedContentStorageTokensPerModelFreeTier limit=0` ante
        # CUALQUIER petición con `cache_control`). Se desactiva solo tras
        # verlo fallar, no por adelantado: el caché ahorra dinero real donde
        # sí funciona y no se sacrifica preventivamente.
        self._disable_cache_control = False
        # V7-11 (2026-09-24): el self-heal de `reasoning_effort` solo escribia
        # LLM_REASONING_EFFORT, pero `agent.py` pasa el effort explicito en
        # CADA turno y el parametro gana sobre la variable de entorno — asi
        # que el mismo UnsupportedParamsError se repetia turno tras turno
        # (4 veces en una corrida real de 6 llamadas utiles). Se recuerda en
        # la instancia para que el reintento ocurra una sola vez.
        self._disable_reasoning = False
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

    def set_model_override(self, model: str | None) -> None:
        """Feature 6: fuerza un modelo distinto para el próximo `send()` (ej.
        un modelo barato para pasos triviales) sin tocar la posición de la
        cascada de fallback (`_model_idx`). `None` desactiva el override."""
        self._override_model = model

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
            attempt_start = time.monotonic()
            current_model = self._override_model or self.model()
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
            else:
                kwargs.pop("api_key", None)
            session_id = os.environ.get("YUNTA_SESSION_ID")
            if session_id:
                kwargs["user"] = session_id
                kwargs["metadata"] = {"session_id": session_id}

            if self._disable_reasoning:
                effort = "off"
            else:
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
                    for attempt in range(5):
                        try:
                            return self._consume_stream(litellm.completion(**kwargs), on_text, messages=messages, model=current_model)
                        except Exception as e:
                            err_str = str(e).lower()
                            err_name = type(e).__name__
                            # P2: Si el endpoint rechaza stream_options (400 Bad Request), reintentar sin el kwarg
                            if "stream_options" in err_str or "stream_options" in str(e):
                                kwargs.pop("stream_options", None)
                                try:
                                    return self._consume_stream(litellm.completion(**kwargs), on_text, messages=messages, model=current_model)
                                except Exception as inner_e:
                                    err_str = str(inner_e).lower()
                                    err_name = type(inner_e).__name__
                            is_retryable = any(
                                x in err_str or x in err_name.lower()
                                for x in ["429", "503", "unavailable", "exhausted", "ratelimit", "quota", "serviceunavailable", "midstreamfallback"]
                            )
                            is_hard_quota = any(
                                q in err_str for q in ["usage limit", "quota exceeded", "exceeded your current quota", "insufficient_quota", "1308"]
                            )
                            if is_retryable and (self._model_idx + 1 < len(self._models) or is_hard_quota):
                                raise
                            if is_retryable and attempt < 4:
                                print(f"\n[Retrying API in {(attempt+1)*5}s due to: {err_name}]")
                                time.sleep((attempt + 1) * 5)
                                continue
                            raise

                t0 = time.monotonic()
                resp = litellm.completion(**kwargs)
                elapsed = time.monotonic() - t0
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

                out.usage = self._extract_usage(getattr(resp, "usage", None), messages, out.content)
                self.total_usage = self.total_usage.add(out.usage)
                self._record_llm_call(
                    current_model, out.usage, elapsed, choice.finish_reason,
                    streaming=False, tool_calls_count=len(choice.message.tool_calls or []),
                )
                return out

            except Exception as e:
                err_str = str(e).lower()
                err_name = type(e).__name__
                # V7-9 (2026-09-24): registrar también el camino de fallo. Antes
                # solo se grababa el éxito, así que un incidente de cuota que
                # abortó una transcripción real de 81 min dejó `llm_calls.jsonl`
                # en 0 entradas pese a varios intentos — invisible por completo.
                self._record_llm_call(
                    current_model, Usage(), time.monotonic() - attempt_start, "",
                    streaming=on_text is not None, tool_calls_count=0,
                    error=f"{err_name}: {str(e)[:200]}",
                )
                if "unsupportedparam" in err_name.lower() or "not support parameter" in err_str:
                    reasoning_effort = "off"
                    os.environ["LLM_REASONING_EFFORT"] = "off"
                    self._disable_reasoning = True  # V7-11: no repetir el descarte cada turno
                    continue
                # V7-10: el tier rechaza el caché de contexto por completo
                # (no es saturación: `limit=0` significa "no disponible aquí").
                # Se reintenta sin `cache_control` en vez de dar por muerto al
                # modelo — sin esto, un fallback a un tier sin caché no puede
                # responder NINGUNA petición con system prompt.
                if not self._disable_cache_control and (
                    "cachedcontentstorage" in err_str
                    or "cached_content" in err_str
                    or ("cache_control" in err_str and "not support" in err_str)
                ):
                    print(f"\n[Cache: {current_model} rechaza el caché de contexto ({err_name}); reintentando sin cache_control]")
                    self._disable_cache_control = True
                    continue
                is_fallback_candidate = any(
                    x in err_str or x in err_name.lower()
                    for x in ["429", "503", "401", "400", "unauthorized", "authentication", "badrequest", "unknown model", "unavailable", "exhausted", "ratelimit", "quota", "serviceunavailable", "midstreamfallback"]
                )
                if is_fallback_candidate and self._override_model and current_model == self._override_model:
                    # Feature 6: el override económico falló — vuelve a la cascada
                    # normal sin avanzar _model_idx (no es un fallo del modelo principal).
                    print(f"\n[Model Override: error en {current_model} ({err_name}), volviendo al modelo de cascada normal]")
                    self._override_model = None
                    continue
                if is_fallback_candidate and (self._model_idx + 1 < len(self._models)):
                    old_m = self.model()
                    self._model_idx += 1
                    new_m = self.model()
                    print(f"\n[Fallback Router: error en {old_m} ({err_name}), conmutando automáticamente a: {new_m}]")
                    continue
                raise

    def _record_llm_call(
        self, model: str, usage: Usage, elapsed_secs: float, finish_reason_raw: str | None,
        streaming: bool, tool_calls_count: int, error: str = "",
    ) -> None:
        """V7-5 (2026-09-22): registra el `finish_reason` crudo del proveedor
        (no el `StopReason` mapeado, que colapsa `"length"` en `OTHER`) para
        poder confirmar o descartar truncamiento por `max_tokens` — nunca
        rompe la llamada real si falla (mismo patrón que `voice_telemetry`)."""
        try:
            from .llm_call_telemetry import record_llm_call
            record_llm_call(
                model=model,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                elapsed_secs=elapsed_secs,
                finish_reason_raw=finish_reason_raw or "",
                streaming=streaming,
                tool_calls=tool_calls_count,
                error=error,
            )
        except Exception:
            pass

    def _extract_usage(
        self,
        u,
        messages: list[Message] | None = None,
        response_content: list[Block] | None = None,
    ) -> Usage:
        in_tok = 0
        out_tok = 0
        cached_tok = 0

        if u is not None:
            if isinstance(u, dict):
                in_tok = u.get("prompt_tokens") or u.get("input_tokens") or 0
                out_tok = u.get("completion_tokens") or u.get("output_tokens") or 0
                details = u.get("prompt_tokens_details")
                if details:
                    if isinstance(details, dict):
                        cached_tok = (
                            details.get("cached_tokens") or details.get("cache_read_input_tokens") or 0
                        )
                    else:
                        cached_tok = (
                            getattr(details, "cached_tokens", 0)
                            or getattr(details, "cache_read_input_tokens", 0)
                            or 0
                        )
                if not cached_tok:
                    cached_tok = (
                        u.get("cache_read_input_tokens") or u.get("prompt_cache_hit_tokens") or 0
                    )
            elif isinstance(u, Usage):
                return u
            else:
                in_tok = getattr(u, "prompt_tokens", 0) or getattr(u, "input_tokens", 0) or 0
                out_tok = getattr(u, "completion_tokens", 0) or getattr(u, "output_tokens", 0) or 0
                details = getattr(u, "prompt_tokens_details", None)
                if details:
                    if isinstance(details, dict):
                        cached_tok = (
                            details.get("cached_tokens") or details.get("cache_read_input_tokens") or 0
                        )
                    else:
                        cached_tok = (
                            getattr(details, "cached_tokens", 0)
                            or getattr(details, "cache_read_input_tokens", 0)
                            or 0
                        )
                if not cached_tok:
                    cached_tok = (
                        getattr(u, "cache_read_input_tokens", 0)
                        or getattr(u, "prompt_cache_hit_tokens", 0)
                        or 0
                    )

        if in_tok == 0 and messages:
            try:
                raw_text = "\n".join(
                    " ".join(b.text or b.tool_input or b.tool_result for b in m.content)
                    for m in messages
                )
                in_tok = litellm.token_counter(model=self.model(), text=raw_text)
            except Exception:
                in_tok = max(
                    10,
                    sum(
                        len(b.text or b.tool_input or b.tool_result)
                        for m in messages
                        for b in m.content
                    )
                    // 4,
                )

        if out_tok == 0 and response_content:
            try:
                out_text = "\n".join(b.text or b.tool_input for b in response_content)
                out_tok = litellm.token_counter(model=self.model(), text=out_text)
            except Exception:
                out_tok = max(
                    1, sum(len(b.text or b.tool_input) for b in response_content) // 4
                )

        return Usage(
            input_tokens=int(in_tok),
            output_tokens=int(out_tok),
            cached_tokens=int(cached_tok),
        )

    def _consume_stream(self, stream, on_text, messages: list[Message] | None = None, model: str | None = None) -> Response:
        text: list[str] = []
        calls: dict = {}
        finish_reason = None
        usage = None
        t0 = time.monotonic()
        for chunk in stream:
            if getattr(chunk, "usage", None) is not None:
                usage = chunk.usage
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
        out.usage = self._extract_usage(usage, messages, out.content)
        self.total_usage = self.total_usage.add(out.usage)
        self._record_llm_call(
            model or self.model(), out.usage, time.monotonic() - t0, finish_reason,
            streaming=True, tool_calls_count=len(calls),
        )
        return out

    def _to_litellm(self, messages: list[Message]) -> list[dict]:
        system_block: dict = {"type": "text", "text": self._system}
        if not self._disable_cache_control:
            system_block["cache_control"] = {"type": "ephemeral"}
        out = [{"role": "system", "content": [system_block]}] if self._system else []
        raw_msgs = []
        for m in messages:
            if m.role == Role.ASSISTANT:
                raw_msgs.append(self._assistant_msg(m))
            else:
                raw_msgs.extend(self._user_msgs(m))

        # Normalizar turnos consecutivos del mismo rol (ej. user + user)
        # para proveedores estrictos como Gemini que rechazan turnos no alternados con BadRequestError
        for d in raw_msgs:
            if out and out[-1].get("role") == "user" and d.get("role") == "user":
                c_prev = out[-1]["content"]
                c_curr = d["content"]
                if isinstance(c_prev, str) and isinstance(c_curr, str):
                    out[-1]["content"] = f"{c_prev}\n\n{c_curr}"
                elif isinstance(c_prev, list) and isinstance(c_curr, list):
                    out[-1]["content"] = c_prev + c_curr
                elif isinstance(c_prev, str) and isinstance(c_curr, list):
                    out[-1]["content"] = [{"type": "text", "text": c_prev}] + c_curr
                elif isinstance(c_prev, list) and isinstance(c_curr, str):
                    out[-1]["content"] = c_prev + [{"type": "text", "text": c_curr}]
            else:
                out.append(d)
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
