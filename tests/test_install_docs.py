"""The install path a newcomer or an agent meets first: the package name (#753), the per-client table and the MCP
registry entry (#771), the licence summary (#774) and the template-API migration fixture (#772)."""

import importlib.util
import json
from pathlib import Path
import re
import tomllib
import zipfile

import yaml

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")


def load(relative):
    spec = importlib.util.spec_from_file_location(Path(relative).stem, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fenced(text):
    """``[(language, body)]`` of the fenced blocks in ``text``."""
    return [(lang, body) for lang, body in re.findall(r"^```(\w*)\n(.*?)^```", text, flags=re.MULTILINE | re.DOTALL)]


def section(text, heading):
    """The text under a ``## heading`` up to the next heading of that level."""
    match = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, flags=re.MULTILINE | re.DOTALL)
    assert match, f"no section {heading!r}"
    return match.group(1)


# ---------------------------------------------------------------- #753: a package name agents can guess


def test_the_first_install_block_of_the_readme_names_the_package():
    first = next(body for _, body in fenced(README) if "install" in body)
    assert "python -m pip install vixl-engine\n" in first
    started = (ROOT / "docs/getting-started.md").read_text(encoding="utf-8")
    assert "python -m pip install vixl-engine\n" in started
    assert started.index("python -m pip install vixl-engine\n") < started.index("git clone")
    assert "`pip install vixl-engine`" in (ROOT / "skills/vixl/SKILL.md").read_text(encoding="utf-8")
    finding = section((ROOT / "skills/vixl/references/cli.md").read_text(encoding="utf-8"), "Finding vixl")
    row = next(line for line in finding.splitlines() if line.startswith("| Not installed"))
    assert "pip install vixl-engine" in row and "`vixl`" in row


def test_the_alias_package_depends_on_the_engine_at_its_own_version(tmp_path):
    from vixl import __version__

    module = load("distribution/alias_package.py")
    project = module.write(tmp_path / "alias")
    meta = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
    engine = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert meta["project"]["name"] == "vixl" and meta["project"]["version"] == __version__
    assert meta["project"]["dependencies"] == [f"vixl-engine=={__version__}"]
    assert meta["project"]["optional-dependencies"] == {
        extra: [f"vixl-engine[{extra}]=={__version__}"] for extra in ("pdf", "server", "anthropic")}
    assert meta["project"]["license"] == engine["license"]
    assert meta["project"]["requires-python"] == engine["requires-python"]
    assert meta["tool"]["hatch"]["build"]["targets"]["wheel"] == {"bypass-selection": True}
    assert (project / "LICENSE").read_bytes() == (ROOT / "LICENSE").read_bytes()
    assert "vixl-engine" in (project / "README.md").read_text(encoding="utf-8")
    assert module.write(tmp_path / "pinned", "1.2.3").joinpath("pyproject.toml").read_text().count("1.2.3") == 5


# ---------------------------------------------------------------- #771: one install step per client


def test_install_for_your_agent_table_and_snippets_start_the_server(tmp_path):
    from vixl.cli import mcp_parser

    extensions = load("distribution/package_extensions.py")
    body = section(README, "Install for your agent")
    rows = [line.split("|")[1].strip() for line in body.splitlines() if line.startswith("| ")][2:]
    assert rows == ["Claude Desktop", "Claude Code", "Cursor", "VS Code", "Codex", "Any other MCP client"]
    blocks = fenced(body)
    assert [lang for lang, _ in blocks] == ["text", "json", "json", "toml"]

    marketplace = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert blocks[0][1].splitlines() == ["/plugin marketplace add jxburros/Vixl",
                                         f"/plugin install {plugin['name']}@{marketplace['name']}"]
    assert marketplace["plugins"][0]["name"] == plugin["name"]

    def expected(workspace):
        return extensions.launch_args(workspace, extensions.published_version())

    cursor, code = (json.loads(text) for _, text in blocks[1:3])
    assert cursor == {"mcpServers": {"vixl": {"command": "uvx", "args": expected("${workspaceFolder}")}}}
    assert code == {"servers": {"vixl": {"type": "stdio", "command": "uvx", "args": expected("${workspaceFolder}")}}}
    codex = tomllib.loads(blocks[3][1])
    assert codex == {"mcp_servers": {"vixl": {"command": "uvx", "args": expected(".")}}}

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for args in (cursor["mcpServers"]["vixl"]["args"], code["servers"]["vixl"]["args"],
                 codex["mcp_servers"]["vixl"]["args"]):
        rest = [str(workspace) if item in (".", "${workspaceFolder}") else item for item in args[args.index("mcp") + 1:]]
        assert mcp_parser().parse_args(rest).workspace == str(workspace)
    assert "vixl.mcpb" in body and "releases/latest" in body


