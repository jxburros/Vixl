import json
import re
import subprocess
import sys

from PIL import Image
import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.interfaces import Session
from vixl.workflows import describe, dispatch


def cli(cwd, *args):
    return subprocess.run([sys.executable, "-m", "vixl", *args], cwd=cwd, capture_output=True, timeout=60)


def two_documents(tmp_path):
    a = Project(100, 60, "white")
    a.apply({"type": "shape", "shape": "rectangle", "name": "box", "x": 10, "y": 10, "width": 20, "height": 20, "fill": "red"})
    a.save(tmp_path / "a.vixl")
    b = Project(100, 60, "white")
    b.apply({"type": "shape", "shape": "rectangle", "name": "box", "x": 50, "y": 10, "width": 20, "height": 20, "fill": "red"})
    b.save(tmp_path / "b.vixl")


def test_diff_cli_reports_changed_pixels_and_writes_the_image(tmp_path):
    two_documents(tmp_path)
    run = cli(tmp_path, "--json", "diff", "a.vixl", "b.vixl", "--out", "d.png")
    assert run.returncode == 0, run.stderr.decode()
    result = json.loads(run.stdout)
    # Two 20 × 20 squares moved apart: 800 changed pixels in the region they span.
    assert result["changed_pixels"] == 800 and result["changed_region"] == [10, 10, 60, 20]
    assert not result["identical"] and Image.open(tmp_path / "d.png").size == (100, 60)
    # The diff image is never overwritten silently, and a limit turns the stats into a failure.
    assert cli(tmp_path, "--json", "diff", "a.vixl", "b.vixl", "--out", "d.png").returncode == 1
    failed = cli(tmp_path, "--json", "diff", "a.vixl", "b.vixl", "--max-fraction", "0.01")
    assert failed.returncode == 1 and json.loads(failed.stderr)["error"] == "diff_exceeded"


def test_diff_compares_a_document_with_an_image_of_another_size(tmp_path):
    two_documents(tmp_path)
    Project.load(tmp_path / "a.vixl").render().resize((200, 120)).save(tmp_path / "a@2x.png")
    from vixl.image_diff import diff_files

    result = diff_files(tmp_path / "a.vixl", tmp_path / "a@2x.png")
    assert result["resized"] and result["changed_fraction"] < 0.05


def test_proof_page_is_self_contained_with_findings_compare_and_decisions(tmp_path):
    two_documents(tmp_path)
    Project.load(tmp_path / "b.vixl").render().save(tmp_path / "b.png")
    session = Session(workspace=tmp_path)
    result = dispatch(session, "proof", {
        "items": ["a.vixl", {"path": "b.png", "label": "Moved", "before": "a.vixl", "note": "Box moved right"}],
        "output": "review/proof.html", "decisions": True, "title": "Round 1"})
    assert result["output"] == "review/proof.html" and result["items"] == 2
    assert result["checked"][0]["path"] == "a.vixl" and result["decision_file"] == "proof-decisions.json"
    html = (tmp_path / "review" / "proof.html").read_text(encoding="utf-8")
    policy = re.search(r'Content-Security-Policy" content="([^"]+)"', html).group(1)
    assert "default-src 'none'" in policy and "img-src data:" in policy and "script-src 'sha256-" in policy
    # Offline: nothing is fetched from anywhere.
    assert not re.search(r'(src|href)="(https?:)?//', html)
    assert 'href="#zoom-item-1"' in html and 'id="zoom-item-2"' in html  # click to enlarge, no script needed
    assert "Box moved right" in html and "% changed" in html and 'value="approved"' in html
    # The script the page runs is exactly the one its policy hashes.
    import base64
    import hashlib

    script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    assert f"'sha256-{digest}'" in policy
    with pytest.raises(VixlError, match="already exists"):
        dispatch(session, "proof", {"items": ["a.vixl"], "output": "review/proof.html"})
    # Without decisions there is no script at all.
    dispatch(session, "proof", {"items": ["a.vixl"], "output": "plain.html", "check": False})
    plain = (tmp_path / "plain.html").read_text(encoding="utf-8")
    assert "<script" not in plain and "script-src" not in plain and "check passed" not in plain


def test_proof_revision_compare_and_schema(tmp_path):
    two_documents(tmp_path)
    project = Project.load(tmp_path / "a.vixl")
    project.apply({"type": "move", "target": "box", "x": 60, "y": 30})
    project.save()
    session = Session(workspace=tmp_path)
    dispatch(session, "proof", {"items": [{"path": "a.vixl", "before": "previous"}], "output": "p.html"})
    assert "revision" in (tmp_path / "p.html").read_text(encoding="utf-8")
    with pytest.raises(VixlError, match="not a file"):
        dispatch(session, "proof", {"items": [{"path": "b.vixl", "before": "nope.png"}], "output": "q.html"})
    schema = describe()["actions"]["proof"]
    assert schema["required"] == ["items", "output"] and schema["properties"]["decisions"]["type"] == "boolean"
