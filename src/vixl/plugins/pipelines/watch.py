"""Watch mode (#569): re-check, re-run or re-sync when a file changes or a schedule comes round.

``vixl watch [--config .vixl/watch.json]`` keeps running; the ``watch`` workflow action runs a bounded number of
polls (``ticks``) and returns what ran. The config is ``{version: 1, name?, poll?, debounce?, triggers: [...]}``;
each trigger is ``{on, run, id?, documents?, group?, pipeline?, binding?, request?, every?, at?}``:

- ``on: save``: a document matching ``documents`` (globs; default every document) or in ``group`` was saved;
- ``on: source-change``: a document that others link to (or were merged from) changed: the dependency graph
  (``workspace_qa.dependents``) names its dependents. ``documents`` / ``group`` limit the sources watched;
- ``on: brand-change``: the content of ``brand.json`` changed;
- ``on: data-change``: a CSV that a data-sync binding, a merged sheet or a pipeline's ``inputs`` reads changed; the
  documents are the graph's ``data`` dependents of that file (``binding`` limits it to named bindings);
- ``on: schedule``: ``every: "24h"`` (``s``, ``m``, ``h``, ``d``; at least a minute) or ``at: "06:00"`` (each day, UTC).
  A schedule fires once per period, however long the watch was stopped, and its first period starts when the watch
  first sees it.

``run`` is ``check`` (check-all over the documents the trigger names), ``check-all`` (over the trigger's
``documents``/``group``, default every document), ``link-impact`` (per changed source; ``save`` and
``source-change`` only), ``pipeline`` (the saved ``pipeline``; skipped when its run record's digests show nothing
changed) or ``data-sync`` (the bindings whose CSV changed; ``data-change`` and ``schedule`` only). ``request`` adds the
action's own options (``checks``, ``fail_on``, ``suites``, ``notify``, ``exports`` ...).

Change detection polls modification times every ``poll`` seconds (default 1) and compares content digests, so a
touched file does not count; when the optional ``watchdog`` package is installed, a file event wakes the poll early.
The state (file digests, schedule times) is kept in ``.vixl-runs/watch/<name>.json``, so a watch started again sees
what changed while it was stopped; the very first start only records the files. Events wait ``debounce`` seconds
(default 0.5) after the last change and repeated events coalesce into one run. One run per document at a time: each
run holds a lock per document, and an event whose documents are busy waits for the next poll.

Every run is reported like ``check-all``: check runs record the check-all history and fire the shared completion
event (so webhooks fire), as do pipeline runs; link-impact and data-sync runs fire a ``watch`` completion event, and
link-impact results go to the history too. Exports are only written by a pipeline or a data-sync, under their own
rules: never over a file they did not write unless the step or request says ``overwrite: true``.
"""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import time

from ...design import named
from ...errors import VixlError, require

CONFIG = ".vixl/watch.json"
STATE = ".vixl-runs/watch"
POLL = 1.0
DEBOUNCE = 0.5
TRIGGERS = ("save", "source-change", "brand-change", "data-change", "schedule")
RUNS = ("check", "check-all", "link-impact", "pipeline", "data-sync")
DEFAULT_RUN = {"save": "check", "source-change": "link-impact", "brand-change": "check-all",
               "data-change": "data-sync", "schedule": "check-all"}
ALLOWED_RUNS = {"link-impact": ("save", "source-change"), "data-sync": ("data-change", "schedule")}
CONFIG_FIELDS = {"version", "name", "poll", "debounce", "triggers"}
TRIGGER_FIELDS = {"id", "on", "run", "documents", "group", "pipeline", "binding", "request", "every", "at"}
REQUEST_FIELDS = {
    "check": {"checks", "suites", "profile", "fail_on", "waivers", "notify", "since_last"},
    "check-all": {"checks", "suites", "profile", "fail_on", "waivers", "notify", "since_last"},
    "link-impact": {"checks", "suites", "profile", "fail_on", "waivers", "apply", "resize", "notify"},
    "pipeline": {"run", "notify"},
    "data-sync": {"exports", "fail_on", "suites", "overwrite", "notify"},
}
REQUEST = {"config", "watch", "ticks", "name"}
MAX_TRIGGERS = 32
MAX_TICKS = 600
MIN_EVERY = 60
KEEP_RUNS = 100
UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
PERIOD = re.compile(r"(\d+)([smhd])")
AT = re.compile(r"([01]\d|2[0-3]):([0-5]\d)")


