"""Seeded seamless patterns, drawn fills, and undoable snapshot-based clone stamping.

Generated fills are raster overlays, keeping the source vector editable underneath.
Clone coordinates are destination-layer pixels; sample_all uses canvas coordinates.
"""
from copy import deepcopy
import math

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .errors import require
from .model import finite, new_layer

TYPES = ("pattern-define", "pattern-fill", "pattern-stroke", "drawn-texture", "clone-stamp")
# name: (family, what it looks like). Every built-in repeats every two cells of `spacing`.
PATTERN_INFO = {
    "stripes": ("geometric", "Even parallel bands."),
    "dots": ("geometric", "Small dots on a square grid."),
    "halftone": ("geometric", "Large print-style dots on a square grid."),
    "hatching": ("geometric", "Thin crossing diagonal lines."),
    "grid": ("geometric", "Thin square grid lines."),
    "checker": ("geometric", "Alternating squares."),
    "noise": ("material", "Fine seeded value noise."),
    "paper": ("material", "Quiet paper tooth."),
    "fabric": ("textile", "Soft woven ripple."),
    "wood": ("natural", "Wavy wood rings."),
    "stone": ("material", "Mottled stone with bright flecks."),
    "scales": ("natural", "Overlapping scale outlines."),
    "diagonal-stripes": ("geometric", "Bands at 45 degrees."),
    "pinstripes": ("geometric", "Thin, widely spaced lines."),
    "chevron": ("geometric", "Stacked V-shaped bands."),
    "zigzag": ("geometric", "Thin zigzag lines."),
    "waves": ("geometric", "Smooth wavy bands."),
    "herringbone": ("geometric", "Columns of slanted strokes alternating direction."),
    "diamonds": ("geometric", "Diamonds on a square grid."),
    "argyle": ("geometric", "Two-tone diamond checker with overstitched lines."),
    "triangles": ("geometric", "Each cell split into two triangles."),
    "honeycomb": ("geometric", "Hexagon cell outlines."),
    "bricks": ("geometric", "Running-bond brick courses with mortar lines."),
    "basketweave": ("geometric", "Alternating horizontal and vertical strand blocks."),
    "plaid": ("textile", "Crossing bands of two widths, tartan-like."),
    "gingham": ("textile", "Two-tone checked cloth with overlapping bands."),
    "polka": ("geometric", "Staggered round dots."),
    "crosses": ("geometric", "Plus signs on a grid."),
    "rings": ("geometric", "Concentric circles in each cell."),
    "squares": ("geometric", "Concentric squares in each cell."),
    "dashes": ("geometric", "Staggered short dashes."),
    "houndstooth": ("textile", "Broken check with hooked diagonals."),
    "dot-grid": ("geometric", "Tiny dots at grid intersections, notebook-style."),
    "graph-paper": ("geometric", "Fine grid with a heavier line every cell."),
    "isometric-grid": ("geometric", "Three line families for isometric sketching."),
    "dither": ("geometric", "Ordered (Bayer) dither of soft noise, retro pixel look."),
    "linen": ("textile", "Fine irregular threads with slubs."),
    "canvas": ("textile", "Tight artist-canvas weave."),
    "burlap": ("textile", "Coarse open weave with gaps."),
    "denim": ("textile", "Diagonal twill with faded streaks."),
    "corduroy": ("textile", "Soft vertical ribs."),
    "knit": ("textile", "Columns of V-shaped stitches."),
    "carbon-fiber": ("textile", "Woven carbon twill with highlights."),
    "tweed": ("textile", "Speckled flecked wool."),
    "quilted": ("textile", "Diamond stitching with puffy shading."),
    "marble": ("material", "Swirling veins."),
    "granite": ("material", "Dense multi-tone speckle."),
    "concrete": ("material", "Soft mottling with pits."),
    "terrazzo": ("material", "Scattered chips in a quiet ground."),
    "cork": ("material", "Small tonal granules with pores."),
    "rust": ("material", "Blotchy corrosion with pitting."),
    "brushed-metal": ("material", "Fine horizontal streaks."),
    "leather": ("material", "Pebbled grain with creases."),
    "corrugated": ("material", "Shaded parallel ridges."),
    "kraft-paper": ("material", "Paper with visible fibres."),
    "watercolor-paper": ("material", "Cold-press paper bumps."),
    "cracked": ("natural", "Dry-earth cracks between plates."),
    "cobblestone": ("natural", "Rounded stones with dark joints."),
    "mosaic": ("material", "Irregular tiles in varied tones with grout."),
    "cells": ("natural", "Thin Voronoi cell walls."),
    "bubbles": ("natural", "Ring outlines of varied sizes."),
    "sand": ("natural", "Fine grain with wind ripples."),
    "clouds": ("natural", "Soft billowing clouds."),
    "camouflage": ("natural", "Three-tone organic blotches."),
    "topographic": ("natural", "Contour lines of a seeded terrain."),
    "caustics": ("natural", "Rippling light network seen under water."),
    "bark": ("natural", "Vertical furrowed tree bark."),
    "leopard": ("natural", "Broken rosettes with lighter centres."),
    "giraffe": ("natural", "Large patches with light borders."),
    "zebra": ("natural", "Warped bold stripes."),
    "confetti": ("natural", "Scattered round flecks."),
    "starfield": ("natural", "Sparse stars of varied size."),
}
PATTERNS = tuple(PATTERN_INFO)
# Organic fills read as repeats at the 16 px default, so they default to a larger cell.
DEFAULT_SPACING = {name: 64 if family in ("material", "natural") else 24
                   for name, (family, _) in list(PATTERN_INFO.items())[12:] if family != "geometric"}
