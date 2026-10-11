"""SVG files compared or previewed through ``image_diff.load_visual`` get the appearance-import sanitizer."""

from PIL import Image
import pytest

from vixl.errors import VixlError
from vixl.image_diff import diff_files, load_visual
from vixl.interfaces import Session
from vixl.workflows import dispatch


def outside_png(tmp_path):
    secret = tmp_path / "outside" / "secret.png"
    secret.parent.mkdir()
    Image.new("RGBA", (40, 40), (255, 0, 0, 255)).save(secret)
    return secret


def test_svg_referencing_an_absolute_path_outside_the_workspace_is_refused(tmp_path):
    secret = outside_png(tmp_path)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    svg = workspace / "evil.svg"
    for attr in ('xlink:href', 'href'):
        svg.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
                       f'width="40" height="40"><image {attr}="{secret}" width="40" height="40"/></svg>')
        with pytest.raises(VixlError) as caught:
            load_visual(svg)
        assert caught.value.code == "unsupported_svg"
    # The same holds through a workspace proof page, which embeds the rendered preview.
    result = dispatch(Session(workspace=workspace), "proof", {"items": ["evil.svg"], "output": "proof.html"})
    assert [entry["path"] for entry in result["failed"]] == ["evil.svg"]
    assert "internal or embedded" in result["failed"][0]["error"]
    assert "data:image/png" not in (workspace / "proof.html").read_text(encoding="utf-8")


def test_svg_with_external_css_url_or_doctype_is_refused(tmp_path):
    secret = outside_png(tmp_path)
    cases = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40">'
        f'<rect width="40" height="40" style="fill:url(file://{secret})"/></svg>',
        '<!DOCTYPE svg [<!ENTITY x "y">]><svg xmlns="http://www.w3.org/2000/svg" width="4" height="4">&x;</svg>',
    ]
    for text in cases:
        with pytest.raises(VixlError) as caught:
            load_visual("x.svg", data=text.encode())
        assert caught.value.code == "unsupported_svg"


def test_oversize_svg_is_refused_before_rasterizing(tmp_path, monkeypatch):
    import resvg_py

    def no_render(**kwargs):
        raise AssertionError("resvg must not run for an oversize SVG")

    monkeypatch.setattr(resvg_py, "svg_to_bytes", no_render)
    huge = b'<svg xmlns="http://www.w3.org/2000/svg" width="200000" height="200000"><rect width="10" height="10"/></svg>'
    with pytest.raises(VixlError) as caught:
        load_visual("huge.svg", data=huge)
    assert caught.value.code == "resource_limit"


def test_svg_structure_limits_apply(tmp_path):
    deep = '<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4">' + "<g>" * 80 + "</g>" * 80 + "</svg>"
    with pytest.raises(VixlError) as caught:
        load_visual("deep.svg", data=deep.encode())
    assert caught.value.code == "resource_limit"


def test_self_contained_svg_still_renders_and_diffs(tmp_path):
    for name, x in (("a.svg", 0), ("b.svg", 20)):
        (tmp_path / name).write_text('<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20">'
                                     f'<rect x="{x}" width="20" height="20" fill="red"/></svg>')
    image = load_visual(tmp_path / "a.svg")
    assert image.size == (40, 20) and image.getpixel((5, 5)) == (255, 0, 0, 255)
    result = diff_files(tmp_path / "a.svg", tmp_path / "b.svg")
    assert result["changed_pixels"] == 800
