"""Windows integration: signed manifest, real archive download/probe/immediate switch plus broken-candidate recovery.
Only GitHub transport is replaced; installed frozen executables are really executed.
"""

from contextlib import ExitStack
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from unittest.mock import patch

from vixl import __version__
from vixl import updater
from vixl import updater_sign

root = Path(sys.argv[1]).resolve()
bundle = Path(sys.argv[2]).resolve()
launcher = root / "bin" / "vixl.exe"
env = os.environ.copy()
env.pop("VIXL_NO_UPDATE", None)
# Simulate an older directory layout using the working runtime as our baseline fixture.
old = "0.0.1"
shutil.move(root / "versions" / __version__, root / "versions" / old)
state = updater.read_state(root)
state.update(current=old, previous=None, pending=None, last_check=time.time())
updater.atomic_json(root / "install.json", state)
# The real manifest built beside the bundle, signed with a key made for this run. Only the GitHub transport is
# replaced, so latest() verifies the signature and update() the checksum exactly as an installed launcher does.
manifest = (bundle.parent / updater.MANIFEST).read_bytes()
seed = os.urandom(32)
signature = (updater_sign.sign(seed, manifest).hex() + "\n").encode("ascii")
tag = f"v{__version__}"
base = f"https://github.com/{updater.REPOSITORY}/releases/download/{tag}/"
metadata = {
    "tag_name": tag,
    "draft": False,
    "prerelease": False,
    "assets": [{"name": name} for name in (updater.MANIFEST, updater.SIGNATURE, bundle.name)],
}
served = {base + updater.MANIFEST: manifest, base + updater.SIGNATURE: signature}


def download(url, destination, limit=0):
    assert url == base + bundle.name, url
    shutil.copyfile(bundle, destination)
    return hashlib.sha256(bundle.read_bytes()).hexdigest(), bundle.stat().st_size


def transport(keys):
    stack = ExitStack()
    stack.enter_context(patch.object(updater_sign, "TRUSTED_KEYS", keys))
    stack.enter_context(patch.object(updater, "json_download", return_value=metadata))
    stack.enter_context(patch.object(updater, "bytes_download", side_effect=lambda url, limit=0: served[url]))
    stack.enter_context(patch.object(updater, "download", side_effect=download))
    return stack


for keys, expected in (((), "signing key"), ((updater_sign.public_key(os.urandom(32)).hex(),), "signature invalid")):
    with transport(keys):
        try:
            updater.update(root)
            raise AssertionError(f"update must be refused: {expected}")
        except updater.UpdateError as exc:
            assert expected in str(exc), exc
    assert updater.read_state(root)["current"] == old
with transport((updater_sign.public_key(seed).hex(),)):
    assert updater.update(root)["status"] == "updated"
assert updater.read_state(root)["current"] == __version__
assert updater.read_state(root)["pending"] is None
# Status must already show the active version without a normal launch activating it.
result = subprocess.run([str(launcher), "updates", "status", "--json"], capture_output=True, text=True, env=env, timeout=90)
assert result.returncode == 0, result.stderr
assert json.loads(result.stdout)["current"] == __version__
env["VIXL_NO_UPDATE"] = "1"
result = subprocess.run([str(launcher), "--version"], capture_output=True, text=True, env=env, timeout=90)
assert result.returncode == 0, result.stderr
assert result.stdout.strip() == __version__
assert updater.read_state(root)["current"] == __version__
assert updater.read_state(root)["previous"] == old
identity = subprocess.check_output(["whoami", "/user", "/fo", "csv", "/nh"], text=True)
sid = next(csv.reader(identity.strip().splitlines()))[1]
lock = root / ".update.lock"
subprocess.run(["icacls", str(lock), "/deny", f"*{sid}:(GW)"], check=True, capture_output=True)
try:
    before = updater.read_state(root)
    for arguments in (["--version"], ["--help"], ["--runtime-info", "--json"], ["commands", "--json"]):
        result = subprocess.run([str(launcher), *arguments], capture_output=True, text=True, env=env, timeout=90)
        assert result.returncode == 0, result.stderr
        assert updater.read_state(root) == before
finally:
    subprocess.run(["icacls", str(lock), "/remove:d", f"*{sid}"], check=True, capture_output=True)

env.pop("VIXL_NO_UPDATE")
# A corrupted candidate must never prevent the known-good version from running.
broken = "999.0.0"
(root / "versions" / broken).mkdir()
(root / "versions" / broken / "vixl-engine.exe").write_bytes(b"not an executable")
state = updater.read_state(root)
state.update(pending=broken, last_check=time.time())
updater.atomic_json(root / "install.json", state)
result = subprocess.run([str(launcher), "--version"], capture_output=True, text=True, env=env, timeout=90)
assert result.returncode == 0 and result.stdout.strip() == __version__, result.stderr
assert updater.read_state(root)["pending"] == broken
for arguments in (["--help"], ["--runtime-info", "--json"]):
    result = subprocess.run([str(launcher), *arguments], capture_output=True, text=True, env=env, timeout=90)
    assert result.returncode == 0, result.stderr
    assert updater.read_state(root)["pending"] == broken
# Ordinary commands perform pending activation/rejection; read-only diagnostics do not.
result = subprocess.run([str(launcher), "commands", "--json"], capture_output=True, text=True, env=env, timeout=90)
assert result.returncode == 0 and "organic-shape" in json.loads(result.stdout)["commands"], result.stderr
state = updater.read_state(root)
assert state["current"] == __version__ and state["pending"] is None and state["rejected"] == broken
# Reproduce access denied using a real Windows file ACL, including the user's
# no-previous-version state. Restore only this test file's deny entry afterward.
denied = "999.0.1"
blocked = updater.executable(root, denied)
blocked.parent.mkdir()
blocked.write_bytes(b"inaccessible candidate")
subprocess.run(["icacls", str(blocked), "/deny", f"*{sid}:(RX)"], check=True, capture_output=True)
try:
    state = updater.read_state(root)
    state.update(pending=denied, previous=None, last_check=time.time())
    updater.atomic_json(root / "install.json", state)
    result = subprocess.run([str(launcher), "--version"], capture_output=True, text=True, env=env, timeout=90)
    assert result.returncode == 0 and result.stdout.strip() == __version__, result.stderr
    assert "Traceback" not in result.stderr
    assert updater.read_state(root)["pending"] == denied
    result = subprocess.run([str(launcher), "commands", "--json"], capture_output=True, text=True, env=env, timeout=90)
    assert result.returncode == 0, result.stderr
    state = updater.read_state(root)
    assert state["current"] == __version__ and state["previous"] is None
    assert state["pending"] is None and state["rejected"] == denied
    assert str(blocked) in state["last_error"] and "Access is denied" in state["last_error"]
finally:
    subprocess.run(["icacls", str(blocked), "/remove:d", f"*{sid}"], check=True, capture_output=True)
# A failed user command is not a reason to roll back a healthy application.
subprocess.run([str(launcher), "not-a-command"], capture_output=True, env=env, timeout=60)
assert updater.read_state(root)["current"] == __version__
print("Native signature, checksum, health check, immediate activation, corrupt/denied-candidate recovery passed.")
