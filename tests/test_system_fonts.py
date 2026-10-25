"""Fonts installed on the host resolve by family, style and PostScript name, are embedded, and are listed.

The suite never reads the machine's own fonts: each test builds a font folder from the bundled faces, points
VIXL_FONT_DIRS at it and replaces the fontconfig, registry and folder probes with fakes.
"""

from io import BytesIO
import json
from pathlib import Path
import shutil

from fontTools.ttLib import TTCollection, TTFont
import numpy as np
import pytest

import vixl
from vixl import Project, VixlError, system_fonts
from vixl.cli import dispatch
from vixl.interfaces import Session

DATA = Path(vixl.__file__).parent / "data"
STYLES = {"Regular": (400, False), "Italic": (400, True), "SemiBold": (600, False), "Bold": (700, False),
          "Bold Italic": (700, True)}


def make_face(source, family, style, weight, italic, fs_type=0):
    """A copy of a bundled face renamed to ``family style`` with that weight and slope."""
    font = TTFont(DATA / source)
    ps = f"{family.replace(' ', '')}-{style.replace(' ', '')}"
    regular = style in ("Regular", "Italic", "Bold", "Bold Italic")
    names = font["name"]
    for record in list(names.names):
        if record.nameID in (1, 2, 4, 6, 16, 17):
            names.removeNames(nameID=record.nameID)
    names.setName(family if regular else f"{family} {style}", 1, 3, 1, 0x409)
    names.setName(style if regular else ("Italic" if italic else "Regular"), 2, 3, 1, 0x409)
    names.setName(f"{family} {style}", 4, 3, 1, 0x409)
    names.setName(ps, 6, 3, 1, 0x409)
    names.setName(family, 16, 3, 1, 0x409)
    names.setName(style, 17, 3, 1, 0x409)
    font["OS/2"].usWeightClass = weight
    font["OS/2"].fsSelection = (font["OS/2"].fsSelection & ~0x61) | (1 if italic else 0) | (0x20 if weight >= 700 else 0) \
        | (0x40 if not italic and weight < 700 else 0)
    font["OS/2"].fsType = fs_type
    font["head"].macStyle = (1 if weight >= 700 else 0) | (2 if italic else 0)
    return font


def save(font, path):
    out = BytesIO()
    font.save(out)
    path.write_bytes(out.getvalue())
    return path


@pytest.fixture
def installed(tmp_path, monkeypatch):
    """A fonts folder holding the family 'Vixl Test Serif' (five styles), a two-face collection, a font whose
    licence restricts embedding and an unreadable file; the platform probes find nothing of the machine's."""
    folder = tmp_path / "fonts"
    (folder / "nested").mkdir(parents=True)
    for style, (weight, italic) in STYLES.items():
        save(make_face("NotoSans-Regular.ttf", "Vixl Test Serif", style, weight, italic),
             folder / f"VixlTestSerif-{style.replace(' ', '')}.ttf")
    collection = TTCollection()
    collection.fonts = [make_face("DejaVuSans.ttf", "Vixl Collection Sans", "Regular", 400, False),
                        make_face("DejaVuSans.ttf", "Vixl Collection Sans", "Bold", 700, False)]
    collection.save(str(folder / "nested" / "VixlCollection.ttc"))
    save(make_face("NotoSans-Regular.ttf", "Vixl Locked", "Regular", 400, False, fs_type=0x0002),
         folder / "VixlLocked.otf")
    (folder / "broken.ttf").write_bytes(b"not a font at all")
    monkeypatch.setenv("VIXL_SYSTEM_FONTS", "on")
    monkeypatch.setenv("VIXL_FONT_DIRS", str(folder))
    monkeypatch.setenv("VIXL_SYSTEM_FONT_INDEX", str(tmp_path / "index.json"))
    monkeypatch.setattr(system_fonts, "fontconfig_files", lambda: [])
    monkeypatch.setattr(system_fonts, "registry_files", lambda: None)
    monkeypatch.setattr(system_fonts, "platform_dirs", lambda: [])
    system_fonts._clear()
    yield folder
    system_fonts._clear()


def pick(name, *args):
    face = system_fonts.lookup(name, *args)
    return face and (face["family"], face["style"], face["weight"], face["italic"])


