"""Vixl marketing kit: social cards, print, a pitch deck and a motion teaser, all made with Vixl.

Run from the repo root:

    python marketing/build.py            # build everything
    python marketing/build.py og deck    # build only some pieces

Every piece is written to marketing/output/<piece>/ as an editable .vixl master plus its exports.
The Digital Shift logo is imported from the identity's Vixl-generated SVGs as editable vector shapes.
"""

import csv
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "output"
os.environ.setdefault("VIXL_NO_UPDATE", "1")
os.chdir(ROOT)  # link sources resolve against the workspace (repo root)

from vixl import Project  # noqa: E402
from vixl.typefaces import install_font  # noqa: E402

# Brand (assets/brand/digital-shift/START-HERE.md) ----------------------------------------------
CHARCOAL = "#252B39"
DEEP = "#1A1F2B"
PANEL = "#2F3647"
LINE = "#3C4458"
BLUE = "#3575EE"
SKY = "#6A9AFF"
WHITE = "#FFFFFF"
MUTED = "#AEB7CA"
PAPER = "#F5F7FB"
INK = CHARCOAL
SUBTLE = "#5B6478"
CODE_KEY = "#8FB4FF"
CODE_STR = "#9FE3B4"
CODE_NUM = "#FFC37A"

LOGOS = "assets/brand/digital-shift/Editable-Vixl"
HEAD, BODY, SEMI, MONO = "inter-tight-800", "inter-400", "inter-600", "jetbrains-mono-500"


def registry_facts():
    """Count the installed engine, so rebuilding cannot silently retain old numbers."""
    from vixl.operations import OPERATION_TYPES
    from vixl.sizes import SIZES
    from vixl.layouts import LAYOUTS
    from vixl.resources import TEMPLATES, CONTAINERS
    from vixl.style_catalog import STYLES
    from vixl.looks import LOOKS
    from vixl.brushes import BRUSHES
    from vixl.model import Limits

    return dict(zip(("operations", "sizes", "layouts", "templates", "containers", "styles", "looks", "brushes"),
                    map(len, (OPERATION_TYPES, SIZES, LAYOUTS, TEMPLATES, CONTAINERS, STYLES, LOOKS, BRUSHES))),
                batch=f"{Limits().max_operations:,}")


FACTS = registry_facts()
INTERFACES = ["MCP", "CLI", "Python", "REST"]
SUB = "A programmable design studio for AI agents. Create, check and deliver layered designs through MCP, CLI, Python or REST."
REPO = "github.com/jxburros/Vixl"


# Helpers ---------------------------------------------------------------------------------------
def new(width, height, background=CHARCOAL, **kw):
    p = Project(width, height, background, **kw)
    p._workspace = str(ROOT)  # image and brand sources resolve against the repo root
    install_font(p, "Inter Tight", 800, role="heading")
    install_font(p, "Inter", 400, role="body")
    install_font(p, "Inter", 600)
    install_font(p, "JetBrains Mono", 500)
    p.apply([
        {"type": "swatch", "name": "brand", "color": BLUE},
        {"type": "swatch", "name": "sky", "color": SKY},
        {"type": "swatch", "name": "charcoal", "color": CHARCOAL},
        {"type": "suite-set", "name": "canvas", "suite": {"rules": [
            {"id": "width", "kind": "property", "target": "canvas", "field": "width", "expected": width},
            {"id": "height", "kind": "property", "target": "canvas", "field": "height", "expected": height},
        ]}},
    ], detail="brief")
    return p


def bounds(p, name):
    """The layer's box on the canvas, grouped or not (``space="parent"`` gives it in its group's coordinates)."""
    return p.bounds(name)


def logo(name, variant, x, y, width=None, height=None):
    """Import the Vixl identity's outlined SVG as portable editable vector geometry."""
    import xml.etree.ElementTree as ET
    from vixl.imports import svg_operations

    # Symbol/stacked masters contain a path extending 0.4 px beyond its local viewport.
    # Use the native geometry for these lockups, keeping Vixl's own clipping and path view.
    if variant.startswith(("mark-", "stacked-")):
        source = Project.load(ROOT / LOGOS / f"{variant}.vixl")
        c = source.state["canvas"]
        scale = min(width / c["width"] if width else float("inf"),
                    height / c["height"] if height else float("inf"))
        operations = []
        for i, layer in enumerate(source.state["layers"]):
            keys = ("shape", "path", "fill", "stroke", "stroke_width", "x", "y", "width", "height")
            if layer["type"] == "text":
                keys = ("text", "x", "y", "size", "color", "spacing", "align")
            operation = {"type": layer["type"], "name": f"{name}-part-{i}",
                         **{key: layer[key] for key in keys if key in layer}}
            if layer["type"] == "text":
                operation["font"] = HEAD
            operations.append(operation)
        left = min(layer["x"] for layer in source.state["layers"])
        top = min(layer["y"] for layer in source.state["layers"])
        operations.extend([
            {"type": "group", "name": name, "targets": [op["name"] for op in operations]},
            {"type": "scale", "target": name, "value": scale, "anchor": [0, 0]},
            {"type": "move", "target": name, "x": x + left * scale, "y": y + top * scale},
        ])
        return operations
    root = ET.fromstring((ROOT / "assets/brand/digital-shift/SVG" / f"{variant}.svg").read_bytes())
    sw, sh = float(root.get("width")), float(root.get("height"))
    scale = min(width / sw if width else float("inf"), height / sh if height else float("inf"))
    root.set("width", str(sw * scale))
    root.set("height", str(sh * scale))
    operations = svg_operations(ET.tostring(root), Project(100, 100), name)
    for operation in operations:
        operation["x"] += x
        operation["y"] += y
    operations.append({"type": "group", "name": name, "targets": [op["name"] for op in operations]})
    return operations




def pixel_stair(prefix, x, y, cell, gap, steps, color=BLUE, fade=True):
    """A diagonal run of pixels that echoes the offset V shapes of the mark."""
    ops = []
    for i in range(steps):
        alpha = 255 - int(i * (200 / max(1, steps - 1))) if fade else 255
        ops.append({"type": "shape", "shape": "rectangle", "name": f"{prefix}-{i}",
                    "x": x + i * (cell + gap), "y": y + i * (cell + gap) // 2,
                    "width": cell, "height": cell, "fill": f"{color}{alpha:02X}"})
    return ops




def chip(p, name, text, x, y, size=22, fg=WHITE, bg=PANEL, stroke=None, pad=(18, 10), font=SEMI,
         radius=None):
    """Pill label: text first (to measure its ink box), then a capsule centred behind it."""
    p.apply({"type": "text", "name": f"{name}-label", "text": text, "font": font, "size": size,
             "color": fg, "x": x + pad[0], "y": y}, detail="brief")
    _, ly, lw, _ = bounds(p, f"{name}-label")
    cap = size * 0.72  # cap height of Inter: centre on it so descenders do not push the label up
    w, h = round(lw + 2 * pad[0]), round(cap + 2 * pad[1] + size * 0.3)
    bg_op = {"type": "shape", "shape": "rounded-rectangle", "name": f"{name}-bg", "x": x, "y": y,
             "width": w, "height": h, "radius": radius if radius is not None else h / 2, "fill": bg}
    if stroke:
        bg_op.update(stroke=stroke, stroke_width=2)
    top_gap = ly - y  # distance from the text box top to its ink top
    p.apply([bg_op,
             {"type": "move", "target": f"{name}-label", "x": x + pad[0], "y": y + (h - cap) / 2 - top_gap},
             {"type": "lower", "target": f"{name}-bg"},
             {"type": "group", "name": name, "targets": [f"{name}-bg", f"{name}-label"]}], detail="brief")
    return x, y, w, h


def chips_row(p, prefix, labels, x, y, gap=12, **kw):
    cx = x
    boxes = []
    for i, label in enumerate(labels):
        box = chip(p, f"{prefix}-{i}", label, cx, y, **kw)
        boxes.append(box)
        cx += box[2] + gap
    return boxes


