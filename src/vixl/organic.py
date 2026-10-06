"""Composable organic shapes: generators, growth rules and presets for living things.

An ``organic`` operation describes a living form as ordered **parts**. Each part takes geometry
from a **generator** (a superformula outline, a leaf profile, a branching tree, Vogel
phyllotaxis, Voronoi cells, a reaction–diffusion pattern …), then applies **rules** in order
(radial symmetry and whorls, mirroring, placement along a spine or at another part's anchors,
scatter, noise, bending, tapering, per-copy jitter, smooth union, paint-order occlusion …).
**Presets** (flower, tree, fern, starfish, jellyfish, shell …) are ready-made part lists whose
parameters can be overridden. The result is editable path layers: one per part (and per extra
output such as leaf veins), grouped when there are several.

Geometry is built in a unit frame (about −1…1, y down, forms grow upward from a base at +y),
then fitted into the layer box. ``blend``, ``occlude`` and ``intersect`` run last, in pixels.
See docs/organic.md for the vocabulary and the research it is based on.
"""

from copy import deepcopy
import math
import re

import numpy as np

from .errors import VixlError, require
from .model import finite
from . import trace

TYPES = ("organic",)
MAX_PARTS = 32
MAX_ELEMENTS = 6000
MAX_POINTS = 400_000
MAX_COPIES = 2000
MAX_COMMANDS = 8192
GOLDEN_ANGLE = 137.50776405003785
POST_RULES = ("blend", "occlude", "intersect")
# Operation fields stored in a form's recipe, so a regrow starts from what was last asked for.
RECIPE_KEYS = ("preset", "parts", "params", "colors", "seed", "naturalness", "padding", "stretch", "fill", "stroke",
               "stroke_width")
UNFILLED = ("transparent", "none")


# ---------------------------------------------------------------------------------------------
# Geometry containers


def element(points, closed=True, smooth=True):
    return {"points": np.asarray(points, dtype=float), "closed": closed, "smooth": smooth}


class Shape:
    """Geometry of one part: elements per output tag, plus named anchors (x, y, angle°)."""

    def __init__(self, tags=None, anchors=None):
        self.tags = tags or {}
        self.anchors = anchors or {}

    def elements(self):
        return [e for items in self.tags.values() for e in items]

    def copy(self):
        return Shape({t: [{**e, "points": e["points"].copy()} for e in items] for t, items in self.tags.items()},
                     {k: [tuple(a) for a in v] for k, v in self.anchors.items()})

    def map(self, fn, angle_fn=None):
        """Apply a point transform to every element and anchor."""
        for items in self.tags.values():
            for e in items:
                if len(e["points"]):
                    e["points"] = fn(e["points"])
        for name, anchors in self.anchors.items():
            moved = []
            for x, y, angle in anchors:
                p = fn(np.array([[x, y]]))[0]
                if angle_fn is None:
                    direction = np.array([[x, y], [x + math.cos(math.radians(angle)) * 1e-3,
                                                   y + math.sin(math.radians(angle)) * 1e-3]])
                    q = fn(direction)
                    turned = math.degrees(math.atan2(q[1, 1] - q[0, 1], q[1, 0] - q[0, 0]))
                else:
                    turned = angle_fn(angle)
                moved.append((float(p[0]), float(p[1]), turned))
            self.anchors[name] = moved
        return self

    def extend(self, other):
        for tag, items in other.tags.items():
            self.tags.setdefault(tag, []).extend(items)
        for name, anchors in other.anchors.items():
            self.anchors.setdefault(name, []).extend(anchors)
        return self

    def bounds(self):
        points = [e["points"] for e in self.elements() if len(e["points"])]
        if not points:
            return (0.0, 0.0, 0.0, 0.0)
        p = np.vstack(points)
        return (float(p[:, 0].min()), float(p[:, 1].min()), float(p[:, 0].max()), float(p[:, 1].max()))

    def base(self):
        """The point a placed copy attaches by: an explicit ``base`` anchor, else bottom centre."""
        if self.anchors.get("base"):
            x, y, _ = self.anchors["base"][0]
            return x, y
        x0, _, x1, y1 = self.bounds()
        return (x0 + x1) / 2, y1


def rotate(points, degrees, origin=(0, 0)):
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    p = np.asarray(points, dtype=float) - origin
    return np.column_stack([p[:, 0] * c - p[:, 1] * s, p[:, 0] * s + p[:, 1] * c]) + origin


def affine(shape, scale=(1, 1), angle=0.0, translate=(0, 0), origin=(0, 0)):
    """Scale about ``origin``, rotate about it, then move it to ``translate``."""
    sx, sy = scale
    ox, oy = origin
    a = math.radians(angle)
    c, s = math.cos(a), math.sin(a)

    def fn(p):
        x, y = (p[:, 0] - ox) * sx, (p[:, 1] - oy) * sy
        return np.column_stack([x * c - y * s + translate[0], x * s + y * c + translate[1]])

    return shape.map(fn)


def loop_noise(count, rng, octaves=3, frequency=3, closed=True):
    """Smooth, seeded noise along a loop (periodic when closed) with values about −1…1."""
    t = np.linspace(0, 1, count, endpoint=not closed)
    total = np.zeros(count)
    amplitude, weight = 1.0, 0.0
    for octave in range(octaves):
        f = frequency * 2 ** octave
        f = max(1, round(f)) if closed else f
        total += amplitude * np.sin(2 * math.pi * f * t + rng.uniform(0, math.tau))
        weight += amplitude
        amplitude *= 0.5
    return total / max(weight, 1e-9)


def field_noise(points, rng_state, frequency=2.0, octaves=3):
    """Smooth 2-D displacement noise (−1…1 per axis) from sums of seeded plane waves."""
    rng = np.random.default_rng(rng_state)
    p = np.asarray(points, dtype=float)
    out = np.zeros_like(p)
    amplitude, weight = 1.0, 0.0
    for octave in range(octaves):
        for axis in (0, 1):
            for _ in range(2):
                theta = rng.uniform(0, math.tau)
                f = frequency * 2 ** octave * rng.uniform(0.8, 1.25)
                out[:, axis] += amplitude * np.sin(f * (p[:, 0] * math.cos(theta) + p[:, 1] * math.sin(theta))
                                                    + rng.uniform(0, math.tau)) / 2
        weight += amplitude
        amplitude *= 0.5
    return out / max(weight, 1e-9)


def normals(points, closed):
    p = np.asarray(points, dtype=float)
    if closed:
        tangent = np.roll(p, -1, axis=0) - np.roll(p, 1, axis=0)
    else:
        tangent = np.gradient(p, axis=0)
    norm = np.maximum(np.hypot(*tangent.T), 1e-12)
    return np.column_stack([-tangent[:, 1], tangent[:, 0]]) / norm[:, None]


def ribbon(spine, widths, cap=True):
    """A closed outline around a spine with per-point half-widths (a tapered tube)."""
    p = np.asarray(spine, dtype=float)
    n = normals(p, False)
    w = np.asarray(widths, dtype=float)[:, None]
    left, right = p + n * w, p - n * w
    points = [left]
    if cap and w[-1, 0] > 1e-6:
        start = math.atan2(n[-1, 1], n[-1, 0])
        arc = [p[-1] + w[-1, 0] * np.array([math.cos(start - math.pi * k / 6), math.sin(start - math.pi * k / 6)])
               for k in range(1, 6)]
        points.append(np.array(arc))
    points.append(right[::-1])
    return np.vstack(points)


# ---------------------------------------------------------------------------------------------
# Parameters


class Params:
    """Validated generator/rule parameters with defaults and ranges."""

    def __init__(self, values, where):
        require(isinstance(values, dict), f"{where} must be an object", field=where)
        self.values, self.where, self.used = values, where, set()

    def number(self, key, default, low, high):
        self.used.add(key)
        value = self.values.get(key, default)
        try:
            return float(finite(value, f"{self.where}.{key}", low, high))
        except VixlError as exc:
            exc.details.setdefault("field", f"{self.where}.{key}")
            raise

    def integer(self, key, default, low, high):
        value = self.number(key, default, low, high)
        require(value == int(value), f"{self.where}.{key} must be a whole number", field=f"{self.where}.{key}")
        return int(value)

    def choice(self, key, default, options):
        self.used.add(key)
        value = self.values.get(key, default)
        require(value in options, f"{self.where}.{key} must be one of {', '.join(map(str, options))}",
                field=f"{self.where}.{key}", allowed=list(options))
        return value

    def flag(self, key, default):
        self.used.add(key)
        value = self.values.get(key, default)
        require(isinstance(value, bool), f"{self.where}.{key} must be true or false", field=f"{self.where}.{key}")
        return value

    def pair(self, key, default, low, high):
        self.used.add(key)
        value = self.values.get(key, default)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            value = [value, value]
        require(isinstance(value, list) and len(value) == 2, f"{self.where}.{key} must be a number or [a, b]",
                field=f"{self.where}.{key}")
        try:
            return [float(finite(v, f"{self.where}.{key}", low, high)) for v in value]
        except VixlError as exc:
            exc.details.setdefault("field", f"{self.where}.{key}")
            raise

    def raw(self, key, default=None):
        self.used.add(key)
        return self.values.get(key, default)

    def done(self, allowed=()):
        unknown = sorted(set(self.values) - self.used - set(allowed))
        require(not unknown, f"Unknown {self.where} setting(s) {', '.join(unknown)}; allowed: "
                f"{', '.join(sorted(self.used | set(allowed)))}", field=f"{self.where}.{unknown[0]}" if unknown else None)


# ---------------------------------------------------------------------------------------------
# Generators


def gen_superformula(p, ctx):
    """Gielis superformula r(φ) = (|cos(mφ/4)/a|^n2 + |sin(mφ/4)/b|^n3)^(−1/n1)."""
    m = p.number("m", 5, 0, 64)
    n1 = p.number("n1", 2, 0.05, 100)
    n2 = p.number("n2", 7, -100, 100)
    n3 = p.number("n3", 7, -100, 100)
    a = p.number("a", 1, 0.05, 20)
    b = p.number("b", 1, 0.05, 20)
    turn = p.number("rotate", -90, -360, 360)
    samples = p.integer("samples", 240, 24, 2000)
    phi = np.linspace(0, math.tau, samples, endpoint=False)
    with np.errstate(all="ignore"):
        term = np.abs(np.cos(m * phi / 4) / a) ** n2 + np.abs(np.sin(m * phi / 4) / b) ** n3
        r = term ** (-1 / n1)
    r = np.where(np.isfinite(r), r, np.nan)
    require(np.isfinite(r).any(), "These superformula parameters give no finite outline", field="params")
    r = np.nan_to_num(r, nan=np.nanmax(r))
    r = np.minimum(r / np.max(r), 1.0)
    points = rotate(np.column_stack([r * np.cos(phi), r * np.sin(phi)]), turn)
    return Shape({"shape": [element(points)]}, {"center": [(0.0, 0.0, -90.0)]})


def gen_blob(p, ctx):
    """A soft, irregular rounded loop: a circle with smooth seeded noise and optional lobes."""
    lobes = p.integer("lobes", 0, 0, 32)
    variation = p.number("variation", 0.25, 0, 1)
    depth = p.number("lobe_depth", 0.12, 0, 0.8)
    samples = p.integer("samples", 120, 24, 1000)
    t = np.linspace(0, math.tau, samples, endpoint=False)
    r = 1 + variation * 0.35 * loop_noise(samples, ctx["rng"], 3, 2)
    if lobes:
        r = r + depth * np.sin(lobes * t + ctx["rng"].uniform(0, math.tau))
    r = r / r.max()
    return Shape({"shape": [element(np.column_stack([r * np.cos(t), r * np.sin(t)]))]},
                 {"center": [(0.0, 0.0, -90.0)]})


LEAF_SHAPES = {
    # (p, q, half-width): widest point at t = p / (p + q) from the base.
    "lanceolate": (0.6, 1.2, 0.2),
    "ovate": (0.55, 1.1, 0.42),
    "elliptic": (0.9, 0.9, 0.36),
    "obovate": (1.3, 0.65, 0.42),
    "orbicular": (0.5, 0.5, 0.9),
    "linear": (0.12, 0.5, 0.06),
    "spatulate": (2.2, 0.45, 0.35),
}


def profile(kind, t):
    """Normalized half-width (0…1) along a leaf or petal from base (t=0) to tip (t=1)."""
    pw, qw, _ = LEAF_SHAPES[kind]
    w = np.power(np.clip(t, 0, 1), pw) * np.power(np.clip(1 - t, 0, 1), qw)
    return w / max(w.max(), 1e-12)


def margin(t, kind, teeth, depth):
    """Leaf margin modulation (multiplier on the half-width) for teeth along the edge."""
    if kind == "entire" or teeth <= 0 or depth <= 0:
        return np.ones_like(t)
    phase = t * teeth
    frac = phase % 1
    if kind == "serrate":       # forward-pointing saw teeth
        wave = 1 - frac
    elif kind == "dentate":     # symmetric outward teeth
        wave = 1 - 2 * np.abs(frac - 0.5)
    elif kind == "crenate":     # rounded scallops
        wave = np.abs(np.sin(math.pi * phase))
    else:                       # lobed
        wave = 0.5 + 0.5 * np.cos(math.tau * phase)
    fade = np.clip(np.minimum(t / 0.12, (1 - t) / 0.08), 0, 1)
    return 1 - depth * (1 - wave) * fade


def gen_leaf(p, ctx):
    """A leaf blade from base (0, 1) to tip (0, −1) with a shape profile, margin teeth,
    fluctuating asymmetry and optional venation (``veins``) and petiole (``stem``)."""
    kind = p.choice("shape", "ovate", (*LEAF_SHAPES, "cordate"))
    width = p.number("width", LEAF_SHAPES.get(kind, (0, 0, 0.45))[2], 0.02, 2)
    edge = p.choice("margin", "entire", ("entire", "serrate", "dentate", "crenate", "lobed"))
    teeth = p.integer("teeth", 14 if edge not in ("entire", "lobed") else 5, 0, 120)
    depth = p.number("tooth_depth", 0.35 if edge == "lobed" else 0.08, 0, 0.9)
    veins = p.choice("veins", "pinnate", ("none", "pinnate", "palmate", "parallel"))
    count = p.integer("vein_count", 6, 1, 40)
    asym = p.number("asymmetry", 0.04, 0, 0.5)
    stem = p.number("petiole", 0.0, 0, 2)
    tip = p.number("tip", 1.0, 0.2, 4)
    n = 90
    t = np.linspace(0, 1, n)
    if kind == "cordate":
        # A heart curve, tip up: lobes either side of a notch where the petiole joins.
        s = np.linspace(0, math.pi, n)
        x = 16 * np.sin(s) ** 3 / 16 * width / 0.45 * 0.5
        y = -(13 * np.cos(s) - 5 * np.cos(2 * s) - 2 * np.cos(3 * s) - np.cos(4 * s)) / 17
        y = (y - y.min()) / (y.max() - y.min()) * 2 - 1
        right = np.column_stack([x, y])[::-1]
        w_right = right[:, 0]
    else:
        w = profile(kind, t) ** (1 / tip) if tip != 1 else profile(kind, t)
        w = w * margin(t, edge, teeth, depth)
        y = 1 - 2 * t
        w_right = width * w * (1 + asym * ctx["rng"].uniform(-1, 1))
        right = np.column_stack([w_right, y])
    left_scale = 1 + asym * ctx["rng"].uniform(-1, 1)
    left = right[::-1] * [-left_scale, 1]
    blade = np.vstack([right, left[1:-1]])
    shape = Shape({"shape": [element(blade, True, True)]},
                  {"base": [(0.0, 1.0, 90.0)], "tip": [(0.0, -1.0, -90.0)]})
    lines = []
    if veins != "none":
        midrib = np.column_stack([np.zeros(24), np.linspace(1, -0.92, 24)])
        if veins in ("pinnate", "palmate") or kind == "cordate":
            lines.append(element(midrib, False, True))
        if veins == "pinnate":
            for k in range(count):
                tk = 0.1 + 0.75 * (k + 0.5) / count
                yk = 1 - 2 * tk
                for side in (1, -1):
                    reach = 0.82 * float(np.interp(min(1, tk + 0.12), t, np.abs(w_right))) if kind != "cordate" else 0.8 * width
                    jitter = 1 + 0.08 * ctx["rng"].uniform(-1, 1)
                    q = np.linspace(0, 1, 8)
                    xs = side * reach * jitter * q
                    ys = yk - 0.24 * q ** 1.5 * (0.6 + 0.4 * reach / max(width, 1e-6))
                    lines.append(element(np.column_stack([xs, ys]), False, True))
        elif veins == "palmate":
            for k in range(count):
                angle = -90 + (k - (count - 1) / 2) * min(120 / max(count - 1, 1), 30)
                a = math.radians(angle)
                reach = 0.85 if k == (count - 1) // 2 else 0.6
                q = np.linspace(0, reach * 1.8, 10)
                lines.append(element(np.column_stack([q * math.cos(a) * width / 0.45, 1 + q * math.sin(a)]), False, True))
        else:
            for k in range(1, count + 1):
                frac = k / (count + 1) * 2 - 1
                xs = frac * w_right * 0.85 if kind != "cordate" else frac * np.abs(right[:, 0]) * 0.8
                lines.append(element(np.column_stack([xs, right[:, 1]]), False, True))
    if stem:
        lines.append(element(np.column_stack([np.zeros(6), np.linspace(1, 1 + stem, 6)]), False, True))
        shape.anchors["base"] = [(0.0, 1 + stem, 90.0)]
    if lines:
        shape.tags["veins"] = lines
    return shape


