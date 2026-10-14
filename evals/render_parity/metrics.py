"""Image measurements shared by the parity cases. Everything works on float arrays in [0, 1].

``coverage`` turns a render into per-pixel ink coverage between a known background and a known ink
colour, so text and shapes can be compared as coverage maps (what an anti-aliased edge actually is)
instead of as colours."""

import math

import numpy as np


def rgb(image):
    """An image as an (h, w, 3) float array in [0, 1]."""
    return np.asarray(image.convert("RGB"), dtype=np.float64) / 255


def coverage(image, background, ink):
    """Per-pixel coverage of ``ink`` over ``background`` (RGB tuples 0-255): the projection of each
    pixel onto the line between the two colours, clipped to [0, 1]."""
    a = rgb(image)
    bg, fg = np.array(background[:3], float) / 255, np.array(ink[:3], float) / 255
    axis = fg - bg
    return np.clip(((a - bg) @ axis) / max(float(axis @ axis), 1e-9), 0, 1)


def diff(a, b):
    """Whole-image difference of two renders, in 0-255 levels."""
    x, y = rgb(a) * 255, rgb(b) * 255
    d = np.abs(x - y).max(axis=2)
    mse = float(((x - y) ** 2).mean())
    return {
        "mean": round(float(d.mean()), 3),
        "max": int(d.max()),
        "over_3": round(float((d > 3).mean() * 100), 3),
        "over_16": round(float((d > 16).mean() * 100), 3),
        "psnr": round(10 * math.log10(255**2 / mse), 2) if mse > 0 else None,
    }


def bbox(cov, threshold=0.05):
    """Ink box (left, top, right, bottom) of a coverage map with sub-pixel edges: each edge moves
    in by the partial coverage of its outermost column or row."""
    cols, rows = cov.max(axis=0), cov.max(axis=1)
    xs, ys = np.nonzero(cols > threshold)[0], np.nonzero(rows > threshold)[0]
    if not len(xs):
        return None
    left, right, top, bottom = xs[0], xs[-1], ys[0], ys[-1]
    return (
        round(float(left + 1 - cols[left]), 3),
        round(float(top + 1 - rows[top]), 3),
        round(float(right + cols[right]), 3),
        round(float(bottom + rows[bottom]), 3),
    )


def weight(cov):
    """Total ink: the sum of coverage (pixel area). Gamma or contrast tweaks show up here."""
    return float(cov.sum())


def local_shift(a, b, window, search=3.0):
    """Sub-pixel horizontal shift of ``b`` relative to ``a`` inside ``window`` (x0, y0, x1, y1), from
    the peak of the cross-correlation of their column ink profiles (parabolic interpolation)."""
    x0, y0, x1, y1 = (int(v) for v in window)
    pa, pb = a[y0:y1].sum(axis=0), b[y0:y1].sum(axis=0)
    lo, hi = max(0, x0), min(len(pa), x1)
    if hi - lo < 2 or pa[lo:hi].sum() < 1e-6:
        return None
    reach = int(math.ceil(search))
    scores = []
    for s in range(-reach, reach + 1):
        segment = pb[max(0, lo + s):max(0, hi + s)]
        reference = pa[lo:hi][: len(segment)]
        scores.append(float((reference * segment).sum()))
    scores = np.array(scores)
    k = int(scores.argmax())
    offset = 0.0
    if 0 < k < len(scores) - 1:
        left, mid, right = scores[k - 1], scores[k], scores[k + 1]
        denominator = left - 2 * mid + right
        offset = 0.5 * (left - right) / denominator if denominator else 0.0
    return round(k - reach + offset, 3)


def edge(profile):
    """A transect across one rising or falling edge: where it crosses half coverage (sub-pixel, from
    the summed coverage) and how many pixels are partial (0.02-0.98)."""
    p = np.asarray(profile, float)
    if p[0] > p[-1]:
        p = p[::-1]
    position = len(p) - float(p.sum())
    partial = int(((p > 0.02) & (p < 0.98)).sum())
    return {"position": round(position, 3), "partial": partial}


def rise_10_90(profile):
    """Distance in pixels over which an edge transect rises from 10% to 90% of its range."""
    p = np.asarray(profile, float)
    if p[0] > p[-1]:
        p = p[::-1]
    low, high = p.min(), p.max()
    if high - low < 1e-6:
        return None
    q = (p - low) / (high - low)

    def crossing(level):
        i = int(np.argmax(q >= level))
        if i == 0:
            return 0.0
        return i - 1 + (level - q[i - 1]) / max(q[i] - q[i - 1], 1e-9)

    return round(crossing(0.9) - crossing(0.1), 3)


def sigma_from_rise(rise):
    """The Gaussian standard deviation that blurs a hard edge to a 10-90% rise of ``rise`` pixels."""
    return None if rise is None else round(rise / (2 * 1.2815516), 3)


def error(cov, ideal, mask=None):
    """Coverage error against an ideal coverage map, in 0-255 levels (rms, max, and the mean signed
    error, which shows a shape drawn too fat or too thin)."""
    d = (np.asarray(cov) - np.asarray(ideal)) * 255
    if mask is not None:
        d = d[mask]
    return {"rms": round(float(np.sqrt((d**2).mean())), 3), "max": round(float(np.abs(d).max()), 2),
            "bias": round(float(d.mean()), 3)}


def levels(row):
    """Banding in one gradient row (0-255 values): distinct levels, the longest run of one value and
    the largest step between neighbours."""
    r = np.round(np.asarray(row, float) * 255).astype(int) if np.asarray(row).max() <= 1.0 else np.asarray(row, int)
    runs, current = [], 1
    for a, b in zip(r, r[1:]):
        if a == b:
            current += 1
        else:
            runs.append(current)
            current = 1
    runs.append(current)
    return {"distinct": int(len(np.unique(r))), "longest_run": int(max(runs)),
            "max_step": int(np.abs(np.diff(r)).max()) if len(r) > 1 else 0}


def box_blur(a, k):
    """Mean over every k x k window of a 2-D array (valid region only)."""
    c = np.cumsum(np.cumsum(np.pad(np.asarray(a, float), ((1, 0), (1, 0))), axis=0), axis=1)
    return (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]) / (k * k)


def banding(region, k=9):
    """How far a horizontal two-stop gradient region (h, w, one channel in 0-1) is from a straight ramp
    once averaged over k x k pixels (roughly what the eye integrates at normal viewing distance), in
    0-255 levels: quantization steps survive the averaging, dither noise mostly does not. The ramp is
    the least-squares line through the averaged region, so where a renderer puts its endpoints (pixel
    centres or edges) does not count."""
    smooth = box_blur(region, k)
    xs = np.arange(smooth.shape[1])
    slope, offset = np.polyfit(xs, smooth.mean(axis=0), 1)
    return round(float(np.sqrt(((smooth - (slope * xs + offset)) ** 2).mean()) * 255), 4)


def sharpness(cov):
    """Mean of the strongest 2% horizontal and vertical neighbour differences: lower means softer."""
    c = np.asarray(cov, float)
    g = np.concatenate([np.abs(np.diff(c, axis=0)).ravel(), np.abs(np.diff(c, axis=1)).ravel()])
    if not len(g):
        return 0.0
    k = max(1, len(g) // 50)
    return round(float(np.sort(g)[-k:].mean()), 4)
