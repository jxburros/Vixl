"""Seeded seamless patterns, drawn fills, and undoable snapshot-based clone stamping.

Generated fills are raster overlays, keeping the source vector editable underneath.
Clone coordinates are destination-layer pixels; sample_all uses canvas coordinates.
"""
from copy import deepcopy
import math

import numpy as np
from PIL import Image, ImageChops, ImageDraw

from .errors import require
from .model import finite, new_layer

TYPES = ("pattern-define", "pattern-fill", "pattern-stroke", "drawn-texture", "clone-stamp")
PATTERNS = ("stripes", "dots", "halftone", "hatching", "grid", "checker", "noise", "paper", "fabric", "wood", "stone", "scales")
DRAWN = ("pencil", "charcoal", "crayon", "ink-wash", "stipple", "hatch")


def schemas(add):
    original_add = add
    descriptions = {
        "name": "Name of the resulting layer or saved pattern.", "selection": "Capture the current canvas selection as the tile.",
        "seamless": "Reject custom tiles whose edge discontinuity exceeds the seam heuristic.",
        "pattern": "Built-in or document custom pattern; discover with pattern-list.",
        "scale": "Texture scale multiplier.", "rotation": "Pattern rotation in degrees.",
        "offset": "Pattern phase [x,y] in pixels.", "spacing": "Base pattern cell spacing in pixels (2–256).",
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
    params = {"pattern": {"type": "string", "examples": list(PATTERNS), "description": "Built-in pattern (" + ", ".join(PATTERNS) + ") or the name of a pattern saved in the document with pattern-define."}, "scale": {"type": "number", "exclusiveMinimum": 0}, "rotation": N,
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
            "drawn": list(DRAWN), "operations": list(TYPES),
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
    spacing = finite(options.get("spacing", 16), "spacing", 2, 256)
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
        else:
            coverage = noise if name == "noise" else .1 + .25*noise
        coverage = np.asarray(coverage, dtype=float)[..., None]
        rows = np.uint8(np.clip(bg + (fg-bg)*coverage, 0, 255))
        if variation:
            rows = _vary(rows, np.floor(u), np.floor(v), seed, variation)
        output[top:top + len(y)] = rows
    return Image.fromarray(output)


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
    else:
        coarse = Image.fromarray(rng.integers(30,255,(max(2, math.ceil(h/(18*scale))), max(2, math.ceil(w/(18*scale)))), dtype=np.uint8))
        mask = coarse.resize((w,h), Image.Resampling.BICUBIC)
    values = np.asarray(mask, dtype=np.float32)
    tooth = rng.uniform(0,1,(h,w))
    values *= (1-grain*tooth) * strength
    if preset in ("charcoal", "crayon", "pencil"):
        values[tooth > 1-.18*grain] = 0
    mask = ImageChops.multiply(Image.fromarray(np.uint8(values)), image.getchannel("A"))
    overlay = Image.new("RGBA", image.size, parse_color(color))
    mask = ImageChops.multiply(mask, overlay.getchannel("A"))
    overlay.putalpha(mask)
    return overlay


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
