"""Run a brief through every chosen arm, as separate sessions of the same model, then follow-up rounds.

A run is ``repeats`` x ``arms`` sessions. Each session has its own workspace and conversation; nothing is shared
between sessions except the model. Round 1 sends the brief. Each follow-up round sends one more message to every
session, which continues its own conversation in its own workspace, so the arms stay comparable change by change.

On disk, per session (``<results>/runs/<run>/<session>/``):

    workspace/              the live working folder
    rounds/<n>/files/       a snapshot of the workspace after round n
    rounds/<n>/preview.png  the round's main deliverable as an image
    system-prompt.txt       the system prompt the session was given
    tools.json              the tool definitions it was given
    conversation.json       the conversation so far (so follow-ups work after a restart)
    events.jsonl            every turn and tool call, with full arguments, tagged with its round
    python/                 the scripts the code arm ran

Keys stay in memory for the life of the server process.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
import time
import uuid

from . import arms as arm_tools
from . import previews
from .providers import PRESETS, ProviderConfig, ProviderError, empty_usage, make_chat, redact

EFFORTS = {"", "low", "medium", "high", "xhigh", "max", "minimal"}
EVENT_TEXT = 12000  # characters of a model message or tool output kept in the log
LIVE = ("queued", "running")


@dataclass
class RunSpec:
    prompt: str
    provider: str
    model: str
    base_url: str = ""
    arms: list = field(default_factory=lambda: ["bare", "code", "vixl"])
    repeats: int = 1
    max_turns: int = 30
    max_tokens: int = 16000
    effort: str = ""
    extra: dict = field(default_factory=dict)
    vision: bool = True
    skill: bool = True
    session_minutes: float = 20
    parallel: int = 3
    price_in: float | None = None  # $ per million input tokens
    price_out: float | None = None

    @classmethod
    def parse(cls, data):
        known = {name: data[name] for name in cls.__dataclass_fields__ if name in data}
        spec = cls(**known)
        spec.prompt = str(spec.prompt or "").strip()
        if not spec.prompt:
            raise ValueError("the prompt is empty")
        if spec.provider not in PRESETS:
            raise ValueError(f"unknown provider {spec.provider!r}")
        if not str(spec.model or "").strip():
            raise ValueError("choose a model")
        spec.model = spec.model.strip()
        spec.arms = [arm for arm in arm_tools.ARMS if arm in (spec.arms or [])]
        if not spec.arms:
            raise ValueError("choose at least one arm")
        spec.repeats = max(1, min(int(spec.repeats), 10))
        spec.max_turns = max(1, min(int(spec.max_turns), 200))
        spec.max_tokens = max(256, min(int(spec.max_tokens), 128000))
        spec.parallel = max(1, min(int(spec.parallel), 8))
        spec.session_minutes = max(1.0, min(float(spec.session_minutes), 240.0))
        if spec.effort not in EFFORTS:
            raise ValueError(f"effort must be one of {', '.join(sorted(e for e in EFFORTS if e))}")
        if not isinstance(spec.extra, dict):
            raise ValueError("extra request fields must be a JSON object")
        for name in ("price_in", "price_out"):
            value = getattr(spec, name)
            setattr(spec, name, float(value) if value not in (None, "") else None)
        return spec

    def provider_config(self, api_key):
        return ProviderConfig(provider=self.provider, model=self.model, base_url=self.base_url, api_key=api_key,
                              max_tokens=self.max_tokens, effort=self.effort, extra=dict(self.extra),
                              vision=self.vision)


def cost(usage, spec):
    if spec.price_in is None or spec.price_out is None:
        return None
    # Cache reads at a tenth of the input price and cache writes at 1.25x: Anthropic's rates; other providers
    # report cached tokens the same way or not at all.
    paid_in = usage["input"] + usage["cache_read"] * 0.1 + usage["cache_write"] * 1.25
    return round((paid_in * spec.price_in + usage["output"] * spec.price_out) / 1_000_000, 5)


def clip(text, limit=EVENT_TEXT):
    text = text or ""
    return text if len(text) <= limit else text[:limit] + f"\n… ({len(text) - limit} more characters)"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def snapshot(workspace, target, previous):
    """Copy the workspace's files to ``target``; return what changed since the ``previous`` snapshot."""
    changed = []
    seen = set()
    for item in previews.deliverables(workspace):
        source, copy = Path(workspace) / item["path"], Path(target) / item["path"]
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, copy)
        seen.add(item["path"])
        before = Path(previous) / item["path"] if previous else None
        if before is None or not before.is_file():
            changed.append({"path": item["path"], "change": "added"})
        elif digest(before) != digest(copy):
            changed.append({"path": item["path"], "change": "modified"})
    if previous and Path(previous).is_dir():
        for item in previews.deliverables(previous):
            if item["path"] not in seen:
                changed.append({"path": item["path"], "change": "removed"})
    return changed


