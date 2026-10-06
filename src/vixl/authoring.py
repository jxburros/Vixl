"""Deterministic organic paths and explicit composition intent."""

import argparse
from copy import deepcopy
import math
import random

from .errors import require

TYPES = ("organic-shape", "path-fit", "layer-intent", "font-fallbacks")
KINDS = ("leaf", "petal", "blob", "rose")


def schemas(add):
    from .schema import S, N, B, SIZE, COORD
    add("organic-shape", {
        "kind": {"enum": list(KINDS)}, "name": S, "seed": {"type": "integer", "minimum": 0},
        "lobes": {"type": "integer", "minimum": 3, "maximum": 32},
        "variation": {"type": "number", "minimum": 0, "maximum": 1},
        "fill": S, "stroke": S, "stroke_width": N, "width": SIZE, "height": SIZE,
        "x": COORD, "y": COORD,
    })
    add("path-fit", {"padding": {"type": "number", "minimum": 0}, "preserve_aspect": B}, ["target"])
    add("layer-intent", {"role": {"enum": ["content", "decoration", "background"]},
                         "allow_overlap": {"type": "array", "items": S, "maxItems": 512},
                         "allow_crop": B}, ["target"])
    add("font-fallbacks", {"fonts": {"type": "array", "items": S, "maxItems": 16}}, ["fonts"])


def fit_path(path, width, height, padding=0, preserve_aspect=True):
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.svgLib.path import parse_path
    require(2 * padding < min(width, height), "Padding must leave space inside the path box")
    bounds = BoundsPen(None)
    parse_path(path, bounds)
    require(bounds.bounds is not None, "Path has no drawable geometry")
    x0, y0, x1, y1 = bounds.bounds
    sx = (width - 2 * padding) / max(x1 - x0, 1e-9)
    sy = (height - 2 * padding) / max(y1 - y0, 1e-9)
    if preserve_aspect:
        sx = sy = min(sx, sy)
    pen = SVGPathPen(None)
    transform = (sx, 0, 0, sy, (width - (x1 - x0) * sx) / 2 - x0 * sx,
                 (height - (y1 - y0) * sy) / 2 - y0 * sy)
    parse_path(path, TransformPen(pen, transform))
    return pen.getCommands()


def organic_path(kind, seed=0, lobes=7, variation=0.2):
    from .creative import pen_path
    rng = random.Random(seed)
    if kind == "leaf":
        bend = (rng.random() - 0.5) * variation * 0.6
        return f"M0 1 C{-0.8+bend} .65 {-0.65+bend} .15 0 0 C{0.65+bend} .15 {0.8+bend} .65 0 1 Z"
    if kind == "petal":
        skew = (rng.random() - 0.5) * variation
        return f"M0 1 C-1 .5 {-0.6+skew} -.2 0 0 C{0.6+skew} -.2 1 .5 0 1 Z"
    def contour(radius, count, phase):
        pts = []
        for i in range(count * 4):
            angle = 2 * math.pi * i / (count * 4)
            r = radius * (1 + 0.12 * math.sin(count * angle + phase) +
                          variation * 0.12 * rng.uniform(-1, 1))
            pts.append([r * math.cos(angle), r * math.sin(angle)])
        return pen_path({"points": pts, "closed": True})
    if kind == "blob":
        return contour(1, lobes, rng.random() * math.tau)
    # Nested cupped petal arcs, with staggered seams and a slightly asymmetric center.
    # Open inner contours avoid the overlapping closed loops of a radial rosette.
    paths = [contour(1, lobes, rng.random())]
    for ring, radius in enumerate((0.84, 0.58, 0.34)):
        count = max(3, lobes - ring * 2)
        phase = ring * 0.58 + rng.uniform(-0.15, 0.15) * variation
        for i in range(count):
            angle = math.tau * i / count + phase
            half = math.pi / count
            a, b = angle - half, angle + half
            r = radius * (1 + rng.uniform(-0.1, 0.1) * variation)
            points = [(r * 0.65 * math.cos(a), r * 0.65 * math.sin(a)),
                      (r * 1.15 * math.cos(a + half * 0.35), r * 1.15 * math.sin(a + half * 0.35)),
                      (r * 1.15 * math.cos(b - half * 0.35), r * 1.15 * math.sin(b - half * 0.35)),
                      (r * 0.65 * math.cos(b), r * 0.65 * math.sin(b))]
            coords = [f"{x:.8g} {y:.8g}" for x, y in points]
            paths.append("M" + coords[0] + " C" + " ".join(coords[1:]))

    return " ".join(paths)


