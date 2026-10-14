"""The craft re-run (craft plan 1c, 1a): the Vixl lane re-run on the tool-comparison briefs, its sources kept beside
the outputs, the other lanes copied from the fixed set, packaging through the kit's rejudge.py and the judge prompt.
Offline: a scripted agent drives the real in-process MCP server; the kit is a small stand-in unless VixlExamples is
present."""

import json
import os
from pathlib import Path
import sys
import types
import zipfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals import craft_rerun  # noqa: E402

README = """# Tool comparison

### Lane rules

- **V:** Use Vixl for all of the visual work. Read `skills/vixl/SKILL.md` first. Don't draw pixels
  yourself; small scripts are fine only for reading inputs.
- **W:** Build it with web code.

**Round 1 (agent lanes).** Start a fresh session in the repository and send:

```text
This is one run of a tool comparison. Lane: <CODE> — <LANE RULE>

Do the brief in evals/tool-comparison/briefs/<BRIEF FILE>. Save everything in
evals/tool-comparison/runs/<TEST>/<AGENT>-<CODE>/ and finish with REPORT.md there.
```

**Round 2: the revision.** Run it in a fresh session:

```text
This is one run of a tool comparison. Lane: <CODE> — <LANE RULE>

evals/tool-comparison/runs/<TEST>/<AGENT>-<CODE>/ holds finished work. Make these changes: <ROUND 2 TEXT>
Write the updated deliverables to round2/ inside that folder.
```
"""
JUDGING = "# Judging prompt\n\nPaste below the line.\n\n---\n\nYou are judging a blind design comparison.\n"


def kit(tmp_path):
    """A stand-in VixlExamples with one brief, a fixed rejudge set holding a web lane, and no real rejudge.py."""
    examples = tmp_path / "VixlExamples"
    root = examples / "evals" / "tool-comparison"
    (root / "briefs").mkdir(parents=True)
    (root / "README.md").write_text(README, encoding="utf-8")
    (root / "JUDGING.md").write_text(JUDGING, encoding="utf-8")
    (root / "rejudge.py").write_text("# stand-in; tests replace load_rejudge\n", encoding="utf-8")
    (root / "briefs" / "T02-social-post.md").write_text("# T02\n\nMake `post.png`, 200 × 100 px.\n", encoding="utf-8")
    (root / "fixtures").mkdir()
    (root / "fixtures" / "badges.csv").write_text("name\nAda\n", encoding="utf-8")
    (root / "fixtures" / "lighthouse.wav").write_bytes(b"RIFF")
    (root / "fixtures" / "make_fixtures.py").write_text("raise SystemExit('not run')\n", encoding="utf-8")
    fixed = root / "rejudge-2026-10-12"
    (fixed / "sealed").mkdir(parents=True)
    (fixed / "sealed" / "key.csv").write_text("test,code,lane\nT02,ABCD,claude-V\nT02,WXYZ,claude-W\n", encoding="utf-8")
    (fixed / "packages").mkdir()
    with zipfile.ZipFile(fixed / "packages" / "T02.zip", "w") as archive:
        archive.writestr("T02/brief.md", "# T02")
        archive.writestr("T02/WXYZ/r1/files/post.png", b"web r1")
        archive.writestr("T02/WXYZ/r1/views/post.png.view.png", b"view")
        archive.writestr("T02/WXYZ/r2/files/post.png", b"web r2")
        archive.writestr("T02/ABCD/r1/files/post.png", b"old vixl")
    return examples


def fake_rejudge(calls):
    def deliverable_names(test, round2=True):
        return ["post.png"] + (["story.png"] if round2 else [])

    def find_deliverables(run, names):
        return [p for p in run.rglob("*") if p.is_file() and p.name in names and "round2" not in
                p.relative_to(run).parts[:-1] and "src" not in p.relative_to(run).parts[:-1]]

    def build(runs, out, tests, seed):
        calls.append((runs, out, list(tests), seed))
        for test in tests:
            (out / "package" / test).mkdir(parents=True, exist_ok=True)
            (out / "package" / test / "brief.md").write_text("brief", encoding="utf-8")
        (out / "sealed").mkdir(parents=True, exist_ok=True)

    return types.SimpleNamespace(round2_request=lambda test: "Make the title red.", deliverable_names=deliverable_names,
                                 find_deliverables=find_deliverables, build=build)