def gen_petal(p, ctx):
    """A petal from base (0, 1) to tip (0, −1): round, pointed, notched or fringed tips."""
    tip = p.choice("tip", "round", ("round", "pointed", "notched", "fringed"))
    width = p.number("width", 0.5, 0.05, 2)
    shape_kind = p.choice("profile", "obovate", tuple(LEAF_SHAPES))
    cup = p.number("cup", 0.0, -0.5, 0.5)
    n = 80
    t = np.linspace(0, 1, n)
    w = profile(shape_kind, t)
    if tip == "round":
        w = np.sqrt(np.clip(w * (1 - 0.4 * t ** 8), 0, None)) * np.sqrt(np.clip(1 - t ** 6, 0, 1))
    elif tip == "pointed":
        w = w ** 0.8
    if tip in ("notched", "fringed"):
        w = np.sqrt(np.clip(w * (1 - 0.4 * t ** 8), 0, None)) * np.sqrt(np.clip(1 - t ** 6, 0, 1))
    y = 1 - 2 * t
    if tip == "fringed":
        w = w * (1 - 0.18 * (t > 0.8) * np.abs(np.sin(t * 70)))
    right = np.column_stack([width * w + cup * (1 - y) * 0.1, y])
    left = right[::-1] * [-1, 1]
    outline = np.vstack([right, left[1:-1]])
    if tip == "notched":
        # Pull the middle of the tip down into a soft V.
        x, yy = outline[:, 0], outline[:, 1]
        depth = 0.22 * np.exp(-(x / (0.3 * width)) ** 2) * np.clip((-0.6 - yy) / 0.4, 0, 1)
        outline = np.column_stack([x, yy + depth])
    return Shape({"shape": [element(outline)]}, {"base": [(0.0, 1.0, 90.0)], "tip": [(0.0, -1.0, -90.0)]})


def gen_spiral(p, ctx):
    """A logarithmic r = a·e^(bθ) (or Archimedean) spiral; ``width`` > 0 makes a tapered ribbon."""
    kind = p.choice("kind", "log", ("log", "archimedean"))
    turns = p.number("turns", 3, 0.25, 12)
    growth = p.number("growth", 3.0, 1.05, 50)
    width = p.number("width", 0.0, 0, 1)
    samples = p.integer("samples", 360, 32, 4000)
    theta = np.linspace(0, turns * math.tau, samples)
    if kind == "log":
        b = math.log(growth) / math.tau
        r = np.exp(b * (theta - theta[-1]))
    else:
        r = theta / theta[-1]
    points = np.column_stack([r * np.cos(theta), r * np.sin(theta)])
    anchors = {"end": [(float(points[-1, 0]), float(points[-1, 1]), 0.0)], "center": [(0.0, 0.0, -90.0)]}
    if width > 0:
        return Shape({"shape": [element(ribbon(points, width * r, cap=True))]}, anchors)
    return Shape({"shape": [element(points, False, True)]}, anchors)


def gen_shell(p, ctx):
    """A planispiral shell (nautilus, ammonite) after Raup: whorls grow by ``growth`` (W) per turn.
    ``chambers`` adds septa and the previous whorl's edge as the ``chambers`` output."""
    growth = p.number("growth", 3.0, 1.2, 20)
    chambers = p.integer("chambers", 14, 0, 60)
    ribs = p.integer("ribs", 0, 0, 120)
    whorls = p.integer("whorls", 1, 0, 6)
    b = math.log(growth) / math.tau
    theta = np.linspace(-math.tau, 0, 220)
    r = np.exp(b * theta)
    outer = np.column_stack([r * np.cos(theta), r * np.sin(theta)])
    shape = Shape({"shape": [element(outer)]}, {"center": [(0.0, 0.0, 0.0)]})
    lines = [element(np.column_stack([r / growth ** k * np.cos(theta), r / growth ** k * np.sin(theta)]), False, True)
             for k in range(1, whorls + 1)]
    for k in range(1, chambers + 1):
        a = -math.tau * k / (chambers + 1)
        ro, ri = math.exp(b * a), math.exp(b * a) / growth
        q = np.linspace(0, 1, 8)
        bend = 0.25 * (ro - ri) * np.sin(math.pi * q)
        rr = ri + (ro - ri) * q
        aa = a + bend / max(ro, 1e-6)
        lines.append(element(np.column_stack([rr * np.cos(aa), rr * np.sin(aa)]), False, True))
    if ribs:
        for k in range(ribs):
            a = -math.tau * (k + 0.5) / ribs
            ro = math.exp(b * a)
            q = np.linspace(0.75, 0.98, 4)
            lines.append(element(np.column_stack([ro * q * math.cos(a), ro * q * math.sin(a)]), False, False))
    if lines:
        shape.tags["chambers"] = lines
    return shape


def gen_tentacle(p, ctx):
    """A tapered tube along a curling, waving spine: tentacles, tails, horns, worms, roots, stems
    and jointed limbs (``elbow`` turns by that many degrees at ``elbow_at``). Grows from its base at
    (0, 0) along ``heading`` (−90, up, by default); ``tip`` anchors the end, ``spine`` the centre line."""
    length = p.number("length", 1.6, 0.05, 20)
    width = p.number("width", 0.12, 0.001, 2)
    taper = p.number("taper", 1.0, 0, 6)
    tip = p.number("tip_width", 0.004, 0, 1)
    curl = p.number("curl", 0.5, -6, 6)
    wave = p.number("wave", 0.6, 0, 10)
    waves = p.number("waves", 1.5, 0, 20)
    heading = p.number("heading", -90, -360, 360)
    wobble = p.number("wobble", 0.3, 0, 5)
    elbow = p.number("elbow", 0, -360, 360)
    elbow_at = p.number("elbow_at", 0.4, 0, 1)
    n = 140
    s = np.linspace(0, 1, n)
    rng = ctx["rng"]
    phase = rng.uniform(0, math.tau)
    noise = loop_noise(n, rng, 2, 1.5, closed=False)
    curvature = curl * math.tau * s ** 3 * 2 + wave * np.sin(math.tau * waves * s + phase) + wobble * noise
    if elbow:
        # A joint: the turn is concentrated around elbow_at, so the limb runs straight on either side.
        bump = np.exp(-((s - elbow_at) / 0.06) ** 2)
        curvature = curvature + math.radians(elbow) * bump / (bump.sum() * length / n)
    angle = math.radians(heading) + np.cumsum(curvature) * (length / n)
    step = length / (n - 1)
    spine = np.vstack([[0, 0], np.cumsum(np.column_stack([np.cos(angle[:-1]), np.sin(angle[:-1])]) * step, axis=0)])
    widths = width * (1 - s) ** taper + tip
    end = spine[-1]
    tangent = spine[-1] - spine[-2]
    sampled = trace.resample(spine, 48)
    return Shape({"shape": [element(ribbon(spine, widths))]},
                 {"base": [(0.0, 0.0, heading - 180)],
                  "tip": [(float(end[0]), float(end[1]), math.degrees(math.atan2(tangent[1], tangent[0])))],
                  "spine": [(float(x), float(y), 0.0) for x, y in sampled]})


HABITS = {
    # angle, ratio, leader_ratio, tropism, children
    "decurrent": (32, 0.72, None, 0.05, 2),
    "excurrent": (65, 0.55, 0.82, -0.02, 2),
    "weeping": (40, 0.74, None, -0.35, 2),
    "shrub": (40, 0.68, None, 0.1, 3),
    "coral": (24, 0.8, None, 0.2, 2),
    "roots": (35, 0.75, None, -0.25, 2),
}


def gen_branch(p, ctx):
    """A recursive branching tree (Honda/Leonardo): child widths follow d^α = Σ d_child^α.
    Anchors ``tips`` (twig ends) and ``forks`` take leaves, flowers and fruit."""
    habit = p.choice("habit", "decurrent", tuple(HABITS))
    spread, ratio, leader, tropism, children = HABITS[habit]
    depth = p.integer("depth", 6, 1, 9)
    spread = p.number("angle", spread, 1, 90)
    ratio = p.number("ratio", ratio, 0.2, 0.95)
    children = p.integer("children", children, 1, 4)
    length = p.number("length", 0.42, 0.05, 2)
    width = p.number("width", 0.07, 0.002, 0.5)
    alpha = p.number("alpha", 2.0, 1.2, 4)
    tropism = p.number("tropism", tropism, -1, 1)
    jitter = p.number("jitter", 0.25, 0, 1)
    curve = p.number("curve", 0.15, 0, 1)
    heading = p.number("heading", -90, -360, 360)
    rng = ctx["rng"]
    segments, tips, forks = [], [], []
    budget = [0]

    def grow(origin, angle, size, thick, level):
        budget[0] += 1
        require(budget[0] <= 3000, "Branching exceeds 3000 segments; lower depth or children", "resource_limit")
        bend = rng.uniform(-curve, curve) * 25
        steps = 4
        points = [np.array(origin, dtype=float)]
        a = angle
        end_thick = thick * ratio ** 0.5 if level < depth else thick * 0.6
        for k in range(steps):
            a += bend / steps
            # Tropism bends growth toward up (positive) or down (negative) a little each step.
            target = -90 if tropism >= 0 else 90
            delta = (target - a + 540) % 360 - 180
            a += abs(tropism) * delta * 0.08
            rad = math.radians(a)
            points.append(points[-1] + np.array([math.cos(rad), math.sin(rad)]) * size / steps)
        spine = np.array(points)
        widths = np.linspace(thick, end_thick, len(spine)) / 2
        segments.append(element(ribbon(spine, widths, cap=True), True, False))
        end = spine[-1]
        if level >= depth:
            tips.append((float(end[0]), float(end[1]), a))
            return
        forks.append((float(end[0]), float(end[1]), a))
        count = children
        child_thick = thick * count ** (-1 / alpha)
        for i in range(count):
            if leader is not None and i == 0:
                grow(end, a + rng.uniform(-4, 4) * jitter, size * leader * (1 + rng.uniform(-jitter, jitter) * 0.3),
                     thick * 0.85, level + 1)
                continue
            if leader is not None:
                side = 1 if (i + level) % 2 else -1
                offset = side * spread
                child = size * ratio * 0.7
            else:
                offset = (i - (count - 1) / 2) * (2 * spread / max(count - 1, 1)) if count > 1 else 0
                child = size * ratio
            offset += rng.uniform(-1, 1) * spread * jitter * 0.5
            grow(end, a + offset, child * (1 + rng.uniform(-jitter, jitter) * 0.4), child_thick, level + 1)

    grow((0.0, 0.0), heading, length, width, 1)
    shape = Shape({"shape": segments}, {"tips": tips, "forks": forks, "base": [(0.0, 0.0, heading + 180)]})
    shape.union = True
    return shape


def lsystem_string(axiom, rules, iterations, limit=60_000):
    text = axiom
    for _ in range(iterations):
        text = "".join(rules.get(ch, ch) for ch in text)
        require(len(text) <= limit, f"The L-system grows past {limit} symbols; lower iterations", "resource_limit")
    return text


def gen_lsystem(p, ctx):
    """A turtle L-system: F/G draw, f moves, +/− turn, [ ] branch, | turns around.
    Draws strokes, or tapered filled branches when ``width`` is set."""
    axiom = p.raw("axiom", "X")
    rules = p.raw("rules", {"X": "F+[[X]-X]-F[-FX]+X", "F": "FF"})
    require(isinstance(axiom, str) and 0 < len(axiom) <= 200, "params.axiom must be 1–200 symbols", field="params.axiom")
    require(isinstance(rules, dict) and 0 < len(rules) <= 16 and all(
        isinstance(k, str) and len(k) == 1 and isinstance(v, str) and len(v) <= 400 for k, v in rules.items()),
        "params.rules maps single symbols to replacement strings", field="params.rules")
    iterations = p.integer("iterations", 5, 0, 10)
    angle = p.number("angle", 25, 0, 180)
    width = p.number("width", 0.0, 0, 0.5)
    taper = p.number("taper", 0.7, 0.2, 1)
    heading = p.number("heading", -90, -360, 360)
    jitter = p.number("jitter", 4, 0, 45)
    text = lsystem_string(axiom, rules, iterations)
    rng = ctx["rng"]
    x = y = 0.0
    a = heading
    depth = 0
    stack, lines, current, segments = [], [], [[(0.0, 0.0)]], []
    for symbol in text:
        if symbol in "FG":
            rad = math.radians(a + rng.uniform(-jitter, jitter) * 0.3)
            nx, ny = x + math.cos(rad), y + math.sin(rad)
            segments.append(((x, y), (nx, ny), depth))
            current[-1].append((nx, ny))
            x, y = nx, ny
        elif symbol == "f":
            rad = math.radians(a)
            x, y = x + math.cos(rad), y + math.sin(rad)
            current.append([(x, y)])
        elif symbol == "+":
            a += angle + rng.uniform(-jitter, jitter)
        elif symbol == "-":
            a -= angle + rng.uniform(-jitter, jitter)
        elif symbol == "|":
            a += 180
        elif symbol == "[":
            stack.append((x, y, a, depth))
            depth += 1
            current.append([(x, y)])
        elif symbol == "]" and stack:
            x, y, a, depth = stack.pop()
            current.append([(x, y)])
    require(segments, "The L-system draws nothing; use F or G", field="params")
    tips = [(float(b[0]), float(b[1]), 0.0) for _, b, _ in segments[-200:]]
    if width > 0:
        items = []
        for (ax, ay), (bx, by), level in segments:
            w = width * taper ** level
            items.append(element(ribbon(np.array([[ax, ay], [bx, by]]), [w / 2, w * taper / 2], cap=True), True, False))
        shape = Shape({"shape": items}, {"tips": tips, "base": [(0.0, 0.0, heading + 180)]})
        shape.union = True
        return shape
    for line in current:
        if len(line) > 1:
            lines.append(element(trace.simplify(np.array(line), 1e-6), False, False))
    return Shape({"shape": lines}, {"tips": tips, "base": [(0.0, 0.0, heading + 180)]})