DRAWN_INFO = {
    "pencil": "Graphite lines with paper tooth.",
    "charcoal": "Pooled smoky coverage broken by tooth.",
    "crayon": "Waxy broad strokes skipping over tooth.",
    "ink-wash": "Pooled translucent ink.",
    "stipple": "Scattered ink dots.",
    "hatch": "Fine parallel strokes.",
    "cross-hatch": "Two crossing families of strokes.",
    "scribble": "Looping hand-drawn scribbles.",
    "spatter": "Flicked ink drops of varied size.",
    "dry-brush": "Streaky broken horizontal brush strokes.",
    "pastel": "Soft chalky strokes with heavy tooth dropout.",
    "smudge": "Blended soft charcoal smears.",
    "marker": "Broad felt-tip strokes with overlaps.",
}
DRAWN = tuple(DRAWN_INFO)


def schemas(add):
    original_add = add
    descriptions = {
        "name": "Name of the resulting layer or saved pattern.", "selection": "Capture the current canvas selection as the tile.",
        "seamless": "Reject custom tiles whose edge discontinuity exceeds the seam heuristic.",
        "pattern": "Built-in or document custom pattern; discover with pattern-list.",
        "scale": "Texture scale multiplier.", "rotation": "Pattern rotation in degrees.",
        "offset": "Pattern phase [x,y] in pixels.", "spacing": "Base pattern cell spacing in pixels (2–256); built-ins repeat every two cells. Default 16, 24 for the newer textiles and 64 for the newer material and natural fills (pattern-list default_spacing).",
        "colors": "Foreground and background color pair.", "seed": "Unsigned 32-bit deterministic random seed.",
        "opacity": "Paint or overlay opacity from 0 to 1.", "points": "Stroke path points in destination-layer pixels (pattern strokes use canvas pixels).",
        "size": "Brush diameter in pixels (1–2048).", "preset": "Drawn medium recipe.", "color": "Mark color.",
        "strength": "Texture coverage strength from 0 to 1.", "jitter": "Line position wobble from 0 to 1.",
        "pressure": "Simulated stroke coverage variation from 0 to 1.", "grain": "Paper tooth interaction from 0 to 1.",
        "source": "Sample anchor [x,y] in layer pixels, or canvas pixels with sample_all.",
        "strokes": "Separate brush paths; non-aligned mode resets sampling to source for each path.",
        "hardness": "Brush edge hardness from 0 (soft) to 1 (hard).", "brush": "Round or square clone brush tip.",
        "tile_variation": "Per-tile tone variation from 0 to 1: each repeat of the tile is lightened or darkened by its own seeded amount, so a large fill does not read as a grid.",
        "aligned": "Preserve the source-to-destination offset across separate strokes (default true).",
        "sample_all": "Sample the rendered canvas snapshot instead of the target raster (default false).",
    }
    summaries = {"pattern-define": "Save a selection or rendered layer as an embedded repeatable tile with a seam report.",
                 "pattern-fill": "Overlay a transformed seamless pattern clipped to an existing layer silhouette.",
                 "pattern-stroke": "Paint a repeatable pattern along a brush path.",
                 "drawn-texture": "Add a seeded hand-drawn texture overlay while keeping the source vector editable.",
                 "clone-stamp": "Clone pixels from a frozen source snapshot with aligned or restarting brush strokes."}
    def add(kind, properties, required=(), **extra):
        properties = {key: {**value, "description": value.get("description", descriptions[key])} for key, value in properties.items()}
        original_add(kind, properties, required, description=summaries[kind], **extra)
    from .schema import S, N, B
    point = {"type": "array", "items": N, "minItems": 2, "maxItems": 2}
    points = {"type": "array", "items": point, "minItems": 1, "maxItems": 10000}
    params = {"pattern": {"type": "string", "examples": list(PATTERNS), "description": f"Built-in pattern ({len(PATTERNS)} geometric, textile, material and natural fills listed with descriptions by pattern-list, e.g. stripes, herringbone, plaid, marble, terrazzo, topographic) or the name of a pattern saved in the document with pattern-define."}, "scale": {"type": "number", "exclusiveMinimum": 0}, "rotation": N,
              "offset": point, "spacing": {"type": "number", "minimum": 2, "maximum": 256},
              "colors": {"type": "array", "items": S, "minItems": 2, "maxItems": 2}, "seed": {"type": "integer"},
              "tile_variation": {"type": "number", "minimum": 0, "maximum": 1}}
    add("pattern-define", {"name": S, "selection": B, "seamless": B}, ["name"])
    add("pattern-fill", {**params, "name": S, "opacity": N}, ["pattern"])
    add("pattern-stroke", {**params, "name": S, "points": points, "size": N, "opacity": N}, ["pattern", "points"])
    add("drawn-texture", {"name": S, "preset": {"enum": list(DRAWN)}, "color": S, "seed": {"type": "integer"},
                          "strength": N, "scale": N, "jitter": N, "pressure": N, "grain": N}, ["preset"])
    add("clone-stamp", {"source": point, "points": points, "strokes": {"type": "array", "items": points, "maxItems": 256},
                        "size": N, "hardness": N, "opacity": N, "brush": {"enum": ["round", "square"]},
                        "aligned": B, "sample_all": B}, ["source"],
        oneOf=[{"required": ["points"], "not": {"required": ["strokes"]}},
               {"required": ["strokes"], "not": {"required": ["points"]}}])


def catalog(project=None):
    return {"builtins": list(PATTERNS), "custom": sorted((project.state.get("patterns") or {}) if project else {}),
            "families": {family: [name for name, info in PATTERN_INFO.items() if info[0] == family]
                         for family in ("geometric", "textile", "material", "natural")},
            "descriptions": {name: info[1] for name, info in PATTERN_INFO.items()},
            "default_spacing": {name: DEFAULT_SPACING.get(name, 16) for name in PATTERNS},
            "drawn": list(DRAWN), "drawn_descriptions": dict(DRAWN_INFO), "operations": list(TYPES),
            "parameters": ["scale", "rotation", "offset", "spacing", "colors", "seed", "tile_variation"]}