def test_the_registry_entry_is_valid_and_names_this_release(tmp_path):
    import jsonschema

    from vixl import __version__
    from vixl.cli import mcp_parser

    module = load("distribution/mcp_registry.py")
    entry = module.entry()
    # tests/fixtures/mcp-registry/server.schema.json is the registry's published schema (module.SCHEMA).
    schema = json.loads((ROOT / "tests/fixtures/mcp-registry/server.schema.json").read_text(encoding="utf-8"))
    assert schema["$id"] == entry["$schema"] == module.SCHEMA
    jsonschema.validate(entry, schema)
    package, = entry["packages"]
    assert entry["version"] == package["version"] == __version__ == module.source_version()
    assert (package["registryType"], package["identifier"], package["runtimeHint"]) == ("pypi", "vixl-engine", "uvx")
    assert len(entry["description"]) <= 100
    # The registry proves the package belongs to the name by this line in the package's README.
    assert f"mcp-name: {entry['name']}" in README
    assert entry["name"] == "io.github.jxburros/vixl"
    # A registry client runs `uvx vixl-engine==VERSION ARGS…`, so the package needs a script of its own name.
    scripts = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
    assert scripts["vixl-engine"] == scripts["vixl"]
    positional, named = package["packageArguments"]
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    assert positional == {"type": "positional", "value": "mcp"}
    assert mcp_parser().parse_args([named["name"], str(workspace)]).workspace == str(workspace)
    assert module.main(["--version", "1.2.3", "--out", str(tmp_path / "server.json")]) == 0
    written = json.loads((tmp_path / "server.json").read_text(encoding="utf-8"))
    assert written["version"] == written["packages"][0]["version"] == "1.2.3"


def test_optional_publish_jobs_are_off_by_default_and_cannot_block_a_release():
    release = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8"))["jobs"]
    registry = release["mcp-registry"]
    assert registry["continue-on-error"] is True and "pypi" in registry["needs"]
    assert "vars.MCP_REGISTRY_PUBLISH == 'true'" in registry["if"] and "!inputs.dry_run" in registry["if"]
    fetch = next(step["run"] for step in registry["steps"] if "PUBLISHER_URL" in step.get("run", ""))
    assert "sha256sum --check" in fetch and "releases/download/v*" in fetch
    for name, job in release.items():
        needs = job.get("needs") or []
        assert "mcp-registry" not in ([needs] if isinstance(needs, str) else needs), name
    build = [step for step in release["verify"]["steps"]
             if "alias" in str(step.get("run", "")) + str((step.get("with") or {}).get("name", ""))]
    assert len(build) == 2 and all(step["continue-on-error"] is True for step in build)
    assert build[1]["with"]["name"] == "alias-package" and build[1]["with"]["if-no-files-found"] == "ignore"
    # The publish job collects `*distributions`; the meta-package must stay out of the release inventory.
    assert not build[1]["with"]["name"].endswith("distributions")
    assert release["pypi"]["with"]["alias-artifact"] == "alias-package"

    pypi = yaml.safe_load((ROOT / ".github/workflows/pypi.yml").read_text(encoding="utf-8"))
    alias = pypi["jobs"]["alias"]
    assert alias["continue-on-error"] is True and alias["needs"] == "publish"
    assert "vars.PYPI_ALIAS_PUBLISH == 'true'" in alias["if"]
    assert alias["permissions"] == {"id-token": "write"}
    assert "needs" not in pypi["jobs"]["publish"]
    assert pypi["on"]["workflow_call"]["inputs"]["alias-artifact"]["default"] == ""


# ---------------------------------------------------------------- #774: licence clarity


def test_the_readme_top_says_who_can_use_vixl_free_and_links_the_licence():
    top = README.split("\n## ", 1)[0]
    assert "](LICENSE)" in top and "](docs/reference/licensing.md)" in top
    assert "fewer than 100" in top and "1,000,000" in top and "Both conditions must hold" in top
    assert "open source? No" in top
    started = (ROOT / "docs/getting-started.md").read_text(encoding="utf-8")
    assert "fewer than 100" in started.split("\n## ", 1)[0] and "](reference/licensing.md)" in started
    fit = section(started, "Is Vixl a fit?")
    for page in ("reference/licensing.md", "reference/providers.md", "reference/coverage.md",
                 "reference/releases.md", "reference/converting.md"):
        assert f"]({page}" in fit and (ROOT / "docs" / page).is_file(), page
    licensing = (ROOT / "docs/reference/licensing.md").read_text(encoding="utf-8")
    licence = (ROOT / "LICENSE").read_text(encoding="utf-8")
    # The page restates the licence's own thresholds; it must not drift from the text it summarises.
    assert "fewer than 100 total individuals" in licence and "1,000,000 USD (2019)" in licence
    assert "fewer than 100 people" in licensing and "US$1,000,000" in licensing and "2019 dollars" in licensing
    assert "the licence text is what counts" in licensing


def test_agent_bundles_carry_the_licence(tmp_path):
    identifier = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["license"]
    for output in load("distribution/package_extensions.py").build(tmp_path):
        with zipfile.ZipFile(output) as archive:
            assert archive.read("LICENSE") == (ROOT / "LICENSE").read_bytes(), output.name
            if output.suffix == ".mcpb":
                assert json.loads(archive.read("manifest.json"))["license"] == identifier


# ---------------------------------------------------------------- #772: the migration guide's data


def test_the_migration_guide_csv_is_the_file_in_the_docs_folder():
    guide = (ROOT / "docs/guides/automation/template-api-migration.md").read_text(encoding="utf-8")
    block = next(body for lang, body in fenced(guide) if lang == "csv")
    assert block == (ROOT / "docs/guides/automation/products.csv").read_text(encoding="utf-8")
    assert "](products.csv)" in guide
    assert "template-api-migration.md" in (ROOT / "docs/use-cases.md").read_text(encoding="utf-8")
    assert "docs/guides/automation/template-api-migration.md" in section(README, "What you can make")