def gen_phyllotaxis(p, ctx):
    """Vogel's model: element n at angle n·137.508° and radius c·√n, filling a disc evenly.
    Elements are dots, seeds (ellipses), petals or diamonds, oriented outward."""
    count = p.integer("count", 160, 3, 2000)
    angle = p.number("angle", GOLDEN_ANGLE, 1, 359)
    kind = p.choice("element", "circle", ("circle", "seed", "petal", "diamond"))
    size = p.number("size", 0.8, 0.05, 3)
    gradient = p.number("gradient", 0.35, -2, 2)
    start = p.integer("skip", 0, 0, 1999)
    c = 1 / math.sqrt(count)
    items, centers = [], []
    for n in range(start + 1, count + 1):
        r = c * math.sqrt(n)
        theta = math.radians(n * angle)
        cx, cy = r * math.cos(theta), r * math.sin(theta)
        radius = c * size * 0.5 * (1 + gradient * (r - 0.5))
        radius = max(radius, c * 0.05)
        orientation = math.degrees(theta) + 90
        if kind == "circle":
            t = np.linspace(0, math.tau, 12, endpoint=False)
            pts = np.column_stack([np.cos(t), np.sin(t)]) * radius
        elif kind == "seed":
            t = np.linspace(0, math.tau, 14, endpoint=False)
            pts = rotate(np.column_stack([0.62 * np.cos(t), 1.0 * np.sin(t)]) * radius * 1.2, orientation)
        elif kind == "diamond":
            pts = rotate(np.array([[0, -1.2], [0.75, 0], [0, 1.2], [-0.75, 0]]) * radius, orientation)
        else:
            t = np.linspace(0, 1, 12)
            w = np.sin(math.pi * t) ** 0.8
            half = np.column_stack([w * 0.6, 1.4 - 2.8 * t]) * radius
            pts = rotate(np.vstack([half, half[-2:0:-1] * [-1, 1]]), orientation)
        items.append(element(pts + [cx, cy], True, kind != "diamond"))
        centers.append((cx, cy, math.degrees(theta)))
    return Shape({"shape": items}, {"points": centers, "center": [(0.0, 0.0, -90.0)]})


def _poisson(rng, radius, count, inside, extent=1.0):
    """Bridson Poisson-disc samples within ``inside`` (a predicate on the −extent…extent square)."""
    cell = radius / math.sqrt(2)
    size = int(math.ceil(2 * extent / cell)) + 1
    grid = -np.ones((size, size), dtype=int)
    points, active = [], []

    def put(q):
        points.append(q)
        active.append(len(points) - 1)
        gx, gy = int((q[0] + extent) / cell), int((q[1] + extent) / cell)
        grid[min(size - 1, gy), min(size - 1, gx)] = len(points) - 1

    for _ in range(200):
        q = rng.uniform(-extent, extent, 2)
        if inside(q):
            put(q)
            break
    while active and len(points) < count:
        index = active[rng.integers(len(active))]
        base = points[index]
        for _ in range(30):
            angle, distance = rng.uniform(0, math.tau), rng.uniform(radius, 2 * radius)
            q = base + distance * np.array([math.cos(angle), math.sin(angle)])
            if np.any(np.abs(q) > extent) or not inside(q):
                continue
            gx, gy = int((q[0] + extent) / cell), int((q[1] + extent) / cell)
            near = grid[max(0, gy - 2):gy + 3, max(0, gx - 2):gx + 3]
            if all(math.dist(q, points[i]) >= radius for i in near[near >= 0]):
                put(q)
                break
        else:
            active.remove(index)
    return np.array(points[:count])


def boundary_polygon(spec, ctx, where):
    """A closed boundary: ``circle``, ``square``, a superformula/blob dict, or another part."""
    if spec in (None, "circle"):
        t = np.linspace(0, math.tau, 96, endpoint=False)
        return np.column_stack([np.cos(t), np.sin(t)])
    if spec in ("square", "rect"):
        return np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]], dtype=float)
    if isinstance(spec, str):
        name = spec[5:] if spec.startswith("part:") else spec
        require(name in ctx["parts"], f"{where} names unknown part {name!r}; earlier parts: {', '.join(ctx['parts']) or 'none'}",
                field=where)
        closed = [e for e in ctx["parts"][name].elements() if e.get("closed")]
        require(closed, f"Part {name!r} has no closed outline to use as a boundary", field=where)
        return max(closed, key=lambda e: abs(trace.area(e["points"])))["points"]
    require(isinstance(spec, dict) and spec.get("generator") in GENERATORS, f"{where} must be circle, square, a part "
            "name or {generator, params}", field=where)
    shape = GENERATORS[spec["generator"]][0](Params(spec.get("params", {}), where), ctx)
    return max((e for e in shape.elements() if e["closed"]), key=lambda e: abs(trace.area(e["points"])))["points"]


def clip_convex(polygon, a, b):
    """Keep the part of ``polygon`` on the left of the directed line a→b (Sutherland–Hodgman)."""
    result = []
    n = len(polygon)
    for i in range(n):
        cur, nxt = polygon[i], polygon[(i + 1) % n]
        side_cur = (b[0] - a[0]) * (cur[1] - a[1]) - (b[1] - a[1]) * (cur[0] - a[0])
        side_nxt = (b[0] - a[0]) * (nxt[1] - a[1]) - (b[1] - a[1]) * (nxt[0] - a[0])
        if side_cur >= 0:
            result.append(cur)
        if (side_cur >= 0) != (side_nxt >= 0):
            t = side_cur / (side_cur - side_nxt)
            result.append(cur + (nxt - cur) * t)
    return np.array(result) if result else np.zeros((0, 2))


def voronoi(sites, bounds):
    """Voronoi cells of ``sites`` clipped to the convex polygon ``bounds``."""
    cells = []
    for i, site in enumerate(sites):
        cell = np.asarray(bounds, dtype=float)
        order = np.argsort(np.hypot(*(sites - site).T))
        for j in order[1:]:
            other = sites[j]
            reach = np.max(np.hypot(*(cell - site).T)) if len(cell) else 0
            if math.dist(site, other) > 2 * reach + 1e-9:
                break
            middle = (site + other) / 2
            direction = other - site
            normal = np.array([-direction[1], direction[0]])
            # Keep the half-plane closer to ``site``.
            cell = clip_convex(cell, middle - normal, middle + normal)
            if len(cell) < 3:
                break
        cells.append(cell)
    return cells


def convex_hull(points):
    p = sorted(map(tuple, np.asarray(points, dtype=float)))
    if len(p) <= 2:
        return np.array(p)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for q in p:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], q) <= 0:
            lower.pop()
        lower.append(q)
    for q in reversed(p):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], q) <= 0:
            upper.pop()
        upper.append(q)
    return np.array(lower[:-1] + upper[:-1])


def gen_cells(p, ctx):
    """Voronoi cells (giraffe patches, plant tissue, honeycomb, dragonfly wings, cracked mud)
    from relaxed seeds inside a boundary, inset by ``gap`` and rounded."""
    count = p.integer("count", 40, 2, 600)
    relax = p.integer("relax", 2, 0, 20)
    gap = p.number("gap", 0.1, 0, 0.8)
    rounding = p.integer("round", 2, 0, 5)
    within = p.raw("within", "circle")
    outline = p.flag("outline", False)
    rng = ctx["rng"]
    boundary = boundary_polygon(within, ctx, "params.within")
    hull = trace.oriented(convex_hull(boundary), clockwise=False)
    hull = hull if trace.area(hull) > 0 else hull[::-1]
    x0, y0 = boundary.min(axis=0)
    x1, y1 = boundary.max(axis=0)
    sites = []
    while len(sites) < count:
        q = rng.uniform([x0, y0], [x1, y1])
        if trace.contains(boundary, q):
            sites.append(q)
    sites = np.array(sites)
    convex_bounds = hull if trace.area(hull) >= 0 else hull[::-1]
    for _ in range(relax):
        cells = voronoi(sites, convex_bounds)
        sites = np.array([trace.centroid(c) if len(c) >= 3 else s for c, s in zip(cells, sites)])
    cells = voronoi(sites, convex_bounds)
    items = []
    for cell, site in zip(cells, sites):
        if len(cell) < 3 or not trace.contains(boundary, trace.centroid(cell)):
            continue
        center = trace.centroid(cell)
        shrunk = center + (cell - center) * (1 - gap)
        if rounding:
            shrunk = trace.chaikin(shrunk, rounding, closed=True)
        items.append(element(shrunk, True, rounding == 0))
    shape = Shape({"shape": items}, {"points": [(float(s[0]), float(s[1]), 0.0) for s in sites]})
    if outline:
        shape.tags["outline"] = [element(boundary, True, True)]
    return shape


PATTERNS = {
    # Gray–Scott feed and kill rates (Pearson's classes, after Karl Sims' presets).
    "spots": (0.030, 0.062),
    "stripes": (0.042, 0.063),
    "labyrinth": (0.029, 0.057),
    "coral": (0.0545, 0.062),
    "mitosis": (0.0367, 0.0649),
    "holes": (0.039, 0.058),
}