def seamless_check(image):
    values = np.asarray(image.convert("RGBA"), dtype=float)
    # Edge discontinuities are compared to ordinary adjacent-pixel variation, avoiding
    # false positives for deliberately sharp pattern edges.
    edge = (np.abs(values[:, 0] - values[:, -1]).mean() + np.abs(values[0] - values[-1]).mean()) / 2
    internal = (np.abs(np.diff(values, axis=0)).mean() if image.height > 1 else 0)
    internal += (np.abs(np.diff(values, axis=1)).mean() if image.width > 1 else 0)
    internal /= 2
    return {"seamless": bool(edge <= max(8, internal * 2)), "edge_error": round(float(edge), 3),
            "interior_variation": round(float(internal), 3), "method": "RGBA boundary variation heuristic; inspect a 3x3 repeat"}


def _colors(project, values):
    from .design import resolve_color
    from .render import color
    require(isinstance(values, list) and len(values) == 2, "Pattern needs two colors")
    return [np.array(color(resolve_color(v, project.state)), dtype=float) for v in values]


def pattern_image(project, size, options):
    name = options["pattern"]
    require(name in PATTERNS or name in project.state.get("patterns", {}), "Unknown pattern; use pattern-list")
    scale = finite(options.get("scale", 1), "scale", 0.05, 100)
    spacing = finite(options.get("spacing", DEFAULT_SPACING.get(name, 16)), "spacing", 2, 256)
    angle = math.radians(finite(options.get("rotation", 0), "rotation", -36000, 36000))
    offset = options.get("offset", [0, 0])
    require(isinstance(offset, list) and len(offset) == 2, "Offset is [x,y]")
    for v in offset:
        finite(v, "offset", -1e6, 1e6)
    project.limits.size(*size)
    output = np.empty((size[1], size[0], 4), dtype=np.uint8)
    custom = project.image(project.state["patterns"][name]["asset"]) if name not in PATTERNS else None
    custom_values = np.asarray(custom) if custom else None
    fg, bg = _colors(project, options.get("colors", ["#333333", "#f3ecdc"]))
    seed = options.get("seed", 0)
    require(isinstance(seed, int) and 0 <= seed <= 2**32 - 1, "Seed must be an unsigned 32-bit integer")
    noise_tile = np.random.default_rng(seed).random((32, 32))
    fields = _Fields(seed)
    variation = finite(options.get("tile_variation", 0), "tile_variation", 0, 1)
    # Chunked coordinates keep full-canvas textures within the document's pixel budget.
    for top in range(0, size[1], 128):
        y, x = np.mgrid[top:min(top + 128, size[1]), :size[0]].astype(float)
        x, y = (x - offset[0]) / scale, (y - offset[1]) / scale
        u, v = x * math.cos(angle) + y * math.sin(angle), -x * math.sin(angle) + y * math.cos(angle)
        if custom:
            rows = custom_values[np.floor(v).astype(int) % custom.height, np.floor(u).astype(int) % custom.width]
            if variation:
                rows = _vary(rows, np.floor(u / custom.width), np.floor(v / custom.height), seed, variation)
            output[top:top + len(y)] = rows
            continue
        u, v = u / spacing, v / spacing
        a, b = u % 1, v % 1
        # Wrap a seeded random field in two cells. Interpolate for material variation,
        # preserve fine grain for noise/paper; opposing tile neighborhoods are periodic.
        nx, ny = (u * 16) % 32, (v * 16) % 32
        ix, iy = np.floor(nx).astype(int), np.floor(ny).astype(int)
        fx, fy = nx - ix, ny - iy
        noise = (noise_tile[iy, ix] * (1-fx) * (1-fy) + noise_tile[iy, (ix+1)%32] * fx * (1-fy) +
                 noise_tile[(iy+1)%32, ix] * (1-fx) * fy + noise_tile[(iy+1)%32, (ix+1)%32] * fx * fy)
        if name == "stripes":
            coverage = a < .35
        elif name in ("dots", "halftone"):
            coverage = (a-.5)**2 + (b-.5)**2 < (.2 if name == "dots" else .35)**2
        elif name == "hatching":
            coverage = ((u+v) % 1 < .12) | ((u-v) % 1 < .12)
        elif name == "grid":
            coverage = (a < .06) | (b < .06)
        elif name == "checker":
            coverage = (np.floor(u).astype(int) + np.floor(v).astype(int)) % 2
        elif name == "fabric":
            coverage = .3 + .3*np.sin(u*2*np.pi)*np.sin(v*2*np.pi) + .2*(a<.1)
        elif name == "wood":
            coverage = .5 + .4*np.sin(2*np.pi*(u + .3*np.sin(2*np.pi*v)))
        elif name == "stone":
            coverage = np.where(noise > .72, .85, .15 + .6*noise)
        elif name == "scales":
            dx = ((u + .5*(np.floor(v).astype(int)%2)) % 1) - .5
            distance = np.sqrt(dx*dx + (b-.05)**2)
            coverage = (distance > .48) & (distance < .58)
        elif name in _EXTRA:
            coverage = _EXTRA[name](u, v, a, b, fields)
        else:
            coverage = noise if name == "noise" else .1 + .25*noise
        coverage = np.clip(np.asarray(coverage, dtype=float), 0, 1)[..., None]
        rows = np.uint8(np.clip(bg + (fg-bg)*coverage, 0, 255))
        if variation:
            rows = _vary(rows, np.floor(u), np.floor(v), seed, variation)
        output[top:top + len(y)] = rows
    return Image.fromarray(output)


