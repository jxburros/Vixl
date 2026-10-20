"""Release selection, integrity, side-by-side activation and failure recovery."""

from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from vixl import updater as u
from vixl import updater_sign as sign
from vixl.cli import dispatch
from vixl.errors import VixlError


@pytest.fixture
def install(tmp_path, monkeypatch):
    root = tmp_path / "Vixl with spaces"
    (root / "versions" / "0.7.0").mkdir(parents=True)
    (root / "versions" / "0.7.0" / "vixl-engine.exe").write_bytes(b"baseline")
    u.atomic_json(
        root / "install.json",
        {"protocol": 1, "current": "0.7.0", "previous": None, "pending": None, "auto": True, "last_check": 0},
    )
    monkeypatch.setenv("VIXL_MANAGED_ROOT", str(root))
    return root


def bundle_bytes(members=None):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, value in (
            members or {"vixl-engine.exe": b"new runtime", "_internal/font.ttf": b"font"}
        ).items():
            archive.writestr(name, value)
    return stream.getvalue()


def release_fixture(monkeypatch, payload=None, release="0.8.0"):
    data = payload if payload is not None else bundle_bytes()
    info = {
        "version": release,
        "url": "fixture",
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "release_url": f"https://github.com/jxburros/Vixl/releases/tag/v{release}",
    }
    monkeypatch.setattr(u, "latest", lambda: deepcopy(info))

    def download(url, destination, limit=u.MAX_DOWNLOAD):
        Path(destination).write_bytes(data)
        return hashlib.sha256(data).hexdigest(), len(data)

    monkeypatch.setattr(u, "download", download)
    return info


def test_background_stage_is_atomic_then_activate_and_rollback(install, monkeypatch):
    release_fixture(monkeypatch)
    probes = []
    monkeypatch.setattr(u, "probe", lambda root, release, folder=None: probes.append((release, folder)))
    assert u.update(install, automatic=True)["status"] == "ready"
    state = u.read_state(install)
    assert state["current"] == "0.7.0" and state["pending"] == "0.8.0"
    assert (install / "versions/0.7.0/vixl-engine.exe").read_bytes() == b"baseline"
    exe, due = u.prepare_launch(install)
    assert exe == install / "versions/0.8.0/vixl-engine.exe" and due
    assert u.read_state(install)["previous"] == "0.7.0"
    assert u.rollback(install)["current"] == "0.7.0"
    assert not u.status(install)["automatic"]
    assert probes[0][1] is not None


def test_check_only_and_no_downgrades(install, monkeypatch):
    release_fixture(monkeypatch)
    before = u.read_state(install)
    assert u.update(install, check_only=True)["status"] == "available"
    assert u.read_state(install) == before
    assert list((install / "versions").iterdir()) == [install / "versions/0.7.0"]
    release_fixture(monkeypatch, release="0.6.9")
    assert u.update(install)["status"] == "up-to-date"


def test_bad_checksum_and_interrupted_download_keep_working_version(install, monkeypatch):
    info = release_fixture(monkeypatch)
    info["sha256"] = "0" * 64
    monkeypatch.setattr(u, "latest", lambda: info)
    with pytest.raises(u.UpdateError, match="checksum"):
        u.update(install)
    assert u.read_state(install)["current"] == "0.7.0"
    assert not (install / "versions/0.8.0").exists()

    def broken(*args):
        raise u.UpdateError("interrupted")

    monkeypatch.setattr(u, "download", broken)
    with pytest.raises(u.UpdateError, match="interrupted"):
        u.update(install)
    assert not u.read_state(install)["pending"]


def test_failed_pending_health_check_and_daily_check_cadence(install, monkeypatch):
    state = u.read_state(install)
    state["pending"] = "0.8.0"
    u.atomic_json(install / "install.json", state)

    def broken(*args, **kwargs):
        raise u.UpdateError("bad runtime")

    monkeypatch.setattr(u, "probe", broken)
    exe, due = u.prepare_launch(install)
    assert exe == install / "versions/0.7.0/vixl-engine.exe" and due
    state = u.read_state(install)
    assert state["pending"] is None and state["rejected"] == "0.8.0"
    assert state["last_error"] == "bad runtime"
    assert u.prepare_launch(install)[1] is False