def test_family_style_postscript_and_case_insensitive_names(installed):
    assert pick("Vixl Test Serif") == ("Vixl Test Serif", "Regular", 400, False)
    assert pick("vixl test serif bold italic") == ("Vixl Test Serif", "Bold Italic", 700, True)
    assert pick("VixlTestSerif-BoldItalic") == ("Vixl Test Serif", "Bold Italic", 700, True)
    assert pick("Vixl Test Serif SemiBold") == ("Vixl Test Serif", "SemiBold", 600, False)
    assert pick("vixltestserif_semibold") == ("Vixl Test Serif", "SemiBold", 600, False)
    assert pick("Vixl Test Serif 700 Italic") == ("Vixl Test Serif", "Bold Italic", 700, True)
    assert pick("Vixl Test Serif Italic") == ("Vixl Test Serif", "Italic", 400, True)
    assert pick("Vixl Collection Sans Bold") == ("Vixl Collection Sans", "Bold", 700, False)
    assert pick("vixltestserif-bold.ttf") == ("Vixl Test Serif", "Bold", 700, False)
    assert pick("Vixl Test Sans") is None and pick("Vixl Test Serif Wobbly") is None
    assert pick("../fonts/VixlTestSerif-Bold.ttf") is None  # never a path


def test_nearest_weight_follows_css_matching(installed):
    assert pick("Vixl Test Serif ExtraBold") == ("Vixl Test Serif", "Bold", 700, False)  # heavier first, then lighter
    assert pick("Vixl Test Serif Light") == ("Vixl Test Serif", "Regular", 400, False)  # lighter first, then heavier
    assert pick("Vixl Test Serif Medium") == ("Vixl Test Serif", "Regular", 400, False)  # 500 looks down before up
    assert pick("Vixl Test Serif", 650, None) == ("Vixl Test Serif", "Bold", 700, False)
    assert pick("Vixl Test Serif SemiBold Italic") == ("Vixl Test Serif", "Bold Italic", 700, True)  # slope first
    assert pick("Vixl Collection Sans Italic") == ("Vixl Collection Sans", "Regular", 400, False)  # no italic face


def test_text_layer_embeds_the_installed_face_and_renders_after_it_is_removed(installed, tmp_path, monkeypatch):
    project = Project(400, 120)
    result = project.apply({"type": "text", "text": "Hamburgefonstiv", "font": "Vixl Test Serif Bold", "size": 40})
    layer = project.layer()
    assert layer["font"] in project.assets and layer["font"].startswith("fonts/")
    assert project.state["fonts"]["vixl-test-serif-700"] == layer["font"]
    reported = result["installed_fonts"][0]
    assert reported["family"] == "Vixl Test Serif" and reported["style"] == "Bold" and reported["embedding"] == "installable"
    expected = (installed / "VixlTestSerif-Bold.ttf").read_bytes()
    assert project.assets[layer["font"]] == expected
    before = np.asarray(project.render())
    project.save(tmp_path / "doc.vixl")
    shutil.rmtree(installed)
    monkeypatch.setenv("VIXL_SYSTEM_FONTS", "off")
    system_fonts._clear()
    again = Project.load(tmp_path / "doc.vixl")
    assert np.array_equal(np.asarray(again.render()), before)
    for suffix in ("svg", "pdf", "pptx"):
        again.export(tmp_path / f"out.{suffix}")
        assert (tmp_path / f"out.{suffix}").stat().st_size > 0
    assert b"VixlTestSerif" in (tmp_path / "out.pdf").read_bytes()  # the PDF embeds the face


def test_collection_face_is_extracted_as_a_standalone_font(installed):
    project = Project(300, 100)
    project.apply({"type": "text", "text": "Bold", "font": "VixlCollectionSans-Bold"})
    data = project.assets[project.layer()["font"]]
    assert data[:4] != b"ttcf"
    font = TTFont(BytesIO(data))
    assert font["name"].getDebugName(6) == "VixlCollectionSans-Bold" and font["OS/2"].usWeightClass == 700
    assert project.state["fonts"]["vixl-collection-sans-700"] == project.layer()["font"]


