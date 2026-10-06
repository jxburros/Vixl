import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from vixl import Project

ROOT = Path(__file__).resolve().parents[1]


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "ci", "GIT_AUTHOR_EMAIL": "ci@example.com",
                        "GIT_COMMITTER_NAME": "ci", "GIT_COMMITTER_EMAIL": "ci@example.com"})


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_ci_script_checks_diffs_against_base_summarizes_and_fails_on_level(tmp_path):
    good = Project(200, 100, "white")
    good.apply({"type": "shape", "shape": "rectangle", "name": "box", "x": 10, "y": 10, "width": 40, "height": 40,
                "fill": "#123456"})
    (tmp_path / "designs").mkdir()
    good.save(tmp_path / "designs" / "good.vixl")
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "base")
    good.apply({"type": "move", "target": "box", "x": 120, "y": 10})
    good.save()
    bad = Project(200, 100, "white")
    bad.apply({"type": "text", "name": "faint", "text": "Hard to read", "x": 10, "y": 10, "size": 14, "color": "#f4f4f4"})
    bad.save(tmp_path / "designs" / "bad.vixl")
    summary = tmp_path / "summary.md"
    env = {**os.environ, "GITHUB_STEP_SUMMARY": str(summary)}
    command = [sys.executable, str(ROOT / "scripts" / "vixl_ci.py"), "--paths", "designs/*.vixl", "--base", "HEAD",
               "--proof", ".vixl-ci/proof.html"]
    done = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=300)
    text = summary.read_text(encoding="utf-8")
    assert done.returncode == 1, done.stderr
    assert "`designs/good.vixl`" in text and "`designs/bad.vixl`" in text and "| new |" in text
    assert "contrast" in text and "%" in text
    assert (tmp_path / ".vixl-ci" / "proof.html").is_file()
    assert list((tmp_path / ".vixl-ci" / "diff").glob("*.png"))
    passing = subprocess.run([*command[:3], "designs/good.vixl", "--fail-on", "error"], cwd=tmp_path, env=env,
                             capture_output=True, text=True, timeout=300)
    assert passing.returncode == 0, passing.stdout + passing.stderr


def test_action_declares_its_inputs_and_runs_the_script():
    text = (ROOT / "action.yml").read_text(encoding="utf-8")
    for name in ("paths", "checks", "suite", "fail-on", "vixl-version", "compare-base", "proof"):
        assert f"\n  {name}:\n" in text
    assert "using: composite" in text and "scripts/vixl_ci.py" in text and "GITHUB_STEP_SUMMARY" not in text.split("runs:")[0]
    assert 'vixl-engine[pdf]==$VIXL_VERSION' in text