def test_background_failure_is_silent(install, monkeypatch, capsys):
    monkeypatch.setattr(u, "latest", lambda: (_ for _ in ()).throw(u.UpdateError("offline")))
    u.background(install)
    assert capsys.readouterr() == ("", "")
    assert u.status(install)["last_error"] == "offline"
    assert u.prepare_launch(install)[0].is_file()


def test_disabled_and_no_update_launches_do_not_activate(install, monkeypatch):
    state = u.read_state(install)
    state["pending"] = "0.8.0"
    u.atomic_json(install / "install.json", state)
    monkeypatch.setattr(u, "probe", lambda *args, **kwargs: pytest.fail("must not probe"))
    exe, due = u.prepare_launch(install, allow_updates=False)
    assert "0.7.0" in str(exe) and not due
    assert u.read_state(install)["pending"] == "0.8.0"
    u.preference(install, False)
    assert u.read_state(install)["pending"] is None
    monkeypatch.setattr(u, "latest", lambda: pytest.fail("must not request network"))
    assert u.update(install, automatic=True)["status"] == "disabled"
    assert u.prepare_launch(install)[1] is False


def test_disable_during_download_prevents_pending_switch(install, monkeypatch):
    release_fixture(monkeypatch)

    def probe(root, release, folder=None):
        u.preference(root, False)

    monkeypatch.setattr(u, "probe", probe)
    assert u.update(install, automatic=True)["status"] == "disabled"
    assert u.read_state(install)["pending"] is None


def test_rejected_version_is_not_automatically_retried(install, monkeypatch):
    release_fixture(monkeypatch)
    state = u.read_state(install)
    state["rejected"] = "0.8.0"
    u.atomic_json(install / "install.json", state)
    assert u.update(install, automatic=True)["status"] == "previously-rejected"


@pytest.mark.parametrize(
    "member",
    [
        "../escape",
        "/absolute",
        "C:/escape",
        "dir\\escape",
        "file.exe:stream",
        "dir/CON.txt",
        "dir/file.",
        "dir/file ",
        "a/../../escape",
    ],
)
def test_malicious_archive_paths_are_rejected(tmp_path, member):
    archive = tmp_path / "bad.zip"
    archive.write_bytes(bundle_bytes({member: b"bad"}))
    with pytest.raises(u.UpdateError):
        u.extract_bundle(archive, tmp_path / "out")
    assert not (tmp_path / "escape").exists()


def test_zip_links_and_case_collisions(tmp_path):
    archive = tmp_path / "bad.zip"
    archive.write_bytes(bundle_bytes({"File": b"a", "file": b"b"}))
    with pytest.raises(u.UpdateError, match="Duplicate"):
        u.extract_bundle(archive, tmp_path / "out")
    with zipfile.ZipFile(archive, "w") as z:
        entry = zipfile.ZipInfo("link")
        entry.create_system = 3
        entry.external_attr = 0o120777 << 16
        z.writestr(entry, "/outside")
    with pytest.raises(u.UpdateError, match="link"):
        u.extract_bundle(archive, tmp_path / "out")