class ScriptedAgent:
    """Round 1: two documents (one outside the run folder), a batch, an export and REPORT.md. Round 2: a revision
    that edits the round-1 document and writes no report, so the final reply becomes it."""

    name = "scripted"

    def __init__(self):
        self.prompts = []

    def run(self, task, tools):
        self.prompts.append(task["prompt"])
        names = {tool["name"] for tool in tools.definitions()}
        assert {"read_text_file", "write_text_file", "vixl_apply"} <= names
        run = "evals/tool-comparison/runs/T02/claude-V"
        trace = []

        def call(name, arguments, error=False):
            failed, blocks = tools.call(name, arguments)
            trace.append({"tool": name, "input": arguments, "error": failed})
            assert failed == error, blocks
            return failed, blocks

        if "round2/" not in task["prompt"]:
            assert not call("read_text_file", {"path": "evals/tool-comparison/briefs/T02-social-post.md"})[0]
            assert "Ada" in call("read_text_file", {"path": "evals/tool-comparison/fixtures/badges.csv"})[1][0]["text"]
            call("read_text_file", {"path": "../outside.md"}, error=True)
            call("write_text_file", {"path": f"{run}/post.svg", "text": "<svg/>"}, error=True)
            call("vixl_document", {"action": "create", "path": "scratch.vixl", "width": 50, "height": 50})
            call("vixl_document", {"action": "create", "path": f"{run}/post.vixl", "width": 200, "height": 100, "background": "white"})
            call("vixl_apply", {"operations": [{"type": "text", "name": "title", "text": "Open studio",
                                                           "size": 24, "color": "#111111", "x": 10, "y": 10}]})
            call("vixl_export", {"path": f"{run}/post.png"})
            call("write_text_file", {"path": f"{run}/REPORT.md", "text": "# Report\n\npost.png from post.vixl\n"})
            return {"round_trips": 3, "trace": trace, "usage": {}, "final": "Done."}
        call("vixl_document", {"action": "open", "path": f"{run}/post.vixl"})
        call("vixl_apply", {"operations": [{"type": "text-set", "target": "title", "color": "#cc0000"}]})
        call("vixl_export", {"path": f"{run}/round2/post.png"})
        return {"round_trips": 2, "trace": trace, "usage": {}, "final": "Made the title red."}


def test_re_run_keeps_sources_copies_fixed_lanes_packages_and_prints_the_prompt(tmp_path, monkeypatch, capsys):
    examples = kit(tmp_path)
    calls = []
    monkeypatch.setattr(craft_rerun, "load_rejudge", lambda kit_path: fake_rejudge(calls))
    runs, out = tmp_path / "runs-new", tmp_path / "rejudge-new"
    agent = ScriptedAgent()
    assert craft_rerun.main(["--examples", str(examples), "--tests", "t02", "--runs", str(runs), "--out", str(out)],
                            agent=agent) == 0

    # The kit's prompts, with the lane rule that keeps the sources and the round-2 request from TESTS.md.
    first, second = agent.prompts
    assert "Lane: V — Use Vixl for all of the visual work" in first and craft_rerun.RULE_ADDITION in first
    assert "briefs/T02-social-post.md" in first and "runs/T02/claude-V/" in first and "<" not in first.split("(This")[0]
    assert "Make these changes: Make the title red." in second and craft_rerun.RULE_ADDITION in second

    lane = runs / "T02" / "claude-V"
    assert (lane / "post.png").is_file() and (lane / "post.vixl").is_file()
    assert (lane / "REPORT.md").read_text(encoding="utf-8").startswith("# Report")
    assert not (lane / "post.svg").exists()
    # 1a: documents left outside the run folder, the batches and the trace are kept beside the outputs.
    assert (lane / "src" / "scratch.vixl").is_file()
    batches = json.loads((lane / "src" / "batches.json").read_text(encoding="utf-8"))
    assert batches[0]["operations"][0]["text"] == "Open studio"
    assert json.loads((lane / "src" / "trace.json").read_text(encoding="utf-8"))
    assert (lane / "round2" / "post.png").is_file()
    assert "Made the title red." in (lane / "round2" / "REPORT.md").read_text(encoding="utf-8")
    assert json.loads((lane / "round2" / "src" / "batches.json").read_text(encoding="utf-8"))[0]["operations"]
    record = json.loads((lane / "src" / "run.json").read_text(encoding="utf-8"))
    assert record["vixl_version"] and [r["round"] for r in record["rounds"]] == [1, 2]
    assert record["rounds"][0]["missing"] == [] and record["rounds"][1]["missing"] == ["story.png"]
    assert record["rounds"][0]["sources"] == ["src/scratch.vixl"]
    # The scripted revision edited the round-1 document in place, which the record names.
    assert record["rounds"][1]["changed_outside_round2"] == ["post.vixl"]

    # The other lane comes from the fixed package, both rounds; the old Vixl run does not.
    assert (runs / "T02" / "claude-W" / "post.png").read_bytes() == b"web r1"
    assert (runs / "T02" / "claude-W" / "round2" / "post.png").read_bytes() == b"web r2"
    assert not (runs / "T02" / "claude-W" / "views").exists()

    assert calls == [(runs, out, ["T02"], None)]
    with zipfile.ZipFile(out / "packages" / "T02.zip") as archive:
        assert "T02/brief.md" in archive.namelist()
    printed = capsys.readouterr().out
    assert str(out / "packages" / "T02.zip") in printed and "You are judging a blind design comparison." in printed
    assert "Paste below the line" not in printed

    # An existing run is not replaced without --overwrite.
    with pytest.raises(SystemExit):
        craft_rerun.main(["--examples", str(examples), "--tests", "T02", "--runs", str(runs), "--out", str(out)],
                         agent=ScriptedAgent())


