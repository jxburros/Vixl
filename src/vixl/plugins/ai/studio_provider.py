"""The ``studio`` provider: every AI capability through an AI Server Studio gateway, for ``vixl host``.

AI Server Studio has not published a gateway contract. This module is Vixl's proposal (documented in
``docs/reference/providers.md``, "Studio gateway"), kept here alone so it is easy to change when Studio's contract
arrives:

* one ``POST {url}/v1/{capability}`` per call, for the capabilities in ``models.CAPABILITIES``;
* the body is ``{"capability", "constraints", "inputs"}``: what the call needs, never a model (the gateway chooses);
* headers: ``Authorization: Bearer TOKEN`` (from ``--provider-token-env``), ``X-Call-Context`` echoing the host
  request's header when it had one, and ``X-Vixl-Version``;
* a success answers the capability's result object (the shapes of the generic ``http`` gateway, plus an optional
  ``model`` naming what the gateway used, which provenance records);
* an error answers a non-2xx status with ``{"error": {"code", "message", "retry_after"?}}``: ``refused`` (or
  403/451) is ``provider_refused``, ``limit_exceeded`` (or 402/429) is ``limit_exceeded``, anything else
  ``provider_error``.

The provider exists only in-process: ``vixl host --provider studio --provider-url URL --provider-token-env ENV``
registers it (``activate``), never providers.json. While it is active ``models.route`` and ``ai.provider`` return it
for every capability and refuse any other provider, and offline mode lets exactly this URL through.
"""

import json
import os
from urllib.parse import urlparse

import httpx

from ...errors import VixlError, require

NAME = "studio"
TYPE = "studio"
API = "/v1"
TIMEOUT = 120
# Request fields that bound the result rather than describe it; the rest of a request are its inputs.
CONSTRAINTS = ("width", "height", "seed", "strength", "mode", "scale")
DROPPED = ("model", "capability")  # The gateway picks the model; the capability is in the path and the body.
MESSAGE = 300  # A gateway message is untrusted text; at most this much reaches an error.

_ACTIVE = None


class StudioProvider:
    """Sends each capability call to the gateway; ``transport`` (an ``httpx`` transport) is for tests."""

    transport = None
    fit_output = False

    def __init__(self, url, token, *, timeout=TIMEOUT):
        from .ai import require_secure_url

        parsed = urlparse(url or "")
        require(parsed.scheme in ("http", "https") and parsed.hostname and not parsed.username
                and not parsed.password and not parsed.query and not parsed.fragment,
                "--provider-url is the gateway's base URL: https://HOST[:PORT][/PATH], no credentials or query",
                "provider_not_configured", field="provider_url")
        require_secure_url(NAME, url, {})  # https, or plain http to a loopback gateway only.
        require(isinstance(token, str) and token, "The studio provider needs its gateway token",
                "provider_not_configured", field="provider_token_env")
        self.name = NAME
        self.url = url.rstrip("/")
        self.timeout = timeout
        self._token = token
        self.config = {"type": TYPE, "url": self.url}

    def __repr__(self):  # Never the token.
        return f"StudioProvider({self.url!r})"

    def endpoint(self, capability):
        from .models import CAPABILITIES

        require(capability in CAPABILITIES, f"The studio gateway has no capability {capability!r}",
                "unsupported_capability", field="capability", allowed=list(CAPABILITIES))
        return f"{self.url}{API}/{capability}"

    def headers(self):
        from ... import __version__
        from ...calls import CALL_CONTEXT, CALL_CONTEXT_HEADER

        headers = {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json",
                   "Accept": "application/json", "X-Vixl-Version": __version__}
        context = CALL_CONTEXT.get()
        if context is not None:
            headers[CALL_CONTEXT_HEADER] = context
        return headers

    @staticmethod
    def body(capability, request):
        constraints = {key: request[key] for key in CONSTRAINTS if request.get(key) is not None}
        inputs = {key: value for key, value in request.items()
                  if key not in CONSTRAINTS and key not in DROPPED and value is not None}
        return {"capability": capability, "constraints": constraints, "inputs": inputs}

    def invoke(self, capability, request):
        from ...fetch import network_allowed
        from .ai import MAX_RESPONSE

        url = self.endpoint(capability)
        network_allowed("The studio AI gateway", url)
        payload = json.dumps(self.body(capability, request)).encode()
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=False, transport=self.transport) as client:
                with client.stream("POST", url, headers=self.headers(), content=payload) as response:
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        require(len(data) <= MAX_RESPONSE, "The studio gateway's answer exceeds the limit",
                                "resource_limit")
                    status = response.status_code
        except httpx.HTTPError as exc:
            raise VixlError("provider_error", f"The studio gateway request failed ({type(exc).__name__})",
                            provider=NAME, hint="Check that AI Server Studio is running at --provider-url") from exc
        try:
            result = json.loads(bytes(data)) if data else {}
        except ValueError:
            result = None
        if not 200 <= status < 300:
            raise gateway_error(status, result)
        require(isinstance(result, dict), "The studio gateway must answer a JSON object", "provider_error",
                provider=NAME)
        if capability == "detect":
            from .ai import normalize_vision

            size = (request.get("width"), request.get("height"))
            result = normalize_vision(capability, result, size=size if all(isinstance(v, int) for v in size) else None)
        return result


