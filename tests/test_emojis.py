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
from vixl.emoji_workflows import dispatch, fields as emoji_fields
from vixl.interfaces import Session
from vixl.model import Limits
from vixl.text import clusters, font_data, glyph_coverage, lines, shape

# Most tests here draw or export the artwork (the emojis content pack; see tests/conftest.py).
pytestmark = pytest.mark.emoji_pack


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
        if "b" not in mode and encoding in (None, "locale"):
            encoding = "cp1252"
        return native_open(path, mode, buffering, encoding, errors, newline)

    monkeypatch.setattr(Path, "open", windows_locale_open)
    with pytest.raises(UnicodeDecodeError):
        (emojis.DATA / "emoji-test.txt").read_text()
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
    with zipfile.ZipFile(emojis.archive_path()) as z:
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


def animated_master(tmp_path, size=72, duration=1000, fps=20, effect=False):
    m = Project(size, size, background="transparent")
    m.apply(
        [
            {
                "type": "shape",
                "shape": "ellipse",
                "name": "dot",
                "width": size * 0.5,
                "height": size * 0.5,
                "x": size * 0.1,
                "y": size * 0.25,
                "fill": "#DC7366",
            },
            {"type": "timeline-set", "duration": duration, "fps": fps, "loop": 1},
            {"type": "keyframe", "target": "dot", "property": "x", "time": 0, "value": size * 0.1},
            {"type": "keyframe", "target": "dot", "property": "x", "time": duration / 2, "value": size * 0.4},
            {"type": "keyframe", "target": "dot", "property": "x", "time": duration, "value": size * 0.1},
        ]
    )
    if effect:
        m.apply({"type": "blur", "target": "dot", "value": 2})
    path = tmp_path / "master.vixl"
    m.save(path, overwrite=True)
    return {"type": "emoji-set", "format": "vixl", "data": base64.b64encode(path.read_bytes()).decode()}


def animated_document(tmp_path, names=("wave", "bounce", "spin"), **options):
    p = text_document("animated")
    master = animated_master(tmp_path, **options)
    p.apply([{**master, "emoji": f":{name}:"} for name in names])
    return p, [f":{name}:" for name in names]


def pack(path):
    with zipfile.ZipFile(path) as z:
        return {name: z.read(name) for name in z.namelist()}, json.loads(z.read("manifest.json"))


def test_every_platform_profile_states_its_source_and_the_day_it_was_checked():
    assert {"whatsapp", "telegram", "telegram-emoji", "telegram-animated", "twitch", "imessage"} <= set(
        emojis.DESTINATIONS
    )
    for name, profile in emojis.DESTINATIONS.items():
        assert re.fullmatch(profile["name_pattern"], "ok") and profile["instructions"]
        if name != "images":
            assert profile["url"].startswith("https://") and re.fullmatch(
                r"\d{4}-\d\d-\d\d", profile["checked"]
            )
            assert profile["max_bytes"] and "KiB" not in profile["instructions"]


@pytest.mark.parametrize(
    "destination, folders, format",
    [
        ("whatsapp", {"stickers": 512}, "WEBP"),
        ("telegram", {"stickers": 512}, "PNG"),
        ("telegram-emoji", {"emoji": 100}, "PNG"),
        ("twitch", {"28": 28, "56": 56, "112": 112}, "PNG"),
        ("imessage", {"stickers": 408}, "PNG"),
    ],
)
def test_sticker_and_emote_destinations_write_files_that_pass_their_own_rules(
    tmp_path, destination, folders, format
):
    p = text_document("😀 :my_emoji:")
    p.apply({**replacement("green"), "emoji": ":my_emoji:"})
    selection = ["😀", "👋🏽", ":my_emoji:"]
    result = emojis.export_pack(tmp_path / "pack.zip", selection, destination, project=p)
    profile = emojis.DESTINATIONS[destination]
    files, manifest = pack(tmp_path / "pack.zip")
    assert manifest["destination"] == destination and manifest["animated"] is False
    assert result["instructions"].startswith(profile["instructions"])
    for entry in manifest["entries"]:
        assert re.fullmatch(profile["name_pattern"], entry["name"])
        for folder, size in folders.items():
            raw = files[f"{folder}/{entry['name']}.{format.lower()}"]
            image = Image.open(io.BytesIO(raw))
            assert image.format == format and image.size == (size, size) and len(raw) < profile["max_bytes"]
            assert image.convert("RGBA").getpixel((0, 0))[3] == 0
        assert entry["image"] in files and entry["svg"] in files
    report = emojis.requirements(destination, selection, p)
    assert report["passed"] and report["checked"] == profile["checked"]
    assert [e["name"] for e in report["entries"]] == [e["name"] for e in manifest["entries"]]
    # A pack whose images are WebP still installs, from its editable sources or SVG appearances.
    q = text_document("😀 :my_emoji:")
    emojis.install_pack(q, (tmp_path / "pack.zip").read_bytes())
    assert q.render().tobytes() == p.render().tobytes()