def code_card(name, x, y, width, lines, size=22, title="design.json", height=None, chrome=True):
    """A dark editor window holding syntax-coloured lines; each line is (indent level, [(text, color)])."""
    top = 58 if chrome else 28
    line = size * 1.5
    h = height or round(top + 30 + line * len(lines))
    ops = [
        {"type": "shape", "shape": "rounded-rectangle", "name": f"{name}-bg", "x": x, "y": y,
         "width": width, "height": h, "radius": 18, "fill": DEEP, "stroke": LINE, "stroke_width": 2},
    ]
    if chrome:
        for i, c in enumerate(["#FF6B6B", "#FFC37A", "#5FD38D"]):
            ops.append({"type": "shape", "shape": "ellipse", "name": f"{name}-dot{i}", "x": x + 24 + i * 22,
                        "y": y + 22, "width": 12, "height": 12, "fill": c})
        ops.append({"type": "text", "name": f"{name}-title", "text": title, "font": MONO, "size": max(20, round(size * 0.8)),
                    "color": MUTED, "x": x + 100, "y": y + 18})
    spans, paragraphs = [], []
    for i, (indent, runs) in enumerate(lines):
        spans.extend({"text": text, "color": color} for text, color in runs)
        if i < len(lines) - 1:
            spans.append({"text": "\n"})
        paragraphs.append({"indent": round(indent * 2 * size * 0.6)})
    ops.append({"type": "rich-text", "name": f"{name}-code", "spans": spans, "paragraphs": paragraphs,
                "font": MONO, "size": size, "color": WHITE, "line_height": 1.25, "x": x + 28, "y": y + top + 6,
                "width": width - 56})
    ops.append({"type": "group", "name": name, "targets": [o["name"] for o in ops]})
    return ops


def op_line(indent, key, value, color, last=False):
    return (indent, [(f'"{key}"', CODE_KEY), (": ", WHITE), (value, color), ("" if last else ",", WHITE)])


SNIPPET = [
    (0, [("[", WHITE)]),
    (1, [("{", WHITE)]),
    op_line(2, "type", '"layout-apply"', CODE_STR),
    op_line(2, "name", '"hero-statement"', CODE_STR),
    op_line(2, "title", '"Launch day"', CODE_STR),
    op_line(2, "seed", "7", CODE_NUM, last=True),
    (1, [("},", WHITE)]),
    (1, [("{", WHITE), ('"type"', CODE_KEY), (": ", WHITE), ('"look"', CODE_STR), (", ", WHITE),
         ('"look"', CODE_KEY), (": ", WHITE), ('"glow"', CODE_STR), ("}", WHITE)]),
    (0, [("]", WHITE)]),
]


def save_and_export(p, folder, stem, exports, check=True, **check_options):
    folder = OUT / folder
    folder.mkdir(parents=True, exist_ok=True)
    report = {}
    if check:
        result = p.check(**check_options)
        report = result
        fixes = [i for i in report["issues"] if i["action"] == "fix"]
        print(f"  check {stem}: {len(report['issues'])} issues, {len(fixes)} to fix")
        for issue in report["issues"]:
            print("   ", issue["action"].upper(), issue["check"], (issue["message"] or "")[:150])
        report["suites"] = {name: p.check_suite(name) for name in p.state.get("suites", {})}
        if not all(suite["passed"] for suite in report["suites"].values()):
            raise RuntimeError(f"Saved suite failed: {stem}")
        (folder / f"{stem}.check.json").write_text(json.dumps(report, indent=2) + "\n")
        if fixes:
            raise RuntimeError(f"Fix design findings before exporting {stem}")
    p.compact()
    p.save(str(folder / f"{stem}.vixl"), overwrite=True)
    for ext, options in exports:
        path = folder / f"{stem}.{ext}"
        p.export(str(path), overwrite=True, **options)
        print("  wrote", path.relative_to(ROOT))
    return report


def sheet(p, path, **options):
    from vixl.deck import contact_sheet

    contact_sheet(p, **options).convert("RGB").save(path)
    print("  wrote", Path(path).relative_to(ROOT))


# Layout helpers --------------------------------------------------------------------------------
def headline(name, text, x, y, size, accent=None, color=WHITE, width=None, align="left", line_height=0.92,
             accent_color=SKY):
    """Display type as rich text so the accent phrase can change colour and the leading stays tight."""
    spans = [{"text": text}]
    if accent and accent in text:
        before, after = text.split(accent, 1)
        spans = [s for s in ({"text": before}, {"text": accent, "color": accent_color}, {"text": after}) if s["text"]]
    op = {"type": "rich-text", "name": name, "spans": spans, "font": HEAD, "size": size, "color": color,
          "line_height": line_height, "align": align, "x": x, "y": y}
    if width:
        op["width"] = width
    return op




# Showcase: real outputs from the repo's explorations and docs, every one of them made with Vixl.
SHOW = {
    "poster": ("Print poster", "explorations/01-print-concert-poster/output/poster-rgb.png"),
    "painting": ("Generative painting", "explorations/05-generative-painting/output/painting.jpg"),
    "pixel": ("Pixel-art game", "explorations/04-pixel-rpg/output/title@4x-nearest.png"),
    "map": ("Tile maps", "explorations/04-pixel-rpg/output/map@3x.png"),
    "donut": ("Data infographic", "explorations/08-infographic/output/social-donut-1080.png"),
    "film": ("Character animation", "explorations/10-character-film/output/film-shot2.png"),
    "photo": ("Photo editing", "explorations/06-photo-lab/output/after.jpg"),
    "campaign": ("Brand campaign", "explorations/09-collab-campaign/output/00-overview.png"),
    "chart": ("Editable charts", "docs/assets/generated/chart.png"),
    "watercolor": ("Artistic filters", "explorations/05-generative-painting/output/variant-watercolor.jpg"),
}


def photo(name, key, x, y, w, h, radius=18, base=PANEL):
    """A showcase image cropped into a rounded frame (frame + clip, both editable)."""
    return [
        {"type": "shape", "shape": "rounded-rectangle", "name": f"{name}-base", "x": x, "y": y,
         "width": w, "height": h, "radius": radius, "fill": base},
        {"type": "frame", "name": name, "path": SHOW[key][1], "x": x, "y": y, "width": w, "height": h,
         "fit": "fill", "downsample": "placed@2x"},
        {"type": "clip", "target": name, "base": f"{name}-base"},
    ]


def fit_code(p, name, pad=30):
    """Grow a code card's background to the measured height of its code."""
    _, by, _, _ = bounds(p, f"{name}-bg")
    _, cy, _, ch = bounds(p, f"{name}-code")
    p.apply({"type": "resize", "target": f"{name}-bg", "height": round(cy + ch + pad - by)}, detail="brief")


def text(name, value, x, y, size, color=MUTED, font=BODY, **extra):
    return {"type": "text", "name": name, "text": value, "font": font, "size": size, "color": color, "x": x,
            "y": y, **extra}


def para(name, value, x, y, size, width, color=MUTED, font=BODY, line_height=1.3, align="left"):
    return {"type": "rich-text", "name": name, "spans": [{"text": value}], "font": font, "size": size,
            "color": color, "line_height": line_height, "x": x, "y": y, "width": width, "align": align}


def glow(name, x, y, size, color=BLUE, strength="55"):
    return {"type": "gradient", "name": name, "direction": "radial", "width": size, "height": size, "x": x, "y": y,
            "stops": [{"offset": 0, "color": f"{color}{strength}"}, {"offset": 0.6, "color": f"{color}10"},
                      {"offset": 1, "color": f"{color}00"}]}


LOOP = [("Inspect", "Read layers, bounds and fonts"), ("Apply", "Editable, atomic operations"),
        ("Check", "Design checks and saved suites"), ("Preview", "Render and review the work"),
        ("Export", "PNG, SVG, PDF, PPTX, MP4 ...")]

MAKES = ["Posters & social", "Charts & diagrams", "Slides & decks", "Fillable forms", "Motion & GIFs",
         "Pixel art & sprites", "Paintings & filters", "CMYK print PDFs"]


