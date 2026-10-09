from pathlib import Path
import tomllib


def test_source_distribution_includes_only_package_sources_and_metadata():
    root = Path(__file__).resolve().parent.parent
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    includes = config["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
    assert set(includes) == {"/src/vixl", "/pyproject.toml", "/README.md", "/LICENSE"}
    assert all((root / path.lstrip("/")).exists() for path in includes)