def test_whatsapp_pack_has_tray_icon_contents_and_pack_size_rules(tmp_path):
    p = text_document(":my_emoji:")
    p.apply({**replacement("green"), "emoji": ":my_emoji:"})
    result = emojis.export_pack(tmp_path / "wa.zip", ["😀", "👋🏽", ":my_emoji:"], "whatsapp", project=p)
    files, manifest = pack(tmp_path / "wa.zip")
    tray = Image.open(io.BytesIO(files["tray.png"]))
    assert tray.format == "PNG" and tray.size == (96, 96) and len(files["tray.png"]) < 50_000
    contents = json.loads(files["contents.json"])["sticker_packs"][0]
    assert contents["tray_image_file"] == "tray.png" and contents["animated_sticker_pack"] is False
    assert [s["emojis"] for s in contents["stickers"]] == [["😀"], ["👋🏽"], []]
    assert all(f"stickers/{s['image_file']}" in files for s in contents["stickers"])
    # A custom sticker has no Unicode emoji to tag it with; the pack says so instead of inventing one.
    assert result["untagged"] == ["my_emoji"] and "my_emoji" in files["README.txt"].decode()
    with pytest.raises(VixlError, match="3–30"):
        emojis.export_pack(tmp_path / "small.zip", ["😀", "👋🏽"], "whatsapp")
    assert not (tmp_path / "small.zip").exists()
    report = emojis.requirements("whatsapp", ["😀", "👋🏽"])
    assert not report["passed"] and "3–30" in report["findings"][0]


def test_twitch_names_are_alphanumeric_and_imessage_takes_only_its_sticker_sizes(tmp_path):
    names = emojis.names_for(["1F600", "1F44B-1F3FD", "1F9D1-200D-1F680"], style="alphanumeric")
    assert len(set(names.values())) == 3 and all(re.fullmatch("[a-z0-9]{2,25}", n) for n in names.values())
    result = emojis.export_pack(tmp_path / "large.zip", ["😀"], "imessage", size=618)
    files, manifest = pack(tmp_path / "large.zip")
    assert result["size"] == manifest["size"] == 618
    assert Image.open(io.BytesIO(files[manifest["entries"][0]["image"]])).size == (618, 618)
    assert "Sticker Pack App" in files["README.txt"].decode()
    assert not any(name.endswith((".xcodeproj", ".pbxproj", ".xcstickers")) for name in files)
    for destination, size in (("imessage", 500), ("whatsapp", 256), ("twitch", 64)):
        with pytest.raises(VixlError, match="required export size"):
            emojis.export_pack(tmp_path / "bad.zip", ["😀"], destination, size=size)