class Session:
    """One arm's conversation in one repeat. It stays in memory between rounds (with its tools still open) and can
    be rebuilt from ``conversation.json`` after a restart."""

    def __init__(self, lab, run_id, session_id, arm, repeat, spec, api_key):
        self.lab, self.run_id, self.id, self.arm, self.repeat = lab, run_id, session_id, arm, repeat
        self.spec, self.api_key = spec, api_key
        self.folder = lab.root / "runs" / run_id / session_id
        self.workspace = self.folder / "workspace"
        self.events = lab.events.setdefault(session_id, [])
        self.chat = self.toolbox = None
        self.round, self.started = 0, None

    def emit(self, kind, **fields):
        event = {"round": self.round, "t": round(time.time() - (self.started or time.time()), 2), "kind": kind,
                 "at": round(time.time(), 2), **fields}
        self.events.append(event)
        with open(self.folder / "events.jsonl", "a", encoding="utf-8") as log:
            log.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")

    def save_conversation(self):
        if self.chat is not None:
            text = json.dumps(self.chat.state(), ensure_ascii=False, default=str)
            (self.folder / "conversation.json").write_text(redact(text, self.api_key), encoding="utf-8")

    def prepare(self, prompt):
        """Open the tools and the conversation; return the message to send this round."""
        if self.toolbox is None:
            self.toolbox = arm_tools.build(self.arm, self.workspace, self.folder, skill=self.spec.skill)
        if self.chat is not None:
            return prompt
        self.chat = self.lab.chat_factory(self.spec.provider_config(self.api_key))
        saved = self.folder / "conversation.json"
        if self.round > 1 and saved.is_file():
            self.chat.restore(json.loads(saved.read_text(encoding="utf-8")))
            self.emit("note", text="Continued the saved conversation; the tools were restarted, so open documents "
                                   "must be opened again.")
            return prompt
        self.chat.start(self.toolbox.system, self.toolbox.definitions())
        (self.folder / "system-prompt.txt").write_text(self.toolbox.system, encoding="utf-8")
        (self.folder / "tools.json").write_text(json.dumps(self.toolbox.definitions(), indent=2), encoding="utf-8")
        if self.round > 1:
            # The first round never reached the model; start over with the brief and the change together.
            self.emit("note", text="No earlier conversation was saved; sent the brief together with this change.")
            return f"{self.spec.prompt}\n\nThen make this change:\n{prompt}"
        return prompt

    def run_round(self, number, prompt):
        spec, store = self.spec, self.lab.store
        self.round = number
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.started = time.time()
        store.set_session_status(self.id, "running")
        store.save_generation(self.id, number, status="running", started=self.started)
        self.emit("status", status="running", prompt=prompt)
        usage, metrics = empty_usage(), {"turns": 0, "tool_calls": 0, "tool_errors": 0, "images": 0}
        status, error, final, replies = "done", "", "", []
        deadline = self.started + spec.session_minutes * 60
        try:
            message = self.prepare(prompt)
            self.chat.add_user([{"type": "text", "text": message}])
            while True:
                if self.lab.cancelled(self.run_id):
                    status = "cancelled"
                    break
                if metrics["turns"] >= spec.max_turns:
                    status = "turn limit"
                    break
                if time.time() > deadline:
                    status = "time limit"
                    break
                metrics["turns"] += 1
                turn = self.chat.step()
                for key in usage:
                    usage[key] += turn.usage.get(key, 0)
                if turn.text:
                    replies.append(turn.text)
                self.emit("turn", n=metrics["turns"], text=clip(turn.text), stop=turn.stop, usage=turn.usage,
                          calls=[arm_tools.describe_call(c.name, c.arguments) for c in turn.calls],
                          tool_calls=[{"id": c.id, "name": c.name, "arguments": c.arguments,
                                       "invalid": c.invalid} for c in turn.calls])
                if turn.again:
                    continue
                if not turn.calls:
                    if turn.stop in ("refusal", "length", "max_tokens"):
                        status = {"refusal": "refused"}.get(turn.stop, "output limit")
                    final = turn.text
                    break
                results = []
                for call in turn.calls:
                    if call.invalid:
                        failed, blocks = True, arm_tools.text(call.invalid)
                    else:
                        failed, blocks = self.toolbox.call(call.name, call.arguments)
                    metrics["tool_calls"] += 1
                    metrics["tool_errors"] += failed
                    images = sum(b["type"] == "image" for b in blocks)
                    metrics["images"] += images
                    shown = " ".join(b.get("text", "") for b in blocks if b["type"] == "text")
                    self.emit("tool", id=call.id, name=call.name, error=failed, images=images, output=clip(shown))
                    results.append((call, failed, blocks))
                self.chat.add_results(results)
            if self.arm == "bare":
                written = arm_tools.extract_files("\n\n".join(replies), self.workspace)
                self.emit("note", text=f"Saved from the reply: {', '.join(written) or 'nothing'}")
        except ProviderError as exc:
            status, error = "failed", str(exc)
        except Exception as exc:  # noqa: BLE001 - one broken session must not stop the run
            status, error = "failed", redact(f"{type(exc).__name__}: {exc}", self.api_key)
        if error:
            self.emit("error", text=error)
        try:
            self.save_conversation()
        except Exception as exc:  # noqa: BLE001 - a conversation that cannot be saved only blocks a restart
            self.emit("note", text=f"The conversation could not be saved: {exc}")
        round_folder = self.folder / "rounds" / str(number)
        previous = self.folder / "rounds" / str(number - 1) / "files" if number > 1 else None
        changed = snapshot(self.workspace, round_folder / "files", previous)
        preview, note = previews.make_preview(round_folder / "files", round_folder / "preview.png",
                                              prefer={c["path"] for c in changed if c["change"] != "removed"})
        if preview and number > 1 and not changed:
            note = "nothing changed in this round"
        metrics.update(usage, seconds=round(time.time() - self.started, 1), cost=cost(usage, spec))
        files = previews.deliverables(round_folder / "files")
        metrics["files"] = len(files)
        store.save_generation(self.id, number, status=status, metrics=metrics, error=error, preview=preview or "",
                              preview_note=note, final=final[:8000], files=files, changed=changed,
                              finished=time.time())
        store.set_session_status(self.id, status)
        self.emit("status", status=status, preview=preview, note=note)

    def close(self):
        if self.toolbox is not None:
            self.toolbox.close()
            self.toolbox = None


