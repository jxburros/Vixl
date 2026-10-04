"""Deterministic synthetic 'photographs' for the photo lab (no camera, no internet).

source_photo(): a sunset-coast frame with deliberate faults a photo editor would fix:
  underexposed, cool/green cast, a 2.2 deg tilted horizon, sensor noise.
second_photo(): an alpine lake at dusk used to test preset transfer.
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def _smooth_noise(rng, h, w, scale, octaves=4):
    out = np.zeros((h, w), np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        sh, sw = max(2, int(h / scale * 2**o)), max(2, int(w / scale * 2**o))
        small = rng.random((sh, sw)).astype(np.float32)
        img = Image.fromarray((small * 255).astype(np.uint8)).resize((w, h), Image.Resampling.BICUBIC)
        out += amp * (np.asarray(img, np.float32) / 255.0)
        total += amp
        amp *= 0.5
    return out / total


def _lerp(a, b, t):
    return a + (b - a) * t[..., None]


def source_photo(w=1600, h=1067, seed=7):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    horizon = 0.60 * h
    sun = (0.66 * w, horizon - 0.07 * h)

    # Sky: deep indigo -> magenta -> orange -> pale gold at horizon
    t = np.clip(yy / horizon, 0, 1)
    stops = [(0.0, (22, 30, 78)), (0.45, (92, 58, 120)), (0.75, (226, 110, 80)), (1.0, (255, 196, 120))]
    sky = np.zeros((h, w, 3), np.float32)
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        m = (t >= t0) & (t <= t1)
        local = np.clip((t - t0) / (t1 - t0), 0, 1)
        sky[m] = _lerp(np.array(c0, np.float32), np.array(c1, np.float32), local)[m]
    d = np.hypot(xx - sun[0], (yy - sun[1]) * 1.1)
    glow = np.exp(-(d / (0.22 * w)) ** 2)[..., None]
    sky = sky + glow * np.array([90, 60, 20], np.float32)
    # Clouds: streaky fbm lit from below
    cl = _smooth_noise(rng, h, w // 3 if False else w, 260)
    streak = np.asarray(Image.fromarray((cl * 255).astype(np.uint8)).resize((w // 6, h)).resize((w, h)), np.float32) / 255
    cloud = np.clip((streak - 0.52) * 3.2, 0, 1) * np.clip((horizon * 0.92 - yy) / (horizon * 0.15), 0, 1) * np.clip(yy / (horizon * 0.3), 0, 1)
    cloud_col = _lerp(np.array([60, 40, 90], np.float32), np.array([255, 150, 110], np.float32), np.clip(yy / horizon, 0, 1) ** 1.5)
    sky = sky * (1 - cloud[..., None] * 0.75) + cloud_col * cloud[..., None] * 0.75
    sun_disc = np.clip(1.2 - d / (0.03 * w), 0, 1)[..., None]
    sky = sky * (1 - sun_disc) + np.array([255, 245, 215], np.float32) * sun_disc

    # Sea: reflect sky, darker, with horizontal wave texture and a sun glitter path
    sea_t = np.clip((yy - horizon) / (h - horizon), 0, 1)
    sea = _lerp(np.array([170, 100, 90], np.float32), np.array([16, 26, 52], np.float32), sea_t ** 0.6)
    fine = rng.random((h // 3, w // 40)).astype(np.float32)
    waves = np.asarray(Image.fromarray((fine * 255).astype(np.uint8)).resize((w, h), Image.Resampling.BICUBIC), np.float32) / 255
    waves = np.clip(waves, 0, 1)
    glitter_w = 0.03 * w + sea_t * 0.18 * w
    path = np.exp(-((xx - sun[0]) / glitter_w) ** 2) * np.clip((waves - 0.5) * 3, 0, 1) * (1 - sea_t * 0.7) * 0.8
    sea = sea * (0.82 + 0.3 * waves[..., None]) + path[..., None] * np.array([255, 200, 140], np.float32)
    img = np.where((yy < horizon)[..., None], sky, sea)

    pil = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(pil)
    # Headland on the left with a lighthouse
    hl = [(0, int(horizon) - 150)]
    for i in range(0, 560, 20):
        hl.append((i, int(horizon - 150 + (i / 560) ** 1.8 * 150 + 10 * np.sin(i / 37.0))))
    hl += [(600, int(horizon) + 4), (0, int(horizon) + 4)]
    draw.polygon(hl, fill=(26, 18, 30))
    lx, ly = 180, int(horizon) - 145
    draw.polygon([(lx - 16, ly), (lx + 16, ly), (lx + 9, ly - 120), (lx - 9, ly - 120)], fill=(30, 22, 34))
    draw.rectangle([lx - 13, ly - 136, lx + 13, ly - 120], fill=(255, 230, 160))
    draw.polygon([(lx - 16, ly - 136), (lx + 16, ly - 136), (lx, ly - 160)], fill=(30, 22, 34))
    # Foreground rocks on the right + standing figure
    rocks = [(860, h), (900, h - 170), (980, h - 230), (1080, h - 250), (1200, h - 215), (1330, h - 240),
             (1450, h - 190), (1600, h - 210), (1600, h)]
    draw.polygon(rocks, fill=(20, 16, 22))
    fx, fy = 1130, h - 236  # feet
    draw.ellipse([fx - 15, fy - 172, fx + 15, fy - 140], fill=(14, 12, 16))          # head
    draw.polygon([(fx - 24, fy - 138), (fx + 24, fy - 138), (fx + 18, fy - 60), (fx - 18, fy - 60)], fill=(14, 12, 16))
    draw.polygon([(fx - 16, fy - 62), (fx - 2, fy - 62), (fx - 6, fy), (fx - 18, fy)], fill=(14, 12, 16))
    draw.polygon([(fx + 2, fy - 62), (fx + 16, fy - 62), (fx + 20, fy), (fx + 8, fy)], fill=(14, 12, 16))
    draw.polygon([(fx + 20, fy - 134), (fx + 30, fy - 132), (fx + 70, fy - 190), (fx + 62, fy - 196)], fill=(14, 12, 16))  # raised arm
    draw.polygon([(fx - 22, fy - 134), (fx - 30, fy - 130), (fx - 34, fy - 70), (fx - 26, fy - 70)], fill=(14, 12, 16))
    # Birds
    for bx, by, s in [(420, 210, 14), (470, 180, 10), (520, 230, 12), (980, 140, 9)]:
        draw.line([(bx - s, by - s // 2), (bx, by), (bx + s, by - s // 2)], fill=(30, 20, 40), width=3)
    pil = pil.filter(ImageFilter.GaussianBlur(0.8))

    # Camera faults: tilt, underexposure, cool-green cast, noise
    pil = pil.rotate(-2.2, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=(20, 20, 30))
    a = np.asarray(pil, np.float32) / 255.0
    a = a ** 1.35 * 0.82                                  # underexposed, crushed
    a *= np.array([0.86, 1.02, 1.08], np.float32)          # cool/green cast
    a += rng.normal(0, 0.022, a.shape).astype(np.float32)  # sensor noise
    return Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8))


def second_photo(w=1200, h=800, seed=11):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    horizon = 0.60 * h
    t = np.clip(yy / horizon, 0, 1)
    sky = _lerp(np.array([40, 60, 110], np.float32), np.array([230, 170, 140], np.float32), t ** 1.6)
    img = sky.copy()
    pil = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(pil)
    for layer, (base, amp, col) in enumerate([(0.30, 0.18, (80, 82, 120)), (0.40, 0.14, (55, 55, 85)), (0.50, 0.08, (30, 32, 48))]):
        pts = [(0, h)]
        noise = _smooth_noise(rng, 1, w, 300 - layer * 80, 3)[0]
        for x in range(0, w + 1, 8):
            y = h * (base + amp * (1 - noise[min(x, w - 1)]) ** 2) - (layer == 0) * 60 * np.exp(-((x - 760) / 120) ** 2)
            pts.append((x, int(y)))
        pts.append((w, h))
        draw.polygon(pts, fill=col)
    a = np.asarray(pil, np.float32)
    lake = yy > horizon
    mirror = a[np.clip((2 * horizon - yy).astype(int), 0, h - 1), xx.astype(int)]
    ripple = 0.78 + 0.06 * np.sin(yy / 2.2 + _smooth_noise(rng, h, w, 80) * 5)
    a = np.where(lake[..., None], mirror * ripple[..., None] * np.array([0.8, 0.9, 1.0]), a)
    a = a / 255.0
    a = a ** 1.25 * 0.9 * np.array([0.9, 1.0, 1.06])
    a += rng.normal(0, 0.02, a.shape)
    return Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.5))


if __name__ == "__main__":
    source_photo().save("coast-raw-preview.png")
    second_photo().save("lake-raw-preview.png")
