"""The craft grader of the agent eval (#656): the ``craft`` check type, the craft tasks and their references, the
craft score in the baseline comparison, and the optional rubric judge (scripted here: no model call is ever made)."""

import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals import judge as judging  # noqa: E402
from evals.harness import ReferenceAgent, Tools, grade, load_tasks, markdown, prepare_workspace, run, summarize  # noqa: E402
from vixl import Project  # noqa: E402

CRAFT = [task for task in load_tasks() if any(c["type"] == "craft" for c in task["checks"])]
BASELINE = json.loads((Path(__file__).resolve().parent.parent / "evals" / "baseline.json").read_text(encoding="utf-8"))


def finished(task, workspace):
    """Replay the task's reference into ``workspace`` (a ``Path``) and return its grade."""
    prepare_workspace(task, workspace)
    tools = Tools(workspace)
    try:
        ReferenceAgent().run(task, tools)
    finally:
        tools.close()
    return grade(task, workspace)


def craft_of(checks):
    (item,) = [c for c in checks if "score" in c]
    return item


def test_there_are_four_sparse_brief_craft_tasks_with_stripped_variants():
    assert sorted(task["id"] for task in CRAFT) == ["craft-menu-prices", "craft-poster-event", "craft-report-cover",
                                                   "craft-social-quote"]
    for task in CRAFT:
        assert task["stripped"] and task["setup"]["font_pairings"]
        (craft,) = [c for c in task["checks"] if c["type"] == "craft"]
        assert set(craft["forbid"]) == {"flat_hierarchy", "single_weight", "no_focal", "accent_unused"}


@pytest.mark.parametrize("task", CRAFT, ids=[t["id"] for t in CRAFT])
def test_the_reference_scores_one_and_the_stripped_version_falls_below_the_threshold(task, tmp_path):
    checks = finished(task, tmp_path)
    assert all(c["passed"] for c in checks), [c for c in checks if not c["passed"]]
    assert craft_of(checks)["score"] == 1.0 and craft_of(checks)["detail"]["findings"] == []
    # Strip the craft out of the finished document (every text set at the body size): the grader now fails it.
    path = tmp_path / task["document"]
    project = Project.load(path)
    project.apply(task["stripped"])
    project.save(path)
    after = grade(task, tmp_path)
    item = craft_of(after)
    (bar,) = [c for c in task["checks"] if c["type"] == "craft"]
    assert item["score"] < bar["min_score"] and not item["passed"]
    assert item["detail"]["findings"] and all(f["region"] and f["code"] for f in item["detail"]["findings"])


def page(tmp_path, *ops, name="d.vixl"):
    project = Project(1000, 1000, "white")
    project.apply([{"type": "type-scale", "base": 20}, *ops])
    project.save(tmp_path / name)
    return {"document": name}


def flat():
    return [{"type": "text", "name": n, "text": n.title(), "size": 24, "x": 100, "y": y, "color": "#111111"}
            for n, y in (("title", 100), ("subtitle", 200), ("note", 300))]


def test_the_craft_check_counts_findings_and_reads_its_options(tmp_path):
    task = page(tmp_path, *flat())
    # Flat type: one flat_hierarchy finding (the largest text is 1.2 times the body).
    one = grade({**task, "checks": [{"type": "craft", "max_findings": 4, "min_score": 0.5}]}, tmp_path)[0]
    assert one["detail"]["findings"][0]["code"] == "flat_hierarchy" and one["score"] == 0.75 and one["passed"]
    # A floor above the score fails it; a forbidden code fails it whatever the score.
    assert not grade({**task, "checks": [{"type": "craft", "max_findings": 4, "min_score": 1.0}]}, tmp_path)[0]["passed"]
    barred = grade({**task, "checks": [{"type": "craft", "max_findings": 100, "min_score": 0, "forbid": ["flat_hierarchy"]}]},
                   tmp_path)[0]
    assert not barred["passed"] and barred["detail"]["forbidden"] == ["flat_hierarchy"] and barred["score"] > 0.9
    # Findings cap the score at 0, never below.
    assert grade({**task, "checks": [{"type": "craft", "max_findings": 1}]}, tmp_path)[0]["score"] == 0.0