def test_existing_names_resolve_as_before(installed):
    project = Project(300, 100)
    project.apply({"type": "text", "text": "a", "font": "DejaVuSans.ttf"})
    assert project.layer()["font"] == "DejaVuSans.ttf"
    project.apply({"type": "text", "text": "b"})
    assert project.layer()["font"] == "NotoSans-Regular.ttf"  # the default never picks an installed font
    data = (DATA / "NotoSans-Regular.ttf").read_bytes()
    project.assets["fonts/noto.ttf"] = data
    project.apply({"type": "font-register", "name": "Vixl-Test-Serif", "asset": "fonts/noto.ttf", "role": "heading"})
    project.apply({"type": "text", "text": "c", "font": "Vixl-Test-Serif"})
    assert project.layer()["font"] == "fonts/noto.ttf"  # a registered name wins over an installed family
    project.apply({"type": "text", "text": "d", "font": "heading"})
    assert project.layer()["font"] == "fonts/noto.ttf"
    project.apply({"type": "text", "text": "e", "font": "DejaVu Sans"})
    assert project.layer()["font"] == "DejaVuSans.ttf"  # bundled families resolve to the bundled file everywhere
    project.apply({"type": "text", "text": "f", "font": "Noto Sans"})
    assert project.layer()["font"] == "NotoSans-Regular.ttf"
    assert not any(system_fonts.lookup(name)["source"] != "bundled" for name in ("DejaVu Sans", "Noto Sans"))


def test_off_switch_and_suggestions(installed, monkeypatch):
    with pytest.raises(VixlError) as caught:
        Project(100, 100).apply({"type": "text", "text": "a", "font": "Vixl Tset Serif"})
    assert caught.value.code == "missing_font" and "Vixl Test Serif" in caught.value.details["suggestions"]
    assert "Installed fonts with close names: Vixl Test Serif" in str(caught.value)
    monkeypatch.setenv("VIXL_SYSTEM_FONTS", "off")
    system_fonts._clear()
    assert system_fonts.lookup("Vixl Test Serif") is None and system_fonts.families()["families"] == []
    with pytest.raises(VixlError) as caught:
        Project(100, 100).apply({"type": "text", "text": "a", "font": "Vixl Test Serif"})
    assert caught.value.code == "missing_font" and "suggestions" not in caught.value.details


def test_extra_mode_keeps_only_the_named_folders(installed, monkeypatch, tmp_path):
    other = tmp_path / "machine"
    other.mkdir()
    save(make_face("DejaVuSans.ttf", "Vixl Machine Sans", "Regular", 400, False), other / "machine.ttf")
    monkeypatch.setattr(system_fonts, "fontconfig_files", lambda: [str(other / "machine.ttf")])
    system_fonts._clear()
    assert pick("Vixl Machine Sans") == ("Vixl Machine Sans", "Regular", 400, False)
    monkeypatch.setenv("VIXL_SYSTEM_FONTS", "extra")
    system_fonts._clear()
    assert pick("Vixl Machine Sans") is None and pick("Vixl Test Serif")


def test_fontconfig_registry_and_folder_sources_merge_without_duplicates(installed, monkeypatch, tmp_path):
    fc, registered, folder = tmp_path / "fc", tmp_path / "registered", tmp_path / "winfonts"
    for path, family in ((fc, "Vixl Fc Sans"), (registered, "Vixl Registry Sans"), (folder, "Vixl Folder Sans")):
        path.mkdir()
        save(make_face("DejaVuSans.ttf", family, "Regular", 400, False), path / "face.ttf")
    duplicate = str(installed / "VixlTestSerif-Bold.ttf")
    monkeypatch.setattr(system_fonts, "fontconfig_files", lambda: [str(fc / "face.ttf"), duplicate])
    system_fonts._clear()
    sources = {face["family"]: face["source"] for face in system_fonts.faces()}
    assert sources["Vixl Fc Sans"] == "fontconfig" and "Vixl Folder Sans" not in sources
    assert sum(face["file"].endswith("VixlTestSerif-Bold.ttf") for face in system_fonts.faces()) == 1
    # Windows: the registry's files (a per-user install outside the folders) and the folders.
    monkeypatch.setattr(system_fonts, "fontconfig_files", lambda: None)
    monkeypatch.setattr(system_fonts, "registry_files", lambda: [str(registered / "face.ttf"), duplicate])
    monkeypatch.setattr(system_fonts, "platform_dirs", lambda: [folder])
    system_fonts._clear()
    sources = {face["family"]: face["source"] for face in system_fonts.faces()}
    assert sources["Vixl Registry Sans"] == "registry" and sources["Vixl Folder Sans"] == "folder"
    assert sources["Vixl Test Serif"] == "extra"
    assert sum(face["file"].endswith("VixlTestSerif-Bold.ttf") for face in system_fonts.faces()) == 1