class _Fields:
    """Seeded periodic noise for the procedural patterns.

    Pattern coordinates are in cells; every field here repeats every two cells so fills tile seamlessly
    and match the period of the original patterns."""

    def __init__(self, seed):
        self.seed = seed
        self._tiles = {}

    def _tile(self, key, shape):
        if key not in self._tiles:
            self._tiles[key] = np.random.default_rng([self.seed, *key]).random(shape)
        return self._tiles[key]

    def value(self, u, v, fu, fv=None):
        """Smooth value noise with fu lattice points per cell across and fv down."""
        fv = fu if fv is None else fv
        tile = self._tile((1, fu, fv), (2 * fv, 2 * fu))
        x, y = (u * fu) % (2 * fu), (v * fv) % (2 * fv)
        ix, iy = np.floor(x).astype(int), np.floor(y).astype(int)
        fx, fy = x - ix, y - iy
        fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
        jx, jy = (ix + 1) % (2 * fu), (iy + 1) % (2 * fv)
        top = tile[iy, ix] * (1 - fx) + tile[iy, jx] * fx
        bottom = tile[jy, ix] * (1 - fx) + tile[jy, jx] * fx
        return top * (1 - fy) + bottom * fy

    def fbm(self, u, v, base=1, octaves=4):
        cached = self._tiles.get(("fbm", base, octaves))
        if cached and cached[0] is u and cached[1] is v:
            return cached[2]
        total, weight, norm = 0, 1, 0
        for octave in range(octaves):
            total = total + weight * self.value(u, v, base << octave)
            norm += weight
            weight /= 2
        self._tiles[("fbm", base, octaves)] = (u, v, total / norm)
        return total / norm

    def worley(self, u, v, n):
        """Distances to the nearest and second-nearest of n x n jittered points per two cells, and the
        nearest point's seeded tone."""
        # Patterns ask for the same field several times per chunk; the identity check keeps the
        # cache to the chunk being drawn.
        cached = self._tiles.get(("worley", n))
        if cached and cached[0] is u and cached[1] is v:
            return cached[2]
        result = self._worley(u, v, n)
        self._tiles[("worley", n)] = (u, v, result)
        return result

    def edge(self, u, v, n):
        """Distance from the wall between two Worley cells (0 on the wall)."""
        f1, f2, _ = self.worley(u, v, n)
        return f2 - f1

    def _worley(self, u, v, n):
        points = self._tile((2, n), (n, n, 3))
        x, y = (u * n / 2) % n, (v * n / 2) % n
        ix, iy = np.floor(x).astype(int), np.floor(y).astype(int)
        f1 = np.full(x.shape, np.inf)
        f2 = np.full(x.shape, np.inf)
        tone = np.zeros(x.shape)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                cx, cy = ix + dx, iy + dy
                point = points[cy % n, cx % n]
                d = np.hypot(cx + point[..., 0] - x, cy + point[..., 1] - y)
                closer = d < f1
                f2 = np.where(closer, f1, np.minimum(f2, d))
                tone = np.where(closer, point[..., 2], tone)
                f1 = np.where(closer, d, f1)
        return f1, f2, tone


_BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16 + 1 / 32


def _honeycomb(u, v):
    # Rows one cell apart, every other row shifted half a cell: period one cell across, two down.
    f1 = np.full(u.shape, np.inf)
    f2 = np.full(u.shape, np.inf)
    row = np.floor(v)
    for dr in (-1, 0, 1, 2):
        r = row + dr
        shift = .5 * (r % 2)
        column = np.floor(u - shift)
        for dc in (-1, 0, 1):
            d = np.hypot(column + dc + shift + .5 - u, r - v)
            f2 = np.where(d < f1, f1, np.minimum(f2, d))
            f1 = np.minimum(f1, d)
    return f2 - f1 < .08


def _parity(*values):
    return sum(np.floor(value).astype(int) for value in values) % 2


def _plaid(a, b):
    def band(t):
        return .5 * (t < .3) + .5 * (np.abs(t - .65) < .025)
    return .9 * np.minimum(1, band(a) + band(b))


def _burlap(u, v, f):
    across, down = (u * 2) % 1 < .72, (v * 2) % 1 < .72
    over = _parity(u * 2, v * 2)
    shade = np.where(across & down, np.where(over, .8, .6), np.where(down, .65, np.where(across, .55, 0)))
    return shade * (.75 + .25 * f.value(u, v, 8))


def _knit(u, v):
    x = (u * 3) % 1
    stitch = ((v * 4 + np.abs(x - .5) * 1.4) % 1) < .55
    return .25 + .5 * stitch - .15 * (np.abs(x - .5) > .45)


def _carbon(u, v):
    pu, pv = (u * 4) % 1, (v * 4) % 1
    light = np.where(_parity(u * 4, v * 4) == 0, pu, pv)
    return .85 - .5 * 4 * light * (1 - light)


def _caustics(u, v, f):
    edge = f.edge(u + .3 * f.value(u, v, 2), v, 6)
    return np.clip(1 - 5 * edge, 0, 1) ** 2


def _leopard(u, v, f):
    f1, _, tone = f.worley(u, v, 4)
    ring = (f1 > .2) & (f1 < .33) & (f.value(u, v, 8) > .35)
    return np.where(ring, 1, np.where(f1 < .2, .35 + .1 * tone, 0))


def _terrazzo(u, v, f):
    f1, _, tone = f.worley(u, v, 10)
    chip = f1 < .2 + .15 * f.value(u, v, 16) * (tone > .3)
    return np.where(chip, .35 + .65 * tone, .05 + .08 * f.value(u, v, 16))


