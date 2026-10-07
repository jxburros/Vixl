"""Principled layout scaffolds that adapt to any canvas and vary by seed.

Templates that always produce the same picture make every adopter look alike. A layout here
is a *composition system*: it encodes a design principle (one focal point, a modular grid,
rule of thirds, golden section, Z-pattern reading order, asymmetric balance …), then reads the
canvas (aspect, safe area, bleed, dpi) and a seed to choose among sound variations: palette
roles with checked contrast, a modular type scale, margins on a spacing unit, alignment, focal
placement and an accent device. The output is ordinary editable layers, swatches, a type scale
and grid guides, so an agent can keep refining instead of starting from a fixed picture.
"""

from copy import deepcopy
import math
import random
import re
import secrets

from PIL import Image, ImageDraw

from .craft import LINE_HEIGHT, base_size
from .errors import VixlError, require
from .safe_catalog import SAFE_PALETTES
from .sizes import safe_sides

LAYOUT_TYPES = ("layout-apply", "type-scale")
RATIOS = {
    "minor-third": 1.2,
    "major-third": 1.25,
    "perfect-fourth": 1.333,
    "augmented-fourth": 1.414,
    "perfect-fifth": 1.5,
    "golden": 1.618,
}
ROLE_STEPS = {"caption": -1, "body": 0, "lead": 1, "subhead": 2, "title": 3, "headline": 4, "display": 5}
# The line-height stage (craft.LINE_HEIGHT) each type-scale role sets in.
ROLE_STAGES = {"caption": "caption", "body": "body", "lead": "lead", "subhead": "lead", "title": "heading",
               "headline": "heading", "display": "display"}
CONTENT_KEYS = ("title", "subtitle", "body", "label", "cta", "caption", "image", "images", "items")
IMAGE_KEYS = ("image", "images")
DENSITY_MARGIN = {"airy": 0.095, "balanced": 0.072, "dense": 0.05}
# Rolls and the builder pick density from this one weighted pool: balanced twice as often.
DENSITY_CHOICES = ("airy", "balanced", "balanced", "dense")
# How density scales a rolled margin and the spacing unit (gaps), relative to balanced.
DENSITY_SPACING = {"airy": 1.25, "balanced": 1.0, "dense": 0.75}
ACCENTS = ("rule", "bar", "dot", "block", "outline", "none")
# A stored design direction: these keys are layout-apply fields; the rest (except the skipped ones) are
# its ``direction`` (margin, corner, look, style, motif, background treatment ...).
DIRECTION_OPTIONS = ("palette", "mode", "type_scale", "density", "accent")
DIRECTION_SKIP = ("layout", "layout_seed", "pairing", *DIRECTION_OPTIONS)
PALETTE_POOL = tuple(SAFE_PALETTES)


class Builder:
    """Collects operations for one layout and carries the chosen system (grid, type, color)."""

    def __init__(self, project, layout, op, seed, fit=1.0):
        from .colors import contrast_ratio, parse

        self.project, self.layout, self.op, self.seed = project, layout, op, seed
        self.rng = random.Random(seed)
        c = project.state["canvas"]
        self.W, self.H = c["width"], c["height"]
        short = min(self.W, self.H)
        aspect = self.W / self.H
        self.orientation = (
            "wide" if aspect >= 2.2 else "tall" if aspect <= 0.45 else "landscape" if aspect > 1.15 else "portrait" if aspect < 0.87 else "square"
        )
        self.dpi = c.get("dpi")
        self.ops = []
        self.created = []
        self.prefix = op.get("prefix", "")
        density = op.get("density") or self.rng.choice(DENSITY_CHOICES)
        require(density in DENSITY_MARGIN, "density must be airy, balanced or dense")
        self.density = density
        inset = c.get("bleed", 0) + max(safe_sides(c))
        # The canvas safe area as (left, top, right, bottom) insets from the canvas edge.
        self.safe = tuple(c.get("bleed", 0) + side for side in safe_sides(c))
        margin = max(short * DENSITY_MARGIN[density], inset + short * 0.02 if inset else 0)
        if "margin" in op.get("direction", {}):
            fraction = op["direction"]["margin"]
            require(isinstance(fraction, (int, float)) and 0.02 <= fraction <= 0.2, "direction.margin must be 0.02–0.2")
            # A rolled margin is the balanced value; density still widens or tightens it.
            margin = max(inset, short * fraction * DENSITY_SPACING[density])
        if self.orientation == "wide":
            margin = max(short * 0.12, inset)
        self.m = round(margin)
        self.L, self.T, self.R, self.B = self.m, self.m, self.W - self.m, self.H - self.m
        self.cw, self.ch = self.R - self.L, self.B - self.T
        # Type: a modular scale from a body size suited to the medium.
        ratio = op.get("type_scale")
        if ratio is None:
            options = ["major-third", "perfect-fourth", "perfect-fifth"] if density != "dense" else ["minor-third", "major-third"]
            if layout.get("dramatic"):
                options = ["perfect-fourth", "perfect-fifth", "golden"]
            ratio = self.rng.choice(options)
        self.ratio_name = ratio if isinstance(ratio, str) else f"{ratio:g}"
        self.ratio = RATIOS.get(ratio, ratio) if isinstance(ratio, str) else ratio
        require(isinstance(self.ratio, (int, float)) and 1.05 <= self.ratio <= 2, "type_scale must be a ratio name or 1.05–2")
        base = op.get("base_size", base_size(c) * fit)
        if layout.get("safe") and layout.get("safe_composition"):
            base = op.get("base_size", max(short * 0.04, 14) * fit)
        require(isinstance(base, (int, float)) and 4 <= base <= 1000, "base_size must be 4–1000 pixels")
        self.base = base
        self.sizes = {role: max(6, round(base * self.ratio**step)) for role, step in ROLE_STEPS.items()}
        if layout.get("safe_composition"):
            thumbnail = 600 if self.W / self.H > 1.6 else 320
            minimum = math.ceil(self.W / thumbnail * 10)
            self.sizes = {role: max(minimum, value) for role, value in self.sizes.items()}
        self.unit = max(2, round(base / 2 * DENSITY_SPACING[density]))
        # Color roles with contrast guarantees.
        self.colors = assign_roles(op, self.rng)
        self.contrast = round(contrast_ratio(parse(self.colors["ink"])[:3], parse(self.colors["background"])[:3]), 2)
        self.align = op.get("align") or self.rng.choice(layout.get("aligns", ["left"]))
        require(self.align in ("left", "center", "right"), "align must be left, center or right")
        self.accent = op.get("accent") or self.rng.choice(layout.get("accents", ACCENTS))
        require(self.accent in ACCENTS, f"accent must be one of {', '.join(ACCENTS)}")
        # Content is fill-in-the-blank: only what the caller supplied is real copy. A slot the
        # design needs but nobody filled renders as a visible "[Label]" placeholder and is
        # recorded as a blank, so it can never ship silently as invented sample text.
        self.content = {k: op[k] for k in CONTENT_KEYS if k in op}
        self.slots = slot_spec(layout)
        self.unfilled = op.get("unfilled", "blank")
        require(self.unfilled in ("blank", "omit"), "unfilled must be blank or omit", field="unfilled")
        self.omitted = []
        self.read = set()
        self.placeholders = {}
        self.image_blanks = []
        self.blank_slots = {}
        typography = project.state.get("typography") or {}
        self.font = op.get("font") or typography.get("body")
        self.display_font = op.get("display_font") or typography.get("heading") or self.font
        from .render import resolve_font
        if self.font and self.font not in project.state.get("fonts", {}):
            self.font = resolve_font(project, self.font)[0]
        if self.display_font and self.display_font not in project.state.get("fonts", {}):
            self.display_font = resolve_font(project, self.display_font)[0]

    def name(self, base):
        return f"{self.prefix}{base}"

    def get(self, key, default=""):
        self.read.add(key)
        if key in self.content:
            value = self.content[key]
            return value if value is not None else default
        slot = self.slots.get(key)
        if key not in IMAGE_KEYS and slot and slot["blank"]:
            if self.unfilled == "blank":
                self.placeholders[key] = slot["placeholder"]
                return slot["placeholder"]
            if key not in self.omitted:
                self.omitted.append(key)
        return default

    def add(self, op):
        self.ops.append(op)
        return op

    def measure(self, text, size, width=None, spacing=0, align="left", font=None):
        from .render import text_metrics
        from .text import UnsupportedText, font_data, measure

        layer = {"text": text, "size": size, "spacing": spacing, "align": align, "font": self.project.state.get("fonts", {}).get(font, font or "DejaVuSans.ttf")}
        try:
            _, box = measure(font_data(self.project, layer), text, size, spacing, align, width)
            return math.ceil(box[2] - box[0]), math.ceil(box[3] - box[1])
        except UnsupportedText:
            w, h, _ = text_metrics(self.project, layer, {})
            return w, h

    def text(self, role, content, x, y, width, *, align=None, name=None, color="@ink", max_height=None, display=False, line=None, stroke=None):
        """Place wrapped text in a box at (x, y); shrinks to fit width and ``max_height``."""
        if not content:
            return (x, y, 0, 0)
        align = align or self.align
        size = self.sizes[role] if isinstance(role, str) else int(role)
        width = max(1, int(width))
        heavy = (role in ("display", "headline", "title")) if isinstance(role, str) else display
        font = self.display_font if heavy else self.font
        # ``line`` is a line-height multiple; by default the craft table's value for the role's stage.
        multiple = line if line is not None else LINE_HEIGHT[ROLE_STAGES.get(role, "heading" if heavy else "body")
                                                             if isinstance(role, str) else "heading" if heavy else "body"]

        def spacing_for(s):
            return self.leading(s, multiple, font)

        if heavy and isinstance(role, str):
            # Keep a readable measure: a heavy line should hold ~10–14 characters, never one word.
            chars = min(10 if role == "display" else 14, len(content))
            size = min(size, max(6, int(width / (chars * 0.56))))
        if heavy and max_height is None:
            max_height = self.ch * 0.55

        w, h = self.measure(content, size, width, spacing_for(size), align, font)
        while size > 6 and (w > width or (max_height and h > max_height)):
            size = max(6, int(size * 0.92))
            w, h = self.measure(content, size, width, spacing_for(size), align, font)
        layer = self.name(name or role)
        op = {"type": "text", "name": layer, "text": content, "size": size, "color": color, "align": align, "line_height": multiple, "x": round(x), "y": round(y)}
        if font:
            op["font"] = font
        self.add(op)
        if stroke:
            # text-set re-measures the text, so the stroke comes before the text box.
            self.add({"type": "text-set", "target": layer, "stroke_width": stroke[0], "stroke_color": stroke[1]})
            h += 2 * stroke[0]
        self.add({"type": "text-layout", "target": layer, "width": width, "height": max(1, h)})
        self.created.append(layer)
        return (round(x), round(y), width, h)

    def leading(self, size, multiple, font=None):
        """Pixel spacing that puts baselines ``multiple`` × ``size`` apart in ``font`` (see craft.spacing_for)."""
        from .craft import spacing_for

        return spacing_for(self.project, self.project.state.get("fonts", {}).get(font, font or "DejaVuSans.ttf"),
                           size, multiple)

    def measure_box(self, size, content, width, max_height, multiple=None):
        """The size text() settles on for heavy ``content`` in a ``width`` × ``max_height`` box, and its extent."""
        multiple = LINE_HEIGHT["heading"] if multiple is None else multiple
        spacing = self.leading(size, multiple, self.display_font)
        w, h = self.measure(content, size, width, spacing, "left", self.display_font)
        while size > 6 and (w > width or h > max_height):
            size = max(6, int(size * 0.92))
            spacing = self.leading(size, multiple, self.display_font)
            w, h = self.measure(content, size, width, spacing, "left", self.display_font)
        return size, spacing, w, h

    def glyphs(self, size, content, cx, cy, name, color="@on-accent"):
        """Short centered text (initials, a glyph) as an unwrapped, auto-sized layer."""
        w, h = self.measure(content, size, None, 0, "left", self.display_font)
        layer = self.name(name)
        self.add({"type": "text", "name": layer, "text": content, "size": int(size), "color": color, "spacing": 0, "x": round(cx - w / 2), "y": round(cy - h / 2), **({"font": self.display_font} if self.display_font else {})})
        self.created.append(layer)
        return (round(cx - w / 2), round(cy - h / 2), w, h)

    def rect(self, name, x, y, w, h, fill="@accent", radius=0, opacity=None, stroke=None, stroke_width=None, shape=None):
        layer = self.name(name)
        op = {
            "type": "shape",
            "name": layer,
            "shape": shape or ("rounded-rectangle" if radius else "rectangle"),
            "x": round(x),
            "y": round(y),
            "width": max(1, round(w)),
            "height": max(1, round(h)),
            "fill": fill,
        }
        if radius:
            op["radius"] = round(radius)
        if stroke:
            op.update(stroke=stroke, stroke_width=stroke_width or max(1, round(self.unit / 3)))
        self.add(op)
        if opacity is not None:
            self.add({"type": "opacity", "target": layer, "value": opacity})
        self.created.append(layer)
        return (round(x), round(y), max(1, round(w)), max(1, round(h)))

    def ellipse(self, name, x, y, w, h, fill="@accent", **kw):
        return self.rect(name, x, y, w, h, fill, shape="ellipse", **kw)

    def rotate(self, name, degrees):
        self.add({"type": "rotate", "target": self.name(name), "value": degrees})

    def background(self, fill="@background"):
        if self.op.get("transparent"):
            return
        self.add({"type": "solid", "name": self.name("background"), "color": fill, "width": self.W, "height": self.H, "x": 0, "y": 0})
        self.created.append(self.name("background"))

    def image(self, name, x, y, w, h, asset=None, slot="image", bleed=False):
        """A frame holding the supplied image asset, or an editable placeholder to replace. ``slot`` images
        takes ``asset`` (one entry of the images list) instead of reading the image slot. ``bleed`` marks a
        full-bleed picture as an intentional crop, so it may run past the safe area."""
        from .assets import add_image
        from .render import color as rgba
        from .design import resolve_color

        w, h = max(1, round(w)), max(1, round(h))
        if slot == "image":
            asset = self.get("image", None)
        layer = self.name(name)
        if asset:
            self.project.image(asset)
        else:
            self.image_blanks.append(layer)
            self.blank_slots[layer] = slot
            scale = min(1, 800 / max(w, h))
            pw, ph = max(2, round(w * scale)), max(2, round(h * scale))
            top = rgba(resolve_color(self.colors["surface"], self.project.state))
            bottom = rgba(resolve_color(self.colors["muted"], self.project.state))
            image = Image.new("RGBA", (pw, ph))
            draw = ImageDraw.Draw(image)
            for row in range(ph):
                t = row / max(ph - 1, 1)
                draw.line([(0, row), (pw, row)], fill=tuple(round(a + (b - a) * t * 0.55) for a, b in zip(top, bottom)))
            ink = rgba(resolve_color(self.colors["ink"], self.project.state))[:3] + (46,)
            s = min(pw, ph)
            cx, cy = pw / 2, ph / 2
            draw.ellipse((cx + s * 0.08, cy - s * 0.28, cx + s * 0.24, cy - s * 0.12), fill=ink)
            draw.polygon([(cx - s * 0.36, cy + s * 0.22), (cx - s * 0.1, cy - s * 0.12), (cx + s * 0.06, cy + s * 0.08), (cx + s * 0.16, cy - s * 0.02), (cx + s * 0.36, cy + s * 0.22)], fill=ink)
            asset = add_image(self.project, image)
        self.add({"type": "frame", "name": layer, "asset": asset, "x": round(x), "y": round(y), "width": w, "height": h, "fit": "fill"})
        if bleed:
            self.add({"type": "layer-intent", "target": layer, "allow_crop": True})
        self.created.append(layer)
        return (round(x), round(y), w, h)

    def button(self, label, x, y, align=None, name="cta", fill="@accent", ink="@on-accent"):
        if not label:
            return (x, y, 0, 0)
        align = align or self.align
        size = self.sizes["body"]
        tw, th = self.measure(label, size, None, 0, "left", self.font)
        pad_x, pad_y = round(size * 1.1), round(size * 0.6)
        w, h = tw + 2 * pad_x, th + 2 * pad_y
        if align == "center":
            x = x - w / 2
        elif align == "right":
            x = x - w
        style = self.layout.get("button") or self.rng.choice(["pill", "rounded", "square"])
        radius = h / 2 if style == "pill" else round(size * 0.35) if style == "rounded" else 0
        self.rect(name + "-button", x, y, w, h, fill, radius=radius)
        self.add({"type": "text", "name": self.name(name), "text": label, "size": size, "color": ink, "x": round(x + pad_x), "y": round(y + pad_y), **({"font": self.font} if self.font else {})})
        self.created.append(self.name(name))
        return (round(x), round(y), round(w), round(h))

    def accent_device(self, x, y, width, height, near="top"):
        """The seeded secondary device that ties a block together (or nothing)."""
        size = max(2, round(self.unit * 0.75))
        if self.accent == "rule":
            length = max(size * 8, round(width * 0.18))
            ax = x if self.align == "left" else x + width - length if self.align == "right" else x + (width - length) / 2
            ay = y - size * 4 if near == "top" else y + height + size * 3
            return self.rect("accent", ax, ay, length, size, "@accent")
        if self.accent == "bar":
            bx = x - size * 5 if self.align != "right" else x + width + size * 4
            return self.rect("accent", bx, y, size * 1.5, max(height, size * 6), "@accent")
        if self.accent == "dot":
            d = size * 4
            ax = x if self.align == "left" else x + width - d if self.align == "right" else x + (width - d) / 2
            return self.ellipse("accent", ax, y - d * 2, d, d, "@accent")
        if self.accent == "block":
            bw, bh = self.W * 0.22, self.H * 0.22
            corner = self.rng.choice(["tl", "tr", "bl", "br"])
            bx = -bw * 0.3 if corner in ("tl", "bl") else self.W - bw * 0.7
            by = -bh * 0.3 if corner in ("tl", "tr") else self.H - bh * 0.7
            return self.rect("accent", bx, by, bw, bh, "@accent", opacity=0.9)
        if self.accent == "outline":
            inset = self.m * 0.45
            return self.rect("accent", inset, inset, self.W - 2 * inset, self.H - 2 * inset, "transparent", stroke="@accent", stroke_width=size)
        return None

    def stack(self, entries, x, y, width, gap=None, align=None):
        """Lay out (role, key|text, name) entries top-down with rhythm gaps; returns bottom y."""
        gap = gap if gap is not None else self.unit * 3
        for role, text, name in entries:
            if not text:
                continue
            if role == "button":
                anchor = x if (align or self.align) == "left" else x + width if (align or self.align) == "right" else x + width / 2
                _, _, _, h = self.button(text, anchor, y, align=align)
            else:
                color = "@accent-text" if name == "label" else "@muted" if role == "caption" else "@ink"
                limit = max(self.unit * 4, (self.B - y) * 0.75) if role in ("display", "headline", "title") else None
                _, _, _, h = self.text(role, text, x, y, width, align=align, name=name, color=color, max_height=limit)
            y += h + gap
        return y - gap

    def stack_height(self, entries, width, gap=None):
        gap = gap if gap is not None else self.unit * 3
        total = 0
        for role, text, _ in entries:
            if not text:
                continue
            if role == "button":
                _, th = self.measure(text, self.sizes["body"], None, 0)
                total += th + 2 * round(self.sizes["body"] * 0.6) + gap
            else:
                size = self.sizes[role]
                heavy = role in ("display", "headline", "title")
                if heavy:
                    chars = min(10 if role == "display" else 14, len(text))
                    size = min(size, max(6, int(width / (chars * 0.56))))
                _, h = self.measure(text, size, width, self.leading(size, LINE_HEIGHT[ROLE_STAGES[role]],
                                                                    self.display_font if heavy else self.font),
                                    self.align, self.display_font if heavy else self.font)
                if heavy:
                    h = min(h, self.ch * 0.55)
                total += h + gap
        return max(0, total - gap)

    def label_text(self):
        label = self.get("label")
        return label.upper() if label and self.op.get("uppercase_labels", True) else label


