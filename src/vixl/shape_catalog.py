"""Parametric, resolution-independent shape paths in layer pixel coordinates.

Lengths accept pixels, percentages, or (for dimension fractions) numbers between 0 and 1.
Compound outlines use opposite winding for holes and remain editable shape recipes.
"""

import math

from .errors import require

KINDS = tuple(
    "ring donut cloud teardrop crescent half-circle banner ribbon tag callout bracket brace wave zigzag blob curve cylinder cube document folder button toggle browser-window phone-frame tablet-frame burst starburst seal flower squircle superellipse lens vesica reuleaux quarter-circle semicircle ellipse-segment kite rhombus isosceles-triangle star-polygon hexagram octagram stairs steps frame corner-bracket L-shape T-shape notched-rectangle plus minus x saltire asterisk trefoil quatrefoil infinity gear cog ruler tick-strip sawtooth square-wave dashed-line checkmark x-mark lightning-bolt lightning sun moon flame map-pin house bell lock magnifier envelope play pause stop skip info question warning music-note sparkle star-rating flourish swash-underline scroll laurel wreath divider corner-ornament sunburst radial-burst motion-lines speed-lines confetti scribble squiggle ticket stamp postmark scalloped-border sticker".split()
)
PARAMETERS = (
    "corner_style",
    "point_radius",
    "valley_radius",
    "rotation_offset",
    "head_length",
    "head_width",
    "shaft_width",
    "heads",
    "head_style",
    "curve",
    "from",
    "to",
    "control",
    "thickness",
    "count",
    "depth",
    "hole",
    "fold",
    "pointer_size",
    "pointer_position",
    "exponent",
    "apex",
    "step",
    "arms",
    "teeth",
    "amplitude",
    "wavelength",
    "phase",
    "ray_length",
    "rating",
    "notch",
    "peel",
    "frame_shape",
    "angle",
    "petals",
    "taper",
    "spacing",
    "smooth",
    "seed",
    "radius",
)


def length(value, base, default=0):
    if value is None:
        return default
    if isinstance(value, str):
        require(value.endswith("%"), "Lengths must be pixels or percentages")
        return float(value[:-1]) * base / 100
    return float(value) * base if 0 < abs(float(value)) <= 1 else float(value)


def poly(points, closed=True):
    return "M" + " L".join(f"{x:.7g} {y:.7g}" for x, y in points) + (" Z" if closed else "")


def ellipse(x, y, w, h, reverse=False):
    if w <= 0 or h <= 0:
        return ""
    sweep = 0 if reverse else 1
    return f"M{x + w:g} {y + h / 2:g} A{w / 2:g} {h / 2:g} 0 1 {sweep} {x:g} {y + h / 2:g} A{w / 2:g} {h / 2:g} 0 1 {sweep} {x + w:g} {y + h / 2:g} Z"


def rounded_polygon(points, radii=0, style="round"):
    """Tangent quadratic corner cuts; adjacent cuts never overlap."""
    radii = radii if isinstance(radii, (list, tuple)) else [radii] * len(points)
    if not any(radii):
        return poly(points)
    cuts = []
    for i, p in enumerate(points):
        a, b = points[i - 1], points[(i + 1) % len(points)]
        da, db = math.dist(a, p), math.dist(b, p)
        r = min(max(0, radii[i]), da / 2, db / 2)
        cuts.append(
            (
                (p[0] + (a[0] - p[0]) * r / max(da, 1e-12), p[1] + (a[1] - p[1]) * r / max(da, 1e-12)),
                (p[0] + (b[0] - p[0]) * r / max(db, 1e-12), p[1] + (b[1] - p[1]) * r / max(db, 1e-12)),
                p,
            )
        )
    output = [f"M{cuts[0][0][0]:g} {cuts[0][0][1]:g}"]
    for a, b, p in cuts:
        output.append(f"L{a[0]:g} {a[1]:g}")
        if style == "chamfer":
            output.append(f"L{b[0]:g} {b[1]:g}")
        else:
            q = (a[0] + b[0] - p[0], a[1] + b[1] - p[1]) if style == "inverted" else p
            output.append(f"Q{q[0]:g} {q[1]:g} {b[0]:g} {b[1]:g}")
    return " ".join(output) + " Z"


def rectangle(w, h, radius=0, style="round"):
    raw = radius if isinstance(radius, (list, tuple)) else [radius] * 4
    rs = [max(0, length(r, min(w, h)) if isinstance(r, str) else float(r)) for r in raw]
    # CSS overlap reduction: scale all radii together, preserving their proportions.
    scale = min(
        1,
        w / max(rs[0] + rs[1], 1e-9),
        w / max(rs[2] + rs[3], 1e-9),
        h / max(rs[0] + rs[3], 1e-9),
        h / max(rs[1] + rs[2], 1e-9),
    )
    rs = [r * scale for r in rs]
    a, b, c, d = rs
    commands = [f"M{a:g} 0", f"L{w - b:g} 0"]

    def corner(r, end, ctrl, concave, sweep=1):
        if style == "chamfer" or not r:
            return f"L{end[0]:g} {end[1]:g}"
        return f"A{r:g} {r:g} 0 0 {0 if style == 'inverted' else sweep} {end[0]:g} {end[1]:g}"

    commands += [
        corner(b, (w, b), (w, 0), (w - b, b)),
        f"L{w:g} {h - c:g}",
        corner(c, (w - c, h), (w, h), (w - c, h - c)),
        f"L{d:g} {h:g}",
        corner(d, (0, h - d), (0, h), (d, h - d)),
        f"L0 {a:g}",
        corner(a, (a, 0), (0, 0), (a, a)),
        "Z",
    ]
    return " ".join(commands)