_EXTRA = {
    "diagonal-stripes": lambda u, v, a, b, f: (u + v) % 1 < .35,
    "pinstripes": lambda u, v, a, b, f: a < .08,
    "chevron": lambda u, v, a, b, f: (v + np.abs(a - .5)) % 1 < .35,
    "zigzag": lambda u, v, a, b, f: (v + np.abs(a - .5)) % 1 < .1,
    "waves": lambda u, v, a, b, f: np.abs((v + .2 * np.sin(2 * np.pi * u)) % 1 - .5) < .15,
    "herringbone": lambda u, v, a, b, f: (np.where(np.floor(u) % 2 == 0, u + v, v - u) * 2) % 1 < .4,
    "diamonds": lambda u, v, a, b, f: np.abs(a - .5) + np.abs(b - .5) < .4,
    "argyle": lambda u, v, a, b, f: np.where(((u + v + .5) % 1 < .04) | ((u - v + .5) % 1 < .04), 1,
                                             .55 * _parity(u + v, u - v)),
    "triangles": lambda u, v, a, b, f: b > a,
    "honeycomb": lambda u, v, a, b, f: _honeycomb(u, v),
    "bricks": lambda u, v, a, b, f: ((v * 2) % 1 < .12) | ((u + .5 * (np.floor(v * 2) % 2)) % 1 < .06),
    "basketweave": lambda u, v, a, b, f: np.where((np.where(_parity(u, v), a, b) * 3) % 1 < .15, 1, .35),
    "plaid": lambda u, v, a, b, f: _plaid(a, b),
    "gingham": lambda u, v, a, b, f: .5 * (a < .5) + .5 * (b < .5),
    "polka": lambda u, v, a, b, f: (((u + .5 * (np.floor(v) % 2)) % 1) - .5) ** 2 + (b - .5) ** 2 < .22 ** 2,
    "crosses": lambda u, v, a, b, f: ((np.abs(a - .5) < .07) & (np.abs(b - .5) < .28)) |
                                     ((np.abs(b - .5) < .07) & (np.abs(a - .5) < .28)),
    "rings": lambda u, v, a, b, f: (np.hypot(a - .5, b - .5) < .5) & ((np.hypot(a - .5, b - .5) * 6) % 1 < .4),
    "squares": lambda u, v, a, b, f: (np.maximum(np.abs(a - .5), np.abs(b - .5)) * 6) % 1 < .4,
    "dashes": lambda u, v, a, b, f: ((u + .5 * (np.floor(v) % 2)) % 1 < .5) & (np.abs(b - .5) < .08),
    "houndstooth": lambda u, v, a, b, f: np.where((a < .5) == (b < .5), a < .5, (a * 4 - b * 4) % 2 < 1),
    "dot-grid": lambda u, v, a, b, f: np.minimum(a, 1 - a) ** 2 + np.minimum(b, 1 - b) ** 2 < .1 ** 2,
    "graph-paper": lambda u, v, a, b, f: np.where((a < .04) | (b < .04), 1,
                                                  .4 * (((u * 4) % 1 < .06) | ((v * 4) % 1 < .06))),
    "isometric-grid": lambda u, v, a, b, f: ((v + .5 * u) % 1 < .05) | ((v - .5 * u) % 1 < .05) | (a < .04),
    "dither": lambda u, v, a, b, f: f.fbm(u, v, 2) > _BAYER[np.floor(v * 8).astype(int) % 4,
                                                          np.floor(u * 8).astype(int) % 4],
    "linen": lambda u, v, a, b, f: .1 + .3 * f.value(u, v, 2, 16) + .3 * f.value(u, v, 16, 2)
                                   + .1 * np.sin(8 * np.pi * u) * np.sin(8 * np.pi * v),
    "canvas": lambda u, v, a, b, f: .35 + .25 * np.sin(8 * np.pi * u) * np.sin(8 * np.pi * v) + .2 * f.value(u, v, 16),
    "burlap": lambda u, v, a, b, f: _burlap(u, v, f),
    "denim": lambda u, v, a, b, f: .45 + .3 * ((np.floor(u * 6) + np.floor(v * 6)) % 3 == 0)
                                   + .15 * f.value(u, v, 8) - .35 * (f.value(u, v, 2, 32) > .82),
    "corduroy": lambda u, v, a, b, f: .2 + .55 * np.sin(np.pi * u * 3) ** 2 + .15 * f.value(u, v, 4, 16),
    "knit": lambda u, v, a, b, f: _knit(u, v),
    "carbon-fiber": lambda u, v, a, b, f: _carbon(u, v),
    "tweed": lambda u, v, a, b, f: .3 + .2 * f.fbm(u, v, 2) + .4 * (f.value(u, v, 16) > .78)
                                   - .25 * (f.value(u, v, 16, 8) < .15),
    "quilted": lambda u, v, a, b, f: np.where(((u + v) % 1 < .04) | ((u - v) % 1 < .04), 1,
                                              .1 + .5 * np.minimum((u + v) % 1, (u - v) % 1)),
    "marble": lambda u, v, a, b, f: (1 - np.abs(np.sin(np.pi * (u + v + 2.5 * f.fbm(u, v, 2))))) ** 6,
    "granite": lambda u, v, a, b, f: np.where(f.value(u, v, 32) > .72, 1,
                                              np.where(f.value(u, v, 32, 16) < .25, .5, .1)) + .1 * f.fbm(u, v, 2),
    "concrete": lambda u, v, a, b, f: .15 + .3 * f.fbm(u, v, 2) + .5 * (
        (f.worley(u, v, 8)[0] < .07) & (f.worley(u, v, 8)[2] > .55)),
    "terrazzo": lambda u, v, a, b, f: _terrazzo(u, v, f),
    "cork": lambda u, v, a, b, f: np.where(f.worley(u, v, 16)[0] < .08, .9, .25 + .45 * f.worley(u, v, 16)[2]),
    "rust": lambda u, v, a, b, f: np.where(f.fbm(u, v, 2) > .52, .5 + .5 * f.value(u, v, 32), .15 * f.value(u, v, 16)),
    "brushed-metal": lambda u, v, a, b, f: .3 + .4 * f.value(u, v, 1, 32) + .2 * f.value(u, v, 2, 64),
    "leather": lambda u, v, a, b, f: np.where(f.edge(u, v, 12) < .08, .75,
                                              .2 + .25 * f.worley(u, v, 12)[2]),
    "corrugated": lambda u, v, a, b, f: .5 + .45 * np.sin(4 * np.pi * u),
    "kraft-paper": lambda u, v, a, b, f: .15 + .2 * f.fbm(u, v, 2) + .25 * (f.value(u, v, 32, 4) > .8)
                                         + .25 * (f.value(u, v, 4, 32) > .82),
    "watercolor-paper": lambda u, v, a, b, f: .05 + .35 * np.minimum(1, f.worley(u, v, 12)[0]) + .1 * f.value(u, v, 16),
    "cracked": lambda u, v, a, b, f: np.where(f.edge(u, v, 6) < .05 + .06 * f.value(u, v, 8), 1,
                                              .1 + .2 * f.worley(u, v, 6)[2]),
    "cobblestone": lambda u, v, a, b, f: np.where(f.edge(u, v, 6) < .12, 1,
                                                  .1 + .35 * f.worley(u, v, 6)[2] + .3 * f.worley(u, v, 6)[0]),
    "mosaic": lambda u, v, a, b, f: np.where(f.edge(u, v, 8) < .08, 0,
                                             .3 + .7 * f.worley(u, v, 8)[2]),
    "cells": lambda u, v, a, b, f: f.edge(u, v, 6) < .05,
    "bubbles": lambda u, v, a, b, f: np.abs(f.worley(u, v, 6)[0] - .15 - .25 * f.worley(u, v, 6)[2]) < .035,
    "sand": lambda u, v, a, b, f: .2 + .3 * f.value(u, v, 32) + .2 * np.sin(2 * np.pi * (2 * v + .5 * f.fbm(u, v, 2))),
    "clouds": lambda u, v, a, b, f: (f.fbm(u, v, 2) - .3) * 2.5,
    "camouflage": lambda u, v, a, b, f: np.where(f.fbm(u, v, 2, 3) < .42, 1, np.where(f.fbm(u, v, 2, 3) < .55, .55, .15)),
    "topographic": lambda u, v, a, b, f: (f.fbm(u, v, 2, 2) * 12) % 1 < .1,
    "caustics": lambda u, v, a, b, f: _caustics(u, v, f),
    "bark": lambda u, v, a, b, f: .25 + .55 * (1 - np.abs(np.sin(np.pi * (u * 3 + 1.5 * f.value(u, v, 2, 1))))) ** 2
                                  + .2 * f.value(u, v, 16, 4),
    "leopard": lambda u, v, a, b, f: _leopard(u, v, f),
    "giraffe": lambda u, v, a, b, f: np.where(f.edge(u, v, 5) < .1 + .05 * f.value(u, v, 8), 0, .85),
    "zebra": lambda u, v, a, b, f: np.sin(2 * np.pi * (u * 2 + 1.5 * f.fbm(u, v, 2, 2))) > .1,
    "confetti": lambda u, v, a, b, f: (f.worley(u, v, 8)[0] < .22) & (f.worley(u, v, 8)[2] > .45),
    "starfield": lambda u, v, a, b, f: f.worley(u, v, 12)[0] < .05 + .2 * f.worley(u, v, 12)[2] ** 4,
}