def gen_pattern(p, ctx):
    """A reaction–diffusion (Gray–Scott) Turing pattern: leopard spots, zebra stripes, brain
    coral labyrinths, coral growth, dividing cells or holes, traced into closed outlines."""
    kind = p.choice("kind", "spots", tuple(PATTERNS))
    feed, kill = PATTERNS[kind]
    feed = p.number("feed", feed, 0.0, 0.12)
    kill = p.number("kill", kill, 0.0, 0.08)
    grid = p.integer("grid", 112, 32, 256)
    steps = p.integer("steps", 3200, 100, 20000)
    scale = p.number("scale", 1.0, 0.25, 4)
    threshold = p.number("threshold", 0.25, 0.05, 0.6)
    rng = ctx["rng"]
    size = max(32, int(grid / scale))
    a = np.ones((size, size))
    b = np.zeros((size, size))
    # Pearson's start: A = 0.5, B = 0.25 in small seed squares, with 1% noise.
    for _ in range(max(4, size // 6)):
        x, y = rng.integers(2, size - 8, 2)
        a[y:y + 6, x:x + 6] = 0.5
        b[y:y + 6, x:x + 6] = 0.25
    a += rng.uniform(-0.01, 0.01, a.shape)
    b += rng.uniform(-0.01, 0.01, b.shape)

    def laplacian(f):
        return (0.2 * (np.roll(f, 1, 0) + np.roll(f, -1, 0) + np.roll(f, 1, 1) + np.roll(f, -1, 1))
                + 0.05 * (np.roll(np.roll(f, 1, 0), 1, 1) + np.roll(np.roll(f, 1, 0), -1, 1)
                          + np.roll(np.roll(f, -1, 0), 1, 1) + np.roll(np.roll(f, -1, 0), -1, 1)) - f)

    for _ in range(steps):
        reaction = a * b * b
        a += laplacian(a) - reaction + feed * (1 - a)
        b += 0.5 * laplacian(b) + reaction - (kill + feed) * b
        np.clip(a, 0, 1, out=a)
        np.clip(b, 0, 1, out=b)
    if size != grid:
        from PIL import Image

        b = np.asarray(Image.fromarray(b.astype(np.float32), "F").resize((grid, grid), Image.Resampling.BICUBIC))
    loops = trace.contours(b, threshold)
    items = []
    for loop in loops:
        if abs(trace.area(loop)) < 2:
            continue
        loop = trace.simplify(loop, 0.3, closed=True)
        items.append(element(loop / (grid / 2) - 1, True, True))
    require(items, "The pattern came out empty; try another kind, seed or threshold", field="params")
    return Shape({"shape": items}, {"center": [(0.0, 0.0, -90.0)]})


def gen_scales(p, ctx):
    """Overlapping scales (fish, reptile, pinecone bracts, roof-tile feathers) in staggered rows.
    Later rows are drawn over earlier ones; combine with ``occlude`` to keep each edge."""
    rows = p.integer("rows", 7, 1, 60)
    columns = p.integer("columns", 8, 1, 60)
    kind = p.choice("shape", "round", ("round", "pointed", "diamond"))
    overlap = p.number("overlap", 0.45, 0, 0.9)
    gradient = p.number("gradient", 0.0, -0.9, 0.9)
    jitter = p.number("jitter", 0.04, 0, 0.5)
    rng = ctx["rng"]
    w = 2 / columns
    h = w * 1.1
    step = h * (1 - overlap)
    items = []
    for row in range(rows):
        size = 1 + gradient * (row / max(rows - 1, 1) - 0.5)
        offset = (w / 2) * (row % 2)
        for col in range(-1, columns + 1):
            cx = -1 + offset + col * w + w / 2
            cy = -1 + row * step
            t = np.linspace(0, math.pi, 14)
            if kind == "round":
                arc = np.column_stack([np.cos(t) * w / 2, np.sin(t) * h * 0.55])
            elif kind == "pointed":
                arc = np.column_stack([np.cos(t) * w / 2, np.sin(t) ** 0.6 * h * 0.7])
            else:
                arc = np.array([[w / 2, 0], [0, h * 0.7], [-w / 2, 0]])
            top = np.array([[-w / 2, -h * 0.5], [w / 2, -h * 0.5]])
            pts = np.vstack([top[1:], arc, top[:1]]) * size * (1 + rng.uniform(-jitter, jitter))
            items.append(element(pts + [cx, cy], True, kind != "diamond"))
    return Shape({"shape": items})


SPINES = ("straight", "arc", "s-curve", "spiral", "wave")


def spine_points(kind, count=80, amount=0.35):
    t = np.linspace(0, 1, count)
    if kind == "straight":
        return np.column_stack([np.zeros(count), 1 - 2 * t])
    if kind == "arc":
        a = math.pi * amount * (2 * t - 1)
        r = 1 / max(math.sin(math.pi * amount), 1e-3)
        return np.column_stack([r * (np.cos(a) - math.cos(math.pi * amount)) * 0.5, -r * np.sin(a)])
    if kind == "s-curve":
        return np.column_stack([amount * np.sin(math.tau * t), 1 - 2 * t])
    if kind == "wave":
        return np.column_stack([amount * 0.6 * np.sin(math.tau * 2 * t), 1 - 2 * t])
    theta = np.linspace(0, math.tau * 1.25, count)
    r = np.exp(0.25 * (theta - theta[-1]))
    return np.column_stack([r * np.cos(theta), r * np.sin(theta)])


def gen_segments(p, ctx):
    """A segmented body along a spine (caterpillar, worm, bamboo, vertebrae, larva): ellipses
    sized by a width profile, ordered tail to head. Pair with ``occlude`` to keep each segment."""
    count = p.integer("count", 12, 2, 200)
    kind = p.choice("spine", "s-curve", SPINES)
    bend = p.number("bend", 0.25, 0, 1.5)
    width = p.number("width", 0.18, 0.01, 2)
    profile_kind = p.choice("profile", "caterpillar", ("caterpillar", "worm", "even", "bamboo", "tail"))
    overlap = p.number("overlap", 0.3, 0, 0.9)
    spine = trace.resample(spine_points(kind, 200, bend), count)
    spacing = trace.length(spine) / max(count - 1, 1)
    items, centers = [], []
    for i, center in enumerate(spine):
        s = i / max(count - 1, 1)
        factor = {
            "caterpillar": 0.85 + 0.25 * math.sin(math.pi * min(1, s * 1.15)),
            "worm": 0.55 + 0.45 * math.sin(math.pi * s),
            "even": 1.0,
            "bamboo": 1.0,
            "tail": 1 - 0.85 * s,
        }[profile_kind]
        tangent = spine[min(i + 1, count - 1)] - spine[max(i - 1, 0)]
        angle = math.degrees(math.atan2(tangent[1], tangent[0]))
        t = np.linspace(0, math.tau, 24, endpoint=False)
        along = spacing * (0.5 + overlap) if profile_kind != "bamboo" else spacing * 0.5
        pts = np.column_stack([np.cos(t) * along, np.sin(t) * width * factor])
        if profile_kind == "bamboo":
            pts = np.array([[-along, -width], [along, -width], [along * 1.02, 0], [along, width],
                            [-along, width], [-along * 1.02, 0]])
        items.append(element(rotate(pts, angle) + center, True, profile_kind != "bamboo"))
        centers.append((float(center[0]), float(center[1]), angle))
    return Shape({"shape": items[::-1]}, {"points": centers, "head": [centers[-1]], "tail": [centers[0]]})


def gen_feather(p, ctx):
    """A feather: a curved rachis, an asymmetric vane with occasional splits, and barbs."""
    barbs = p.integer("barbs", 36, 0, 200)
    curve = p.number("curve", 0.12, -1, 1)
    asym = p.number("asymmetry", 0.35, 0, 0.9)
    splits = p.integer("splits", 2, 0, 12)
    rng = ctx["rng"]
    t = np.linspace(0, 1, 60)
    rachis = np.column_stack([curve * np.sin(math.pi * t) * 0.6, 1 - 2 * t])
    w = profile("lanceolate", np.clip((t - 0.12) / 0.88, 0, 1)) * 0.38
    right = rachis + np.column_stack([w * (1 + asym * 0.5), -w * 0.25])
    left = rachis + np.column_stack([-w * (1 - asym * 0.5), -w * 0.25])
    cuts = sorted(rng.uniform(0.25, 0.9, splits))
    for c in cuts:
        k = int(c * 59)
        side = right if rng.random() < 0.5 else left
        side[k:k + 2] = rachis[k:k + 2] + (side[k:k + 2] - rachis[k:k + 2]) * 0.55
    vane = np.vstack([right, left[::-1]])
    barb_lines = []
    for i in range(barbs):
        s = 0.15 + 0.82 * i / max(barbs - 1, 1)
        k = int(s * 59)
        for side, sign in ((right, 1), (left, -1)):
            start = rachis[k]
            end = side[min(59, k + 4)]
            middle = (start + end) / 2 + [0, -0.03]
            barb_lines.append(element(np.array([start, middle, end]), False, True))
    return Shape({"shape": [element(vane)], "rachis": [element(rachis, False, True)], "barbs": barb_lines},
                 {"base": [(float(rachis[0, 0]), float(rachis[0, 1]), 90.0)], "tip": [(float(rachis[-1, 0]), float(rachis[-1, 1]), -90.0)]})


def gen_ellipse(p, ctx):
    """A plain ellipse, egg or teardrop: the simple rounded forms bodies, eyes and seeds use."""
    kind = p.choice("form", "ellipse", ("ellipse", "egg", "teardrop", "crescent"))
    aspect = p.number("aspect", 1.0, 0.05, 20)
    point = p.number("point", 2.0, 0.5, 8)
    t = np.linspace(0, math.tau, 96, endpoint=False)
    if kind == "egg":
        x, y = np.cos(t) * (1 - 0.18 * np.sin(t)), np.sin(t)
    elif kind == "teardrop":
        x, y = np.sin(t) * np.abs(np.sin(t / 2)) ** point, -np.cos(t)
    elif kind == "crescent":
        a = np.linspace(0, math.pi, 48)
        outer = np.column_stack([np.cos(a), -np.sin(a)])
        inner = np.column_stack([np.cos(a[::-1]) * 0.85, -np.sin(a[::-1]) * 0.55])
        return Shape({"shape": [element(np.vstack([outer, inner]) * [aspect, 1])]})
    else:
        x, y = np.cos(t), np.sin(t)
    return Shape({"shape": [element(np.column_stack([x * aspect, y]))]}, {"center": [(0.0, 0.0, -90.0)]})


def gen_rings(p, ctx):
    """Concentric growth rings (tree rings, ripples, agate, onion layers) with noise."""
    count = p.integer("count", 10, 1, 120)
    noise = p.number("noise", 0.04, 0, 0.5)
    spacing = p.choice("spacing", "even", ("even", "growth"))
    rng = ctx["rng"]
    items = []
    for k in range(1, count + 1):
        r = k / count if spacing == "even" else math.sqrt(k / count)
        t = np.linspace(0, math.tau, 96, endpoint=False)
        rr = r * (1 + noise * loop_noise(96, rng, 3, 2))
        items.append(element(np.column_stack([rr * np.cos(t), rr * np.sin(t)]), True, True))
    return Shape({"shape": items})


def gen_path(p, ctx):
    """Any SVG path as a starting form (normalized so its larger side spans −1…1)."""
    from .geometry import path_polygons

    data = p.raw("d")
    require(isinstance(data, str), "params.d needs an SVG path", field="params.d")
    polygons = [np.array(poly, dtype=float) for poly in path_polygons(data) if len(poly) >= 2]
    require(polygons, "params.d has no geometry", field="params.d")
    allp = np.vstack(polygons)
    lo, hi = allp.min(axis=0), allp.max(axis=0)
    scale = 2 / max(hi - lo)
    items = []
    for poly in polygons:
        closed = len(poly) > 2 and np.allclose(poly[0], poly[-1])
        items.append(element((poly - (lo + hi) / 2) * scale, closed, False))
    return Shape({"shape": items})


GENERATORS = {
    "superformula": (gen_superformula, "Gielis superformula outline: starfish, flowers, cells, diatoms, cactus sections"),
    "blob": (gen_blob, "Irregular rounded loop with smooth noise and optional lobes: cells, pebbles, amoebae"),
    "leaf": (gen_leaf, "Leaf blade by shape profile with margin teeth, venation and petiole"),
    "petal": (gen_petal, "Petal with round, pointed, notched or fringed tip"),
    "spiral": (gen_spiral, "Logarithmic or Archimedean spiral line or tapered ribbon: tendrils, fiddleheads, horns"),
    "shell": (gen_shell, "Planispiral shell after Raup's model, with chambers and ribs"),
    "tentacle": (gen_tentacle, "Tapered tube along a curling, waving spine: tentacles, tails, horns, worms, roots, stems"),
    "branch": (gen_branch, "Recursive branching tree with Leonardo's thickness rule and growth habits"),
    "lsystem": (gen_lsystem, "Lindenmayer system turtle drawing: ferns, weeds, coral, lightning"),
    "phyllotaxis": (gen_phyllotaxis, "Vogel's golden-angle spiral packing: seed heads, florets, pinecones"),
    "cells": (gen_cells, "Relaxed Voronoi cells: giraffe patches, plant tissue, honeycomb, cracked mud"),
    "pattern": (gen_pattern, "Reaction-diffusion Turing patterns: spots, stripes, labyrinth, coral, mitosis, holes"),
    "scales": (gen_scales, "Overlapping staggered scales: fish, reptiles, cones, feathers"),
    "segments": (gen_segments, "Segmented body along a spine: caterpillars, worms, bamboo, vertebrae"),
    "feather": (gen_feather, "Feather with rachis, asymmetric vane, splits and barbs"),
    "ellipse": (gen_ellipse, "Ellipse, egg, teardrop or crescent"),
    "rings": (gen_rings, "Concentric growth rings with noise"),
    "path": (gen_path, "Any SVG path as the starting form"),
}


# ---------------------------------------------------------------------------------------------
# Rules


def rule_transform(shape, r, ctx):
    scale = r.pair("scale", 1, -100, 100)
    sx = r.number("scale_x", 1, -100, 100) * scale[0]
    sy = r.number("scale_y", 1, -100, 100) * scale[1]
    angle = r.number("rotate", 0, -3600, 3600)
    move = r.pair("translate", 0, -100, 100)
    shear = r.number("shear", 0, -10, 10)
    if shear:
        shape.map(lambda q: np.column_stack([q[:, 0] + shear * q[:, 1], q[:, 1]]))
    return affine(shape, (sx, sy), angle, move)


def _place(shape, x, y, angle, scale=1.0, flip=False):
    """A copy of ``shape`` with its base at (x, y), pointing along ``angle`` (degrees; −90 is up)."""
    bx, by = shape.base()
    copy = shape.copy()
    if flip:
        copy.map(lambda q: np.column_stack([2 * bx - q[:, 0], q[:, 1]]))
    return affine(copy, (scale, scale), angle + 90, (x, y), (bx, by))


def _jittered(rng, amount):
    return 1 + rng.uniform(-amount, amount)


def rule_radial(shape, r, ctx):
    """n copies around the centre, pointing outward; ``rings`` adds alternating whorls."""
    count = r.integer("count", 5, 1, 360)
    radius = r.number("radius", 0.0, -10, 10)
    start = r.number("start", -90, -3600, 3600)
    rings = r.integer("rings", 1, 1, 12)
    ring_scale = r.number("ring_scale", 0.78, 0.05, 2)
    ring_radius = r.number("ring_radius", 0.75, 0, 2)
    jitter = r.number("jitter", 0.0, 0, 1) * ctx["naturalness"]
    spin = r.number("spiral", 0, -360, 360)
    spread = r.number("spread", 360, 1, 360)
    rng = ctx["rng"]
    result = Shape()
    total = 0
    step = spread / count if spread >= 360 else spread / max(count - 1, 1)
    for ring in range(rings):
        # Whorls alternate: each ring sits in the gaps of the one outside it.
        offset = start + ring * 180 / count + ring * spin
        scale = ring_scale ** ring
        for k in range(count):
            total += 1
            require(total <= MAX_COPIES, f"radial makes more than {MAX_COPIES} copies", "resource_limit")
            angle = offset + step * k + rng.uniform(-1, 1) * 8 * jitter
            rr = radius * ring_radius ** ring
            x, y = rr * math.cos(math.radians(angle)), rr * math.sin(math.radians(angle))
            result.extend(_place(shape, x, y, angle, scale * _jittered(rng, 0.08 * jitter)))
    # Outer whorls are drawn first so inner ones sit on top.
    return result


def rule_mirror(shape, r, ctx):
    """Bilateral symmetry: add a reflected copy across a vertical (x) or horizontal (y) axis."""
    axis = r.choice("axis", "x", ("x", "y"))
    at = r.number("at", 0.0, -100, 100)
    keep = r.flag("keep", True)
    asym = r.number("asymmetry", 0.03, 0, 0.5) * ctx["naturalness"]
    mirrored = shape.copy()
    i = 0 if axis == "x" else 1

    def flip(q):
        q = q.copy()
        q[:, i] = 2 * at - q[:, i]
        return q

    mirrored.map(flip)
    if asym:
        rng = ctx["rng"]
        factor = _jittered(rng, asym)
        cx, cy = mirrored.base()
        affine(mirrored, (factor, factor), rng.uniform(-3, 3) * asym * 10, (cx, cy), (cx, cy))
    return shape.extend(mirrored) if keep else mirrored


def _resolve_spine(spec, ctx, where):
    if isinstance(spec, list):
        require(2 <= len(spec) <= 2000 and all(isinstance(q, list) and len(q) == 2 for q in spec),
                f"{where} must be 2–2000 [x, y] points", field=where)
        return np.array([[finite(v, where, -100, 100) for v in q] for q in spec], dtype=float)
    if spec in SPINES:
        return spine_points(spec)
    require(isinstance(spec, str), f"{where} must be a spine name ({', '.join(SPINES)}), points or a part", field=where)
    name = spec[5:] if spec.startswith("part:") else spec
    require(name in ctx["parts"], f"{where} names unknown part {name!r}", field=where)
    shape = ctx["parts"][name]
    if len(shape.anchors.get("spine", [])) >= 2:
        return np.array([(x, y) for x, y, _ in shape.anchors["spine"]])
    lines = [e["points"] for e in shape.elements() if not e["closed"]]
    if lines:
        return max(lines, key=lambda q: trace.length(q))
    outline = max((e["points"] for e in shape.elements()), key=lambda q: trace.length(q, True))
    # A closed outline's spine: its centre line from bottom to top.
    x0, y0, x1, y1 = shape.bounds()
    return np.array([[(x0 + x1) / 2, y1], [(x0 + x1) / 2, y0]]) if len(outline) else outline


def rule_along(shape, r, ctx):
    """Copies along a spine (leaves on a stem, pinnae on a frond, vertebrae, spines on a back).
    ``side`` alternate/both/left/right; ``scale`` [start, end] or ``envelope`` sizes them."""
    spine = _resolve_spine(r.raw("spine", "straight"), ctx, "rule.spine")
    count = r.integer("count", 8, 1, MAX_COPIES)
    side = r.choice("side", "alternate", ("alternate", "both", "left", "right", "center"))
    angle = r.number("angle", 50, -180, 180)
    scale = r.pair("scale", [1, 0.5], 0.001, 100)
    envelope = r.choice("envelope", "none", ("none", *LEAF_SHAPES))
    start, end = r.pair("range", [0.05, 0.95], 0, 1)
    jitter = r.number("jitter", 0.3, 0, 1) * ctx["naturalness"]
    turn = r.number("turn", 0, -360, 360)
    rng = ctx["rng"]
    points = trace.resample(spine, 400)
    distance = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(points, axis=0).T))])
    total = distance[-1]
    result = Shape()
    for k in range(count):
        s = start + (end - start) * (k / max(count - 1, 1) if count > 1 else 0.5)
        index = int(np.searchsorted(distance, s * total).clip(1, len(points) - 1))
        x, y = points[index]
        tangent = points[index] - points[index - 1]
        heading = math.degrees(math.atan2(tangent[1], tangent[0]))
        size = scale[0] + (scale[1] - scale[0]) * s
        if envelope != "none":
            size *= float(profile(envelope, np.array([s]))[0])
        size *= _jittered(rng, 0.15 * jitter)
        sides = {"alternate": [1 if k % 2 else -1], "both": [-1, 1], "left": [-1], "right": [1], "center": [0]}[side]
        for sign in sides:
            if size <= 0.002:
                continue
            direction = (heading + sign * (angle + rng.uniform(-8, 8) * jitter) if sign else heading) + turn
            result.extend(_place(shape, x, y, direction, size, flip=sign < 0))
    return result


def rule_at(shape, r, ctx):
    """Copies at another part's anchors (``branches.tips``, ``stem.tip``, ``body.points``)."""
    ref = r.raw("anchors")
    require(isinstance(ref, str) and "." in ref, "rule.anchors must be PART.ANCHOR, e.g. branches.tips", field="rule.anchors")
    name, anchor = ref.rsplit(".", 1)
    require(name in ctx["parts"], f"rule.anchors names unknown part {name!r}", field="rule.anchors")
    anchors = ctx["parts"][name].anchors.get(anchor)
    require(anchors, f"Part {name!r} has no {anchor!r} anchors; it has {', '.join(ctx['parts'][name].anchors) or 'none'}",
            field="rule.anchors")
    scale = r.number("scale", 1, 0.001, 100)
    keep = r.number("probability", 1, 0, 1)
    limit = r.integer("limit", MAX_COPIES, 1, MAX_COPIES)
    orient = r.flag("orient", True)
    offset = r.number("angle", 0, -360, 360)
    jitter = r.number("jitter", 0.3, 0, 1) * ctx["naturalness"]
    rng = ctx["rng"]
    result = Shape()
    placed = 0
    for x, y, angle in anchors:
        if placed >= limit or rng.random() > keep:
            continue
        heading = (angle if orient else -90) + offset + rng.uniform(-25, 25) * jitter
        result.extend(_place(shape, x, y, heading, scale * _jittered(rng, 0.25 * jitter)))
        placed += 1
    require(placed, "No anchors were kept; raise probability", field="rule.probability")
    return result


