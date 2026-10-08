"""Unicode coverage, rendering parity, portable customization and destination pack behavior."""

import base64
from copy import deepcopy
import io
import json
from pathlib import Path
import re
import zipfile

import numpy as np
from PIL import Image
import pytest
import resvg_py

from vixl import Project, VixlError
from vixl import emojis
from vixl.emoji_workflows import dispatch
from vixl.interfaces import Session
from vixl.model import Limits
from vixl.text import clusters, font_data, glyph_coverage, lines, shape


def text_document(text="Hello 😀 👋🏽 🧑‍🚀 🇬🇧", rich=False):
    p = Project(600, 140, background="white")
    p.apply(
        {"type": "rich-text", "markdown": text, "name": "t", "size": 40, "color": "#23364D"}
        if rich
        else {"type": "text", "text": text, "name": "t", "size": 40, "color": "#23364D"}
    )
    return p


def replacement(color="red"):
    p = Project(72, 72, background="transparent")
    p.apply({"type": "shape", "shape": "ellipse", "width": 40, "height": 40, "x": 16, "y": 16, "fill": color})
    image = io.BytesIO()
    p.render().save(image, format="PNG")
    return {
        "type": "emoji-set",
        "emoji": "😀",
        "format": "png",
        "data": base64.b64encode(image.getvalue()).decode(),
    }


def svg_pixels(p):
    return Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=p.export(format="SVG").decode()))).convert(
        "RGBA"
    )


def test_complete_stable_unicode_catalog_includes_every_qualified_sequence_and_component(monkeypatch):
    # Exercise Windows' default text encoding on every CI platform.
    native_open = Path.open

    def windows_locale_open(path, mode="r", buffering=-1, encoding=None, errors=None, newline=None):
        if "b" not in mode and encoding is None:
            encoding = "cp1252"
        return native_open(path, mode, buffering, encoding, errors, newline)

    monkeypatch.setattr(Path, "open", windows_locale_open)
    data = emojis._catalog()
    expected = []
    for line in (emojis.DATA / "emoji-test.txt").read_text(encoding="utf-8").splitlines():
        m = re.match(r"([0-9A-F ]+)\s*;\s*(fully-qualified|component)\s*#", line)
        if m:
            expected.append("-".join(m[1].split()))
    assert data["unicode_version"] == "17.0"
    unicode_entries = {key for key in emojis._entries() if not key.startswith(":")}
    assert set(expected) == unicode_entries and len(expected) == 3953
    assert data["unicode_count"] == 3953 and data["original_count"] == 100
    assert data["original_groups"] == {"VIXL Reactions": 44, "VIXL Faces": 24, "VIXL Everyday": 32}
    with zipfile.ZipFile(emojis.DATA / "artwork.zip") as z:
        for e in data["entries"]:
            assert emojis.scan(e["emoji"]) == [(0, len(e["emoji"]), e["id"])]
            assert len(z.read("svg/" + e["id"] + ".svg")) > 100
            assert len(z.read("vixl/" + e["id"] + ".vixl")) > 100


@pytest.mark.parametrize("rich", [False, True])
def test_bundled_reactions_render_without_registration_and_can_be_replaced_and_reset(rich):
    p = text_document(":approved: :thinking: :support: :in_progress:", rich)
    original = p.render().tobytes()
    data = font_data(p, p.layer("t"))
    assert emojis.is_glyph(shape(data, ":approved:", 40)[0][0].data)
    p.apply({"type": "emoji-mode", "mode": "font"})
    assert emojis.is_glyph(shape(font_data(p, p.layer("t")), ":approved:", 40)[0][0].data)
    assert not glyph_coverage(p, p.layer("t"))["missing"]
    p.apply({**replacement(), "emoji": ":approved:"})
    assert p.render().tobytes() != original
    assert emojis.select(project=p).count(":approved:") == 1
    rows = emojis.catalog(query="Approved", project=p)["entries"]
    assert len([e for e in rows if e["id"] == ":approved:"]) == 1
    p.apply({"type": "emoji-reset", "emoji": ":approved:"})
    assert p.render().tobytes() == original