def _vary(rows, cell_x, cell_y, seed, amount):
    """Lighten or darken each tile cell by its own seeded amount (up to 25% at amount 1)."""
    h = np.sin(cell_x * 12.9898 + cell_y * 78.233 + (seed % 9973) * 0.6180339) * 43758.5453
    shift = (h - np.floor(h)) * 2 - 1
    factor = (1 + 0.25 * amount * shift)[..., None]
    rgb = np.clip(rows[..., :3].astype(float) * factor, 0, 255)
    return np.concatenate([np.uint8(rgb), rows[..., 3:]], axis=-1)


def _target_image(project, target):
    from .render import layer_ink, ink_origin, resolve_layout
    layer = project.layer(target)
    bounds = resolve_layout(project)[layer["id"]]
    image = layer_ink(project, layer, bounds)
    x, y = ink_origin(image, bounds)
    return layer, image, [x, y, image.width, image.height]


def _overlay(project, image, source, bounds, name, opacity=1):
    from .assets import add_image
    from .operations import append_layer, default_name
    layer = new_layer(name or default_name(project, "texture"), "raster", image.width, image.height,
                      asset=add_image(project, image), x=bounds[0], y=bounds[1], opacity=opacity)
    if source:
        for key in ("parent",):
            if key in source:
                layer[key] = source[key]
    return append_layer(project, layer)