class Lab:
    def __init__(self, root, chat_factory=make_chat):
        from .store import Store

        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = Store(self.root / "lab.db")
        self.chat_factory = chat_factory
        self.events = {}
        self.live = {}  # session id -> Session, kept between rounds
        self.keys = {}  # (provider, base_url) -> key, this process only
        self._cancelled = set()
        self.threads = {}
        self.judging = set()
        for run in self.store.runs():  # a run left "running" by a stopped server is not running now
            if run["status"] == "running":
                self.store.set_run_status(run["id"], "interrupted")

    # --- keys ----------------------------------------------------------------------------------------------------

    def resolve_key(self, provider, base_url, given):
        preset = PRESETS[provider]
        slot = (provider, (base_url or preset["base_url"]).rstrip("/"))
        if given:
            self.keys[slot] = given
            return given
        if slot in self.keys:
            return self.keys[slot]
        for name in preset["env"]:
            if os.environ.get(name):
                return os.environ[name]
        if preset["key_required"]:
            raise ValueError(f"{preset['label']} needs an API key: paste one or set {' or '.join(preset['env'])}")
        return ""

    def key_known(self, provider, base_url=""):
        try:
            return bool(self.resolve_key(provider, base_url, ""))
        except ValueError:
            return False

    # --- runs and rounds -----------------------------------------------------------------------------------------

    def start(self, data, api_key=""):
        spec = RunSpec.parse(data)
        key = self.resolve_key(spec.provider, spec.base_url, api_key)
        run_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        (self.root / "runs" / run_id).mkdir(parents=True)
        self.store.add_run(run_id, asdict(spec))
        sessions = []
        for repeat in range(spec.repeats):
            for arm in spec.arms:
                session_id = f"{arm}-{repeat + 1}-{uuid.uuid4().hex[:4]}"
                (self.root / "runs" / run_id / session_id).mkdir()
                self.store.add_session(session_id, run_id, arm, repeat)
                self.store.save_generation(session_id, 1)
                session = Session(self, run_id, session_id, arm, repeat, spec, key)
                self.live[session_id] = session
                sessions.append(session)
        self._launch(run_id, sessions, 1, spec.prompt, spec.parallel)
        return run_id

    def follow_up(self, run_id, prompt, api_key=""):
        """Send one more message to every session of a finished run; return the round's number."""
        prompt = str(prompt or "").strip()
        if not prompt:
            raise ValueError("the follow-up is empty")
        if self.busy(run_id):
            raise ValueError("wait for the current round to finish")
        run = self.store.run(run_id)
        if run is None:
            raise KeyError(run_id)
        spec = RunSpec.parse(run["spec"])
        key = self.resolve_key(spec.provider, spec.base_url, api_key)
        number = len(run["rounds"]) + 1
        self.store.add_round(run_id, number, prompt)
        self._cancelled.discard(run_id)
        sessions = []
        for row in run["sessions"]:
            session = self.live.get(row["id"])
            if session is None:
                session = Session(self, run_id, row["id"], row["arm"], row["repeat"], spec, key)
                self.live[row["id"]] = session
            session.api_key = key
            self.store.save_generation(row["id"], number)
            self.store.set_session_status(row["id"], "queued")
            sessions.append(session)
        self.store.set_run_status(run_id, "running")
        self._launch(run_id, sessions, number, prompt, spec.parallel)
        return number

    def _launch(self, run_id, sessions, number, prompt, parallel):
        def work():
            with ThreadPoolExecutor(max_workers=parallel) as pool:
                list(pool.map(lambda session: session.run_round(number, prompt), sessions))
            self.store.set_run_status(run_id, "cancelled" if self.cancelled(run_id) else "done")

        thread = threading.Thread(target=work, daemon=True)
        self.threads[run_id] = thread
        thread.start()

    def busy(self, run_id):
        thread = self.threads.get(run_id)
        return thread is not None and thread.is_alive()

    def wait(self, run_id, timeout=None):
        thread = self.threads.get(run_id)
        if thread is not None:
            thread.join(timeout)

    def cancel(self, run_id):
        self._cancelled.add(run_id)

    def cancelled(self, run_id):
        return run_id in self._cancelled

    def delete(self, run_id):
        if self.busy(run_id):
            raise ValueError("cancel the run and let it stop before deleting it")
        run = self.store.run(run_id)
        if run is None:
            raise KeyError(run_id)
        for session in run["sessions"]:
            self.events.pop(session["id"], None)
            live = self.live.pop(session["id"], None)
            if live is not None:
                live.close()
        self.store.delete_run(run_id)
        shutil.rmtree(self.root / "runs" / run_id, ignore_errors=True)

    def session_events(self, session_id, since=0):
        if session_id not in self.events:
            folder = self.session_folder(session_id)
            path = folder / "events.jsonl" if folder else None
            if path is None or not path.is_file():
                return []
            self.events[session_id] = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                                       if line.strip()]
        return self.events[session_id][since:]

    def session_folder(self, session_id):
        session = self.store.session(session_id)
        return self.root / "runs" / session["run_id"] / session_id if session else None

    # --- judging -------------------------------------------------------------------------------------------------

    def judge(self, run_id, data, api_key=""):
        """Score every preview of one round (the latest unless ``round`` is given) in the background."""
        from .judging import judge_session

        run = self.store.run(run_id)
        if run is None:
            raise KeyError(run_id)
        provider = data.get("provider") or run["provider"]
        if provider not in PRESETS:
            raise ValueError(f"unknown provider {provider!r}")
        base_url = data.get("base_url", run["spec"].get("base_url", "") if provider == run["provider"] else "")
        model = (data.get("model") or run["model"]).strip()
        number = int(data.get("round") or len(run["rounds"]))
        key = self.resolve_key(provider, base_url, api_key)
        config = ProviderConfig(provider=provider, model=model, base_url=base_url, api_key=key, max_tokens=2000)
        prompts = [r["prompt"] for r in run["rounds"] if r["round"] <= number]
        brief = prompts[0] + "".join(f"\n\nFollow-up change {i + 2}: {p}" for i, p in enumerate(prompts[1:]))
        targets = [s for s in run["sessions"]
                   for g in s["generations"] if g["round"] == number and g["preview"]]
        if not targets:
            raise ValueError(f"no session left anything to judge in round {number}")
        self.judging.add(run_id)

        def work():
            try:
                for session in targets:
                    image = self.session_folder(session["id"]) / "rounds" / str(number) / "preview.png"
                    result = judge_session(self.chat_factory, config, brief, image.read_bytes())
                    self.store.judgment(session["id"], number, f"{provider}:{model}", result)
            finally:
                self.judging.discard(run_id)

        threading.Thread(target=work, daemon=True).start()
        return len(targets)
