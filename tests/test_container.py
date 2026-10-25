"""The official container image (#546): what can be checked without Docker. The CI workflow
(.github/workflows/container.yml) builds the image and smoke-tests it read-only."""

import importlib.util
import io
import json
from pathlib import Path
import re
import shlex

import pytest
import yaml

from vixl import __version__

ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = ROOT / "distribution" / "container" / "Dockerfile"
WORKFLOW = ROOT / ".github" / "workflows" / "container.yml"
pytestmark = pytest.mark.skipif(not DOCKERFILE.is_file(), reason="distribution/ is not in the sdist")


def dockerfile():
    return DOCKERFILE.read_text(encoding="utf-8")


def test_the_image_version_matches_the_package():
    versions = re.findall(r"^ARG VERSION=(\S+)$", dockerfile(), re.MULTILINE)
    assert versions and set(versions) == {__version__}
    assert '"vixl-engine[server,pdf]==${VERSION}"' in dockerfile()
    releases = (ROOT / "docs" / "reference" / "releases.md").read_text(encoding="utf-8")
    assert "distribution/container/Dockerfile" in releases and "ghcr.io/jxburros/vixl" in releases


def test_the_entrypoint_flags_exist_and_parse():
    from vixl.host import host_parser

    entry = re.search(r"^ENTRYPOINT (\[.*\])$", dockerfile(), re.MULTILINE)
    command = json.loads(entry.group(1))
    assert command[:2] == ["vixl", "host"]
    parsed = host_parser().parse_args(command[2:])
    assert (parsed.root, parsed.offline, parsed.bind, parsed.port) == ("/data", True, "0.0.0.0", 8767)
    flags = [word for word in command[2:] if word.startswith("--")]
    help_text = host_parser().format_help()
    assert all(flag in help_text for flag in flags)
    assert "EXPOSE 8767" in dockerfile()


def test_the_image_runs_unprivileged_offline_and_read_only():
    text = dockerfile()
    assert "useradd --uid 10001" in text and text.count("USER 10001:10001") == 2  # base, and back after apt in full
    assert 'VOLUME ["/data"]' in text and "VIXL_OFFLINE=1" in text
    assert "HOME=/tmp/vixl" in text  # caches on the tmpfs when run with --read-only
    # Packs are fetched (and checked by SHA-256) at build time into VIXL_PACK_DIR; the runtime never downloads.
    assert "packs.install(name)" in text and text.count("VIXL_PACK_DIR=/opt/vixl/packs") == 2
    stages = re.findall(r"^FROM \S+ AS (\w+)$", text, re.MULTILINE)
    assert stages == ["build", "base", "full", "runtime"]  # runtime last: the default target
    full = text.split("AS full", 1)[1].split("FROM ", 1)[0]
    assert "ffmpeg" in full
    assert re.search(r'^HEALTHCHECK .*CMD \["python", "/opt/vixl/healthcheck.py"\]$', text, re.MULTILINE)


def healthcheck():
    spec = importlib.util.spec_from_file_location("healthcheck", ROOT / "distribution/container/healthcheck.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_health_check_sends_the_host_token(tmp_path, monkeypatch):
    check = healthcheck()
    seen = []

    class Answer(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def urlopen(request, timeout):
        seen.append((request.full_url, request.get_header("Authorization")))
        return Answer(json.dumps({"ok": True, "warm": False}).encode())

    monkeypatch.setattr(check.urllib.request, "urlopen", urlopen)
    monkeypatch.delenv("VIXL_HOST_TOKEN_FILE", raising=False)
    monkeypatch.setenv("VIXL_HOST_TOKEN", "from-env")
    assert check.main() == 0
    secret = tmp_path / "token"
    secret.write_text("from-file\n")
    monkeypatch.setenv("VIXL_HOST_TOKEN_FILE", str(secret))  # the file wins, as in vixl host
    assert check.main() == 0
    assert seen == [("http://127.0.0.1:8767/host/health", "Bearer from-env"),
                    ("http://127.0.0.1:8767/host/health", "Bearer from-file")]

    def refused(request, timeout):
        raise OSError("401")

    monkeypatch.setattr(check.urllib.request, "urlopen", refused)
    assert check.main() == 1


def test_the_workflow_builds_both_tags_and_smoke_tests_read_only():
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    triggers = workflow["on"]
    assert triggers["push"]["tags"] == ["v*"] and "workflow_dispatch" in triggers
    job = workflow["jobs"]["image"]
    assert job["permissions"] == {"contents": "read", "packages": "write"}
    assert {item["suffix"] for item in job["strategy"]["matrix"]["variant"]} == {"", "-full"}
    assert job["env"]["IMAGE"] == "ghcr.io/jxburros/vixl"
    script = "\n".join(step.get("run", "") for step in job["steps"])
    assert "--read-only --tmpfs /tmp -v vixl-smoke:/data" in script
    for route in ("/host/info", "/compose", "/exports", "/download"):
        assert route in script
    assert all(not step.get("uses") or "docker/" not in step["uses"] for step in job["steps"])
    build = next(step["run"] for step in job["steps"] if step.get("name") == "Build")
    assert "--build-arg" in shlex.split(build.replace("\\\n", " "))