def loop_steps(p, prefix, x, y, width, size=30, vertical=False, dark=True, step_h=None):
    """The inspect -> apply -> check -> preview -> export loop as numbered cards."""
    fg, sub, card, num = (WHITE, MUTED, PANEL, SKY) if dark else (INK, SUBTLE, WHITE, "#2A62D6")
    n = len(LOOP)
    ops = []
    if vertical:
        h = step_h or round(size * 3.3)
        for i, (title, desc) in enumerate(LOOP):
            cy = y + i * (h + 18)
            ops += [
                {"type": "shape", "shape": "rounded-rectangle", "name": f"{prefix}-card{i}", "x": x, "y": cy,
                 "width": width, "height": h, "radius": 20, "fill": card,
                 **({} if dark else {"stroke": "#DCE2EE", "stroke_width": 2})},
                text(f"{prefix}-num{i}", f"0{i + 1}", x + 32, cy + h / 2 - size * 0.62, round(size * 1.1), num, HEAD),
                text(f"{prefix}-title{i}", title, x + 32 + size * 2.6, cy + h / 2 - size * 0.95, size, fg, HEAD),
                text(f"{prefix}-desc{i}", desc, x + 32 + size * 2.6, cy + h / 2 + size * 0.2, round(size * 0.62), sub),
            ]
    else:
        gap = 20
        w = (width - gap * (n - 1)) / n
        h = step_h or round(size * 4.2)
        for i, (title, desc) in enumerate(LOOP):
            cx = x + i * (w + gap)
            ops += [
                {"type": "shape", "shape": "rounded-rectangle", "name": f"{prefix}-card{i}", "x": round(cx), "y": y,
                 "width": round(w), "height": h, "radius": 18, "fill": card,
                 **({} if dark else {"stroke": "#DCE2EE", "stroke_width": 2})},
                text(f"{prefix}-num{i}", f"0{i + 1}", round(cx + 26), y + 24, round(size * 0.7), num, HEAD),
                text(f"{prefix}-title{i}", title, round(cx + 26), y + 24 + size * 1.1, size, fg, HEAD),
                para(f"{prefix}-desc{i}", desc, round(cx + 26), round(y + 24 + size * 2.5), round(size * 0.55),
                     round(w - 52), sub),
            ]
            if i < n - 1:
                ops.append({"type": "shape", "shape": "chevron", "name": f"{prefix}-arrow{i}",
                            "x": round(cx + w + gap / 2 - 6), "y": round(y + h / 2 - 9), "width": 12, "height": 18,
                            "fill": num})
    p.apply(ops, detail="brief")


# Pieces ---------------------------------------------------------------------------------------
def rect(name, x, y, width, height, fill=PANEL, radius=16):
    return {"type": "shape", "shape": "rounded-rectangle", "name": name,
            "x": x, "y": y, "width": width, "height": height, "radius": radius, "fill": fill}


def print_document(size, bleed=False, background=WHITE):
    p = new(100, 100, background)
    p.apply({"type": "canvas", "size": size, "dpi": 150, "bleed": bleed, "background": background})
    p.apply({"type": "suite-set", "name": "canvas", "suite": {"rules": [
        {"id": "width", "kind": "property", "target": "canvas", "field": "width", "expected": p.state["canvas"]["width"]},
        {"id": "height", "kind": "property", "target": "canvas", "field": "height", "expected": p.state["canvas"]["height"]},
    ]}})
    return p


def footer(p, y, margin, dark=True, size=24):
    w = p.state["canvas"]["width"]
    p.apply([*logo("footer-logo", "horizontal-reverse" if dark else "horizontal-color", margin, y - 10, width=170),
             text("footer-url", REPO, w - margin, y, size, MUTED if dark else SUBTLE, MONO)])
    _, _, tw, _ = bounds(p, "footer-url")
    p.apply({"type": "move", "target": "footer-url", "x": w - margin - tw, "y": y})


def chart_op(name, x, y, w, h, size=28):
    return {"type": "chart", "name": name, "kind": "stacked-bar", "x": x, "y": y, "width": w, "height": h,
            "categories": ["Brief", "Create", "Review", "Deliver"],
            "series": [{"name": "Graphics", "values": [2, 5, 3, 4], "color": BLUE},
                       {"name": "Documents", "values": [1, 3, 2, 3], "color": "#9CC6FA"}],
            "font_size": size, "label_font": BODY, "title_font": HEAD,
            "text_color": INK, "grid_color": "#DCE2EE", "legend": "bottom", "total_labels": True,
            "value_labels": False, "min": 0, "ticks": 4, "number_format": "0"}


def diagram_op(name, x, y, w, h, size=32):
    return {"type": "diagram", "name": name, "x": x, "y": y, "width": w, "height": h,
            "direction": "LR", "layout": "layered", "font": BODY, "size": size, "theme": "dark",
            "node_color": PANEL, "edge_color": SKY, "text_color": WHITE,
            "nodes": [{"id": "brief", "label": "Inspect"}, {"id": "edit", "label": "Apply"},
                      {"id": "check", "label": "Check", "kind": "decision"},
                      {"id": "preview", "label": "Preview"}, {"id": "export", "label": "Export"}],
            "edges": [["brief", "edit"], ["edit", "check"], ["check", "preview"], ["preview", "export"]]}


def build_showcase():
    """Native chart, native workflow diagram and a vector capability poster."""
    p = new(1200, 900, WHITE)
    p.apply([*logo("logo", "horizontal-color", 70, 40, width=220),
             text("kicker", "DATA THAT STAYS EDITABLE", 70, 175, 24, SUBTLE, MONO),
             headline("headline", "Keep the story.\nChange the data.", 70, 230, 78, "Change the data.", INK,
                      accent_color=BLUE),
             chart_op("campaign", 70, 450, 1060, 350, 25),
             text("source", "Illustrative workflow data · Native chart in PowerPoint · Made with Vixl", 70, 840, 20, SUBTLE)])
    save_and_export(p, "showcase", "editable-chart", [("png", {}), ("svg", {}), ("pptx", {})],
                    checks=["bounds", "flow", "contrast", "fonts"])
    p = new(1600, 900)
    p.apply([*logo("logo", "horizontal-reverse", 80, 45, width=220),
             text("kicker", "THE AGENT DESIGN WORKFLOW", 80, 180, 26, SKY, MONO),
             headline("headline", "Structure. Feedback.\nA file you can keep editing.", 80, 230, 78,
                      "keep editing."),
             diagram_op("workflow", 80, 500, 1440, 240),
             para("note", "Inspect the document, apply operations, run checks, visually review, then deliver. "
                  "The diagram itself is editable shapes, paths and labels.", 80, 770, 26, 1380)])
    save_and_export(p, "showcase", "agent-workflow", [("png", {}), ("svg", {}), ("pdf", {})],
                    checks=["bounds", "flow", "contrast", "fonts", "diagram"])
    SHOW["workflow"] = ("Editable workflow", "marketing/output/showcase/agent-workflow.png")
    SHOW["chart"] = ("Data-bound charts", "marketing/output/showcase/editable-chart.png")
    p = new(1600, 1200)
    p.apply([*logo("logo", "horizontal-reverse", 80, 50, width=240),
             text("kicker", "THE VIXL FIELD GUIDE", 80, 180, 26, SKY, MONO),
             headline("headline", "A studio you can program.", 80, 240, 86, "program.")])
    features = [("Design", "Layouts, type, vectors, masks, shaped images and emoji artwork."),
                ("Explain", "Data-bound charts, routed diagrams, decks and fillable PDFs."),
                ("Animate", "Keyframes, character poses, cameras, audio and app states."),
                ("Repeat", "Variables, typed recipes, CSV variants and reusable containers."),
                ("Review", "Design checks, saved suites, proof pages and live review."),
                ("Deliver", "Raster, vector, print, slides and motion; keep the .vixl master.")]
    for i, (label, body) in enumerate(features):
        x, y = 80 + i % 3 * 490, 435 + i // 3 * 320
        p.apply([rect(f"card-{i}", x, y, 460, 285),
                 text(f"number-{i}", f"0{i+1}", x + 30, y + 25, 28, SKY, MONO),
                 text(f"label-{i}", label, x + 30, y + 85, 52, WHITE, HEAD),
                 para(f"body-{i}", body, x + 30, y + 166, 29, 390)])
    footer(p, 1120, 80, size=24)
    save_and_export(p, "showcase", "capability-map", [("png", {}), ("svg", {}), ("pdf", {})],
                    checks=["bounds", "flow", "overlap", "contrast", "fonts"])