def rule_scatter(shape, r, ctx):
    """Poisson-disc scatter inside a boundary with log-normal sizes and random turns."""
    count = r.integer("count", 30, 1, MAX_COPIES)
    distance = r.number("spacing", 0.0, 0, 2)
    within = r.raw("within", "circle")
    size = r.number("scale", 0.15, 0.001, 10)
    sigma = r.number("size_variation", 0.2, 0, 1)
    turn = r.number("rotation", 180, 0, 180)
    rng = ctx["rng"]
    boundary = boundary_polygon(within, ctx, "rule.within")
    lo, hi = boundary.min(axis=0), boundary.max(axis=0)
    extent = float(max(np.abs(lo).max(), np.abs(hi).max()))
    spacing = distance or extent * 1.6 / math.sqrt(count)
    samples = _poisson(rng, spacing, count, lambda q: trace.contains(boundary, q), extent)
    result = Shape()
    for x, y in samples:
        factor = size * math.exp(rng.normal(0, sigma * ctx["naturalness"] + 1e-9))
        result.extend(_place(shape, x, y, -90 + rng.uniform(-turn, turn), factor))
    return result


def rule_phyllotaxis(shape, r, ctx):
    """Copies at Vogel's golden-angle positions, oriented outward (florets, seeds, scales)."""
    count = r.integer("count", 60, 1, MAX_COPIES)
    angle = r.number("angle", GOLDEN_ANGLE, 1, 359)
    scale = r.pair("scale", [0.04, 0.12], 0.001, 10)
    radius = r.number("radius", 1, 0.01, 100)
    result = Shape()
    c = radius / math.sqrt(count)
    for n in range(1, count + 1):
        rr = c * math.sqrt(n)
        theta = math.radians(n * angle)
        s = scale[0] + (scale[1] - scale[0]) * rr / radius
        result.extend(_place(shape, rr * math.cos(theta), rr * math.sin(theta), math.degrees(theta), s))
    return result


def rule_grid(shape, r, ctx):
    """Copies on a square or hexagonal grid with jitter, optionally inside a boundary."""
    rows = r.integer("rows", 5, 1, 100)
    columns = r.integer("columns", 5, 1, 100)
    kind = r.choice("layout", "hex", ("hex", "square"))
    scale = r.number("scale", 0.3, 0.001, 10)
    jitter = r.number("jitter", 0.1, 0, 1) * ctx["naturalness"]
    within = r.raw("within")
    require(rows * columns <= MAX_COPIES, f"grid makes more than {MAX_COPIES} copies", "resource_limit")
    boundary = boundary_polygon(within, ctx, "rule.within") if within else None
    rng = ctx["rng"]
    result = Shape()
    for row in range(rows):
        for col in range(columns):
            x = -1 + 2 * (col + 0.5 + (0.5 if kind == "hex" and row % 2 else 0)) / columns
            y = -1 + 2 * (row + 0.5) / rows
            x += rng.uniform(-jitter, jitter) / columns
            y += rng.uniform(-jitter, jitter) / rows
            if boundary is not None and not trace.contains(boundary, (x, y)):
                continue
            result.extend(_place(shape, x, y, -90 + rng.uniform(-20, 20) * jitter, scale * _jittered(rng, jitter * 0.2)))
    return result


def rule_noise(shape, r, ctx):
    """Smooth, seeded wobble: outlines move along their normals; lines sideways."""
    amount = r.number("amount", 0.04, 0, 1) * ctx["naturalness"] * 2
    frequency = r.number("frequency", 3, 0.1, 64)
    octaves = r.integer("octaves", 3, 1, 6)
    x0, y0, x1, y1 = shape.bounds()
    size = max(x1 - x0, y1 - y0, 1e-6)
    rng = ctx["rng"]
    for e in shape.elements():
        q = e["points"]
        if len(q) < 3:
            continue
        if len(q) < 48 and e["smooth"]:
            q = trace.resample(q, 48, e["closed"])
        n = normals(q, e["closed"])
        offset = loop_noise(len(q), rng, octaves, frequency, e["closed"]) * amount * size
        e["points"] = q + n * offset[:, None]
    return shape


def rule_warp(shape, r, ctx):
    """D'Arcy Thompson coordinate warps: bend, taper, bulge, pinch, twist, shear, wave."""
    kind = r.choice("kind", "bend", ("bend", "taper", "bulge", "pinch", "twist", "shear", "wave", "noise"))
    amount = r.number("amount", 0.3, -10, 10)
    x0, y0, x1, y1 = shape.bounds()
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    w, h = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
    seed = int(ctx["rng"].integers(0, 2**31))

    def fn(q):
        x, y = q[:, 0], q[:, 1]
        s = (y1 - y) / h  # 0 at the base (bottom), 1 at the top
        if kind == "bend":
            return np.column_stack([x + amount * s * s * h, y])
        if kind == "taper":
            return np.column_stack([cx + (x - cx) * (1 - amount * s), y])
        if kind in ("bulge", "pinch"):
            d = np.hypot((x - cx) / w, (y - cy) / h) * 2
            k = (1 + amount * np.exp(-d * d * 2)) if kind == "bulge" else (1 - amount * np.exp(-d * d * 2))
            return np.column_stack([cx + (x - cx) * k, cy + (y - cy) * k])
        if kind == "twist":
            d = np.hypot(x - cx, y - cy) / max(w, h)
            a = amount * math.pi * d
            return np.column_stack([cx + (x - cx) * np.cos(a) - (y - cy) * np.sin(a),
                                    cy + (x - cx) * np.sin(a) + (y - cy) * np.cos(a)])
        if kind == "shear":
            return np.column_stack([x + amount * (cy - y), y])
        if kind == "wave":
            return np.column_stack([x + amount * 0.1 * w * np.sin(math.tau * s * 2), y])
        d = field_noise(np.column_stack([x / max(w, h), y / max(w, h)]), seed, 2.5)
        return q + d * amount * 0.1 * max(w, h)

    for e in shape.elements():
        if len(e["points"]) >= 2 and e["smooth"] and len(e["points"]) < 24:
            e["points"] = trace.resample(e["points"], 24, e["closed"])
    return shape.map(fn)


def rule_jitter(shape, r, ctx):
    """Independent small changes per element (fluctuating asymmetry): no two copies identical."""
    move = r.number("position", 0.02, 0, 1) * ctx["naturalness"] * 2
    turn = r.number("rotation", 5, 0, 180) * ctx["naturalness"] * 2
    grow = r.number("scale", 0.06, 0, 1) * ctx["naturalness"] * 2
    rng = ctx["rng"]
    x0, y0, x1, y1 = shape.bounds()
    size = max(x1 - x0, y1 - y0, 1e-6)
    for e in shape.elements():
        if not len(e["points"]):
            continue
        c = e["points"].mean(axis=0)
        k = 1 + rng.uniform(-grow, grow)
        e["points"] = rotate((e["points"] - c) * k, rng.uniform(-turn, turn)) + c + rng.uniform(-move, move, 2) * size
    return shape


def rule_smooth(shape, r, ctx):
    """Round corners by Chaikin corner cutting."""
    iterations = r.integer("iterations", 2, 1, 5)
    for e in shape.elements():
        if len(e["points"]) >= 3:
            e["points"] = trace.chaikin(e["points"], iterations, e["closed"])
            e["smooth"] = False
    return shape


def rule_clip(shape, r, ctx):
    """Keep elements whose centre lies inside a boundary (circle, square or a part)."""
    boundary = boundary_polygon(r.raw("within", "circle"), ctx, "rule.within")
    for tag in list(shape.tags):
        shape.tags[tag] = [e for e in shape.tags[tag] if len(e["points"]) and trace.contains(boundary, e["points"].mean(axis=0))]
    return shape


def rule_inset(shape, r, ctx):
    """Shrink each closed element toward its centroid (gaps between cells or scales)."""
    amount = r.number("amount", 0.1, -1, 0.95)
    for e in shape.elements():
        if e["closed"] and len(e["points"]) >= 3:
            c = trace.centroid(e["points"])
            e["points"] = c + (e["points"] - c) * (1 - amount)
    return shape


def rule_gradient(shape, r, ctx):
    """Scale each element by its position: radially (larger outward) or along an axis."""
    axis = r.choice("axis", "radial", ("radial", "x", "y"))
    start, end = r.pair("scale", [1, 0.5], 0.001, 100)
    x0, y0, x1, y1 = shape.bounds()
    reach = max(abs(x0), abs(x1), abs(y0), abs(y1), 1e-6)
    for e in shape.elements():
        if not len(e["points"]):
            continue
        c = e["points"].mean(axis=0)
        if axis == "radial":
            s = math.hypot(*c) / reach
        elif axis == "x":
            s = (c[0] - x0) / max(x1 - x0, 1e-6)
        else:
            s = (y1 - c[1]) / max(y1 - y0, 1e-6)
        e["points"] = c + (e["points"] - c) * (start + (end - start) * s)
    return shape


def rule_use(shape, r, ctx):
    """Add another part's geometry (to repeat, transform or blend it here)."""
    name = r.raw("part")
    require(isinstance(name, str) and name in ctx["parts"], "rule.part must name an earlier part", field="rule.part")
    return shape.extend(ctx["parts"][name].copy())


def check_post(r):
    """Validate blend / occlude / intersect settings; they run after fitting, in pixels."""
    kind = r.raw("rule")
    if kind == "blend":
        r.number("radius", 0.03, 0, 0.5)
    elif kind == "occlude":
        r.number("gap", 1.5, 0, 50)
    else:
        within = r.raw("within")
        require(within is None or within in ("circle", "square") or (isinstance(within, str) and re.fullmatch(r"[a-z0-9-]+", within)),
                "intersect.within must be circle, square or a part name", field="rule.within")
        r.choice("half", "none", ("none", "top", "bottom", "left", "right"))
        r.number("gap", 0, 0, 50)


RULES = {
    "transform": (rule_transform, "Scale, rotate, shear and move"),
    "radial": (rule_radial, "Radial symmetry: n copies pointing outward; rings make alternating whorls"),
    "mirror": (rule_mirror, "Bilateral symmetry with slight fluctuating asymmetry"),
    "along": (rule_along, "Copies along a spine: alternate, opposite or one side, sized by an envelope"),
    "at": (rule_at, "Copies at another part's anchors (tips, forks, points)"),
    "scatter": (rule_scatter, "Poisson-disc scatter with log-normal sizes"),
    "phyllotaxis": (rule_phyllotaxis, "Copies at golden-angle positions"),
    "grid": (rule_grid, "Copies on a hex or square grid with jitter"),
    "noise": (rule_noise, "Smooth wobble along outlines"),
    "warp": (rule_warp, "Coordinate warps: bend, taper, bulge, pinch, twist, shear, wave, noise"),
    "jitter": (rule_jitter, "Per-element variation in position, rotation and size"),
    "smooth": (rule_smooth, "Round corners (Chaikin)"),
    "clip": (rule_clip, "Keep elements inside a boundary"),
    "inset": (rule_inset, "Shrink elements toward their centres"),
    "gradient": (rule_gradient, "Size gradient radially or along an axis"),
    "use": (rule_use, "Bring in an earlier part's geometry"),
    "blend": (check_post, "Smooth union (metaball-like fillets) of the part's outlines, in pixels"),
    "occlude": (check_post, "Paint-order occlusion: later elements cover earlier ones, edges kept with a gap"),
    "intersect": (check_post, "Keep what lies inside another part, a circle or square fitted to this part, and/or one half of it"),
}


# ---------------------------------------------------------------------------------------------
# Presets


def _p(values, key, default):
    return values.get(key, default)


def preset_flower(v):
    petals = int(_p(v, "petals", 5))
    rings = int(_p(v, "rings", 1))
    center = float(_p(v, "center", 0.32))
    return [
        {"name": "petals", "generator": "petal",
         "params": {"tip": _p(v, "tip", "round"), "width": _p(v, "petal_width", 0.55)},
         "rules": [{"rule": "transform", "scale": 0.5},
                   {"rule": "radial", "count": petals, "radius": center * 0.55, "rings": rings, "jitter": 0.5},
                   {"rule": "noise", "amount": 0.01, "frequency": 2}],
         "fill": _p(v, "petal_color", "#f6b7c8"), "stroke": "rgba(120, 40, 70, 0.35)", "stroke_width": 1},
        {"name": "center", "generator": "phyllotaxis",
         "params": {"count": int(_p(v, "florets", 90)), "element": "seed", "size": 0.9},
         "rules": [{"rule": "transform", "scale": center}],
         "fill": _p(v, "center_color", "#e6a817"), "stroke": "rgba(90, 50, 0, 0.5)", "stroke_width": 0.6},
    ]


def preset_daisy(v):
    return preset_flower({"petals": 21, "tip": "notched", "petal_width": 0.32, "center": 0.24,
                          "petal_color": "#ffffff", "center_color": "#f2b705", "florets": 120, **v})


def preset_sunflower(v):
    return [
        {"name": "back-petals", "generator": "petal", "params": {"tip": "pointed", "width": 0.4, "profile": "lanceolate"},
         "rules": [{"rule": "transform", "scale": 0.42}, {"rule": "radial", "count": int(_p(v, "petals", 21)), "radius": 0.36,
                                                          "start": -90 + 180 / int(_p(v, "petals", 21)), "jitter": 0.6}],
         "fill": "#e9a400"},
        {"name": "petals", "generator": "petal", "params": {"tip": "pointed", "width": 0.42, "profile": "lanceolate"},
         "rules": [{"rule": "transform", "scale": 0.45}, {"rule": "radial", "count": int(_p(v, "petals", 21)), "radius": 0.36, "jitter": 0.6}],
         "fill": _p(v, "petal_color", "#ffc21a")},
        {"name": "seeds", "generator": "phyllotaxis", "params": {"count": int(_p(v, "seeds", 340)), "element": "seed", "gradient": 0.5},
         "rules": [{"rule": "transform", "scale": 0.4}], "fill": "#4a2c12", "stroke": "#2a170a", "stroke_width": 0.4},
    ]


def preset_rose(v):
    count = int(_p(v, "petals", 5))
    return [
        {"name": "outer", "generator": "petal", "params": {"tip": "round", "width": 0.75},
         "rules": [{"rule": "transform", "scale": 0.5}, {"rule": "radial", "count": count, "radius": 0.18, "rings": 3,
                                                         "ring_scale": 0.72, "ring_radius": 0.55, "spiral": 17, "jitter": 0.7},
                   {"rule": "occlude", "gap": 1.2}],
         "fill": _p(v, "petal_color", "#d7263d"), "stroke": "#7a0f1f", "stroke_width": 1},
        {"name": "bud", "generator": "spiral", "params": {"turns": 2.2, "growth": 2.4, "width": 0.18},
         "rules": [{"rule": "transform", "scale": 0.13}], "fill": "#a3142a"},
    ]


def preset_tree(v):
    leaves = _p(v, "leaves", True)
    parts = [{"name": "branches", "generator": "branch",
              "params": {"habit": _p(v, "habit", "decurrent"), "depth": int(_p(v, "depth", 6)),
                         **({"angle": v["angle"]} if "angle" in v else {})},
              "fill": _p(v, "bark_color", "#5b4636")}]
    if leaves:
        parts.append({"name": "leaves", "generator": "leaf", "params": {"shape": _p(v, "leaf_shape", "elliptic"), "veins": "none"},
                      "rules": [{"rule": "at", "anchors": "branches.tips", "scale": float(_p(v, "leaf_size", 0.045)),
                                 "probability": 0.95}, {"rule": "jitter", "rotation": 20}],
                      "fill": _p(v, "leaf_color", "#4f8a3b")})
    return parts