def test_fontconfig_probe_parses_fc_list(monkeypatch):
    class Done:
        returncode = 0
        stdout = b"/usr/share/fonts/a.ttf\n\n/usr/share/fonts/b.ttc\n"

    monkeypatch.setattr(system_fonts.sys, "platform", "linux")
    monkeypatch.setattr(system_fonts.shutil, "which", lambda name: "/usr/bin/fc-list")
    calls = []
    monkeypatch.setattr(system_fonts.subprocess, "run", lambda argv, **kw: calls.append(argv) or Done())
    assert system_fonts.fontconfig_files() == ["/usr/share/fonts/a.ttf", "/usr/share/fonts/b.ttc"]
    assert calls[0][1:] == ["--format", "%{file}\\n"]
    monkeypatch.setattr(system_fonts.shutil, "which", lambda name: None)
    assert system_fonts.fontconfig_files() is None  # no fontconfig: the folders are scanned


def test_listing_api_and_cli(installed):
    listing = system_fonts.families("test serif")
    assert listing["count"] == 1 and listing["families"][0]["family"] == "Vixl Test Serif"
    styles = listing["families"][0]["styles"]
    assert [s["style"] for s in styles] == ["Regular", "SemiBold", "Bold", "Italic", "Bold Italic"]
    assert styles[2]["postscript"] == "VixlTestSerif-Bold" and styles[2]["file"].endswith("VixlTestSerif-Bold.ttf")
    assert styles[2]["index"] == 0 and styles[2]["embedding"] == "installable"
    collection = system_fonts.families("collection")["families"][0]["styles"]
    assert [s["index"] for s in collection] == [0, 1]
    locked = system_fonts.families("locked")["families"][0]["styles"][0]
    assert locked["embedding"] == "restricted"
    assert "broken" not in json.dumps(system_fonts.families())
    capped = system_fonts.families(limit=1, compact=True)
    assert capped["count"] == 3 and len(capped["families"]) == 1 and "truncated" in capped
    assert capped["families"][0]["styles"] == ["Regular", "Bold"]
    out, _ = dispatch(["font", "system", "serif", "--styles"])
    assert out["families"] == [{"family": "Vixl Test Serif", "styles": ["Regular", "SemiBold", "Bold", "Italic", "Bold Italic"]}]


def test_reference_and_rest_listing(installed):
    from vixl.mcp_actions import reference_fonts

    shown = reference_fonts(None, view="installed", query="vixl")
    assert shown["count"] == 3 and all(isinstance(style, str) for row in shown["families"] for style in row["styles"])
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from vixl.interfaces import create_app

    Project(10, 10).save(installed.parent / "doc.vixl")
    with TestClient(create_app(installed.parent / "doc.vixl")) as client:
        body = client.get("/typefaces/installed", params={"query": "test serif"}).json()
    assert body["families"][0]["family"] == "Vixl Test Serif"
    assert "file" not in body["families"][0]["styles"][0]  # no server paths for remote clients


def test_catalog_marks_installed_families(installed):
    from vixl import typefaces

    save(make_face("NotoSans-Regular.ttf", "Lora", "Regular", 400, False), installed / "Lora.ttf")
    system_fonts._clear()
    rows = {row["family"]: row for row in typefaces.list_fonts()["fonts"]}
    assert rows["Lora"].get("installed") is True and "installed" not in rows.get("Merriweather", {})


def test_rich_text_bold_and_italic_spans_use_the_installed_faces(installed):
    from vixl.richtext import variant_font

    project = Project(600, 120)
    project.apply({"type": "rich-text", "font": "Vixl Test Serif", "size": 32,
                   "spans": [{"text": "plain "}, {"text": "bold ", "bold": True}, {"text": "italic", "italic": True}]})
    layer = project.layer()
    fonts = project.state["fonts"]
    assert {"vixl-test-serif-400", "vixl-test-serif-700", "vixl-test-serif-400-italic"} <= set(fonts)
    assert variant_font(project, layer["font"], True, False, layer["rich"]) == (fonts["vixl-test-serif-700"], False, False)
    assert variant_font(project, layer["font"], False, True, layer["rich"]) == (fonts["vixl-test-serif-400-italic"], False, False)
    assert project.assets[fonts["vixl-test-serif-700"]] == (installed / "VixlTestSerif-Bold.ttf").read_bytes()
    project.render()