ROLES = ("background", "surface", "ink", "muted", "accent", "accent-text", "on-accent")


def assign_roles(op, rng):
    """Background/surface/ink/muted/accent/on-accent from a palette with checked contrast.

    By default roles follow light or dark mode (lightest color behind the work in light mode,
    darkest in dark mode). ``keep_order`` takes the palette as given instead: background, surface,
    then accents. The result carries ``_explain``: each role's color, source and reason."""
    from .colors import contrast_ratio, hex_of, mix, parse, relative_luminance, srgb_to_oklab, to_polar
    from .palette_roles import describe, explicit, notes
    from .resources import get

    palette = op.get("palette")
    if palette is None:
        palette = rng.choice(PALETTE_POOL)
    colors = get("palettes", palette) if isinstance(palette, str) else palette
    require(isinstance(colors, list) and 2 <= len(colors) <= 256, "palette must be a palette name or 2–256 colors")
    parsed = [parse(c) for c in colors]
    keep_order = bool(op.get("keep_order"))
    by_light = sorted(parsed, key=lambda c: relative_luminance(c[:3]))
    mode_source = op.get("_mode_source") or ("mode argument" if op.get("mode") else "rolled from the seed")
    if keep_order and (not op.get("mode") or op.get("_mode_source") == "inherited from the canvas background"):
        mode = "dark" if relative_luminance(parsed[0][:3]) < 0.4 else "light"
        mode_source = "taken from the first palette color"
    else:
        mode = op.get("mode") or rng.choice(["light", "light", "dark"])
    require(mode in ("light", "dark"), "mode must be light or dark")
    background = parsed[0] if keep_order else by_light[-1] if mode == "light" else by_light[0]
    ink = by_light[0] if mode == "light" else by_light[-1]
    label = palette if isinstance(palette, str) else "custom"
    chosen = explicit(colors, op["role_map"]) if op.get("role_map") else {}
    if op.get("policy") == "strict" and not keep_order:
        candidates = [c for c in parsed if c not in (background, ink)] or [ink]
        accent = max(candidates, key=lambda c: to_polar(srgb_to_oklab(c[:3]))[1])
        def contrast(c):
            return contrast_ratio(c[:3], background[:3])
        readable = [c for c in parsed if contrast(c) >= 4.5] or [ink]
        roles = {"background": background, "surface": background, "ink": ink,
                 "muted": min(readable, key=contrast), "accent": accent,
                 "accent-text": accent if contrast(accent) >= 4.5 else ink,
                 "on-accent": max(parsed, key=lambda c: contrast_ratio(c[:3], accent[:3]))}
        result = {k: hex_of(v) for k, v in roles.items()}
        result.update(chosen)
        return {**result, "_palette": label, "_mode": mode, "_mode_source": mode_source,
                "_explain": describe(colors, result, mode=mode, mode_source=mode_source, policy="strict",
                                     explicit_roles=chosen),
                "_notes": notes(keep_order=False, mode=mode, mode_source=mode_source, explicit_roles=chosen)}
    white, black = (1.0, 1.0, 1.0, 1.0), (0.0, 0.0, 0.0, 1.0)
    extreme = black if mode == "light" else white
    if keep_order:
        # Honour the order given: nothing is lightened or darkened to suit the mode. Ink is not in the
        # order, so it is derived from the background hue.
        ink = mix(background, extreme, 0.9)
    else:
        if mode == "light" and relative_luminance(background[:3]) < 0.6:
            background = mix(background, white, 0.82)
        if mode == "dark" and relative_luminance(background[:3]) > 0.08:
            background = mix(background, black, 0.75)
    for step in range(12):
        if contrast_ratio(ink[:3], background[:3]) >= 7.1:
            break
        ink = mix(ink, extreme, 0.25)

    def chroma(c):
        return to_polar(srgb_to_oklab(c[:3]))[1]

    if keep_order:
        accent = parsed[2] if len(parsed) > 2 else parsed[1]
        surface = parsed[1] if len(parsed) > 2 else mix(background, ink, 0.07 if mode == "light" else 0.12)
    else:
        candidates = [c for c in parsed if c not in (background, ink)] or [ink]
        accent = max(candidates, key=lambda c: chroma(c) + rng.random() * 0.02)
        for step in range(12):
            if contrast_ratio(accent[:3], background[:3]) >= 3:
                break
            accent = mix(accent, extreme, 0.18)
        surface = mix(background, ink, 0.07 if mode == "light" else 0.12)

    def readable(c, target=4.6):  # margin for hex rounding
        return min(contrast_ratio(c[:3], background[:3]), contrast_ratio(c[:3], surface[:3])) >= target

    # Secondary and small accent text must read on the background and on surface panels (4.5:1);
    # fills and large type need only 3:1.
    muted = mix(ink, background, 0.38)
    for step in range(12):
        if readable(muted):
            break
        muted = mix(muted, ink, 0.3)
    accent_text = accent
    for step in range(16):
        if readable(accent_text):
            break
        accent_text = mix(accent_text, extreme, 0.15)
    on_accent = max((background, ink, white, black), key=lambda c: contrast_ratio(c[:3], accent[:3]))
    roles = {
        "background": hex_of(background[:3] + (1.0,)),
        "surface": hex_of(surface[:3] + (1.0,)),
        "ink": hex_of(ink[:3] + (1.0,)),
        "muted": hex_of(muted[:3] + (1.0,)),
        "accent": hex_of(accent[:3] + (1.0,)),
        "accent-text": hex_of(accent_text[:3] + (1.0,)),
        "on-accent": hex_of(on_accent[:3] + (1.0,)),
    }
    for key, value in (op.get("colors") or {}).items():
        require(key in roles, f"colors keys are {', '.join(roles)}")
        parse(value)
        roles[key] = value
    roles.update(chosen)
    given = {**{k: v for k, v in (op.get("colors") or {}).items()}, **chosen}
    roles["_palette"] = label
    roles["_mode"] = mode
    roles["_mode_source"] = mode_source
    roles["_explain"] = describe(colors, roles, mode=mode, mode_source=mode_source, keep_order=keep_order,
                                 explicit_roles=given)
    roles["_notes"] = notes(keep_order=keep_order, mode=mode, mode_source=mode_source, explicit_roles=given)
    return roles


# Each layout receives a Builder; geometry is derived from the canvas, never fixed pixels.


def _hero_statement(b):
    b.background()
    width = b.cw if b.orientation in ("portrait", "tall") else b.cw * b.rng.choice([0.72, 0.8, 0.9])
    x = b.L if b.align == "left" else b.R - width if b.align == "right" else b.L + (b.cw - width) / 2
    entries = [("caption", b.label_text(), "label"), ("display", b.get("title"), "headline"), ("lead", b.get("subtitle"), "subtitle"), ("button", b.get("cta"), "cta")]
    height = b.stack_height(entries, width)
    anchor = b.rng.choice(["upper", "lower", "center"])
    y = b.T + b.ch * 0.08 if anchor == "upper" else b.B - height - b.ch * 0.06 if anchor == "lower" else b.T + (b.ch - height) * 0.42
    y = min(max(b.T, y), max(b.T, b.B - height))
    b.accent_device(x, y, width, height)
    b.stack(entries, x, y, width)
    if b.get("caption"):
        b.text("caption", b.get("caption"), b.L, b.B - b.sizes["caption"] * 1.4, b.cw, name="caption", color="@muted", align="left" if b.align != "left" else "right")


def _editorial_grid(b):
    b.background()
    columns = 12 if b.orientation in ("landscape", "wide", "square") else 6
    gutter = b.unit * 2
    while columns > 1 and (b.cw - (columns - 1) * gutter) / columns < max(4, b.unit):
        columns //= 2  # Small canvases get fewer, wider columns instead of zero-width ones.
    if (b.cw - (columns - 1) * gutter) / columns <= 0:
        gutter = 0
    b.add({"type": "grid", "name": b.name("layout"), "columns": columns, "rows": 1, "margin": b.m, "gutter": gutter})
    col = (b.cw - (columns - 1) * gutter) / columns

    def span(start, count):
        return b.L + start * (col + gutter), count * col + (count - 1) * gutter

    y = b.T
    _, _, _, h = b.text("caption", b.label_text(), b.L, y, b.cw, name="label", color="@accent-text", align="left")
    y += h + b.unit * 2
    b.rect("rule", b.L, y, b.cw, max(1, round(b.unit / 3)), "@ink")
    y += b.unit * 3
    wide = b.orientation in ("landscape", "wide", "square")
    hx, hw = span(0, 8 if wide else columns)
    _, _, _, h = b.text("headline", b.get("title"), hx, y, hw, name="headline", align="left", max_height=b.ch * 0.36)
    y += h + b.unit * 3
    if wide:
        tx, tw = span(0, 5)
        ix, iw = span(6, 6)
        body_top = y
        _, _, _, h = b.text("lead", b.get("subtitle"), tx, y, tw, name="subtitle", align="left", color="@ink")
        y += h + b.unit * 2
        b.text("body", b.get("body"), tx, y, tw, name="body", align="left", max_height=b.B - y)
        image_h = max(b.unit * 8, b.B - body_top - b.sizes["caption"] * 2.2)
        b.image("image", ix, body_top, iw, image_h)
        b.text("caption", b.get("caption"), ix, body_top + image_h + b.unit, iw, name="caption", color="@muted", align="left")
    else:
        ix, iw = span(0, columns)
        image_h = (b.B - y) * 0.42
        b.image("image", ix, y, iw, image_h)
        y += image_h + b.unit
        _, _, _, h = b.text("caption", b.get("caption"), ix, y, iw, name="caption", color="@muted", align="left")
        y += h + b.unit * 3
        _, _, _, h = b.text("lead", b.get("subtitle"), b.L, y, b.cw, name="subtitle", align="left")
        y += h + b.unit * 2
        b.text("body", b.get("body"), b.L, y, b.cw, name="body", align="left", max_height=b.B - y)