class SignedRelease:
    """GitHub transport for latest(): release metadata, a manifest and its .sig, signed by a key made in the test."""

    def __init__(self, monkeypatch, release="0.8.0"):
        import os

        self.seed = os.urandom(32)
        self.public = sign.public_key(self.seed).hex()
        monkeypatch.setattr(sign, "TRUSTED_KEYS", (self.public,))
        self.release = {
            "tag_name": f"v{release}",
            "draft": False,
            "prerelease": False,
            "assets": [{"name": u.MANIFEST}, {"name": u.SIGNATURE}, {"name": f"vixl-{release}-windows-x64.zip"}],
        }
        self.manifest = {
            "protocol": 1,
            "version": release,
            "platform": "windows-x64",
            "asset": f"vixl-{release}-windows-x64.zip",
            "sha256": "a" * 64,
            "size": 123,
            "min_launcher": 1,
        }
        self.tamper = None
        self.signer = self.seed
        self.requested = []
        monkeypatch.setattr(u, "json_download", self.json)
        monkeypatch.setattr(u, "bytes_download", self.bytes)

    def manifest_bytes(self):
        return (json.dumps(self.manifest, indent=2) + "\n").encode()

    def json(self, url):
        assert url == u.API
        return deepcopy(self.release)

    def bytes(self, url, limit=1024 * 1024):
        self.requested.append(url.rsplit("/", 1)[-1])
        data = self.manifest_bytes()
        if url.endswith("/" + u.SIGNATURE):
            return (sign.sign(self.signer, data).hex() + "\n").encode()
        assert url.endswith("/" + u.MANIFEST)
        return self.tamper(data) if self.tamper else data


def test_latest_only_trusts_published_stable_correct_platform(monkeypatch):
    fixture = SignedRelease(monkeypatch)
    release, manifest = fixture.release, fixture.manifest
    assert (
        u.latest()["url"]
        == "https://github.com/jxburros/Vixl/releases/download/v0.8.0/vixl-0.8.0-windows-x64.zip"
    )
    release["prerelease"] = True
    with pytest.raises(u.UpdateError):
        u.latest()
    release["prerelease"] = False
    manifest["protocol"] = 2
    with pytest.raises(u.UpdateError, match="newer installer"):
        u.latest()
    manifest["protocol"] = 1
    manifest["asset"] = "https://evil.test/run.exe"
    with pytest.raises(u.UpdateError):
        u.latest()


def test_valid_signature_accepted(monkeypatch):  # #621
    fixture = SignedRelease(monkeypatch)
    assert u.latest()["sha256"] == "a" * 64
    assert fixture.requested == [u.MANIFEST, u.SIGNATURE]
    # A signed manifest without min_launcher (the field is optional) is accepted.
    del fixture.manifest["min_launcher"]
    assert u.latest()["version"] == "0.8.0"


def test_unsigned_manifest_refused(install, monkeypatch):  # #621
    fixture = SignedRelease(monkeypatch)
    fixture.release["assets"] = [a for a in fixture.release["assets"] if a["name"] != u.SIGNATURE]
    with pytest.raises(u.UpdateError, match="signature missing"):
        u.latest()
    assert fixture.requested == []
    # Through update(), the refusal leaves the installed version active and downloads no runtime.
    monkeypatch.setattr(u, "download", lambda *a, **k: pytest.fail("must not download the runtime"))
    with pytest.raises(u.UpdateError, match="signature missing"):
        u.update(install)
    assert u.read_state(install)["current"] == "0.7.0"


@pytest.mark.parametrize("signature", [b"", b"not hex", b"00" * 64 + b"\n", "é".encode() * 64])
def test_malformed_signature_refused(monkeypatch, signature):  # #621
    fixture = SignedRelease(monkeypatch)
    real = fixture.bytes
    monkeypatch.setattr(u, "bytes_download", lambda url, limit=0: signature if url.endswith(".sig") else real(url))
    with pytest.raises(u.UpdateError, match="signature invalid"):
        u.latest()


def test_tampered_manifest_refused(install, monkeypatch):  # #621
    fixture = SignedRelease(monkeypatch)

    def flip(data):
        index = data.index(b"a" * 64)
        return data[:index] + b"b" + data[index + 1:]

    fixture.tamper = flip
    with pytest.raises(u.UpdateError, match="Update signature invalid; current version kept"):
        u.latest()
    fixture.tamper = lambda data: data + b" "  # even whitespace outside the JSON is covered
    with pytest.raises(u.UpdateError, match="signature invalid"):
        u.latest()
    monkeypatch.setattr(u, "download", lambda *a, **k: pytest.fail("must not download the runtime"))
    with pytest.raises(u.UpdateError, match="signature invalid"):
        u.update(install)
    assert u.read_state(install)["current"] == "0.7.0"


