"""Managed-install updater. Standard library only: also bundled in the stable launcher.

Trust root: the Ed25519 keys pinned in updater_sign.TRUSTED_KEYS sign each release's vixl-update.json, which names
the runtime's SHA-256. Downloads come over HTTPS from GitHub releases in jxburros/Vixl; projects cannot supply
update URLs.
"""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

try:
    from . import updater_sign
except ImportError:  # the stable launcher freezes both modules at top level, outside the vixl package
    import updater_sign

REPOSITORY = "jxburros/Vixl"
API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
PROTOCOL = 1
INTERVAL = 24 * 60 * 60
MAX_DOWNLOAD = 256 * 1024 * 1024
MAX_EXPANDED = 1024 * 1024 * 1024
MANIFEST = "vixl-update.json"
SIGNATURE = "vixl-update.json.sig"
# Revision of this update code. A release whose manifest sets a higher `min_launcher` (for example after a key
# rotation that older launchers cannot verify) asks for a new installer instead of half-updating.
LAUNCHER = 1


class UpdateError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise UpdateError(message)


def version(value):
    require(
        isinstance(value, str) and re.fullmatch(r"\d+\.\d+\.\d+", value), "Expected a stable X.Y.Z version"
    )
    return tuple(map(int, value.split(".")))


def root_path():
    value = os.environ.get("VIXL_MANAGED_ROOT")
    if not value:
        import sys

        try:  # the stable launcher imports this module on its own, outside the vixl package
            from vixl import __version__
        except ImportError:
            __version__ = "(unknown version)"
        message = (f"This is Vixl {__version__} installed with pip (or from source); update it with "
                   "`python -m pip install -U vixl-engine`. Automatic updates are for the Windows installer")
        if sys.platform == "win32":
            message += " (Vixl-Setup from https://github.com/jxburros/Vixl/releases/latest)"
        require(False, message + ".")
    root = Path(value).resolve()
    require(
        (root / "install.json").is_file(),
        "Managed installation metadata is missing. Run the installer to repair Vixl.",
    )
    return root