def test_dry_run_prints_the_plan_and_writes_nothing(tmp_path, monkeypatch, capsys):
    examples = kit(tmp_path)
    monkeypatch.setattr(craft_rerun, "load_rejudge", lambda kit_path: fake_rejudge([]))
    monkeypatch.setenv("VIXL_EXAMPLES", str(examples))
    before = sorted(p for p in examples.rglob("*"))
    assert craft_rerun.main(["--dry-run", "--tests", "T02", "--model", "some-model", "--effort", "low"]) == 0
    printed = capsys.readouterr().out
    assert "some-model, effort low" in printed and "T02 T02-social-post.md" in printed and "fixed: claude-W" in printed
    assert "Round 1 prompt (T02)" in printed and "rejudge.py" in printed
    assert sorted(p for p in examples.rglob("*")) == before
    with pytest.raises(SystemExit):
        craft_rerun.main(["--dry-run", "--tests", "T99"])


def test_examples_are_found_from_the_flag_the_environment_or_a_sibling(tmp_path, monkeypatch):
    examples = kit(tmp_path)
    assert craft_rerun.find_examples(str(examples)) == examples.resolve()
    monkeypatch.setenv("VIXL_EXAMPLES", str(examples))
    assert craft_rerun.find_examples() == examples.resolve()
    monkeypatch.delenv("VIXL_EXAMPLES")
    monkeypatch.setattr(craft_rerun, "ROOT", tmp_path / "Vixl")
    assert craft_rerun.find_examples() == examples.resolve()
    with pytest.raises(SystemExit, match="--examples"):
        craft_rerun.find_examples(str(tmp_path / "nowhere"))


def real_kit():
    candidates = [os.environ.get("VIXL_EXAMPLES"), craft_rerun.ROOT.parent / "VixlExamples"]
    for candidate in filter(None, candidates):
        if (Path(candidate) / craft_rerun.KIT / "rejudge.py").is_file():
            return Path(candidate)
    return None


@pytest.mark.skipif(real_kit() is None, reason="no VixlExamples checkout")
def test_the_real_kit_gives_prompts_fixed_lanes_and_a_workspace(tmp_path):
    examples = real_kit()
    kit_path = examples / craft_rerun.KIT
    pytest.importorskip("PIL")
    rejudge = craft_rerun.load_rejudge(kit_path)
    for test in craft_rerun.TESTS:
        first, second = craft_rerun.prompts(kit_path, rejudge, test)
        assert "<" not in first.split("(This run")[0].replace("<!--", "") and "Make these changes: " in second
    fixed = craft_rerun.fixed_source(kit_path)
    assert "claude-W" in craft_rerun.fixed_lanes(fixed, "T08")
    run = craft_rerun.prepare_workspace(tmp_path / "ws", examples, "T14")
    assert (tmp_path / "ws" / craft_rerun.KIT / "fixtures" / "lighthouse.lrc").is_file()
    assert (tmp_path / "ws" / craft_rerun.KIT / "fixtures" / "lighthouse.wav").stat().st_size > 1000
    assert (tmp_path / "ws" / "skills" / "vixl" / "SKILL.md").is_file() and run.is_dir()