def test_a_waiver_does_not_hide_a_finding_from_the_craft_check(tmp_path):
    task = page(tmp_path, *flat(), {"type": "waiver", "check": "composition", "reason": "on purpose"})
    assert Project.load(tmp_path / "d.vixl").check(checks=["composition"])["issues"][0]["action"] == "informational"
    result = grade({**task, "checks": [{"type": "craft"}]}, tmp_path)[0]
    assert result["detail"]["findings"] and not result["passed"]


def test_bad_craft_options_are_a_failed_check_not_a_crash(tmp_path):
    task = page(tmp_path, *flat())
    for options in ({"max_findings": 0}, {"min_score": 2}, {"forbid": ["no_such_code"]}, {"forbid": "flat_hierarchy"}):
        result = grade({**task, "checks": [{"type": "craft", **options}]}, tmp_path)[0]
        assert not result["passed"] and "ValueError" in result["detail"]


def test_the_craft_score_reaches_the_results_the_summary_and_the_report():
    craft = next(t for t in CRAFT if t["id"] == "craft-social-quote")
    plain = next(t for t in load_tasks() if t["id"] == "equal-spacing")
    results, summary = run([craft, plain], ReferenceAgent())
    assert [r["craft_score"] for r in results] == [1.0, None]
    assert summary["mean_craft_score"] == 1.0 and "mean_judge_score" not in summary
    text = markdown(results, summary, {"agent": "reference"})
    assert "| Craft |" in text and "craft 1.0" in text and "| 1.0 |" in text
    assert "mean_craft_score" not in summarize([results[1]])


# --- the stored baseline -------------------------------------------------------------------------


def test_the_baseline_stores_a_craft_floor_for_every_craft_task():
    assert set(BASELINE["craft_scores"]) == {t["id"] for t in CRAFT} and BASELINE["min_mean_craft_score"] == 1.0
    assert set(BASELINE["craft_scores"]) <= set(BASELINE["required_passes"])


def test_a_craft_drop_fails_the_baseline_comparison(tmp_path, monkeypatch):
    from evals import run as runner

    craft = next(t for t in CRAFT if t["id"] == "craft-poster-event")
    stripped = {**craft, "reference": [*craft["reference"], {"tool": "vixl_apply",
                                                              "arguments": {"operations": craft["stripped"]}}]}
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"required_passes": [], "craft_scores": {craft["id"]: 1.0},
                                    "min_mean_craft_score": 1.0}))
    monkeypatch.setattr(runner, "load_tasks", lambda pattern="*": [craft])
    assert runner.main(["--tasks", craft["id"], "--baseline", str(baseline), "--out", str(tmp_path / "ok")]) == 0
    monkeypatch.setattr(runner, "load_tasks", lambda pattern="*": [stripped])
    code = runner.main(["--tasks", craft["id"], "--baseline", str(baseline), "--out", str(tmp_path / "drop")])
    report = (tmp_path / "drop" / "report.md").read_text(encoding="utf-8")
    assert code == 1 and "craft-poster-event craft 0." in report and "< 1.0" in report and "mean craft 0." in report


def test_craft_regressions_need_the_task_to_have_run():
    from evals.run import craft_regressions

    baseline = {"craft_scores": {"a": 1.0, "b": 0.5}, "min_mean_craft_score": 0.9}
    results = [{"task": "a", "craft_score": 0.8}]
    assert craft_regressions(results, {"mean_craft_score": 0.8}, baseline) == [
        "a craft 0.8 < 1.0", "b craft None < 0.5", "mean craft 0.8 < 0.9"]
    assert craft_regressions([{"task": "a", "craft_score": 1.0}, {"task": "b", "craft_score": 0.5}],
                             {"mean_craft_score": 0.95}, baseline) == []


# --- the optional judge: scripted, never a real call ----------------------------------------------


class Scripted:
    """Plays back replies like ``client.messages.create`` and records each request."""

    def __init__(self, *replies):
        self.replies, self.requests = list(replies), []
        self.messages = self

    def create(self, **kwargs):
        self.requests.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=reply)])


GOOD = json.dumps({"scores": {name: 4 for name in judging.RUBRIC} | {"motif": 2}, "notes": "The motif is generic."})


