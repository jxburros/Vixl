"""Run model-written Python for the code-tools arm.

This is a guard rail, not a security boundary: the code runs as you, in a subprocess whose working folder is the
session's workspace, with a time limit, a scrubbed environment (no API keys) and, on Linux where unprivileged user
namespaces work, no network (``unshare -rn``). It can still read files elsewhere on the machine. Vixl itself is
blocked from import so the control arm cannot reach it through Python.
"""

from functools import lru_cache
import importlib.util
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys

BOOT = r"""
import runpy, sys
class _NoVixl:
    def find_spec(self, name, path=None, target=None):
        if name == "vixl" or name.startswith("vixl."):
            raise ModuleNotFoundError("No module named 'vixl' (not available in this session)")
        return None
sys.meta_path.insert(0, _NoVixl())
script = sys.argv[1]
sys.argv = ["script.py"]
runpy.run_path(script, run_name="__main__")
"""

# Import name -> the name people know it by, for the tool description.
LIBRARIES = {"PIL": "Pillow", "numpy": "numpy", "matplotlib": "matplotlib", "pandas": "pandas",
             "reportlab": "reportlab", "fpdf": "fpdf2", "pptx": "python-pptx", "docx": "python-docx",
             "openpyxl": "openpyxl", "pypdf": "pypdf", "svgwrite": "svgwrite", "drawsvg": "drawsvg",
             "cairosvg": "cairosvg", "cairo": "pycairo", "skia": "skia-python", "plotly": "plotly",
             "seaborn": "seaborn", "fontTools": "fonttools"}
OUTPUT_LIMIT = 8000


@lru_cache(maxsize=1)
def installed_libraries():
    return [label for name, label in LIBRARIES.items() if importlib.util.find_spec(name) is not None]


@lru_cache(maxsize=1)
def network_isolation():
    """The command prefix that removes network access, or () where it is not available."""
    if not sys.platform.startswith("linux") or shutil.which("unshare") is None:
        return ()
    try:
        done = subprocess.run(["unshare", "-rn", "true"], capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ()
    return ("unshare", "-rn") if done.returncode == 0 else ()


def environment(home):
    keep = ("PATH", "LANG", "LC_ALL", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "FONTCONFIG_PATH",
            "FONTCONFIG_FILE", "PLAYWRIGHT_BROWSERS_PATH")
    env = {key: os.environ[key] for key in keep if key in os.environ}
    env.update({"HOME": str(home), "USERPROFILE": str(home), "TMPDIR": str(home), "TEMP": str(home),
                "TMP": str(home), "MPLBACKEND": "Agg", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"})
    return env


def snapshot(folder):
    files = {}
    for path in Path(folder).rglob("*"):
        if path.is_file():
            stat = path.stat()
            files[path.relative_to(folder).as_posix()] = (stat.st_size, stat.st_mtime_ns)
    return files


def clip(text):
    return text if len(text) <= OUTPUT_LIMIT else text[:OUTPUT_LIMIT] + f"\n… ({len(text) - OUTPUT_LIMIT} more characters)"


def run_python(code, workspace, scratch, timeout=60):
    """Run ``code``; return (is_error, text). ``scratch`` holds the script and HOME, outside the workspace."""
    workspace, scratch = Path(workspace), Path(scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    home = scratch / "home"
    home.mkdir(exist_ok=True)
    number = len(list(scratch.glob("script-*.py"))) + 1
    script = scratch / f"script-{number:03d}.py"
    script.write_text(code, encoding="utf-8")
    before = snapshot(workspace)
    command = [*network_isolation(), sys.executable, "-E", "-c", BOOT, str(script)]
    options = {"start_new_session": True} if os.name == "posix" else {}
    process = subprocess.Popen(command, cwd=workspace, env=environment(home), stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", **options)
    try:
        out, err = process.communicate(timeout=timeout)
        timed_out = False
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        out, err = process.communicate()
        timed_out = True
    after = snapshot(workspace)
    changed = sorted(name for name, info in after.items() if before.get(name) != info)
    lines = []
    if timed_out:
        lines.append(f"Stopped after {timeout} s (time limit).")
    else:
        lines.append(f"Exit code {process.returncode}.")
    if out.strip():
        lines.append("stdout:\n" + clip(out.rstrip()))
    if err.strip():
        lines.append("stderr:\n" + clip(err.rstrip()))
    lines.append("Files written or changed: " + (", ".join(changed) if changed else "none"))
    return timed_out or process.returncode != 0, "\n".join(lines)
