"""Watch mode (#569): triggers, debounce, schedules and reporting, driven by a fake clock and the bounded watch."""

import json

import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.interfaces import Session
from vixl.plugins.pipelines import watch
from vixl.workflows import dispatch

from test_link_impact import host, logo


class FakeClock:
    def __init__(self, start=1_800_000_000.0):
        self.now = start

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(watch, "CLOCK", fake)
    return fake


@pytest.fixture
def linked(tmp_path):
    logo(tmp_path / "logo.vixl")
    host(tmp_path / "page.vixl", "logo.vixl", 280)  # a wider logo runs off its right edge
    host(tmp_path / "wide.vixl", "logo.vixl", 20)
    return Session(None, workspace=tmp_path)


def configure(session, *triggers, **extra):
    session.resolve(".vixl").mkdir(exist_ok=True)
    session.resolve(".vixl/watch.json").write_text(json.dumps({"version": 1, "triggers": list(triggers), **extra}))


def bounded(session, **request):
    return dispatch(session, "watch", {"ticks": 1, **request})


def test_saving_a_linked_source_re_checks_its_dependents_and_reports_the_failing_one(linked, clock):
    configure(linked, {"on": "source-change", "run": "link-impact"})
    first = bounded(linked)
    assert first["runs"] == [] and linked.resolve(".vixl-runs/watch/watch.json").is_file()  # the baseline
    logo(linked.resolve("logo.vixl"), width=160)
    result = bounded(linked)
    [run] = result["runs"]
    assert run["trigger"] == "1-source-change" and run["files"] == ["logo.vixl"] and run["passed"] is False
    assert run["failing"] == ["page.vixl"] and result["passed"] is False
    assert run["sources"][0]["passes"] == ["wide.vixl"]
    history = json.loads(linked.resolve(run["history"]).read_text())
    assert history["documents"]["page.vixl"]["failing"] and not history["documents"]["wide.vixl"]["failing"]
    assert bounded(linked)["runs"] == []  # nothing changed since


def test_debounce_coalesces_repeated_saves_into_one_run(linked, clock):
    config = {"version": 1, "triggers": [{"on": "save", "run": "check", "documents": ["*.vixl"]}]}
    watcher = watch.Watcher(linked, config, clock=clock)
    assert watcher.tick() == []  # the baseline
    page = Project.load(linked.resolve("page.vixl"))
    for text in ("One", "Two", "Three"):
        page.apply({"type": "text-set", "target": "headline", "text": text})
        page.save()
        clock.sleep(0.3)
        assert watcher.tick() == []  # each save pushes the run back by the debounce
    wide = Project.load(linked.resolve("wide.vixl"))
    wide.apply({"type": "text-set", "target": "headline", "text": "Also"})
    wide.save()
    assert watcher.tick() == []
    clock.sleep(watch.DEBOUNCE)
    [run] = watcher.tick()
    assert run["events"] == 4 and run["documents"] == ["page.vixl", "wide.vixl"] and run["run"] == "check"
    assert run["history"] and run["totals"]["passed"] + run["totals"]["needs_review"] == 2
    clock.sleep(5)
    assert watcher.tick() == []


def test_a_touched_file_is_not_a_change(linked, clock):
    import os

    configure(linked, {"on": "save"})
    bounded(linked)
    os.utime(linked.resolve("page.vixl"), (clock.now + 100, clock.now + 100))
    assert bounded(linked)["runs"] == []


def test_a_schedule_fires_once_per_period(linked, clock):
    config = {"version": 1, "triggers": [{"on": "schedule", "every": "24h", "run": "check-all"}]}
    watcher = watch.Watcher(linked, config, clock=clock)
    assert watcher.tick() == []  # the first period starts now
    clock.sleep(23 * 3600)
    assert watcher.tick() == []
    clock.sleep(3600)
    [run] = watcher.tick() + watcher.drain(force=True)
    assert run["on"] == "schedule" and run["run"] == "check-all"
    clock.sleep(3600)
    assert watcher.tick() + watcher.drain(force=True) == []
    # Stopped for three days: it fires once when it comes back, not three times.
    clock.sleep(3 * 86400)
    again = watch.Watcher(linked, config, clock=clock)
    assert len(again.tick() + again.drain(force=True)) == 1


def test_a_daily_at_schedule_fires_after_its_time_of_day(linked, clock):
    from datetime import datetime, timezone

    clock.now = datetime(2026, 10, 1, 5, 0, tzinfo=timezone.utc).timestamp()
    watcher = watch.Watcher(linked, {"triggers": [{"on": "schedule", "at": "06:00", "run": "check"}]}, clock=clock)
    assert watcher.tick() == []
    clock.sleep(1800)
    assert watcher.tick() + watcher.drain(force=True) == []
    clock.sleep(3600)  # 06:30
    assert len(watcher.tick() + watcher.drain(force=True)) == 1
    clock.sleep(3600 * 12)
    assert watcher.tick() + watcher.drain(force=True) == []