def preset_pine(v):
    return [
        {"name": "trunk", "generator": "tentacle", "params": {"length": 2.1, "width": 0.07, "taper": 0.6, "curl": 0, "wave": 0,
                                                              "wobble": 0.05, "heading": -90},
         "fill": "#5a3d2b"},
        {"name": "boughs", "generator": "superformula", "params": {"m": 0, "n1": 2, "n2": 2, "n3": 2},
         "rules": [{"rule": "transform", "scale_x": 0.75, "scale_y": 0.18},
                   {"rule": "warp", "kind": "noise", "amount": 0.6},
                   {"rule": "along", "spine": "part:trunk", "count": int(_p(v, "tiers", 7)), "side": "center",
                    "scale": [1.1, 0.25], "range": [0.15, 0.95]}, {"rule": "blend", "radius": 0.012}],
         "fill": _p(v, "needle_color", "#2f5d3a")},
    ]


def preset_fern(v):
    return [{"name": "frond", "generator": "lsystem",
             "params": {"axiom": "X", "rules": {"X": "F+[[X]-X]-F[-FX]+X", "F": "FF"}, "iterations": int(_p(v, "iterations", 5)),
                        "angle": float(_p(v, "angle", 25)), "jitter": 3},
             "fill": "transparent", "stroke": _p(v, "color", "#3f7d3a"), "stroke_width": float(_p(v, "stroke_width", 1.2))}]


def preset_frond(v):
    return [
        {"name": "rachis", "generator": "tentacle", "params": {"length": 2, "width": 0.025, "taper": 0.8, "curl": 0.08,
                                                               "wave": 0, "wobble": 0.1, "heading": -90},
         "fill": "#3d6b2f"},
        {"name": "pinnae", "generator": "leaf", "params": {"shape": "lanceolate", "margin": "crenate", "teeth": 9,
                                                           "tooth_depth": 0.25, "veins": "none"},
         "rules": [{"rule": "along", "spine": "part:rachis", "count": int(_p(v, "pinnae", 28)), "side": "both",
                    "angle": 62, "scale": [0.36, 0.08], "envelope": "lanceolate", "range": [0.04, 0.98]}],
         "fill": _p(v, "color", "#4c8c3a")},
    ]


def preset_leaf(v):
    return [{"name": "leaf", "generator": "leaf",
             "params": {k: v[k] for k in ("shape", "margin", "teeth", "tooth_depth", "veins", "vein_count", "petiole", "width") if k in v}
             | {"petiole": v.get("petiole", 0.25)},
             "rules": [{"rule": "warp", "kind": "bend", "amount": float(_p(v, "bend", 0.12))}],
             "fill": _p(v, "color", "#5c9b3c"), "styles": {"veins": {"stroke": _p(v, "vein_color", "#cfe8a8"), "stroke_width": 1.2}}}]


def preset_branch(v):
    return [
        {"name": "stem", "generator": "tentacle", "params": {"length": 2.2, "width": 0.035, "taper": 0.9, "curl": 0.1,
                                                             "wave": 0.4, "waves": 0.6, "heading": -70},
         "fill": "#6b4f2a"},
        {"name": "leaves", "generator": "leaf", "params": {"shape": _p(v, "leaf_shape", "ovate"), "petiole": 0.2, "veins": "pinnate"},
         "rules": [{"rule": "along", "spine": "part:stem", "count": int(_p(v, "leaf_count", 9)), "side": "alternate",
                    "angle": 48, "scale": [0.42, 0.2], "range": [0.15, 0.97]}],
         "fill": _p(v, "leaf_color", "#5d9b40"), "styles": {"veins": {"stroke": "#cfe5a6", "stroke_width": 0.8}}},
    ]


def preset_vine(v):
    return [
        {"name": "vine", "generator": "tentacle", "params": {"length": 3, "width": 0.025, "taper": 0.5, "curl": 0.3,
                                                             "wave": 1.6, "waves": 0.9, "heading": -20},
         "fill": "#4d7a2e"},
        {"name": "leaves", "generator": "leaf", "params": {"shape": "cordate", "veins": "palmate", "vein_count": 5, "petiole": 0.25},
         "rules": [{"rule": "along", "spine": "part:vine", "count": int(_p(v, "leaf_count", 7)), "side": "alternate",
                    "angle": 60, "scale": [0.3, 0.16], "range": [0.08, 0.88]}],
         "fill": _p(v, "leaf_color", "#5fa344"), "styles": {"veins": {"stroke": "#bfe09a", "stroke_width": 0.8}}},
        {"name": "tendril", "generator": "spiral", "params": {"turns": 2.5, "growth": 4},
         "rules": [{"rule": "at", "anchors": "vine.tip", "scale": 0.16}],
         "fill": "transparent", "stroke": "#4d7a2e", "stroke_width": 2},
    ]


def preset_grass(v):
    blades = int(_p(v, "blades", 14))
    return [{"name": "blades", "generator": "leaf", "params": {"shape": "linear", "veins": "none", "width": 0.09},
             "rules": [{"rule": "warp", "kind": "bend", "amount": 0.25},
                       {"rule": "radial", "count": blades, "radius": 0, "start": -150, "spread": 120, "jitter": 1}],
             "fill": _p(v, "color", "#5e9e3a")}]


