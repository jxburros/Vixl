"""GIF/WebP/APNG size fitting, presets and measured WebP suggestions (#246)."""

from PIL import Image, features
import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.timeline import export_timeline


def busy(width=240, height=160, duration=2000):
    p = Project(width, height)
    p.apply([
        {"type": "gradient", "name": "sky", "start": "#1e3a8a", "end": "#f472b6", "direction": "angled", "angle": 30},
        {"type": "shape", "name": "sun", "shape": "ellipse", "width": 60, "height": 60, "x": 10, "y": 40, "fill": "#fde68a"},
        {"type": "timeline-set", "duration": duration, "fps": 20},
        {"type": "keyframes", "target": "sun", "property": "x", "keys": [{"time": 0, "value": 10}, {"time": duration, "value": 170}]},
        {"type": "keyframes", "target": "sky", "property": "end", "keys": [{"time": 0, "value": "#f472b6"}, {"time": duration, "value": "#22d3ee"}]},
    ])
    return p


def test_target_bytes_steps_down_until_the_gif_fits(tmp_path):
    p = busy()
    full = export_timeline(p, tmp_path / "full.gif")
    target = full["bytes"] // 4
    fitted = export_timeline(p, tmp_path / "fit.gif", target_bytes=target)
    chosen = fitted["chosen"]
    assert chosen["fits"] and fitted["bytes"] == chosen["bytes"] <= target
    assert chosen["tries"] > 1 and (tmp_path / "fit.gif").stat().st_size == fitted["bytes"]
    assert fitted["fps"] == chosen["fps"] and fitted["size"][0] == round(240 * chosen["scale"])
    with Image.open(tmp_path / "fit.gif") as image:
        assert image.size == tuple(fitted["size"])
    # Colors go first, then frame rate, then scale.
    assert chosen["colors"] < 256 and (chosen["scale"] < 1 or chosen["fps"] < 20 or chosen["colors"] <= 128)


def test_unreachable_target_writes_the_smallest_and_warns(tmp_path):
    result = export_timeline(busy(), tmp_path / "tiny.gif", target_bytes=200)
    # 256, 128, 64 colors; every 2nd, 3rd frame; 0.75, 0.56, 0.42 scale.
    assert not result["chosen"]["fits"] and result["chosen"]["tries"] == 8
    assert any("target_bytes 200 not reached" in w for w in result["warnings"])
    assert result["chosen"]["scale"] < 1 and result["chosen"]["fps"] < 20


def test_target_fits_webp_by_quality_first(tmp_path):
    p = busy()
    full = export_timeline(p, tmp_path / "full.webp")
    result = export_timeline(p, tmp_path / "fit.webp", target_bytes=int(full["bytes"] * 0.8))
    assert result["chosen"]["fits"] and result["chosen"]["quality"] < 90


def test_presets_fill_defaults_and_are_checked(tmp_path):
    p = busy(width=1200, height=400, duration=500)
    result = export_timeline(p, tmp_path / "mail.gif", preset="email")
    assert result["preset"] == "email" and result["size"][0] <= 600
    assert result["chosen"]["fps"] <= 10 and result["chosen"]["colors"] <= 128
    assert result["bytes"] <= 1_000_000
    chat = export_timeline(p, tmp_path / "chat.gif", preset="chat", fps=8)
    assert chat["chosen"]["fps"] <= 8 and chat["size"][0] <= 480
    with pytest.raises(VixlError):
        export_timeline(p, tmp_path / "x.gif", preset="tiktok")
    with pytest.raises(VixlError):
        export_timeline(p, tmp_path / "x.mp4", target_bytes=1000)


@pytest.mark.skipif(not features.check("webp"), reason="Pillow without WebP")
def test_big_gif_warning_quotes_a_measured_webp_size(tmp_path):
    result = export_timeline(busy(), tmp_path / "big.gif", max_bytes=1000)
    warning = next(w for w in result["warnings"] if "max_bytes" in w)
    assert "measured" in warning and "10x" not in warning
