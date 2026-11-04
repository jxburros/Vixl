"""The Vixl Originals: catalog families installed from the fonts content pack, and the outline fixes they needed."""

import hashlib
from pathlib import Path
import zipfile

import httpx
import numpy as np
import pytest

from vixl import house_style, packs, typefaces
from vixl.errors import VixlError
from vixl.project import Project

FONT = (Path(typefaces.__file__).parent / "data" / "DejaVuSans.ttf").read_bytes()
ORIGINALS = [entry for entry in typefaces.fonts() if entry.get("source") == "vixl"]


def pack(tmp_path, members=("vixl-orbit-400.ttf",)):
    path = tmp_path / "fonts.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for member in members:
            archive.writestr(member, FONT)
    return path


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("VIXL_FONT_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("VIXL_PACK_DIR", str(tmp_path / "packs"))
    monkeypatch.delenv("VIXL_FONTS_PACK", raising=False)
    return tmp_path / "cache"


def test_twenty_originals_are_catalogued_paired_and_tiered():
    assert len(ORIGINALS) == 20
    paired = {p[role]["family"] for p in typefaces.pairings() for role in ("heading", "body")}
    for entry in ORIGINALS:
        assert entry["family"].startswith("Vixl ") and len(entry["weights"]) == 1 and not entry["italic"]
        assert entry["family"] in paired, entry["family"]
    tiers = house_style.entries("pairings")
    for pairing in typefaces.pairings():
        if pairing["name"].startswith("vixl-"):
            assert tiers[pairing["name"]]["tier"] in ("bold", "avant-garde")


def test_an_original_installs_from_the_local_pack_without_network(cache, tmp_path, monkeypatch):
    monkeypatch.setenv("VIXL_FONTS_PACK", str(pack(tmp_path)))
    monkeypatch.setenv("VIXL_OFFLINE", "1")
    project = Project(200, 100)
    result = typefaces.install_font(project, "vixl orbit", 400, role="heading")
    assert result["family"] == "Vixl Orbit" and result["source"]["origin"] == "pack"
    assert result["source"]["member"] == "vixl-orbit-400.ttf"
    assert project.assets[result["file"]["asset"]] == FONT
    assert (cache / "vixl-orbit-400.ttf").read_bytes() == FONT  # later installs and renders use the cache
    assert typefaces.fetch_font("Vixl Orbit", 400, source=(found := {}))[0] == FONT and found["origin"] == "cache"


def test_an_original_names_its_weight_and_a_missing_member(cache, tmp_path, monkeypatch):
    monkeypatch.setenv("VIXL_FONTS_PACK", str(pack(tmp_path, members=())))
    with pytest.raises(VixlError) as caught:
        typefaces.fetch_font("Vixl Bolt", 400)
    assert caught.value.code == "unavailable_weight"
    with pytest.raises(VixlError) as caught:
        typefaces.fetch_font("Vixl Bolt", 800)
    assert caught.value.code == "unknown_font" and "vixl-bolt-800.ttf" in str(caught.value)


def test_the_pack_downloads_through_the_callers_client_and_is_checked(cache, tmp_path, monkeypatch):
    data = pack(tmp_path, members=("vixl-neon-400.ttf",)).read_bytes()
    monkeypatch.setitem(packs.PACKS, "fonts", {**packs.PACKS["fonts"], "sha256": hashlib.sha256(data).hexdigest(),
                                                "bytes": len(data)})
    seen = []

    def serve(request):
        seen.append(str(request.url))
        return httpx.Response(200, content=data)

    client = httpx.Client(transport=httpx.MockTransport(serve))
    assert typefaces.fetch_font("Vixl Neon", 400, client=client)[0] == FONT
    assert seen == [packs.url("fonts")] and packs.status("fonts")["installed"]
    monkeypatch.setitem(packs.PACKS, "fonts", {**packs.PACKS["fonts"], "sha256": "0" * 64})
    (cache / "vixl-neon-400.ttf").unlink()
    with pytest.raises(VixlError) as caught:
        typefaces.fetch_font("Vixl Neon", 400, client=client)
    assert caught.value.code == "pack_mismatch"


@pytest.mark.parametrize("rotation", [0, 30])
def test_outline_stroke_boxes_the_outline_so_pathfinder_keeps_all_of_it(rotation):
    from vixl.pathfinder_geometry import shape_contours

    p = Project(300, 240, background="white")
    p.apply({"type": "shape", "shape": "path", "name": "line", "x": 80, "y": 100, "path": "M0 0 L100 0",
             "stroke": "#000", "stroke_width": 20, "fill": "transparent", "line_cap": "round", "rotation": rotation})
    before = np.asarray(p.render().convert("L")).astype(int)
    p.apply({"type": "outline-stroke", "target": "line"})
    assert (np.abs(np.asarray(p.render().convert("L")).astype(int) - before) > 64).sum() == 0
    layer = p.layer("line")
    assert layer["height"] == pytest.approx(20) and layer["width"] == pytest.approx(120, abs=0.5)
    ys = [y for contour in shape_contours(layer) for seg in contour for _, y in seg]
    assert max(ys) - min(ys) == pytest.approx(20)  # the whole stroke, not a one-pixel sliver of it


# An outlined, simplified parenthesis from Vixl Neon: written to three decimals, its right-most point (94.552) sits a
# hair outside the box its stroke was fitted to (94.55159). Clipping that hair cut along the outline itself.
PAREN = (
         "M6.31 32.966 L30.222 54.46 L36.916 62.266 L42.225 70.123 L47.632 80.25 L52.461 92.498 L55.282 103.236 L56.731 "
         "114.807 L56.656 174.554 L54.62 187.784 L50.838 200.119 L44.661 213.622 L36.916 225.717 L29.243 234.496 L4.053 "
         "257.413 L0.945 263.186 L0.189 266.389 L0 269.675 L1.331 276.095 L4.777 281.674 L7.173 283.93 L12.946 287.038 "
         "L19.435 287.983 L25.855 286.652 L31.434 283.206 L58.626 258.468 L65.744 250.177 L72.147 241.203 L77.832 231.665 "
         "L83.675 219.632 L86.946 211.335 L90.283 200.745 L92.723 189.993 L93.969 181.331 L94.552 170.597 L94.457 113.159 "
         "L93.428 102.317 L90.845 89.378 L86.946 76.648 L81.849 64.279 L75.645 52.442 L68.39 41.321 L60.107 31.113 L52.482 "
         "23.537 L28.795 2.81 L22.703 0.385 L16.149 0.189 L12.946 0.945 L7.173 4.053 L2.81 8.948 L1.331 11.888 L0 18.308 "
         "L0.945 24.797 L4.053 30.57 L6.31 32.966 Z")


def test_a_path_a_rounding_hair_outside_its_box_still_unions():
    from vixl.booleans import combine_outlines
    from vixl.pathfinder_geometry import shape_contours

    p = Project(300, 400)
    p.apply({"type": "shape", "shape": "path", "name": "paren", "path": PAREN, "fill": "#000"})
    p.layer("paren").update(width=94.55159, height=287.98319, path_view=[94.55159, 287.98319])
    contours = shape_contours(p.layer("paren"))
    assert len(contours) == 1 and combine_outlines([contours], lambda inside: inside)


def test_an_offline_client_fails_like_a_google_download(cache):
    def refuse(request):
        raise httpx.ConnectError("offline", request=request)

    with pytest.raises(VixlError) as caught:
        typefaces.fetch_font("Vixl Pixel", 400, client=httpx.Client(transport=httpx.MockTransport(refuse)))
    assert caught.value.code == "font_download_failed"


def test_offline_without_the_pack_fails_like_a_google_download(cache, monkeypatch):
    monkeypatch.setenv("VIXL_OFFLINE", "1")
    with pytest.raises(VixlError) as caught:
        typefaces.fetch_font("Vixl Matrix", 400)
    assert caught.value.code == "font_download_failed" and "fonts content pack" in str(caught.value)