def _split_screen(b):
    b.background()
    fraction = b.rng.choice([0.5, 0.5, 0.618, 0.382])
    horizontal = b.orientation in ("landscape", "wide", "square")
    first = b.rng.random() < 0.5
    if horizontal:
        split = round(b.W * fraction)
        image_box = (0, 0, split, b.H) if first else (b.W - split, 0, split, b.H)
        text_box = (split, 0, b.W - split, b.H) if first else (0, 0, b.W - split, b.H)
    else:
        split = round(b.H * fraction)
        image_box = (0, 0, b.W, split) if first else (0, b.H - split, b.W, split)
        text_box = (0, split, b.W, b.H - split) if first else (0, 0, b.W, b.H - split)
    b.image("image", *image_box)
    if b.rng.random() < 0.35:
        b.rect("panel", *text_box, "@surface")
    pad = b.m
    tx, ty, tw, th = text_box[0] + pad, text_box[1] + pad, text_box[2] - 2 * pad, text_box[3] - 2 * pad
    entries = [("caption", b.label_text(), "label"), ("headline", b.get("title"), "headline"), ("body", b.get("subtitle") or b.get("body"), "body"), ("button", b.get("cta"), "cta")]
    height = b.stack_height(entries, tw)
    y = ty + max(0, (th - height) / 2)
    b.accent_device(tx, y, tw, height)
    b.stack(entries, tx, y, tw)


def _centered_axis(b):
    b.background()
    width = b.cw * (0.86 if b.orientation in ("portrait", "tall") else 0.7)
    x = b.L + (b.cw - width) / 2
    entries = [("caption", b.label_text(), "label"), ("headline", b.get("title"), "headline"), ("lead", b.get("subtitle"), "subtitle")]
    height = b.stack_height(entries, width) + b.unit * 8
    cta = b.get("cta")
    if cta:
        height += b.sizes["body"] * 2.4 + b.unit * 3
    y = b.T + max(0, (b.ch - height) * 0.44)  # Optical center sits slightly above the middle.
    bottom = b.stack(entries[:2], x, y, width, align="center")
    divider = max(b.unit * 6, round(width * 0.12))
    ornament = b.rng.choice(["rule", "dot", "diamond"])
    oy = bottom + b.unit * 3
    if ornament == "rule":
        b.rect("divider", b.W / 2 - divider / 2, oy, divider, max(2, round(b.unit / 2)), "@accent")
    else:
        d = b.unit * 1.6
        b.rect("divider", b.W / 2 - d / 2, oy - d / 2, d, d, "@accent", shape="ellipse" if ornament == "dot" else "diamond")
    y = oy + b.unit * 4
    y = b.stack(entries[2:], x, y, width, align="center") + b.unit * 4
    if cta:
        b.button(cta, b.W / 2, y, align="center")


def _asymmetric_balance(b):
    b.background()
    left = b.rng.random() < 0.5
    d = min(b.W, b.H) * b.rng.choice([0.55, 0.65, 0.8])
    cx = b.W * (0.78 if left else 0.22)
    cy = b.H * b.rng.choice([0.22, 0.3])
    shape = b.rng.choice(["ellipse", "rectangle", "ellipse"])
    b.rect("counterweight", cx - d / 2, cy - d / 2, d, d, "@accent", shape=shape, opacity=0.92)
    gap = b.unit * 4
    beside = (b.R - (cx + d / 2 + gap)) if not left else ((cx - d / 2 - gap) - b.L)
    below = b.B - (cy + d / 2 + gap)
    width = b.cw * (0.62 if b.orientation != "tall" else 0.9)
    entries_probe = [("caption", b.label_text(), "label"), ("headline", b.get("title"), "headline"), ("body", b.get("subtitle"), "subtitle"), ("button", b.get("cta"), "cta")]
    if b.stack_height(entries_probe, width) > below:
        width = max(b.cw * 0.4, beside)
    x = b.L if left else b.R - width
    align = "left" if left else "right"
    entries = [("caption", b.label_text(), "label"), ("headline", b.get("title"), "headline"), ("body", b.get("subtitle"), "subtitle"), ("button", b.get("cta"), "cta")]
    height = b.stack_height(entries, width)
    y = max(b.T, b.B - height)
    b.stack(entries, x, y, width, align=align)
    if b.get("caption"):
        b.text("caption", b.get("caption"), b.L if not left else b.R - b.cw * 0.3, b.T, b.cw * 0.3, name="caption", color="@muted", align="right" if left else "left")


def _z_pattern(b):
    b.background()
    third = b.cw / 3
    b.text("caption", b.label_text() or b.get("caption"), b.L, b.T, third * 1.4, name="label", color="@accent-text", align="left")
    if b.get("caption") and b.get("label"):
        b.text("caption", b.get("caption"), b.R - third * 1.4, b.T, third * 1.4, name="caption", color="@muted", align="right")
    width = b.cw * 0.84
    _, hy, _, hh = b.text("headline", b.get("title"), b.L + (b.cw - width) / 2, b.T + b.ch * 0.26, width, name="headline", align="center", max_height=b.ch * 0.42)
    bottom = b.B
    if b.get("cta"):
        size = b.sizes["body"]
        bh = size * 2.3
        b.button(b.get("cta"), b.R, bottom - bh, align="right")
    b.text("body", b.get("subtitle") or b.get("body"), b.L, max(hy + hh + b.unit * 4, bottom - b.ch * 0.22), b.cw * 0.5, name="body", align="left", max_height=b.ch * 0.22)


def _f_pattern(b):
    b.background()
    bar = max(3, round(b.unit * 0.8))
    b.rect("spine", b.L, b.T, bar, b.ch, "@accent")
    x = b.L + bar * 5
    width = b.cw - bar * 5
    y = b.T
    _, _, _, h = b.text("headline", b.get("title"), x, y, width, name="headline", align="left", max_height=b.ch * 0.3)
    y += h + b.unit * 4
    sections = [s for s in str(b.get("items") or b.get("body")).split("\n") if s.strip()][:6]
    if not sections:
        return
    for index, section in enumerate(sections):
        head, _, rest = section.partition(":")
        _, _, _, h = b.text("subhead", head.strip(), x, y, width, name=f"point-{index + 1}", align="left", max_height=b.B - y)
        y += h + b.unit
        if rest.strip():
            _, _, _, h = b.text("body", rest.strip(), x, y, width * 0.8, name=f"point-{index + 1}-text", align="left", color="@muted", max_height=b.B - y)
            y += h
        y += b.unit * 3
        if y > b.B - b.sizes["subhead"]:
            break


def _rule_of_thirds(b):
    b.background()
    ix = b.rng.choice([1, 2])
    iy = b.rng.choice([1, 2])
    fx, fy = b.W * ix / 3, b.H * iy / 3
    d = min(b.W, b.H) * 0.42
    if b.get("image") or b.rng.random() < 0.6:
        b.image("image", fx - d / 2, fy - d / 2, d, d)
    else:
        b.ellipse("focal", fx - d / 2, fy - d / 2, d, d, "@accent")
    gap = b.unit * 4
    if ix == 2:
        text_x, width, align = b.L, fx - d / 2 - gap - b.L, "left"
    else:
        text_x, width, align = fx + d / 2 + gap, b.R - (fx + d / 2 + gap), "right"
    entries = [("caption", b.label_text(), "label"), ("headline", b.get("title"), "headline"), ("body", b.get("subtitle"), "subtitle"), ("button", b.get("cta"), "cta")]
    height = b.stack_height(entries, width)
    y = b.T if iy == 2 else max(b.T, b.B - height)
    b.stack(entries, text_x, y, width, align=align)


def _golden_section(b):
    b.background()
    phi = 0.618
    if b.W >= b.H:
        big = round(b.W * phi)
        image_box = (0, 0, big, b.H) if b.rng.random() < 0.5 else (b.W - big, 0, big, b.H)
        text_box = (big, 0, b.W - big, b.H) if image_box[0] == 0 else (0, 0, b.W - big, b.H)
    else:
        big = round(b.H * phi)
        # The copy below the picture stays inside the canvas: the picture gives up height when it must.
        entries = [("caption", b.label_text(), "label"), ("title", b.get("title"), "headline"),
                   ("body", b.get("subtitle") or b.get("body"), "body"), ("button", b.get("cta"), "cta")]
        needed = b.stack_height(entries, b.W - 2 * b.m) + 2 * b.m + max(0, b.safe[3] - b.m)
        big = max(round(b.H * 0.4), min(big, b.H - needed))
        image_box = (0, 0, b.W, big)
        text_box = (0, big, b.W, b.H - big)
    b.image("image", *image_box, bleed=True)
    line = max(2, round(b.unit / 2))
    if text_box[2] < b.W:
        edge = text_box[0] if text_box[0] else text_box[2] - line
        b.rect("golden-division", edge, 0, line, b.H, "@accent")
    else:
        b.rect("golden-division", 0, text_box[1], b.W, line, "@accent")
    pad = b.m
    tx, ty, tw = text_box[0] + pad, text_box[1] + pad, text_box[2] - 2 * pad
    entries = [("caption", b.label_text(), "label"), ("title", b.get("title"), "headline"), ("body", b.get("subtitle") or b.get("body"), "body"), ("button", b.get("cta"), "cta")]
    b.stack(entries, tx, ty, tw, align="left")


def _big_number(b):
    b.background()
    align = b.align
    width = b.cw
    y = b.T + b.ch * 0.08
    _, _, _, h = b.text("caption", b.label_text(), b.L, y, width, name="label", color="@accent-text", align=align)
    y += h + b.unit * 2
    title = b.get("title")
    size = round(min(b.ch * 0.4, width / max(len(title), 1) * 1.55))
    _, _, _, h = b.text(size, title, b.L, y, width, name="number", align=align, color="@accent", max_height=b.ch * 0.5, display=True, line=LINE_HEIGHT["display"])
    y += h + b.unit * 3
    b.accent_device(b.L, y + b.unit * 4, width, 0)
    y += b.unit * 4
    _, _, _, h = b.text("subhead", b.get("subtitle"), b.L, y, width * 0.85 if align != "center" else width, name="subtitle", align=align)
    y += h + b.unit * 2
    b.text("body", b.get("body"), b.L, y, width * 0.7 if align == "left" else width, name="body", align=align, color="@muted", max_height=b.B - y)


def _quote_card(b):
    b.background()
    align = b.align if b.align != "right" else "left"
    width = b.cw * (0.86 if b.orientation != "wide" else 0.6)
    x = b.L if align == "left" else b.L + (b.cw - width) / 2
    mark = round(min(b.sizes["display"] * 2.6, b.ch * 0.3))
    entries_h = b.stack_height([("title", b.get("title"), "quote"), ("body", b.get("subtitle"), "attribution")], width) + mark * 0.55
    y = b.T + max(0, (b.ch - entries_h) * 0.45)
    b.text(mark, "“", x if align == "left" else b.W / 2 - mark * 0.3, y - mark * 0.25, mark, name="quote-mark", color="@accent", align="left", display=True, line=LINE_HEIGHT["display"])
    y += mark * 0.55
    _, _, _, h = b.text("title", b.get("title"), x, y, width, name="quote", align=align, max_height=b.B - y - b.sizes["body"] * 3, line=LINE_HEIGHT["lead"])
    y += h + b.unit * 4
    b.text("body", ("— " + b.get("subtitle")) if b.get("subtitle") and not b.get("subtitle").startswith("—") else b.get("subtitle"), x, y, width, name="attribution", align=align, color="@muted")