def test_reaction_export_preserves_original_provenance_and_pack_roundtrip(tmp_path):
    output = tmp_path / "reactions.zip"
    keys = [key for key in emojis._entries() if key.startswith(":")]
    emojis.export_pack(output, keys, destination="discord")
    with zipfile.ZipFile(output) as z:
        entries = json.loads(z.read("manifest.json"))["entries"]
        assert len(entries) == 100
        for e in entries:
            assert e["source_origin"] == emojis._entries()[e["id"]]["source"]
            assert e["author"] == "VIXL contributors"
            assert e["license"] == "CC-BY-SA-4.0"
            assert e["unicode_sequence"] is None and e["codepoints"] == []
            assert e["kind"] == "original" and e["shortcodes"] == [e["id"]]
            master = emojis.load_master(z.read(e["source"]), Limits())
            assert master.state["emoji_artwork"]["style"] == "VIXL Line 2"
            assert master.render().getchannel("A").getbbox()
    p = text_document(":approved: :celebrate: :available:")
    before = p.render().tobytes()
    emojis.install_pack(p, output.read_bytes())
    assert p.render().tobytes() == before
    assert len(emojis.select(project=p)) == 4053
    repack = tmp_path / "repacked.zip"
    emojis.export_pack(repack, keys, destination="discord", project=p)
    with zipfile.ZipFile(repack) as z:
        again = json.loads(z.read("manifest.json"))["entries"]
        assert [(e["source_origin"], e["author"]) for e in again] == [
            (e["source_origin"], e["author"]) for e in entries
        ]


@pytest.mark.parametrize("value", [":skeptical:", ":high_five:", ":coffee_time:"])
def test_original_categories_have_one_glyph_cluster_and_searchable_names(value):
    p = text_document(value)
    data = font_data(p, p.layer("t"))
    assert len(shape(data, value, 40)[0]) == 1
    assert lines(data, value * 3, 40, 45) == [value] * 3
    entry = emojis._entries()[value]
    found = emojis.catalog(query=entry["name"], group=entry["group"])["entries"]
    assert any(e["id"] == value for e in found)


@pytest.mark.parametrize("value", ["☕", "©️", "®️", "🔡", "🇭🇰", "📿", "🫶", "🫦"])
def test_editable_masters_preserve_fill_holes_inherited_fill_and_dotted_strokes(value):
    key = emojis.identifier(value)
    master = emojis.load_master(emojis.bundled(key, "vixl"), Limits())
    actual = master.render().convert("RGBA")
    expected = Image.open(io.BytesIO(emojis.png(emojis.bundled(key), 72))).convert("RGBA")
    assert actual.getchannel("A").getbbox()
    a, b = [np.asarray(image).astype(float) for image in (actual, expected)]
    # Compare visible color, excluding RGB in transparent pixels.
    for pixels in (a, b):
        pixels[:, :, :3] *= pixels[:, :, 3:4] / 255
    assert np.abs(a - b).mean() < 3


@pytest.mark.parametrize(
    "value",
    [
        "👩🏿‍🚀",
        "👨‍👩‍👧‍👦",
        "🏳️‍🌈",
        "🇺🇸",
        "1️⃣",
        "🏴\U000e0067\U000e0062\U000e0073\U000e0063\U000e0074\U000e007f",
    ],
)
def test_longest_match_sequences_remain_one_glyph_and_one_wrapping_cluster(value):
    p = text_document(value)
    data = font_data(p, p.layer("t"))
    glyphs, width = shape(data, value, 40)
    assert len(glyphs) == 1 and width == 40 and glyphs[0].text == value
    assert clusters(data, value) == [value]
    assert lines(data, value * 3, 40, 45) == [value] * 3
    assert glyph_coverage(p, p.layer("t"))["missing"] == []


def test_qualification_variants_vs15_digits_and_adjacent_sequences():
    assert emojis.identifier("❤") == emojis.identifier("❤️")
    assert emojis.scan("❤\ufe0e") == []
    assert emojis.scan("123 # *") == []
    assert len(emojis.scan("👋🏽👋😀🇫🇷")) == 4


