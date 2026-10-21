from pathlib import Path
import tomllib


def test_source_distribution_carries_the_sources_tests_and_what_tests_read():
    """Tests read docs/, skills/ and the changelog, so the sdist ships them (large media stay in VixlExamples)."""
    root = Path(__file__).resolve().parent.parent
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    sdist = config["tool"]["hatch"]["build"]["targets"]["sdist"]
    includes = sdist["include"]
    assert set(includes) == {"/src/vixl", "/tests", "/docs", "/skills", "/CHANGELOG.md", "/pyproject.toml",
                             "/README.md", "/LICENSE"}
    assert all((root / path.lstrip("/")).exists() for path in includes)
    assert "/tests/visual/_failures" in sdist["exclude"]


def test_included_directories_stay_small_enough_for_the_sdist_cap():
    """CI builds the sdist and fails above 15 MB; this catches the growth earlier, without building."""
    root = Path(__file__).resolve().parent.parent
    total = 0
    for name in ("src/vixl", "tests", "docs", "skills"):
        total += sum(path.stat().st_size for path in (root / name).rglob("*")
                     if path.is_file() and "_failures" not in path.parts and "__pycache__" not in path.parts)
    assert total < 40 * 1024 * 1024, f"{total / 1e6:.1f} MB of uncompressed sdist content"


def _package_extensions():
    import importlib.util

    location = Path(__file__).resolve().parents[1] / "distribution/package_extensions.py"
    spec = importlib.util.spec_from_file_location("package_extensions", location)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _doc_launch_lines(root):
    """`vixl mcp` command lines and MCP `args` arrays in fenced blocks of the user docs and the skill."""
    import json
    import re
    import shlex

    files = [root / "README.md", *sorted((root / "docs").rglob("*.md")), *sorted((root / "skills").rglob("*.md"))]
    for path in files:
        if "project" in path.relative_to(root).parts:
            continue
        fenced = False
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("```"):
                fenced = not fenced
                continue
            if not fenced:
                continue
            where = f"{path.relative_to(root)}:{number}"
            for match in re.finditer(r'"args":\s*(\[[^\]]*\])', line):
                args = json.loads(match.group(1))
                if "mcp" in args:
                    yield where, args
            if "vixl mcp" in line and '"args"' not in line:
                command = line.split(" #", 1)[0]
                if "[" in command or "|" in command:
                    continue  # usage synopsis, not a command
                yield where, shlex.split(command, posix=True)


def test_shipped_launch_args_parse(tmp_path):
    import json
    import re
    import zipfile

    from vixl.cli import mcp_parser
    from vixl.interfaces import mcp_server

    root = Path(__file__).resolve().parent.parent
    module = _package_extensions()
    outputs = module.build(tmp_path / "dist")
    sources = []
    for output in outputs:
        with zipfile.ZipFile(output) as archive:
            if output.suffix == ".mcpb":
                manifest = json.loads(archive.read("manifest.json"))
                sources.append(("vixl.mcpb manifest.json", manifest["server"]["mcp_config"]["args"]))
            else:
                bundled = json.loads(archive.read(".mcp.json"))
                sources.append(("vixl-claude-code.zip .mcp.json", bundled["mcpServers"]["vixl"]["args"]))
    checked_in = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))
    sources.append((".mcp.json", checked_in["mcpServers"]["vixl"]["args"]))
    plugin = json.loads((root / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    pointed = json.loads((root / plugin["mcpServers"]).read_text(encoding="utf-8"))
    sources += [(f"plugin.json -> {name}", server["args"]) for name, server in pointed["mcpServers"].items()]
    documented = list(_doc_launch_lines(root))
    assert any(where.startswith("README.md") for where, _ in documented)
    sources += documented

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for where, args in sources:
        assert "mcp" in args, where
        rest = args[args.index("mcp") + 1:]
        rest = [re.sub(r"\$\{[^}]*\}", lambda _: str(workspace), item) for item in rest]
        try:
            parsed = mcp_parser().parse_args(rest)
        except Exception as error:
            raise AssertionError(f"{where}: {args} does not start the server: {error}") from error
        if not parsed.http and where in {"vixl.mcpb manifest.json", ".mcp.json"}:
            mcp_server(workspace=str(workspace), tools=parsed.tools)
    assert checked_in["mcpServers"]["vixl"]["args"] == module.launch_args(".")


def test_launch_args_reject_removed_flags():
    import pytest

    from vixl.cli import mcp_parser
    from vixl.errors import VixlError

    with pytest.raises(VixlError):
        mcp_parser().parse_args(["--workspace", ".", "--tools", "core", "--schema", "slim"])


def _yaml_files(root):
    return [*sorted((root / ".github/workflows").glob("*.yml")), root / "action.yml"]


def _steps(document):
    """Every step of a workflow's jobs or a composite action."""
    if "jobs" in document:
        for job in document["jobs"].values():
            yield from job.get("steps", [])
    else:
        yield from document.get("runs", {}).get("steps", [])


def test_workflows_pin_actions_by_sha(tmp_path):  # #673
    import importlib.util
    import re

    import yaml

    root = Path(__file__).resolve().parent.parent
    uses = []
    for path in _yaml_files(root):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        uses += [(path.name, step["uses"]) for step in _steps(document) if "uses" in step]
    assert len(uses) > 20
    unpinned = [(name, ref) for name, ref in uses if not re.search(r"@[0-9a-f]{40}$", ref)]
    assert not unpinned, unpinned

    spec = importlib.util.spec_from_file_location("check_workflow_pins", root / "scripts/check_workflow_pins.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    assert script.main([str(root)]) == 0
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / ".github/workflows/x.yml").write_text(
        "jobs:\n  a:\n    steps:\n      - uses: actions/checkout@v4\n"
        "      - uses: ./local\n      - uses: 'actions/cache@0057852bfaa89a56745cba8c7296529d2fc39830' # v4\n")
    assert [ref for _, _, ref in script.unpinned(tmp_path)] == ["actions/checkout@v4"]
    assert script.main([str(tmp_path)]) == 1


def test_manifest_launch_is_immutable(tmp_path):  # #673
    import json
    import zipfile

    from vixl import __version__

    root = Path(__file__).resolve().parent.parent
    pinned = f"vixl-engine=={__version__}"
    checked_in = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))
    assert checked_in["mcpServers"]["vixl"]["args"][:2] == ["--from", pinned]
    mcpb = next(path for path in _package_extensions().build(tmp_path) if path.suffix == ".mcpb")
    with zipfile.ZipFile(mcpb) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["server"]["mcp_config"]["args"][:2] == ["--from", pinned]
    for page in ("README.md", "docs/getting-started.md"):
        text = (root / page).read_text(encoding="utf-8")
        assert pinned in text and "archive/refs/tags" not in text, page