def test_one_call_exports_slack_discord_and_whatsapp_packs_from_one_document(tmp_path, monkeypatch):
    p = text_document("😀 :my_emoji:")
    p.apply({**replacement("green"), "emoji": ":my_emoji:"})
    renders = []
    render = emojis.png
    monkeypatch.setattr(emojis, "png", lambda svg, size: renders.append(size) or render(svg, size))
    selection = ["😀", "👋🏽", ":my_emoji:"]
    result = emojis.export_pack(tmp_path / "set.zip", selection, ["slack", "discord", "whatsapp"], project=p)
    assert result["destinations"] == ["slack", "discord", "whatsapp"] and result["count"] == 3
    assert [Path(o["output"]).name for o in result["outputs"]] == [
        "set-slack.zip",
        "set-discord.zip",
        "set-whatsapp.zip",
    ]
    assert not (tmp_path / "set.zip").exists()
    # Slack and Discord share the 128 px masters: each emoji is drawn once per size (plus the tray icon).
    assert sorted(renders) == [96] + [128] * 3 + [512] * 3
    for item in result["outputs"]:
        files, manifest = pack(item["output"])
        profile = emojis.DESTINATIONS[item["destination"]]
        assert manifest["destination"] == item["destination"] and len(manifest["entries"]) == 3
        for entry in manifest["entries"]:
            image = Image.open(io.BytesIO(files[entry["image"]]))
            assert image.size == (profile["size"],) * 2 and len(files[entry["image"]]) < profile["max_bytes"]
    single = tmp_path / "single.zip"
    emojis.export_pack(single, selection, "slack", project=p)
    assert pack(single)[0].keys() == pack(tmp_path / "set-slack.zip")[0].keys()
    assert pack(single)[0]["png/my_emoji.png"] == pack(tmp_path / "set-slack.zip")[0]["png/my_emoji.png"]
    combined = emojis.requirements(["slack", "discord", "whatsapp"], selection, p)
    assert (
        combined["passed"] and [r["destination"] for r in combined["destinations"]] == result["destinations"]
    )
    # One destination failing its rules leaves no file behind for the others.
    with pytest.raises(VixlError, match="3–30"):
        emojis.export_pack(tmp_path / "two.zip", ["😀", "👋🏽"], ["slack", "whatsapp"])
    assert not list(tmp_path.glob("two*.zip"))
    with pytest.raises(VixlError, match="already exists"):
        emojis.export_pack(tmp_path / "set.zip", selection, ["discord"], project=p)
    with pytest.raises(VixlError, match="Unknown emoji destination"):
        emojis.export_pack(tmp_path / "x.zip", ["😀"], ["slack", "slack"])


@pytest.mark.parametrize(
    "destination, folder, format, size",
    [
        ("discord", "gif", "GIF", 128),
        ("slack", "gif", "GIF", 128),
        ("whatsapp", "stickers", "WEBP", 512),
        ("imessage", "stickers", "PNG", 408),
    ],
)
def test_animated_pack_respects_the_destination_frame_duration_and_byte_budgets(
    tmp_path, destination, folder, format, size
):
    # Four seconds at 20 fps is 80 frames: more than Slack's 50-frame budget.
    p, keys = animated_document(tmp_path, duration=4000)
    result = emojis.export_pack(tmp_path / "pack.zip", keys, destination, project=p, animated=True)
    spec = emojis.DESTINATIONS[destination]["animated"]
    files, manifest = pack(tmp_path / "pack.zip")
    assert manifest["animated"] is True and result["animated"] == 3 and result["format"] == spec["format"]
    for entry in manifest["entries"]:
        motion = entry["animation"]
        raw = files[motion["file"]]
        assert motion["file"] == f"{folder}/{entry['name']}.{format.lower()}" and len(raw) < spec["max_bytes"]
        image = Image.open(io.BytesIO(raw))
        assert image.format == format and image.size == (size, size) and image.n_frames > 1
        assert image.n_frames <= spec.get("max_frames", 80) and motion["frames"] == image.n_frames
        durations = []
        for index in range(image.n_frames):
            image.seek(index)
            image.load()
            durations.append(image.info["duration"])
        assert min(durations) >= spec.get("min_frame_ms", 1)
        assert abs(sum(durations) - 4000) <= 50 and sum(durations) <= spec.get("max_duration", 4050)
        # The master plays once; emoji destinations loop forever, WhatsApp keeps the master's count.
        assert motion["loop"] == spec.get("loop", 1)
        if format == "GIF":
            assert image.info["loop"] == 0 and Image.open(io.BytesIO(files[entry["image"]])).size == (
                128,
                128,
            )
    if destination == "slack":
        assert manifest["entries"][0]["animation"]["fps"] == 12
    if destination == "whatsapp":
        assert json.loads(files["contents.json"])["sticker_packs"][0]["animated_sticker_pack"] is True
    assert emojis.requirements(destination, keys, p, animated=True)["passed"]


