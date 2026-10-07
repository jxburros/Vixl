import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter

from vixl import Project, denoise
from vixl.assets import add_image
from vixl.commands import compile_command
from vixl.errors import VixlError
from vixl.schema import operation_schema

SIZE = 192


def scene(grain=6.0, blotch=5.0, seed=1):
    """A clean picture (a step edge, a disc, a thin line, flat areas) and a copy with luminance
    grain and smooth, colour-only blotches added."""
    n = SIZE
    clean = Image.new("RGB", (n, n), (120, 130, 140))
    draw = ImageDraw.Draw(clean)
    draw.rectangle([0, 0, n // 2, n], fill=(70, 90, 160))
    draw.rectangle([n // 2, 0, n, n // 2], fill=(200, 170, 120))
    draw.ellipse([n * 0.15, n * 0.55, n * 0.45, n * 0.85], fill=(220, 60, 50))
    draw.line([(n * 0.55, n * 0.7), (n * 0.95, n * 0.9)], fill=(20, 20, 20), width=2)
    clean = clean.filter(ImageFilter.GaussianBlur(0.6))
    rng = np.random.default_rng(seed)
    low = np.exp(-2 * (np.pi * 3) ** 2 * (np.fft.fftfreq(n)[None, :] ** 2 + np.fft.fftfreq(n)[:, None] ** 2))
    smooth = [np.fft.ifft2(np.fft.fft2(rng.normal(0, 1, (n, n))) * low).real for _ in range(2)]
    cb, cr = [c / c.std() * blotch for c in smooth]
    red, blue = cr / 0.713, cb / 0.564
    green = -(0.299 * red + 0.114 * blue) / 0.587  # leaves the luminance alone
    noise = np.stack([red, green, blue], axis=-1) + rng.normal(0, grain, (n, n, 1))
    noisy = np.clip(np.asarray(clean, np.float32) + noise, 0, 255).astype(np.uint8)
    return clean, Image.fromarray(noisy)


def luma(image):
    return np.asarray(image.convert("L"), np.float32)


def flat_noise(image):
    """Standard deviation of the luminance in two flat patches."""
    y = luma(image)
    return float(np.mean([y[20:80, 20:80].std(), y[20:80, SIZE - 80:SIZE - 20].std()]))


def chroma_noise(image):
    a = np.asarray(image.convert("YCbCr"), np.float32)[20:80, 20:80]
    return float(np.mean([a[..., 1].std(), a[..., 2].std()]))


def edge_steepness(image):
    """The steepest step across the vertical edge (levels per pixel)."""
    rows = luma(image)[SIZE // 4 + 10:SIZE // 4 + 70].mean(axis=0)
    return float(np.abs(np.diff(rows)[SIZE // 2 - 12:SIZE // 2 + 12]).max())


def denoised(image, **settings):
    return denoise.denoise_image(image.convert("RGBA"), {"name": "denoise", **settings}).convert("RGB")


def test_flat_noise_drops_while_edges_stay_sharper_than_gaussian_blur_of_equal_reduction():
    clean, noisy = scene()
    result = denoised(noisy, luminance=50, chroma=50)
    before, after = flat_noise(noisy), flat_noise(result)
    assert after < 0.2 * before, f"flat-area noise {before:.2f} -> {after:.2f}"
    # The Gaussian blur that cleans the flat areas just as much (found by bisection).
    low, high = 0.3, 6.0
    for _ in range(14):
        sigma = (low + high) / 2
        if flat_noise(noisy.filter(ImageFilter.GaussianBlur(sigma))) > after:
            low = sigma
        else:
            high = sigma
    blurred = noisy.filter(ImageFilter.GaussianBlur(high))
    assert flat_noise(blurred) <= after * 1.05
    drawn = edge_steepness(clean)
    assert edge_steepness(result) > 0.9 * drawn, "the edge keeps its steepness"
    assert edge_steepness(blurred) < 0.5 * drawn, "equal noise reduction by blurring flattens the edge"
    # A thin line keeps its contrast too: its darkest pixel stays dark.
    line = (slice(int(SIZE * 0.7), int(SIZE * 0.9)), slice(int(SIZE * 0.55), int(SIZE * 0.95)))
    assert luma(result)[line].min() < luma(blurred)[line].min() - 25
    assert np.abs(luma(result) - luma(clean)).mean() < 0.5 * np.abs(luma(noisy) - luma(clean)).mean()


def test_luminance_and_chroma_strengths_are_independent():
    _, noisy = scene()
    colour_only = denoised(noisy, luminance=0, chroma=80)
    assert chroma_noise(colour_only) < 0.6 * chroma_noise(noisy)
    assert flat_noise(colour_only) > 0.9 * flat_noise(noisy), "grain is left for the luminance control"
    grain_only = denoised(noisy, luminance=60, chroma=0)
    assert flat_noise(grain_only) < 0.25 * flat_noise(noisy)
    assert chroma_noise(grain_only) > 0.95 * chroma_noise(noisy), "colour blotches are left for the chroma control"
    strong, gentle = denoised(noisy, luminance=100, chroma=100), denoised(noisy, luminance=20, chroma=20)
    assert flat_noise(strong) < flat_noise(gentle) and chroma_noise(strong) < chroma_noise(gentle)
    assert denoised(noisy, luminance=0, chroma=0).tobytes() == noisy.tobytes()


def test_colour_does_not_bleed_across_an_edge():
    clean, noisy = scene()
    result = np.asarray(denoised(noisy, luminance=50, chroma=100), np.float32)
    inside_disc = result[int(SIZE * 0.7) - 4:int(SIZE * 0.7) + 4, int(SIZE * 0.3) - 4:int(SIZE * 0.3) + 4].mean(axis=(0, 1))
    assert inside_disc[0] > 190 and inside_disc[2] < 90, "the red disc stays red next to the blue ground"


def test_a_clean_picture_is_hardly_touched():
    clean, _ = scene(grain=0, blotch=0)
    change = np.abs(np.asarray(denoised(clean), np.float32) - np.asarray(clean, np.float32))
    assert change.mean() < 0.6 and np.percentile(change, 99) < 6, "default strengths"
    change = np.abs(np.asarray(denoised(clean, luminance=100, chroma=100), np.float32) - np.asarray(clean, np.float32))
    assert change.mean() < 1.5, "even at full strength"


def test_result_does_not_depend_on_threads_or_strips(monkeypatch):
    _, noisy = scene()
    expected = denoised(noisy, luminance=60, chroma=60).tobytes()
    monkeypatch.setattr(denoise, "STRIP_PIXELS", 2048)
    assert denoised(noisy, luminance=60, chroma=60).tobytes() == expected
    monkeypatch.setattr(denoise.os, "cpu_count", lambda: 1)
    assert denoised(noisy, luminance=60, chroma=60).tobytes() == expected


def test_transparency_and_tiny_images():
    _, noisy = scene()
    rgba = np.asarray(noisy.convert("RGBA")).copy()
    rgba[:, :50, 3] = 0
    rgba[:, 50:90, 3] = 128
    source = Image.fromarray(rgba)
    result = np.asarray(denoise.denoise_image(source, {"name": "denoise"}))
    assert (result[..., 3] == rgba[..., 3]).all()
    assert (result[:, :50] == rgba[:, :50]).all(), "invisible pixels are left alone and do not colour their neighbours"
    assert np.abs(result[:, 50:, :3].astype(int) - rgba[:, 50:, :3]).mean() > 0.5
    tiny = Image.new("RGBA", (3, 3), (10, 20, 30, 255))
    assert denoise.denoise_image(tiny, {"name": "denoise"}).tobytes() == tiny.tobytes()
    thin = Image.fromarray(np.random.default_rng(0).integers(0, 255, (5, 40, 4), dtype=np.uint8))
    assert denoise.denoise_image(thin, {"name": "denoise", "search": 10}).size == (40, 5)


def test_noise_level_measures_the_grain():
    rng = np.random.default_rng(3)
    plane = rng.normal(100, 4.0, (300, 300)).astype(np.float32)
    assert abs(denoise.noise_level(plane) - 4.0) < 0.3
    ramp = np.tile(np.linspace(0, 255, 300, dtype=np.float32), (300, 1))
    assert denoise.noise_level(ramp) < 0.1, "a gradient is not noise"


def test_denoise_is_a_non_destructive_effect_on_an_image_layer(tmp_path):
    _, noisy = scene()
    p = Project(SIZE, SIZE)
    p.apply({"type": "add", "asset": add_image(p, noisy.convert("RGBA")), "name": "photo"})
    before = p.render().tobytes()
    p.apply({"type": "denoise", "target": "photo", "luminance": 60, "chroma": 40})
    effect = p.layer("photo")["effects"][0]
    assert effect["name"] == "denoise" and effect["luminance"] == 60 and effect["chroma"] == 40
    cleaned = p.render()
    assert flat_noise(cleaned.convert("RGB")) < 0.25 * flat_noise(noisy)
    assert cleaned.tobytes() == p.render().tobytes(), "deterministic"
    p.apply({"type": "effect-set", "target": "photo", "effect": 1, "luminance": 90, "search": 3})
    assert p.layer("photo")["effects"][0]["search"] == 3
    p.apply({"type": "effect-disable", "target": "photo", "effect": 1})
    assert p.render().tobytes() == before, "disabling restores the photo"
    p.apply({"type": "effect-enable", "target": "photo", "effect": 1})
    assert p.render().tobytes() != before
    path = tmp_path / "doc.vixl"
    p.save(path)
    assert Project.load(path).layer("photo")["effects"][0]["luminance"] == 90
    # The effect stack keeps working with other effects and in an SVG export (rasterized there).
    p.apply({"type": "sharpen", "target": "photo", "amount": 1.2})
    assert p.render().size == (SIZE, SIZE)
    assert "<image" in p.export(format="SVG").decode()


def test_amount_sets_both_strengths_and_bad_values_are_refused():
    assert denoise.settings({"name": "denoise"}) == (50.0, 50.0, 5)
    assert denoise.settings({"name": "denoise", "amount": 30}) == (30.0, 30.0, 5)
    assert denoise.settings({"name": "denoise", "amount": 30, "chroma": 80, "search": 3}) == (30.0, 80.0, 3)
    p = Project(32, 32)
    p.apply({"type": "solid", "name": "ground", "color": "#808080"})
    for bad in ({"luminance": 120}, {"chroma": -5}, {"search": 0}, {"search": 11}, {"search": 10.6}, {"amount": 400}):
        with pytest.raises(VixlError):
            p.apply({"type": "denoise", "target": "ground", **bad})


def test_schema_and_command_line_describe_the_controls():
    properties = next(v for v in operation_schema()["properties"]["operations"]["items"]["oneOf"]
                      if v["properties"]["type"]["const"] == "denoise")["properties"]
    for key, kind in (("luminance", "number"), ("chroma", "number"), ("search", "integer")):
        assert properties[key]["type"] == kind and properties[key]["description"].startswith("denoise:")
    assert compile_command(["denoise", "photo", "--luminance", "40", "--chroma", "70", "--search", "4"]) == {
        "type": "denoise", "target": "photo", "luminance": 40.0, "chroma": 70.0, "search": 4}
    assert compile_command(["denoise", "photo", "35"]) == {"type": "denoise", "target": "photo", "value": 35.0}
    assert compile_command(["filter", "denoise", "--target", "photo", "--chroma", "60"]) == {
        "type": "effect", "name": "denoise", "target": "photo", "chroma": 60.0}