def test_the_judge_scores_the_delivered_document_against_the_rubric(tmp_path):
    task = next(t for t in CRAFT if t["id"] == "craft-social-quote")
    workspace = tmp_path / "w"
    workspace.mkdir()
    finished(task, workspace)
    client = Scripted(f"Here you go: {GOOD}")
    result = judging.Judge("scripted-judge", client=client, save=tmp_path / "judge")(task, workspace)
    assert result["scores"]["motif"] == 2 and result["mean"] == 3.67 and result["model"] == "scripted-judge"
    assert result["notes"] == "The motif is generic."
    (request,) = client.requests
    image, prompt = request["messages"][0]["content"]
    assert image["type"] == "image" and image["source"]["media_type"] == "image/png"
    assert task["prompt"] in prompt["text"] and all(name in prompt["text"] for name in judging.RUBRIC)
    assert (tmp_path / "judge" / "craft-social-quote.png").read_bytes()[:4] == b"\x89PNG"


@pytest.mark.parametrize("reply", ["no json here", '{"scores": {"hierarchy": 9}}', '{"scores": {"hierarchy": 1}}',
                                   json.dumps({"scores": {name: 3.5 for name in judging.RUBRIC}}), RuntimeError("boom")])
def test_a_bad_reply_or_a_failed_call_is_recorded_not_raised(reply, tmp_path):
    task = next(t for t in CRAFT if t["id"] == "craft-social-quote")
    finished(task, tmp_path)
    result = judging.Judge("scripted-judge", client=Scripted(reply))(task, tmp_path)
    assert "error" in result and "scores" not in result


def test_a_task_that_left_no_document_cannot_be_judged(tmp_path):
    task = next(t for t in CRAFT if t["id"] == "craft-social-quote")
    result = judging.Judge("scripted-judge", client=Scripted(GOOD))(task, tmp_path)
    assert "no .vixl document" in result["error"]


def test_a_judged_run_keeps_the_rubric_beside_each_craft_task_only():
    craft = next(t for t in CRAFT if t["id"] == "craft-social-quote")
    plain = next(t for t in load_tasks() if t["id"] == "equal-spacing")
    client = Scripted(GOOD)
    results, summary = run([craft, plain], ReferenceAgent(), judge=judging.Judge("scripted-judge", client=client))
    assert results[0]["judge"]["mean"] == 3.67 and "judge" not in results[1]
    assert summary["mean_judge_score"] == 3.67 and len(client.requests) == 1  # the plain task was not judged
    assert "3.67/5" in markdown(results, summary, {"agent": "reference"})


def test_the_judge_is_off_unless_asked_for_and_its_endpoint_is_configurable(tmp_path, monkeypatch):
    from evals import run as runner

    craft = next(t for t in CRAFT if t["id"] == "craft-social-quote")
    made = []

    class Fake:
        def __init__(self, model, endpoint=None, client=None, save=None):
            made.append({"model": model, "endpoint": endpoint, "save": save})
            self.model = model

        def __call__(self, task, workspace):
            return {"scores": {name: 5 for name in judging.RUBRIC}, "mean": 5.0, "notes": "", "model": self.model}

    monkeypatch.setattr(runner, "load_tasks", lambda pattern="*": [craft])
    monkeypatch.setattr(judging, "Judge", Fake)
    monkeypatch.delenv(judging.ENDPOINT_ENV, raising=False)
    assert runner.main(["--out", str(tmp_path / "off")]) == 0 and not made
    assert "judge" not in json.loads((tmp_path / "off" / "results.json").read_text())["results"][0]
    monkeypatch.setenv(judging.ENDPOINT_ENV, "https://judge.example/v1")
    assert runner.main(["--judge", "--judge-model", "judge-model", "--out", str(tmp_path / "on")]) == 0
    assert made == [{"model": "judge-model", "endpoint": "https://judge.example/v1", "save": tmp_path / "on" / "judge"}]
    saved = json.loads((tmp_path / "on" / "judge.json").read_text())
    assert saved["craft-social-quote"]["mean"] == 5.0
    runner.main(["--judge", "--judge-endpoint", "https://other.example", "--out", str(tmp_path / "flag")])
    assert made[-1]["endpoint"] == "https://other.example" and made[-1]["model"] == "claude-opus-5-5"


def test_the_agent_eval_workflow_never_turns_the_judge_on():
    workflow = (Path(__file__).resolve().parent.parent / ".github" / "workflows" / "agent-eval.yml").read_text(encoding="utf-8")
    assert "--judge" not in workflow