def atomic_json(path, value):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=".vixl-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, allow_nan=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def locked(root, timeout=15):
    """Cross-process advisory lock, shared by launcher, CLI, and background worker."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".update.lock").open("a+b") as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise UpdateError("Another Vixl update is in progress; try again shortly.")
                time.sleep(0.05)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def read_state(root):
    try:
        data = (Path(root) / "install.json").read_bytes()
        require(len(data) < 65536, "Invalid installation metadata")
        state = json.loads(data)
        require(state["protocol"] == PROTOCOL, "This installation needs a newer installer")
        version(state["current"])
        for key in ("previous", "pending", "rejected"):
            if state.get(key):
                version(state[key])
        require(isinstance(state["auto"], bool), "Invalid update preference")
        return state
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise UpdateError("Cannot read installation metadata; run the installer to repair Vixl.") from exc


def executable(root, release):
    version(release)
    return Path(root) / "versions" / release / "vixl-engine.exe"


def child_environment(root):
    env = os.environ.copy()
    env["VIXL_MANAGED_ROOT"] = str(Path(root).resolve())
    # Each frozen process owns its own PyInstaller runtime, not its parent's extraction folder.
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def probe(root, release, folder=None):
    exe = Path(folder) / "vixl-engine.exe" if folder else executable(root, release)
    try:
        # is_file() can raise on older Python and suppress access errors on
        # newer Python. Keep stat inside the recovery boundary on every version.
        require(stat.S_ISREG(exe.stat().st_mode), f"Vixl {release} is incomplete")
        result = subprocess.run(
            [str(exe), "--vixl-healthcheck"],
            capture_output=True,
            timeout=45,
            env=child_environment(root),
            cwd=str(exe.parent),
        )
        payload = json.loads(result.stdout)
        require(
            result.returncode == 0 and isinstance(payload, dict)
            and payload.get("version") == release and payload.get("ok") is True,
            f"Vixl {release} did not pass its startup health check",
        )
    except FileNotFoundError as exc:
        raise UpdateError(f"Vixl {release} is incomplete at {exe}; no version switch was made") from exc
    except OSError as exc:
        raise UpdateError(
            f"Cannot access or start Vixl {release} at {exe}: {exc}. "
            "No version switch was made. Check file permissions or repair Vixl with the installer."
        ) from exc
    except (ValueError, subprocess.TimeoutExpired) as exc:
        raise UpdateError(f"Vixl {release} could not start; the previous version was kept") from exc


def initialize(root, release):
    version(release)
    with locked(root):
        probe(root, release)
        state = (
            read_state(root)
            if (Path(root) / "install.json").exists()
            else {
                "protocol": PROTOCOL,
                "auto": True,
                "previous": None,
                "pending": None,
                "last_check": 0,
            }
        )
        old = state.get("current")
        require(
            not old or version(release) >= version(old),
            "Installer downgrades are disabled; use vixl update --rollback instead",
        )
        if old != release:
            state["previous"] = old
        state.update(current=release, pending=None, rejected=None, last_error=None)
        atomic_json(Path(root) / "install.json", state)
    return state


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def check_url(url):
    parsed = urllib.parse.urlparse(url)
    require(
        parsed.scheme == "https"
        and parsed.hostname
        in {
            "api.github.com",
            "github.com",
            "release-assets.githubusercontent.com",
            "objects.githubusercontent.com",
        }
        and parsed.port in (None, 443)
        and not parsed.username
        and not parsed.password,
        "Update download is not from an approved GitHub host",
    )


def download(url, destination, limit=MAX_DOWNLOAD):
    check_url(url)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Vixl-Updater/1",
            "Accept": "application/vnd.github+json"
            if urllib.parse.urlparse(url).hostname == "api.github.com"
            else "application/octet-stream",
        },
    )
    opener = urllib.request.build_opener(SafeRedirect())
    count = 0
    digest = hashlib.sha256()
    try:
        with opener.open(request, timeout=30) as response, Path(destination).open("wb") as output:
            while chunk := response.read(1024 * 1024):
                count += len(chunk)
                require(count <= limit, "Update download exceeds the size limit")
                output.write(chunk)
                digest.update(chunk)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError("No published stable release is available yet") from exc
        raise UpdateError(f"GitHub update request failed (HTTP {exc.code})") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UpdateError("Could not reach GitHub; your installed version is unchanged") from exc
    return digest.hexdigest(), count


def bytes_download(url, limit=1024 * 1024):
    with tempfile.TemporaryDirectory(prefix="vixl-release-") as tmp:
        dest = Path(tmp) / "response"
        download(url, dest, limit)
        return dest.read_bytes()


def json_download(url):
    try:
        result = json.loads(bytes_download(url))
        require(isinstance(result, dict), "Invalid GitHub release metadata")
        return result
    except ValueError as exc:
        raise UpdateError("Invalid GitHub release metadata") from exc


def signed_manifest(data, signature):
    """Verify the exact downloaded bytes before parsing them; the signature covers every field."""
    require(
        updater_sign.TRUSTED_KEYS,
        "This Vixl build has no update signing key; install the latest release from GitHub to update",
    )
    require(updater_sign.trusted(data, signature), "Update signature invalid; current version kept")
    try:
        manifest = json.loads(data)
    except ValueError as exc:
        raise UpdateError("Invalid update metadata") from exc
    require(isinstance(manifest, dict), "Invalid update metadata")
    return manifest


def latest():
    release = json_download(API)
    require(
        release.get("draft") is False and release.get("prerelease") is False,
        "Only published stable releases can update Vixl",
    )
    tag = release.get("tag_name", "")
    require(isinstance(tag, str) and tag.startswith("v"), "Unexpected release tag")
    release_version = tag[1:]
    version(release_version)
    names = {a.get("name") for a in release.get("assets", []) if isinstance(a, dict)}
    bundle = f"vixl-{release_version}-windows-x64.zip"
    require({bundle, MANIFEST} <= names, "This release does not contain a Windows update")
    require(SIGNATURE in names, "Update signature missing; current version kept")
    base = f"https://github.com/{REPOSITORY}/releases/download/{tag}/"
    manifest = signed_manifest(bytes_download(base + MANIFEST, 64 * 1024), bytes_download(base + SIGNATURE, 1024))
    minimum = manifest.get("min_launcher", 1)
    require(
        type(minimum) is int and minimum <= LAUNCHER
        and manifest.get("protocol") == PROTOCOL
        and manifest.get("version") == release_version
        and manifest.get("platform") == "windows-x64"
        and manifest.get("asset") == bundle,
        "This release requires a newer installer or has invalid update metadata",
    )
    digest = manifest.get("sha256", "")
    require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest), "Invalid release checksum")
    size = manifest.get("size")
    require(type(size) is int and 0 < size <= MAX_DOWNLOAD, "Invalid release asset size")
    return {
        **manifest,
        "url": base + bundle,
        "release_url": f"https://github.com/{REPOSITORY}/releases/tag/{tag}",
    }


def extract_bundle(archive, destination):
    """Reject traversal, links, NTFS alternate streams and Windows name collisions."""
    destination = Path(destination)
    try:
        with zipfile.ZipFile(archive) as z:
            entries = z.infolist()
            require(
                len(entries) <= 20000 and sum(e.file_size for e in entries) <= MAX_EXPANDED,
                "Expanded update exceeds limits",
            )
            seen = set()
            for entry in entries:
                raw = entry.filename.rstrip("/")
                parts = raw.split("/")
                key = raw.casefold()
                require(
                    raw
                    and "\\" not in raw
                    and not PurePosixPath(raw).is_absolute()
                    and all(
                        p not in ("", ".", "..")
                        and not p.endswith((".", " "))
                        and not re.search(r'[<>:"|?*\x00-\x1f]', p)
                        and not re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", p)
                        for p in parts
                    ),
                    "Unsafe path in update archive",
                )
                require(
                    key not in seen and not stat.S_ISLNK(entry.external_attr >> 16),
                    "Duplicate path or link in update archive",
                )
                seen.add(key)
                require(entry.file_size <= MAX_DOWNLOAD, "Update member exceeds limits")
            for entry in entries:
                dest = destination.joinpath(*entry.filename.rstrip("/").split("/"))
                if entry.is_dir():
                    dest.mkdir(parents=True, exist_ok=True)
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(entry) as source, dest.open("wb") as output:
                        shutil.copyfileobj(source, output)
        require((destination / "vixl-engine.exe").is_file(), "Update archive has no Vixl runtime")
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        raise UpdateError("Update archive could not be safely extracted") from exc


def install_runtime(stage, destination):
    """Allow short Windows scanner/probe locks to clear before the atomic move."""
    delays = (0.1, 0.2, 0.4, 0.8, 1.6, 2.0)
    for attempt in range(len(delays) + 1):
        try:
            os.replace(stage, destination)
            return
        except OSError as exc:
            if getattr(exc, "winerror", None) not in (5, 32, 33) or attempt == len(delays):
                raise UpdateError(
                    f"Cannot install the verified runtime at {destination}: {exc}. "
                    "The current version is kept; retry vixl update after the file lock clears."
                ) from exc
            time.sleep(delays[attempt])


def update(root, check_only=False, automatic=False):
    """Download/check outside the short state lock; serialize downloads separately."""
    root = Path(root)
    # A second lock directory keeps normal editing launches independent of a slow download.
    with locked(root / "update-work", timeout=0 if automatic else 15):
        with locked(root):
            state = read_state(root)
            if automatic and not state["auto"]:
                return {"status": "disabled"}
            current = state["current"]
        release = latest()
        target = release["version"]
        result = {"current": current, "latest": target, "release_url": release["release_url"]}
        if version(target) <= version(current):
            return {**result, "status": "up-to-date"}
        if check_only:
            return {**result, "status": "available"}
        if automatic and state.get("rejected") == target:
            return {**result, "status": "previously-rejected"}
        with tempfile.TemporaryDirectory(prefix="vixl-download-", dir=root / "update-work") as tmp:
            archive = Path(tmp) / "update.zip"
            digest, size = download(release["url"], archive)
            require(
                digest == release["sha256"] and size == release["size"],
                "Update checksum or size mismatch; current version kept",
            )
            stage = Path(tmp) / "runtime"
            extract_bundle(archive, stage)
            probe(root, target, folder=stage)
            with locked(root):
                state = read_state(root)
                if automatic and not state["auto"]:
                    return {**result, "status": "disabled"}
                if version(target) <= version(state["current"]):
                    return {**result, "status": "up-to-date"}
                target_dir = root / "versions" / target
                if target_dir.exists():
                    probe(root, target)
                else:
                    target_dir.parent.mkdir(parents=True, exist_ok=True)
                    install_runtime(stage, target_dir)
                if automatic:
                    state.update(pending=target, last_error=None, rejected=None)
                else:
                    # Select the verified side-by-side runtime before returning. Never
                    # replace files loaded by this command or an existing editing session.
                    probe(root, target)
                    state.update(
                        previous=state["current"], current=target, pending=None,
                        last_error=None, rejected=None,
                    )
                atomic_json(root / "install.json", state)
        if not automatic:
            return {
                **result,
                "previous": state["previous"],
                "current": target,
                "pending": None,
                "status": "updated",
                "message": f"Vixl {target} is now active. Existing sessions keep their original runtime.",
            }
        return {
            **result,
            "status": "ready",
            "message": "Update verified. It will activate the next time you launch vixl.",
        }


def status(root):
    with locked(root):
        state = read_state(root)
    return {
        "current": state["current"],
        "previous": state.get("previous"),
        "pending": state.get("pending"),
        "automatic": state["auto"],
        "last_check": state.get("last_check"),
        "last_error": state.get("last_error"),
    }


def preference(root, enabled):
    with locked(root):
        state = read_state(root)
        state["auto"] = enabled
        # Disabling updates also stops a queued switch. Downloaded runtimes are retained.
        if not enabled:
            state["pending"] = None
        atomic_json(Path(root) / "install.json", state)
    return {"automatic": enabled}


def rollback(root):
    with locked(root):
        state = read_state(root)
        target = state.get("previous")
        require(target, "No previous version is available yet")
        probe(root, target)
        old = state["current"]
        state.update(current=target, previous=old, pending=None, auto=False, rejected=old, last_error=None)
        atomic_json(Path(root) / "install.json", state)
    return {
        "current": target,
        "automatic": False,
        "message": "Rolled back for subsequent launches. Automatic updates are off; use vixl updates on to re-enable.",
    }


def prepare_launch(root, allow_updates=True):
    """Activate only validated pending versions; never treat editing errors as failed updates."""
    if not allow_updates:
        state = read_state(root)
        exe = executable(root, state["current"])
        try:
            exists = stat.S_ISREG(exe.stat().st_mode)
        except FileNotFoundError:
            exists = False
        except OSError as exc:
            raise UpdateError(f"Cannot access the active Vixl runtime at {exe}: {exc}. Use vixl updates status to inspect the installation or run the installer to repair Vixl.") from exc
        require(exists, f"Active runtime is missing at {exe}; run the installer to repair Vixl")
        return exe, False
    with locked(root):
        state = read_state(root)
        pending = state.get("pending")
        if pending:
            try:
                probe(root, pending)
                state.update(previous=state["current"], current=pending, pending=None, last_error=None)
            except UpdateError as exc:
                state.update(pending=None, rejected=pending, last_error=str(exc))
            atomic_json(Path(root) / "install.json", state)
        exe = executable(root, state["current"])
        try:
            current_exists = stat.S_ISREG(exe.stat().st_mode)
        except FileNotFoundError:
            current_exists = False
        except OSError as exc:
            raise UpdateError(
                f"Cannot access the active Vixl runtime at {exe}: {exc}. "
                "Use vixl updates status to inspect the installation or run the installer to repair Vixl."
            ) from exc
        if not current_exists:
            previous = state.get("previous")
            require(previous, "Installed runtime is missing; run the installer to repair Vixl")
            probe(root, previous)
            state.update(
                current=previous,
                pending=None,
                auto=False,
                last_error="Recovered the previous runtime; run the installer to repair Vixl",
            )
            atomic_json(Path(root) / "install.json", state)
            exe = executable(root, previous)
        due = allow_updates and state["auto"] and time.time() - state.get("last_check", 0) >= INTERVAL
        if due:
            state["last_check"] = time.time()
            atomic_json(Path(root) / "install.json", state)
        return exe, due


def background(root):
    try:
        update(root, automatic=True)
    except Exception as exc:  # noqa: BLE001 - a background update check must never fail the command it runs beside
        # Background checks must never write into CLI JSON/image/MCP streams.
        try:
            with locked(root):
                state = read_state(root)
                state["last_error"] = str(exc)[:500]
                atomic_json(Path(root) / "install.json", state)
        except Exception:  # noqa: BLE001 - nowhere left to report the error to
            pass