def arrowhead(tip, tangent, size, width, style="triangle"):
    """Shared head generator for arrows and markers, independent of a layer's aspect ratio."""
    tx, ty = tip
    dx, dy = tangent
    norm = max(math.hypot(dx, dy), 1e-12)
    dx, dy = dx / norm, dy / norm
    bx, by = tx - dx * size, ty - dy * size
    a, b = (bx - dy * width / 2, by + dx * width / 2), (bx + dy * width / 2, by - dx * width / 2)
    if style == "open":
        # A filled chevron, so it works without a separate stroke style.
        t = max(1, width * 0.12)
        return poly(
            [
                a,
                (tx, ty),
                b,
                (b[0] - dx * t, b[1] - dy * t),
                (tx - dx * t * 2, ty - dy * t * 2),
                (a[0] - dx * t, a[1] - dy * t),
            ]
        )
    if style == "round":
        return f"M{a[0]:g} {a[1]:g} Q{tx + dx * size * 0.4:g} {ty + dy * size * 0.4:g} {b[0]:g} {b[1]:g} Z"
    return poly(
        [a, (tx, ty), b, (tx - dx * size * 0.65, ty - dy * size * 0.65)]
        if style == "concave"
        else [a, (tx, ty), b]
    )


def arrow(layer, w, h):
    hl = min(w / 2, length(layer.get("head_length"), w, min(w * 0.35, h * 0.8)))
    hw = min(h, length(layer.get("head_width"), h, h))
    sw = min(hw, length(layer.get("shaft_width"), h, h * 0.3))
    heads, style = layer.get("heads", "end"), layer.get("head_style", "triangle")
    start, end = layer.get("from", [0, h / 2]), layer.get("to", [w, h / 2])
    control = layer.get(
        "control", [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2 - length(layer.get("curve"), h, 0)]
    )
    curved = "control" in layer or "curve" in layer or "from" in layer or "to" in layer
    if not curved and style in ("triangle", "concave"):
        left, right = (hl if heads in ("start", "both") else 0), (w - hl if heads in ("end", "both") else w)
        pts = [(left, (h - sw) / 2), (right, (h - sw) / 2)]
        if heads in ("end", "both"):
            pts += [(right, (h - hw) / 2), (w, h / 2), (right, (h + hw) / 2)]
        pts += [(right, (h + sw) / 2), (left, (h + sw) / 2)]
        if heads in ("start", "both"):
            pts += [(left, (h + hw) / 2), (0, h / 2), (left, (h - hw) / 2)]
        if style == "concave":
            pts = [
                (x + hl * 0.2 if x == left and left else x - hl * 0.2 if x == right and right < w else x, y)
                for x, y in pts
            ]
        return rounded_polygon(pts, length(layer.get("point_radius"), min(w, h), 0))
    points = []
    for i in range(65):
        t = i / 64
        points.append(
            (
                (1 - t) ** 2 * start[0] + 2 * (1 - t) * t * control[0] + t * t * end[0],
                (1 - t) ** 2 * start[1] + 2 * (1 - t) * t * control[1] + t * t * end[1],
            )
        )
    from .vector_strokes import stroke_outline, clip_run

    distances = [0.0]
    for a, b in zip(points, points[1:]):
        distances.append(distances[-1] + math.dist(a, b))
    require(distances[-1] > 0, "Arrow endpoints/control must define a nonzero curve")
    fractions = [value / distances[-1] for value in distances]
    inset = min(0.45, (sw / 2 if style == "open" else hl * 0.7) / distances[-1])
    shaft, _ = clip_run(
        points,
        fractions,
        inset if heads in ("start", "both") else 0,
        1 - inset if heads in ("end", "both") else 1,
    )
    path = stroke_outline(shaft, sw, False, "round", "round")
    if heads in ("end", "both"):
        path += " " + arrowhead(end, (end[0] - control[0], end[1] - control[1]), hl, hw, style)
    if heads in ("start", "both"):
        path += " " + arrowhead(start, (start[0] - control[0], start[1] - control[1]), hl, hw, style)
    # A single exterior prevents internal seam strokes at overlapping shaft/head joins.
    from .vector_boolean import offset

    return offset(path, 0)


def radial(n, w, h, inner=1, rotation=-90):
    return [
        (
            w / 2 + math.cos(math.radians(rotation) + i * math.tau / n) * w / 2 * (inner if i % 2 else 1),
            h / 2 + math.sin(math.radians(rotation) + i * math.tau / n) * h / 2 * (inner if i % 2 else 1),
        )
        for i in range(n)
    ]


