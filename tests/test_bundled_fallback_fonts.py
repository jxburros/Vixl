"""Bundled Noto fallback faces draw the Latin, Greek, Cyrillic and symbol characters DejaVu Sans lacks (#419)."""

from pathlib import Path

import pytest

from vixl import Project
from vixl.text import BUNDLED_FALLBACKS, coverage, file_bytes, glyph_coverage

DATA = Path(__file__).resolve().parents[1] / "src" / "vixl" / "data"
# Each character is missing from DejaVu Sans: power symbol, helm, alchemical air, ⟁, ⧉, a Cyrillic letter
# from Extended-C and a Latin letter from Extended-D.
MIXED = "Ελληνικά Кириллица ⏻ ⎈ 🜁 ⟁ ⧉ ᲀ Ꟁ"


def test_dejavu_lacks_the_sample_characters():
    dejavu = coverage(file_bytes(DATA / "DejaVuSans.ttf"))
    assert all(ord(c) not in dejavu for c in MIXED.split(" ", 2)[2].replace(" ", ""))


def test_mixed_script_and_symbol_text_has_no_tofu_offline():
    p = Project(900, 200, "#fff")
    p.apply({"type": "text", "name": "t", "text": MIXED, "size": 40, "color": "black"})
    layer = p.layer("t")
    report = glyph_coverage(p, layer)
    assert report["missing"] == []
    assert not [i for i in p.check()["issues"] if i["check"] == "fonts" and i.get("missing")]


@pytest.mark.parametrize("kind", ["svg", "pdf", "pptx"])
def test_exports_draw_fallback_glyphs(tmp_path, kind):
    p = Project(900, 200, "#fff")
    p.apply({"type": "text", "name": "t", "text": MIXED, "size": 40, "color": "black"})
    p.export(tmp_path / f"t.{kind}")
    if kind == "pdf":
        import pypdfium2

        text = pypdfium2.PdfDocument(str(tmp_path / "t.pdf"))[0].get_textpage().get_text_range()
        assert "⏻" in text and "⧉" in text
    if kind == "pptx":
        import zipfile

        slide = zipfile.ZipFile(tmp_path / "t.pptx").read("ppt/slides/slide1.xml").decode()
        assert 'typeface="Noto Sans Symbols 2"' in slide


def test_bundled_files_and_licence_ship_together():
    total = sum((DATA / name).stat().st_size for name in BUNDLED_FALLBACKS)
    assert total < 6 * 1024 * 1024
    licence = (DATA / "NOTO-LICENSE.txt").read_text(encoding="utf-8")
    assert "SIL OPEN FONT LICENSE Version 1.1" in licence
    assert all(name in licence for name in BUNDLED_FALLBACKS)


# --- #684: scripts the bundled fonts do not draw (CJK, Devanagari, Thai) ---------------------------------------

SCRIPTS = "Café हिन्दी 日本語 中文 ไทย 한국어"


def _font(chars, family):
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from font_helper import make_font

    return make_font(chars, family)


def _fake_fetch(chars, calls=None):
    def fetch(family, weight=400, italic=False, *, client=None, source=None):
        if calls is not None:
            calls.append(family)
        if source is not None:
            source.update(origin="download")
        return _font(chars, family), family

    return fetch


def test_apply_warns_on_uncovered_scripts():
    p = Project(900, 200, "#fff")
    result = p.apply({"type": "text", "name": "t", "text": SCRIPTS, "size": 40, "color": "black"})
    warning = next(w for w in result["warnings"] if "no available font draws" in w)
    for name in ("Devanagari", "Han", "Thai", "Hangul"):
        assert name in warning
    assert "Noto Sans SC" in warning and "Noto Sans Devanagari" in warning and "font-cover" in warning
    assert "font-fallbacks" in warning and "'t'" in warning
    assert sum("no available font draws" in w for w in result["warnings"]) == 1  # one warning per layer
    # Kana with Han asks for the Japanese face, which draws both.
    kana = p.apply({"type": "text", "name": "jp", "text": "ひらがな 日本", "y": 100, "size": 40, "color": "black"})
    warning = next(w for w in kana["warnings"] if "no available font draws" in w)
    assert "Noto Sans JP" in warning and "Noto Sans SC" not in warning


@pytest.mark.parametrize("text", ["Hello, world", "مرحبا بالعالم", "שלום עולם", MIXED])
def test_covered_scripts_apply_without_warning(text):
    result = Project(900, 200, "#fff").apply({"type": "text", "name": "t", "text": text, "size": 40, "color": "black"})
    assert not [w for w in result.get("warnings", []) if "no available font draws" in w]


def test_only_changed_layers_are_warned_about():
    p = Project(900, 300, "#fff")
    p.apply({"type": "text", "name": "t", "text": "中文", "size": 40, "color": "black"})
    result = p.apply({"type": "text", "name": "latin", "text": "Hello", "y": 100, "size": 40, "color": "black"})
    assert not [w for w in result.get("warnings", []) if "no available font draws" in w]


