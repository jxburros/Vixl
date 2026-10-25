"""Completion webhooks (#579): POST the shared completion event to a receiver when a job, check-all or pipeline run ends.

A run asks for a webhook with ``notify: {url, secret_env}`` (on ``submit``, ``pipeline-run`` and ``check-all``), or
the workspace sets a default in ``.vixl/notify.json``: ``{"url": ..., "secret_env": ..., "allow": [host patterns]}``.
Only hosts in ``allow`` (exact names or ``*.suffix``) receive anything, so a request cannot send the event to a host
the workspace owner did not list. The POST goes through ``fetch.post_bounded``: HTTPS, the same public-address checks
as downloads (``VIXL_ALLOW_PRIVATE_FETCH=1`` for intranet receivers), plain HTTP only to a loopback address, no
redirects.

The body is the event without document content: kind, id, status, outcome state, counts, the report path, the error
code, the Vixl version, a time and the delivery id. With ``secret_env`` the body is signed: ``X-Vixl-Signature:
sha256=<HMAC-SHA256 of the body with the secret>``; ``X-Vixl-Delivery`` is a fresh id per event (the same across its
retries, so a receiver can drop duplicates). A 5xx, 408, 429 or a transport failure is retried 3 times with backoff;
any other status ends the delivery. Nothing is sent while ``VIXL_OFFLINE`` is set. The returned delivery record goes
into the job record (``deliveries``) or the run's result (``notify``).
"""

from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
import re
import time
from urllib.parse import urlsplit
import uuid

from ...errors import VixlError, require

CONFIG = ".vixl/notify.json"
RETRIES = 3
BACKOFF = (0.5, 1.0, 2.0)
RETRY_STATUS = (408, 429)
ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")
FIELDS = {"url", "secret_env"}
CONFIG_FIELDS = {"url", "secret_env", "allow"}
SCHEMA = {"type": "object", "description": "Send the completion event to a webhook when the run ends: {url, "
          "secret_env}. The host must be in the allow list of .vixl/notify.json; the body has no document content and "
          "is signed with the secret in the environment variable secret_env (X-Vixl-Signature: sha256=...).",
          "properties": {"url": {"type": "string", "description": "The receiver: an https URL (http only to "
                                 "localhost)."},
                         "secret_env": {"type": "string", "description": "Name of the environment variable that holds "
                                        "the signing secret."}}}


def validate(value, field="notify", allowed=FIELDS):
    require(isinstance(value, dict) and set(value) <= allowed,
            f"{field} is {{{', '.join(sorted(allowed))}}}", field=field, allowed=sorted(allowed))
    if "url" in value or allowed == FIELDS:
        require(isinstance(value.get("url"), str) and value["url"].strip(), f"{field}.url is the receiver URL",
                field=f"{field}.url")
        scheme = urlsplit(value["url"]).scheme.lower()
        require(scheme in ("https", "http"), f"{field}.url is an https URL", "unsafe_url", field=f"{field}.url")
    if value.get("secret_env") is not None:
        require(isinstance(value["secret_env"], str) and ENV_NAME.fullmatch(value["secret_env"]),
                f"{field}.secret_env names an environment variable", field=f"{field}.secret_env")
    if "allow" in value:
        require(isinstance(value["allow"], list) and all(isinstance(item, str) and item for item in value["allow"]),
                f"{field}.allow is a list of host names or *.suffix patterns", field=f"{field}.allow")
    return value


def config(workspace):
    """The workspace webhook settings (``.vixl/notify.json``), or {} without one."""
    from pathlib import Path

    from ...production import read_json

    if not workspace:
        return {}
    path = Path(workspace) / CONFIG
    if not path.is_file():
        return {}
    return validate(read_json(path), CONFIG, CONFIG_FIELDS)


def body(event, delivery):
    """What is sent: the event's facts, never document content (no layer text, names or the workspace path)."""
    from ... import __version__

    counts = {str(key): value for key, value in (event.get("counts") or {}).items()
              if isinstance(value, int) and not isinstance(value, bool)}
    report = event.get("report")
    return {"event": event.get("event", "job-complete"), "kind": event.get("kind"), "id": event.get("id"),
            "status": event.get("status"), "state": event.get("state"), "counts": counts,
            "report": report if isinstance(report, str) else None, "error": event.get("error"),
            "vixl_version": __version__, "delivery": delivery,
            "time": datetime.now(timezone.utc).replace(microsecond=0).isoformat()}


def _shown(url):
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.hostname}{':' + str(parts.port) if parts.port else ''}{parts.path}"


def send(url, payload, secret, delivery):
    """POST ``payload`` with retries; returns the delivery record (attempts, final HTTP status, delivered)."""
    from ...fetch import post_bounded

    data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json", "X-Vixl-Event": payload["event"], "X-Vixl-Delivery": delivery}
    if secret:
        headers["X-Vixl-Signature"] = "sha256=" + hmac.new(secret.encode("utf-8"), data, hashlib.sha256).hexdigest()
    attempts, status, error = 0, None, None
    for attempt in range(RETRIES + 1):
        attempts += 1
        try:
            status, error = post_bounded(url, data, headers, label="Webhook", loopback_http=True)["status"], None
        except VixlError as exc:
            if exc.code != "fetch_failed":
                raise
            status, error = None, str(exc)
        if status is not None and 200 <= status < 300:
            break
        if status is not None and status < 500 and status not in RETRY_STATUS:
            break
        if attempt < RETRIES:
            time.sleep(BACKOFF[min(attempt, len(BACKOFF) - 1)])
    delivered = status is not None and 200 <= status < 300
    return {"status": "delivered" if delivered else "failed", "attempts": attempts, "http_status": status,
            "signed": bool(secret), **({"error": error} if error and not delivered else {})}


def deliver(event):
    """The ``job-complete`` hook: send the event when the run asked for a webhook or the workspace sets one."""
    from ...fetch import host_listed, offline

    workspace = event.get("workspace")
    try:
        settings = config(workspace)
        wanted = event.get("notify")
        if wanted is None and settings.get("url"):
            wanted = {key: settings[key] for key in ("url", "secret_env") if key in settings}
        if not wanted:
            return None
        validate(wanted)
    except VixlError as exc:
        return {"hook": "notify", "status": "refused", "reason": str(exc)}
    delivery = uuid.uuid4().hex
    record = {"hook": "notify", "delivery": delivery, "url": _shown(wanted["url"])}
    if offline():
        return {**record, "status": "skipped", "reason": "offline (VIXL_OFFLINE): nothing was sent"}
    host = urlsplit(wanted["url"]).hostname or ""
    allow = settings.get("allow") or []
    if not host_listed(host, [item.lower().rstrip(".") for item in allow]):
        return {**record, "status": "refused", "reason": f"{host} is not in the allow list of {CONFIG}"
                + ("" if allow else " (there is none)")}
    secret = None
    if wanted.get("secret_env"):
        secret = os.environ.get(wanted["secret_env"])
        if not secret:
            return {**record, "status": "refused", "reason": f"the secret variable {wanted['secret_env']} is not set"}
    try:
        return {**record, **send(wanted["url"], body(event, delivery), secret, delivery)}
    except VixlError as exc:
        return {**record, "status": "refused", "reason": str(exc)}