def test_wrong_key_refused(monkeypatch):  # #621
    import os

    fixture = SignedRelease(monkeypatch)
    fixture.signer = os.urandom(32)
    with pytest.raises(u.UpdateError, match="signature invalid"):
        u.latest()
    # Any pinned key verifies: the backup key signs after a rotation.
    monkeypatch.setattr(sign, "TRUSTED_KEYS", (fixture.public, sign.public_key(fixture.signer).hex()))
    assert u.latest()["version"] == "0.8.0"


def test_build_without_signing_key_refuses_updates(monkeypatch):  # #621
    SignedRelease(monkeypatch)
    monkeypatch.setattr(sign, "TRUSTED_KEYS", ())
    with pytest.raises(u.UpdateError, match="no update signing key"):
        u.latest()


def test_newer_min_launcher_asks_for_installer(monkeypatch):  # #621
    fixture = SignedRelease(monkeypatch)
    fixture.manifest["min_launcher"] = u.LAUNCHER + 1
    with pytest.raises(u.UpdateError, match="newer installer"):
        u.latest()
    fixture.manifest["min_launcher"] = "1"
    with pytest.raises(u.UpdateError, match="newer installer"):
        u.latest()


RFC8032 = [
    ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
     "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
     "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
    ("c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
     "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025", "af82",
     "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a"),
]


@pytest.mark.parametrize("secret, public, message, signature", RFC8032)
def test_ed25519_rfc8032_vectors(secret, public, message, signature):  # #621
    secret, public, message, signature = map(bytes.fromhex, (secret, public, message, signature))
    assert sign.public_key(secret) == public
    assert sign.sign(secret, message) == signature
    assert sign.verify(public, message, signature)
    assert not sign.verify(public, message + b"\0", signature)
    assert not sign.verify(public, message, signature[:63] + bytes([signature[63] ^ 1]))
    # S at or above the group order is rejected (no malleable second signature).
    s = int.from_bytes(signature[32:], "little") + 2**252 + 27742317777372353535851937790883648493
    assert not sign.verify(public, message, signature[:32] + s.to_bytes(32, "little"))
    assert not sign.verify(b"\xff" * 32, message, signature) and not sign.verify(public, message, signature[:63])


def test_sign_manifest_script_signs_only_with_a_trusted_key(tmp_path, monkeypatch):  # #621
    import importlib.util
    import os

    monkeypatch.setattr(sys, "path", list(sys.path))  # the script appends src/vixl; keep that out of other tests
    location = Path(__file__).resolve().parents[1] / "distribution/sign_manifest.py"
    spec = importlib.util.spec_from_file_location("sign_manifest", location)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    manifest = tmp_path / u.MANIFEST
    manifest.write_bytes(b'{"protocol": 1}\n')
    seed = os.urandom(32)
    with pytest.raises(SystemExit, match="not in updater_sign.TRUSTED_KEYS"):
        script.sign_file(manifest, seed, keys=())
    assert not (tmp_path / u.SIGNATURE).exists()
    keys = (sign.public_key(seed).hex(),)
    written = script.sign_file(manifest, seed, keys=keys)
    assert written == tmp_path / u.SIGNATURE
    assert sign.trusted(manifest.read_bytes(), written.read_bytes(), keys)
    monkeypatch.setenv(script.ENVIRONMENT, "short")
    with pytest.raises(SystemExit, match="64 hex"):
        script.main([str(manifest)])