class SystemClock:
    """Wall-clock seconds; tests swap in a fake clock (``CLOCK``)."""

    def time(self):
        return time.time()

    def sleep(self, seconds):
        time.sleep(seconds)


CLOCK = SystemClock()


# Configuration ----------------------------------------------------------------------------------

def every_seconds(value, field="every"):
    """Seconds of a period such as ``"24h"``, ``"90m"`` or ``"1h30m"``."""
    require(isinstance(value, str) and value and PERIOD.sub("", value.strip()) == "",
            f"{field} is a period such as 24h, 90m or 1h30m (units s, m, h, d)", field=field)
    seconds = sum(int(number) * UNITS[unit] for number, unit in PERIOD.findall(value))
    require(seconds >= MIN_EVERY, f"{field} is at least a minute", field=field)
    return seconds


def _strings(value, field):
    if isinstance(value, str):
        value = value.split()
    require(isinstance(value, list) and value and all(isinstance(item, str) and item for item in value),
            f"{field} is a list of globs or paths", field=field)
    return value


def validate(config):
    """Validate a watch config (raises ``VixlError`` naming the field); returns it with every trigger's ``id`` and
    ``run`` filled in."""
    from ...automation import bounded_object

    require(isinstance(config, dict), "A watch config is {version: 1, triggers: [...]}", field="watch")
    bounded_object(config, CONFIG_FIELDS, "Unknown watch config field")
    require(config.get("version", 1) == 1, "Watch config version must be 1", field="version")
    for field, low in (("poll", 0.05), ("debounce", 0.0)):
        if field in config:
            value = config[field]
            require(isinstance(value, (int, float)) and not isinstance(value, bool) and low <= value <= 3600,
                    f"{field} is a number of seconds ({low}-3600)", field=field)
    triggers = config.get("triggers")
    require(isinstance(triggers, list) and 0 < len(triggers) <= MAX_TRIGGERS,
            f"triggers is a list of 1-{MAX_TRIGGERS} triggers", field="triggers")
    found, ids = [], set()
    for index, trigger in enumerate(triggers):
        where = f"triggers[{index}]"
        require(isinstance(trigger, dict), f"{where} is a trigger object {{on, run, ...}}", field=where)
        bounded_object(trigger, TRIGGER_FIELDS, f"Unknown field in {where}")
        on = trigger.get("on")
        require(on in TRIGGERS, f"{where}.on is one of {', '.join(TRIGGERS)}", field=f"{where}.on",
                allowed=list(TRIGGERS))
        run = trigger.get("run", DEFAULT_RUN[on])
        require(run in RUNS, f"{where}.run is one of {', '.join(RUNS)}", field=f"{where}.run", allowed=list(RUNS))
        require(on in ALLOWED_RUNS.get(run, TRIGGERS), f"{where}: run {run} goes with on "
                f"{' or '.join(ALLOWED_RUNS.get(run, ()))}", field=f"{where}.run")
        ident = trigger.get("id") or f"{index + 1}-{on}"
        require(isinstance(ident, str) and ident not in ids, f"{where}.id is a unique name", field=f"{where}.id")
        ids.add(ident)
        item = {**trigger, "id": named(ident), "run": run}
        if "documents" in trigger:
            item["documents"] = _strings(trigger["documents"], f"{where}.documents")
        if "group" in trigger:
            require(isinstance(trigger["group"], str) and trigger["group"], f"{where}.group is a group name",
                    field=f"{where}.group")
        if "binding" in trigger:
            item["binding"] = _strings(trigger["binding"], f"{where}.binding")
        if run == "pipeline":
            require(isinstance(trigger.get("pipeline"), (str, dict)) and trigger["pipeline"],
                    f"{where}.pipeline names a saved pipeline (or is an inline one)", field=f"{where}.pipeline")
        else:
            require("pipeline" not in trigger, f"{where}.pipeline goes with run: pipeline", field=f"{where}.pipeline")
        request = trigger.get("request", {})
        require(isinstance(request, dict), f"{where}.request is an object of {run} options", field=f"{where}.request")
        bounded_object(request, REQUEST_FIELDS[run], f"Unknown {run} option in {where}.request")
        if on == "schedule":
            require(("every" in trigger) != ("at" in trigger), f"{where}: a schedule has every or at",
                    field=f"{where}.every")
            if "every" in trigger:
                every_seconds(trigger["every"], f"{where}.every")
            else:
                require(isinstance(trigger["at"], str) and AT.fullmatch(trigger["at"]),
                        f"{where}.at is a UTC time of day HH:MM", field=f"{where}.at")
        else:
            require(not ({"every", "at"} & set(trigger)), f"{where}: every and at go with on: schedule",
                    field=f"{where}.every")
        found.append(item)
    return {**config, "triggers": found}