@pytest.mark.parametrize("rich", [False, True])
def test_default_artwork_matches_vector_svg_with_normal_text_and_rtl(rich):
    p = text_document("Hi 😀 العربية 🧑🏽‍🚀 שלום 🇬🇧", rich)
    actual = np.asarray(p.render()).astype(float)
    exported = np.asarray(svg_pixels(p)).astype(float)
    assert np.abs(actual - exported).mean() < 0.25
    assert not glyph_coverage(p, p.layer("t"))["missing"]
    svg = p.export(format="SVG").decode()
    assert "#23364D" in svg and "matrix" in svg
    # These symbols also exist in DejaVu: default rendering still uses our colorful artwork.
    assert emojis.is_glyph(shape(font_data(p, p.layer("t")), "😀", 40)[0][0].data)


def test_font_preference_keeps_supported_font_glyphs_and_falls_back_for_missing_sequences():
    p = text_document("😀 🧑🏽‍🚀")
    p.apply({"type": "emoji-mode", "mode": "font"})
    data = font_data(p, p.layer("t"))
    assert not emojis.is_glyph(shape(data, "😀", 40)[0][0].data)
    assert emojis.is_glyph(shape(data, "🧑🏽‍🚀", 40)[0][0].data)
    p.apply(replacement())
    assert emojis.is_glyph(shape(font_data(p, p.layer("t")), "😀", 40)[0][0].data)


def test_font_preference_falls_back_when_font_format_cannot_be_rendered(monkeypatch):
    from vixl import text

    p = text_document("😀")
    data = font_data(p, p.layer("t"))[0]

    def unsupported(data):
        raise text.UnsupportedText("unsupported color font")

    monkeypatch.setattr(text, "face", unsupported)
    assert not emojis.font_supports((data,), "😀")


def test_replacement_cache_invalidation_undo_save_reload_and_custom_shortcode(tmp_path):
    p = text_document("😀 :my_emoji:")
    initial = p.render().tobytes()
    p.apply(replacement("red"))
    red = p.render().tobytes()
    assert red != initial
    p.apply(replacement("blue"))
    assert p.render().tobytes() != red
    p.undo()
    assert p.render().tobytes() == red
    p.apply({**replacement("green"), "emoji": ":my_emoji:"})
    assert len(emojis.scan(p.layer("t")["text"], p.state["emojis"]["overrides"])) == 2
    path = tmp_path / "portable.vixl"
    p.save(path)
    q = Project.load(path)
    assert q.render().tobytes() == p.render().tobytes()
    assert emojis.artwork(q, ":my_emoji:") == emojis.artwork(p, ":my_emoji:")
    q.apply({"type": "emoji-reset", "emoji": "😀"})
    assert "1F600" not in q.state["emojis"]["overrides"]
    assert ":my_emoji:" in q.state["emojis"]["overrides"]


@pytest.mark.parametrize("format", ["PDF", "PPTX"])
@pytest.mark.parametrize("rich", [False, True])
def test_pdf_and_pptx_preserve_emoji_appearance_and_report_raster_fallback(format, rich):
    p = text_document(rich=rich)
    report = {}
    out = p.export(format=format, report=report)
    assert len(out) > 1000 and report["raster_fallbacks"]
    assert "emoji" in json.dumps(report).lower()