def _framed(b):
    b.background()
    inset = b.m * 0.55
    line = max(2, round(b.unit / 2))
    b.rect("frame-outer", inset, inset, b.W - 2 * inset, b.H - 2 * inset, "transparent", stroke="@accent", stroke_width=line)
    gap = line * 4
    b.rect("frame-inner", inset + gap, inset + gap, b.W - 2 * (inset + gap), b.H - 2 * (inset + gap), "transparent", stroke="@accent", stroke_width=max(1, line // 2))
    width = b.cw * 0.78
    x = b.L + (b.cw - width) / 2
    entries = [("caption", b.label_text(), "label"), ("headline", b.get("title"), "headline"), ("lead", b.get("subtitle"), "subtitle"), ("body", b.get("body"), "body"), ("caption", b.get("caption"), "caption")]
    height = b.stack_height(entries, width, b.unit * 4)
    b.stack(entries, x, b.T + max(0, (b.ch - height) * 0.46), width, gap=b.unit * 4, align="center")


def _diagonal_band(b):
    b.background()
    angle = b.rng.choice([-12, -9, -7, 7, 9, 12])
    band_h = b.H * 0.26
    b.rect("band", -b.W * 0.15, b.H * 0.52 - band_h / 2, b.W * 1.3, band_h, "@accent")
    b.rotate("band", angle)
    width = b.cw * 0.9
    _, _, _, h = b.text("headline", b.get("title"), b.L, b.T + b.ch * 0.05, width, name="headline", align="left", max_height=b.ch * 0.32)
    if b.get("subtitle"):
        sw = b.W * 0.8
        _, _, _, sh = b.text("subhead", b.get("subtitle"), (b.W - sw) / 2, b.H * 0.52, sw, name="subtitle", color="@on-accent", align="center", max_height=band_h * 0.6)
        # Center the text block on the band so both rotate about the same point.
        next(op for op in reversed(b.ops) if op.get("name") == b.name("subtitle") and op["type"] == "text")["y"] = round(b.H * 0.52 - sh / 2)
        b.rotate("subtitle", angle)
    entries = [("body", b.get("body"), "body"), ("button", b.get("cta"), "cta")]
    height = b.stack_height(entries, b.cw * 0.6)
    b.stack(entries, b.R - b.cw * 0.6, max(b.H * 0.7, b.B - height), b.cw * 0.6, align="right")


def _typographic_poster(b):
    b.background()
    words = b.get("title").replace("[", "").replace("]", "").split()
    hero = (words[0] if words else "TYPE").upper()
    rest = " ".join(words[1:])
    entries = [("caption", b.label_text(), "label"), ("headline", rest, "headline"), ("body", b.get("subtitle"), "subtitle"), ("caption", b.get("caption"), "caption")]
    width = b.cw * 0.6
    height = b.stack_height(entries, width)
    top_word = b.rng.random() < 0.5
    zone = max(b.unit * 4, b.ch - height - b.unit * 6)
    # One word scaled to the full measure: type used as image, kept whole and clear of the copy.
    size = round(min(b.cw / max(len(hero), 1) * 1.75, zone * 0.9))
    w, h = b.measure(hero, size, None, 0, "left", b.display_font)
    while size > 6 and (w > b.cw or h > zone):
        size = int(size * 0.94)
        w, h = b.measure(hero, size, None, 0, "left", b.display_font)
    y = b.T if top_word else b.B - h
    b.glyphs(size, hero, b.L + w / 2, y + h / 2, "hero-word", color="@accent")
    align = b.rng.choice(["left", "right"])
    tx = b.L if align == "left" else b.R - width
    ty = b.B - height if top_word else b.T
    b.stack(entries, tx, ty, width, align=align)


def _product_card(b):
    b.background()
    radius = round(min(b.W, b.H) * 0.03)
    image_h = b.ch * (0.56 if b.orientation != "landscape" else 0.0)
    if b.orientation in ("landscape", "wide"):
        image_w = b.cw * 0.5
        b.image("image", b.L, b.T, image_w, b.ch)
        x, width, y = b.L + image_w + b.unit * 6, b.cw - image_w - b.unit * 6, b.T + b.ch * 0.12
    else:
        b.rect("image-panel", b.L, b.T, b.cw, image_h, "@surface", radius=radius)
        b.image("image", b.L + b.unit * 2, b.T + b.unit * 2, b.cw - b.unit * 4, image_h - b.unit * 4)
        x, width, y = b.L, b.cw, b.T + image_h + b.unit * 4
    entries = [("caption", b.label_text(), "label"), ("title", b.get("title"), "headline"), ("body", b.get("body") or b.get("subtitle"), "body")]
    y = b.stack(entries, x, y, width, align="left") + b.unit * 4
    price = b.get("caption")
    if price:
        _, _, _, h = b.text("subhead", price, x, y, width / 2, name="price", color="@accent-text", align="left")
    if b.get("cta"):
        b.button(b.get("cta"), x + width, y, align="right")


def _event_poster(b):
    b.background()
    bottom = b.B - (b.sizes["body"] * 3.2 if b.get("cta") or b.get("caption") else 0)
    ops, created = len(b.ops), len(b.created)
    # Grow the type on large formats until the content fills the page, keeping the last fit.
    previous = 1.0
    for grow in (1.0, 1.25, 1.5, 1.8, 2.2):
        del b.ops[ops:], b.created[created:]
        y = _event_details(b, grow)
        if y > bottom or y > b.T + b.ch * 0.6:
            if y > bottom and grow > 1:
                del b.ops[ops:], b.created[created:]
                y = _event_details(b, previous)
            break
        previous = grow
    spare = bottom - y - b.unit * 4
    if spare > b.ch * 0.15:
        # Headline at the top, the facts at the foot: move the date and details down together.
        heading = next(i for i in range(ops, len(b.ops)) if b.ops[i].get("name") == b.name("headline"))
        for op in b.ops[heading + 1:]:
            if "y" in op:
                op["y"] = round(op["y"] + spare)
        y += spare
    if b.get("cta"):
        b.button(b.get("cta"), b.L, max(y + b.unit * 4, b.B - b.sizes["body"] * 2.4), align="left")
    if b.get("caption"):
        b.text("caption", b.get("caption"), b.L, b.B - b.sizes["caption"] * 1.3, b.cw, name="caption", color="@muted", align="right")


def _event_details(b, grow):
    def role(name, cap=None):
        return name if grow == 1 else round(b.sizes[name] * min(grow, cap or grow))

    y = b.T
    _, _, _, h = b.text(role("headline"), b.get("title"), b.L, y, b.cw, name="headline", align="left", max_height=b.ch * 0.38, display=True)
    y += h + b.unit * 4 * grow
    headline_size = next(op["size"] for op in reversed(b.ops) if op.get("type") == "text")
    date = b.get("label")
    if date:
        pad = b.unit * 3 * min(grow, 1.5)
        bw = b.cw * (0.5 if b.orientation != "tall" else 0.8)
        # The block widens to hold the date on one line rather than wrapping it.
        # The event name stays the dominant element: the date is at most ~60% of the headline as placed.
        size = min(round(b.sizes["title"] * grow), round(headline_size * 0.6))
        size = max(size, 6)
        bw = min(b.cw, max(bw, b.measure(date, size, None, round(size * 0.1), "left", b.display_font)[0] + pad * 2 + size * 0.3))
        b.rect("date-block", b.L, y, bw, 1, "@accent")
        block = b.ops[-1]
        # Size the block to the text as placed (heavy type may shrink to fit), not the nominal size.
        _, _, _, th = b.text(size, date, b.L + pad, y + pad, bw - pad * 2, name="date", color="@on-accent", align="left", display=True)
        block["height"] = round(th + pad * 2)
        y += th + pad * 2 + b.unit * 4 * grow
    details = [line for line in str(b.get("body")).split("\n") if line.strip()]
    for index, line in enumerate(details[:6]):
        _, _, _, h = b.text(role("lead", 1.5), line, b.L, y, b.cw, name=f"detail-{index + 1}", align="left", color="@ink" if index == 0 else "@muted")
        y += h + b.unit * 2 * min(grow, 1.5)
    return y


def _banner(b):
    if b.orientation not in ("wide", "landscape"):
        return _centered_axis(b)
    b.background()
    cta = b.get("cta")
    cta_w = 0
    if cta:
        tw, _ = b.measure(cta, b.sizes["body"], None, 0)
        cta_w = tw + b.sizes["body"] * 2.2
    text_w = b.cw - cta_w - b.unit * 6
    title_size = b.sizes["title"]
    _, th = b.measure(b.get("title"), title_size, text_w, b.leading(title_size, LINE_HEIGHT["heading"], b.display_font),
                      "left", b.display_font)
    entries = [("title", b.get("title"), "headline"), ("body", b.get("subtitle"), "subtitle")]
    height = b.stack_height(entries, text_w, b.unit * 1.5)
    y = b.T + max(0, (b.ch - height) / 2)
    b.stack(entries, b.L, y, text_w, gap=b.unit * 1.5, align="left")
    if cta:
        bh = b.sizes["body"] * 2.2
        b.button(cta, b.R, b.H / 2 - bh / 2, align="right")


def _letterhead(b):
    b.background()
    line = max(2, round(b.unit / 3))
    y = b.T
    mark = b.sizes["title"] * 1.4
    b.rect("logo-mark", b.L, y, mark, mark, "@accent", shape=b.rng.choice(["ellipse", "rounded-rectangle", "hexagon"]), radius=round(mark * 0.2))
    initials = initials_of(b.get("title"))
    if initials:
        b.text(round(mark * 0.42), initials, b.L, y + mark * 0.27, mark, name="logo-initials", color="@on-accent", align="center", display=True)
    b.text("title", b.get("title"), b.L + mark + b.unit * 3, y + mark * 0.12, b.cw * 0.5, name="name", align="left", max_height=mark)
    contact = str(b.get("subtitle")).replace(" | ", "\n")
    b.text("caption", contact, b.R - b.cw * 0.4, y, b.cw * 0.4, name="contact", align="right", color="@muted")
    y += mark + b.unit * 4
    b.rect("header-rule", b.L, y, b.cw, line, "@accent")
    if b.get("body"):
        b.text("body", b.get("body"), b.L, y + b.unit * 10, b.cw * 0.8, name="body", align="left", max_height=b.B - y - b.unit * 20)
    b.rect("footer-rule", b.L, b.B - b.sizes["caption"] * 2.2, b.cw, max(1, line // 2), "@muted")
    b.text("caption", b.get("caption"), b.L, b.B - b.sizes["caption"] * 1.4, b.cw, name="footer", align="center", color="@muted")


def _business_card(b):
    b.background()
    stripe = b.rng.choice(["left", "top", "bottom", "none"])
    t = max(3, round(min(b.W, b.H) * 0.035))
    if stripe == "left":
        b.rect("stripe", 0, 0, t, b.H, "@accent")
    elif stripe in ("top", "bottom"):
        b.rect("stripe", 0, 0 if stripe == "top" else b.H - t, b.W, t, "@accent")
    mark = b.sizes["title"] * 1.3
    b.rect("logo-mark", b.R - mark, b.T, mark, mark, "@accent", shape=b.rng.choice(["ellipse", "rounded-rectangle", "diamond"]), radius=round(mark * 0.22))
    entries = [("title", b.get("title"), "name"), ("body", b.get("subtitle"), "role")]
    y = b.T
    y = b.stack(entries, b.L, y, b.cw - mark - b.unit * 2, gap=b.unit, align="left")
    contact = str(b.get("body")).replace(" | ", "\n")
    _, ch = b.measure(contact, b.sizes["caption"], b.cw, b.leading(b.sizes["caption"], LINE_HEIGHT["caption"], b.font),
                      "left", b.font)
    b.text("caption", contact, b.L, b.B - ch, b.cw, name="contact", align="left", color="@muted")


def _slide_title(b):
    b.background()
    bar = max(4, round(b.unit))
    b.rect("accent-bar", b.L, b.T + b.ch * 0.4, bar * 6, bar, "@accent")
    _, y, _, h = b.text("display", b.get("title"), b.L, b.T + b.ch * 0.4 + bar * 4, b.cw * 0.82, name="title", align="left", max_height=b.ch * 0.36)
    b.text("subhead", b.get("subtitle"), b.L, y + h + b.unit * 3, b.cw * 0.7, name="subtitle", align="left", color="@muted")
    b.text("caption", b.get("caption") or b.get("label"), b.L, b.B - b.sizes["caption"] * 1.4, b.cw, name="footer", align="left", color="@muted")


def _slide_content(b):
    b.background()
    y = b.T
    _, _, _, h = b.text("title", b.get("title"), b.L, y, b.cw, name="title", align="left", max_height=b.ch * 0.2)
    y += h + b.unit * 5
    has_image = b.rng.random() < 0.6 or b.get("image")
    text_w = b.cw * (0.55 if has_image else 0.85)
    items = [line.strip().lstrip("-•* ").strip() for line in str(b.get("items") or b.get("body")).split("\n") if line.strip()][:7]
    dot = max(4, round(b.sizes["lead"] * 0.28))
    for index, item in enumerate(items):
        b.ellipse(f"bullet-{index + 1}", b.L, y + b.sizes["lead"] * 0.42, dot, dot, "@accent")
        _, _, _, h = b.text("lead", item, b.L + dot * 3, y, text_w - dot * 3, name=f"point-{index + 1}", align="left", max_height=b.B - y)
        y += h + b.unit * 3
    if has_image:
        top = b.T + b.sizes["title"] * 1.6 + b.unit * 5
        b.image("image", b.L + b.cw * 0.6, top, b.cw * 0.4, b.B - top - b.sizes["caption"] * 2)
    b.text("caption", b.get("caption"), b.L, b.B - b.sizes["caption"] * 1.3, b.cw, name="footer", align="right", color="@muted")


def _mark(b, size, x, y):
    shape = b.op.get("mark") or b.rng.choice(["ellipse", "rounded-rectangle", "hexagon", "diamond", "shield", "octagon"])
    b.rect("mark", x, y, size, size, "@accent", shape=shape, radius=round(size * 0.24))
    initials = b.get("label") or initials_of(b.get("title"))
    if initials:
        glyph = round(size * (0.5 if len(initials) == 1 else 0.38))
        # Shields and diamonds carry visual weight low/centered; nudge the optical center.
        offset = {"shield": -0.04, "diamond": 0.0}.get(shape, 0.0) * size
        b.glyphs(glyph, initials, x + size / 2, y + size / 2 + offset, "mark-initials")
    return shape


def _logo_horizontal(b):
    b.op.setdefault("transparent", True)
    b.background()
    mark = min(b.H * 0.62, b.W * 0.28)
    name_size = round(mark * 0.42)
    tagline = b.get("subtitle")
    nw, nh = b.measure(b.get("title"), name_size, None, 0, "left", b.display_font)
    tw, th = b.measure(tagline, round(name_size * 0.36), None, 0) if tagline else (0, 0)
    gap = round(mark * 0.28)
    total = mark + gap + max(nw, tw)
    scale = min(1, b.cw / total)
    mark, name_size, gap = mark * scale, max(6, round(name_size * scale)), gap * scale
    x = (b.W - min(total, b.cw)) / 2
    y = (b.H - mark) / 2
    _mark(b, mark, x, y)
    _, nh = b.measure(b.get("title"), name_size, None, 0, "left", b.display_font)
    text_h = nh + (b.unit + th * scale if tagline else 0)
    ty = y + (mark - text_h) / 2
    nw, nh = b.measure(b.get("title"), name_size, None, 0, "left", b.display_font)
    left = x + mark + gap
    b.glyphs(name_size, b.get("title"), left + nw / 2, ty + nh / 2, "wordmark", color="@ink")
    if tagline:
        tag_size = max(6, round(name_size * 0.36))
        tw, th = b.measure(tagline, tag_size, None, 0)
        b.glyphs(tag_size, tagline, left + tw / 2, ty + nh + b.unit + th / 2, "tagline", color="@muted")


def _logo_stacked(b):
    b.op.setdefault("transparent", True)
    b.background()
    mark = min(b.W, b.H) * 0.42
    name_size = round(mark * 0.3)
    nw, nh = b.measure(b.get("title"), name_size, None, 0, "left", b.display_font)
    if nw > b.cw:
        name_size = max(6, int(name_size * b.cw / nw))
        nw, nh = b.measure(b.get("title"), name_size, None, 0, "left", b.display_font)
    tagline = b.get("subtitle")
    tag_size = max(6, round(name_size * 0.38))
    _, th = b.measure(tagline, tag_size, None, 0) if tagline else (0, 0)
    gap = mark * 0.18
    total = mark + gap + nh + (b.unit * 2 + th if tagline else 0)
    y = (b.H - total) / 2
    _mark(b, mark, (b.W - mark) / 2, y)
    y += mark + gap
    b.text(name_size, b.get("title"), b.L, y, b.cw, name="wordmark", align="center", display=True, line=LINE_HEIGHT["display"])
    if tagline:
        b.text(tag_size, tagline, b.L, y + nh + b.unit * 2, b.cw, name="tagline", color="@muted", align="center", line=LINE_HEIGHT["caption"])


def _emblem(b):
    b.op.setdefault("transparent", True)
    b.background()
    d = min(b.cw, b.ch)
    x, y = (b.W - d) / 2, (b.H - d) / 2
    ring = max(2, round(d * 0.02))
    b.ellipse("badge", x, y, d, d, "@accent")
    inner = d * 0.68
    b.ellipse("badge-inner", (b.W - inner) / 2, (b.H - inner) / 2, inner, inner, "transparent", stroke="@on-accent", stroke_width=ring)
    name = b.get("title").upper()
    # The name runs along a circular path centered in the band between edge and inner ring.
    size = max(6, round(d * 0.07))
    radius = d * 0.42 - size * 0.35
    tw, th = b.measure(name, size, None, 0, "left", b.display_font)
    sweep = min(math.radians(150), tw / radius * 1.08)
    if tw / radius * 1.08 > sweep:
        size = max(6, int(size * sweep / (tw / radius * 1.08)))
    sweep = max(sweep, math.radians(20))
    points = [
        [round(d / 2 + radius * math.cos(angle), 2), round(d / 2 + radius * math.sin(angle), 2)]
        for angle in (math.radians(270) - sweep / 2 + sweep * i / 48 for i in range(49))
    ]
    layer = b.name("arc-name")
    b.add({"type": "text", "name": layer, "text": name, "size": size, "color": "@on-accent", "x": round(x), "y": round(y), **({"font": b.display_font} if b.display_font else {})})
    b.add({"type": "text-layout", "target": layer, "width": round(d), "height": round(d), "path": points})
    b.created.append(layer)
    initials = b.get("label") or initials_of(b.get("title"))
    b.glyphs(round(d * (0.26 if len(initials) == 1 else 0.19)), initials, b.W / 2, b.H / 2 - d * 0.02, "initials")
    if b.get("subtitle"):
        b.glyphs(max(6, round(d * 0.04)), b.get("subtitle").upper(), b.W / 2, y + d * 0.66, "tagline")


def _monogram(b):
    b.op.setdefault("transparent", True)
    b.background()
    d = min(b.cw, b.ch)
    _mark(b, d, (b.W - d) / 2, (b.H - d) / 2)


def _app_icon(b):
    s = min(b.W, b.H)
    radius = round(s * 0.2237)  # Continuous-corner approximation used by modern icon grids.
    b.rect("icon-background", 0, 0, b.W, b.H, "@accent", radius=radius)
    b.add({"type": "layer-style", "target": b.name("icon-background"), "name": "gradient-overlay", "settings": {"start": "lighten(@accent, 8%)", "end": "darken(@accent, 12%)", "direction": "vertical"}})
    keyline = s * 0.62
    glyph = b.get("label") or initials_of(b.get("title"))[:1]
    if glyph:
        size = round(keyline * (0.82 if len(glyph) == 1 else 0.5))
        b.glyphs(size, glyph, b.W / 2, b.H / 2, "glyph")
    else:
        b.ellipse("glyph", (b.W - keyline * 0.6) / 2, (b.H - keyline * 0.6) / 2, keyline * 0.6, keyline * 0.6, "@on-accent")


def _thumbnail_bold(b):
    b.background()
    left = b.rng.random() < 0.5
    image_w = b.W * 0.46
    b.image("image", b.W - image_w if left else 0, 0, image_w, b.H)
    width = b.W - image_w - b.m * 1.5
    x = b.L if left else image_w + b.m * 0.5
    size = round(b.H * 0.2)
    words = b.get("title")
    reserve = b.sizes["subhead"] * 2.4 if b.get("label") else 0
    _, _, w, h = b.text(size, words, x, b.T, width, name="headline", align="left", max_height=max(b.unit * 4, b.ch * 0.78 - reserve), display=True, line=LINE_HEIGHT["display"])
    if b.accent in ("block", "bar", "rule"):
        b.rect("highlight", x - b.unit, b.T + h + b.unit * 2, width * 0.6, max(4, round(size * 0.18)), "@accent")
    if b.get("label"):
        b.button(b.get("label"), x, b.B - b.sizes["subhead"] * 1.8, align="left")


def _story_vertical(b):
    b.background()
    c = b.project.state["canvas"]
    safe = max(safe_sides(c)[1], safe_sides(c)[3], round(b.H * 0.12))
    top, bottom = safe, b.H - safe
    _, _, _, h = b.text("caption", b.label_text(), b.L, top, b.cw, name="label", color="@accent-text", align=b.align)
    y = top + h + b.unit * 3
    _, _, _, h = b.text("headline", b.get("title"), b.L, y, b.cw, name="headline", align=b.align, max_height=(bottom - top) * 0.3)
    y += h + b.unit * 4
    cta_h = b.sizes["body"] * 2.6 if b.get("cta") else 0
    image_h = max(0, bottom - y - cta_h - b.unit * 8 - (b.sizes["lead"] * 3 if b.get("subtitle") else 0))
    if image_h > b.unit * 10:
        b.image("image", b.L, y, b.cw, image_h)
        y += image_h + b.unit * 4
    b.text("lead", b.get("subtitle"), b.L, y, b.cw, name="subtitle", align=b.align)
    if b.get("cta"):
        anchor = b.L if b.align == "left" else b.R if b.align == "right" else b.W / 2
        b.button(b.get("cta"), anchor, bottom - cta_h, align=b.align)


def _price_list(b):
    b.background()
    y = b.T
    _, _, _, h = b.text("headline", b.get("title"), b.L, y, b.cw, name="title", align=b.align, max_height=b.ch * 0.2)
    y += h + b.unit * 2
    if b.get("subtitle"):
        _, _, _, h = b.text("body", b.get("subtitle"), b.L, y, b.cw, name="subtitle", align=b.align, color="@muted")
        y += h
    y += b.unit * 5
    rows = [line for line in str(b.get("items") or b.get("body")).split("\n") if line.strip()][:24]
    available = b.B - y
    row_h = min(b.sizes["lead"] * 2.4, available / max(len(rows), 1))
    size = max(6, min(b.sizes["lead"], round(row_h / 2.2)))
    for index, row in enumerate(rows):
        if "|" in row:
            item, price = (part.strip() for part in row.split("|", 1))
        elif " - " in row:
            item, price = (part.strip() for part in row.rsplit(" - ", 1))
        else:
            item, price = row.strip(), ""
        b.text(size, item, b.L, y, b.cw * 0.7, name=f"item-{index + 1}", align="left")
        if price:
            b.text(size, price, b.L + b.cw * 0.7, y, b.cw * 0.3, name=f"price-{index + 1}", align="right", color="@accent-text")
        y += row_h
        if index < len(rows) - 1:
            b.rect(f"separator-{index + 1}", b.L, y - row_h * 0.22, b.cw, 1, "@surface" if b.colors["_mode"] == "light" else "@muted", opacity=0.9)


def _photo_caption(b):
    b.image("image", 0, 0, b.W, b.H, bleed=True)
    entries = [("caption", b.label_text(), "label"), ("headline", b.get("title"), "headline"), ("body", b.get("subtitle"), "subtitle")]
    width = b.cw * 0.86
    height = b.stack_height(entries, width)
    top = max(0, round(b.B - height - b.unit * 4))
    fade = round(min(top, b.H * 0.22))
    # A gradient fades the photo into a near-solid scrim, so text never sits on busy image areas.
    if fade:
        b.add({"type": "gradient", "name": b.name("scrim-fade"), "start": "alpha(@background, 0)", "end": "alpha(@background, 0.94)", "direction": "vertical", "width": b.W, "height": fade, "x": 0, "y": top - fade})
        b.created.append(b.name("scrim-fade"))
    b.rect("scrim", 0, top, b.W, b.H - top, "@background", opacity=0.94)
    b.stack(entries, b.L, b.B - height, width, align="left")


def _minimal_mark(b):
    b.background()
    corner = b.rng.choice(["tl", "tr", "bl", "br"])
    width = b.cw * 0.42
    x = b.L if corner in ("tl", "bl") else b.R - width
    align = "left" if corner in ("tl", "bl") else "right"
    entries = [("subhead", b.get("title"), "headline"), ("caption", b.get("subtitle"), "subtitle")]
    height = b.stack_height(entries, width, b.unit * 2)
    y = b.T if corner in ("tl", "tr") else b.B - height
    b.stack(entries, x, y, width, gap=b.unit * 2, align=align)
    d = b.unit * 3
    ox = b.W * (0.62 if align == "left" else 0.38)
    oy = b.H * (0.62 if corner in ("tl", "tr") else 0.38)
    b.ellipse("accent", ox - d / 2, oy - d / 2, d, d, "@accent")


def _bento_grid(b):
    b.background()
    gap = b.unit * 2
    radius = round(min(b.W, b.H) * 0.025)
    cols, rows = (3, 2) if b.W >= b.H else (2, 3)
    cw = (b.cw - (cols - 1) * gap) / cols
    rh = (b.ch - (rows - 1) * gap) / rows

    def cell(c, r, cs=1, rs=1):
        return b.L + c * (cw + gap), b.T + r * (rh + gap), cs * cw + (cs - 1) * gap, rs * rh + (rs - 1) * gap

    if cols == 3:
        hero, stat, image, info = cell(0, 0, 2, 1), cell(2, 0), cell(0, 1), cell(1, 1, 2, 1)
    else:
        hero, stat, image, info = cell(0, 0, 2, 1), cell(0, 1), cell(1, 1), cell(0, 2, 2, 1)
    pad = b.unit * 3
    b.rect("tile-hero", *hero, "@accent", radius=radius)
    b.text("headline", b.get("title"), hero[0] + pad, hero[1] + pad, hero[2] - 2 * pad, name="headline", color="@on-accent", align="left", max_height=hero[3] - 2 * pad)
    b.rect("tile-stat", *stat, "@surface", radius=radius)
    _, sy, _, sh = b.text("title", b.get("label"), stat[0] + pad, stat[1] + pad, stat[2] - 2 * pad, name="stat", color="@accent-text", align="left", max_height=stat[3] * 0.5)
    label_y = max(sy + sh + b.unit, stat[1] + stat[3] - pad - b.sizes["caption"] * 2.6)
    b.text("caption", b.get("caption"), stat[0] + pad, label_y, stat[2] - 2 * pad, name="stat-label", color="@muted", align="left", max_height=stat[1] + stat[3] - label_y)
    b.image("image", *image)
    b.rect("tile-info", *info, "@surface", radius=radius)
    b.stack([("body", b.get("subtitle") or b.get("body"), "body")], info[0] + pad, info[1] + pad, info[2] - 2 * pad, align="left")
    if b.get("cta"):
        b.button(b.get("cta"), info[0] + info[2] - pad, info[1] + info[3] - pad - b.sizes["body"] * 2.3, align="right")

# Memes: image slots and caption rules only (no stock images). Captions are white with a black stroke and set
# uppercase (uppercase=false keeps the case); they shrink to fit their box. Fonts follow the document typography
# or display_font: an Impact-style OFL face such as Anton (vixl_font_install) suits them.


def _meme_text(b, text, x, y, width, max_height, name, anchor="top", stroked=True, color="#ffffff"):
    if not text:
        return (x, y, 0, 0)
    if stroked and b.op.get("uppercase", True):
        text = text.upper()
    # The picture bleeds, but the caption stays inside the canvas safe area.
    left, top, right, bottom = b.safe
    x0, x1 = max(x, left), min(x + width, b.W - right)
    if x1 - x0 >= width * 0.5:
        x, width = x0, x1 - x0
    y = min(y, b.H - bottom) if anchor == "bottom" else max(y, top)
    size = max(8, round(min(b.W, b.H) * 0.11))
    # Never break a word: shrink until the longest word fits the line.
    longest = max(text.split(), key=len)
    while size > 8 and b.measure(longest, size, None, 0, "left", b.display_font)[0] > width:
        size = max(8, int(size * 0.92))
    x, top, w, h = b.text(size, text, x, y, width, name=name, align="center", color=color, max_height=max_height,
                          display=True, line=LINE_HEIGHT["display"])
    layer = b.name(name)
    op = next(op for op in b.ops if op.get("name") == layer and op["type"] == "text")
    if stroked:
        # A stroke style (outside the glyphs) is the outline the contrast check reads text through.
        b.add({"type": "layer-style", "target": layer, "name": "stroke",
               "settings": {"color": "#000000", "width": max(3, round(op["size"] * 0.07))}})
    if anchor == "bottom":
        op["y"] = top = round(y - h)
    return (x, top, w, h)


def _meme_lines(b, count):
    lines = [line.strip() for line in str(b.get("items") or "").splitlines() if line.strip()]
    return (lines + [""] * count)[:count]


def _meme_images(b, count):
    images = b.get("images", None) or []
    require(isinstance(images, list) and all(isinstance(item, str) for item in images) and len(images) <= count,
            f"images is a list of up to {count} asset ids", field="images")
    return images + [None] * (count - len(images))


def _meme_top_bottom(b):
    b.background("#000000")
    b.image("image", 0, 0, b.W, b.H, bleed=True)
    pad = round(min(b.W, b.H) * 0.04)
    _meme_text(b, b.get("title"), pad, pad, b.W - 2 * pad, b.H * 0.3, "top-text")
    _meme_text(b, b.get("caption"), pad, b.H - pad, b.W - 2 * pad, b.H * 0.3, "bottom-text", anchor="bottom")


def _meme_caption_above(b):
    pad = max(round(min(b.W, b.H) * 0.05), *b.safe)
    b.background("#ffffff")
    size = max(8, round(min(b.W, b.H) * 0.065))
    _, _, _, h = b.text(size, b.get("title"), pad, pad, b.W - 2 * pad, name="caption", align="left", color="#111111",
                        max_height=b.H * 0.3, display=True, line=LINE_HEIGHT["heading"])
    band = max(round(b.H * 0.16), h + 2 * pad)
    b.image("image", 0, band, b.W, b.H - band, bleed=True)


def _meme_comparison(b):
    b.background("#ffffff")
    images, lines = _meme_images(b, 2), _meme_lines(b, 2)
    split = round(b.W * 0.5)
    pad = max(round(min(b.W, b.H) * 0.04), *b.safe)
    for index in range(2):
        top, height = round(b.H * index / 2), round(b.H / 2)
        b.image(f"panel-{index + 1}", 0, top, split, height, asset=images[index], slot="images", bleed=True)
        text = lines[index]
        if not text:
            continue
        size = max(8, round(min(b.W, b.H) * 0.07))
        size, _, _, h = b.measure_box(size, text, b.W - split - 2 * pad, height - 2 * pad)
        b.text(size, text, split + pad, top + max(pad, (height - h) / 2), b.W - split - 2 * pad,
               name=f"label-{index + 1}", align="left", color="#111111", max_height=height - 2 * pad, display=True,
               line=LINE_HEIGHT["heading"])
    b.rect("divider", 0, round(b.H / 2) - 1, b.W, 2, "#000000")
    b.add({"type": "layer-intent", "target": b.name("divider"), "allow_crop": True})


def _meme_labelled(b):
    b.background("#000000")
    b.image("image", 0, 0, b.W, b.H, bleed=True)
    lines = [line for line in _meme_lines(b, 6) if line]
    left, _, right, _ = b.safe
    width = (b.W - left - right) / max(1, len(lines))
    for index, text in enumerate(lines):
        _meme_text(b, text, left + index * width + width * 0.06, b.H * 0.62, width * 0.88, b.H * 0.25,
                   f"label-{index + 1}")


def _meme_reaction(b):
    b.background("#000000")
    left, top, right, bottom = b.safe
    pad = max(round(min(b.W, b.H) * 0.05), left, right)
    reserve = max(round(b.H * 0.22), bottom + round(b.H * 0.1))
    b.image("image", 0, 0, b.W, b.H - reserve, bleed=True)
    _meme_text(b, b.get("caption"), pad, b.H - reserve + pad / 2, b.W - 2 * pad,
               reserve - pad / 2 - max(pad / 2, bottom), "caption", stroked=False)


def _meme_four_panel(b):
    b.background("#000000")
    images, lines = _meme_images(b, 4), _meme_lines(b, 4)
    gutter = max(2, round(min(b.W, b.H) * 0.008))
    w, h = (b.W - gutter) / 2, (b.H - gutter) / 2
    pad = round(min(w, h) * 0.05)
    for index in range(4):
        x, y = (index % 2) * (w + gutter), (index // 2) * (h + gutter)
        b.image(f"panel-{index + 1}", x, y, w, h, asset=images[index], slot="images", bleed=True)
        _meme_text(b, lines[index], x + pad, y + h - pad, w - 2 * pad, h * 0.4, f"caption-{index + 1}", anchor="bottom")



def _layout(fn, description, principles, best_for, examples, **extra):
    """``examples`` show the kind and length of copy each slot expects; they are never rendered."""
    return {"build": fn, "description": description, "principles": principles, "best_for": best_for, "examples": examples, **extra}


def initials_of(text):
    """Up to two initials from real words, ignoring placeholder brackets and punctuation."""
    return "".join(word[0] for word in re.findall(r"[^\W_]+", str(text))[:2]).upper()


SLOT_TEXT = {
    "title": ("Headline", "The main message in a few strong words"),
    "subtitle": ("Subheading", "One line that supports or explains the headline"),
    "body": ("Body", "Supporting copy: a sentence or short paragraph"),
    "label": ("Kicker", "A short eyebrow label set above the headline"),
    "cta": ("Action", "A two- or three-word call to action, shown as a button"),
    "caption": ("Caption", "A small supporting note"),
    "items": ("Items", "One item per line"),
    "images": ("Images", "A list of embedded image asset ids, one per panel in reading order (vixl_import_image returns "
               "them). Panels left empty get placeholder frames to fill later"),
    "image": ("Image", "An embedded image asset id (vixl_import_image returns one). Left empty, a placeholder frame is drawn; "
              "fill it later by importing a file, placing a saved resource, drawing it with shape/organic/paint operations, "
              "or generating it with an AI tool: see next_steps in the layout-apply result"),
}
# Layout-specific meaning for slots: (label, hint[, placeholder]). Placeholders keep the shape
# the layout parses (one detail per line, "item | price") so the blank composition is honest.
SLOT_OVERRIDES = {
    "event-poster": {"title": ("Event name", "What the event is called"), "label": ("Date", "The key fact, usually day and date"), "body": ("Details", "One detail per line: time, place, extras", "[Time]\n[Place]\n[Detail]"), "cta": ("Action", "What to do, e.g. RSVP"), "caption": ("Link", "Website, handle or contact")},
    "big-number": {"title": ("Number", "The statistic itself, short (e.g. a percentage)"), "label": ("Metric", "What the number measures"), "subtitle": ("Context", "A sentence that gives the number meaning"), "body": ("Source", "Where the number comes from")},
    "quote-card": {"title": ("Quote", "The quotation, without quote marks"), "subtitle": ("Attribution", "Who said it, and their role")},
    "framed": {"label": ("Document type", "e.g. what the certificate or invitation is"), "title": ("Name", "Recipient or honoree"), "subtitle": ("Reason", "Why it is presented"), "body": ("Date line", "When or where"), "caption": ("Signature line", "Who signs, and the date")},
    "product-card": {"label": ("Badge", "A short tag such as New or Sale"), "title": ("Product name", "The product's name"), "body": ("Benefit", "One or two lines on the benefit"), "caption": ("Price", "The price, formatted for the market")},
    "letterhead": {"title": ("Organization", "The organization's name"), "subtitle": ("Contact", "Contact details separated by |"), "caption": ("Address", "Footer address line"), "body": ("Letter body", "Optional body text")},
    "business-card": {"title": ("Name", "The person's name"), "subtitle": ("Role", "Job title"), "body": ("Contact", "Contact details separated by |")},
    "slide-title": {"title": ("Presentation title", "The talk or deck title"), "subtitle": ("Subtitle", "Subtitle or speaker"), "caption": ("Footer", "Organization · date")},
    "slide-content": {"title": ("Slide heading", "One idea per slide"), "items": ("Points", "One point per line, parallel in form", "[Point]\n[Point]\n[Point]"), "caption": ("Slide number", "Footer or slide number")},
    "logo-horizontal": {"title": ("Brand name", "The name as it should read"), "subtitle": ("Tagline", "Optional short tagline")},
    "logo-stacked": {"title": ("Brand name", "The name as it should read"), "subtitle": ("Tagline", "Optional short tagline")},
    "emblem": {"title": ("Brand name", "Runs around the badge"), "subtitle": ("Tagline", "A short line such as a founding year"), "label": ("Initials", "Optional override for the center initials")},
    "monogram": {"title": ("Brand name", "Initials are taken from it"), "label": ("Initials", "Optional override for the initials")},
    "app-icon": {"title": ("App name", "The glyph is taken from it"), "label": ("Glyph", "Optional override for the icon glyph")},
    "thumbnail-bold": {"title": ("Few huge words", "Two to four words that read at thumbnail size"), "label": ("Badge", "A short tag")},
    "price-list": {"title": ("Menu title", "The list's title"), "subtitle": ("Subheading", "A short description"), "items": ("Items", "One per line as: item | price", "[Item] | [Price]\n[Item] | [Price]\n[Item] | [Price]")},
    "f-pattern": {"items": ("Points", "One per line as: heading: explanation", "[Point]: [Explanation]\n[Point]: [Explanation]\n[Point]: [Explanation]")},
    "bento-grid": {"label": ("Stat", "A short figure for the stat tile"), "caption": ("Stat label", "What the stat measures"), "subtitle": ("Supporting copy", "Copy for the info tile")},
    "typographic-poster": {"title": ("Headline", "The first word is set huge as the image; the rest reads as the headline", "[Word] [rest of headline]"), "label": ("Issue", "Volume, issue or series label"), "caption": ("Date and place", "When and where")},
    "photo-caption": {"label": ("Category", "A short category label")},
    "z-pattern": {"caption": ("Note", "A small note such as a deadline")},
    "editorial-grid": {"caption": ("Image caption", "Describes the image")},
    "diagonal-band": {"subtitle": ("Band text", "The offer or line set on the band")},
    "meme-top-bottom": {"title": ("Top text", "The setup, a few words"), "caption": ("Bottom text", "The punchline"),
                        "image": ("Image", "The picture: an asset you have the rights to use")},
    "meme-caption-above": {"title": ("Caption", "One or two sentences set above the picture")},
    "meme-comparison": {"items": ("Panel labels", "One per line: the rejected option, then the preferred one",
                                  "[Rejected option]\n[Preferred option]"),
                        "images": ("Panel images", "Two asset ids: the reaction to each option")},
    "meme-labelled": {"items": ("Labels", "One label per line (up to 6); move each label layer onto its object",
                                "[Label]\n[Label]\n[Label]")},
    "meme-reaction": {"caption": ("Caption", "What the reaction answers, in a short line")},
    "meme-four-panel": {"items": ("Panel captions", "One caption per line, four panels in reading order",
                                  "[Caption]\n[Caption]\n[Caption]\n[Caption]"),
                        "images": ("Panel images", "Up to four asset ids in reading order")},
}
MULTI_IMAGE_LAYOUTS = {"meme-comparison", "meme-four-panel"}
IMAGE_LAYOUTS = {"meme-top-bottom", "meme-caption-above", "meme-labelled", "meme-reaction", "bento-grid", "editorial-grid", "golden-section", "photo-caption", "product-card", "rule-of-thirds", "slide-content", "split-screen", "story-vertical", "thumbnail-bold"}
OPTIONAL_SLOTS = {"emblem": {"label"}, "monogram": {"label"}, "app-icon": {"label"}, "letterhead": {"body"}, "logo-horizontal": {"subtitle"}, "logo-stacked": {"subtitle"}}

# Every slot each builder can read (some only on certain canvases); used for discovery only —
# apply-time validation uses the slots a build actually read.
OPTIONAL_READS = {
    "app-icon": ('label', 'title'),
    "asymmetric-balance": ('caption', 'cta', 'label', 'subtitle', 'title'),
    "banner": ('cta', 'subtitle', 'title', 'label'),
    "bento-grid": ('body', 'caption', 'cta', 'image', 'label', 'subtitle', 'title'),
    "big-number": ('body', 'label', 'subtitle', 'title'),
    "business-card": ('body', 'subtitle', 'title'),
    "centered-axis": ('cta', 'label', 'subtitle', 'title'),
    "diagonal-band": ('body', 'cta', 'subtitle', 'title'),
    "editorial-grid": ('body', 'caption', 'image', 'label', 'subtitle', 'title'),
    "emblem": ('label', 'subtitle', 'title'),
    "event-poster": ('body', 'caption', 'cta', 'label', 'title'),
    "f-pattern": ('body', 'items', 'title'),
    "framed": ('body', 'caption', 'label', 'subtitle', 'title'),
    "golden-section": ('body', 'cta', 'image', 'label', 'subtitle', 'title'),
    "hero-statement": ('caption', 'cta', 'label', 'subtitle', 'title'),
    "letterhead": ('body', 'caption', 'subtitle', 'title'),
    "logo-horizontal": ('subtitle', 'title', 'label'),
    "logo-stacked": ('subtitle', 'title', 'label'),
    "minimal-mark": ('subtitle', 'title'),
    "monogram": ('label', 'title'),
    "photo-caption": ('image', 'label', 'subtitle', 'title'),
    "price-list": ('body', 'items', 'subtitle', 'title'),
    "product-card": ('body', 'caption', 'cta', 'image', 'label', 'subtitle', 'title'),
    "quote-card": ('subtitle', 'title'),
    "rule-of-thirds": ('cta', 'image', 'label', 'subtitle', 'title'),
    "slide-content": ('body', 'caption', 'image', 'items', 'title'),
    "slide-title": ('caption', 'label', 'subtitle', 'title'),
    "split-screen": ('body', 'cta', 'image', 'label', 'subtitle', 'title'),
    "story-vertical": ('cta', 'image', 'label', 'subtitle', 'title'),
    "thumbnail-bold": ('image', 'label', 'title'),
    "typographic-poster": ('caption', 'label', 'subtitle', 'title'),
    "z-pattern": ('body', 'caption', 'cta', 'label', 'subtitle', 'title'),
    "meme-top-bottom": ('caption', 'image', 'title'),
    "meme-caption-above": ('image', 'title'),
    "meme-comparison": ('images', 'items'),
    "meme-labelled": ('image', 'items'),
    "meme-reaction": ('caption', 'image'),
    "meme-four-panel": ('images', 'items'),
}


def slot_spec(layout):
    """Slot → label, hint, placeholder and whether an unfilled slot is shown as a blank."""
    name = next((key for key, value in LAYOUTS.items() if value is layout), None)
    overrides = SLOT_OVERRIDES.get(name, {})
    examples = layout["examples"]
    keys = [k for k in CONTENT_KEYS if k in examples or k in overrides or (k == "image" and name in IMAGE_LAYOUTS)
            or (k == "images" and name in MULTI_IMAGE_LAYOUTS)]
    spec = {}
    for key in keys:
        label, hint, *placeholder = overrides.get(key, SLOT_TEXT[key])
        blank = key not in OPTIONAL_SLOTS.get(name, ()) and (key in IMAGE_KEYS or bool(examples.get(key)))
        spec[key] = {"label": label, "hint": hint, "placeholder": placeholder[0] if placeholder else f"[{label}]", "blank": blank}
        if examples.get(key):
            spec[key]["example"] = examples[key]
    return spec


COPY = {"label": "New season", "title": "Make the main point in a few strong words", "subtitle": "One supporting sentence that explains why it matters.", "cta": "Learn more"}
LAYOUTS = {
    "hero-statement": _layout(_hero_statement, "One dominant headline with a quiet supporting line.", ["single focal point", "scale contrast between headline and support", "generous negative space"], ["social", "poster", "web", "slides"], COPY, aligns=["left", "left", "center", "right"], dramatic=True),
    "editorial-grid": _layout(_editorial_grid, "Magazine-style modular grid with kicker, headline, deck, body and captioned image.", ["modular column grid", "clear typographic hierarchy", "consistent gutters and rules"], ["print", "poster", "web", "slides"], {**COPY, "body": "Body copy sits on the column grid. Keep lines between 45 and 75 characters, align every element to a column edge, and let white space separate groups instead of extra lines.", "caption": "Image caption, set small and muted."}, accents=["rule"]),
    "split-screen": _layout(_split_screen, "Image and message in two clear zones, split evenly or at the golden ratio.", ["figure–ground separation", "two-zone hierarchy", "proportional division"], ["web", "social", "slides", "ads"], COPY, aligns=["left"]),
    "centered-axis": _layout(_centered_axis, "Formal, symmetric stack on a central axis with an ornament divider.", ["symmetrical balance", "optical centering", "consistent vertical rhythm"], ["invitations", "announcements", "social", "certificates"], COPY, aligns=["center"], accents=["none"]),
    "asymmetric-balance": _layout(_asymmetric_balance, "Heavy color shape on one side balanced by the text block opposite.", ["asymmetric visual weight", "tension and balance", "directional flow"], ["poster", "social", "web"], COPY),
    "z-pattern": _layout(_z_pattern, "Elements placed along the Z reading path ending at the call to action.", ["Z-pattern scanning", "terminal-area call to action", "reading order"], ["ads", "web", "banners", "social"], {**COPY, "caption": "Limited time"}, accents=["none"]),
    "f-pattern": _layout(_f_pattern, "Text-heavy layout for scanning: strong left edge, headline, then labelled points.", ["F-pattern scanning", "left-aligned scannable structure", "parallel subheads"], ["print", "slides", "infographics", "web"], {"title": "Three things to know", "items": "First point: a short explanation that supports it.\nSecond point: keep each one parallel in form.\nThird point: end on the most useful idea."}, accents=["bar"]),
    "rule-of-thirds": _layout(_rule_of_thirds, "Focal image or shape on a thirds intersection, message in the opposite field.", ["rule of thirds", "focal placement", "counterbalance"], ["social", "poster", "photo"], COPY),
    "golden-section": _layout(_golden_section, "Canvas divided at the golden ratio: image in the major section, message in the minor.", ["golden ratio proportion", "dominant and subordinate areas", "nested proportion"], ["print", "web", "social"], COPY, accents=["none"]),
    "big-number": _layout(_big_number, "A giant statistic with label and context; numbers as the hero.", ["data as focal point", "extreme scale contrast", "label–value–context hierarchy"], ["infographics", "social", "slides"], {"label": "Customer satisfaction", "title": "94%", "subtitle": "of customers would recommend us to a friend.", "body": "Survey of 2,000 customers, 2025."}, aligns=["left", "center"], accents=["rule", "none"]),
    "quote-card": _layout(_quote_card, "Large quotation with a decorative mark and attribution.", ["typographic focal point", "hanging punctuation", "restrained palette"], ["social", "slides", "print"], {"title": "Design is not just what it looks like. Design is how it works.", "subtitle": "Attribution, Role"}, aligns=["left", "center"], accents=["none"]),
    "framed": _layout(_framed, "Double-ruled border framing a centered, formal composition.", ["enclosure and containment", "symmetry", "formality through restraint"], ["certificates", "invitations", "menus", "print"], {"label": "Certificate of achievement", "title": "Recipient Name", "subtitle": "In recognition of outstanding work", "body": "Presented on the first of June", "caption": "Signature · Date"}, accents=["none"]),
    "diagonal-band": _layout(_diagonal_band, "A rotated color band adds motion; text aligns around it.", ["diagonal energy", "dynamic tension", "color band as anchor"], ["sports", "sales", "social", "poster"], {**COPY, "subtitle": "Up to 40% off this week"}),
    "typographic-poster": _layout(_typographic_poster, "One oversized word bleeds off the edge behind the message.", ["type as image", "intentional cropping", "extreme scale contrast"], ["poster", "social", "covers"], {"title": "Bold ideas for the next decade", "subtitle": "A one-day festival of design and technology.", "label": "Vol. 3", "caption": "June 14 · City Hall"}, dramatic=True),
    "product-card": _layout(_product_card, "Image, name, description, price and button with consistent padding.", ["proximity grouping", "price emphasis", "clear call to action"], ["ecommerce", "social", "ads"], {"label": "New", "title": "Product name", "body": "One or two lines describing the benefit, not the specification.", "caption": "$49", "cta": "Shop now"}, button="rounded"),
    "event-poster": _layout(_event_poster, "Headline, prominent date block and stacked details for events.", ["information hierarchy", "chunking details", "color-coded key fact"], ["poster", "social", "flyers"], {"title": "Summer Night Market", "label": "Sat · June 21", "body": "6 pm – 11 pm\nRiverside Park, Pier 4\nFree entry · Food · Live music", "cta": "RSVP", "caption": "example.com/market"}),
    "banner": _layout(_banner, "Wide format: message left, call to action right, vertically centered.", ["horizontal reading flow", "single line hierarchy", "CTA in terminal area"], ["ads", "web", "email", "social headers"], {"title": "Your offer in one line", "subtitle": "A short supporting detail", "cta": "Get started"}),
    "letterhead": _layout(_letterhead, "Letterhead with mark, name, contact block, rules and footer.", ["identity consistency", "margins for content", "quiet hierarchy"], ["stationery", "print"], {"title": "Studio Name", "subtitle": "hello@example.com | +1 555 0100 | example.com", "caption": "123 Example Street · City · Country"}, accents=["none"]),
    "business-card": _layout(_business_card, "Name, role and contact with a mark and edge accent.", ["proximity", "alignment to one edge", "contrast of name and details"], ["stationery"], {"title": "Alex Morgan", "subtitle": "Creative Director", "body": "alex@example.com | +1 555 0100 | example.com"}, accents=["none"]),
    "slide-title": _layout(_slide_title, "Presentation title slide with accent bar, subtitle and footer.", ["left-edge alignment", "scale hierarchy", "consistent footer"], ["slides"], {"title": "Presentation title", "subtitle": "Subtitle or speaker name", "caption": "Company · 2025"}, accents=["none"]),
    "slide-content": _layout(_slide_content, "Heading, bullet points and optional image for content slides.", ["one idea per slide", "parallel bullets", "image–text balance"], ["slides"], {"title": "Slide heading", "items": "First key point\nSecond key point\nThird key point", "caption": "1"}),
    "logo-horizontal": _layout(_logo_horizontal, "Mark beside wordmark with proportional clear space and optional tagline.", ["clear space", "optical alignment", "scalable simplicity"], ["logos"], {"title": "Brand", "subtitle": ""}, accents=["none"]),
    "logo-stacked": _layout(_logo_stacked, "Mark centered above the wordmark and tagline.", ["symmetry", "clear space", "scalable simplicity"], ["logos", "icons"], {"title": "Brand", "subtitle": ""}, accents=["none"]),
    "emblem": _layout(_emblem, "Circular badge with name on an arc and initials at the center.", ["containment", "radial symmetry", "legibility at small sizes"], ["logos", "badges", "stickers"], {"title": "Brand Name", "subtitle": "Est. 2025"}, accents=["none"]),
    "monogram": _layout(_monogram, "Initials inside a geometric container.", ["reduction", "geometric construction", "small-size legibility"], ["logos", "icons", "favicons"], {"title": "Brand Name"}, accents=["none"]),
    "app-icon": _layout(_app_icon, "Rounded icon tile with gradient and a glyph inside the keyline.", ["keyline grid", "single recognizable glyph", "contrast at small sizes"], ["icons", "favicons"], {"title": "App"}, accents=["none"]),
    "thumbnail-bold": _layout(_thumbnail_bold, "Few huge words with outline beside a subject image; built for small sizes.", ["legibility at thumbnail size", "high contrast", "face/subject plus words"], ["youtube", "social", "covers"], {"title": "Huge three words", "label": "NEW"}, dramatic=True, button="rounded"),
    "story-vertical": _layout(_story_vertical, "Vertical story respecting top and bottom UI safe zones.", ["safe zones", "top-down reading", "thumb-reach call to action"], ["stories", "reels", "tiktok"], COPY, aligns=["left", "center"]),
    "price-list": _layout(_price_list, "Menu or price list with aligned columns and separators.", ["tabular alignment", "consistent row rhythm", "right-aligned figures"], ["menus", "price lists", "print"], {"title": "Menu", "subtitle": "Seasonal dishes", "items": "Soup of the day | $8\nGarden salad | $10\nGrilled fish | $22\nLemon tart | $7"}, aligns=["left", "center"]),
    "photo-caption": _layout(_photo_caption, "Full-bleed image with a gradient scrim keeping caption text legible.", ["figure first", "scrim for contrast", "caption hierarchy"], ["social", "web", "covers"], {"label": "Travel", "title": "A caption headline over the photo", "subtitle": "Keep text on the scrim, never on busy image areas."}),
    "minimal-mark": _layout(_minimal_mark, "Small text in a corner with vast negative space and one accent dot.", ["negative space", "restraint", "deliberate placement"], ["poster", "social", "covers"], {"title": "Less, but better", "subtitle": "A quiet line of context."}, accents=["none"]),
    "bento-grid": _layout(_bento_grid, "Rounded tiles of varied spans: message, stat, image and info.", ["modular tiles", "varied emphasis by span", "consistent gutters"], ["web", "social", "slides", "infographics"], {"title": "Everything in one place", "label": "3×", "caption": "faster setup", "subtitle": "Short supporting copy in its own tile.", "cta": "Try it"}, accents=["none"]),
    "meme-top-bottom": _layout(_meme_top_bottom, "Classic meme: full-bleed picture with stroked uppercase top and bottom text.", ["text over image with a stroke for contrast", "setup and punchline", "few words, huge type"], ["memes", "social"], {"title": "When the build passes", "caption": "On the first try"}, accents=["none"]),
    "meme-caption-above": _layout(_meme_caption_above, "Caption in a white band above the picture.", ["caption first, then image", "plain text on white", "image carries the joke"], ["memes", "social"], {"title": "Me explaining why the meeting could have been an email"}, accents=["none"]),
    "meme-comparison": _layout(_meme_comparison, "Two-row comparison: a reaction image beside each labelled option.", ["contrast of two choices", "image–label pairs", "reading order top to bottom"], ["memes", "social"], {"items": "Writing docs by hand\nGenerating them from the schema"}, accents=["none"]),
    "meme-labelled": _layout(_meme_labelled, "Picture with stroked labels for the objects in it.", ["labels as metaphor", "short labels", "label on its object"], ["memes", "social"], {"items": "Me\nNew framework\nWorking code"}, accents=["none"]),
    "meme-reaction": _layout(_meme_reaction, "Reaction frame (GIF-ready): picture over a black subtitle bar.", ["one reaction", "subtitle-style caption", "loops cleanly"], ["memes", "gifs", "social"], {"caption": "Me reading my own code from last year"}, accents=["none"]),
    "meme-four-panel": _layout(_meme_four_panel, "Four panels in a 2×2 grid, each with a stroked caption.", ["sequence in reading order", "escalation across panels", "one caption per panel"], ["memes", "comics", "social"], {"items": "Idea\nPrototype\nScope creep\nRewrite"}, accents=["none"]),
}


def _safe_composition(b):
    """Fifteen restrained systems: varied alignment, measure, position and quiet framing."""
    b.background()
    fraction, vertical, alignment, device = b.layout["safe_composition"]
    b.align = b.op.get("align", alignment)
    width = b.cw * (max(fraction, 0.82) if b.orientation in ("portrait", "tall") else fraction)
    x = b.L if b.align == "left" else b.R - width if b.align == "right" else b.L + (b.cw - width) / 2
    entries = [("caption", b.label_text(), "label"), ("headline", b.get("title"), "headline"),
               ("lead", b.get("subtitle"), "subtitle"), ("body", b.get("body"), "body"),
               ("button", b.get("cta"), "cta"), ("caption", b.get("caption"), "caption")]
    height = b.stack_height(entries, width, gap=b.unit * 2)
    y = b.T + max(0, b.ch - height) * vertical
    if device == "rule":
        b.rect("quiet-rule", b.L, b.T, b.cw, max(2, b.unit / 4), "@accent")
    elif device == "rail":
        b.rect("quiet-rail", b.L / 2, b.T, max(2, b.unit / 4), b.ch, "@accent")
    elif device == "panel":
        b.rect("quiet-panel", b.L / 2, b.T / 2, b.W - b.L, b.H - b.T, "@surface", radius=b.unit)
    elif device == "footer":
        b.rect("quiet-footer", b.L, b.B - b.unit / 4, b.cw, max(2, b.unit / 4), "@accent")
    if not (b.accent == "rule" and device == "rule"):
        # A chosen (or rolled) accent joins the composition's own device; "none", the default, adds nothing.
        b.accent_device(x, y, width, height)
    b.stack(entries, x, y, width, gap=b.unit * 2, align=b.align)


SAFE_COMPOSITIONS = {
    "quiet-editorial": (0.72, 0.20, "left", "rule"),
    "offset-column": (0.70, 0.45, "right", "rail"),
    "centered-note": (0.76, 0.42, "center", "none"),
    "open-letter": (0.84, 0.18, "left", "footer"),
    "gallery-label": (0.65, 0.78, "left", "none"),
    "soft-panel": (0.78, 0.45, "center", "panel"),
    "modern-bulletin": (0.92, 0.12, "left", "rule"),
    "balanced-announcement": (0.82, 0.32, "center", "footer"),
    "right-margin": (0.67, 0.26, "right", "none"),
    "calm-cover": (0.76, 0.62, "left", "rail"),
    "centered-rule": (0.84, 0.50, "center", "rule"),
    "inset-editorial": (0.69, 0.28, "left", "panel"),
    "wide-statement": (0.96, 0.42, "left", "none"),
    "quiet-invitation": (0.68, 0.28, "center", "footer"),
    "asymmetric-note": (0.74, 0.68, "right", "rule"),
}
for _name, _composition in SAFE_COMPOSITIONS.items():
    LAYOUTS[_name] = _layout(_safe_composition, f"Restrained {_name.replace('-', ' ')} with a clear message and measured spacing.",
                            ["readable hierarchy", "measured whitespace", "restrained decoration"],
                            ["poster", "social", "web", "slides", "print"], COPY,
                            safe=True, safe_composition=_composition, aligns=[_composition[2]], accents=["none"])
for _name, _layout_entry in LAYOUTS.items():
    _layout_entry.setdefault("safe", False)


IMAGE_OPTIONS = [
    {"option": "import", "how": "vixl_import_image(path='photo.png') returns an asset id; then re-apply this layout with "
     "image=<asset>, replace=true and the same seed, or run {type: replace-contents, target: <image layer>, asset: <asset>} "
     "and remove the temporary layer"},
    {"option": "resource", "how": "A saved shape or container: vixl_workflow(action='resource-list', request={kind: 'shapes'}) "
     "then {type: shape-place, resource: NAME, x, y, width, height} inside the slot"},
    {"option": "draw", "how": "Build it from shape, pen, pathfinder, organic (flowers, trees, shells …) and paint operations "
     "inside the slot's bounds, group them, and remove the placeholder; {type: rasterize} on the group gives an asset for replace-contents"},
    {"option": "ai", "how": "vixl_ai_generate(prompt=…, width, height) (needs a configured provider: vixl_models_list), then "
     "replace-contents with the generated layer's asset"},
]


def next_steps(project):
    """What to do about the layout's unfilled slots, with the image slot's bounds and every way to fill it."""
    from .render import resolve_layout

    record = project.state.get("layout") or {}
    blanks = record.get("blanks", [])
    if not blanks:
        return []
    steps = []
    text = list(dict.fromkeys(b["slot"] for b in blanks if b["slot"] not in IMAGE_KEYS))
    if text:
        steps.append({"slot": text, "action": "fill",
                      "how": f"Re-apply layout-apply with name={record.get('name')!r}, seed={record.get('seed')}, replace=true "
                             f"and the copy for: {', '.join(text)}"})
    images = [b for b in blanks if b["slot"] in IMAGE_KEYS]
    bounds = resolve_layout(project) if images else {}
    for blank in images:
        layer = next((x for x in project.state["layers"] if x["name"] == blank["layer"]), None)
        if layer is None:
            continue
        x, y, w, h = bounds[layer["id"]]
        steps.append({"slot": blank["slot"], "layer": layer["name"], "bounds": [x, y, w, h], "aspect_ratio": round(w / max(h, 1), 3),
                      "action": "fill", "options": IMAGE_OPTIONS,
                      "note": "The placeholder is an editable frame; check reports it as an unfilled blank until it is replaced"})
    return steps


def describe(name):
    """Full form for one layout: each slot's label, hint, example and whether it becomes a blank."""
    item = LAYOUTS[name]
    spec = slot_spec(item)
    extra = sorted(set(OPTIONAL_READS.get(name, ())) - set(spec))
    return {
        "description": item["description"],
        "safe": item.get("safe", False),
        "principles": item["principles"],
        "best_for": item["best_for"],
        "slots": {
            k: {"label": v["label"], "hint": v["hint"], "blank_if_unfilled": v["blank"], **({"example": v["example"]} if "example" in v else {}),
                **({"fill_with": IMAGE_OPTIONS} if k in IMAGE_KEYS else {})}
            for k, v in spec.items()
        },
        **({"also_accepts": extra} if extra else {}),
    }


def catalog():
    return {
        "layouts": {
            name: {
                "description": item["description"],
                "safe": item.get("safe", False),
                "best_for": item["best_for"],
                "slots": {k: v["label"] for k, v in slot_spec(item).items()},
            }
            for name, item in LAYOUTS.items()
        },
        "detail": "vixl layout show NAME (vixl_layouts_list name=…) gives principles and each slot's meaning",
        "options": {
            "seed": "Integer or 'random'; omitted seeds are fresh unless document/workspace variety is fixed. "
            "Unspecified palette, mode, type scale, density, alignment and accent are rolled from the seed",
            "unfilled": "blank (default): unfilled slots render as visible [Label] placeholders recorded as blanks that "
            "check reports as errors; omit: leave unfilled slots out (vixl_roll apply omits them when given "
            "slots); the layout record's omitted lists what was left out",
            "font": "Registered body font; defaults to the document typography (font pair), else the proofing fallback",
            "display_font": "Registered heading font; defaults to the document typography heading, else font",
            "palette": "Palette name or list of colors (roles are assigned with contrast checks)",
            "colors": "Override roles: background, surface, ink, muted, accent, accent-text, on-accent",
            "mode": "inherit (default), light or dark",
            "type_scale": "Ratio name (" + ", ".join(RATIOS) + ") or number",
            "density": "airy, balanced or dense (margins and scale)",
            "align": "left, center or right where the layout allows",
            "accent": ", ".join(ACCENTS),
            "content": "Slots differ per layout; see slots. Supplying a slot the layout does not use is an error",
            "prefix": "Prefix for created layer names",
            "replace": "Remove layers created by the previous layout first",
        },
    }


def _seed(op, canvas):
    if op.get("seed") == "random":
        return secrets.randbelow(2**32)
    if "seed" in op:
        require(isinstance(op["seed"], int) and 0 <= op["seed"] < 2**32, "seed must be a nonnegative 32-bit integer or 'random'")
        return op["seed"]
    return secrets.randbelow(2**32)


def execute_layout(project, op):
    from .operations import execute

    state = project.state
    if op["type"] == "type-scale":
        ratio = op.get("ratio", "perfect-fourth")
        value = RATIOS.get(ratio, ratio) if isinstance(ratio, str) else ratio
        require(isinstance(value, (int, float)) and 1.05 <= value <= 2, "ratio must be a scale name or 1.05–2")
        base = op.get("base", 16)
        require(isinstance(base, (int, float)) and 4 <= base <= 1000, "base must be 4–1000 pixels")
        prefix = op.get("prefix", "")
        for role, step in ROLE_STEPS.items():
            settings = {"size": max(6, round(base * value**step))}
            if op.get("color"):
                settings["color"] = op["color"]
            execute(project, {"type": "style-define", "name": f"{prefix}{role}", "kind": "character", "settings": settings})
        return
    op = deepcopy(op)
    explicit_palette = "palette" in op or "colors" in op
    from .variety import seed_for
    from .brand import for_project

    defaults = state.get("design_defaults", {})
    if "seed" not in op:
        # A sparse apply takes the document's whole stored direction, as vixl_roll(apply=true) does;
        # explicit fields win key by key, and an explicit seed asks for a fresh choice instead.
        direction = defaults.get("direction", {})
        op["seed"], _ = seed_for(project, direction.get("layout_seed", defaults.get("seed")), op.get("variety"))
        for key, value in direction.items():
            if key in DIRECTION_OPTIONS:
                op.setdefault(key, deepcopy(value))
        inherited = {key: deepcopy(value) for key, value in direction.items() if key not in DIRECTION_SKIP}
        if inherited:
            op["direction"] = {**inherited, **op.get("direction", {})}
    kit = for_project(project)
    if kit.get("palette") and not explicit_palette:
        op["colors"] = kit["palette"]
    if op.get("mode", "inherit") == "inherit":
        from .render import color
        rgba = color(state["canvas"].get("background", "transparent"))
        if rgba[3]:
            op["mode"] = "dark" if sum(v * w for v, w in zip(rgba[:3], (0.2126, 0.7152, 0.0722))) < 128 else "light"
            op["_mode_source"] = "inherited from the canvas background"
        else:
            op.pop("mode", None)
    if op.get("predictable"):
        for key, value in {"align": "left", "density": "balanced", "type_scale": "perfect-fourth", "accent": "rule"}.items():
            op.setdefault(key, value)
    name = op["name"]
    if name not in LAYOUTS:
        import difflib

        close = difflib.get_close_matches(name, list(LAYOUTS), 3, 0.5)
        raise VixlError("unknown_layout", f"Unknown layout {name!r}" + (f"; did you mean {', '.join(close)}?" if close else
                        "; the layouts are listed under allowed (vixl layout list)"), field="name", suggestions=close,
                        allowed=sorted(LAYOUTS))
    layout = LAYOUTS[name]
    if op.get("replace") and state.get("layout"):
        previous = set(state["layout"].get("layers", []))
        doomed = [layer["id"] for layer in state["layers"] if layer["id"] in previous]
        for ident in doomed:
            if any(layer["id"] == ident for layer in state["layers"]):
                execute(project, {"type": "remove", "target": ident})
            state.get("blanks", {}).pop(ident, None)
    seed = _seed(op, state["canvas"])
    snapshot = project.clone()
    fit = 1.0
    for attempt in range(6):
        # Build on a copy; if text would leave the canvas, rebuild with a smaller type scale so the
        # same composition fits small formats (business cards, banners) instead of overflowing.
        trial = snapshot.clone()
        trial._resource_budget = getattr(project, "_resource_budget", project.limits.max_operations)
        builder = _build(trial, layout, op, seed, fit)
        if "base_size" in op or attempt == 5 or not _overflows(trial, builder):
            break
        fit *= 0.84
    supplied = [k for k in CONTENT_KEYS if k in op]
    unused = [k for k in supplied if k not in builder.read]
    if unused:
        used = [k for k in CONTENT_KEYS if k in builder.read]
        raise VixlError(
            "unused_slot",
            f"Layout {name!r} does not use {', '.join(map(repr, unused))} on this canvas, so that copy would be "
            f"silently dropped. It uses: {', '.join(used)}. Move the copy into one of those slots or choose "
            "another layout (vixl layout show NAME lists each slot's meaning).",
            field=unused[0],
            suggestions=used,
        )
    project.state, project.assets = trial.state, trial.assets
    project._resource_budget = trial._resource_budget
    state = project.state
    created = [layer["id"] for layer in state["layers"] if layer["name"] in set(builder.created)]
    blanks = _record_blanks(state, builder, name, created)
    rolled = [
        key
        for key, value, option in (
            ("palette", builder.colors["_palette"], "palette"),
            ("mode", builder.colors["_mode"], "mode"),
            ("type_scale", builder.ratio_name, "type_scale"),
            ("density", builder.density, "density"),
            ("align", builder.align, "align"),
            ("accent", builder.accent, "accent"),
        )
        if option not in op and not (option == "palette" and "colors" in op and len(op["colors"]) >= 3)
    ]
    fonts = {"heading": builder.display_font, "body": builder.font} if builder.font or builder.display_font else None
    state["layout"] = {
        "name": name,
        "seed": seed,
        "palette": builder.colors["_palette"],
        "mode": builder.colors["_mode"],
        "mode_source": builder.colors["_mode_source"],
        "roles": builder.colors["_explain"],
        "type_scale": builder.ratio_name,
        "base_size": round(builder.base, 2),
        "density": builder.density,
        "margin": builder.m,
        "align": builder.align,
        "accent": builder.accent,
        "contrast": builder.contrast,
        "principles": layout["principles"],
        "fonts": fonts or "fallback",
        "rolled": rolled,
        "layers": created,
        **({"direction": deepcopy(op["direction"])} if op.get("direction") else {}),
    }
    notes = []
    if blanks:
        notes.append(
            f"Fill the blank slots ({', '.join(dict.fromkeys(b['slot'] for b in blanks))}; see blanks for what each needs), "
            f"then re-apply with the copy, replace=true and seed={seed} to keep this composition. "
            "check reports unfilled blanks as errors; unfilled='omit' leaves optional copy out instead."
        )
        state["layout"]["blanks"] = blanks
    if builder.omitted:
        state["layout"]["omitted"] = builder.omitted
        notes.append(
            f"Left out unfilled slots ({', '.join(builder.omitted)}): the composition is laid out around the copy "
            f"it has, so supplying them later (replace=true, seed={seed}) re-lays it out; unfilled='blank' keeps "
            "[Label] placeholders that check rejects until filled."
        )
    if not fonts:
        from .variety import font_next_step

        state["layout"]["font_choice"] = font_next_step(project, seed)
        notes.append(
            "No fonts were chosen, so text uses the bundled fallback font, which is for proofing only. Choose a "
            "pairing (vixl font pairings, or vixl font pair random) or pass font/display_font."
        )
    if len(rolled) >= 4:
        notes.append(
            f"Few design parameters were given, so seed {seed} chose {', '.join(sorted(rolled))}. Treat this as one "
            "roll of the dice: try seed='random' (or vixl roll) a few times, compare previews, and keep the seed you like."
        )
    if isinstance(op.get("palette"), list):
        notes.extend(builder.colors["_notes"])
    if fit < 1:
        notes.append(
            f"Type was reduced to {fit:.0%} of the medium's scale to fit this canvas; "
            "shorten the copy or choose a larger size or a layout made for this format."
        )
    if notes:
        state["layout"]["notes"] = notes


def _record_blanks(state, builder, layout_name, created):
    """Register placeholder layers in ``state['blanks']`` so checks can refuse to ship them."""
    registry = state.setdefault("blanks", {})
    by_name = {layer["name"]: layer for layer in state["layers"] if layer["id"] in set(created)}
    # Layouts split some slots (one detail per line, "item | price"), so match each bracketed token.
    markers = {slot: {t.lower() for t in re.findall(r"\[[^\]]+\]", placeholder)} for slot, placeholder in builder.placeholders.items()}
    found = []
    for layer in by_name.values():
        if layer["type"] != "text":
            continue
        text = layer["text"].lower()
        bare = re.sub(r"[\[\]]", "", text).strip()
        for slot, lines in markers.items():
            if any(token in text or bare == token[1:-1] for token in lines):
                spec = builder.slots[slot]
                registry[layer["id"]] = {"slot": slot, "text": layer["text"], "hint": spec["hint"], "source": f"layout:{layout_name}"}
                found.append({"slot": slot, "layer": layer["name"], "hint": spec["hint"]})
                break
    for name in builder.image_blanks:
        layer = by_name.get(name)
        if layer:
            slot = builder.blank_slots.get(name, "image")
            registry[layer["id"]] = {"slot": slot, "asset": layer["asset"], "hint": SLOT_TEXT[slot][1], "source": f"layout:{layout_name}"}
            found.append({"slot": slot, "layer": name, "hint": f"pass {slot}=" + ("ASSET_ID" if slot == "image" else "[ASSET_ID, …]")
                          + ", or fill the frame later (see next_steps)"})
    return found


def _build(project, layout, op, seed, fit):
    from .normalize import apply_centering, resolve_geometry
    from .operations import execute
    from .schema import validate_operation

    state = project.state
    builder = Builder(project, layout, deepcopy(op), seed, fit)
    # Swatches and a type scale first, so every created layer references them.
    for role in ROLES:
        execute(project, {"type": "swatch", "name": role, "color": builder.colors[role]})
    execute(project, {"type": "type-scale", "base": round(builder.base, 2), "ratio": builder.ratio})
    layout["build"](builder)
    existing = {layer["name"] for layer in state["layers"]}
    clashes = sorted(set(builder.created) & existing)
    require(not clashes, f"Layer names already exist ({', '.join(clashes[:5])}); pass prefix or replace=true", "name_conflict")
    remaining = project._resource_budget - len(builder.ops) + 1
    require(remaining >= 0, "Layout exceeds the operation limit", "resource_limit")
    project._resource_budget = remaining
    for operation in builder.ops:
        operation = validate_operation(operation)
        resolved, centered = resolve_geometry(project, operation)
        execute(project, resolved)
        apply_centering(project, centered, operation)
    if op.get("direction"):
        from .variety import apply_direction

        apply_direction(project, builder, op["direction"])
    # Decoration a layout lets run off the canvas (a corner block, a counterweight) is a drawn bleed:
    # mark it so checks report it as informational instead of cut-off content.
    from .render import resolve_layout

    canvas = state["canvas"]
    bounds = resolve_layout(project)
    for layer in state["layers"]:
        if layer["name"] in set(builder.created) and layer["type"] != "text":
            x, y, w, h = bounds[layer["id"]]
            if x < 0 or y < 0 or x + w > canvas["width"] or y + h > canvas["height"]:
                layer["allow_crop"] = True
    return builder


def _overflows(project, builder):
    from .render import resolve_layout

    c = project.state["canvas"]
    names = set(builder.created)
    bounds = resolve_layout(project)
    for layer in project.state["layers"]:
        if layer["name"] in names and layer["type"] == "text":
            x, y, w, h = bounds[layer["id"]]
            if x < -1 or y < -1 or x + w > c["width"] + 1 or y + h > c["height"] + 1:
                return True
    return False


def validate_layout_record(state):
    record = state.get("layout")
    if record is None:
        return
    require(isinstance(record, dict) and isinstance(record.get("layers", []), list), "Invalid layout record", "invalid_project")
    require(record.get("name") in LAYOUTS, "Invalid layout record", "invalid_project")


def schemas(add):
    from .schema import S, N, B

    add(
        "layout-apply",
        {
            "name": S,
            "seed": {"type": ["integer", "string"]},
            "variety": {"enum": ["low", "medium", "high", "fixed"], "description": "Sparse-choice range; fixed defaults to seed 0 or the workspace seed."},
            "direction": {"type": "object", "description": "Extra rolled choices: motif, look, style, margin, corner, background_treatment and color_assignment."},
            "unfilled": {
                "enum": ["blank", "omit"],
                "description": "blank (default): slots left unfilled show as [Label] placeholders that check "
                "rejects; omit: leave unfilled slots out, so the layout is final and passes check.",
            },
            "palette": {"type": ["string", "array"]},
            "colors": {"type": "object"},
            # Choice fields are validated (with the allowed values) when the layout is built.
            **{key: S for key in ("mode", "density", "align", "accent")},
            "type_scale": {"type": ["string", "number"]},
            "base_size": N,
            "mark": S,
            "font": S,
            "display_font": S,
            "transparent": B,
            "uppercase_labels": B,
            "prefix": S,
            "replace": B,
            "predictable": B,
            "keep_order": B,
            **{key: S for key in CONTENT_KEYS if key != "images"},
            "images": {"type": "array", "items": S, "maxItems": 8,
                       "description": "Multi-panel layouts (meme-comparison, meme-four-panel): one image asset id per panel."},
            "uppercase": {"type": "boolean", "description": "Meme layouts: set stroked captions uppercase (default true)."},
        },
        ["name"],
    )
    add("type-scale", {"base": N, "ratio": {"type": ["string", "number"]}, "prefix": S, "color": S})