def build_og():
    p = new(1200, 630)
    p.apply([glow("glow", 550, -240, 900), *logo("logo", "horizontal-reverse", 64, 40, width=230),
             headline("headline", "Ideas become\neditable.", 64, 190, 88, "editable."),
             text("sub", "A programmable design studio\nfor AI agents.", 64, 414, 28),
             *code_card("code", 680, 124, 456, SNIPPET, size=20, title="design.json")])
    fit_code(p, "code")
    chips_row(p, "interfaces", INTERFACES, 64, 530, size=20)
    save_and_export(p, "social", "og-card-1200x630", [("png", {})], thumbnail_width=600)


def build_github():
    p = new(1280, 640, PAPER)
    p.apply([*logo("logo", "horizontal-color", 64, 42, width=230),
             headline("headline", "Ideas become\neditable.", 64, 206, 78, "editable.", INK, accent_color=BLUE),
             para("sub", "A programmable design studio for AI agents. Layered graphics, documents and motion.",
                  64, 407, 27, 530, SUBTLE),
             *photo("poster", "poster", 674, 48, 240, 350),
             *photo("pixel", "pixel", 674, 418, 240, 174),
             *photo("painting", "painting", 934, 48, 298, 244),
             *photo("chart", "chart", 934, 312, 298, 280)])
    chips_row(p, "iface", INTERFACES, 64, 540, size=20, fg=INK, bg=WHITE)
    save_and_export(p, "social", "github-preview-1280x640", [("png", {})], thumbnail_width=640)


def build_linkedin():
    p = new(1584, 396)
    p.apply([glow("glow", 960, -420, 1000),
             *pixel_stair("pixels", 70, 100, 22, 12, 8, SKY),
             headline("headline", "Ideas become editable.", 440, 120, 72, "editable."),
             text("sub", "A programmable design studio for AI agents.", 442, 227, 30),
             *logo("logo", "horizontal-reverse", 1280, 35, width=230),
             text("footer", REPO, 950, 326, 22, MUTED, MONO)])
    save_and_export(p, "social", "linkedin-banner-1584x396", [("png", {})], thumbnail_width=792)


def build_story():
    p = new(1080, 1920)
    m = 80
    p.apply([glow("glow", -180, 820, 1400),
             *logo("logo", "horizontal-reverse", m, 270, width=240),
             headline("headline", "Ideas\nbecome\neditable.", m, 440, 134, "editable."),
             *photo("poster", "poster", m, 900, 370, 500),
             *photo("painting", "painting", 476, 900, 524, 238),
             *photo("chart", "chart", 476, 1164, 524, 236),
             para("sub", "Graphics. Documents. Motion.\nMade with Vixl.", m, 1460, 42, 920)])
    chips_row(p, "iface", INTERFACES, m, 1600, size=28)
    save_and_export(p, "social", "story-1080x1920", [("png", {})], thumbnail_width=540,
                    safe_area={"left": 60, "right": 60, "top": 250, "bottom": 250})


def build_carousel():
    p = new(1080, 1350)
    m = 88
    p.apply([{"type": "master", "action": "add", "name": "frame", "background": CHARCOAL},
             *logo("footer-logo", "horizontal-reverse", m, 1230, width=168),
             text("page-num", "${page} / ${pages}", 900, 1250, 26, MUTED, MONO)])

    def page(name, kicker, title, accent=None):
        p.apply({"type": "page", "action": "add", "name": name, "master": "frame", "notes": kicker})
        p.apply([text("kicker", kicker, m, 120, 28, SKY, MONO),
                 headline("headline", title, m, 210, 100, accent)])

    page("cover", "A DESIGN STUDIO FOR AI AGENTS", "Ideas\nbecome\neditable.", "editable.")
    p.apply([*logo("mark", "mark-reverse", 665, 625, width=260),
             para("sub", "Create graphics, documents and motion. Keep the layers. Keep working.", m, 870, 42, 800),
             text("swipe", "MEET VIXL  →", m, 1110, 28, SKY, MONO)])
    page("document", "KEEP THE DOCUMENT", "One master.\nRoom to change.", "change.")
    for i, (title, body) in enumerate([
        ("Live text + vectors", "Edit copy, paths, masks and effects."),
        ("Reusable ingredients", "Variables, templates and containers."),
        ("Reviewable source", "Unpack designs into JSON and assets for Git.")]):
        y = 570 + i * 190
        p.apply([rect(f"card-{i}", m, y, 904, 162), text(f"label-{i}", title, m + 32, y + 25, 40, WHITE, HEAD),
                 para(f"body-{i}", body, m + 32, y + 87, 32, 835)])
    page("loop", "FROM BRIEF TO FILE", "Build. Check.\nLook. Deliver.", "Deliver.")
    loop_steps(p, "loop", m, 560, 904, size=42, vertical=True, step_h=110)
    page("gallery", "ALL MADE WITH VIXL", "A whole\ncreative workflow.", "creative workflow.")
    keys = ["poster", "painting", "pixel", "chart", "film", "photo"]
    for i, key in enumerate(keys):
        x, y = m + i % 2 * 466, 565 + i // 2 * 204
        p.apply(photo(f"image-{i}", key, x, y, 438, 178))
        chip(p, f"label-{i}", SHOW[key][0], x + 12, y + 117, size=25, pad=(12, 8))
    page("delivery", "MAKE ONCE. PUT IT TO WORK.", "Beyond\na single image.", "single image.")
    items = [("Campaigns", "Checked variants from typed recipes."),
             ("Documents", "Native charts in PPTX. Fillable PDFs."),
             ("Motion", "App states, themes and reduced-motion stills.")]
    for i, (title, body) in enumerate(items):
        y = 570 + i * 200
        p.apply([text(f"num-{i}", f"0{i+1}", m, y + 5, 36, SKY, MONO),
                 text(f"label-{i}", title, m + 90, y, 44, WHITE, HEAD),
                 para(f"body-{i}", body, m + 90, y + 75, 34, 780)])
    page("start", "START CREATING", "Give your agent\na design studio.", "design studio.")
    p.apply([para("sub", "Install Vixl, connect through MCP, or build with the CLI, Python and REST.", m, 600, 40, 850),
             para("repo", REPO, m, 845, 34, 900, WHITE, MONO),
             para("license", "Source-available · PolyForm Small Business 1.0.0\nAI generation uses configured external providers.",
                  m, 1030, 28, 875)])
    save_and_export(p, "carousel", "carousel-1080x1350", [("pdf", {})],
                    checks=["bounds", "flow", "overlap", "contrast", "fonts", "deck"], deck={"profile": "phone"})
    for i, record in enumerate(p.state["pages"]):
        p.export(OUT / "carousel" / f"slide-{i+1}-{record['name']}.png", page=record["name"], overwrite=True)
    sheet(p, OUT / "carousel/contact-sheet.png", width=360, columns=3)
    # Remove superseded named slides, so a directory upload contains exactly this carousel.
    valid = {f"slide-{i+1}-{r['name']}.png" for i, r in enumerate(p.state["pages"])}
    for path in (OUT / "carousel").glob("slide-*.png"):
        if path.name not in valid:
            path.unlink()


