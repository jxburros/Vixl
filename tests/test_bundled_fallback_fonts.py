"""Noto Sans is the proofing face, with DejaVu Sans and the Noto symbol and math faces behind it; scripts the bundled
faces lack draw from a face already on the machine, else the apply warns and names the font-cover step (#419, #684).

``fixtures/fonts/cjk-test.ttf`` is a synthesized stand-in for a CJK face (``font_helper.make_font``: a filled box for
each of a few Han, kana and Hangul characters), built offline so no CJK font has to ship or download."""

from pathlib import Path

import pytest

from vixl import Project
from vixl.text import BUNDLED_FONTS, coverage, file_bytes, glyph_coverage

DATA = Path(__file__).resolve().parents[1] / "src" / "vixl" / "data"
CJK_FIXTURE = Path(__file__).parent / "fixtures" / "fonts" / "cjk-test.ttf"


@pytest.fixture(autouse=True)
def _no_machine_faces(tmp_path, monkeypatch):
    """A face a developer's font cache happens to hold must not change what these tests see."""
    monkeypatch.setenv("VIXL_FONT_CACHE", str(tmp_path / "empty-cache"))
    monkeypatch.delenv("VIXL_CJK_PACK", raising=False)
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
    total = sum((DATA / name).stat().st_size for name in BUNDLED_FONTS)
    assert total < 6 * 1024 * 1024
    licence = (DATA / "NOTO-LICENSE.txt").read_text(encoding="utf-8")
    assert "SIL OPEN FONT LICENSE Version 1.1" in licence
    noto = [name for name in BUNDLED_FONTS if name.startswith("Noto")]
    assert len(noto) == 4 and all(name in licence for name in noto)
    assert "DejaVuSans.ttf" in BUNDLED_FONTS and "DejaVu" in (DATA / "FONT-LICENSE.txt").read_text(encoding="utf-8")


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


def test_font_cover_again_with_new_bytes_replaces_the_fallback(tmp_path, monkeypatch):
    from vixl import typefaces

    monkeypatch.setenv("VIXL_FONT_CACHE", str(tmp_path / "cache"))
    builds = []

    def fetch(family, weight=400, italic=False, *, client=None, source=None):
        builds.append(family)
        return _font(SCRIPTS, f"{family} build {len(builds)}"), family

    monkeypatch.setattr(typefaces, "fetch_font", fetch)
    p = Project(900, 200, "#fff")
    p.apply({"type": "text", "name": "t", "text": "ภาษาไทย", "size": 40, "color": "black"})
    first = typefaces.cover_fonts(p, scripts=["thai"])["font_fallbacks"]
    second = typefaces.cover_fonts(p, scripts=["thai"])["font_fallbacks"]
    assert len(builds) == 2 and len(first) == len(second) == 1 and first != second
    assert second == [p.state["fonts"]["noto-sans-thai-400"]]


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


# --- #419: Noto Sans is the proofing face; DejaVu Sans stays bundled and nameable ----------------------------------


def test_the_proofing_face_is_noto_sans():
    from vixl.text import PROOFING_FONT, font_style, primary_font_data

    p = Project(400, 100, "#fff")
    p.apply({"type": "text", "name": "t", "text": "Proof", "size": 30, "color": "black"})
    assert p.layer("t")["font"] == PROOFING_FONT == "NotoSans-Regular.ttf" == BUNDLED_FONTS[0]
    assert font_style(primary_font_data(p, p.layer("t")))[0] == "Noto Sans"
    assert [i for i in p.check()["issues"] if i["check"] == "fonts" and "proofing only" in i["message"]]