def test_launcher_freeze_finds_the_verifier_outside_the_package():  # #621
    source = Path(__file__).resolve().parents[1] / "src" / "vixl"
    code = "import updater, updater_sign; assert updater.updater_sign is updater_sign; print(updater.LAUNCHER)"
    result = subprocess.run([sys.executable, "-I", "-c", f"import sys; sys.path.append({str(source)!r}); {code}"],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0 and result.stdout.strip() == "1", result.stderr


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/file",
        "https://evil.test/file",
        "https://github.com@evil.test/file",
        "https://github.com:8443/file",
        "file:///etc/passwd",
    ],
)
def test_download_and_redirect_host_allowlist(url):
    with pytest.raises(u.UpdateError):
        u.check_url(url)


def test_cli_management_without_project(install, monkeypatch):
    monkeypatch.chdir(install)
    value, _ = dispatch(["updates", "off", "--json"])
    assert value == {"automatic": False}
    value, _ = dispatch(["updates", "status"])
    assert value["current"] == "0.7.0"
    release_fixture(monkeypatch)
    value, _ = dispatch(["update", "--check"])
    assert value["status"] == "available"
    monkeypatch.delenv("VIXL_MANAGED_ROOT")
    with pytest.raises(VixlError, match="Windows installer") as caught:
        dispatch(["update"])
    assert "pip install -U vixl-engine" in str(caught.value)


def test_probe_checks_real_version_and_health_result(install, monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, b'{"ok":true,"version":"0.7.0"}', b""),
    )
    u.probe(install, "0.7.0")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, b'{"ok":true,"version":"9.0.0"}', b""),
    )
    with pytest.raises(u.UpdateError):
        u.probe(install, "0.7.0")


def test_initialize_rejects_downgrade_preserves_opt_out(install, monkeypatch):
    monkeypatch.setattr(u, "probe", lambda *a, **kw: None)
    u.preference(install, False)
    u.initialize(install, "0.8.0")
    state = u.read_state(install)
    assert state["previous"] == "0.7.0" and state["auto"] is False
    with pytest.raises(u.UpdateError, match="downgrades"):
        u.initialize(install, "0.6.0")
    assert u.read_state(install) == state


def test_process_lock_excludes_other_processes(install):
    script = "from pathlib import Path; from vixl.updater import locked; import sys\nwith locked(Path(sys.argv[1]), timeout=.1): pass"
    import sys

    with u.locked(install):
        result = subprocess.run([sys.executable, "-c", script, str(install)], capture_output=True, timeout=5)
    assert result.returncode != 0 and b"Another Vixl update" in result.stderr


def test_launcher_rollback_does_not_depend_on_running_engine(install, monkeypatch, capsys):
    import importlib.util
    import sys

    path = Path(__file__).resolve().parents[1] / "distribution" / "launcher.py"
    monkeypatch.setitem(sys.modules, "updater", u)
    spec = importlib.util.spec_from_file_location("vixl_launcher_test", path)
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    state = u.read_state(install)
    state["previous"] = "0.6.0"
    u.atomic_json(install / "install.json", state)
    monkeypatch.setattr(sys, "executable", str(install / "bin/vixl.exe"))
    monkeypatch.setattr(sys, "argv", ["vixl", "update", "--rollback", "--json"])
    monkeypatch.setattr(u, "probe", lambda *a, **kw: None)
    monkeypatch.setattr(
        subprocess, "call", lambda *a, **kw: pytest.fail("broken active CLI must not execute")
    )
    assert launcher.main() == 0
    assert json.loads(capsys.readouterr().out)["current"] == "0.6.0"
    assert not u.read_state(install)["auto"]


@pytest.mark.parametrize("automatic_enabled", [True, False])
def test_explicit_update_activates_before_returning(install, monkeypatch, automatic_enabled):
    release_fixture(monkeypatch)
    u.preference(install, automatic_enabled)
    probes = []
    monkeypatch.setattr(u, "probe", lambda root, release, folder=None: probes.append((release, folder)))
    value, _ = dispatch(["update", "--json"])
    assert value["status"] == "updated"
    assert value["current"] == "0.8.0" and value["previous"] == "0.7.0"
    state = u.read_state(install)
    assert state["current"] == "0.8.0" and state["pending"] is None
    assert state["auto"] == automatic_enabled
    assert probes[-1] == ("0.8.0", None)  # Probe again at the final installed path.
    assert u.prepare_launch(install, allow_updates=False)[0] == u.executable(install, "0.8.0")
    assert u.rollback(install)["current"] == "0.7.0"