def execute(project, op):
    from .operations import execute as apply
    kind = op["type"]
    if kind == "font-fallbacks":
        from .render import resolve_font
        from .text import primary_font_data
        fonts = []
        for name in op["fonts"]:
            require(name in project.state.get("fonts", {}) or name in ("heading", "body", "DejaVuSans.ttf"), "Import fallback fonts with font import first; use their registered names")
            resolved = resolve_font(project, name)[0]
            if resolved not in project.assets and resolved != "DejaVuSans.ttf":
                import hashlib
                data = primary_font_data(project, {"font": resolved})
                resolved = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
                project.assets[resolved] = data
            fonts.append(resolved)
        project.state["font_fallbacks"] = fonts
        return
    layer = project.layer(op["target"]) if op.get("target") else None
    if kind == "layer-intent":
        require(layer is not None, "Layer intent needs a target")
        if "role" in op:
            layer["role"] = op["role"]
        if "allow_overlap" in op:
            layer["allow_overlap"] = [project.layer(name)["id"] for name in op["allow_overlap"]]
        if "allow_crop" in op:
            # A deliberate bleed or crop: checks report it as informational instead of a problem.
            if op["allow_crop"]:
                layer["allow_crop"] = True
            else:
                layer.pop("allow_crop", None)
        return
    if kind == "path-fit":
        require(layer["type"] == "shape" and layer["shape"] == "path", "Path fit needs a path layer")
        layer["path"] = fit_path(layer["path"], layer["width"], layer["height"],
                                 op.get("padding", 0), op.get("preserve_aspect", True))
        layer["path_view"] = [layer["width"], layer["height"]]
        return
    recipe = deepcopy(layer.get("organic", {})) if layer else {}
    recipe.update({key: op[key] for key in ("kind", "seed", "lobes", "variation") if key in op})
    recipe.setdefault("kind", "blob")
    recipe.setdefault("seed", 0)
    recipe.setdefault("lobes", 7)
    recipe.setdefault("variation", 0.2)
    width, height = op.get("width", layer["width"] if layer else 256), op.get("height", layer["height"] if layer else 256)
    path = fit_path(organic_path(**recipe), width, height, min(2, width / 10, height / 10), False)
    fields = {key: op[key] for key in ("name", "fill", "stroke", "stroke_width", "x", "y") if key in op}
    if layer:
        require(layer["type"] == "shape" and layer["shape"] == "path", "Organic editing needs a path layer")
        layer.update(fields, path=path, width=width, height=height, path_view=[width, height])
    else:
        apply(project, {"type": "shape", "shape": "path", "path": path,
                        "width": width, "height": height, "fill": "transparent", "stroke": "black", **fields})
        layer = project.layer()
    layer["organic"] = recipe


def compile_command(cmd, args):
    if cmd not in TYPES:
        return None
    from .commands import Parser
    p = Parser(prog=f"vixl {cmd}")
    if cmd == "organic-shape":
        p.add_argument("kind", nargs="?", choices=KINDS)
        for key in ("name", "target", "fill", "stroke"):
            p.add_argument("--" + key)
        for key in ("width", "height", "seed", "lobes"):
            p.add_argument("--" + key, type=int)
        for key in ("x", "y", "stroke-width", "variation"):
            p.add_argument("--" + key, type=float)
    elif cmd == "path-fit":
        p.add_argument("target")
        p.add_argument("--padding", type=float)
        p.add_argument("--stretch", dest="preserve_aspect", action="store_false", default=None)
    elif cmd == "layer-intent":
        p.add_argument("target")
        p.add_argument("--role", choices=["content", "decoration", "background"])
        p.add_argument("--allow-overlap", nargs="*")
        p.add_argument("--allow-crop", action=argparse.BooleanOptionalAction, default=None,
                       help="mark a deliberate edge crop or bleed (checks report it as informational)")
    else:
        p.add_argument("fonts", nargs="*")
    return {"type": cmd, **{k: v for k, v in vars(p.parse_args(args)).items() if v is not None}}