def build_poster():
    p = print_document("tabloid", bleed=True, background=CHARCOAL)
    w, h = p.state["canvas"]["width"], p.state["canvas"]["height"]
    m = 140
    p.apply([glow("glow", -400, 1400, 1900),
             *logo("logo", "horizontal-reverse", m, 130, width=320),
             text("kicker", "A PROGRAMMABLE DESIGN STUDIO FOR AI AGENTS", m, 420, 31, SKY, MONO),
             headline("headline", "IDEAS\nBECOME\nEDITABLE.", m, 670, 244, "EDITABLE.", line_height=0.96),
             para("sub", "Graphics, documents and motion.\nBuilt as layers. Checked before delivery.\nMade with Vixl.",
                  m, 1510, 52, w - 2 * m, WHITE),
             {"type": "qr", "name": "repo-qr", "data": "https://github.com/jxburros/Vixl", "size": 220,
              "x": m, "y": h - 500, "color": CHARCOAL, "background": WHITE},
             text("cta", "Meet Vixl", m + 270, h - 460, 64, WHITE, HEAD),
             para("interfaces", "MCP · CLI · Python · REST", m + 270, h - 345, 36, 900)])
    footer(p, h - 175, m, size=32)
    save_and_export(p, "print", "poster-tabloid", [("png", {"scale": 0.5}), ("pdf", {"color_space": "cmyk"})],
                    checks=["bounds", "flow", "overlap", "contrast", "safe_area", "fonts", "print"])


def build_onepager():
    p = print_document("letter")
    w, h = p.state["canvas"]["width"], p.state["canvas"]["height"]
    m = 90
    p.apply([rect("header", 0, 0, w, 480, CHARCOAL, 0),
             *logo("logo", "horizontal-reverse", m, 55, width=230),
             headline("headline", "Ideas become editable.", m, 207, 76, "editable."),
             para("sub", SUB, m, 330, 28, w - 2 * m)])
    features = [
        ("Create", "Layouts, type, vector paths, shaped images, painting, pixel art and emoji artwork."),
        ("Explain", "Data-bound charts, diagrams, decks, rich documents and fillable PDFs."),
        ("Animate", "Keyframes, rigged character poses, cameras, audio and app-state packages."),
        ("Repeat", "Typed recipes, variables, CSV-driven variants, reusable containers and templates."),
        ("Review", "Design checks and saved suites, offline proof pages, live review and branching history."),
        ("Deliver", "PNG, SVG, PDF, layered-pixel PSD, PPTX, HTML, GIF, WebP, MP4 and print exports."),
    ]
    for i, (title, body) in enumerate(features):
        x, y = m + i % 2 * 580, 550 + i // 2 * 215
        p.apply([text(f"label-{i}", title, x, y, 39, INK, HEAD),
                 para(f"body-{i}", body, x, y + 65, 27, 505, SUBTLE)])
    p.apply([text("start", "Choose your way in", m, 1240, 37, INK, HEAD),
             para("install", "Windows: use the installer from GitHub Releases.\nDevelopers: clone the repository and install with Python 3.11+.\nConnect an agent: vixl mcp --workspace . --tools core --schema slim",
                  m, 1308, 23, w - 2 * m, SUBTLE),
             para("license", "Source-available under PolyForm Small Business 1.0.0. See LICENSE for eligibility.\n"
                  "Core authoring works locally; AI generation and vision require configured external providers.",
                  m, 1490, 19, w - 2 * m, SUBTLE)])
    footer(p, h - 75, m, dark=False, size=20)
    save_and_export(p, "print", "one-pager-letter", [("pdf", {}), ("png", {})],
                    checks=["bounds", "flow", "overlap", "contrast", "fonts", "print"])


def build_brief():
    """Useful creative-intake form with real AcroForm fields and explicit tab order."""
    p = print_document("letter")
    w, h = p.state["canvas"]["width"], p.state["canvas"]["height"]
    m = 90
    p.apply([*logo("logo", "horizontal-color", m, 45, width=210),
             text("kicker", "MADE WITH VIXL / FILLABLE PDF", m, 185, 21, SUBTLE, MONO),
             headline("headline", "Start with a clear brief.", m, 250, 64, color=INK),
             para("sub", "Use this worksheet to plan a graphic, document or motion piece. Type into the PDF fields "
                  "or print it for a working session.", m, 350, 25, w - 2 * m, SUBTLE)])
    fields = [
        ("project_name", "Project / campaign", "text", 480, 72, 100),
        ("audience", "Who is it for?", "text", 635, 72, 120),
        ("message", "The one thing they should remember", "multiline", 790, 135, 260),
        ("action", "What should they do next?", "text", 1005, 72, 120),
        ("deliverables", "Deliverables, dimensions and channels", "multiline", 1160, 130, 260),
    ]
    for i, (key, label, kind, y, height, limit) in enumerate(fields):
        p.apply([text(f"label-{i}", label, m, y, 26, INK, SEMI),
                 {"type": "field", "name": key, "kind": kind, "label_layer": f"label-{i}",
                  "x": m, "y": y + 48, "width": w - 2 * m, "height": height, "max_length": limit,
                  "font": BODY, "size": 24, "min_size": 18, "tab": i + 1,
                  "appearance": {"style": "box", "fill": PAPER, "stroke": SUBTLE, "stroke_width": 1}}])
    p.apply([{"type": "field", "name": "review", "kind": "checkbox", "label": "Review copy, accessibility and export settings",
              "x": m, "y": 1395, "width": 28, "height": 28, "tab": 6},
             text("review-label", "Review copy, accessibility and export settings", m + 46, 1387, 23, INK),
             para("note", "Bring brand assets and content you have permission to use. Keep the editable master with the exports.",
                  m, 1480, 22, w - 2 * m, SUBTLE)])
    footer(p, h - 70, m, dark=False, size=20)
    save_and_export(p, "print", "creative-brief-letter", [("pdf", {"fillable": True}), ("png", {})],
                    checks=["bounds", "flow", "overlap", "contrast", "fonts", "form", "print"])


def build_stickers():
    p = print_document("letter")
    cells = [(110, 90), (700, 90), (110, 600), (700, 600), (110, 1110), (700, 1110)]
    for i, (x, y) in enumerate(cells):
        p.apply(rect(f"cut-{i}", x, y, 465, 420, CHARCOAL if i != 2 else PAPER, 64))
    for i in (0, 1):
        x, y = cells[i]
        p.apply(logo(f"logo-{i}", "mark-reverse" if i == 0 else "stacked-reverse", x + 105, y + 58, width=255))
    x, y = cells[2]
    p.apply([text("credit", "MADE WITH", x + 96, y + 110, 34, INK, MONO),
             *logo("logo-2", "horizontal-color", x + 55, y + 185, width=355)])
    for i, phrase in enumerate(["Ideas\nbecome\neditable.", "Keep\nthe\nlayers.", "MCP\nREADY"], 3):
        x, y = cells[i]
        p.apply(headline(f"sticker-{i}", phrase, x, y + 75, 80, width=465, align="center"))
    p.apply(text("note", "Event handout · Cut around each tile · Made with Vixl", 110, 1580, 22, SUBTLE))
    save_and_export(p, "print", "sticker-sheet-letter", [("pdf", {}), ("png", {"scale": 0.5})],
                    checks=["bounds", "flow", "overlap", "contrast", "fonts"])