def preset_fur_blob(v):
    """A furry body: tufts pointing out all round an ellipse, the body over them, inner flicks on top."""
    count = int(_p(v, "tufts", 56))
    aspect = float(_p(v, "aspect", 1.0))
    color = _p(v, "color", "#b07848")
    length = float(_p(v, "length", 0.22))

    def ring(radius):
        t = np.linspace(0, math.tau, 181)
        return [[round(radius * aspect * math.cos(a), 4), round(radius * math.sin(a), 4)] for a in t]

    def fur(spine, n, size, width):
        # Along a clockwise ring, side "left" at 90 degrees points straight out.
        return [{"rule": "warp", "kind": "bend", "amount": 0.25},
                {"rule": "along", "spine": spine, "count": max(n, 1), "side": "left", "angle": 90,
                 "scale": [size, size], "range": [0, 1 - 1 / max(n, 1)], "jitter": 1}], width

    tuft_rules, _ = fur(ring(0.97), count, length, 0.3)
    flick_rules, _ = fur(ring(0.86), count // 2, length * 0.55, 0.16)
    return [
        {"name": "tufts", "generator": "leaf", "params": {"shape": "lanceolate", "veins": "none", "width": 0.3},
         "rules": tuft_rules, "fill": color},
        {"name": "body", "generator": "ellipse", "params": {"aspect": aspect}, "fill": color},
        {"name": "flicks", "generator": "leaf", "params": {"shape": "linear", "veins": "none", "width": 0.16},
         "rules": flick_rules, "fill": _p(v, "flick_color", "rgba(60, 35, 20, 0.35)")},
    ]


def preset_starfish(v):
    return [
        {"name": "body", "generator": "superformula", "params": {"m": int(_p(v, "arms", 5)), "n1": 2, "n2": 7, "n3": 7},
         "rules": [{"rule": "noise", "amount": 0.02, "frequency": 4}, {"rule": "warp", "kind": "noise", "amount": 0.25}],
         "fill": _p(v, "color", "#e8743b")},
        {"name": "tubercles", "generator": "ellipse",
         "rules": [{"rule": "scatter", "count": int(_p(v, "bumps", 70)), "within": "body", "scale": 0.025, "size_variation": 0.3},
                   {"rule": "gradient", "axis": "radial", "scale": [1.6, 0.5]}],
         "fill": _p(v, "bump_color", "#f6c28b")},
    ]


def preset_jellyfish(v):
    count = int(_p(v, "tentacles", 8))
    return [
        {"name": "tentacles", "generator": "tentacle", "params": {"length": 2.4, "width": 0.035, "taper": 0.7, "curl": 0.15,
                                                                  "wave": 1.6, "waves": 2.0},
         "rules": [{"rule": "along", "spine": [[-0.7, 0], [0.7, 0]], "count": count, "side": "center", "turn": 90,
                    "scale": [1, 1], "range": [0, 1]}, {"rule": "jitter", "rotation": 6},
                   {"rule": "noise", "amount": 0.02, "frequency": 1.5}],
         "fill": _p(v, "tentacle_color", "rgba(201, 120, 255, 0.75)")},
        {"name": "bell", "generator": "superformula", "params": {"m": 8, "n1": 6, "n2": 1.8, "n3": 1.8, "rotate": 0},
         "rules": [{"rule": "transform", "scale_x": 0.95, "scale_y": 0.8, "translate": [0, 0.05]},
                   {"rule": "warp", "kind": "noise", "amount": 0.15},
                   {"rule": "intersect", "half": "top"}],
         "fill": _p(v, "bell_color", "rgba(181, 92, 255, 0.85)")},
    ]


def preset_octopus(v):
    color = _p(v, "color", "#c4456a")
    return [
        {"name": "arms", "generator": "tentacle", "params": {"length": 1.5, "width": 0.13, "taper": 1.1, "curl": 0.55,
                                                             "wave": 1.0, "waves": 1.0, "tip_width": 0.03},
         "rules": [{"rule": "radial", "count": 8, "radius": 0.18, "start": 20, "spread": 140, "jitter": 0.6},
                   {"rule": "noise", "amount": 0.008, "frequency": 2}],
         "hidden": True},
        {"name": "head", "generator": "ellipse", "params": {"form": "egg", "aspect": 0.85},
         "rules": [{"rule": "transform", "scale": 0.62, "translate": [0, -0.62]}], "hidden": True},
        {"name": "body", "generator": "blob", "params": {"variation": 0.1},
         "rules": [{"rule": "transform", "scale": 0.36, "translate": [0, -0.05]}, {"rule": "use", "part": "arms"},
                   {"rule": "use", "part": "head"}, {"rule": "blend", "radius": 0.025}],
         "fill": color},
        {"name": "eyes", "generator": "ellipse",
         "rules": [{"rule": "transform", "scale": 0.08, "translate": [0.2, -0.5]}, {"rule": "mirror", "axis": "x"}],
         "fill": "#fff7e8", "stroke": "#3a1020", "stroke_width": 2},
    ]


def preset_shell(v):
    return [{"name": "shell", "generator": "shell",
             "params": {"growth": float(_p(v, "growth", 3.0)), "chambers": int(_p(v, "chambers", 14)), "ribs": int(_p(v, "ribs", 0))},
             "fill": _p(v, "color", "#f1dcc0"), "stroke": "#8a5a3b", "stroke_width": 1.5,
             "styles": {"chambers": {"stroke": "#9b6b47", "stroke_width": 1.2}}}]


def preset_snail(v):
    body = _p(v, "body_color", "#c9a27e")
    return [
        {"name": "horns", "generator": "tentacle", "params": {"length": 0.4, "width": 0.025, "taper": 0.2, "tip_width": 0.022,
                                                              "curl": 0.1, "wave": 0, "wobble": 0.05},
         "rules": [{"rule": "radial", "count": 2, "radius": 0, "start": -125, "spread": 35},
                   {"rule": "transform", "translate": [-0.78, 0.5]}],
         "fill": body},
        {"name": "body", "generator": "ellipse", "params": {"form": "teardrop", "point": 1.2},
         "rules": [{"rule": "transform", "rotate": 90}, {"rule": "transform", "scale_x": 1.05, "scale_y": 0.2,
                                                           "translate": [0.05, 0.62]}],
         "fill": body},
        {"name": "shell", "generator": "shell", "params": {"growth": 2.4, "chambers": 0, "whorls": 3},
         "rules": [{"rule": "transform", "scale": 0.55, "rotate": 90, "translate": [0.2, 0.08]}],
         "fill": _p(v, "shell_color", "#b5651d"), "stroke": "#6b3a12", "stroke_width": 1.5,
         "styles": {"chambers": {"stroke": "#6b3a12", "stroke_width": 2}}},
    ]


def preset_caterpillar(v):
    color = _p(v, "color", "#7cc242")
    return [
        {"name": "body", "generator": "segments", "params": {"count": int(_p(v, "segments", 13)), "spine": "s-curve",
                                                             "bend": 0.22, "width": 0.2, "profile": "caterpillar"},
         "rules": [{"rule": "transform", "rotate": 90}, {"rule": "occlude", "gap": 1.5}],
         "fill": color, "stroke": "#3f6e1f", "stroke_width": 1},
        {"name": "head", "generator": "ellipse",
         "rules": [{"rule": "at", "anchors": "body.head", "scale": 0.24, "orient": False}],
         "fill": _p(v, "head_color", "#5a9a2c"), "stroke": "#3f6e1f", "stroke_width": 1},
    ]


def preset_worm(v):
    return [{"name": "worm", "generator": "tentacle", "params": {"length": 2.6, "width": 0.11, "taper": 0.15, "tip_width": 0.03,
                                                                  "curl": 0.1, "wave": 2.2, "waves": 1.4, "heading": 0},
             "fill": _p(v, "color", "#d98a8a")}]


def preset_mushroom(v):
    return [
        {"name": "stem", "generator": "tentacle", "params": {"length": 1.1, "width": 0.13, "taper": 0.2,
                                                             "tip_width": 0.04, "curl": 0.02, "wave": 0.2},
         "rules": [{"rule": "transform", "translate": [0, 0.8]}], "fill": _p(v, "stem_color", "#efe4d0")},
        {"name": "cap", "generator": "superformula", "params": {"m": 4, "n1": 4, "n2": 4, "n3": 4},
         "rules": [{"rule": "transform", "scale_x": 0.85, "scale_y": 0.5, "translate": [0, -0.05]},
                   {"rule": "noise", "amount": 0.01}, {"rule": "intersect", "half": "top"}],
         "fill": _p(v, "cap_color", "#c8341f")},
        {"name": "spots", "generator": "blob", "params": {"variation": 0.4},
         "rules": [{"rule": "scatter", "count": int(_p(v, "spots", 11)), "within": {"generator": "ellipse", "params": {"aspect": 1.7}},
                    "scale": 0.07, "size_variation": 0.35},
                   {"rule": "transform", "scale_x": 0.42, "scale_y": 0.22, "translate": [0, -0.25]},
                   {"rule": "intersect", "within": "cap", "gap": 1}],
         "fill": _p(v, "spot_color", "#fbf5e6")},
    ]


def preset_feather(v):
    return [{"name": "feather", "generator": "feather", "params": {"barbs": int(_p(v, "barbs", 40)), "curve": 0.15},
             "fill": _p(v, "color", "#9fb7c9"),
             "styles": {"rachis": {"stroke": "#4d5c66", "stroke_width": 2},
                        "barbs": {"stroke": "rgba(70, 90, 110, 0.45)", "stroke_width": 0.8}}}]


def preset_coral(v):
    return [{"name": "coral", "generator": "branch",
             "params": {"habit": "coral", "depth": int(_p(v, "depth", 5)), "width": 0.14, "alpha": 3, "ratio": 0.78,
                        "jitter": 0.45, "curve": 0.4, "angle": 28},
             "rules": [{"rule": "blend", "radius": 0.012}], "fill": _p(v, "color", "#ff7f6e")}]


def preset_brain_coral(v):
    return [
        {"name": "dome", "generator": "blob", "params": {"variation": 0.15}, "fill": _p(v, "base_color", "#c9925b")},
        {"name": "grooves", "generator": "pattern", "params": {"kind": "labyrinth", "grid": 120},
         "rules": [{"rule": "intersect", "within": "dome", "gap": 2}], "fill": _p(v, "color", "#e6b07a")},
    ]


def preset_cactus(v):
    ribs = int(_p(v, "ribs", 8))
    color = _p(v, "color", "#5a9a5a")
    lines = " ".join(
        f"M{x:.3f} 0.98 Q{x * 1.3:.3f} 0 {x:.3f} -0.85" for x in (-0.24 + 0.48 * k / (ribs - 1) for k in range(ribs)))
    return [
        {"name": "column", "generator": "superformula", "params": {"m": 4, "n1": 6, "n2": 6, "n3": 6},
         "rules": [{"rule": "transform", "scale_x": 0.27, "scale_y": 1}], "hidden": True},
        {"name": "body", "generator": "tentacle", "params": {"length": 1.0, "width": 0.15, "taper": 0.0, "tip_width": 0.0,
                                                             "curl": 0, "wave": 0, "wobble": 0.05, "heading": 0, "elbow": -90, "elbow_at": 0.42},
         "rules": [{"rule": "transform", "translate": [0.12, 0.3]}, {"rule": "mirror", "axis": "x"},
                   {"rule": "use", "part": "column"}, {"rule": "blend", "radius": 0.02}],
         "fill": color},
        {"name": "ribs", "generator": "path", "params": {"d": lines},
         "rules": [{"rule": "transform", "scale": 0.97}, {"rule": "intersect", "within": "body"}],
         "fill": "transparent", "stroke": "rgba(30, 70, 30, 0.6)", "stroke_width": 1.5},
    ]


def preset_cells(v):
    return [{"name": "cells", "generator": "cells", "params": {"count": int(_p(v, "count", 45)), "gap": 0.08, "within": "circle",
                                                               "outline": True},
             "fill": _p(v, "color", "#9ad0a0"), "stroke": "#4f8a5b", "stroke_width": 1,
             "styles": {"outline": {"fill": "transparent", "stroke": "#3d6b47", "stroke_width": 2.5}}}]


def preset_giraffe(v):
    return [{"name": "patches", "generator": "cells", "params": {"count": int(_p(v, "count", 36)), "gap": 0.14, "within": "square",
                                                                 "round": 2},
             "rules": [{"rule": "noise", "amount": 0.01, "frequency": 5}],
             "fill": _p(v, "color", "#a0522d")}]


def preset_spots(v):
    return [{"name": "pattern", "generator": "pattern", "params": {"kind": _p(v, "kind", "spots"), "grid": int(_p(v, "grid", 110))},
             "fill": _p(v, "color", "#2b1d12")}]


def preset_scales(v):
    return [{"name": "scales", "generator": "scales", "params": {"rows": int(_p(v, "rows", 8)), "columns": int(_p(v, "columns", 7))},
             "rules": [{"rule": "clip", "within": "square"}, {"rule": "occlude", "gap": 1.5}],
             "fill": _p(v, "color", "#4f9db0"), "stroke": "#2c5d6b", "stroke_width": 1}]


def preset_dandelion(v):
    return [
        {"name": "seeds", "generator": "tentacle", "params": {"length": 1, "width": 0.01, "taper": 0.2, "curl": 0, "wave": 0,
                                                              "wobble": 0.05, "heading": -90},
         "rules": [{"rule": "radial", "count": int(_p(v, "seeds", 60)), "radius": 0.05, "jitter": 0.8}],
         "fill": _p(v, "color", "#e9e6dc")},
        {"name": "head", "generator": "ellipse", "rules": [{"rule": "transform", "scale": 0.08}], "fill": "#8a7c5c"},
    ]


def preset_cell(v):
    return [
        {"name": "membrane", "generator": "blob", "params": {"lobes": 3, "variation": 0.5},
         "rules": [{"rule": "noise", "amount": 0.03, "frequency": 2}], "fill": _p(v, "color", "rgba(150, 210, 190, 0.8)"),
         "stroke": "#3f8f7a", "stroke_width": 2},
        {"name": "nucleus", "generator": "blob", "params": {"variation": 0.3},
         "rules": [{"rule": "transform", "scale": 0.28, "translate": [0.1, -0.05]}], "fill": "#4d7f9b"},
        {"name": "organelles", "generator": "ellipse", "params": {"form": "egg", "aspect": 0.6},
         "rules": [{"rule": "scatter", "count": 9, "within": "membrane", "scale": 0.06, "size_variation": 0.3}],
         "fill": "#e0a96d"},
    ]


def preset_pinecone(v):
    return [
        {"name": "outline", "generator": "ellipse", "params": {"form": "egg", "aspect": 0.62}, "hidden": True},
        {"name": "scales", "generator": "scales", "params": {"rows": int(_p(v, "rows", 14)), "columns": 7, "shape": "pointed",
                                                             "overlap": 0.5},
         "rules": [{"rule": "transform", "scale_x": 0.66, "scale_y": 1.05}, {"rule": "clip", "within": "outline"},
                   {"rule": "occlude", "gap": 1.2}],
         "fill": _p(v, "color", "#8b5a2b"), "stroke": "#4e2f12", "stroke_width": 1},
    ]


def preset_lily_pad(v):
    return [{"name": "pad", "generator": "path", "params": {"d": "M0 0 L0.17 -0.985 A1 1 0 1 1 -0.17 -0.985 Z"},
             "rules": [{"rule": "noise", "amount": 0.008}], "fill": _p(v, "color", "#4f9e4a")},
            {"name": "veins", "generator": "path", "params": {"d": " ".join(
                f"M0 0 L{math.cos(math.radians(a)):.3f} {math.sin(math.radians(a)):.3f}" for a in range(-60, 241, 25))},
             "rules": [{"rule": "transform", "scale": 0.92}, {"rule": "intersect", "within": "pad", "gap": 2}],
             "fill": "transparent", "stroke": "#8fca7a", "stroke_width": 1.2}]


PRESETS = {
    "flower": (preset_flower, "Petals in alternating whorls around a phyllotaxis centre", {"petals": 5, "rings": 1, "tip": "round"}),
    "daisy": (preset_daisy, "Many notched white rays around a golden disc", {"petals": 21}),
    "sunflower": (preset_sunflower, "Two whorls of pointed rays around a Vogel seed head", {"petals": 21, "seeds": 340}),
    "rose": (preset_rose, "Spiralling, occluded petal whorls around a bud", {"petals": 5}),
    "tree": (preset_tree, "Branching tree with leaves at the twig tips", {"habit": "decurrent", "depth": 6, "leaves": True}),
    "pine": (preset_pine, "Conifer: a trunk with tapering tiers of boughs", {"tiers": 7}),
    "fern": (preset_fern, "Classic L-system fern (strokes)", {"iterations": 5, "angle": 25}),
    "frond": (preset_frond, "Pinnate frond: lanceolate pinnae along a curved rachis", {"pinnae": 28}),
    "leaf": (preset_leaf, "One leaf with venation and petiole", {"shape": "ovate", "margin": "entire"}),
    "branch": (preset_branch, "A leafy twig: alternate leaves along a curved stem", {"leaf_count": 9}),
    "vine": (preset_vine, "Curling vine with heart-shaped leaves and a tendril", {"leaf_count": 7}),
    "grass": (preset_grass, "A tuft of bending grass blades", {"blades": 14}),
    "fur-blob": (preset_fur_blob, "A furry body: tufts all round an ellipse with inner flicks", {"tufts": 56, "aspect": 1.0}),
    "starfish": (preset_starfish, "Superformula starfish with tubercles", {"arms": 5}),
    "jellyfish": (preset_jellyfish, "Scalloped bell with waving tentacles", {"tentacles": 8}),
    "octopus": (preset_octopus, "Head and eight curling arms blended into one body", {}),
    "shell": (preset_shell, "Nautilus-like chambered spiral shell", {"growth": 3, "chambers": 14}),
    "snail": (preset_snail, "Snail: spiral shell on a soft body", {}),
    "caterpillar": (preset_caterpillar, "Segmented caterpillar on an S-curve", {"segments": 13}),
    "worm": (preset_worm, "Wriggling worm", {}),
    "mushroom": (preset_mushroom, "Spotted cap on a stem", {"spots": 11}),
    "feather": (preset_feather, "Feather with vane, rachis and barbs", {"barbs": 40}),
    "coral": (preset_coral, "Branching coral with blended joints", {"depth": 6}),
    "brain-coral": (preset_brain_coral, "Reaction-diffusion labyrinth on a dome", {}),
    "cactus": (preset_cactus, "Saguaro-style column with arms and ribs", {"ribs": 8}),
    "cell": (preset_cell, "A cell with nucleus and organelles", {}),
    "cells": (preset_cells, "Voronoi tissue in a round boundary", {"count": 45}),
    "giraffe": (preset_giraffe, "Giraffe coat patches", {"count": 36}),
    "spots": (preset_spots, "Reaction-diffusion animal markings (kind: spots, stripes, labyrinth …)", {"kind": "spots"}),
    "scales": (preset_scales, "Overlapping fish scales", {"rows": 8, "columns": 7}),
    "dandelion": (preset_dandelion, "Seed head of radiating fine stalks", {"seeds": 60}),
    "pinecone": (preset_pinecone, "Golden-angle cone scales with overlap", {"scales": 89}),
    "lily-pad": (preset_lily_pad, "Notched round pad with radiating veins", {}),
}


def catalog():
    """Discovery: presets, generators and rules with their documentation."""
    import inspect

    def doc(fn):
        return (inspect.getdoc(fn) or "").split("\n\n")[0].replace("\n", " ")

    return {
        "presets": {name: {"description": text, "params": defaults} for name, (_, text, defaults) in PRESETS.items()},
        "generators": {name: {"description": text, "details": doc(fn)} for name, (fn, text) in GENERATORS.items()},
        "rules": {name: {"description": text} for name, (_, text) in RULES.items()},
        "frame": "Unit frame about −1…1, y down. Forms grow upward from a base at +y; copies attach by their base.",
        "post_rules": list(POST_RULES),
        "docs": "docs/organic.md",
    }


# ---------------------------------------------------------------------------------------------
# Building parts


def build_parts(parts, seed, naturalness):
    """Generate every part in unit coordinates. Returns [(spec, Shape)]."""
    require(isinstance(parts, list) and 1 <= len(parts) <= MAX_PARTS, f"An organic form needs 1–{MAX_PARTS} parts", field="parts")
    ctx = {"parts": {}, "naturalness": naturalness}
    built = []
    names = set()
    for index, spec in enumerate(parts):
        where = f"parts[{index}]"
        require(isinstance(spec, dict), f"{where} must be an object", field=where)
        allowed = {"name", "generator", "params", "rules", "fill", "stroke", "stroke_width", "opacity", "styles", "seed", "hidden"}
        unknown = sorted(set(spec) - allowed)
        require(not unknown, f"Unknown {where} field(s) {', '.join(unknown)}; allowed: {', '.join(sorted(allowed))}",
                field=f"{where}.{unknown[0]}" if unknown else None)
        name = spec.get("name", f"part-{index + 1}")
        require(isinstance(name, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,40}", name) and name not in names,
                f"{where}.name must be a unique lower-case slug", field=f"{where}.name")
        names.add(name)
        generator = spec.get("generator")
        require(generator in GENERATORS, f"{where}.generator must be one of {', '.join(GENERATORS)}",
                field=f"{where}.generator", allowed=list(GENERATORS))
        part_seed = spec.get("seed", seed * 1009 + index * 7919)
        require(isinstance(part_seed, int) and part_seed >= 0, f"{where}.seed must be a whole number", field=f"{where}.seed")
        ctx["rng"] = np.random.default_rng(part_seed)
        params = Params(spec.get("params", {}), f"{where}.params")
        shape = GENERATORS[generator][0](params, ctx)
        params.done()
        rules = spec.get("rules", [])
        require(isinstance(rules, list) and len(rules) <= 24, f"{where}.rules must be a list of at most 24 rules", field=f"{where}.rules")
        post = []
        for k, rule in enumerate(rules):
            rwhere = f"{where}.rules[{k}]"
            require(isinstance(rule, dict) and rule.get("rule") in RULES, f"{rwhere}.rule must be one of {', '.join(RULES)}",
                    field=f"{rwhere}.rule", allowed=list(RULES))
            settings = Params(rule, rwhere)
            settings.used.add("rule")
            if rule["rule"] in POST_RULES:
                check_post(settings)
                post.append(dict(rule))
            else:
                union = getattr(shape, "union", False)
                shape = RULES[rule["rule"]][0](shape, settings, ctx)
                shape.union = union
            settings.done()
            count = sum(len(items) for items in shape.tags.values())
            require(count <= MAX_ELEMENTS, f"{where} has more than {MAX_ELEMENTS} elements", "resource_limit")
            require(sum(len(e["points"]) for e in shape.elements()) <= MAX_POINTS,
                    f"{where} has more than {MAX_POINTS} points", "resource_limit")
        shape.post = post
        ctx["parts"][name] = shape
        built.append(({**spec, "name": name}, shape))
    return built


def _colors(spec, project):
    from .design import resolve_color
    from .render import color

    for key in ("fill", "stroke"):
        if key in spec:
            color(resolve_color(spec[key], project.state))


def fit_transform(built, width, height, padding, preserve=True):
    """Scale and offset mapping the unit frame onto the layer box."""
    boxes = [shape.bounds() for _, shape in built if shape.elements()]
    require(boxes, "The organic form has no geometry", field="parts")
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes)
    y1 = max(b[3] for b in boxes)
    sx = (width - 2 * padding) / max(x1 - x0, 1e-9)
    sy = (height - 2 * padding) / max(y1 - y0, 1e-9)
    if preserve:
        sx = sy = min(sx, sy)
    ox = (width - (x1 - x0) * sx) / 2 - x0 * sx
    oy = (height - (y1 - y0) * sy) / 2 - y0 * sy
    return sx, sy, ox, oy, (x0, y0, x1, y1)


def natural_size(built, width, height, default=400):
    """Fill in a missing width or height from the form's aspect ratio."""
    boxes = [shape.bounds() for _, shape in built if shape.elements()]
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes)
    y1 = max(b[3] for b in boxes)
    aspect = max(x1 - x0, 1e-6) / max(y1 - y0, 1e-6)
    if width is None and height is None:
        return (default, max(8, round(default / aspect))) if aspect >= 1 else (max(8, round(default * aspect)), default)
    if width is None:
        return max(8, round(height * aspect)), height
    if height is None:
        return width, max(8, round(width / aspect))
    return width, height


def traced(points):
    """A closed loop from contour tracing: its direction marks it as an outline or a hole."""
    return {**element(points, True, True), "traced": True}