def test_animated_pack_steps_colours_then_frame_rate_down_to_fit_and_refuses_what_cannot_fit(
    tmp_path, monkeypatch
):
    p, keys = animated_document(tmp_path, names=("wave",))
    emojis.export_pack(tmp_path / "full.zip", keys, "discord", project=p, animated=True)
    full = pack(tmp_path / "full.zip")[1]["entries"][0]["animation"]
    assert full["tries"] == 1 and full["colors"] == 256 and full["fps"] == 20
    monkeypatch.setitem(emojis.DESTINATIONS["discord"]["animated"], "max_bytes", full["bytes"] - 200)
    emojis.export_pack(tmp_path / "fit.zip", keys, "discord", project=p, animated=True)
    files, manifest = pack(tmp_path / "fit.zip")
    fitted = manifest["entries"][0]["animation"]
    assert fitted["tries"] > 1 and fitted["bytes"] < full["bytes"] - 200 == len(files[fitted["file"]]) + (
        full["bytes"] - 200 - fitted["bytes"]
    )
    assert fitted["colors"] < 256 and Image.open(io.BytesIO(files[fitted["file"]])).size == (128, 128)
    monkeypatch.setitem(emojis.DESTINATIONS["discord"]["animated"], "max_bytes", 200)
    with pytest.raises(VixlError, match="animated byte limit") as error:
        emojis.export_pack(tmp_path / "never.zip", keys, "discord", project=p, animated=True)
    assert error.value.code == "resource_limit" and not (tmp_path / "never.zip").exists()
    assert not emojis.requirements("discord", keys, p, animated=True)["passed"]


def test_animated_pack_rules_mixed_sets_long_timelines_and_format_choice(tmp_path):
    p, keys = animated_document(tmp_path, duration=12_000, fps=5)
    with pytest.raises(VixlError, match="at most 10000 ms"):
        emojis.export_pack(tmp_path / "long.zip", keys, "whatsapp", project=p, animated=True)
    p, keys = animated_document(tmp_path)
    with pytest.raises(VixlError, match="cannot mix still and animated"):
        emojis.export_pack(tmp_path / "mixed.zip", [*keys, "😀"], "whatsapp", project=p, animated=True)
    # Emoji uploads may mix: a still emoji stays a PNG and is named in the result.
    result = emojis.export_pack(tmp_path / "mixed.zip", [*keys, "😀"], "discord", project=p, animated=True)
    assert result["animated"] == 3 and len(result["still"]) == 1
    files, manifest = pack(tmp_path / "mixed.zip")
    assert "animation" not in manifest["entries"][3] and len([n for n in files if n.startswith("gif/")]) == 3
    emojis.export_pack(tmp_path / "webp.zip", keys, "images", project=p, animated="webp", size=64)
    files, manifest = pack(tmp_path / "webp.zip")
    image = Image.open(io.BytesIO(files["webp/wave.webp"]))
    assert image.format == "WEBP" and image.size == (64, 64) and image.n_frames > 1
    assert manifest["entries"][0]["animation"]["loop"] == 1
    with pytest.raises(VixlError, match="animated packs are gif"):
        emojis.export_pack(tmp_path / "bad.zip", keys, "discord", project=p, animated="webp")
    with pytest.raises(VixlError, match="no animated profile"):
        emojis.export_pack(tmp_path / "bad.zip", keys, "telegram", project=p, animated=True)
    # Without the flag an animated master exports as the still it always was.
    emojis.export_pack(tmp_path / "still.zip", keys, "discord", project=p)
    assert not any(n.startswith("gif/") for n in pack(tmp_path / "still.zip")[0])


