import io
import json
import sys

import pytest

from vixl import Project
from vixl.cli import dispatch, main
from vixl.cli_summary import command_of, human_output, size, summarize, wants_json


class Terminal(io.StringIO):
    def isatty(self):
        return True


@pytest.fixture
def document(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VIXL_JSON", raising=False)
    project = Project(400, 300)
    project.apply([
        {"type": "text", "text": "Hello", "name": "title", "size": 30, "x": -50, "y": 5},
        {"type": "shape", "shape": "rectangle", "name": "box", "width": 20, "height": 20},
    ])
    project.save(tmp_path / "d.vixl")
    return tmp_path / "d.vixl"


def run_in_terminal(monkeypatch, argv):
    out, err = Terminal(), Terminal()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    code = main(argv)
    return code, out.getvalue(), err.getvalue()


def test_created_and_opened():
    result = {"path": "/x/a.vixl", "canvas": {"width": 800, "height": 600, "background": "#18283b"}, "layers": 0}
    assert summarize(result, "new") == "created a.vixl  800×600  bg #18283b"
    assert summarize({**result, "layers": 3}, "open") == "opened a.vixl  800×600  bg #18283b  3 layers"


def test_state_inspect_undo_redo():
    layers = [{"name": "title", "type": "text"}, {"name": "box", "type": "shape"}]
    state = {"canvas": {"width": 10, "height": 20, "background": "#fff"}, "layers": layers}
    assert summarize(state, "inspect") == "10×20  bg #fff  2 layers: title (text), box (shape)"
    assert summarize({"undo": 2, **state}, "undo").startswith("undid 2 steps  10×20")
    assert summarize({"redo": 1, **state}, "redo").startswith("redid 1 step  10×20")
    assert "undo 5: only 1" in summarize({"undo": 1, "notes": ["undo 5: only 1"], **state}, "undo")
    many = {**state, "layers": [{"name": f"l{i}", "type": "shape"} for i in range(10)]}
    assert summarize(many, "inspect").endswith("+2 more")


def test_edit_added_changed_removed_dry_run():
    added = {"success": True, "changes": {"layers": {"a": {"added": True, "name": "title", "type": "text", "bounds": [0, 0, 1, 1]}}}}
    assert summarize(added, "text") == 'added text "title"'
    changed = {"success": True, "changes": {"layers": {"a": {"x": 3, "bounds": [3, 0, 1, 1]}, "b": {"opacity": 0.5}}}}
    assert summarize(changed, "move") == "changed 2 layers: x, opacity"
    removed = {"success": True, "changes": {"layers": {"a": {"removed": True, "name": "box"}}}}
    assert summarize(removed, "x") == 'removed "box"'
    assert summarize({"success": True, "changes": {}}, "x") == "no changes"
    batch = {"success": True, "dry_run": True, "operations": 3, "warnings": ["careful"],
             "changes": {"layers": {"a": {"added": True, "name": "n", "type": "shape"}}, "canvas": {"width": 5}}}
    lines = summarize(batch, "apply").splitlines()
    assert lines[0] == "dry run: applied 3 operations"
    assert lines[1:] == ['added shape "n"', "changed canvas", "warning: careful"]


def test_check_pass_and_fail():
    passed = {"passed": True, "errors": 0, "warnings": 0, "issues": [], "checked": {"checks": ["bounds", "contrast"]}}
    assert summarize(passed, "check") == "check passed (bounds, contrast) — 0 errors, 0 warnings"
    issues = [{"severity": "warning", "layers": ["b"], "message": "later"},
              {"severity": "error", "layers": ["a"], "message": "first"}]
    failed = {"passed": False, "errors": 1, "warnings": 1, "issues": issues, "checked": {"checks": list("abcdefg")}}
    lines = summarize(failed, "check").splitlines()
    assert lines[0] == "check failed (7 checks) — 1 error, 1 warning"
    assert lines[1].split() == ["error", "a", "first"] and lines[2].split() == ["warning", "b", "later"]
    assert summarize({**failed, "issues": issues * 8}, "check").splitlines()[-1] == "  … 6 more"


def test_export_and_render():
    assert summarize({"output": "hello.png", "bytes": 16589}, "export") == "exported hello.png (16.2 KB)"
    assert summarize({"output": "r.png", "bytes": 12}, "render") == "rendered r.png (12 B)"
    assert size(5 * 1024 * 1024) == "5.0 MB"


def test_listings_history_validate_assert():
    layers = [{"name": "title", "type": "text", "width": 83, "height": 24, "x": 3.0, "y": 5.0},
              {"name": "box", "type": "shape", "visible": False}]
    lines = summarize(layers, "layers").splitlines()
    assert lines[0] == "2 layers" and "83×24 at 3,5" in lines[1] and lines[2].endswith("hidden")
    assert summarize([], "layers") == "no layers"
    nodes = [{"id": "rev_1", "parent": None, "operations": [], "label": "Create document"},
             {"id": "rev_2", "parent": "rev_1", "operations": [{}], "label": None}]
    assert summarize(nodes, "history").splitlines() == ["2 revisions", "  rev_1  Create document", "  rev_2  1 operation"]
    assert summarize({"valid": True, "checks": [{"rule": "a", "passed": True}]}, "validate") == "validation passed — 1 rule"
    assert "  b" in summarize({"valid": False, "checks": [{"rule": "b", "passed": False}]}, "validate")
    assert summarize({"passed": True, "rule": "x > 1"}, "assert") == "assertion passed: x > 1"


def test_generic_fallback():
    result = {"head": "rev_1", "count": 3, "ok": True, "names": ["a", "b"], "big": list(range(9)), "nested": {"k": 1},
              "text": "x" * 100, "none": None}
    lines = summarize(result, "branches").splitlines()
    assert lines[0] == "branches"
    assert "  head: rev_1" in lines and "  ok: yes" in lines and "  names: a, b" in lines
    assert "  big: 9 items" in lines and "  nested: k" in lines
    assert next(line for line in lines if line.startswith("  text")).endswith("…")
    assert not any("none" in line for line in lines)
    assert summarize({}, "each") == "each: done"
    assert summarize(["a", "b"], "x") == "2 items: a, b"
    assert summarize([{"name": "n1"}, {"id": "i2"}], "x").splitlines() == ["2 items", "  n1", "  i2"]


def test_mode_detection():
    assert command_of(["-p", "a.vixl", "--detail", "brief", "check", "--strict"]) == "check"
    assert command_of(["--json"]) is None
    assert wants_json(["--json", "x"], {}) and wants_json(["x"], {"VIXL_JSON": "1"})
    assert not wants_json(["x"], {"VIXL_JSON": "0"}) and not wants_json(["x"], {})
    assert human_output(["check"], Terminal()) and not human_output(["check"], io.StringIO())
    assert not human_output(["check", "--json"], Terminal())


def test_terminal_prints_summary(document, monkeypatch):
    code, out, _ = run_in_terminal(monkeypatch, ["-p", str(document), "layers"])
    assert code == 0 and out.startswith("2 layers\n") and "title" in out
    code, out, _ = run_in_terminal(monkeypatch, ["-p", str(document), "check"])
    assert out.startswith("d.vixl: check ") and "—" in out
    code, out, _ = run_in_terminal(monkeypatch, ["-p", str(document), "export", "o.png"])
    assert out.startswith("d.vixl: exported o.png (")
    code, out, _ = run_in_terminal(monkeypatch, ["-p", str(document), "text", "add", "Hi", "--name", "t2"])
    assert code == 0 and out.startswith('d.vixl: added text "t2"')


def test_json_flag_and_env_override_terminal(document, monkeypatch):
    code, out, _ = run_in_terminal(monkeypatch, ["--json", "-p", str(document), "layers"])
    assert [layer["name"] for layer in json.loads(out)] == ["title", "box"]
    monkeypatch.setenv("VIXL_JSON", "1")
    code, out, _ = run_in_terminal(monkeypatch, ["-p", str(document), "check"])
    assert "passed" in json.loads(out)


@pytest.mark.parametrize("argv", [["layers"], ["inspect"], ["check"], ["history"]])
def test_piped_output_is_unchanged(document, capsys, argv):
    full = ["-p", str(document), *argv]
    result = dispatch(full)[0]
    capsys.readouterr()
    main(full)
    assert capsys.readouterr().out == json.dumps(result, indent=2, ensure_ascii=True, allow_nan=False) + "\n"


def test_piped_export_is_json(document, capsys):
    assert main(["-p", str(document), "export", "p.png"]) == 0
    assert json.loads(capsys.readouterr().out)["output"] == "p.png"


def test_errors(document, monkeypatch, capsys):
    assert main(["-p", str(document), "inspect", "titel"]) == 1
    assert capsys.readouterr().err.startswith("ERROR: ")
    code, _, err = run_in_terminal(monkeypatch, ["-p", str(document), "inspect", "titel"])
    assert code == 1 and err.startswith("ERROR: ")
    code, _, err = run_in_terminal(monkeypatch, ["--json", "-p", str(document), "inspect", "titel"])
    assert json.loads(err)["error"] == "layer_not_found"