@pytest.mark.parametrize("fail_at_final_path", [False, True])
def test_explicit_failed_healthcheck_keeps_previous_state(install, monkeypatch, fail_at_final_path):
    release_fixture(monkeypatch)
    before = u.read_state(install)

    def probe(root, release, folder=None):
        if not fail_at_final_path or folder is None:
            raise u.UpdateError("broken runtime")

    monkeypatch.setattr(u, "probe", probe)
    with pytest.raises(u.UpdateError, match="broken runtime"):
        u.update(install)
    assert u.read_state(install) == before
    assert u.executable(install, "0.7.0").read_bytes() == b"baseline"


def test_explicit_update_activates_existing_pending_version(install, monkeypatch):
    release_fixture(monkeypatch)
    monkeypatch.setattr(u, "probe", lambda *a, **kw: None)
    u.update(install, automatic=True)
    assert u.status(install)["pending"] == "0.8.0"
    assert u.update(install)["status"] == "updated"
    assert u.status(install)["pending"] is None
    assert u.status(install)["current"] == "0.8.0"


@pytest.mark.parametrize("args, expected", [(["update"], "updated"), (["--json", "update", "--check"], "available")])
def test_launcher_update_does_not_require_working_engine(install, monkeypatch, capsys, args, expected):
    import importlib.util
    import sys

    path = Path(__file__).resolve().parents[1] / "distribution" / "launcher.py"
    monkeypatch.setitem(sys.modules, "updater", u)
    spec = importlib.util.spec_from_file_location("vixl_launcher_update_test", path)
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    release_fixture(monkeypatch)
    monkeypatch.setattr(sys, "executable", str(install / "bin/vixl.exe"))
    monkeypatch.setattr(sys, "argv", ["vixl", *args])
    monkeypatch.setattr(u, "probe", lambda *a, **kw: None)
    monkeypatch.setattr(subprocess, "call", lambda *a, **kw: pytest.fail("must not execute active CLI"))
    assert launcher.main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == expected
    assert u.status(install)["current"] == ("0.8.0" if expected == "updated" else "0.7.0")


@pytest.mark.parametrize("payload", [b"null", b"[]", b'"unexpected"', b'{"ok": false, "version": "0.7.0"}'])
def test_probe_rejects_malformed_healthcheck_payload(install, monkeypatch, payload):
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 0, payload, b""))
    with pytest.raises(u.UpdateError):
        u.probe(install, "0.7.0")