def path(layer):
    k, w, h = layer["shape"], float(layer["width"]), float(layer["height"])
    p = layer
    mn = min(w, h)
    t = length(p.get("thickness"), mn, mn * 0.15)
    n = int(p.get("count", p.get("sides", 6)))
    n = max(2, min(n, 128))
    rot = p.get("rotation_offset", 0) - 90

    def normalized(points, closed=True):
        return poly([(x * w, y * h) for x, y in points], closed)

    def line(points, width=None):
        from .vector_strokes import stroke_outline

        return stroke_outline(
            [(x * w, y * h) for x, y in points], width or max(1, t / 2), False, "round", "round"
        )

    if k in ("rectangle", "rounded-rectangle", "capsule", "button"):
        return rectangle(
            w,
            h,
            p.get("radius", mn / (2 if k == "capsule" else 5) if k != "rectangle" else 0),
            p.get("corner_style", "round"),
        )
    if k == "ellipse":
        return ellipse(0, 0, w, h)
    if k == "line":
        return poly([(0, 0), (w, h)], False)
    if k == "arrow":
        return arrow(p, w, h)
    if k in ("polygon", "star", "burst", "starburst", "seal", "flower", "sparkle"):
        n = int(
            p.get(
                "sides",
                p.get(
                    "count",
                    p.get(
                        "petals",
                        p.get(
                            "arms",
                            4
                            if k == "sparkle"
                            else 5
                            if k == "star"
                            else 12
                            if k in ("burst", "starburst", "seal", "sunburst", "sun")
                            else 6,
                        ),
                    ),
                ),
            )
        )
        inner = p.get(
            "inner_radius",
            0.15
            if k == "sparkle"
            else 0.75
            if k in ("burst", "starburst", "seal", "flower", "sunburst", "sun")
            else 0.5,
        )
        if k == "polygon":
            pts = radial(n, w, h, 1, rot)
        elif k in ("seal", "flower"):
            pts = []
            for i in range(n * 24):
                a = i * math.tau / (n * 24)
                r = inner + (1 - inner) * (0.5 + 0.5 * math.cos(n * a))
                pts.append(
                    (
                        w / 2 + w / 2 * r * math.cos(a + math.radians(rot)),
                        h / 2 + h / 2 * r * math.sin(a + math.radians(rot)),
                    )
                )
        else:
            pts = radial(n * 2, w, h, inner, rot)
        radii = [length(p.get("valley_radius" if i % 2 else "point_radius"), mn, 0) for i in range(len(pts))]
        return rounded_polygon(pts, radii, p.get("corner_style", "round"))
    if k in ("ring", "donut", "frame", "phone-frame", "tablet-frame", "browser-window", "scalloped-border"):
        t = min(t, mn / 2 - 0.001)
        kind = p.get("frame_shape", "ellipse" if k in ("ring", "donut") else "rectangle")
        if kind == "ellipse":
            return ellipse(0, 0, w, h) + " " + ellipse(t, t, w - 2 * t, h - 2 * t, True)
        if kind == "polygon":
            outer = radial(n, w, h, 1, rot)
            inner = [(t + x * (w - 2 * t) / w, t + y * (h - 2 * t) / h) for x, y in outer]
            return poly(outer) + " " + poly(inner[::-1])
        outer = rectangle(w, h, p.get("radius", mn * 0.1 if k != "frame" else 0))
        inset = t * 2 if k == "browser-window" else t
        inner = poly([(t, inset), (t, h - t), (w - t, h - t), (w - t, inset)])
        if k == "scalloped-border":
            outer = path({**p, "shape": "stamp"})
        return outer + " " + inner
    if k in ("squircle", "superellipse"):
        e = p.get("exponent", 4)
        return poly(
            [
                (
                    w / 2 + w / 2 * math.copysign(abs(math.cos(a)) ** (2 / e), math.cos(a)),
                    h / 2 + h / 2 * math.copysign(abs(math.sin(a)) ** (2 / e), math.sin(a)),
                )
                for a in [i * math.tau / 192 for i in range(192)]
            ]
        )
    if k in ("lens", "vesica"):
        depth = length(p.get("depth"), w, w * 0.5)
        return f"M{w / 2:g} 0 C{w / 2 + depth:g} {h / 3:g} {w / 2 + depth:g} {2 * h / 3:g} {w / 2:g} {h:g} C{w / 2 - depth:g} {2 * h / 3:g} {w / 2 - depth:g} {h / 3:g} {w / 2:g} 0 Z"
    if k == "reuleaux":
        n = int(p.get("sides", p.get("count", 3)))
        require(n >= 3 and n % 2 == 1, "Reuleaux polygons require an odd number of sides (at least 3)")
        pts = radial(n, 1, 1, 1, rot)
        out = f"M{pts[0][0] * w:g} {pts[0][1] * h:g}"
        for i in range(n):
            a, b = pts[i], pts[(i + 1) % n]
            cx, cy = pts[(i + (n + 1) // 2) % n]
            r = math.dist(a, (cx, cy))
            out += f" A{r * w:g} {r * h:g} 0 0 1 {b[0] * w:g} {b[1] * h:g}"
        return out + " Z"
    if k == "quarter-circle" and "start_angle" not in p and "end_angle" not in p:
        return f"M0 {h:g} L0 0 A{w:g} {h:g} 0 0 1 {w:g} {h:g} Z"
    if k in ("semicircle", "half-circle") and "start_angle" not in p and "end_angle" not in p:
        return f"M0 {h:g} A{w / 2:g} {h:g} 0 0 1 {w:g} {h:g} Z"
    if k in ("quarter-circle", "semicircle", "half-circle", "ellipse-segment"):
        start, end = p.get("start_angle", 180 if k != "quarter-circle" else 270), p.get("end_angle", 360)
        pts = [
            (
                w / 2 + w / 2 * math.cos(math.radians(start + (end - start) * i / 96)),
                h / 2 + h / 2 * math.sin(math.radians(start + (end - start) * i / 96)),
            )
            for i in range(97)
        ]
        if k == "quarter-circle":
            pts.append((w / 2, h / 2))
        return poly(pts)
    if k in ("kite", "rhombus", "isosceles-triangle"):
        apex = p.get("apex", 0.5)
        if k == "isosceles-triangle":
            return normalized([(apex, 0), (1, 1), (0, 1)])
        skew = 0.5 + 0.45 * math.sin(math.radians(p.get("angle", 0))) if k == "rhombus" else apex
        return normalized([(skew, 0), (1, 0.5), (1 - skew, 1), (0, 0.5)])
    if k in ("star-polygon", "hexagram", "octagram"):
        n = int(p.get("sides", 6 if k == "hexagram" else 8 if k == "octagram" else 7))
        step = int(p.get("step", 2 if k != "octagram" else 3))
        require(1 <= step < n, "star-polygon step must be smaller than sides")
        points = radial(n, w, h, 1, rot)
        return " ".join(
            poly([points[(j + i * step) % n] for i in range(n // math.gcd(n, step))])
            for j in range(math.gcd(n, step))
        )
    if k in ("stairs", "steps"):
        pts = [(0, h), (0, 0)]
        for i in range(n):
            pts += [((i + 1) * w / n, i * h / n), ((i + 1) * w / n, (i + 1) * h / n)]
        return poly(pts)
    if k in ("plus", "cross", "minus", "T-shape", "L-shape", "corner-bracket", "bracket"):
        if k == "minus":
            return poly([(0, (h - t) / 2), (w, (h - t) / 2), (w, (h + t) / 2), (0, (h + t) / 2)])
        if k in ("L-shape", "corner-bracket"):
            return poly([(0, 0), (t, 0), (t, h - t), (w, h - t), (w, h), (0, h)])
        if k == "T-shape":
            return poly(
                [
                    (0, 0),
                    (w, 0),
                    (w, t),
                    ((w + t) / 2, t),
                    ((w + t) / 2, h),
                    ((w - t) / 2, h),
                    ((w - t) / 2, t),
                    (0, t),
                ]
            )
        if k == "bracket":
            return poly([(w, 0), (w, t), (t, t), (t, h - t), (w, h - t), (w, h), (0, h), (0, 0)])
        return poly(
            [
                ((w - t) / 2, 0),
                ((w + t) / 2, 0),
                ((w + t) / 2, (h - t) / 2),
                (w, (h - t) / 2),
                (w, (h + t) / 2),
                ((w + t) / 2, (h + t) / 2),
                ((w + t) / 2, h),
                ((w - t) / 2, h),
                ((w - t) / 2, (h + t) / 2),
                (0, (h + t) / 2),
                (0, (h - t) / 2),
                ((w - t) / 2, (h - t) / 2),
            ]
        )
    if k in ("x", "saltire", "x-mark"):
        return line([(0, 0), (1, 1)], t) + " " + line([(0, 1), (1, 0)], t)
    if k == "cloud":
        depth = length(p.get("depth"), h, h * 0.18)
        return f"M{w * 0.18:g} {h:g} C{-w * 0.05:g} {h:g} {-w * 0.05:g} {h * 0.5:g} {w * 0.17:g} {h * 0.45:g} C{w * 0.08:g} {depth:g} {w * 0.4:g} {-depth:g} {w * 0.54:g} {h * 0.22:g} C{w * 0.8:g} {-depth * 0.3:g} {w * 1.05:g} {h * 0.25:g} {w * 0.89:g} {h * 0.5:g} C{w * 1.1:g} {h * 0.55:g} {w * 1.03:g} {h:g} {w * 0.8:g} {h:g} Z"
    if k == "sunburst":
        n = int(p.get("count", p.get("sides", 12)))
        inner = p.get("inner_radius", 0.2)
        taper = p.get("taper", 0.15)
        parts = []
        for i in range(n):
            a = i * math.tau / n
            points = []
            for angle, radius in (
                (a - math.pi / n * 0.7, inner),
                (a - math.pi / n * taper, 1),
                (a + math.pi / n * taper, 1),
                (a + math.pi / n * 0.7, inner),
            ):
                points.append(
                    (w / 2 + w / 2 * radius * math.cos(angle), h / 2 + h / 2 * radius * math.sin(angle))
                )
            parts.append(poly(points))
        return " ".join(parts)
    if k in ("sun", "asterisk"):
        n = int(p.get("count", p.get("arms", 12 if k == "sun" else 6)))
        inner = length(p.get("ray_length"), mn, mn * 0.16) / mn
        parts = []
        for i in range(n):
            a = i * math.tau / n
            r0 = 0.32 if k == "sun" else 0
            r1 = min(0.5, r0 + inner) if k == "sun" else 0.48
            parts.append(
                line(
                    [
                        (0.5 + r0 * math.cos(a), 0.5 + r0 * math.sin(a)),
                        (0.5 + r1 * math.cos(a), 0.5 + r1 * math.sin(a)),
                    ],
                    max(1, t * 0.55),
                )
            )
        if k == "sun":
            parts.append(ellipse(w * 0.25, h * 0.25, w * 0.5, h * 0.5))
        return " ".join(parts)
    if k in ("trefoil", "quatrefoil", "blob"):
        lobes = 3 if k == "trefoil" else 4 if k == "quatrefoil" else n
        pts = []
        for i in range(lobes * 48):
            a = i * math.tau / (lobes * 48)
            r = 0.76 + 0.24 * math.cos(lobes * a)
            pts.append((w / 2 + w / 2 * r * math.cos(a), h / 2 + h / 2 * r * math.sin(a)))
        return poly(pts)
    if k == "infinity":
        return line(
            [
                (0.5 + 0.46 * math.cos(a), 0.5 + 0.45 * math.sin(2 * a))
                for a in [i * math.tau / 192 for i in range(193)]
            ],
            t,
        )
    if k in ("gear", "cog"):
        n = int(p.get("teeth", n))
        inner = 1 - length(p.get("depth"), mn, mn * 0.15) / (mn / 2)
        pts = []
        for i in range(n * 4):
            a = i * math.tau / (n * 4)
            r = 1 if i % 4 in (1, 2) else inner
            pts.append((w / 2 + w / 2 * r * math.cos(a), h / 2 + h / 2 * r * math.sin(a)))
        hole = length(p.get("hole"), mn, mn * 0.3)
        return poly(pts) + " " + ellipse((w - hole) / 2, (h - hole) / 2, hole, hole, True)
    if k in (
        "wave",
        "zigzag",
        "sawtooth",
        "square-wave",
        "dashed-line",
        "curve",
        "scribble",
        "squiggle",
        "swash-underline",
    ):
        amp = length(p.get("amplitude"), h, h * 0.4)
        wl = length(p.get("wavelength"), w, w / max(n, 1))
        phase = p.get("phase", 0)
        pts = []
        steps = max(32, min(2048, math.ceil(w / max(wl, 1)) * 32))
        for i in range(steps + 1):
            x = i * w / steps
            q = x / max(wl, 1) + phase
            y = math.sin(math.tau * q)
            if k == "zigzag":
                y = 4 * abs(q % 1 - 0.5) - 1
            elif k == "sawtooth":
                y = 2 * (q % 1) - 1
            elif k == "square-wave":
                y = 1 if q % 1 < 0.5 else -1
            pts.append((x, h / 2 + amp * y))
        if k == "dashed-line":
            return " ".join(poly([(i * w / n, h / 2), ((i + 0.55) * w / n, h / 2)], False) for i in range(n))
        if k == "curve":
            pts += [(w, h), (0, h)]
        return poly(pts, k == "curve")
    if k in ("ruler", "tick-strip", "radial-burst", "motion-lines", "speed-lines"):
        if k == "radial-burst":
            return " ".join(
                line(
                    [
                        (0.5 + 0.28 * math.cos(a), 0.5 + 0.28 * math.sin(a)),
                        (0.5 + 0.48 * math.cos(a), 0.5 + 0.48 * math.sin(a)),
                    ],
                    max(1, t / 4),
                )
                for a in [i * math.tau / n for i in range(n)]
            )
        if k in ("motion-lines", "speed-lines"):
            return " ".join(
                line([(0.2 * (i % 3), (i + 0.5) / n), (1, (i + 0.5) / n)], max(1, t / 3)) for i in range(n)
            )
        return (
            line([(0, 1), (1, 1)], max(1, t / 3))
            + " "
            + " ".join(
                line([(i / n, 1), (i / n, 0.2 if i % 5 == 0 else 0.6)], max(1, t / 4)) for i in range(n + 1)
            )
        )
    if k in ("crescent", "moon"):
        d = length(p.get("depth"), w, w * 0.4)
        return f"M{w * 0.7:g} 0 C{-w * 0.3:g} 0 {-w * 0.3:g} {h:g} {w * 0.7:g} {h:g} C{w * 0.7 - d:g} {h * 0.75:g} {w * 0.7 - d:g} {h * 0.25:g} {w * 0.7:g} 0 Z"
    if k in ("teardrop", "flame", "map-pin"):
        if k == "teardrop":
            return f"M{w:g} 0 C{w:g} {h * 0.7:g} {w * 0.8:g} {h:g} {w * 0.4:g} {h:g} C{-w * 0.2:g} {h:g} {-w * 0.2:g} {h * 0.2:g} {w:g} 0 Z"
        if k == "flame":
            return f"M{w * 0.52:g} 0 C{w * 0.8:g} {h * 0.28:g} {w * 0.5:g} {h * 0.45:g} {w * 0.78:g} {h * 0.52:g} Q{w * 0.88:g} {h * 0.38:g} {w * 0.84:g} {h * 0.25:g} C{w * 1.24:g} {h * 0.74:g} {w * 0.87:g} {h:g} {w * 0.5:g} {h:g} C{w * 0.05:g} {h:g} {-w * 0.12:g} {h * 0.7:g} {w * 0.1:g} {h * 0.42:g} Q{w * 0.28:g} {h * 0.2:g} {w * 0.52:g} 0 Z"
        return (
            f"M{w / 2:g} {h:g} C0 {h * 0.6:g} 0 {h * 0.4:g} 0 {h * 0.3:g} C0 {-h * 0.1:g} {w:g} {-h * 0.1:g} {w:g} {h * 0.3:g} C{w:g} {h * 0.5:g} {w:g} {h * 0.6:g} {w / 2:g} {h:g} Z "
            + ellipse(w * 0.3, h * 0.1, w * 0.4, h * 0.35, True)
        )
    if k in ("banner", "ribbon"):
        fold = length(p.get("fold"), w, w * 0.15)
        return poly(
            [
                (0, 0),
                (fold, h * 0.18),
                (w - fold, h * 0.18),
                (w, 0),
                (w - fold / 2, h * 0.5),
                (w, h),
                (w - fold, h * 0.82),
                (fold, h * 0.82),
                (0, h),
                (fold / 2, h * 0.5),
            ]
        )
    if k in ("tag", "ticket", "notched-rectangle", "stamp", "postmark", "sticker", "confetti"):
        if k == "tag":
            hole = length(p.get("hole"), mn, mn * 0.13)
            return (
                normalized([(0.22, 0), (1, 0), (1, 1), (0.22, 1), (0, 0.5)])
                + " "
                + ellipse(w * 0.15 - hole / 2, h / 2 - hole / 2, hole, hole, True)
            )
        if k == "sticker":
            peel = length(p.get("peel"), mn, mn * 0.25)
            return (
                poly([(0, 0), (w, 0), (w, h - peel), (w - peel, h), (0, h)])
                + " "
                + poly([(w - peel, h), (w - peel, h - peel), (w, h - peel)])
            )
        if k in ("stamp", "postmark"):
            pts = []
            depth = length(p.get("depth"), mn, mn * 0.035)
            for side in range(4):
                for i in range(n * 4):
                    q = i / (n * 4)
                    d = depth * (1 - math.cos(math.tau * i / 4)) / 2
                    pts.append([(q * w, d), (w - d, q * h), ((1 - q) * w, h - d), (d, (1 - q) * h)][side])
            return poly(pts)
        if k == "confetti":
            return rectangle(w, h, p.get("radius", mn * 0.15))
        return rectangle(w, h, p.get("notch", mn * 0.15), "inverted" if k == "ticket" else "chamfer")
    if k == "callout":
        s = length(p.get("pointer_size"), mn, mn * 0.2)
        x = w * p.get("pointer_position", 0.3)
        return poly([(0, 0), (w, 0), (w, h - s), (min(w, x + s), h - s), (x, h), (x, h - s), (0, h - s)])
    if k == "brace":
        return line([(1, 0), (0.4, 0.05), (0.4, 0.4), (0, 0.5), (0.4, 0.6), (0.4, 0.95), (1, 1)], t)
    if k == "cylinder":
        d = length(p.get("depth"), h, h * 0.22)
        return (
            f"M0 {d / 2:g} C0 {-d / 6:g} {w:g} {-d / 6:g} {w:g} {d / 2:g} L{w:g} {h - d / 2:g} C{w:g} {h + d / 6:g} 0 {h + d / 6:g} 0 {h - d / 2:g} Z "
            + ellipse(0, 0, w, d)
        )
    if k == "cube":
        depth = p.get("depth", 0.25)
        depth = min(0.45, max(0.05, depth if depth <= 1 else depth / h))
        outer = normalized([(0.5, 0), (1, depth), (1, 1 - depth), (0.5, 1), (0, 1 - depth), (0, depth)])
        seams = (
            line([(0, depth), (0.5, depth * 2), (1, depth)], max(1, mn * 0.02))
            + " "
            + line([(0.5, depth * 2), (0.5, 1)], max(1, mn * 0.02))
        )
        return outer + " " + hole_path(seams)

    if k == "document":
        return f"M0 0 H{w:g} V{h * 0.85:g} C{w * 0.6:g} {h * 0.6:g} {w * 0.4:g} {h * 1.15:g} 0 {h * 0.9:g} Z"
    if k == "folder":
        return normalized([(0, 0.15), (0.35, 0.15), (0.45, 0.3), (1, 0.3), (1, 1), (0, 1)])
    if k == "toggle":
        return rectangle(w, h, min(w, h) / 2) + " " + ellipse(w - h * 0.9, h * 0.1, h * 0.8, h * 0.8, True)
    if k == "checkmark":
        return line([(0, 0.5), (0.35, 1), (1, 0)], t)
    if k in ("lightning", "lightning-bolt"):
        return normalized([(0.55, 0), (0.1, 0.55), (0.45, 0.55), (0.3, 1), (0.95, 0.35), (0.6, 0.35)])
    if k == "house":
        return normalized(
            [
                (0, 0.45),
                (0.5, 0),
                (1, 0.45),
                (0.85, 0.45),
                (0.85, 1),
                (0.6, 1),
                (0.6, 0.65),
                (0.4, 0.65),
                (0.4, 1),
                (0.15, 1),
                (0.15, 0.45),
            ]
        )
    if k == "bell":
        return (
            normalized(
                [
                    (0.45, 0),
                    (0.55, 0),
                    (0.6, 0.1),
                    (0.8, 0.2),
                    (0.85, 0.65),
                    (1, 0.8),
                    (1, 0.9),
                    (0, 0.9),
                    (0, 0.8),
                    (0.15, 0.65),
                    (0.2, 0.2),
                    (0.4, 0.1),
                ]
            )
            + " "
            + ellipse(w * 0.35, h * 0.85, w * 0.3, h * 0.15)
        )
    if k == "lock":
        return (
            normalized(
                [
                    (0, 0.4),
                    (0.2, 0.4),
                    (0.2, 0.1),
                    (0.35, 0),
                    (0.65, 0),
                    (0.8, 0.1),
                    (0.8, 0.4),
                    (1, 0.4),
                    (1, 1),
                    (0, 1),
                ]
            )
            + " "
            + poly([(w * 0.35, h * 0.4), (w * 0.65, h * 0.4), (w * 0.65, h * 0.2), (w * 0.35, h * 0.2)])
        )
    if k == "magnifier":
        return (
            ellipse(0, 0, w * 0.72, h * 0.72)
            + " "
            + ellipse(t, t, w * 0.72 - 2 * t, h * 0.72 - 2 * t, True)
            + " "
            + line([(0.62, 0.62), (1, 1)], t)
        )
    if k == "envelope":
        return rectangle(w, h) + " " + poly([(t, t), (w / 2, h * 0.55), (w - t, t)])
    if k in ("play", "pause", "stop", "skip"):
        if k == "stop":
            return rectangle(w, h, p.get("radius", 0))
        if k == "pause":
            return (
                normalized([(0, 0), (0.35, 0), (0.35, 1), (0, 1)])
                + " "
                + normalized([(0.65, 0), (1, 0), (1, 1), (0.65, 1)])
            )
        out = normalized([(0, 0), (0.85 if k == "skip" else 1, 0.5), (0, 1)])
        return out + (" " + normalized([(0.85, 0), (1, 0), (1, 1), (0.85, 1)]) if k == "skip" else "")
    if k in ("info", "question", "warning"):
        out = normalized([(0.5, 0), (1, 1), (0, 1)]) if k == "warning" else ellipse(0, 0, w, h)
        if k == "question":
            mark = line([(0.3, 0.3), (0.4, 0.18), (0.65, 0.18), (0.73, 0.35), (0.5, 0.52), (0.5, 0.65)], t)
        else:
            mark = poly(
                [(w * 0.44, h * 0.25), (w * 0.44, h * 0.65), (w * 0.56, h * 0.65), (w * 0.56, h * 0.25)]
            )
        # Reverse glyph subpaths to create a contrasting cutout.
        return out + " " + hole_path(mark) + " " + ellipse(w * 0.44, h * 0.76, w * 0.12, h * 0.12, True)
    if k == "music-note":
        return (
            ellipse(0, h * 0.7, w * 0.35, h * 0.3)
            + " "
            + ellipse(w * 0.65, h * 0.55, w * 0.35, h * 0.3)
            + " "
            + normalized(
                [
                    (0.25, 0.85),
                    (0.35, 0.85),
                    (0.35, 0.25),
                    (0.9, 0.1),
                    (0.9, 0.7),
                    (1, 0.7),
                    (1, 0),
                    (0.25, 0.2),
                ]
            )
        )
    if k == "star-rating":
        n = int(p.get("count", 5))
        rating = max(0, min(n, p.get("rating", n)))
        from .booleans import combine_outlines
        from .pathfinder_geometry import _from_commands, path_data, outline_commands
        from .geometry import parse_path

        result = []
        for i in range(n):
            size = min(w / n, h)
            pts = [
                (i * w / n + (w / n - size) / 2 + x * size, (h - size) / 2 + y * size)
                for x, y in radial(10, 1, 1, 0.45, -90)
            ]
            star = poly(pts)
            fraction = max(0, min(1, rating - i))
            if fraction:
                clip = poly(
                    [(i * w / n, 0), ((i + fraction) * w / n, 0), ((i + fraction) * w / n, h), (i * w / n, h)]
                )
                result.append(
                    path_data(
                        outline_commands(
                            combine_outlines(
                                [
                                    _from_commands(parse_path(star), 1, 1),
                                    _from_commands(parse_path(clip), 1, 1),
                                ],
                                lambda a, b: a and b,
                            )
                        )
                    )
                )
        return " ".join(result) or "M0 0 L0 0"
    if k in ("flourish", "scroll", "laurel", "wreath", "divider", "corner-ornament"):
        if k in ("laurel", "wreath"):
            out = []
            for i in range(n * 2):
                a = math.pi * 0.15 + i * math.pi * 1.7 / (n * 2 - 1)
                x, y = 0.5 + 0.38 * math.cos(a), 0.5 + 0.38 * math.sin(a)
                tip = (x + 0.15 * math.cos(a + 0.5), y + 0.15 * math.sin(a + 0.5))
                c1 = (x + 0.15 * math.cos(a - 0.35), y + 0.15 * math.sin(a - 0.35))
                c2 = (x + 0.04 * math.cos(a + 1.2), y + 0.04 * math.sin(a + 1.2))
                out.append(
                    f"M{x * w:g} {y * h:g} Q{c1[0] * w:g} {c1[1] * h:g} {tip[0] * w:g} {tip[1] * h:g} Q{c2[0] * w:g} {c2[1] * h:g} {x * w:g} {y * h:g} Z"
                )
            return " ".join(out)
        if k == "divider":
            from .geometry import parse_path
            from .pathfinder_geometry import path_data

            motif = path({**p, "shape": "sparkle", "width": w * 0.2, "height": h})
            motif = path_data(
                [
                    (c, [v + w * 0.4 if i % 2 == 0 else v for i, v in enumerate(values)])
                    for c, values in parse_path(motif)
                ]
            )
            return line([(0, 0.5), (0.38, 0.5)]) + " " + motif + " " + line([(0.62, 0.5), (1, 0.5)])

        if k == "corner-ornament":
            return line([(0, 1), (0, 0), (1, 0)]) + " " + line([(0, 0.6), (0.25, 0.25), (0.6, 0)])
        if k == "scroll":
            depth = min(0.45, length(p.get("depth"), h, h * 0.3) / h)
            pts = [(i / 96, 0.5 + depth * 0.4 * math.sin(math.pi * i / 96)) for i in range(97)]
            out = line(pts, max(1, t / 3))
            for center, sign in ((0.15, -1), (0.85, 1)):
                spiral = []
                for i in range(97):
                    q = i / 96
                    angle = math.pi / 2 + sign * q * math.tau * 1.3
                    radius = 0.15 * (1 - q)
                    spiral.append(
                        (center + radius * math.cos(angle), 0.5 + depth * radius / 0.15 * math.sin(angle))
                    )
                out += " " + line(spiral, max(1, t / 3))
            return out
        pts = []
        for i in range(193):
            q = i / 192
            a = q * math.tau * p.get("count", 2)
            pts.append((q, 0.5 + 0.4 * math.sin(a) * (1 - q * 0.6)))
        return line(pts, max(1, t / 3))
    from .geometry import SHORTCUTS, parse_path
    from .pathfinder_geometry import path_data

    if k in SHORTCUTS:
        return path_data(
            [
                (command, [value * (w if i % 2 == 0 else h) / 100 for i, value in enumerate(values)])
                for command, values in parse_path(SHORTCUTS[k])
            ]
        )
    if k in ("pentagon", "hexagon", "octagon"):
        return path({**p, "shape": "polygon", "sides": {"pentagon": 5, "hexagon": 6, "octagon": 8}[k]})
    raise ValueError(f"No parametric generator for {k}")


def active(layer):
    return (
        layer.get("shape") in KINDS
        or layer.get("shape") == "arrow"
        or any(key in layer for key in PARAMETERS if key not in ("radius", "sides", "angle", "spacing"))
        or isinstance(layer.get("radius"), (str, list, tuple))
    )


def schema():
    from .schema import N, B, enum

    length_schema = {
        "anyOf": [{"type": "number", "minimum": 0}, {"type": "string", "pattern": r"^\d+(?:\.\d+)?%$"}]
    }
    props = {
        key: {**N, "description": f"Parametric {key.replace('_', ' ')} for the selected shape."}
        for key in PARAMETERS
    }
    for key in (
        "head_length",
        "head_width",
        "shaft_width",
        "thickness",
        "depth",
        "hole",
        "fold",
        "pointer_size",
        "point_radius",
        "valley_radius",
        "amplitude",
        "wavelength",
        "ray_length",
        "notch",
        "peel",
    ):
        props[key] = {
            **length_schema,
            "description": f"{key.replace('_', ' ').capitalize()} in pixels, a fraction up to 1, or a percentage.",
        }
    props.update(
        radius={
            "anyOf": [length_schema, {"type": "array", "items": length_schema, "minItems": 4, "maxItems": 4}],
            "description": "Corner radius in pixels/percent, or top-left, top-right, bottom-right, bottom-left radii.",
        },
        corner_style=enum("round", "chamfer", "inverted"),
        heads=enum("start", "end", "both"),
        head_style=enum("triangle", "open", "concave", "round"),
        frame_shape=enum("rectangle", "ellipse", "polygon"),
        smooth=B,
    )
    for key in ("from", "to", "control"):
        props[key] = {
            "type": "array",
            "items": N,
            "minItems": 2,
            "maxItems": 2,
            "description": "Arrow point in local layer pixels.",
        }
    for key in ("count", "teeth", "petals", "arms", "step"):
        props[key] = {
            "type": "integer",
            "minimum": 1,
            "maximum": 128,
            "description": f"Number of {key} in the selected shape.",
        }
    props["exponent"] = {
        "type": "number",
        "minimum": 0.2,
        "maximum": 32,
        "description": "Superellipse exponent (2 ellipse, 4 squircle).",
    }
    for v in props.values():
        v.setdefault("description", "Shape-specific editable geometry setting.")
    return props


def validate(layer):
    from .model import finite

    for key in PARAMETERS:
        if key in layer and isinstance(layer[key], (int, float)):
            finite(layer[key], key, -1e6, 1e6)
    radius = layer.get("radius", 0)
    rs = radius if isinstance(radius, list) else [radius]
    require(len(rs) in (1, 4), "radius must be a number, percentage or four corner radii")
    for r in rs:
        require(
            math.isfinite(length(r, min(layer["width"], layer["height"])))
            and length(r, min(layer["width"], layer["height"])) >= 0,
            "Invalid corner radius",
        )
    require(layer.get("corner_style", "round") in ("round", "chamfer", "inverted"), "Invalid corner style")
    require(0.2 <= layer.get("exponent", 4) <= 32, "exponent must be 0.2–32")
    if layer.get("shape") == "reuleaux":
        count = layer.get("sides", layer.get("count", 3))
        require(
            count >= 3 and count % 2 == 1, "Reuleaux polygons require an odd number of sides (at least 3)"
        )
    for key in ("count", "teeth", "petals", "arms", "sides"):
        require(1 <= layer.get(key, 6) <= 128, f"{key} must be 1–128")


def hole_path(path):
    from .geometry import path_polygons
    from .vector_strokes import area

    return " ".join(poly(points[::-1] if area(points) > 0 else points) for points in path_polygons(path))