def test_restricted_faces_warn_locally_and_are_refused_through_services(installed, tmp_path):
    project = Project(300, 100)
    result = project.apply({"type": "text", "text": "a", "font": "Vixl Locked"})
    assert project.layer()["font"] in project.assets
    assert any("embedding permission 'restricted'" in warning for warning in result.get("warnings", []))
    session = Session(workspace=tmp_path)
    session.create("doc.vixl", 300, 100)
    ok = session.apply([{"type": "text", "name": "a", "text": "A", "font": "Vixl Test Serif Bold"}])
    assert ok["success"]
    with pytest.raises(VixlError) as caught:
        session.apply([{"type": "text", "name": "b", "text": "B", "font": "Vixl Locked"}])
    assert caught.value.code == "forbidden" and "restricted" in str(caught.value)
    with pytest.raises(VixlError) as caught:
        session.apply([{"type": "text", "name": "c", "text": "C", "font": "Vixl Tset Serif"}])
    assert "Vixl Test Serif" in caught.value.details["suggestions"]


def test_scanning_is_bounded_and_cached_on_disk(installed, monkeypatch, tmp_path):
    first = system_fonts.faces()
    assert json.loads((tmp_path / "index.json").read_text())["version"] == system_fonts.INDEX_VERSION
    # A new process reads the index instead of parsing the fonts again.
    system_fonts._clear()
    monkeypatch.setattr(system_fonts, "faces_of", lambda path: pytest.fail(f"re-parsed {path}"))
    assert [face["postscript"] for face in system_fonts.faces()] == [face["postscript"] for face in first]
    # A changed file is parsed again; files beyond the limits are skipped.
    monkeypatch.undo()
    monkeypatch.setenv("VIXL_SYSTEM_FONTS", "on")
    monkeypatch.setenv("VIXL_FONT_DIRS", str(installed))
    monkeypatch.setenv("VIXL_SYSTEM_FONT_INDEX", str(tmp_path / "index.json"))
    for name in ("fontconfig_files", "registry_files"):
        monkeypatch.setattr(system_fonts, name, lambda: None if name == "registry_files" else [])
    monkeypatch.setattr(system_fonts, "platform_dirs", lambda: [])
    monkeypatch.setattr(system_fonts, "MAX_FILES", 2)
    system_fonts._clear()
    assert len({face["file"] for face in system_fonts.faces() if face["source"] != "bundled"}) <= 2
    monkeypatch.setattr(system_fonts, "MAX_FILES", 6000)
    monkeypatch.setattr(system_fonts, "MAX_FILE_BYTES", 1000)
    system_fonts._clear()
    assert [face for face in system_fonts.faces() if face["source"] != "bundled"] == []


def test_a_font_installed_while_running_is_found_after_the_probe_interval(installed, monkeypatch):
    assert pick("Vixl Late Sans") is None
    save(make_face("DejaVuSans.ttf", "Vixl Late Sans", "Regular", 400, False), installed / "late.ttf")
    monkeypatch.setattr(system_fonts, "PROBE_TTL", 0.0)
    assert pick("Vixl Late Sans") == ("Vixl Late Sans", "Regular", 400, False)


@pytest.mark.perf
def test_warm_lookup_is_fast(installed):
    import time

    system_fonts.faces()
    system_fonts._clear()
    start = time.perf_counter()
    system_fonts.faces()  # a new process: the disk index, no parsing
    warm = time.perf_counter() - start
    start = time.perf_counter()
    for _ in range(1000):
        system_fonts.lookup("Vixl Test Serif Bold Italic")
    assert warm < 0.25 and time.perf_counter() - start < 0.05


def test_script_faces_include_installed_catalog_families_and_their_system_names(installed):
    save(make_face("DejaVuSans.ttf", "Noto Sans CJK SC", "Regular", 400, False), installed / "cjk.ttf")
    save(make_face("DejaVuSans.ttf", "Noto Sans CJK SC", "Bold", 700, False), installed / "cjk-bold.ttf")
    system_fonts._clear()
    found = system_fonts.script_faces(["Noto Sans SC", "Noto Sans Thai"])
    assert found == [(installed / "cjk.ttf").read_bytes()]
    from vixl.typefaces import local_script_faces

    assert (installed / "cjk.ttf").read_bytes() in local_script_faces(["Noto Sans SC"])