def drawn_image(image, preset, *, seed=0, color="#25221f", strength=.6, scale=1, jitter=.5, pressure=.5, grain=.5):
    from .render import color as parse_color
    require(preset in DRAWN, "Unknown drawn texture")
    finite(strength, "strength", 0, 1)
    finite(scale, "scale", .1, 20)
    finite(jitter, "jitter", 0, 1)
    finite(pressure, "pressure", 0, 1)
    finite(grain, "grain", 0, 1)
    require(isinstance(seed, int) and 0 <= seed <= 2**32-1, "Seed must be an unsigned 32-bit integer")
    rng = np.random.default_rng(seed)
    w, h = image.size
    mask = Image.new("L", image.size)
    draw = ImageDraw.Draw(mask)
    if preset in ("pencil", "hatch", "crayon"):
        step = max(2, round((5 if preset != "crayon" else 11)*scale))
        for y in range(-w, h+w, step):
            points = [(x, y + x*.3 + rng.uniform(-2,2)*jitter*scale) for x in range(0, w+step, step)]
            draw.line(points, fill=round(255*(1-pressure*rng.uniform(0,.65))),
                      width=max(1, round((3 if preset == "crayon" else 1)*scale)))
    elif preset == "stipple":
        count = min(300000, max(1, round(w*h / (30*scale*scale))))
        for x,y,r in rng.uniform(0,1,(count,3)):
            r = max(.5, r*2*scale)
            draw.ellipse((x*w-r,y*h-r,x*w+r,y*h+r), fill=round(255*(1-pressure*rng.uniform(0,.6))))
    elif preset in ("charcoal", "ink-wash"):
        coarse = Image.fromarray(rng.integers(30,255,(max(2, math.ceil(h/(18*scale))), max(2, math.ceil(w/(18*scale)))), dtype=np.uint8))
        mask = coarse.resize((w,h), Image.Resampling.BICUBIC)
    else:
        mask = _drawn_marks(mask, preset, rng, scale=scale, jitter=jitter, pressure=pressure)
    values = np.asarray(mask, dtype=np.float32)
    tooth = rng.uniform(0,1,(h,w))
    # Felt-tip ink sits on top of the paper; dry media skip over its tooth.
    values *= (1-grain*tooth*(.3 if preset == "marker" else 1)) * strength
    if preset in ("charcoal", "crayon", "pencil", "pastel", "dry-brush"):
        values[tooth > 1-(.4 if preset == "pastel" else .18)*grain] = 0
    mask = ImageChops.multiply(Image.fromarray(np.uint8(values)), image.getchannel("A"))
    overlay = Image.new("RGBA", image.size, parse_color(color))
    mask = ImageChops.multiply(mask, overlay.getchannel("A"))
    overlay.putalpha(mask)
    return overlay


def _drawn_marks(mask, preset, rng, *, scale, jitter, pressure):
    """Coverage mask for the presets added after the original six."""
    w, h = mask.size
    draw = ImageDraw.Draw(mask)

    def tone(spread):
        return round(255*(1-pressure*rng.uniform(0, spread)))

    def lines(step, width, slope, spread=.65):
        for y in range(-round(w*abs(slope))-step, h+round(w*abs(slope))+step, step):
            points = [(x, y + x*slope + rng.uniform(-2, 2)*jitter*scale) for x in range(0, w+step, step)]
            draw.line(points, fill=tone(spread), width=max(1, round(width*scale)))

    if preset == "cross-hatch":
        step = max(2, round(6*scale))
        lines(step, 1, .4)
        lines(step, 1, -1.2)
    elif preset == "pastel":
        lines(max(3, round(9*scale)), 6, .25, .5)
    elif preset == "marker":
        lines(max(3, round(9*scale)), 11, -.35, .35)
    elif preset == "dry-brush":
        step = max(2, round(5*scale))
        for y in range(-step, h+step, step):
            x = rng.uniform(-w*.2, w*.1)
            while x < w:
                length = rng.uniform(.3, .9)*w
                draw.line([(x, y + rng.uniform(-1, 1)*jitter*3*scale), (x+length, y + rng.uniform(-1, 1)*jitter*3*scale)],
                          fill=tone(.5), width=max(1, round(rng.uniform(4, 9)*scale)))
                x += length + rng.uniform(0, .25)*w
        # Bristle streaks: whole rows lose ink together, as a dry brush does.
        streaks = np.clip(rng.uniform(-.2, 1.6, (h, 1)), 0, 1)
        mask = Image.fromarray(np.uint8(np.asarray(mask, dtype=np.float32) * streaks))
    elif preset == "scribble":
        count = min(4000, max(1, round(w*h / (700*scale*scale))))
        for _ in range(count):
            x, y, angle = rng.uniform(0, w), rng.uniform(0, h), rng.uniform(0, 2*math.pi)
            turn = rng.uniform(.08, .35) * rng.choice((-1, 1))
            points = []
            for _ in range(60):
                points.append((x, y))
                angle += turn + rng.uniform(-.4, .4)*(.5+jitter)
                x, y = x + math.cos(angle)*3*scale, y + math.sin(angle)*3*scale
            draw.line(points, fill=tone(.6), width=max(1, round(scale)), joint="curve")
    elif preset == "spatter":
        count = min(200000, max(1, round(w*h / (120*scale*scale))))
        for _ in range(count):
            x, y = rng.uniform(0, w), rng.uniform(0, h)
            r = max(.5, min(12*scale, rng.exponential(1.1*scale)))
            draw.ellipse((x-r, y-r, x+r, y+r), fill=tone(.4))
    elif preset == "smudge":
        coarse = rng.integers(0, 255, (max(2, math.ceil(h/(40*scale))), max(2, math.ceil(w/(40*scale)))), dtype=np.uint8)
        mask = Image.fromarray(coarse).resize((w, h), Image.Resampling.BICUBIC)
        mask = mask.filter(ImageFilter.GaussianBlur(max(1, 6*scale)))
    return mask