def build_deck():
    """Twelve-slide product deck with notes and a genuinely native PowerPoint chart."""
    p = new(1920, 1080)
    m = 140
    p.apply([{"type": "master", "action": "add", "name": "frame", "background": CHARCOAL},
             *logo("footer-logo", "horizontal-reverse", m, 955, width=170),
             text("page-num", "${page} / ${pages}", 1670, 985, 24, MUTED, MONO)])

    def slide(name, kicker, title, notes, accent=None):
        p.apply({"type": "page", "action": "add", "name": name, "master": "frame", "notes": notes,
                 "transition": "fade"})
        p.apply([text("kicker", kicker, m, 100, 28, SKY, MONO),
                 headline("headline", title, m, 180, 94, accent)])

    def cards(items, y=430, height=385):
        cw = (1640 - 40 * (len(items) - 1)) // len(items)
        for i, (title, body) in enumerate(items):
            x = m + i * (cw + 40)
            p.apply([rect(f"card-{i}", x, y, cw, height),
                     text(f"number-{i}", f"0{i+1}", x + 36, y + 32, 28, SKY, MONO),
                     text(f"label-{i}", title, x + 36, y + 110, 49, WHITE, HEAD),
                     para(f"body-{i}", body, x + 36, y + 194, 34, cw - 72)])

    slide("title", "VIXL / A DESIGN STUDIO FOR AI AGENTS", "Ideas become\neditable.",
          "Vixl is a programmable design studio for AI agents. It turns graphics, documents and motion into "
          "layered files you can inspect, revise and deliver. This deck was authored with Vixl.", "editable.")
    p.apply([*logo("mark", "mark-reverse", 1270, 270, width=450),
             para("sub", "Graphics. Documents. Motion.\nMCP · CLI · Python · REST", m, 590, 44, 1050),
             text("credit", "THIS DECK IS MADE WITH VIXL", m, 830, 28, SKY, MONO)])
    slide("document", "THE CORE IDEA", "A design is a document.",
          "The .vixl master keeps editable content, settings and branching history. Raster images remain pixels; "
          "text, supported shapes and paths remain editable. Deliver the master alongside the formats people need.", "document.")
    cards([("Content", "Text, vector paths, images, masks and effects."),
           ("Structure", "Groups, variables, pages, layouts and reusable components."),
           ("History", "Undo, checkpoints, branches and document diffs.")])
    slide("workflow", "THE AGENT LOOP", "Feedback at every step.",
          "Inspect, apply, check, preview and export. The diagram is made from Vixl's diagram operation, with "
          "editable nodes, routed paths and text. Automated checks complement visual review; they do not judge taste.", "every step.")
    p.apply(diagram_op("workflow", m, 405, 1640, 275, size=34))
    p.apply(para("note", "Read the structure. Apply atomic edits. Check requirements.\nRender and review the design. Export the files.",
                 m, 750, 36, 1600, WHITE))
    slide("gallery", "A BROAD CREATIVE TOOLSET", "From print to pixels.",
          "These examples are real outputs in this repository: print layout, generative painting, a pixel game, "
          "data graphics, character animation and photo editing. They show different workflows rather than usage statistics.", "pixels.")
    keys = ["poster", "painting", "pixel", "chart", "film", "photo"]
    for i, key in enumerate(keys):
        x, y = m + i % 3 * 556, 375 + i // 3 * 276
        p.apply(photo(f"gallery-{i}", key, x, y, 528, 248))
        chip(p, f"gallery-label-{i}", SHOW[key][0], x + 14, y + 184, size=25, pad=(14, 8))
    slide("data", "DATA TO STORY", "Edit the data. Keep the chart.",
          "This is illustrative workflow data, not a customer result or performance claim. Vixl binds the chart "
          "to categories and series. In the PowerPoint export it is a native chart with an embedded workbook. "
          "Open PowerPoint's Edit Data command to inspect it.", "Keep the chart.")
    p.apply([rect("chart-panel", m, 370, 1020, 520, WHITE),
             chart_op("native-chart", m + 40, 410, 940, 415, size=29),
             text("source", "ILLUSTRATIVE WORKFLOW DATA", m + 40, 840, 20, SUBTLE, MONO),
             para("data-note", "Change values with chart-data.\n\nVixl updates the scale, bars, labels and totals.\n\nPPTX includes the data table.",
                  1240, 410, 35, 520, WHITE)])
    slide("repeat", "CREATIVE AUTOMATION", "One recipe. Useful variations.",
          "The included social campaign is a typed recipe. Its inputs supply headline, description and accent. "
          "Production instantiates three rows, runs the saved design suite and exports the checked variants. "
          "Use the supplied CSV and production request as a starting point.", "Useful variations.")
    p.apply([*photo("campaign", "campaign-kit", m, 390, 960, 460),
             para("repeat-note", "Typed inputs + variables\n\nText fitting + saved checks\n\nCSV-driven batches\n\nReusable containers and templates",
                  1190, 415, 35, 570, WHITE)])
    slide("motion", "MOTION THAT SHIPS", "Animate the idea.\nPackage the behavior.",
          "Vixl supports timeline tracks, cameras, audio and rigged joint pose keys. The app demo in this kit "
          "ships ready, creating and delivered states with light/dark themes, explicit transitions, editable "
          "masters and reduced-motion PNGs. The teaser is an editable timeline exported to MP4 and GIF.", "Package the behavior.")
    cards([("Author", "Keyframes, motion recipes, character poses, cameras and audio."),
           ("Export", "GIF, animated WebP, APNG, MP4 and other supported timeline formats."),
           ("Integrate", "App states, theme variables, transitions and reduced-motion stills.")], y=455, height=390)
    slide("review", "CHECKED DELIVERY", "Make requirements measurable.",
          "Design checks cover bounds, flow, contrast, fonts and other selected concerns. Saved suites can "
          "encode margins, hierarchy and spacing. Proof pages collect previews and findings offline. "
          "A passing check proves its rules, so a person or agent still needs to review the rendered design.", "measurable.")
    cards([("Define", "Save layout and delivery requirements as test suites."),
           ("Inspect", "Run checks, review findings and look at actual previews."),
           ("Share", "Use offline proof pages or a live REST review session.")])
    slide("collaborate", "REVIEWABLE WORK", "Designs belong in the workflow.",
          "Unpack a .vixl master into stable current-state JSON and hashed assets for Git review. Pack it "
          "back into a document after edits. Branching history, project groups and reusable libraries support "
          "collaboration. The included campaign has an unpacked source folder to inspect.", "workflow.")
    cards([("Git review", "Readable JSON + assets through pack and unpack."),
           ("Shared work", "Branches, explicit merges, project groups and reusable libraries."),
           ("Portable files", "Embedded content and fonts, plus the editable master.")])
    slide("interfaces", "FOUR WAYS IN", "Same operations. Your tools.",
          "MCP serves agents, the CLI serves scripts and CI, Python serves generators and notebooks, and REST "
          "serves integrations and live review. All share canonical operations. The server extra is needed for REST.", "Your tools.")
    cards([("MCP", "Connect an agent to the workspace."), ("CLI", "Script and batch from a terminal."),
           ("Python", "Compose files from code and data."), ("REST", "Integrate with web services.")], height=360)
    slide("delivery", "A COMPLETE HANDOFF", "Send the formats people need.",
          "Supported vectors stay vector in SVG/PDF where possible; some features use reported raster "
          "fallbacks. PPTX preserves supported editable shapes, text, tables and charts. PSD export is layered "
          "pixels, not native editable type. CMYK is an export setting; a printer should confirm the chosen profile.", "people need.")
    cards([("Screen", "PNG, JPEG, WebP, SVG and icons."),
           ("Documents", "PDF, fillable PDF, PPTX and HTML decks."),
           ("Print + motion", "CMYK PDF/TIFF, GIF, WebP, MP4 and more.")])
    slide("start", "START CREATING", "Give your agent a design studio.",
          "Windows users can use the installer from GitHub Releases. Developers need Python 3.11 or newer; "
          "clone the repo, then install its extras. Run the MCP command in an existing workspace. Vixl is "
          "source-available under PolyForm Small Business 1.0.0; read LICENSE for eligibility. Core authoring "
          "works locally. AI generation and vision need configured external providers.", "design studio.")
    command = [
        (0, [("git clone https://github.com/jxburros/Vixl.git", WHITE)]),
        (0, [("cd Vixl", WHITE)]),
        (0, [("python -m pip install -e '.[server,pdf]'", WHITE)]),
        (0, [("vixl mcp --workspace . --tools core --schema slim", CODE_STR)]),
    ]
    p.apply(code_card("install", m, 375, 1640, command, size=30, title="terminal"))
    p.apply([text("windows", "Windows installer: GitHub Releases", m, 725, 34, WHITE, SEMI),
             text("repo", REPO, m, 790, 31, SKY, MONO),
             para("license", "Source-available · PolyForm Small Business 1.0.0\nAI features use configured external providers.",
                  m, 854, 27, 1540)])
    save_and_export(p, "deck", "vixl-pitch-deck", [("pdf", {}), ("pptx", {}), ("html", {})],
                    checks=["bounds", "flow", "overlap", "contrast", "fonts", "deck"], deck={"profile": "screen"})
    sheet(p, OUT / "deck/contact-sheet.png", width=480, columns=3)
    p.export(OUT / "deck/vixl-pitch-deck.png", page="title", scale=0.5, overwrite=True)