def gateway_error(status, body):
    """The VixlError for a gateway's non-2xx answer (``{"error": {code, message, retry_after?}}``)."""
    error = body.get("error") if isinstance(body, dict) else None
    error = error if isinstance(error, dict) else {}
    code = error.get("code") if isinstance(error.get("code"), str) else ""
    message = error.get("message") if isinstance(error.get("message"), str) else ""
    message = " ".join(message.split())[:MESSAGE]
    details = {"provider": NAME, "status": status, **({"gateway_code": code[:64]} if code else {})}
    said = f": {message}" if message else ""
    if code == "refused" or (not code and status in (403, 451)):
        return VixlError("provider_refused", f"The studio gateway refused the request{said}", **details,
                         hint="Change the request; the gateway's policy does not allow it")
    if code == "limit_exceeded" or (not code and status in (402, 429)):
        retry = error.get("retry_after")
        if isinstance(retry, (int, float)) and not isinstance(retry, bool) and 0 <= retry <= 86400:
            details["retry_after"] = round(retry)
        return VixlError("limit_exceeded", f"The studio gateway's limit was reached{said}", limit="provider",
                         **details, hint="Wait and retry, or ask the Studio administrator for a higher limit")
    return VixlError("provider_error", f"The studio gateway answered HTTP {status}{said}", **details,
                     hint="Retry; if it fails again, check the gateway's logs")


def activate(url, token_env):
    """Register the studio provider for this process (``vixl host --provider studio``); returns ``{type, url}``."""
    global _ACTIVE
    from ...fetch import allow_offline

    require(isinstance(token_env, str) and token_env, "--provider studio needs --provider-token-env ENV",
            "provider_not_configured", field="provider_token_env")
    token = os.environ.get(token_env, "").strip()
    require(token, f"Set {token_env} to the studio gateway token", "provider_not_configured",
            field="provider_token_env")
    backend = StudioProvider(url, token)
    deactivate()
    allow_offline(backend.url + API)
    _ACTIVE = backend
    return {"type": TYPE, "url": backend.url}


def deactivate():
    global _ACTIVE
    from ...fetch import disallow_offline

    if _ACTIVE is not None:
        disallow_offline(_ACTIVE.url + API)
    _ACTIVE = None


def active():
    """The registered studio provider, or None."""
    return _ACTIVE


def selected(name=None):
    """The studio provider when it is active and ``name`` is it (or None); refuses any other provider while active.
    None when it is not active."""
    if _ACTIVE is None:
        return None
    if name not in (None, NAME):
        raise VixlError("forbidden", f"This host sends every AI call to its studio gateway; provider {name!r} is "
                        "not available", field="provider", allowed=[NAME],
                        hint="Leave provider out, or name studio")
    return _ACTIVE


# ---------------------------------------------------------------------------------------------------- vixl host


def host_flags(parser):
    """The ``host-flags`` hook: ``--provider studio --provider-url URL --provider-token-env ENV``."""
    parser.add_argument("--provider", choices=[NAME], help="Send every AI call to an AI Server Studio gateway")
    parser.add_argument("--provider-url", help="--provider studio: the gateway's base URL (https, or http on loopback)")
    parser.add_argument("--provider-token-env", help="--provider studio: the variable holding the gateway token")


AI_FIELDS = {"command", "args", "if_revision", "request_id"}
AI_COMMANDS = ("ask", "generate", "ai", "select", "detect", "ocr")


def host_routes(app, host):
    """The ``host-route`` hook: register the provider the host was started with (``host.options``), and
    ``POST /w/{ws}/documents/{id}/ai``, which runs an AI command on a document through that provider only."""
    options = host.options
    if getattr(options, "provider", None) == NAME:
        host.provider = activate(getattr(options, "provider_url", None), getattr(options, "provider_token_env", None))
    else:
        require(not getattr(options, "provider_url", None) and not getattr(options, "provider_token_env", None),
                "--provider-url and --provider-token-env go with --provider studio", "usage_error", field="provider")
        deactivate()  # The provider belongs to the host that registered it; a host without one has none.

    @app.post("/w/{ws}/documents/{doc}/ai")
    async def run_ai(ws: str, doc: str, body: dict):
        from ...interfaces import known_fields

        require(isinstance(body, dict), "The ai body is a JSON object", "invalid_request")
        known_fields(body, AI_FIELDS, "ai")
        command, args = body.get("command"), body.get("args", [])
        require(command in AI_COMMANDS, f"command is one of {', '.join(AI_COMMANDS)}", field="command",
                allowed=list(AI_COMMANDS))
        require(isinstance(args, list) and all(isinstance(item, str) for item in args),
                "args is a list of strings: the command's words and flags", field="args")
        require(not any(item == "--provider" or item.startswith("--provider=") for item in args),
                "The host chooses the provider", "forbidden", field="args")
        require(active() is not None, "This host has no AI provider; start it with --provider studio "
                "--provider-url URL --provider-token-env ENV", "provider_not_configured", field="provider")

        def apply(session, path):
            import hashlib

            target = session.resolve(path)
            before = hashlib.sha256(target.read_bytes()).digest()
            result = session.ai(command, list(args), document=path)
            changed = hashlib.sha256(target.read_bytes()).digest() != before
            return result, host.bump(ws, doc) if changed else None  # Still under the document's lock.

        def run():
            from ...untrusted import mark

            (result, bumped), revision = host.mutate(ws, doc, body.get("if_revision"), apply, bump=False)
            revision = bumped or revision
            return mark({**result, "id": doc, "revision": revision}) if isinstance(result, dict) else {
                "result": result, "id": doc, "revision": revision}

        return await host.call(ws, "ai", run, request_id=body.get("request_id"), document=doc,
                               body={k: v for k, v in body.items() if k != "request_id"})