def apply_post(shape_elements, post, size, others, resolution=2):
    """Pixel-space rules on box-coordinate elements. ``resolution`` supersamples the raster."""
    from PIL import Image, ImageFilter

    elements = shape_elements
    w, h = size
    big = (max(1, int(w * resolution)), max(1, int(h * resolution)))
    for rule in post:
        kind = rule["rule"]
        closed = [e for e in elements if e["closed"] and len(e["points"]) >= 3]
        open_lines = [e for e in elements if not e["closed"]]
        if kind == "blend":
            radius = rule.get("radius", 0.03) * max(w, h) * resolution
            mask = trace.rasterize(closed, big, resolution)
            image = Image.fromarray(mask.astype(np.uint8) * 255)
            if radius > 0:
                image = image.filter(ImageFilter.GaussianBlur(radius))
            field = np.asarray(image, dtype=float) / 255
            loops = trace.contours(field, 0.5)
            elements = [traced(trace.simplify(loop / resolution, 0.35, True))
                        for loop in loops if abs(trace.area(loop)) > 4 * resolution ** 2] + open_lines
        elif kind == "occlude":
            gap = rule.get("gap", 1.5) * resolution
            labels = np.zeros((big[1], big[0]), dtype=np.int32)
            from PIL import ImageDraw

            for index, e in enumerate(closed, 1):
                image = Image.new("L", big, 0)
                ImageDraw.Draw(image).polygon([tuple(q) for q in e["points"] * resolution], fill=255)
                labels[np.asarray(image) > 127] = index
            pieces = []
            for index in range(1, len(closed) + 1):
                mask = labels == index
                if not mask.any():
                    continue
                if gap >= 1:
                    image = Image.fromarray(mask.astype(np.uint8) * 255).filter(ImageFilter.MinFilter(int(gap) * 2 + 1))
                    mask = np.asarray(image) > 127
                ys, xs = np.nonzero(mask)
                if not len(xs):
                    continue
                x0, y0 = max(0, xs.min() - 2), max(0, ys.min() - 2)
                crop = mask[y0:ys.max() + 3, x0:xs.max() + 3]
                for loop in trace.contours(crop.astype(float), 0.5):
                    if abs(trace.area(loop)) > 2 * resolution ** 2:
                        pieces.append(traced(trace.simplify((loop + [x0, y0]) / resolution, 0.35, True)))
            elements = pieces + open_lines
        else:
            within = rule.get("within")
            half = rule.get("half", "none")
            boxes = [e["points"] for e in closed] or [e["points"] for e in open_lines]
            if not boxes:
                continue
            allp = np.vstack(boxes) * resolution
            bx0, by0 = np.floor(allp.min(axis=0)).astype(int)
            bx1, by1 = np.ceil(allp.max(axis=0)).astype(int)
            from PIL import ImageDraw

            if isinstance(within, str) and within in others:
                region = trace.rasterize(others[within], big, resolution)
            elif within in ("circle", "square"):
                image = Image.new("L", big, 0)
                draw = ImageDraw.Draw(image)
                (draw.ellipse if within == "circle" else draw.rectangle)((bx0, by0, bx1, by1), fill=255)
                region = np.asarray(image) > 127
            else:
                require(within is None, f"intersect.within names unknown part {within!r}", field="rule.within")
                region = np.ones((big[1], big[0]), dtype=bool)
            cx, cy = (bx0 + bx1) // 2, (by0 + by1) // 2
            if half == "top":
                region[max(0, cy):] = False
            elif half == "bottom":
                region[:max(0, cy)] = False
            elif half == "left":
                region[:, max(0, cx):] = False
            elif half == "right":
                region[:, :max(0, cx)] = False
            gap = rule.get("gap", 0) * resolution
            if gap >= 1:
                region = np.asarray(Image.fromarray(region.astype(np.uint8) * 255).filter(
                    ImageFilter.MinFilter(int(gap) * 2 + 1))) > 127
            if closed:
                mask = trace.rasterize(closed, big, resolution) & region
                loops = trace.contours(mask.astype(float), 0.5)
                kept = [traced(trace.simplify(loop / resolution, 0.35, True))
                        for loop in loops if abs(trace.area(loop)) > 2 * resolution ** 2]
            else:
                kept = []
            lines = []
            for e in open_lines:
                q = e["points"] * resolution
                inside = [0 <= int(x) < big[0] and 0 <= int(y) < big[1] and region[int(y), int(x)] for x, y in q]
                run = []
                for point, flag in zip(e["points"], inside):
                    if flag:
                        run.append(point)
                    elif len(run) > 1:
                        lines.append(element(np.array(run), False, e["smooth"]))
                        run = []
                    else:
                        run = []
                if len(run) > 1:
                    lines.append(element(np.array(run), False, e["smooth"]))
            elements = kept + lines
    return elements


def render_paths(built, width, height, padding, preserve=True, strokes=None):
    """Fit the parts into the box and produce one path per part output: [(name, tag, d)]."""
    sx, sy, ox, oy, _ = fit_transform(built, width, height, padding, preserve)
    results, placed = [], {}
    for spec, shape in built:
        tags = {}
        for tag, items in shape.tags.items():
            moved = [{**e, "points": np.column_stack([e["points"][:, 0] * sx + ox, e["points"][:, 1] * sy + oy])}
                     for e in items if len(e["points"])]
            tags[tag] = moved
        post = getattr(shape, "post", [])
        if getattr(shape, "union", False) and not any(r["rule"] == "blend" for r in post):
            post = [{"rule": "blend", "radius": 0.0}] + post
        if post:
            tags["shape"] = apply_post(tags.get("shape", []), post, (width, height), placed)
        placed[spec["name"]] = [e for e in tags.get("shape", []) if e["closed"]]
        if spec.get("hidden"):
            continue
        for tag, items in tags.items():
            if not items:
                continue
            # Generated outlines all run the same way, so overlapping copies (mirrored ones
            # included) unite under the nonzero fill rule instead of cancelling into holes.
            items = [e if e.get("traced") or not e["closed"] else {**e, "points": trace.oriented(e["points"])}
                     for e in items]
            tolerance = 0.2
            for _ in range(8):
                simplified = [{**e, "points": trace.simplify(e["points"], tolerance, e["closed"])} for e in items]
                d = trace.elements_path(simplified)
                commands = len(re.findall(r"[MLCZ]", d))
                if commands <= MAX_COMMANDS and len(d) <= 262_144:
                    break
                tolerance *= 2
            else:
                raise VixlError("resource_limit", f"Part {spec['name']!r} is too detailed for one path; lower counts or depth",
                                field="parts")
            if d:
                results.append((spec["name"], tag, d))
    return results


# ---------------------------------------------------------------------------------------------
# Operation


def schemas(add):
    from .schema import S, N, SIZE, COORD

    obj = {"type": "object"}
    add("organic", {
        "name": S,
        "preset": {"enum": list(PRESETS)},
        "parts": {"type": "array", "items": obj, "minItems": 1, "maxItems": MAX_PARTS},
        "params": obj,
        "colors": {"type": "object", "additionalProperties": S},
        "seed": {"type": "integer", "minimum": 0},
        "naturalness": {"type": "number", "minimum": 0, "maximum": 1},
        "width": SIZE,
        "height": SIZE,
        "x": COORD,
        "y": COORD,
        "padding": {"type": "number", "minimum": 0},
        "stretch": {"type": "boolean"},
        "fill": {**S, "description": "Fill for every filled part; colors names single parts and wins over it."},
        "stroke": {**S, "description": "Line color for every part, extra line outputs such as chambers and veins included."},
        "stroke_width": {**N, "description": "Line width for every part and extra line output."},
    }, anyOf=[{"required": ["preset"]}, {"required": ["parts"]}, {"required": ["target"]}])


def recipe_parts(recipe):
    """The part list for a stored or requested recipe (a preset with overrides, or parts)."""
    if recipe.get("parts") is not None:
        return deepcopy(recipe["parts"])
    preset = recipe.get("preset")
    require(preset in PRESETS, f"Unknown organic preset {preset!r}; presets: {', '.join(PRESETS)}", field="preset",
            allowed=list(PRESETS))
    params = recipe.get("params", {})
    require(isinstance(params, dict), "params must be an object", field="params")
    return PRESETS[preset][0](dict(params))


def regrown_style(kept, derived, op):
    """Style for a regrown layer: its current look, except what this operation sets again.

    ``colors``/``fill`` restore the recipe's fill, ``stroke`` and ``stroke_width`` their own
    field, and a new ``preset`` or ``parts`` list restyles everything. Anything else (a plain
    new seed) keeps the colors and widths the user has since edited on the layer.
    """
    fresh = bool({"preset", "parts"} & set(op))
    result = dict(kept)
    for key, fields in (("fill", ("colors", "fill")), ("stroke", ("stroke",)), ("stroke_width", ("stroke_width",))):
        if fresh or any(field in op for field in fields):
            result[key] = derived[key]
    return result


def execute(project, op):
    from .operations import append_layer, default_name, execute as apply
    from .model import new_layer

    target = project.layer(op["target"]) if op.get("target") else None
    recipe = deepcopy(target.get("organic", {})) if target else {}
    if target is not None:
        require(recipe, f"{target['name']!r} was not made by organic; target an organic layer or group", field="target")
    for key in RECIPE_KEYS:
        if key in op:
            recipe[key] = deepcopy(op[key])
    if "preset" in op and "parts" not in op:
        recipe.pop("parts", None)
    if "parts" in op:
        recipe.pop("preset", None)
    seed = recipe.setdefault("seed", 0)
    naturalness = float(recipe.setdefault("naturalness", 0.5))
    parts = recipe_parts(recipe)
    colors = recipe.get("colors", {})
    require(isinstance(colors, dict), "colors maps part names to fill colors", field="colors")
    if "fill" in recipe:
        # One fill for the whole form; line-only parts (a fern, its veins) stay unfilled.
        for spec in parts:
            if str(spec.get("fill", "")).strip().lower() not in UNFILLED:
                spec["fill"] = recipe["fill"]
    for spec in parts:
        if spec.get("name") in colors:
            spec["fill"] = colors[spec["name"]]
    if "stroke" in recipe or "stroke_width" in recipe:
        for spec in parts:
            if "stroke" in recipe:
                spec["stroke"] = recipe["stroke"]
            if "stroke_width" in recipe:
                spec["stroke_width"] = recipe["stroke_width"]
    unknown = sorted(set(colors) - {spec.get("name") for spec in parts})
    require(not unknown, f"colors names unknown part(s) {', '.join(unknown)}; parts: "
            f"{', '.join(spec.get('name', '?') for spec in parts)}", field="colors")
    built = build_parts(parts, seed, naturalness)
    for spec, _ in built:
        _colors(spec, project)
        for tag, style in (spec.get("styles") or {}).items():
            require(isinstance(style, dict) and not set(style) - {"fill", "stroke", "stroke_width", "opacity"},
                    f"styles.{tag} takes fill, stroke, stroke_width and opacity", field=f"styles.{tag}")
            _colors(style, project)
    if target is not None:
        width = op.get("width", target["width"])
        height = op.get("height", target["height"])
    else:
        width, height = natural_size(built, op.get("width"), op.get("height"))
    project.limits.size(width, height)
    widest = max([spec.get("stroke_width", 0) for spec, _ in built if spec.get("stroke", "transparent") != "transparent"]
                 + [recipe.get("stroke_width", style.get("stroke_width", 1))
                    for spec, _ in built for style in (spec.get("styles") or {}).values()] + [0])
    padding = finite(recipe.get("padding", 2 + widest / 2), "padding", 0, min(width, height) / 2 - 1)
    paths = render_paths(built, width, height, padding, not recipe.get("stretch", False))
    styles = {spec["name"]: spec for spec, _ in built}
    layers = []
    for name, tag, d in paths:
        spec = styles[name]
        style = {"fill": spec.get("fill", "#5c8f4a"), "stroke": spec.get("stroke", "transparent"),
                 "stroke_width": spec.get("stroke_width", 1)}
        # What the operation sets outranks the preset's own line styling for an output.
        extra = {k: v for k, v in (spec.get("styles") or {}).get(tag, {}).items() if k not in recipe}
        if tag != "shape":
            style = {"fill": "transparent", "stroke": spec.get("stroke", "rgba(0, 0, 0, 0.45)"),
                     "stroke_width": spec.get("stroke_width", 1)}
        style.update(extra)
        layers.append((name if tag == "shape" else f"{name}-{tag}", d, style, spec.get("opacity", 1)))
    require(layers, "The organic form drew nothing", field="parts")
    stored = {k: v for k, v in recipe.items() if k in RECIPE_KEYS}

    def path_layer(label, d, style, opacity, x=0, y=0):
        layer = new_layer(label, "shape", width, height, shape="path", path=d, path_view=[width, height],
                          fill=style["fill"], stroke=style["stroke"], stroke_width=style["stroke_width"],
                          line_cap="round", x=x, y=y)
        layer["opacity"] = finite(opacity, "opacity", 0, 1)
        return layer

    def place(layer):
        for key in ("x", "y"):
            if key in op:
                layer[key] = finite(op[key], key)

    if target is None:
        name = op["name"] if "name" in op else default_name(project, recipe.get("preset", "organic"))
        x = op.get("x", 0)
        y = op.get("y", 0)
        if len(layers) == 1:
            label, d, style, opacity = layers[0]
            layer = path_layer(name, d, style, opacity, x, y)
            layer["organic"] = stored
            append_layer(project, layer)
            return
        ids = []
        for label, d, style, opacity in layers:
            layer = path_layer(default_name(project, f"{name}/{label}"), d, style, opacity, x, y)
            append_layer(project, layer)
            ids.append(layer["id"])
        apply(project, {"type": "group", "name": name, "targets": ids})
        group = project.layer(name)
        group["organic"] = stored
        group["role"] = group.get("role", "content")
        project.state["active_layer"] = group["id"]
        return
    if target["type"] == "shape":
        require(len(layers) == 1, f"{target['name']!r} is a single path; this recipe draws {len(layers)} parts. "
                "Remove it and create the form again", field="target")
        label, d, style, opacity = layers[0]
        kept = {"fill": target["fill"], "stroke": target.get("stroke", "transparent"),
                "stroke_width": target.get("stroke_width", 1)}
        target.update(path=d, path_view=[width, height], width=width, height=height, line_cap="round",
                      **regrown_style(kept, style, op))
        target["organic"] = stored
        place(target)
        project.state["active_layer"] = target["id"]
        return
    require(target["type"] == "group", "Organic regeneration needs the organic group or path", field="target")
    from .design import descendants

    old = descendants(project, target["id"])
    keep_styles = {layer["name"].split("/", 1)[-1]: layer for layer in project.state["layers"] if layer["id"] in old}
    project.state["layers"][:] = [layer for layer in project.state["layers"] if layer["id"] not in old]
    position = project.state["layers"].index(target)
    created = []
    for label, d, style, opacity in layers:
        previous = keep_styles.get(label)
        if previous is not None:
            kept = {"fill": previous["fill"], "stroke": previous.get("stroke", "transparent"),
                    "stroke_width": previous.get("stroke_width", 1)}
            style = regrown_style(kept, style, op)
            if not {"preset", "parts"} & set(op):
                opacity = previous["opacity"]
        layer = path_layer(default_name(project, f"{target['name']}/{label}"), d, style, opacity)
        layer.update(parent=target["id"], width=width, height=height)
        created.append(layer)
        project.state["layers"].insert(position, layer)
        position += 1
    require(len(project.state["layers"]) <= project.limits.max_layers, "Layer limit reached", "resource_limit")
    sx = target["width"] / target["content_width"]
    sy = target["height"] / target["content_height"]
    target.update(content_width=width, content_height=height, width=max(1, round(width * sx)), height=max(1, round(height * sy)))
    target["organic"] = stored
    place(target)
    project.state["active_layer"] = target["id"]


def compile_command(cmd, args):
    if cmd != "organic":
        return None
    import json

    from .commands import Parser, number_or_center

    p = Parser(prog="vixl organic", description="Composable organic shapes. vixl organics lists presets, generators and rules.")
    p.add_argument("preset", nargs="?", choices=list(PRESETS))
    p.add_argument("--name")
    p.add_argument("--target")
    p.add_argument("--seed", type=int)
    p.add_argument("--naturalness", type=float)
    for key in ("width", "height"):
        p.add_argument("--" + key, type=int)
    for key in ("x", "y"):
        p.add_argument("--" + key, type=number_or_center)
    for key in ("padding", "stroke-width"):
        p.add_argument("--" + key, type=float)
    p.add_argument("--stroke")
    p.add_argument("--fill", help="Fill for every filled part (--color names single parts)")
    p.add_argument("--set", action="append", help="Preset parameter KEY=VALUE (JSON values allowed), e.g. petals=8")
    p.add_argument("--color", action="append", help="Part fill PART=COLOR, e.g. petals=#fff")
    p.add_argument("--parts", type=json.loads, help="JSON list of parts (instead of a preset)")
    p.add_argument("--stretch", action="store_true", default=None)
    a = vars(p.parse_args(args))
    op = {"type": "organic"}
    for key, value in a.items():
        if value is None or key in ("set", "color"):
            continue
        op[key] = value
    if a.get("set"):
        params = {}
        for item in a["set"]:
            require("=" in item, "Use --set KEY=VALUE", "usage_error")
            key, value = item.split("=", 1)
            try:
                params[key] = json.loads(value)
            except ValueError:
                params[key] = value
        op["params"] = params
    if a.get("color"):
        op["colors"] = dict(item.split("=", 1) for item in a["color"])
    return op