def test_no_export_is_overwritten_and_an_unchanged_pipeline_is_not_run_again(linked, clock):
    pipeline = {"version": 1, "targets": {"documents": ["page.vixl", "wide.vixl"]},
                "steps": [{"export": {"targets": [{"path": "out/{doc}.png"}]}}]}
    dispatch(linked, "resource-save", {"kind": "pipelines", "name": "previews", "value": pipeline})
    linked.resolve("out").mkdir()
    linked.resolve("out/wide.png").write_bytes(b"someone else's file")
    configure(linked, {"on": "save", "run": "pipeline", "pipeline": "previews"})
    bounded(linked)
    page = Project.load(linked.resolve("page.vixl"))
    page.apply({"type": "text-set", "target": "headline", "text": "New"})
    page.save()
    [run] = bounded(linked)["runs"]
    assert run["status"] == "failed" and run["failing"] == ["wide.vixl"]
    assert linked.resolve("out/wide.png").read_bytes() == b"someone else's file"
    assert linked.resolve("out/page.png").is_file()
    stamp = linked.resolve("out/page.png").stat().st_mtime_ns
    linked.resolve("out/wide.png").unlink()
    wide = Project.load(linked.resolve("wide.vixl"))
    wide.apply({"type": "text-set", "target": "headline", "text": "Wider"})
    wide.save()
    [again] = bounded(linked)["runs"]
    # The run record's digests show that only wide.vixl changed; page.png is reused, not written again.
    assert again["stale"] == ["wide.vixl"] and again["status"] == "completed"
    assert linked.resolve("out/page.png").stat().st_mtime_ns == stamp
    # A save outside the pipeline's documents changes none of its inputs: nothing runs.
    Project(100, 100, "white").save(linked.resolve("other.vixl"))
    [current] = bounded(linked)["runs"]
    assert current["status"] == "up-to-date" and current["documents"] == ["other.vixl"]


def test_a_brand_change_re_checks_and_fires_the_completion_event(linked, clock, monkeypatch):
    events = []
    monkeypatch.setattr("vixl.jobs.notify_complete", lambda event: events.append(event) or [])
    configure(linked, {"on": "brand-change"})
    bounded(linked)
    linked.resolve("brand.json").write_text(json.dumps({"name": "Acme"}))
    [run] = bounded(linked)["runs"]
    assert run["run"] == "check-all" and run["files"] == ["brand.json"] and run["history"]
    assert [event["kind"] for event in events] == ["check-all"]


def test_a_data_change_re_syncs_the_binding(tmp_path, clock):
    from test_data_sync import ROWS, member, write_csv

    for index, (sku, _, _) in enumerate(ROWS, 1):
        member(tmp_path / f"p{index}.vixl", sku)
    write_csv(tmp_path / "prices.csv", ROWS)
    session = Session(None, workspace=tmp_path)
    dispatch(session, "group-define", {"name": "shelf", "documents": ["p1.vixl", "p2.vixl", "p3.vixl"]})
    dispatch(session, "data-sync", {"bind": {"data": "prices.csv", "key": "sku", "to": {"group": "shelf"}}})
    configure(session, {"on": "data-change", "request": {"exports": [{"path": "out/{doc}.png"}]}})
    bounded(session)
    write_csv(tmp_path / "prices.csv", [ROWS[0], ("A2", "$25", "Desk"), ROWS[2]])
    [run] = bounded(session)["runs"]
    assert run["run"] == "data-sync" and run["files"] == ["prices.csv"] and run["passed"]
    assert run["documents"] == ["p1.vixl", "p2.vixl", "p3.vixl"]
    assert run["bindings"][0]["published"] == ["p2.vixl"] and (tmp_path / "out/p2.png").is_file()
    assert Project.load(tmp_path / "p2.vixl").state["variables"]["price"] == "$25"


def test_a_busy_document_waits_for_the_next_poll(linked, clock):
    from vixl.fileio import file_lock

    watcher = watch.Watcher(linked, {"triggers": [{"on": "save"}]}, clock=clock)
    watcher.tick()
    page = Project.load(linked.resolve("page.vixl"))
    page.apply({"type": "text-set", "target": "headline", "text": "Busy"})
    page.save()
    watcher.tick()
    clock.sleep(1)
    locks = linked.resolve(".vixl-runs/watch/locks")
    with file_lock(str(locks / "page.vixl"), timeout=0):
        import threading

        result = []
        thread = threading.Thread(target=lambda: result.append(watcher.tick()))
        thread.start()
        thread.join()
    assert result == [[]] and watcher.pending
    clock.sleep(1)
    assert len(watcher.tick()) == 1 and not watcher.pending


def test_a_bad_config_names_the_field(linked):
    with pytest.raises(VixlError, match="on is one of"):
        watch.validate({"triggers": [{"on": "rename"}]})
    with pytest.raises(VixlError, match="goes with on"):
        watch.validate({"triggers": [{"on": "brand-change", "run": "link-impact"}]})
    with pytest.raises(VixlError, match="at least a minute"):
        watch.validate({"triggers": [{"on": "schedule", "every": "5s"}]})
    with pytest.raises(VixlError, match="Unknown check option"):
        watch.validate({"triggers": [{"on": "save", "request": {"overwrite": True}}]})
    with pytest.raises(VixlError, match="No watch config"):
        bounded(linked)


def test_the_cli_runs_a_bounded_watch_and_a_pipeline(linked, clock, capsys):
    from vixl.cli import main

    configure(linked, {"on": "save"})
    assert main(["--json", "watch", "--once", "--workspace", str(linked.workspace)]) == 0
    assert json.loads(capsys.readouterr().out)["runs"] == []
    pipeline = {"version": 1, "targets": {"documents": ["wide.vixl"]},
                "steps": [{"export": {"targets": [{"path": "out/{doc}.png"}]}}]}
    dispatch(linked, "resource-save", {"kind": "pipelines", "name": "one", "value": pipeline})
    assert main(["--json", "pipeline", "run", "one", "--workspace", str(linked.workspace)]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["dry_run"] and plan["outputs"] == ["out/wide.png"]
    assert main(["--json", "pipeline", "run", "one", "--execute", "--run", "cli",
                 "--workspace", str(linked.workspace)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "completed"
    assert linked.resolve(".vixl-runs/cli/run.json").is_file()