def test_telegram_animated_pack_writes_tgs_that_passes_the_tgs_constraints(tmp_path):
    import gzip

    p, keys = animated_document(tmp_path)
    result = emojis.export_pack(tmp_path / "tgs.zip", keys, "telegram-animated", project=p)
    assert result["format"] == "tgs" and result["animated"] == 3
    files, manifest = pack(tmp_path / "tgs.zip")
    for entry in manifest["entries"]:
        raw = files[f"stickers/{entry['name']}.tgs"]
        data = json.loads(gzip.decompress(raw))
        assert len(raw) < 64 * 1024 and data["tgs"] == 1 and (data["w"], data["h"]) == (512, 512)
        assert data["fr"] == 60 and (data["op"] - data["ip"]) / data["fr"] <= 3
        assert not data["meta"]["fallbacks"] and not any("p" in asset for asset in data["assets"])
        assert entry["image"].endswith(".tgs") and entry["source"].endswith(".vixl")
    assert (
        "stickers/wave.tgs" not in files["index.html"].decode()
        and emojis.requirements("telegram-animated", keys, p)["passed"]
    )
    q = text_document("animated")
    emojis.install_pack(q, (tmp_path / "tgs.zip").read_bytes())
    assert set(q.state["emojis"]["overrides"]) == set(keys)
    # Raster fallbacks are refused, as TGS export refuses them; so are stills and long animations.
    blurred, keys = animated_document(tmp_path, effect=True)
    with pytest.raises(VixlError, match="layer effects"):
        emojis.export_pack(tmp_path / "raster.zip", keys, "telegram-animated", project=blurred)
    with pytest.raises(VixlError, match="no animated VIXL master"):
        emojis.export_pack(tmp_path / "still.zip", ["😀"], "telegram-animated", project=p)
    assert not emojis.requirements("telegram-animated", ["😀"], p)["passed"]
    slow, keys = animated_document(tmp_path, duration=4000)
    with pytest.raises(VixlError, match="at most 3000 ms"):
        emojis.export_pack(tmp_path / "slow.zip", keys, "telegram-animated", project=slow)
    assert not list(tmp_path.glob("r*.zip")) and not list(tmp_path.glob("s*.zip"))


def test_workflow_and_cli_export_several_destinations_and_animated_packs(tmp_path, capsys):
    from vixl.cli import main
    from vixl.workflow_schema import properties

    p, keys = animated_document(tmp_path)
    p.save(tmp_path / "doc.vixl")
    session = Session(tmp_path / "doc.vixl", workspace=tmp_path)
    result = dispatch(
        session,
        "emoji-export",
        {"output": "out/pack.zip", "destination": ["slack", "discord", "whatsapp"], "emojis": keys},
    )
    assert [o["output"] for o in result["outputs"]] == [
        "out/pack-slack.zip",
        "out/pack-discord.zip",
        "out/pack-whatsapp.zip",
    ]
    result = dispatch(
        session,
        "emoji-export",
        {"output": "moving.zip", "destination": "twitch", "emojis": keys, "animated": True},
    )
    assert result["animated"] == 3 and result["sizes"] == [28, 56, 112]
    files, manifest = pack(tmp_path / "moving.zip")
    assert manifest["entries"][0]["files"] == ["112/wave.gif", "56/wave.gif", "28/wave.gif"]
    assert [Image.open(io.BytesIO(files[n])).size[0] for n in manifest["entries"][0]["files"]] == [
        112,
        56,
        28,
    ]
    report = dispatch(session, "emoji-requirements", {"destination": ["twitch", "imessage"], "emojis": keys})
    assert report["passed"] and len(report["destinations"]) == 2
    with pytest.raises(VixlError):
        dispatch(session, "emoji-export", {"output": "x.zip", "destination": ["slack", "nowhere"]})
    listed = dispatch(session, "emoji-destinations", {})
    assert (
        listed["destinations"]["whatsapp"]["animated"]["max_bytes"] == 500_000
        and listed["checked"] >= "2026-11-14"
    )
    schema = properties("emoji-export", emoji_fields("emoji-export"))
    assert "telegram-animated" in schema["destination"]["anyOf"][1]["items"]["enum"] and "animated" in schema
    assert properties("emoji-template", ["destination"])["destination"]["type"] == "string"
    code = main(
        [
            "-p",
            str(tmp_path / "doc.vixl"),
            "emoji",
            "--workspace",
            str(tmp_path),
            "export",
            "--destination",
            "discord",
            "imessage",
            "--emojis",
            *keys,
            "--animated",
            "--out",
            "cli.zip",
        ]
    )
    printed = json.loads(capsys.readouterr().out)
    assert code == 0 and [o["output"] for o in printed["outputs"]] == ["cli-discord.zip", "cli-imessage.zip"]
    assert Image.open(io.BytesIO(pack(tmp_path / "cli-imessage.zip")[0]["stickers/wave.png"])).n_frames > 1