def build_campaign():
    """A practical three-post campaign built with checked typed recipe production."""
    from vixl.production import capture_recipe, run, instantiate
    from vixl.project_folder import unpack

    folder = OUT / "campaign"
    # Only this builder-owned output directory is replaced; no user input lives here.
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    p = new(1080, 1080)
    p.apply([*logo("logo", "horizontal-reverse", 80, 45, width=230),
             text("kicker", "A DESIGN STUDIO FOR AI AGENTS", 80, 210, 27, SKY, MONO),
             text("title", "Keep the layers.", 80, 340, 106, WHITE, HEAD),
             text("body", "Create, inspect and revise layered designs.", 80, 670, 40),
             {"type": "text-layout", "target": "body", "width": 875, "height": 140},
             rect("accent", 80, 860, 920, 8, SKY, 0),
             text("footer", REPO, 80, 960, 27, MUTED, MONO),
             {"type": "action-define", "name": "fit-title", "action": {"operations": [
                 {"type": "fit-text", "target": "title", "width": 920, "height": 260, "minimum": 68, "maximum": 106}]}},
             {"type": "suite-set", "name": "delivery", "suite": {"rules": [
                 {"id": "headline-fits", "kind": "text-fit", "target": "title", "minimum": 68},
                 {"id": "headline-margin", "kind": "relation", "target": "title", "to": "canvas",
                  "position": "inside", "minimum": 70},
                 {"id": "readable", "kind": "contrast", "target": "title", "minimum": 4.5},
                 {"id": "layout", "kind": "design", "options": {"checks": ["bounds", "flow", "overlap", "contrast", "fonts"]}},
             ]}}])
    with (HERE / "posts.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    recipe = capture_recipe(p, {"version": 1, "inputs": {
        "title": {"type": "string", "default": rows[0]["title"], "maxLength": 60},
        "body": {"type": "string", "default": rows[0]["body"], "maxLength": 100},
        "accent": {"type": "color", "default": SKY}}, "actions": ["fit-title"], "examples": rows},
        {"title": {"target": "title", "field": "text"}, "body": {"target": "body", "field": "text"},
         "accent": {"target": "accent", "field": "fill"}})
    recipe.compact()
    recipe.save(folder / "campaign-recipe.vixl")
    spec = {"version": 1, "rows": rows, "suites": ["delivery"], "workers": 1}
    (folder / "production.json").write_text(json.dumps({"spec": spec, "output": "campaign-custom"}, indent=2) + "\n")
    shutil.copyfile(HERE / "posts.csv", folder / "posts.csv")
    report = run(recipe, spec, folder / "rendered")
    if report["status"] != "completed":
        raise RuntimeError(f"Campaign failed: {report}")
    previews = new(1800, 700)
    previews.apply(text("headline", "One recipe. Three useful posts.", 60, 30, 50, WHITE, HEAD))
    for i, result in enumerate(report["results"]):
        candidate = instantiate(recipe, result["values"])
        save_and_export(candidate, "campaign", f"post-{i+1}-1080x1080", [("png", {})],
                        checks=["bounds", "flow", "overlap", "contrast", "fonts"], thumbnail_width=540)
        previews.apply({"type": "frame", "name": f"post-{i}", "path": str(folder / f"post-{i+1}-1080x1080.png"),
                        "x": 60 + i * 580, "y": 140, "width": 520, "height": 520, "downsample": "placed@2x"})
    save_and_export(previews, "campaign", "contact-sheet", [("png", {})], checks=["bounds", "flow", "fonts"])
    unpack(folder / "campaign-recipe.vixl", folder / "source")
    SHOW["campaign-kit"] = ("Checked campaign variants", "marketing/output/campaign/contact-sheet.png")


def build_app():
    """A reusable branded status graphic with three states, two themes and reduced-motion stills."""
    from vixl.interfaces import Session
    from vixl.workflows import dispatch

    root = OUT / "app"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    states = {}
    for state, label in (("ready", "Ready to create"), ("creating", "Creating"), ("delivered", "Ready to share")):
        p = new(640, 320)
        p.apply([{"type": "variable", "name": "bg", "value": CHARCOAL},
                 {"type": "variable", "name": "fg", "value": WHITE},
                 {"type": "variable", "name": "accent", "value": SKY},
                 rect("surface", 0, 0, 640, 320, "${bg}", 0),
                 text("kicker", "VIXL / IDEAS BECOME EDITABLE", 40, 40, 20, "${fg}", MONO),
                 text("title", label, 40, 135, 49, "${fg}", HEAD),
                 text("footer", "A design studio for AI agents", 40, 252, 22, "${fg}")])
        for i in range(3):
            p.apply(rect(f"pixel-{i}", 490 + i * 38, 150, 20, 20, "${accent}", 0))
        p.apply({"type": "timeline-set", "duration": 1200, "fps": 12, "loop_mode": "seamless"})
        if state == "creating":
            for i in range(3):
                p.apply([{"type": "keyframe", "target": f"pixel-{i}", "property": "translate-y", "time": 0, "value": 0},
                         {"type": "keyframe", "target": f"pixel-{i}", "property": "translate-y", "time": 300 + i * 120,
                          "value": -18, "easing": "ease-in-out"},
                         {"type": "keyframe", "target": f"pixel-{i}", "property": "translate-y", "time": 1200, "value": 0}])
        # Validate still content plus sampled moving-pixel margins, before packaging.
        p.apply({"type": "suite-set", "name": "motion", "suite": {
            "sampling": {"mode": "sampled", "count": 6}, "rules": [
                {"id": f"pixel-{i}-inside", "kind": "relation", "target": f"pixel-{i}", "to": "canvas",
                 "position": "inside", "minimum": 20} for i in range(3)]}})
        motion_report = p.check_suite("motion")
        if not motion_report["passed"]:
            raise RuntimeError(f"App motion suite failed: {motion_report}")
        save_and_export(p, "app", state, [("png", {})], checks=["bounds", "flow", "contrast", "fonts"])
        (root / f"{state}.motion-check.json").write_text(json.dumps(motion_report, indent=2) + "\n")
        states[state] = {"source": f"marketing/output/app/{state}.vixl", "loop": True}
    request = {"states": states, "default_state": "ready", "themes": {
        "dark": {"bg": CHARCOAL, "fg": WHITE, "accent": SKY},
        "light": {"bg": PAPER, "fg": INK, "accent": BLUE}}, "transitions": [
            {"from": "ready", "event": "create", "to": "creating"},
            {"from": "creating", "event": "deliver", "to": "delivered"},
            {"from": "delivered", "event": "reset", "to": "ready"}],
        "output": "marketing/output/app/package", "format": "webp"}
    dispatch(Session(workspace=ROOT), "app-animation-package", request)
    (root / "package-request.json").write_text(json.dumps(request, indent=2) + "\n")