def load_config(session, path=None):
    from ...production import read_json

    relative = path or CONFIG
    file = session.resolve(relative)
    require(file.is_file(), f"No watch config at {relative}; write one with triggers (see the production guide, "
            "Watch mode)", "not_found", field="config")
    return validate(read_json(file))


# The watcher ------------------------------------------------------------------------------------

def _digest(path):
    from ...production import file_digest

    try:
        return file_digest(path)
    except OSError:
        return None


class Watcher:
    """Poll the workspace, turn changes and schedules into debounced events, and run them (see the module)."""

    def __init__(self, session, config, *, name=None, clock=None, on_run=None):
        self.session = session
        self.config = validate(config)
        self.name = named(name or self.config.get("name") or "watch")
        self.clock = clock or CLOCK
        self.poll = float(self.config.get("poll", POLL))
        self.debounce = float(self.config.get("debounce", DEBOUNCE))
        self.triggers = self.config["triggers"]
        self.path = session.resolve(f"{STATE}/{self.name}.json")
        self.state = self._load()
        self.baseline = not self.state["files"] and not self.state.get("started")
        self.pending = {}
        self.runs = []
        self.on_run = on_run
        self.waker = None
        self._built = None

    # State --------------------------------------------------------------------------------------

    def _load(self):
        from ...production import read_json

        empty = {"version": 1, "files": {}, "schedule": {}}
        if not self.path.is_file():
            return empty
        try:
            value = read_json(self.path)
        except VixlError:
            return empty
        if not isinstance(value, dict) or not isinstance(value.get("files"), dict):
            return empty
        return {**empty, **value, "schedule": dict(value.get("schedule") or {})}

    def _save(self):
        from ...production import write_json

        write_json(self.path, {**self.state, "version": 1, "name": self.name})

    # Scanning -----------------------------------------------------------------------------------

    def graph(self):
        if self._built is None:
            from ..workspace_qa.dependents import graph

            self._built = graph(self.session)
        return self._built

    def _bindings(self):
        from .data_sync import bindings

        return bindings(self.session.workspace)

    def _pipeline(self, trigger):
        from .spec import resolve

        try:
            return resolve(self.session, trigger["pipeline"])[1]
        except VixlError:
            return {}

    def data_files(self):
        """CSVs and other data whose change is a ``data-change``: data-sync bindings, merged sheets' data and the
        ``inputs`` of the pipelines a data-change trigger runs."""
        files = {str(bind.get("data")) for bind in self._bindings().values() if bind.get("data")}
        if any(t["on"] == "data-change" for t in self.triggers):
            for target, items in self.graph()["reverse"].items():
                if any(item["kind"] == "data" for item in items):
                    files.add(target)
            for trigger in self.triggers:
                if trigger["on"] == "data-change" and trigger["run"] == "pipeline":
                    files.update(self._pipeline(trigger).get("inputs", []))
        return {Path(name).as_posix() for name in files}

    def watched(self):
        from ..workspace_qa.dependents import collect

        names = set(collect(self.session))
        names.add("brand.json")
        names |= self.data_files()
        return sorted(names)

    def changes(self):
        """``{path: added | changed | removed}`` since the last scan, by content (a touched file is not a change)."""
        known, changed, seen = self.state["files"], {}, {}
        for relative in self.watched():
            try:
                path = self.session.resolve(relative)
                stat = path.stat()
            except (OSError, VixlError):
                continue
            if not path.is_file():
                continue
            stamp = [stat.st_size, stat.st_mtime_ns]
            old = known.get(relative)
            if old and old[:2] == stamp:
                seen[relative] = old
                continue
            digest = _digest(path)
            seen[relative] = [*stamp, digest]
            if not old:
                changed[relative] = "added"
            elif old[2] != digest:
                changed[relative] = "changed"
        for relative in set(known) - set(seen):
            changed[relative] = "removed"
        dirty = seen != known
        self.state["files"] = seen
        return changed, dirty

    # Events -------------------------------------------------------------------------------------

    def _scope(self, trigger):
        """Documents a trigger names (``documents`` / ``group``), or None for every document."""
        from ..workspace_qa.workspace_checks import members

        if trigger.get("documents") is None and trigger.get("group") is None:
            return None
        paths, _ = members(self.session, {key: trigger[key] for key in ("documents", "group") if key in trigger},
                           allow_empty=True)
        return {self.session.relative(path) for path in paths}

    def _dependents(self, target, kinds):
        from ..workspace_qa.dependents import walk

        try:
            walked = walk(self.session, target, kinds=kinds, built=self.graph())
        except VixlError:
            return []
        return [item["document"] for item in walked["dependents"]]

    def match(self, trigger, changed):
        """``[(key, documents, sources, files)]``: the events ``changed`` raises for ``trigger``."""
        on, run = trigger["on"], trigger["run"]
        saved = sorted(path for path, kind in changed.items() if path.endswith(".vixl") and kind != "removed")
        if on in ("save", "source-change"):
            scope = self._scope(trigger) if saved else None
            sources = [path for path in saved if scope is None or path in scope]
            events = []
            for source in sources:
                documents = [source] if on == "save" else self._dependents(source, ("link", "template"))
                if on == "source-change" and not documents:
                    continue
                if run == "link-impact":
                    events.append(((trigger["id"], source), set(), {source}, {source}))
                else:
                    events.append(((trigger["id"],), set(documents), {source}, {source}))
            return events
        if on == "brand-change":
            if "brand.json" not in changed:
                return []
            scope = self._scope(trigger)
            return [((trigger["id"],), scope or set(), set(), {"brand.json"})]
        if on == "data-change":
            data = sorted(path for path in changed if not path.endswith(".vixl") and path != "brand.json")
            if not data:
                return []
            wanted = set(trigger.get("binding") or ())
            bound = {name: bind for name, bind in self._bindings().items() if not wanted or name in wanted}
            events = []
            for file in data:
                bindings = sorted(name for name, bind in bound.items() if Path(str(bind.get("data"))).as_posix() == file)
                documents = set(self._dependents(file, ("data",)))
                if wanted and not bindings:
                    continue
                if trigger["run"] == "pipeline":
                    if file not in self._pipeline(trigger).get("inputs", []) and not documents:
                        continue
                elif not documents and not bindings:
                    continue
                events.append(((trigger["id"],), documents, set(bindings), {file}))
            return events
        return []

    def due_schedule(self, trigger, now):
        """True once per period of a schedule trigger (and records the time it fired)."""
        last = self.state["schedule"].get(trigger["id"])
        if last is None:
            self.state["schedule"][trigger["id"]] = now  # the first period starts now
            return False
        if "every" in trigger:
            fire = now - last >= every_seconds(trigger["every"])
        else:
            hours, minutes = map(int, trigger["at"].split(":"))
            today = datetime.fromtimestamp(now, timezone.utc).replace(hour=hours, minute=minutes, second=0,
                                                                     microsecond=0)
            occurrence = today if today.timestamp() <= now else today - timedelta(days=1)
            fire = last < occurrence.timestamp()
        if fire:
            self.state["schedule"][trigger["id"]] = now
        return fire

    def enqueue(self, trigger, key, documents, sources, files, now):
        event = self.pending.get(key)
        if event is None:
            event = self.pending[key] = {"trigger": trigger, "documents": set(), "sources": set(), "files": set(),
                                         "events": 0, "first": now}
        event["documents"] |= documents
        event["sources"] |= sources
        event["files"] |= files
        event["events"] += 1
        event["due"] = now + self.debounce  # a later change pushes the run back: repeated saves coalesce

    def tick(self):
        """One poll: scan, raise events, then run the events that are due. Returns the runs it made."""
        now = self.clock.time()
        self._built = None
        changed, dirty = self.changes()
        if self.baseline:
            changed, self.baseline = {}, False  # the first start only records the files
            self.state["started"] = now
            dirty = True
        schedule = dict(self.state["schedule"])
        for trigger in self.triggers:
            if trigger["on"] == "schedule":
                if self.due_schedule(trigger, now):
                    self.enqueue(trigger, (trigger["id"],), self._scope(trigger) or set(), set(), set(), now)
            elif changed:
                for key, documents, sources, files in self.match(trigger, changed):
                    self.enqueue(trigger, key, documents, sources, files, now)
        if dirty or schedule != self.state["schedule"]:
            self._save()
        return self.drain(now)

    def drain(self, now=None, force=False):
        now = self.clock.time() if now is None else now
        done = []
        for key in sorted((k for k, e in self.pending.items() if force or e["due"] <= now), key=str):
            event = self.pending.pop(key)
            entry = self.execute(event, now)
            if entry is None:  # its documents are busy: try again at the next poll
                event["due"] = now + self.poll
                self.pending[key] = event
                continue
            done.append(entry)
        if done:
            self._save()
        return done

    # Running ------------------------------------------------------------------------------------

    def execute(self, event, now):
        """Run one event under a lock per document; None when another run holds one of them."""
        from contextlib import ExitStack

        from ...fileio import file_lock

        trigger = event["trigger"]
        documents = sorted(event["documents"] | event["sources"] if trigger["run"] == "link-impact"
                           else event["documents"])
        locks = self.session.resolve(f"{STATE}/locks")
        locks.mkdir(parents=True, exist_ok=True)
        try:
            with ExitStack() as stack:
                for relative in documents:
                    stack.enter_context(file_lock(str(locks / re.sub(r"[^A-Za-z0-9._-]+", "__", relative)),
                                                  timeout=0))
                started = datetime.fromtimestamp(now, timezone.utc).replace(microsecond=0).isoformat()
                try:
                    result = self.perform(trigger, event)
                except VixlError as exc:
                    result = {"status": "error", "passed": False, "error": exc.as_dict()}
        except Exception as exc:  # noqa: BLE001 - filelock raises its own Timeout type
            if type(exc).__name__ == "Timeout":
                return None
            raise
        entry = {"trigger": trigger["id"], "on": trigger["on"], "run": trigger["run"], "time": started,
                 "events": event["events"], "files": sorted(event["files"]),
                 **({"documents": documents} if documents else {}), **result}
        self.runs = [*self.runs, entry][-KEEP_RUNS:]
        if self.on_run:
            self.on_run(entry)
        return entry

    def perform(self, trigger, event):
        run = trigger["run"]
        request = dict(trigger.get("request") or {})
        documents = sorted(path for path in event["documents"] if self.session.resolve(path).is_file())
        if run in ("check", "check-all"):
            from ..workspace_qa.workspace_checks import run as check_all

            if run == "check" and documents:
                scope = {"documents": documents}
            elif run == "check" and event["documents"]:
                return {"status": "skipped", "passed": True, "reason": "the documents are gone"}
            else:
                scope = {key: trigger[key] for key in ("documents", "group") if key in trigger}
            result = check_all(self.session, {**request, **scope})
            return {"status": "completed", "passed": result["passed"],
                    "totals": {key: result["totals"][key] for key in ("passed", "failed", "needs_review", "error",
                                                                     "failing")},
                    "failing": [entry["path"] for entry in result["documents"] if entry["failing"]],
                    "history": result.get("history"), **({"notify": result["notify"]} if "notify" in result else {})}
        if run == "link-impact":
            return self._link_impact(trigger, event, request)
        if run == "pipeline":
            return self._pipeline_run(trigger, request)
        return self._data_sync(trigger, event, request)

    def _link_impact(self, trigger, event, request):
        from ..workspace_qa.link_impact import run as impact
        from ..workspace_qa.workspace_checks import _record_history, _scope

        reports, entries = [], []
        for source in sorted(event["sources"]):
            if not self.session.resolve(source).is_file():
                continue
            result = impact(self.session, {**{k: v for k, v in request.items() if k != "notify"}, "source": source,
                                           **{key: trigger[key] for key in ("group",) if key in trigger}})
            entries += result["documents"]
            reports.append({"source": source, "passed": result["passed"], "count": result["count"],
                            "passes": result["passes"], "fails": [item["document"] for item in result["fails"]],
                            "changed": result["changed"], **({"published": result["published"]}
                                                             if result.get("published") else {})})
        passed = all(report["passed"] for report in reports)
        summary = {"status": "completed", "passed": passed, "sources": reports,
                   "failing": sorted({path for report in reports for path in report["fails"]})}
        if entries:
            from ... import __version__

            history = {"time": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                       "vixl_version": __version__, "fail_on": request.get("fail_on") or "error",
                       "documents": entries}
            check = {key: request[key] for key in ("checks", "fail_on", "suites", "profile", "waivers")
                     if key in request}
            summary["history"] = _record_history(self.session, _scope(check, [e["path"] for e in entries]), history)
        self._emit(trigger, summary, request)
        return summary

    def _pipeline_run(self, trigger, request):
        from .runner import Run, run as pipeline_run

        scope = {key: trigger[key] for key in ("documents", "group") if key in trigger}
        call = {"pipeline": trigger["pipeline"], **scope, **({"run": request["run"]} if "run" in request else {})}
        stale = Run(self.session, call).stale()
        if not stale:
            return {"status": "up-to-date", "passed": True,
                    "reason": "the run record's digests match every document's inputs"}
        result = pipeline_run(self.session, {**call, "dry_run": False,
                                             **({"notify": request["notify"]} if "notify" in request else {})})
        counts = {key: value for key, value in result["counts"].items() if value}
        return {"status": result["status"], "passed": result["status"] == "completed", "stale": stale,
                "counts": counts, "record": result["record"],
                "failing": [d["path"] for d in result["documents"] if d["outcome"] in ("held", "failed")],
                **({"notify": result["notify"]} if result.get("notify") else {})}

    def _data_sync(self, trigger, event, request):
        from .data_sync import run as sync

        bound = self._bindings()
        names = sorted(event["sources"]) if event["files"] else sorted(
            name for name in bound if not trigger.get("binding") or name in trigger["binding"])
        reports = []
        for name in names:
            bind = bound.get(name)
            if not bind:
                continue
            options = {k: v for k, v in request.items() if k != "notify"}
            if "group" not in (bind.get("to") or {}):
                options.pop("exports", None)
            try:
                result = sync(self.session, {**options, "bind": bind, "name": name})
            except VixlError as exc:
                reports.append({"binding": name, "status": "error", "error": exc.as_dict()})
                continue
            held = [entry["document"] for entry in result.get("documents", []) if entry.get("status") == "held"]
            reports.append({"binding": name, "status": "held" if held else "completed",
                            "rows": {key: result["rows"][key] for key in ("added", "changed", "removed")},
                            **({"published": result["published"]} if result.get("published") else {}),
                            **({"held": held} if held else {})})
        passed = all(report["status"] == "completed" for report in reports)
        summary = {"status": "completed", "passed": passed, "bindings": reports,
                   "failing": sorted({path for report in reports for path in report.get("held", [])})}
        self._emit(trigger, summary, request)
        return summary

    def _emit(self, trigger, summary, request):
        """The shared completion event of a run that does not send its own (completion webhooks)."""
        from ...jobs import notify_complete

        event = {"event": "job-complete", "kind": "watch", "id": f"{self.name}-{trigger['id']}",
                 "status": summary["status"], "state": "validated" if summary["passed"] else "validation_failed",
                 "counts": {"failing": len(summary.get("failing", []))}, "report": summary.get("history"),
                 "workspace": str(self.session.workspace), "notify": request.get("notify"), "error": None}
        deliveries = notify_complete(event)
        if deliveries:
            summary["notify"] = deliveries

    # Loops --------------------------------------------------------------------------------------

    def wait(self, seconds):
        if self.waker is not None:
            self.waker.wait(seconds)
            self.waker.clear()
        else:
            self.clock.sleep(seconds)

    def next_wait(self):
        """Until the next poll, or sooner when a pending event falls due before it."""
        now = self.clock.time()
        due = [event["due"] - now for event in self.pending.values()]
        return max(0.0, min([self.poll, *due]))

    def run(self, ticks=None):
        """Poll ``ticks`` times (forever when None), then run whatever is still pending. Returns the runs."""
        from ...fileio import file_lock

        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            lock = file_lock(str(self.path.with_suffix("")), timeout=1)
            lock.__enter__()
        except Exception as exc:  # noqa: BLE001 - filelock raises its own Timeout type
            raise VixlError("busy", f"The watch {self.name!r} is already running", field="name") from exc
        done = []
        try:
            count = 0
            while True:
                done += self.tick()
                count += 1
                if ticks is not None and count >= ticks:
                    break
                self.wait(self.next_wait())
            if ticks is not None:
                done += self.drain(force=True)
        finally:
            lock.__exit__(None, None, None)
        return done

    def summary(self, done):
        return {"name": self.name, "state": self.session.relative(self.path), "runs": done,
                "passed": all(entry.get("passed", True) for entry in done),
                "pending": [{"trigger": event["trigger"]["id"], "documents": sorted(event["documents"])}
                            for event in self.pending.values()],
                "triggers": [{"id": t["id"], "on": t["on"], "run": t["run"]} for t in self.triggers]}