def test_dejavu_sans_stays_behind_noto_and_can_be_named():
    from vixl.text import font_data, font_style

    p = Project(600, 200, "#fff")
    # Arabic is a script Noto Sans lacks and DejaVu Sans draws.
    p.apply([{"type": "text", "name": "mixed", "text": "Hello مرحبا", "size": 30, "color": "black"},
             {"type": "text", "name": "old", "text": "Proof", "font": "DejaVuSans.ttf", "size": 30, "y": 100,
              "color": "black"}])
    chain = [font_style(data)[0] for data in font_data(p, p.layer("mixed"))]
    assert chain[:2] == ["Noto Sans", "DejaVu Sans"] and glyph_coverage(p, p.layer("mixed"))["missing"] == []
    assert font_style(font_data(p, p.layer("old")))[0] == "DejaVu Sans"
    flagged = next(i for i in p.check()["issues"] if i["check"] == "fonts" and "proofing only" in i["message"])
    assert set(flagged["layers"]) == {"mixed", "old"}  # a saved document's DejaVu text is still the proofing face


def test_dejavu_sans_can_be_registered_as_the_body_face():
    p = Project(600, 200, "#fff")
    p.apply({"type": "font-register", "name": "dejavu", "asset": "DejaVuSans.ttf", "role": "body"})
    asset = p.state["fonts"]["dejavu"]
    assert asset.startswith("fonts/") and p.assets[asset] == (DATA / "DejaVuSans.ttf").read_bytes()
    p.apply({"type": "text", "name": "t", "text": "Body copy", "size": 16, "color": "black"})
    assert p.layer("t")["font"] == asset


# --- #419: CJK, Devanagari and Thai from a face already on this machine -----------------------------------------


def _no_network(monkeypatch):
    import httpx

    monkeypatch.setattr(httpx.Client, "send", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network used")))


def _ink_height(project):
    import numpy as np

    rows = np.where((np.asarray(project.render().convert("L")) < 128).any(axis=1))[0]
    return int(rows.max() - rows.min() + 1) if len(rows) else 0


def _cache_with(tmp_path, monkeypatch, name):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / name).write_bytes(CJK_FIXTURE.read_bytes())
    monkeypatch.setenv("VIXL_FONT_CACHE", str(cache))
    return cache


def test_cjk_draws_from_a_cached_face_without_registering_it(tmp_path, monkeypatch):
    _no_network(monkeypatch)
    text = "中文字"
    empty = Project(400, 100, "#fff")
    first = empty.apply({"type": "text", "name": "t", "text": text, "size": 40, "color": "black"})
    assert glyph_coverage(empty, empty.layer("t"))["missing"] == sorted(text)
    assert any("no available font draws" in w for w in first["warnings"])
    tofu = _ink_height(empty)
    _cache_with(tmp_path, monkeypatch, "noto-sans-sc-400.ttf")
    p = Project(400, 100, "#fff")
    result = p.apply({"type": "text", "name": "t", "text": text, "size": 40, "color": "black"})
    report = glyph_coverage(p, p.layer("t"))
    assert report["missing"] == [] and report["local"] == sorted(text) and report["local_fonts"] == ["Vixl CJK Test"]
    assert "font_fallbacks" not in p.state and not [name for name in p.assets if name.startswith("fonts/")]
    # Drawn: the stand-in face draws each character as a thin bar, where a missing glyph is a tall empty box.
    assert tofu > 20 and 0 < _ink_height(p) < 8
    warning = next(w for w in result["warnings"] if "does not embed" in w)
    assert "Vixl CJK Test" in warning and '{"type": "font-cover", "scripts": ["Han"]}' in warning
    assert "vixl font cover --script Han" in warning
    issue = next(i for i in p.check()["issues"] if i["check"] == "fonts" and i.get("local"))
    assert issue["severity"] == "warning" and "font-cover" in issue["message"]