def test_release_publish_waits_for_the_protected_environment():  # #673
    import re
    import yaml

    root = Path(__file__).resolve().parent.parent
    workflow = yaml.safe_load((root / ".github/workflows/release.yml").read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    writers = {name for name, job in jobs.items() if "write" in (job.get("permissions") or {}).values()}
    assert writers == {"publish-vixl", "pypi"}
    assert workflow["permissions"] == {"contents": "read"}
    assert jobs["publish"]["permissions"] == {"contents": "read"}
    assert jobs["publish"]["environment"]["name"] == "release"
    assert {"plan", "verify", "windows"} <= set(jobs["publish"]["needs"])
    finish = jobs["publish-vixl"]
    assert re.fullmatch(r"JX-Holdings-LLC/release-infrastructure/\.github/workflows/finish\.yml@[0-9a-f]{40}", finish["uses"])
    assert finish["uses"].rsplit("@", 1)[1] == finish["with"]["toolkit-ref"]
    assert finish["with"]["source-sha"] == "${{ needs.plan.outputs.sha }}"
    assert finish["with"]["dry-run"] == "${{ inputs.dry_run }}"
    assert {"plan", "publish", "pypi"} <= set(finish["needs"])
    pypi = yaml.safe_load((root / ".github/workflows/pypi.yml").read_text(encoding="utf-8"))["jobs"]["publish"]
    assert pypi["environment"]["name"] == "pypi"
    assert pypi["permissions"] == {"id-token": "write"}
    assert not any("checkout@" in step.get("uses", "") for step in pypi["steps"])
    assert "permissions" not in jobs["plan"]


def test_release_signs_the_manifest_inside_the_protected_job():  # #621
    import yaml

    root = Path(__file__).resolve().parent.parent
    text = (root / ".github/workflows/release.yml").read_text(encoding="utf-8")
    jobs = yaml.safe_load(text)["jobs"]
    names = [step.get("name", "") for step in jobs["publish"]["steps"]]
    sign = names.index("Sign the update manifest")
    assert sign < names.index("Checksum every release asset") < names.index("Stage the complete configured release inventory")
    step = jobs["publish"]["steps"][sign]
    assert step["env"] == {"VIXL_UPDATE_SIGNING_KEY": "${{ secrets.VIXL_UPDATE_SIGNING_KEY }}"}
    assert "distribution/sign_manifest.py release/vixl-update.json" in step["run"]
    assert text.count("secrets.") == 1  # no other job sees a secret
    assert any("updater_sign.TRUSTED_KEYS" in step.get("run", "") for step in jobs["verify"]["steps"])