@pytest.mark.parametrize("destination", ["images", "discord", "slack"])
def test_export_install_roundtrip_contains_sources_names_license_and_uploadable_png(tmp_path, destination):
    p = text_document("😀 :my_emoji:")
    p.apply({**replacement("green"), "emoji": ":my_emoji:"})
    path = tmp_path / "pack.zip"
    emojis.export_pack(path, ["😀", "👋🏽", ":my_emoji:"], destination, project=p)
    with zipfile.ZipFile(path) as z:
        manifest = json.loads(z.read("manifest.json"))
        assert "index.html" in z.namelist() and "LICENSE.txt" in z.namelist()
        assert manifest["entries"][0]["source"].endswith(".vixl")
        assert len({e["name"] for e in manifest["entries"]}) == 3
        assert [e["unicode_sequence"] for e in manifest["entries"]] == ["😀", "👋🏽", None]
        assert manifest["entries"][2]["shortcodes"] == [":my_emoji:"]
        for e in manifest["entries"]:
            assert "".join(chr(int(codepoint, 16)) for codepoint in e["codepoints"]) == (
                e["unicode_sequence"] or ""
            )
            assert re.fullmatch(emojis.DESTINATIONS[destination]["name_pattern"], e["name"])
            image = Image.open(io.BytesIO(z.read(e["image"])))
            assert image.size == (128, 128) and image.mode == "RGBA"
    q = text_document("😀 :my_emoji:")
    emojis.install_pack(q, path.read_bytes())
    assert len(q.state["emojis"]["overrides"]) == 3
    assert q.render().tobytes() == p.render().tobytes()
    q.undo()
    assert not q.state.get("emojis", {}).get("overrides")
    assert emojis.requirements(destination, ["😀", "👋🏽"], p)["passed"]
    with pytest.raises(VixlError, match="already exists"):
        emojis.export_pack(path, ["😀"])


def test_builtin_master_is_editable_with_vector_layers_and_retains_license(tmp_path):
    p = emojis.load_master(emojis.bundled("1F600", "vixl"), Limits())
    assert len(p.state["layers"]) > 4 and all(layer["type"] == "shape" for layer in p.state["layers"])
    path = tmp_path / "edited.vixl"
    p.apply({"type": "move", "target": p.state["layers"][0]["id"], "x": 2})
    p.save(path)
    q = text_document()
    q.apply(
        {
            "type": "emoji-set",
            "emoji": "😀",
            "format": "vixl",
            "data": base64.b64encode(path.read_bytes()).decode(),
        }
    )
    assert q.state["emojis"]["overrides"]["1F600"]["license"] == "CC-BY-SA-4.0"
    assert emojis.artwork(q, "1F600", "vixl") == path.read_bytes()


@pytest.mark.parametrize("kind", ["blank", "face", "symbol", "sheet"])
def test_templates_are_editable_transparent_and_have_creation_help(kind):
    p = emojis.template(kind)
    assert p.state["canvas"]["background"] == "transparent"
    assert p.state["emoji_template"]["safe_margin"] == 8
    assert p.state["emoji_template"]["help"]
    p.render()


def test_bad_pack_is_atomic_and_does_not_extract_paths(tmp_path):
    p = text_document()
    before = deepcopy(p.state)
    assets = dict(p.assets)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("../../evil.png", base64.b64decode(replacement()["data"]))
        z.writestr(
            "manifest.json",
            json.dumps(
                {
                    "version": 1,
                    "entries": [
                        {"id": "😀", "image": "../../evil.png"},
                        {"id": "🧑‍🚀", "image": "missing.png"},
                    ],
                }
            ),
        )
    with pytest.raises(VixlError):
        emojis.install_pack(p, buf.getvalue())
    assert p.state == before and p.assets == assets
    assert not (tmp_path.parent / "evil.png").exists()


def test_workflows_respect_workspace_and_support_catalog_without_a_document(tmp_path):
    session = Session(workspace=tmp_path)
    assert dispatch(session, "emoji-list", {"query": "rocket"})["total"] > 0
    dispatch(session, "emoji-template", {"kind": "face", "output": "face.vixl"})
    dispatch(session, "emoji-get", {"emoji": "😀", "output": "smile.vixl"})
    assert Project.load(tmp_path / "face.vixl").state["layers"]
    with pytest.raises(VixlError):
        dispatch(session, "emoji-get", {"emoji": "😀", "output": "../escape.vixl"})
    with pytest.raises(VixlError):
        dispatch(session, "emoji-export", {"output": "pack.zip", "sources": "no"})
    session = Session(tmp_path / "face.vixl", workspace=tmp_path)
    dispatch(session, "emoji-replace", {"emoji": ":wave:", "source": "smile.vixl"})
    assert ":wave:" in Project.load(tmp_path / "face.vixl").state["emojis"]["overrides"]
    dispatch(
        session, "emoji-export", {"output": "discord.zip", "destination": "discord", "emojis": [":wave:"]}
    )