def test_font_cover_registers_fallbacks_and_the_check_passes(tmp_path, monkeypatch):
    from vixl import typefaces

    monkeypatch.setenv("VIXL_FONT_CACHE", str(tmp_path / "cache"))
    calls = []
    monkeypatch.setattr(typefaces, "fetch_font", _fake_fetch(SCRIPTS, calls))
    p = Project(900, 200, "#fff")
    p.apply({"type": "text", "name": "t", "text": SCRIPTS, "size": 40, "color": "black"})
    assert [i for i in p.check()["issues"] if i["check"] == "fonts" and i.get("missing")]
    result = typefaces.cover_fonts(p)
    assert set(result["scripts"]) == {"Devanagari", "Han", "Thai", "Hangul"}
    assert set(calls) == {"Noto Sans Devanagari", "Noto Sans SC", "Noto Sans Thai", "Noto Sans KR"}
    assert len(p.state["font_fallbacks"]) == 4 and result["font_fallbacks"] == p.state["font_fallbacks"]
    assert glyph_coverage(p, p.layer("t"))["missing"] == []
    assert not [i for i in p.check()["issues"] if i["check"] == "fonts" and i.get("missing")]
    # A later edit no longer warns, and covering again adds nothing twice.
    again = p.apply({"type": "text-set", "target": "t", "text": SCRIPTS + " 中"})
    assert not [w for w in again.get("warnings", []) if "no available font draws" in w]
    typefaces.cover_fonts(p, scripts=["thai"])
    assert len(p.state["font_fallbacks"]) == 4


def test_font_cover_keeps_existing_fallbacks(monkeypatch):
    from vixl import typefaces

    monkeypatch.setattr(typefaces, "fetch_font", _fake_fetch("ไทย"))
    p = Project(300, 100, "#fff")
    p.assets["fonts/own.ttf"] = _font("x", "Own")
    p.apply([{"type": "font-register", "name": "own", "asset": "fonts/own.ttf"},
             {"type": "font-fallbacks", "fonts": ["own"]}])
    first = list(p.state["font_fallbacks"])
    typefaces.cover_fonts(p, text="ไทย")
    assert p.state["font_fallbacks"][:1] == first and len(p.state["font_fallbacks"]) == 2


def test_font_cover_offline_refuses_and_names_the_families(tmp_path, monkeypatch):
    import httpx

    from vixl import VixlError, typefaces

    monkeypatch.setenv("VIXL_FONT_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("VIXL_OFFLINE", "1")
    monkeypatch.setattr(httpx.Client, "send", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network used")))
    p = Project(900, 200, "#fff")
    p.apply({"type": "text", "name": "t", "text": "हिन्दी ไทย", "size": 40, "color": "black"})
    before = p.state
    with pytest.raises(VixlError) as caught:
        typefaces.cover_fonts(p)
    assert caught.value.code == "network_disabled"
    assert "Noto Sans Devanagari" in str(caught.value) and "Noto Sans Thai" in str(caught.value)
    assert caught.value.details["families"] == ["Noto Sans Devanagari", "Noto Sans Thai"]
    assert p.state == before and "font_fallbacks" not in p.state  # nothing changed


def test_font_cover_offline_uses_the_font_cache(tmp_path, monkeypatch):
    from vixl import typefaces

    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "noto-sans-thai-400.ttf").write_bytes(_font("ไทย", "Noto Sans Thai"))
    monkeypatch.setenv("VIXL_FONT_CACHE", str(cache))
    monkeypatch.setenv("VIXL_OFFLINE", "1")
    p = Project(300, 100, "#fff")
    p.apply({"type": "text", "name": "t", "text": "ไทย", "size": 40, "color": "black"})
    result = typefaces.cover_fonts(p)
    assert result["installed"] == [{"name": "noto-sans-thai-400", "family": "Noto Sans Thai", "weight": 400,
                                    "origin": "cache"}]
    assert glyph_coverage(p, p.layer("t"))["missing"] == []


def test_font_cover_is_a_session_step_and_a_cli_command(tmp_path, monkeypatch):
    from vixl import steps, typefaces
    from vixl.cli import dispatch

    assert steps.step_type("font_cover") == "font-cover"
    schema = steps.step_schema("font-cover")
    assert {"text", "scripts", "weight"} <= set(schema["properties"])
    monkeypatch.setattr(typefaces, "fetch_font", _fake_fetch("ไทย"))
    path = tmp_path / "doc.vixl"
    p = Project(300, 100, "#fff")
    p.apply({"type": "text", "name": "t", "text": "ไทย", "size": 40, "color": "black"})
    p.save(path)
    dispatch(["--project", str(path), "font", "cover", "--script", "Thai"])
    assert len(Project.load(path).state["font_fallbacks"]) == 1


def test_unknown_script_is_rejected():
    from vixl import VixlError, typefaces

    with pytest.raises(VixlError, match="Unknown script"):
        typefaces.cover_fonts(Project(10, 10), scripts=["klingon"])
