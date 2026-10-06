"""Edge-preserving noise reduction for the ``denoise`` effect.

Luminance is cleaned with non-local means: each pixel becomes the average of the pixels in a
window around it, weighted by how much their 5 x 5 neighbourhoods look like its own, so grain
averages out in flat areas while edges and fine lines, whose neighbourhoods match only along the
edge, stay sharp. Chroma noise is blotchier than grain, so the colour planes are smoothed at
reduced resolution with the cleaned luminance guiding which pixels may be averaged together;
colour does not bleed across an edge. Strengths are relative to the noise measured in the image
itself, so one setting suits a clean photo and a grainy one alike.

Cost: ``search`` sets the window radius, and the time grows with the number of window positions
tried: every position within two pixels, then every other one farther out, 24 + ((2 * search + 1)
** 2 - 25) / 2 in all (72 at the default of 5, 124 at 7, at most 232). That takes roughly a
second per megapixel at the default and is spread over up to four threads in strips (the result
is the same whatever the thread count); chroma, at half or quarter resolution, adds about a third.
Only NumPy and Pillow are used.
"""

from concurrent.futures import ThreadPoolExecutor
import os

import numpy as np
from PIL import Image

from .errors import require
from .model import finite

DEFAULTS = {"luminance": 50.0, "chroma": 50.0, "search": 5}
KEYS = tuple(DEFAULTS)
PATCH = 2                  # patch radius: 5 x 5 pixel patches
MAX_SEARCH = 10            # at most 232 window positions
STRIP_PIXELS = 1 << 18     # pixels per strip: the working arrays stay in cache
CHROMA_LEVELS = 12.0       # chroma levels that count as one colour at full chroma strength
CHROMA_DETAIL = 0.5        # chroma detail steeper than this share of that tolerance is kept as drawn
LUMA_GUIDE = 2.0           # luminance differences count this much more than chroma ones when matching
NOISE_FLOOR = 1.0          # levels; a clean image is smoothed a little, not left alone or wrecked


def settings(effect):
    """(luminance, chroma, search) of a ``denoise`` effect. ``amount`` sets both strengths when
    they are not given; nothing at all gives the defaults."""
    shared = effect.get("amount") or None
    luminance = effect.get("luminance", shared if shared is not None else DEFAULTS["luminance"])
    chroma = effect.get("chroma", shared if shared is not None else DEFAULTS["chroma"])
    return float(luminance), float(chroma), int(effect.get("search", DEFAULTS["search"]))


def validate(effect):
    finite(effect.get("amount", 0), "amount", 0, 100)
    luminance, chroma, search = settings(effect)
    finite(luminance, "luminance", 0, 100)
    finite(chroma, "chroma", 0, 100)
    require(float(effect.get("search", DEFAULTS["search"])).is_integer() and 1 <= search <= MAX_SEARCH,
            f"denoise search must be a whole number of pixels from 1 to {MAX_SEARCH}")


def noise_level(plane):
    """The standard deviation of the noise in a float plane (levels of 0-255): the median absolute
    response of a 3 x 3 kernel that is blind to flat areas and gradients, from bands of rows when
    the plane is large. Edges are a small share of the pixels, so the median ignores them."""
    h, w = plane.shape
    if h < 3 or w < 3:
        return 0.0
    band = 66
    starts = range(0, max(1, h - band + 2), band - 2)
    skip = max(1, round(h * w / 1_500_000))
    responses = []
    for start in list(starts)[::skip]:
        p = plane[start:start + band]
        if len(p) < 3:
            continue
        r = (p[:-2, :-2] + p[:-2, 2:] + p[2:, :-2] + p[2:, 2:] - 2 * (p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2]
                                                                       + p[1:-1, 2:]) + 4 * p[1:-1, 1:-1])
        responses.append(np.abs(r).ravel())
    # A unit-variance white noise has 36 times that variance after the kernel.
    return float(np.median(np.concatenate(responses))) / (0.6745 * 6)


def _lambda(strength):
    """How different two patches may be, in units of the noise, before they stop counting as the same."""
    return 0.3 + 1.2 * strength / 100