def _waker(root):
    """A ``threading.Event`` that a ``watchdog`` observer sets on any file event, or (None, None) without it."""
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError:
        return None, None
    import threading

    event = threading.Event()

    class Handler(FileSystemEventHandler):
        def on_any_event(self, _):
            event.set()

    observer = Observer()
    observer.daemon = True
    observer.schedule(Handler(), str(root), recursive=True)
    observer.start()
    return event, observer


# Entry points -----------------------------------------------------------------------------------

def run(session, request):
    """The ``watch`` workflow action: a bounded watch of ``ticks`` polls (default 1) that returns what ran."""
    from ...automation import bounded_object

    bounded_object(request, REQUEST, "Unknown watch field")
    require(not ("config" in request and "watch" in request), "Give config (a file) or watch (inline), not both",
            field="watch")
    config = request["watch"] if "watch" in request else load_config(session, request.get("config"))
    ticks = request.get("ticks", 1)
    require(type(ticks) is int and 1 <= ticks <= MAX_TICKS, f"ticks is 1-{MAX_TICKS} polls", field="ticks")
    watcher = Watcher(session, config, name=request.get("name"))
    done = watcher.run(ticks)
    return watcher.summary(done)


def cli(args, options, limits):
    from ...commands import Parser
    from ...interfaces import Session

    p = Parser(prog="vixl watch", description="Re-check, re-run pipelines or re-sync data when files change or a "
               "schedule comes round (triggers in .vixl/watch.json); runs until stopped unless --once or --ticks")
    p.add_argument("--config", help=f"The watch config (default {CONFIG})")
    p.add_argument("--workspace", default=".", help="Workspace folder (default: the current folder)")
    p.add_argument("--once", action="store_true", help="Poll once (what changed since the last watch, schedules due), "
                   "run it and exit")
    p.add_argument("--ticks", type=int, help="Poll this many times, then exit")
    p.add_argument("--name", help="State name (default the config's name, else watch)")
    a = p.parse_args(args)
    require(not (a.once and a.ticks), "Give --once or --ticks, not both", "usage_error", field="ticks")
    session = Session(None, limits, workspace=Path(a.workspace).resolve())
    if a.once or a.ticks:
        request = {"ticks": 1 if a.once else a.ticks, **({"config": a.config} if a.config else {}),
                   **({"name": a.name} if a.name else {})}
        result = run(session, request)
        report = Report(result)
        report.passed = result["passed"]
        return report
    import sys

    def show(entry):
        print(json.dumps(entry, default=str) if options.json else _line(entry), flush=True)

    watcher = Watcher(session, load_config(session, a.config), name=a.name, on_run=show)
    watcher.waker, observer = _waker(session.workspace)
    print(f"Watching {session.workspace} ({len(watcher.triggers)} trigger(s)); Ctrl-C stops", file=sys.stderr,
          flush=True)
    done = []
    try:
        done = watcher.run()
    except KeyboardInterrupt:
        done = watcher.runs
    finally:
        if observer is not None:
            observer.stop()
    return Report(watcher.summary(done))


def _line(entry):
    verdict = "passed" if entry.get("passed", True) else "FAILED"
    failing = entry.get("failing") or []
    line = f"{entry['time']} {entry['trigger']} ({entry['on']} -> {entry['run']}): {entry['status']}, {verdict}"
    return line + (f"; failing: {', '.join(failing[:5])}" if failing else "")


class Report(dict):
    """The JSON result of ``vixl watch``; ``passed`` sets the exit code."""

    passed = True
