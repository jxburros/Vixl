"""Model providers for the lab: one Anthropic adapter and one adapter for OpenAI-compatible chat APIs.

Every provider is driven through the same small interface so the arms differ only in their tools:

    chat.start(system, tools)      tools: [{name, description, input_schema}]
    chat.add_user(blocks)          blocks: [{"type": "text", "text"}, {"type": "image", "media_type", "data"}]
    turn = chat.step()             one model call; returns a Turn
    chat.add_results(results)      [(Call, is_error, blocks)] for the turn's tool calls

OpenAI, Meta's Muse API, Moonshot's Kimi API, Ollama and LM Studio all speak the OpenAI Chat Completions format, so
they share ``OpenAIChat``. Chat Completions tool messages carry text only, so images a tool returns are sent in one
user message right after the tool messages. API keys live only on the adapter object; ``redact`` removes them from
any error text before it is shown or stored.
"""

from dataclasses import dataclass, field
import json
import time

PRESETS = {
    "anthropic": {"label": "Anthropic", "kind": "anthropic", "base_url": "https://api.anthropic.com",
                  "env": ["ANTHROPIC_API_KEY"], "key_required": True,
                  "suggestions": ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-2"]},
    "openai": {"label": "OpenAI", "kind": "openai", "base_url": "https://api.openai.com/v1",
               "env": ["OPENAI_API_KEY"], "key_required": True, "max_tokens_field": "max_completion_tokens"},
    "meta": {"label": "Meta (Muse)", "kind": "openai", "base_url": "https://api.meta.ai/v1",
             "env": ["META_API_KEY", "MODEL_API_KEY"], "key_required": True},
    "moonshot": {"label": "Moonshot (Kimi)", "kind": "openai", "base_url": "https://api.moonshot.ai/v1",
                 "env": ["MOONSHOT_API_KEY"], "key_required": True},
    "ollama": {"label": "Local: Ollama", "kind": "openai", "base_url": "http://localhost:11434/v1",
               "env": [], "key_required": False},
    "lmstudio": {"label": "Local: LM Studio", "kind": "openai", "base_url": "http://localhost:1234/v1",
                 "env": [], "key_required": False},
    "custom": {"label": "Other OpenAI-compatible", "kind": "openai", "base_url": "", "env": [], "key_required": False},
}

# Models that accept Anthropic's server-side refusal fallback (the same set the eval harness opts in for).
FALLBACK_MODELS = {"claude-fable-5-2", "claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}
RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}


class ProviderError(RuntimeError):
    """A model call failed; the message is safe to show (keys removed)."""


def redact(text, *secrets):
    text = str(text)
    for secret in secrets:
        if secret and len(secret) >= 6:
            text = text.replace(secret, "***")
    return text


@dataclass
class ProviderConfig:
    provider: str
    model: str
    base_url: str = ""
    api_key: str = field(default="", repr=False)
    max_tokens: int = 16000
    effort: str = ""
    extra: dict = field(default_factory=dict)
    vision: bool = True
    timeout: float = 600.0

    @property
    def preset(self):
        return PRESETS.get(self.provider, PRESETS["custom"])


@dataclass
class Call:
    id: str
    name: str
    arguments: dict
    invalid: str = ""  # set when the model's arguments were not a JSON object


@dataclass
class Turn:
    text: str
    calls: list
    usage: dict
    stop: str
    again: bool = False  # the model paused mid-turn and should be called again with no new input


def plain(value):
    """SDK objects (Anthropic content blocks) as JSON-ready dicts, keeping every field the API sent."""
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    if hasattr(value, "__dict__"):
        return {key: plain(item) for key, item in vars(value).items() if item is not None}
    return value


def empty_usage():
    return {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}


IMAGE_OFF = "[an image was returned here, but image input is turned off for this run]"


class AnthropicChat:
    """Anthropic Messages API through the official SDK. The assistant turn is appended unchanged so thinking blocks
    stay valid; all tool results of a turn go back in one user message."""

    def __init__(self, config, client=None):
        self.config = config
        if client is None:
            import anthropic

            options = {"api_key": config.api_key or None, "timeout": config.timeout, "max_retries": 3}
            if config.base_url and config.base_url.rstrip("/") != PRESETS["anthropic"]["base_url"]:
                options["base_url"] = config.base_url
            client = anthropic.Anthropic(**options)
        self.client = client
        self.system, self.tools, self.messages = "", [], []

    def start(self, system, tools):
        self.system = system
        self.tools = [{"name": t["name"], "description": t.get("description", ""), "input_schema": t["input_schema"]}
                      for t in tools]
        self.messages = []

    def _block(self, block):
        if block["type"] == "image":
            if not self.config.vision:
                return {"type": "text", "text": IMAGE_OFF}
            return {"type": "image", "source": {"type": "base64", "media_type": block["media_type"],
                                                "data": block["data"]}}
        return {"type": "text", "text": block.get("text", "")}

    def add_user(self, blocks):
        self.messages.append({"role": "user", "content": [self._block(b) for b in blocks]})

    def add_results(self, results):
        content = []
        for call, failed, blocks in results:
            content.append({"type": "tool_result", "tool_use_id": call.id, "is_error": bool(failed),
                            "content": [self._block(b) for b in blocks] or [{"type": "text", "text": "(no output)"}]})
        self.messages.append({"role": "user", "content": content})

    def step(self):
        config = self.config
        arguments = {"model": config.model, "max_tokens": config.max_tokens, "system": self.system,
                     "messages": self.messages, "cache_control": {"type": "ephemeral"}}
        if self.tools:
            arguments["tools"] = self.tools
        if config.effort:
            arguments["output_config"] = {"effort": config.effort}
        arguments.update(config.extra or {})
        try:
            if config.model in FALLBACK_MODELS:
                response = self.client.beta.messages.create(
                    betas=["server-side-fallback-2026-07-01"], fallbacks="default", **arguments)
            else:
                response = self.client.messages.create(**arguments)
        except Exception as exc:  # noqa: BLE001 - every SDK failure becomes one safe message
            status = getattr(exc, "status_code", None)
            message = getattr(exc, "message", None) or str(exc)
            raise ProviderError(redact(f"{type(exc).__name__}{f' {status}' if status else ''}: {message}",
                                       config.api_key)) from None
        self.messages.append({"role": "assistant", "content": response.content})
        text = "".join(getattr(b, "text", "") for b in response.content if getattr(b, "type", "") == "text")
        calls = [Call(b.id, b.name, dict(b.input or {})) for b in response.content
                 if getattr(b, "type", "") == "tool_use"]
        raw = response.usage
        usage = {"input": getattr(raw, "input_tokens", 0) or 0, "output": getattr(raw, "output_tokens", 0) or 0,
                 "cache_read": getattr(raw, "cache_read_input_tokens", 0) or 0,
                 "cache_write": getattr(raw, "cache_creation_input_tokens", 0) or 0}
        stop = response.stop_reason or ""
        return Turn(text, calls, usage, stop, again=stop == "pause_turn" and not calls)

    def state(self):
        """The conversation as JSON: enough to continue it after the server restarts."""
        return {"system": self.system, "tools": self.tools, "messages": plain(self.messages)}

    def restore(self, state):
        self.system, self.tools, self.messages = state["system"], state["tools"], state["messages"]

    def list_models(self):
        try:
            return sorted(m.id for m in self.client.models.list())
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(redact(f"{type(exc).__name__}: {getattr(exc, 'message', exc)}",
                                       self.config.api_key)) from None


# Fields of an assistant message that are sent back on the next request. Others (annotations, refusal, audio ...)
# are dropped because some OpenAI-compatible servers reject unknown fields in input messages; reasoning_content is
# kept because Moonshot's thinking models require it back.
ASSISTANT_FIELDS = ("role", "content", "tool_calls", "reasoning_content", "reasoning", "name")


def function_schema(schema):
    schema = {key: value for key, value in (schema or {}).items() if key != "$schema"}
    schema.setdefault("type", "object")
    schema.setdefault("properties", {})
    return schema


class OpenAIChat:
    """OpenAI Chat Completions, for OpenAI itself and every compatible server (Meta, Moonshot, Ollama, LM Studio)."""

    def __init__(self, config, http=None, sleep=time.sleep):
        import httpx

        self.config = config
        self.http = http or httpx.Client(timeout=config.timeout)
        self.sleep = sleep
        self.base = (config.base_url or config.preset["base_url"]).rstrip("/")
        if not self.base:
            raise ProviderError("this provider needs a base URL")
        self.headers = {"Content-Type": "application/json"}
        if config.api_key:
            self.headers["Authorization"] = f"Bearer {config.api_key}"
        self.tools, self.messages = [], []

    def start(self, system, tools):
        self.tools = [{"type": "function", "function": {"name": t["name"], "description": t.get("description", ""),
                                                        "parameters": function_schema(t["input_schema"])}}
                      for t in tools]
        self.messages = [{"role": "system", "content": system}]

    def _part(self, block):
        if block["type"] == "image" and self.config.vision:
            return {"type": "image_url",
                    "image_url": {"url": f"data:{block['media_type']};base64,{block['data']}"}}
        return {"type": "text", "text": IMAGE_OFF if block["type"] == "image" else block.get("text", "")}

    def add_user(self, blocks):
        parts = [self._part(b) for b in blocks]
        if all(p["type"] == "text" for p in parts):
            # Plain string content: the form every compatible server accepts, including text-only local models.
            self.messages.append({"role": "user", "content": "\n\n".join(p["text"] for p in parts)})
        else:
            self.messages.append({"role": "user", "content": parts})

    def add_results(self, results):
        images = []
        for call, failed, blocks in results:
            texts = []
            for block in blocks:
                if block["type"] == "image":
                    if self.config.vision:
                        images.append(block)
                        texts.append(f"[image {len(images)} is attached in the next message]")
                    else:
                        texts.append(IMAGE_OFF)
                else:
                    texts.append(block.get("text", ""))
            text = "\n".join(t for t in texts if t) or "(no output)"
            self.messages.append({"role": "tool", "tool_call_id": call.id,
                                  "content": f"ERROR: {text}" if failed else text})
        if images:
            self.messages.append({"role": "user", "content": [
                {"type": "text", "text": "Images returned by the tool calls above, in order:"}]
                + [self._part(b) for b in images]})

    def _request(self, method, path, body=None):
        import httpx

        url = f"{self.base}{path}"
        last = None
        for attempt in range(4):
            try:
                response = self.http.request(method, url, headers=self.headers,
                                             content=json.dumps(body) if body is not None else None)
            except httpx.HTTPError as exc:
                last = f"{type(exc).__name__}: {exc}"
            else:
                if response.status_code < 400:
                    try:
                        return response.json()
                    except ValueError:
                        raise ProviderError(f"{url} did not answer with JSON: {response.text[:200]!r}") from None
                last = f"HTTP {response.status_code}: {response.text[:800]}"
                if response.status_code not in RETRY_STATUS:
                    break
            if attempt < 3:
                self.sleep(2 ** (attempt + 1))
        raise ProviderError(redact(last, self.config.api_key))

    def step(self):
        config = self.config
        body = {"model": config.model, "messages": self.messages,
                config.preset.get("max_tokens_field", "max_tokens"): config.max_tokens}
        if self.tools:
            body["tools"] = self.tools
        if config.effort:
            body["reasoning_effort"] = config.effort
        body.update(config.extra or {})
        data = self._request("POST", "/chat/completions", body)
        try:
            choice = data["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError):
            raise ProviderError(redact(f"unexpected reply: {json.dumps(data)[:400]}", config.api_key)) from None
        kept = {key: message[key] for key in ASSISTANT_FIELDS if message.get(key) is not None}
        kept["role"] = "assistant"
        kept.setdefault("content", "")
        self.messages.append(kept)
        calls = []
        for index, tool_call in enumerate(message.get("tool_calls") or []):
            function = tool_call.get("function") or {}
            raw = function.get("arguments") or "{}"
            call = Call(tool_call.get("id") or f"call_{index}", function.get("name", ""), {})
            try:
                arguments = raw if isinstance(raw, dict) else json.loads(raw)
                if not isinstance(arguments, dict):
                    raise ValueError("not an object")
                call.arguments = arguments
            except ValueError as exc:
                call.invalid = f"the arguments were not a JSON object ({exc}): {str(raw)[:200]}"
            calls.append(call)
        raw_usage = data.get("usage") or {}
        cached = (raw_usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
        usage = {"input": max((raw_usage.get("prompt_tokens") or 0) - cached, 0),
                 "output": raw_usage.get("completion_tokens") or 0, "cache_read": cached, "cache_write": 0}
        text = message.get("content") or ""
        if isinstance(text, list):
            text = "".join(part.get("text", "") for part in text if isinstance(part, dict))
        return Turn(text, calls, usage, choice.get("finish_reason") or "")

    def state(self):
        return {"tools": self.tools, "messages": self.messages}

    def restore(self, state):
        self.tools, self.messages = state["tools"], state["messages"]

    def list_models(self):
        data = self._request("GET", "/models")
        items = (data.get("data") or data.get("models") or []) if isinstance(data, dict) else data
        names = [item.get("id") or item.get("name") if isinstance(item, dict) else str(item) for item in items]
        return sorted(name for name in names if name)


def make_chat(config):
    if config.preset["kind"] == "anthropic":
        return AnthropicChat(config)
    return OpenAIChat(config)
