"""Vixl runs without the VixlExamples repository: the engine never names it, and downloads go to VixlPacks."""

from pathlib import Path

from vixl import packs

SRC = Path(__file__).resolve().parents[1] / "src" / "vixl"


def test_the_engine_does_not_reference_the_examples_repository():
    offenders = [str(path.relative_to(SRC)) for path in SRC.rglob("*")
                 if path.is_file() and path.suffix in {".py", ".json", ".md", ".txt", ".toml", ".html"}
                 and "VixlExamples" in path.read_text(encoding="utf-8", errors="ignore")]
    assert not offenders, f"the engine must not depend on VixlExamples: {offenders}"


def test_every_pack_is_pinned_in_the_packs_repository():
    assert packs.REPOSITORY == "https://raw.githubusercontent.com/jxburros/VixlPacks"
    for name, spec in packs.PACKS.items():
        assert len(spec["commit"]) == 40 and len(spec["sha256"]) == 64, name
        assert packs.url(name).startswith(f"{packs.REPOSITORY}/{spec['commit']}/"), name