def build_teaser():
    """A play-once 6.6 second timeline plus a useful reduced-motion poster."""
    from vixl.timeline import contact_sheet, export_timeline, render_at

    p = new(1080, 1080)
    p.apply([*logo("logo", "horizontal-reverse", 340, 70, width=400),
             *logo("mark", "mark-reverse", 390, 245, width=300),
             headline("headline", "Ideas become\neditable.", 60, 605, 88, "editable.", width=960, align="center"),
             text("footer", REPO, 90, 985, 27, MUTED, MONO),
             {"type": "timeline-set", "duration": 6600, "fps": 24, "loop_mode": "off", "loop": 1}])
    for i, label in enumerate(["Inspect", "Apply", "Check", "Preview", "Export"]):
        x = 80 + i * 188
        p.apply([text(f"step-{i}", label, x, 850, 29, WHITE, SEMI),
                 rect(f"line-{i}", x, 925, 140, 6, LINE, 0)])
    p.apply([rect("progress", 80, 925, 140, 6, SKY, 0),
             {"type": "layer-intent", "target": "progress", "role": "decoration"},
             {"type": "animate-preset", "target": "mark", "preset": "pop-in", "start": 0, "duration": 600},
             {"type": "keyframe", "target": "progress", "property": "translate-x", "time": 0, "value": 0},
             {"type": "keyframe", "target": "progress", "property": "translate-x", "time": 5500, "value": 752},
             {"type": "keyframe", "target": "progress", "property": "translate-x", "time": 6600, "value": 752},
             {"type": "suite-set", "name": "motion", "suite": {"sampling": {"mode": "sampled", "count": 12},
                 "rules": [{"id": "title-margin", "kind": "relation", "target": "headline", "to": "canvas",
                            "position": "inside", "minimum": 55},
                           {"id": "progress-inside", "kind": "relation", "target": "progress", "to": "canvas",
                            "position": "inside", "minimum": 50}]}}])
    report = p.check_suite("motion")
    if not report["passed"]:
        raise RuntimeError(f"Teaser motion suite failed: {report}")
    save_and_export(p, "motion", "teaser", [], checks=["bounds", "flow", "overlap", "contrast", "fonts"])
    folder = OUT / "motion"
    (folder / "teaser.motion-check.json").write_text(json.dumps(report, indent=2) + "\n")
    export_timeline(p, folder / "teaser.mp4", fps=24, overwrite=True)
    export_timeline(p, folder / "teaser.gif", fps=12, scale=0.5, colors=128, overwrite=True)
    render_at(p, 5800).convert("RGB").save(folder / "teaser-frame.png")
    contact_sheet(p, count=12, columns=6, max_width=1800).convert("RGB").save(folder / "teaser-contact-sheet.png")


def build_copy():
    """Copy is supplied as data and plain text so it can be pasted into publishing tools."""
    copy = json.loads((HERE / "copy.json").read_text(encoding="utf-8"))
    folder = OUT / "copy"
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copytree(HERE / "licenses", OUT / "licenses", dirs_exist_ok=True)
    (folder / "marketing-copy.json").write_text(json.dumps(copy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sections = [copy["headline"], copy["one_sentence"], "SHORT DESCRIPTION\n" + copy["short_description"],
                "PRODUCT DESCRIPTION\n" + copy["product_description"], "LICENSING\n" + copy["licensing"],
                "GET STARTED\n" + copy["get_started"]]
    for post in copy["posts"]:
        sections.append(f"{post['label'].upper()}\nAsset: {post['asset']}\n\n{post['caption']}\n\nAlt text: {post['alt']}")
    sections.append("DEMO SCRIPT\n" + "\n\n".join(copy["demo_script"]))
    (folder / "marketing-copy.txt").write_text("\n\n".join(sections) + "\n", encoding="utf-8")


def build_overview():
    p = new(2400, 1740)
    tiles = [
        ("social/og-card-1200x630.png", "Link preview", 700, 368),
        ("deck/vixl-pitch-deck.png", "Product deck · 12 slides", 700, 394),
        ("campaign/contact-sheet.png", "Reusable social campaign", 700, 272),
        ("carousel/slide-1-cover.png", "Carousel · 6 slides", 350, 438),
        ("print/one-pager-letter.png", "Product sheet", 350, 453),
        ("print/creative-brief-letter.png", "Fillable creative brief", 350, 453),
        ("print/poster-tabloid.png", "CMYK print poster", 350, 537),
        ("showcase/capability-map.png", "Capability map", 350, 263),
        ("motion/teaser-frame.png", "Motion teaser", 350, 350),
    ]
    p.apply([*logo("logo", "horizontal-reverse", 80, 45, width=280),
             headline("headline", "The Vixl marketing pack.", 460, 83, 76, "Vixl"),
             text("sub", "Useful materials. Editable originals. Made with Vixl.", 80, 220, 34)])
    placements = [(80, 340), (80, 800), (80, 1290), (850, 340), (1260, 340), (1670, 340),
                  (850, 900), (1260, 950), (1670, 980)]
    for i, ((path, label, w, h), (x, y)) in enumerate(zip(tiles, placements)):
        p.apply([{ "type": "frame", "name": f"tile-{i}", "path": str(OUT / path),
                   "x": x, "y": y, "width": w, "height": h, "fit": "fit", "downsample": "placed@2x"},
                 text(f"label-{i}", label, x, y + h + 20, 26, MUTED)])
    p.apply([text("app-title", "Includes an app animation family", 1260, 1435, 34, WHITE, HEAD),
             para("app-sub", "3 states · Light + dark themes\nReduced-motion PNGs · HTML consumer", 1260, 1495, 28, 890)])
    save_and_export(p, ".", "kit-overview", [("png", {"scale": 0.75})], checks=["bounds", "flow", "fonts"])


def build_proof():
    from vixl.proof import proof_page

    items = [
        ("social/og-card-1200x630.png", "Link preview"),
        ("social/github-preview-1280x640.png", "GitHub social preview"),
        ("social/linkedin-banner-1584x396.png", "LinkedIn banner"),
        ("social/story-1080x1920.png", "Story"),
        ("carousel/carousel-1080x1350.vixl", "Six-page carousel"),
        ("deck/vixl-pitch-deck.vixl", "Product deck with notes"),
        ("print/poster-tabloid.pdf", "CMYK tabloid poster"),
        ("print/one-pager-letter.pdf", "Product sheet"),
        ("print/creative-brief-letter.pdf", "Fillable creative brief"),
        ("print/sticker-sheet-letter.png", "Event sticker handout"),
        ("showcase/capability-map.png", "Capability map"),
        ("showcase/editable-chart.png", "Data-bound chart"),
        ("showcase/agent-workflow.png", "Editable workflow diagram"),
        ("campaign/contact-sheet.png", "Checked campaign variants"),
        ("motion/teaser-frame.png", "Motion teaser still"),
        ("app/package/assets/creating/dark-reduced.png", "App status animation still"),
    ]
    result = proof_page([{"path": path, "label": label} for path, label in items], OUT / "proof.html",
                        resolve=lambda value: OUT / value, title="Vixl marketing pack", check=False,
                        decisions=True, overwrite=True)
    if result["failed"]:
        raise RuntimeError(f"Proof generation failed: {result['failed']}")


def build_manifest():
    from vixl import __version__

    files = {}
    for path in sorted(OUT.rglob("*")):
        if path.is_file() and path != OUT / "manifest.json":
            files[path.relative_to(OUT).as_posix()] = {
                "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest = {"format": "vixl-marketing-pack", "engine_version": __version__, "registry_facts": FACTS,
                "files": files}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


PIECES = {"showcase": build_showcase, "campaign": build_campaign, "og": build_og, "github": build_github,
          "linkedin": build_linkedin, "story": build_story, "carousel": build_carousel, "poster": build_poster,
          "onepager": build_onepager, "brief": build_brief, "stickers": build_stickers, "deck": build_deck,
          "app": build_app, "teaser": build_teaser, "copy": build_copy, "overview": build_overview,
          "proof": build_proof}


def main(argv):
    names = argv or list(PIECES)
    unknown = set(names) - PIECES.keys()
    if unknown:
        raise SystemExit(f"Unknown pieces: {', '.join(sorted(unknown))}. Choose: {', '.join(PIECES)}")
    # Consumers share fresh native showcases, including when only a consumer is requested.
    SHOW["workflow"] = ("Editable workflow", "marketing/output/showcase/agent-workflow.png")
    SHOW["chart"] = ("Data-bound charts", "marketing/output/showcase/editable-chart.png")
    SHOW["campaign-kit"] = ("Checked campaign variants", "marketing/output/campaign/contact-sheet.png")
    dependencies = {"github": ["showcase"], "story": ["showcase"], "carousel": ["showcase"],
                    "deck": ["showcase", "campaign"],
                    "overview": ["og", "deck", "carousel", "poster", "onepager", "brief", "teaser", "app"],
                    "proof": ["overview", "github", "linkedin", "story", "stickers", "copy"]}
    built = set()

    def build(name):
        if name in built:
            return
        for dependency in dependencies.get(name, []):
            build(dependency)
        print(f"[{name}]", flush=True)
        PIECES[name]()
        built.add(name)

    for name in names:
        build(name)
    build_manifest()


if __name__ == "__main__":
    main(sys.argv[1:])
