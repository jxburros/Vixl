"""Stable per-user launcher. Frozen separately; it does not import the imaging engine."""

import os
import json
from pathlib import Path
import subprocess
import sys

import updater

REGISTRY_KEY = r"Software\Vixl"  # Written by the installer: InstallRoot = {app}


def is_install_root(path):
    return (Path(path) / "install.json").is_file() or (Path(path) / "versions").is_dir()


def registry_install_root():
    """The installer-recorded root, or None. Never raises."""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "InstallRoot")
        return str(value) if value else None
    except (ImportError, OSError, ValueError):
        return None


def resolve_root(executable, environ, registry=None):
    r"""Find the managed installation this launcher copy belongs to.

    The normal copy lives at <root>\bin\vixl.exe. The installer may also place a copy
    in %LOCALAPPDATA%\Microsoft\WindowsApps (on PATH for already-running processes);
    that copy finds the root through VIXL_HOME, the root a parent launcher passed to
    its children, the installer's registry record, then the default per-user folder.
    """
    beside = Path(executable).resolve().parent.parent
    if is_install_root(beside):
        return beside
    for name in ("VIXL_HOME", "VIXL_MANAGED_ROOT"):
        if environ.get(name):
            return Path(environ[name])
    recorded = registry() if registry else None
    if recorded and is_install_root(recorded):
        return Path(recorded)
    if environ.get("LOCALAPPDATA"):
        return Path(environ["LOCALAPPDATA"]) / "Programs" / "Vixl"
    return beside


def main():
    args = sys.argv[1:]
    try:
        if args[:1] == ["--vixl-install"]:
            # The installer always runs <root>\bin\vixl.exe, before install.json exists.
            updater.require(len(args) == 2, "Installer requires a version")
            updater.initialize(Path(sys.executable).resolve().parent.parent, args[1])
            return 0
        root = resolve_root(sys.executable, os.environ, registry_install_root)
        if args == ["--vixl-background-update"]:
            updater.background(root)
            return 0
        # Management must work even when the active CLI cannot import, or is too
        # old to implement immediate activation. Do not activate pending updates
        # as a side effect of --check, status, or preference changes.
        control_args = [arg for arg in args if arg != "--json"]
        if control_args in (["update"], ["update", "--check"], ["update", "--rollback"]):
            result = (
                updater.rollback(root) if "--rollback" in control_args
                else updater.update(root, check_only="--check" in control_args)
            )
            print(json.dumps(result))
            return 0
        if control_args in (["updates"], ["updates", "status"], ["updates", "on"], ["updates", "off"]):
            result = (
                updater.preference(root, control_args[1] == "on")
                if control_args[-1] in ("on", "off") else updater.status(root)
            )
            print(json.dumps(result))
            return 0
        # Update controls inspect the currently installed state without switching it underneath the command.
        controls = any(x in ("update", "updates") for x in args)
        read_only = any(arg in ("--version", "--help", "-h", "--runtime-info") for arg in args) or control_args[:1] == ["help"]
        allow = os.environ.get("VIXL_NO_UPDATE") != "1" and not controls and not read_only
        exe, due = updater.prepare_launch(root, allow_updates=allow)
        env = updater.child_environment(root)
        if due:
            try:
                subprocess.Popen(
                    [sys.executable, "--vixl-background-update"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    cwd=str(root),
                    env=env,
                    close_fds=True,
                    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                )
            except OSError:
                pass  # Editing still works if Windows prevents background process creation.
        try:
            return subprocess.call([str(exe), *args], env=env)
        except OSError as exc:
            raise updater.UpdateError(
                f"Cannot launch Vixl at {exe}: {exc}. "
                "Use vixl updates status to inspect the installation or run the installer to repair Vixl."
            ) from exc
    except (updater.UpdateError, OSError) as exc:
        message = (
            json.dumps({"error": "update_error", "message": str(exc)}) if "--json" in args else f"Vixl: {exc}"
        )
        print(message, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