def test_font_cover_embeds_the_cached_face_offline(tmp_path, monkeypatch):
    from vixl import typefaces

    _no_network(monkeypatch)
    _cache_with(tmp_path, monkeypatch, "noto-sans-sc-400.ttf")
    monkeypatch.setenv("VIXL_OFFLINE", "1")
    p = Project(400, 100, "#fff")
    p.apply({"type": "text", "name": "t", "text": "中文", "size": 40, "color": "black"})
    result = typefaces.cover_fonts(p)
    assert [item["origin"] for item in result["installed"]] == ["cache"] and len(p.state["font_fallbacks"]) == 1
    report = glyph_coverage(p, p.layer("t"))
    assert report["missing"] == [] and "local" not in report  # the document draws it itself now
    assert not [i for i in p.check()["issues"] if i["check"] == "fonts" and (i.get("local") or i.get("missing"))]


def test_a_japanese_face_in_the_cache_serves_han_text(tmp_path, monkeypatch):
    _cache_with(tmp_path, monkeypatch, "noto-sans-jp-400.ttf")
    p = Project(400, 100, "#fff")
    p.apply({"type": "text", "name": "t", "text": "汉字", "size": 40, "color": "black"})
    assert glyph_coverage(p, p.layer("t"))["missing"] == []


@pytest.mark.parametrize("packed", [False, True])
def test_the_cjk_pack_override_is_a_font_file_or_a_zip(tmp_path, monkeypatch, packed):
    import zipfile

    _no_network(monkeypatch)
    if packed:
        source = tmp_path / "cjk.zip"
        with zipfile.ZipFile(source, "w") as archive:
            archive.writestr("fonts/noto-sans-kr-400.ttf", CJK_FIXTURE.read_bytes())
            archive.writestr("README.txt", "not a font")
    else:
        source = tmp_path / "MyCJK.ttf"
        source.write_bytes(CJK_FIXTURE.read_bytes())
    monkeypatch.setenv("VIXL_CJK_PACK", str(source))
    p = Project(400, 100, "#fff")
    result = p.apply({"type": "text", "name": "t", "text": "한국어", "size": 40, "color": "black"})
    assert glyph_coverage(p, p.layer("t"))["missing"] == []
    assert any("does not embed" in w for w in result["warnings"])


def test_a_missing_pack_file_or_a_broken_cached_face_leaves_the_warning(tmp_path, monkeypatch):
    from vixl import packs

    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "noto-sans-thai-400.ttf").write_bytes(b"not a font")
    monkeypatch.setenv("VIXL_FONT_CACHE", str(cache))
    monkeypatch.setenv("VIXL_CJK_PACK", str(tmp_path / "missing.zip"))
    assert packs.local("cjk") is None
    p = Project(400, 100, "#fff")
    result = p.apply({"type": "text", "name": "t", "text": "ไทย", "size": 40, "color": "black"})
    warning = next(w for w in result["warnings"] if "no available font draws" in w)
    assert '{"type": "font-cover", "scripts": ["Thai"]}' in warning and "vixl font cover --script Thai" in warning
    assert "VIXL_CJK_PACK" in warning
    error = next(i for i in p.check()["issues"] if i["check"] == "fonts" and i.get("missing"))
    assert "font-cover" in error["message"]


@pytest.mark.parametrize("kind", ["pdf", "svg", "pptx"])
def test_exports_draw_the_cached_face(tmp_path, monkeypatch, kind):
    _cache_with(tmp_path, monkeypatch, "noto-sans-sc-400.ttf")
    p = Project(400, 100, "#fff")
    p.apply({"type": "text", "name": "t", "text": "Hi 中文", "size": 40, "color": "black"})
    p.export(tmp_path / f"t.{kind}")
    if kind == "pdf":
        import pypdfium2

        assert "中文" in pypdfium2.PdfDocument(str(tmp_path / "t.pdf"))[0].get_textpage().get_text_range()
    elif kind == "svg":
        assert (tmp_path / "t.svg").read_text().count("<path") >= 4
    else:
        import zipfile

        slide = zipfile.ZipFile(tmp_path / "t.pptx").read("ppt/slides/slide1.xml").decode()
        assert 'typeface="Vixl CJK Test"' in slide
