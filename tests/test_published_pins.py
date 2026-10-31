"""The install pins name the newest published release, never the unpublished source version (#762)."""

import importlib.util
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def pins():
    spec = importlib.util.spec_from_file_location("published_pins", ROOT / "scripts/published_pins.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def copy(tmp_path):
    for name in {"src/vixl/__init__.py", pins().RECORD, *(name for name, _ in pins().PINS)}:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / name, tmp_path / name)
    return tmp_path


def test_every_install_pin_follows_the_published_record():
    module = pins()
    assert module.problems() == []
    assert all(versions for _, _, versions in module.found())
    assert module.key(module.published()) <= module.key(module.source())


def test_set_rewrites_every_pin_and_refuses_a_version_ahead_of_the_source(tmp_path):
    module = pins()
    root = copy(tmp_path)
    module.set_version("0.1.0", root)
    assert module.published(root) == "0.1.0" and module.problems(root) == []
    assert {pin for _, _, versions in module.found(root) for pin in versions} == {"0.1.0"}
    assert '"vixl-engine==0.1.0"' in (root / ".mcp.json").read_text(encoding="utf-8")
    assert "jxburros/Vixl@v0.1.0" in (root / "docs/guides/automation/ci.md").read_text(encoding="utf-8")
    major, minor, patch = module.key(module.source())
    try:
        module.set_version(f"{major}.{minor}.{patch + 1}", root)
    except SystemExit as refused:
        assert "ahead of the source version" in str(refused)
    else:
        raise AssertionError("a version ahead of the source was recorded")


def test_a_pin_left_on_another_version_is_reported(tmp_path):
    module = pins()
    root = copy(tmp_path)
    readme = root / "README.md"
    published = module.published(root)
    readme.write_text(readme.read_text(encoding="utf-8").replace(f"vixl-engine=={published} ", "vixl-engine==9.9.9 "),
                      encoding="utf-8")
    assert module.problems(root) == [f"README.md: pins 9.9.9, but {module.RECORD} names {published}"]
    assert module.main(["--root", str(root)]) == 1