def _nlm(guides, targets, floor, search, opacity=None):
    """Non-local means. Every pixel of each ``targets`` plane becomes the weighted mean of the
    pixels within ``search`` of it: a candidate counts as much as its 5 x 5 patch looks like the
    pixel's own in the ``guides`` planes (already scaled so the summed squared differences are
    dimensionless; ``floor`` is what pure noise adds up to, which costs nothing). ``opacity``
    weights candidates so that transparent pixels never colour their neighbours."""
    h, w = guides[0].shape
    m = search + PATCH
    mode = "reflect" if min(h, w) > m else "edge"
    guides = [np.pad(g, m, mode=mode) for g in guides]
    padded = [np.pad(t, m, mode=mode) for t in targets]
    alpha = None if opacity is None else np.pad(opacity, m, mode=mode)
    # Every position within two pixels, then every other one (a checkerboard) farther out: the same
    # noise reduction as the full window at about 60% of the cost.
    offsets = [(dy, dx) for dy in range(-search, search + 1) for dx in range(-search, search + 1)
               if (dy or dx) and (max(abs(dy), abs(dx)) <= 2 or (dy + dx) % 2 == 0)]
    result = [np.empty((h, w), np.float32) for _ in targets]
    span = 2 * PATCH

    def strip(first, last):
        n = last - first
        rows, cols = slice(m + first, m + last), slice(m, m + w)
        near = [g[m + first - PATCH:m + last + PATCH, m - PATCH:m + w + PATCH] for g in guides]
        centre = [t[rows, cols] for t in padded]
        own = np.ones((n, w), np.float32) if alpha is None else alpha[rows, cols]
        total = [c * own for c in centre]
        weights = own.copy()
        for dy, dx in offsets:
            d = None
            for g, a in zip(guides, near):
                diff = a - g[m + first - PATCH + dy:m + last + PATCH + dy, m - PATCH + dx:m + w + PATCH + dx]
                diff *= diff
                d = diff if d is None else np.add(d, diff, out=d)
            vertical = d[:n].copy()
            for k in range(1, span + 1):
                vertical += d[k:k + n]
            patch = vertical[:, :w].copy()
            for k in range(1, span + 1):
                patch += vertical[:, k:k + w]
            patch -= floor
            np.maximum(patch, 0, out=patch)
            np.negative(patch, out=patch)
            weight = np.exp(patch, out=patch)
            if alpha is not None:
                weight *= alpha[m + first + dy:m + last + dy, m + dx:m + w + dx]
            for plane, t in zip(total, padded):
                plane += weight * t[m + first + dy:m + last + dy, m + dx:m + w + dx]
            weights += weight
        for k, (plane, c) in enumerate(zip(total, centre)):
            mean = plane / np.maximum(weights, 1e-6)
            result[k][first:last] = mean if alpha is None else np.where(own > 0, mean, c)

    step = max(8, STRIP_PIXELS // w)
    bands = [(first, min(first + step, h)) for first in range(0, h, step)]
    workers = max(1, min(4, os.cpu_count() or 1, len(bands)))
    if workers == 1:
        for band in bands:
            strip(*band)
    else:
        with ThreadPoolExecutor(workers) as pool:
            list(pool.map(lambda band: strip(*band), bands))
    return result


def _resize(plane, size, filter):
    return np.asarray(Image.fromarray(plane).resize(size, filter), np.float32)


def denoise_image(image, effect):
    """The RGBA ``image`` with luminance and chroma noise reduced as the ``denoise`` effect asks."""
    luminance, chroma, search = settings(effect)
    if luminance <= 0 and chroma <= 0:
        return image.copy()
    source = np.asarray(image.convert("RGBA"))
    h, w = source.shape[:2]
    if min(h, w) < 4:
        return image.copy()
    rgb = source[..., :3].astype(np.float32)
    opacity = None if source[..., 3].min() == 255 else source[..., 3].astype(np.float32) / 255
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    y = 0.299 * r + 0.587 * g + 0.114 * b
    cb, cr = (b - y) * 0.564, (r - y) * 0.713
    if luminance > 0:
        k = 1 / (_lambda(luminance) * max(noise_level(y), NOISE_FLOOR) * (2 * PATCH + 1))
        (y,) = _nlm([y * k], [y], 2 / _lambda(luminance) ** 2, search, opacity)
    if chroma > 0:
        # Colour noise comes in blotches: smooth it at reduced resolution, steered by the luminance.
        factor = 2 if chroma <= 60 else 4
        size = (max(1, round(w / factor)), max(1, round(h / factor)))
        planes = (y, cb, cr)
        if opacity is None:
            small = [_resize(plane, size, Image.Resampling.BOX) for plane in planes]
            small_opacity = None
        else:
            # Average only the visible pixels, so what lies under transparency does not tint the edge.
            small_opacity = _resize(opacity, size, Image.Resampling.BOX)
            small = [_resize(plane * opacity, size, Image.Resampling.BOX) / np.maximum(small_opacity, 1e-3)
                     for plane in planes]
        sigma = [max(noise_level(plane), NOISE_FLOOR / 2) for plane in small[1:]]
        # Blotches are too smooth for the noise estimate to see, so the tolerance also grows with
        # the strength alone (levels of chroma that count as the same colour).
        tolerance = [max(CHROMA_LEVELS * chroma / 100, _lambda(chroma) * s) for s in sigma]
        scale = [1 / (t * (2 * PATCH + 1)) for t in tolerance]
        guide = [small[0] * LUMA_GUIDE * scale[0], small[1] * scale[0], small[2] * scale[1]]
        floor = 2 * sum((s / t) ** 2 for s, t in zip(sigma, tolerance))
        cb_s, cr_s = _nlm(guide, small[1:], floor, max(2, round(search * 0.75)), small_opacity)
        cleaned = []
        for full, low, kept in ((cb, small[1], cb_s), (cr, small[2], cr_s)):
            # What the reduced copy cannot hold (a colour edge, a fine line) goes back in where it
            # stands out from the noise, so colour edges keep their full-resolution sharpness.
            detail = full - _resize(low, (w, h), Image.Resampling.BILINEAR)
            limit = max(2 * noise_level(detail), CHROMA_DETAIL * CHROMA_LEVELS * chroma / 100)
            keep = np.clip((np.abs(detail) - limit) / limit, 0, 1)
            cleaned.append(_resize(kept, (w, h), Image.Resampling.BILINEAR) + detail * keep)
        cb, cr = cleaned
    r = y + cr / 0.713
    b = y + cb / 0.564
    g = (y - 0.299 * r - 0.114 * b) / 0.587
    out = source.copy()
    cleaned = np.clip(np.stack([r, g, b], axis=-1) + 0.5, 0, 255).astype(np.uint8)
    out[..., :3] = cleaned if opacity is None else np.where(source[..., 3:] > 0, cleaned, source[..., :3])
    return Image.fromarray(out)
