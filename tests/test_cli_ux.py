"""CLI first impressions (#693): a short schema listing, results that name their file, did-you-mean suggestions,
error messages that name the file or folder, readable help, and CLI spelling for every hint."""

import io
import json
import sys

import pytest

from vixl import Project
from vixl.cli import ambient_note, dispatch, main
from vixl.cli_summary import summarize
from vixl.errors import VixlError, for_surface, friendly


class Terminal(io.StringIO):
    def isatty(self):
        return True


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VIXL_JSON", raising=False)
    Project(200, 100).save(tmp_path / "hello.vixl")
    return tmp_path


def error_of(argv):
    with pytest.raises(VixlError) as caught:
        dispatch(argv)
    return caught.value


def test_schema_without_arguments_lists_operations_briefly(workspace):
    listing, _ = dispatch(["schema"])
    text = json.dumps(listing, indent=2)
    assert len(text) < 20_000 and listing["count"] > 200 and "--all" in listing["next"]
    assert any("text" in names for names in listing["groups"].values())
    full, _ = dispatch(["schema", "--all"])
    assert "$schema" in full or "properties" in full
    assert set(dispatch(["schema", "text"])[0]) == {"text"}
    assert "shape" in error_of(["schema", "shap"]).details["suggestions"]
    assert summarize(listing, "schema").splitlines()[0].endswith("operations")


def test_new_requires_an_output_name(workspace):
    error = error_of(["new", "100x100"])
    assert error.code == "usage_error" and "-o" in str(error)
    assert not (workspace / "untitled.vixl").exists()
    assert dispatch(["-p", "made.vixl", "new", "50x50"])[0]["path"].endswith("made.vixl")


def test_edit_results_and_summaries_name_the_file(workspace):
    result, _ = dispatch(["-p", "hello.vixl", "text", "add", "Hi", "--name", "t"])
    assert result["path"].endswith("hello.vixl")
    assert summarize(result, "text").startswith('hello.vixl: added text "t"')
    report, _ = dispatch(["-p", "hello.vixl", "check"])
    assert summarize(report, "check").startswith("hello.vixl: check ")


def test_ambient_document_is_named_once_on_stderr(workspace, capsys):
    dispatch(["open", "hello.vixl"])
    ambient_note(None, workspace / "hello.vixl", True)
    ambient_note(None, workspace / "hello.vixl", True)
    err = capsys.readouterr().err
    assert err.count("note: editing hello.vixl") == 1
    ambient_note("hello.vixl", workspace / "hello.vixl", True)  # -p given: nothing to say
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("with_document", [True, False])
def test_mistyped_command_suggests_the_real_one(workspace, with_document):
    if with_document:
        dispatch(["open", "hello.vixl"])
    error = error_of(["rendr"])
    assert error.code == "unknown_command" and "render" in error.details["suggestions"]
    assert "render" in str(error)


def test_mistyped_option_suggests_the_real_one(workspace):
    error = error_of(["-p", "hello.vixl", "text", "add", "Hi", "--colour", "red"])
    assert error.code == "usage_error" and "--color" in error.details["suggestions"] and "--color" in str(error)


def test_bad_json_names_the_file(workspace):
    (workspace / "ops.json").write_text('[{"type": "text"}\n{"x": 1}]')
    error = error_of(["-p", "hello.vixl", "apply", "ops.json"])
    assert error.code == "invalid_json" and str(error).startswith("ops.json: line 2 column 1")


def test_missing_folder_is_named(workspace):
    error = error_of(["-p", "hello.vixl", "export", "nowhere/out.png"])
    assert str(error) == "Folder does not exist: nowhere" and error.details["field"] == "path"
    friendly_error = friendly(FileNotFoundError(2, "No such file or directory", str(workspace / "gone" / "x.png")),
                              relative_to=workspace)
    assert "the folder gone does not exist" in str(friendly_error)


def test_help_strings_must_expand_on_every_python():
    """Python 3.14 refuses `help="50% or a marker"` when the option is added; every version refuses it here."""
    from vixl.commands import Parser

    with pytest.raises(ValueError, match="badly formed help string"):
        Parser(prog="x").add_argument("--times", help="milliseconds, 1.5s, 50% or a marker")
    Parser(prog="x").add_argument("--times", help="milliseconds, 1.5s, 50%% or a marker (default %(default)s)")


def test_help_shows_text_option_and_short_check_lines(workspace, capsys):
    for argv in (["text", "--help"], ["check", "--help"]):
        try:
            main(["-p", "hello.vixl", *argv])
        except SystemExit:  # argparse exits after printing help
            pass
    text_help, _, out = capsys.readouterr().out.partition("usage: vixl check")
    assert "--text TEXT" in text_help
    assert max(len(line) for line in out.splitlines()) < 120 and "CHECK is one of:" in out
    dispatch(["-p", "hello.vixl", "text", "add", "--text", "Hello", "--name", "x"])
    assert Project.load(workspace / "hello.vixl").layer("x")["text"] == "Hello"


@pytest.mark.parametrize("hint", [
    "see vixl_reference('operations') for the operations that edit it",
    "vixl_reference('operations', name=['text'])",
    "vixl_reference('capabilities', name='charts')",
    "vixl_reference('finishing')",
    "vixl_reference('fonts')",
    "run vixl_check(checks=['composition']) first",
    "vixl_render(region=[x, y, w, h], max_width=w)",
    "vixl_apply(workflow='repair-layout')",
    "vixl_document(action='inspect', layer=NAME)",
    "vixl_document(action='create', path='a.vixl', size='a4')",
    "vixl_document(action='open')",
    "vixl_document(action='notes')",
    "vixl_document(action='commit')",
    "vixl_document(action='list')",
    "vixl_document(action='close')",
])
def test_cli_hints_name_no_mcp_tools(hint):
    assert "vixl_" not in for_surface(hint, "cli")


def test_cli_hints_rewrite_document_actions_to_their_commands():  # #693
    rewritten = {
        "vixl_document(action='create', path='a.vixl')": "vixl new",
        "vixl_document(action='open')": "vixl open FILE",
        "vixl_document(action='notes')": "vixl notes",
        "vixl_document(action='checkout', ref='x')": "vixl checkout",
        "vixl_document(action='rollback')": "vixl transaction rollback",
    }
    for hint, command in rewritten.items():
        assert for_surface(hint, "cli") == command


def test_cli_error_output_names_no_mcp_tools(workspace, monkeypatch):
    err = Terminal()
    monkeypatch.setattr(sys, "stderr", err)
    main(["-p", "hello.vixl", "shape", "rectangle", "--name", "box", "--width", "10", "--height", "10"])
    assert main(["-p", "hello.vixl", "text", "add", "Hi", "--target", "box"]) == 1
    assert "ERROR" in err.getvalue() and "vixl_" not in err.getvalue()