@pytest.fixture
def launcher(install, monkeypatch):
    import importlib.util
    import sys

    path = Path(__file__).resolve().parents[1] / "distribution" / "launcher.py"
    monkeypatch.setitem(sys.modules, "updater", u)
    spec = importlib.util.spec_from_file_location("vixl_launcher_access_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, "executable", str(install / "bin/vixl.exe"))
    return module


def deny_stat(monkeypatch, blocked):
    original = Path.stat

    def stat(path, *args, **kwargs):
        if path == blocked:
            raise PermissionError(13, "Access is denied", str(path))
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", stat)


@pytest.mark.parametrize("failure", ["stat", "start"])
def test_denied_pending_runtime_launches_current_without_previous_version(
    install, monkeypatch, launcher, capsys, failure,
):
    import sys
    import time

    blocked = u.executable(install, "0.8.0")
    blocked.parent.mkdir()
    blocked.write_bytes(b"blocked runtime")
    state = u.read_state(install)
    state.update(pending="0.8.0", last_check=time.time())
    u.atomic_json(install / "install.json", state)
    if failure == "stat":
        deny_stat(monkeypatch, blocked)

    def denied_run(*args, **kwargs):
        assert failure == "start", "stat failure must be handled before starting the candidate"
        raise PermissionError(13, "Access is denied", str(blocked))

    monkeypatch.setattr(subprocess, "run", denied_run)
    calls = []
    monkeypatch.setattr(subprocess, "call", lambda argv, **kw: calls.append(argv) or 0)
    monkeypatch.setattr(sys, "argv", ["vixl", "status"])
    assert launcher.main() == 0
    assert calls == [[str(u.executable(install, "0.7.0")), "status"]]
    state = u.read_state(install)
    assert state["current"] == "0.7.0" and state["previous"] is None
    assert state["pending"] is None and state["rejected"] == "0.8.0"
    assert str(blocked) in state["last_error"] and "Access is denied" in state["last_error"]
    assert capsys.readouterr().err == ""
    # Do not keep trying the rejected executable on later launches.
    assert launcher.main() == 0
    assert len(calls) == 2


def test_explicit_update_of_denied_existing_candidate_keeps_active_runtime(install, monkeypatch):
    release_fixture(monkeypatch)
    blocked = u.executable(install, "0.8.0")
    blocked.parent.mkdir()
    blocked.write_bytes(b"blocked runtime")
    state = u.read_state(install)
    state["pending"] = "0.8.0"
    u.atomic_json(install / "install.json", state)
    deny_stat(monkeypatch, blocked)
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **kw: subprocess.CompletedProcess(a, 0, b'{"ok":true,"version":"0.8.0"}', b""),
    )
    with pytest.raises(VixlError, match="Access is denied") as caught:
        dispatch(["update"])
    assert caught.value.code == "update_error"
    assert u.read_state(install) == state
    assert u.executable(install, "0.7.0").read_bytes() == b"baseline"
    assert u.prepare_launch(install)[0] == u.executable(install, "0.7.0")
    assert u.read_state(install)["pending"] is None


@pytest.mark.parametrize("args", [["updates"], ["updates", "status"], ["updates", "off"], ["updates", "on"]])
def test_launcher_update_settings_work_when_active_and_pending_are_denied(
    install, monkeypatch, launcher, capsys, args,
):
    import sys

    state = u.read_state(install)
    state["pending"] = "0.8.0"
    u.atomic_json(install / "install.json", state)
    deny_stat(monkeypatch, u.executable(install, "0.7.0"))
    monkeypatch.setattr(u, "probe", lambda *a, **kw: pytest.fail("must not probe pending version"))
    monkeypatch.setattr(subprocess, "call", lambda *a, **kw: pytest.fail("must not launch active version"))
    monkeypatch.setattr(sys, "argv", ["vixl", *args, "--json"])
    assert launcher.main() == 0
    result = json.loads(capsys.readouterr().out)
    if args[-1] in ("on", "off"):
        assert result == {"automatic": args[-1] == "on"}
        if args[-1] == "off":
            assert u.read_state(install)["pending"] is None
    else:
        assert result["current"] == "0.7.0" and result["pending"] == "0.8.0"


@pytest.mark.parametrize("failure", ["stat", "start"])
def test_denied_active_runtime_reports_actionable_error_without_traceback(
    install, monkeypatch, launcher, capsys, failure,
):
    import sys

    active = u.executable(install, "0.7.0")
    if failure == "stat":
        deny_stat(monkeypatch, active)
    monkeypatch.setenv("VIXL_NO_UPDATE", "1")
    monkeypatch.setattr(sys, "argv", ["vixl", "--version", "--json"])

    def denied_call(*a, **kw):
        assert failure == "start"
        raise PermissionError(13, "Access is denied", str(active))

    monkeypatch.setattr(subprocess, "call", denied_call)
    before = u.read_state(install)
    assert launcher.main() == 1
    output = capsys.readouterr()
    assert output.out == ""
    result = json.loads(output.err)
    assert result["error"] == "update_error"
    assert str(active) in result["message"] and "updates status" in result["message"]
    assert "Traceback" not in output.err
    assert u.read_state(install) == before