def clone_image(destination, source, source_point, strokes, *, size=32, hardness=.8, opacity=1, aligned=True, brush="round"):
    finite(size, "size", 1, 2048)
    finite(hardness, "hardness", 0, 1)
    finite(opacity, "opacity", 0, 1)
    require(isinstance(aligned, bool), "aligned must be boolean")
    require(brush in ("round", "square"), "Clone brush must be round or square")
    require(isinstance(source_point, list) and len(source_point) == 2, "Source is [x,y]")
    for n in source_point:
        finite(n, "source coordinate", -1e6, 1e6)
    require(isinstance(strokes, list) and 0 < len(strokes) <= 256, "Choose 1–256 strokes")
    require(sum(len(s) for s in strokes) <= 10000, "Clone exceeds 10000 points", "resource_limit")
    for stroke in strokes:
        require(stroke, "Clone stroke is empty")
        for point in stroke:
            require(isinstance(point, list) and len(point) == 2, "Clone point is [x,y]")
            for v in point:
                finite(v, "clone coordinate", -1e6, 1e6)
    result = destination.copy()
    diameter = max(1, math.ceil(size))
    y,x = np.mgrid[:diameter,:diameter]
    dx,dy = np.abs((x+.5-diameter/2)/(diameter/2)), np.abs((y+.5-diameter/2)/(diameter/2))
    radius = np.hypot(dx,dy) if brush == "round" else np.maximum(dx,dy)
    coverage = (radius <= 1).astype(float) if hardness == 1 else np.clip((1-radius)/max(1e-6,1-hardness),0,1)
    brush_mask = Image.fromarray(np.uint8(255*opacity*coverage))
    anchor = strokes[0][0]
    dabs = 0
    for stroke in strokes:
        if not aligned:
            anchor = stroke[0]
        pts = [stroke[0]]
        for a,b in zip(stroke,stroke[1:]):
            count = max(1, math.ceil(math.dist(a,b)/max(1,size*.2)))
            require(dabs + len(pts) + count <= 100000 and
                    (dabs + len(pts) + count) * diameter**2 <= 100_000_000,
                    "Clone exceeds dab/pixel budget", "resource_limit")
            pts.extend([[a[0]+(b[0]-a[0])*j/count,a[1]+(b[1]-a[1])*j/count] for j in range(1,count+1)])
        require((dabs + len(pts)) * diameter**2 <= 100_000_000, "Clone exceeds pixel budget", "resource_limit")
        for px,py in pts:
            left,top = round(px-diameter/2),round(py-diameter/2)
            sx,sy = round(source_point[0]+px-anchor[0]-diameter/2),round(source_point[1]+py-anchor[1]-diameter/2)
            patch = source.crop((sx,sy,sx+diameter,sy+diameter))
            patch.putalpha(ImageChops.multiply(patch.getchannel("A"),brush_mask))
            result.alpha_composite(patch,(left,top))
        dabs += len(pts)
    return result


def execute(project, op):
    from .assets import add_image
    kind = op["type"]
    if kind == "clone-stamp":
        layer = project.layer(op.get("target"))
        require(layer["type"] == "raster", "Clone stamp requires a raster layer; rasterize the target first")
        image = project.image(layer["asset"])
        if layer.get("crop"):
            image = image.crop(tuple(layer["crop"]))
        image = image.resize((layer["width"],layer["height"]))
        sample_all = op.get("sample_all", False)
        require(isinstance(sample_all, bool), "sample_all must be boolean")
        if sample_all:
            require(not layer.get("parent") and not layer.get("rotation") and not layer.get("flip_x") and not layer.get("flip_y"),
                    "Sample-all needs an unrotated top-level target")
        source = project.render() if sample_all else image.copy()
        strokes = op.get("strokes", [op["points"]] if "points" in op else [])
        image = clone_image(image, source, op["source"], strokes,
                            **{k:op[k] for k in ("size","hardness","opacity","aligned","brush") if k in op})
        layer["asset"] = add_image(project, image)
        layer.pop("crop", None)
        layer.pop("linked", None)
        return
    if kind == "pattern-define":
        from .design import named
        named(op["name"])
        if op.get("selection"):
            from .operations import selection_image
            image = project.render()
            mask = selection_image(project)
            box = mask.getbbox()
            require(box is not None, "Selection is empty")
            image.putalpha(ImageChops.multiply(image.getchannel("A"),mask))
            image = image.crop(box)
        else:
            _, image, _ = _target_image(project, op.get("target"))
        report = seamless_check(image)
        require(not op.get("seamless", False) or report["seamless"], "Tile has a visible boundary discontinuity", **report)
        patterns = project.state.setdefault("patterns", {})
        require(op["name"] in patterns or len(patterns) < 128, "Pattern library is full", "resource_limit")
        patterns[op["name"]] = {"asset": add_image(project,image), "width": image.width, "height":image.height, "check":report}
        from .selectors import record
        record(project, "patterns", {"name": op["name"], "width": image.width, "height": image.height, "seam": report})
        return report
    if kind == "pattern-stroke":
        canvas = project.state["canvas"]
        size = (canvas["width"],canvas["height"])
        image = pattern_image(project,size,op)
        mask = Image.new("L",size)
        width = round(finite(op.get("size",16),"size",1,2048))
        points = op["points"]
        draw = ImageDraw.Draw(mask)
        draw.line([tuple(p) for p in points],fill=255,width=width,joint="curve")
        for x,y in (points[0],points[-1]):
            draw.ellipse((x-width/2,y-width/2,x+width/2,y+width/2),fill=255)
        image.putalpha(ImageChops.multiply(image.getchannel("A"),mask))
        return _overlay(project,image,None,[0,0,*size],op.get("name"),finite(op.get("opacity",1),"opacity",0,1))
    layer, original, bounds = _target_image(project,op.get("target"))
    if kind == "drawn-texture":
        image = drawn_image(original,op["preset"],**{k:op[k] for k in ("seed","color","strength","scale","jitter","pressure","grain") if k in op})
    else:
        image = pattern_image(project,original.size,op)
        image.putalpha(ImageChops.multiply(image.getchannel("A"),original.getchannel("A")))
    result = _overlay(project,image,layer,bounds,op.get("name"),finite(op.get("opacity",1),"opacity",0,1))
    result["provenance"] = {"type":kind,"source":layer["id"],"parameters":deepcopy(op)}
    return result