def load_launcher(monkeypatch, name="vixl_launcher_root_test"):
    import importlib.util
    import sys

    path = Path(__file__).resolve().parents[1] / "distribution" / "launcher.py"
    monkeypatch.setitem(sys.modules, "updater", u)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def alias(tmp_path):
    folder = tmp_path / "LocalAppData" / "Microsoft" / "WindowsApps"
    folder.mkdir(parents=True)
    exe = folder / "vixl.exe"
    exe.write_bytes(b"launcher")
    return exe


def test_launcher_root_is_beside_bin_for_normal_install(install, monkeypatch, tmp_path):
    launcher = load_launcher(monkeypatch)
    other = tmp_path / "elsewhere"
    env = {"VIXL_HOME": str(other), "LOCALAPPDATA": str(tmp_path)}
    # install.json beside bin wins over every fallback, including an explicit VIXL_HOME.
    assert launcher.resolve_root(install / "bin" / "vixl.exe", env, lambda: str(other)) == install.resolve()
    # A fresh install has versions\ before --vixl-install writes install.json.
    (install / "install.json").unlink()
    assert launcher.resolve_root(install / "bin" / "vixl.exe", env) == install.resolve()


def test_launcher_alias_root_fallback_order(install, monkeypatch, alias, tmp_path):
    launcher = load_launcher(monkeypatch)
    local = str(alias.parents[2])
    explicit = tmp_path / "explicit"
    assert launcher.resolve_root(alias, {"VIXL_HOME": str(explicit), "LOCALAPPDATA": local}) == explicit
    assert launcher.resolve_root(alias, {"VIXL_MANAGED_ROOT": str(install), "LOCALAPPDATA": local}) == install
    # The installer's registry record is used when it names a real installation.
    assert launcher.resolve_root(alias, {"LOCALAPPDATA": local}, lambda: str(install)) == install
    default = Path(local) / "Programs" / "Vixl"
    assert launcher.resolve_root(alias, {"LOCALAPPDATA": local}, lambda: str(tmp_path / "gone")) == default
    assert launcher.resolve_root(alias, {"LOCALAPPDATA": local}, lambda: None) == default
    assert launcher.resolve_root(alias, {}) == alias.resolve().parent.parent


def test_registry_root_lookup_never_raises(monkeypatch):
    launcher = load_launcher(monkeypatch)
    value = launcher.registry_install_root()
    assert value is None or isinstance(value, str)


def test_launcher_alias_copy_runs_installed_engine_and_respawns_itself(install, monkeypatch, alias):
    import sys

    launcher = load_launcher(monkeypatch)
    monkeypatch.delenv("VIXL_MANAGED_ROOT")
    monkeypatch.delenv("VIXL_HOME", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(alias.parents[2]))
    monkeypatch.setattr(launcher, "registry_install_root", lambda: str(install))
    monkeypatch.setattr(sys, "executable", str(alias))
    monkeypatch.setattr(sys, "argv", ["vixl", "--version"])
    monkeypatch.setattr(
        u, "prepare_launch", lambda root, allow_updates=True: (u.executable(root, "0.7.0"), True)
    )
    calls = []
    monkeypatch.setattr(subprocess, "call", lambda cmd, env: calls.append((cmd, env)) or 0)
    spawned = []
    monkeypatch.setattr(subprocess, "DETACHED_PROCESS", 0, raising=False)
    monkeypatch.setattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0, raising=False)
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: spawned.append((cmd, kw)))
    assert launcher.main() == 0
    ((cmd, env),) = calls
    assert cmd == [str(install.resolve() / "versions" / "0.7.0" / "vixl-engine.exe"), "--version"]
    assert env["VIXL_MANAGED_ROOT"] == str(install.resolve())
    ((background, options),) = spawned
    assert background == [str(alias), "--vixl-background-update"]
    # The respawned alias copy finds the same root from the environment it is given.
    assert launcher.resolve_root(alias, options["env"]) == install.resolve()

