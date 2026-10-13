"""Build the Vixl user guide: a letter-size booklet for people, made entirely with Vixl.

Run from the repository root: python examples/build_user_guide.py
Writes docs/user-guide/ (the editable master, a vector PDF, a contact sheet and the cover).
The brand fonts (Inter Tight, Inter, JetBrains Mono) are fetched once from Google Fonts and cached;
the logo is the Ripple wordmark geometry from assets/brand/ripple/build.py, drawn as path layers.
"""

import argparse
import importlib.util
import re
from pathlib import Path

from vixl import Project, __version__
from vixl.deck import contact_sheet
from vixl.typefaces import install_font

ROOT = Path(__file__).resolve().parents[1]

W, H = 1700, 2200  # US Letter at 200 dpi
M = 150  # outer margin
CW = W - 2 * M

INK, PAPER, WHITE = "#252B39", "#F6F4EF", "#FFFFFF"
BLUE, MID, SKY, PALE = "#3575EE", "#5B8FF5", "#6A9AFF", "#A9C4FF"
MUTED, RULE, TINT, NIGHT = "#5D6577", "#D8D4CA", "#E6ECFA", "#1C2130"
DEEP = "#2457C9"  # the brand blue darkened to pass AA contrast for small text on paper
REVERSE_RIPPLE = [SKY, SKY, "#5B87E6", "#5B87E6", "#4A6FC0", "#4A6FC0", "#3A5288"]
COLOR_RIPPLE = [BLUE, BLUE, MID, MID, SKY, SKY, PALE]

DISPLAY, BODY, SEMI, MONO = "inter-tight-800", "inter-400", "inter-600", "jetbrains-mono-500"
VARIANTS = {"bold": "inter-700", "italic": "inter-400-italic"}


def load_ripple():
    spec = importlib.util.spec_from_file_location("ripple", ROOT / "assets/brand/ripple/build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RIPPLE = load_ripple()


# Building blocks ----------------------------------------------------------------------------------
def text(name, value, x, y, size, color=INK, font=BODY, **extra):
    return dict(type="text", name=name, text=value, x=x, y=y, size=size, color=color, font=font, **extra)


def label(name, value, x, y, color=DEEP, size=24):
    """Uppercase, tracked part label: the house craft signature."""
    return text(name, value.upper(), x, y, size, color, SEMI, tracking=3)


def boxed(name, value, x, y, width, size, color, font, align, **extra):
    """One line set left, centred or right inside a box of `width`."""
    return dict(type="rich-text", name=name, spans=[dict(text=value, **extra)], x=x, y=y, width=width,
                size=size, color=color, font=font, align=align)


def prose(name, markdown, x, y, width, size=34, color=INK, **extra):
    """Rich text; `backticks` become JetBrains Mono spans (rich-text markdown has no inline code)."""
    markdown = re.sub(r"`([^`]+)`", lambda m: f"[{m[1]}]{{font={MONO}}}", markdown)
    return dict(type="rich-text", name=name, markdown=markdown, x=x, y=y, width=width, size=size,
                color=color, font=BODY, font_variants=VARIANTS, line_height=1.45, **extra)


def rect(name, x, y, w, h, fill, **extra):
    return dict(type="shape", shape="rectangle", name=name, x=x, y=y, width=w, height=h, fill=fill, **extra)


def rule(name, x, y, w, color=RULE, weight=2):
    return rect(name, x, y, w, weight, color)


def card(name, x, y, w, h, fill=WHITE, shadow=INK, offset=12):
    """Sharp-cornered card with a thin outline and a hard offset shadow."""
    return [rect(f"{name}-shadow", x + offset, y + offset, w, h, shadow),
            rect(name, x, y, w, h, fill, stroke=INK, stroke_width=2)]


def icon(name, shape, x, y, size, fill=BLUE, **extra):
    return dict(type="shape", shape=shape, name=name, x=x, y=y, width=size, height=size, fill=fill, **extra)


def code(name, lines, x, y, w, size=27, pad=44, title=None):
    """A terminal panel: comments (#) in muted blue, commands in white, prompts in sky."""
    step = round(size * 1.7)
    top = 74 if title else pad
    h = top + pad + step * len(lines) - (step - size)
    ops = [rect(f"{name}-shadow", x + 12, y + 12, w, h, BLUE), rect(name, x, y, w, h, NIGHT)]
    if title:
        ops += [rect(f"{name}-bar", x, y, w, 54, "#2A3142"),
                *[icon(f"{name}-dot-{i}", "ellipse", x + 26 + i * 28, y + 19, 16, c)
                  for i, c in enumerate(("#E8705F", "#E9B949", "#58B87A"))],
                text(f"{name}-title", title, x + 120, y + 14, 22, "#A9B3C9", MONO)]
    for i, line in enumerate(lines):
        ly = y + top + i * step
        if not line:
            continue
        if line.startswith("#"):
            ops.append(text(f"{name}-{i}", line, x + pad, ly, size, "#94A0BA", MONO))
        elif line.startswith("$ "):
            ops += [text(f"{name}-{i}-prompt", "$", x + pad, ly, size, SKY, MONO),
                    text(f"{name}-{i}", line[2:], x + pad + round(size * 1.25), ly, size, WHITE, MONO)]
        else:
            ops.append(text(f"{name}-{i}", line, x + pad, ly, size, WHITE, MONO))
    return ops, h


def bands(name, x, y, w, h, colors, drift=(0, 16, -14, 22, -18, 26, -10), unit=4, fill=0.55):
    """The Ripple motif as a page device: seven bands that drift sideways like broken water."""
    slot = h / len(colors)
    ops = [rect(f"{name}-{i}", round(x + drift[i] * unit), round(y + i * slot),
                w, max(2, round(slot * fill)), c) for i, c in enumerate(colors)]
    return ops + [dict(type="layer-intent", targets=[o["name"] for o in ops], role="decoration",
                       allow_crop=True, decorative=True)]


def logo(prefix, x, y, u, ink, colours, kind="wordmark"):
    """Ripple logo as path layers, its ink box's top-left at (x, y)."""
    shapes = RIPPLE.wordmark(u, ink, colours) if kind == "wordmark" else RIPPLE.mark(u, ink, colours)
    x0, y0, _, _ = RIPPLE.extent(shapes)
    ops = []
    for i, (part, pts, fill) in enumerate(shapes):
        pts = RIPPLE.moved(pts, x - x0, y - y0)
        left, top = min(p[0] for p in pts), min(p[1] for p in pts)
        d = "M" + " L".join(f"{round(px - left, 2)} {round(py - top, 2)}" for px, py in pts) + " Z"
        ops.append(dict(type="shape", shape="path", name=f"{prefix}-{part.replace(' ', '-')}-{i}",
                        path=d, x=round(left, 2), y=round(top, 2), fill=fill))
    return ops


def logo_size(u, kind="wordmark"):
    shapes = RIPPLE.wordmark(u, INK, COLOR_RIPPLE) if kind == "wordmark" else RIPPLE.mark(u, INK, COLOR_RIPPLE)
    x0, y0, x1, y1 = RIPPLE.extent(shapes)
    return x1 - x0, y1 - y0


def page(name, section, notes):
    return dict(type="page", action="add", name=name, master="std", notes=notes,
                variables={"section": section})


def opener(key, number, title, lead, y=230):
    """Section opener: big blue number, display title, lead paragraph."""
    return [text(f"{key}-number", number, M - 6, y, 150, BLUE, DISPLAY),
            text(f"{key}-title", title, M - 4, y + 190, 104, INK, DISPLAY, line_height=1.02),
            prose(f"{key}-lead", lead, M, y + 330 + 112 * title.count("\n"), 1180, 40, MUTED)]


# Pages --------------------------------------------------------------------------------------------
def master():
    wm_w, _ = logo_size(0.16, "mark")
    return [dict(type="master", action="add", name="std", background=PAPER),
            label("run-head", "Vixl · a field guide for humans", M, 92, MUTED, 21),
            boxed("run-section", "${section|default: }", W - M - 700, 92, 700, 21, DEEP, SEMI, "right", tracking=3),
            rule("run-rule", M, 140, CW, INK, 2),
            rule("foot-rule", M, H - 150, CW, RULE, 2),
            *logo("foot-mark", M, H - 118, 0.16, INK, COLOR_RIPPLE, kind="mark"),
            text("foot-name", "Vixl " + __version__, M + wm_w + 22, H - 112, 21, MUTED, SEMI),
            boxed("foot-page", "${page}", W - M - 200, H - 120, 200, 34, INK, MONO, "right")]


def cover():
    wm_w, wm_h = logo_size(1.75)
    ops = [dict(type="page", action="add", name="cover", master="none", background=INK,
                notes="Cover. Every element is a live layer: the wordmark is path geometry, the type is text.",
                variables={"section": "Cover"}),
           label("cover-kicker", f"User guide · Vixl {__version__}", M, 150, SKY, 26),
           rule("cover-kicker-rule", M, 205, 120, SKY, 4),
           *logo("cover-logo", (W - wm_w) / 2, 470, 1.75, WHITE, REVERSE_RIPPLE),
           text("cover-title", "A field guide\nfor humans", M - 6, 470 + wm_h + 210, 150, WHITE, DISPLAY,
                line_height=1.0),
           prose("cover-sub", "How to make, check and ship editable designs with Vixl: the install, the first "
                 "design, the working loop and everything that comes after.",
                 M, 470 + wm_h + 560, 1180, 40, PALE),
           *bands("cover-bands", -60, H - 300, W + 120, 210, REVERSE_RIPPLE, unit=7),
           label("cover-foot", "Ideas become editable.", M, H - 400, WHITE, 26)]
    return ops


def contents():
    rows = [("01", "What Vixl is", "Three promises, and what you get back"),
            ("02", "Install", "Windows installer, pip, updates"),
            ("03", "Your first design", "Six commands, one checked file"),
            ("04", "The working loop", "Create, apply, inspect, check, preview, export"),
            ("05", "Inside a .vixl file", "Layers, pages, variables and history"),
            ("06", "Four ways in", "CLI, Python, MCP and REST"),
            ("07", "Working with an agent", "Briefs that get good results"),
            ("08", "What you can make", "Twelve kinds of work"),
            ("09", "Check before you ship", "The rules Vixl can measure"),
            ("10", "Export", "Choosing the file people get back"),
            ("11", "When things go wrong", "Symptoms, causes, fixes"),
            ("12", "Cheat sheet", "The commands you'll use daily")]
    ops = [page("contents", "Contents", "Contents and how to read this guide."),
           text("toc-title", "Contents", M - 4, 230, 104, INK, DISPLAY)]
    y0, step = 430, 104
    for i, (num, title, detail) in enumerate(rows):
        y = y0 + i * step
        ops += [text(f"toc-num-{i}", num, M, y + 4, 30, DEEP, MONO),
                text(f"toc-title-{i}", title, M + 110, y, 42, INK, DISPLAY),
                text(f"toc-detail-{i}", detail, M + 690, y + 10, 29, MUTED),
                rule(f"toc-rule-{i}", M, y + 78, CW)]
    by = y0 + len(rows) * step + 50
    ops += [*card("toc-note", M, by, CW, 300, TINT),
            label("toc-note-label", "How to read this guide", M + 50, by + 46),
            prose("toc-note-body", "Read 01–04 once, in order. After that, dip in. Commands are shown as you'd type "
                  "them in a terminal; lines starting with **#** are comments. Everything here works offline "
                  "except font downloads and AI providers.", M + 50, by + 100, CW - 100, 33)]
    return ops


def what_it_is():
    ops = [page("what", "01 · What Vixl is", "Lead with Editable: the pillars and what you get back."),
           *opener("what", "01", "What Vixl is",
                   "Ask an AI for a poster and you usually get a *picture* of a poster. Vixl gives you the "
                   "real thing: layers, live text, fonts, a history you can rewind, and a master you can still "
                   "change next week.")]
    pillars = [("Programmable", "code", "One JSON operation format behind the CLI, Python, MCP and REST. "
                "Batches of up to 10,000 operations apply atomically, so a half-finished edit never lands."),
               ("Editable", "layers", "Text stays text, effects stay a stack and history branches. Charts open "
                "in PowerPoint as charts; forms export as PDFs people can fill in."),
               ("Checked", "checkmark", "Contrast, spacing, bounds, fonts, trim and bleed are measured before "
                "export, so nobody finds out at the print shop.")]
    y, cw, gap = 900, 440, 40
    for i, (title, glyph, body) in enumerate(pillars):
        x = M + i * (cw + gap)
        ops += card(f"pillar-{i}", x, y, cw - 12, 640)
        if glyph == "code":
            ops += [text(f"pillar-{i}-glyph", "{ }", x + 40, y + 36, 64, BLUE, MONO)]
        elif glyph == "layers":
            ops += [rect(f"pillar-{i}-glyph-{k}", x + 40 + k * 14, y + 50 + k * 14, 70, 50,
                         [PALE, MID, BLUE][k], stroke=INK, stroke_width=2) for k in range(3)]
        else:
            ops += [icon(f"pillar-{i}-glyph", "checkmark", x + 40, y + 46, 80, BLUE)]
        ops += [text(f"pillar-{i}-title", title, x + 40, y + 170, 46, INK, DISPLAY),
                prose(f"pillar-{i}-body", body, x + 40, y + 250, cw - 92, 29)]
    gy = 1640
    ops += [label("what-get", "What you get back", M, gy),
            prose("what-get-body",
                  "- A **.vixl master**: one portable file holding layers, pages, fonts and history.\n"
                  "- **Exports** in the format the job needs: PNG, PDF, SVG, PPTX, video and more.\n"
                  "- **A check report** that says what was measured and what passed.",
                  M, gy + 56, CW, 34)]
    return ops


def install():
    ops = [page("install", "02 · Install", "Two install routes; verify the version."),
           *opener("install", "02", "Install",
                   "Pick the route that matches how you work. Both give you the same `vixl` command, the "
                   "same file format and the same results.")]
    y = 780
    ops += [*card("win", M, y, 670, 520, WHITE),
            label("win-label", "Windows", M + 44, y + 44),
            text("win-title", "The installer", M + 44, y + 96, 50, INK, DISPLAY),
            prose("win-body", "Download **Vixl-Setup-VERSION-windows-x64.exe** from GitHub Releases. It "
                  "bundles Python, REST and MCP, installs for your account and updates itself with "
                  "verified downloads.", M + 44, y + 180, 580, 30),
            *card("src", M + 730, y, 670, 520, WHITE),
            label("src-label", "macOS · Linux · Windows", M + 774, y + 44),
            text("src-title", "Python 3.11+", M + 774, y + 96, 50, INK, DISPLAY),
            prose("src-body", "Install from a source checkout into a virtual environment. Add **server** for "
                  "REST and live review, **pdf** for importing PDF pages. MCP is always included.",
                  M + 774, y + 180, 580, 30)]
    panel, h = code("install-code", [
        "# from a source checkout",
        "$ python -m venv .venv",
        "$ source .venv/bin/activate",
        "$ python -m pip install -e '.[server,pdf]'",
        "",
        "# confirm, then keep it current",
        "$ vixl --version",
        "$ vixl update --check",
        "$ vixl update"], M, y + 600, CW - 12, title="terminal")
    ops += panel
    ty = y + 600 + h + 70
    ops += [icon("install-tip-icon", "info", M, ty, 52, BLUE),
            prose("install-tip", "**`vixl` not found?** Reopen the terminal, or activate the virtual environment "
                  "you installed into. Pip installs update with pip; the Windows build updates itself.",
                  M + 80, ty - 2, CW - 80, 30, MUTED)]
    return ops


def first_design():
    ops = [page("first", "03 · Your first design", "Six commands from blank to checked export."),
           *opener("first", "03", "Your first\ndesign",
                   "Six commands take you from nothing to a checked, exported image that is still fully "
                   "editable.")]
    y = 870
    panel, h = code("first-code", [
        "$ vixl new 800x600 --background '#18283b' -o hello.vixl",
        "$ vixl -p hello.vixl text add 'Hello, Vixl' --name title \\",
        "      --size 64 --color '#ffffff'",
        "$ vixl -p hello.vixl align title center",
        "$ vixl -p hello.vixl check --checks bounds contrast",
        "$ vixl -p hello.vixl render --out hello-preview.png",
        "$ vixl -p hello.vixl export hello.png"], M, y, CW - 12, size=26, title="hello.vixl")
    ops += panel
    py = y + h + 90
    # The result, drawn as the real layers at 70%.
    ops += [label("first-result", "The result", M, py),
            rect("hello-shadow", M + 12, py + 62, 560, 420, BLUE),
            rect("hello-canvas", M, py + 50, 560, 420, "#18283b"),
            boxed("hello-title", "Hello, Vixl", M, py + 228, 560, 45, WHITE, BODY, "center")]
    steps = ["**new** makes an 800 × 600 document with a background.",
             "**text add** puts a real text layer on it, named *title*.",
             "**align** centres it. Names let you address layers later.",
             "**check** measures bounds and contrast and reports back.",
             "**render** previews; **export** writes the PNG. Look before you hand it over."]
    ops.append(prose("first-steps", "\n".join(f"{i + 1}. {s}" for i, s in enumerate(steps)),
                     M + 640, py + 50, CW - 640, 30))
    ops.append(prose("first-note", "Editing commands save as they go. Changed your mind? "
                     "`vixl -p hello.vixl undo`.", M, py + 540, CW, 30, MUTED))
    return ops


def loop():
    ops = [page("loop", "04 · The working loop", "The review loop: everything in Vixl follows it."),
           *opener("loop", "04", "The working loop",
                   "Every piece follows the same six steps. The last three repeat until the checks pass and "
                   "the preview looks right.")]
    steps = [("Create", "Size, background, fonts", "new · page add"),
             ("Apply", "Operations, atomically", "text · shape · apply"),
             ("Inspect", "Layers and their bounds", "inspect · layers"),
             ("Check", "Explicit, measured rules", "check · assert"),
             ("Preview", "Look at the pixels", "render"),
             ("Export", "The right format", "export")]
    x0, y0, cw, ch, gx, gy = M, 830, 420, 300, 70, 150
    for i, (name, detail, cmd) in enumerate(steps):
        col, row = i % 3, i // 3
        x, y = x0 + col * (cw + gx), y0 + row * (ch + gy)
        accent = BLUE if i < 3 else (INK if i < 5 else BLUE)
        ops += [*card(f"step-{i}", x, y, cw, ch, WHITE, BLUE if i in (3, 4) else INK),
                text(f"step-{i}-num", f"0{i + 1}", x + 36, y + 32, 28, DEEP if accent == BLUE else accent, MONO),
                text(f"step-{i}-name", name, x + 36, y + 80, 56, INK, DISPLAY),
                text(f"step-{i}-detail", detail, x + 36, y + 162, 28, MUTED),
                text(f"step-{i}-cmd", cmd, x + 36, y + 232, 24, DEEP, MONO)]
        if col < 2:
            ops.append(dict(type="shape", shape="arrow", name=f"step-{i}-arrow",
                            x=x + cw + 14, y=y + ch / 2 - 18, width=gx - 22, height=36, fill=INK))
    # Return path: up out of Preview, across the gap between the rows, into Inspect.
    px, ix, top, mid = x0 + (cw + gx) + cw / 2, x0 + 2 * (cw + gx) + cw / 2, y0 + ch + 14, y0 + ch + gy / 2 + 6
    ops += [dict(type="shape", shape="path", name="loop-back", x=ix, y=top,
                 path=f"M{px - ix} {y0 + ch + gy - top} L{px - ix} {mid - top} L0 {mid - top} L0 20",
                 fill="none", stroke=BLUE, stroke_width=5, closed=False),
            icon("loop-back-head", "isosceles-triangle", ix - 15, top - 2, 30, BLUE),
            boxed("loop-back-tag", "again", px + 18, mid - 46, 200, 24, DEEP, MONO, "left")]
    ly = y0 + 2 * ch + gy + 110
    ops += [*card("loop-note", x0, ly, CW - 12, 190, TINT, BLUE),
            label("loop-note-label", "Not right yet?", x0 + 48, ly + 40),
            prose("loop-note-body", "Revise, then inspect, check and preview again. `undo` and `checkpoint` "
                  "make experiments cheap: nothing you try is permanent.", x0 + 48, ly + 88, CW - 110, 31)]
    return ops


def anatomy():
    ops = [page("anatomy", "05 · Inside a .vixl file", "Exploded view of a document."),
           *opener("anatomy", "05", "Inside a\n.vixl file",
                   "A Vixl document is one portable file. Fonts and images travel inside it, so it renders "
                   "the same on any machine.")]
    # Exploded stack of planes.
    sx, sy = M + 10, 900
    planes = [("Background", PALE), ("Shapes & images", MID), ("Text", BLUE), ("Effects & checks", INK)]
    for i, (name, fill) in enumerate(planes):
        x, y = sx + i * 36, sy + (len(planes) - 1 - i) * 145
        ops += [dict(type="shape", shape="parallelogram", name=f"plane-{i}", x=x, y=y, width=520, height=130,
                     fill=fill, stroke=INK, stroke_width=2, slant=0.25),
                rule(f"plane-{i}-leader", x + 470, y + 64, sx + 760 - x - 490, INK, 2),
                label(f"plane-{i}-label", name, sx + 790, y + 52, INK)]
    parts = [("Layers", "Every element is a named layer with a stable ID: text, shapes, paths, images, "
              "groups, paint, charts, fields."),
             ("Pages & masters", "Decks, booklets and carousels. Masters hold what repeats, like the "
              "header on this page."),
             ("Variables", "Write `$${headline}` once, then export a hundred versions with different copy."),
             ("History", "Undo, redo, named checkpoints and branches. Try something bold; come back.")]
    gy = 1580
    for i, (title, body) in enumerate(parts):
        x = M + (i % 2) * 710
        y = gy + (i // 2) * 230
        ops += [rect(f"part-{i}-bar", x, y, 6, 170, BLUE),
                text(f"part-{i}-title", title, x + 34, y - 4, 40, INK, DISPLAY),
                prose(f"part-{i}-body", body, x + 34, y + 58, 620, 28, MUTED)]
    return ops


def interfaces():
    ops = [page("ways", "06 · Four ways in", "CLI, Python, MCP, REST: same operations."),
           *opener("ways", "06", "Four ways in",
                   "The command line, Python, an AI agent over MCP or any HTTP client: they all speak the "
                   "same JSON operations, so what works in one works in all four.")]
    blocks = [("CLI", "For you, in a terminal", [
                  "$ vixl -p poster.vixl text add 'Sale'",
                  "$ vixl -p poster.vixl undo"]),
              ("Python", "For scripts and notebooks", [
                  "p = Project.load('poster.vixl')",
                  "p.apply([{'type': 'opacity',",
                  "  'target': 'logo', 'value': 0.7}])",
                  "p.save()"]),
              ("MCP", "For AI agents", [
                  "$ vixl mcp --workspace . \\",
                  "    --tools core --schema slim"]),
              ("REST", "For any HTTP client", [
                  "$ vixl -p poster.vixl serve",
                  "$ curl 127.0.0.1:8765/render \\",
                  "    -o preview.png"])]
    y = 820
    for i, (name, who, lines) in enumerate(blocks):
        col, row = i % 2, i // 2
        x = M + col * 712
        by = y + row * 470
        ops += [text(f"way-{i}-name", name, x, by, 64, INK, DISPLAY),
                label(f"way-{i}-who", who, x, by + 92, MUTED, 22)]
        lines = lines + [""] * (4 - len(lines))  # equal panels: every panel holds four lines
        panel, _ = code(f"way-{i}-code", lines, x, by + 150, 676, size=23, pad=34)
        ops += panel
    ops.append(prose("ways-note", "Every operation has a schema: `vixl schema text` lists its fields, and "
                     "`--dry-run` shows what a batch would change without changing anything.",
                     M, 1770, CW, 30, MUTED))
    return ops


def agents():
    ops = [page("agents", "07 · Working with an agent", "How to brief an agent that drives Vixl."),
           *opener("agents", "07", "Working with\nan agent",
                   "Connect an agent over MCP and it does the clicking. Your job is the brief. Good briefs "
                   "name the purpose, the place and the proof.")]
    y = 900
    ops += [*card("brief", M, y, CW, 360, NIGHT, BLUE),
            label("brief-label", "A brief that works", M + 56, y + 50, SKY),
            prose("brief-body", "“A 1080 × 1350 Instagram post for our Friday open studio. Headline *OPEN "
                  "STUDIO*, date *Friday 19:00*. Use our brand.json. Dark background, one accent. Check contrast "
                  "and safe area, show me a preview, then export PNG and keep the master.”",
                  M + 56, y + 110, CW - 112, 36, WHITE)]
    tips = [("Say what it's for", "Poster, slide, form, sticker. The purpose picks sensible defaults."),
            ("Give the real words", "Placeholder copy hides layout problems until it's too late."),
            ("Name the size and place", "A preset like *instagram-post* or *letter*, and where it will be seen."),
            ("Ask for checks", "Contrast, bounds, safe area, print. Ask to see the report."),
            ("Ask for a preview", "Look before export. Request changes by layer name."),
            ("Keep the master", "The .vixl file is the design. Exports are copies.")]
    ty = 1380
    for i, (title, body) in enumerate(tips):
        col, row = i % 2, i // 2
        x, yy = M + col * 712, ty + row * 170
        ops += [icon(f"tip-{i}-icon", "checkmark", x, yy + 6, 40, BLUE),
                text(f"tip-{i}-title", title, x + 64, yy, 34, INK, DISPLAY),
                prose(f"tip-{i}-body", body, x + 64, yy + 50, 600, 27, MUTED)]
    return ops


def gallery():
    ops = [page("make", "08 · What you can make", "Twelve kinds of work; each tile names its guide."),
           *opener("make", "08", "What you\ncan make",
                   "One engine, a lot of outputs. Each of these has its own guide in the docs folder.")]
    tiles = [("star", "Posters & social", "sizes-and-layouts"),
             ("browser-window", "Slides & decks", "slides"),
             ("document", "Fillable forms", "forms"),
             ("cube", "Charts & tables", "charts"),
             ("gear", "Diagrams", "diagrams"),
             ("flower", "Organic & painted", "organic"),
             ("play", "Motion & video", "animation-authoring"),
             ("sparkle", "Logos & icons", "production"),
             ("speech-bubble", "Emoji packs", "emojis"),
             ("magnifier", "Photo filters", "artistic-filters"),
             ("folder", "Brands & templates", "brands"),
             ("ticket", "Print with bleed", "color-and-print")]
    x0, y0, tw, th, g = M, 860, 448, 270, 28
    for i, (shape, title, guide) in enumerate(tiles):
        col, row = i % 3, i // 3
        x, y = x0 + col * (tw + g), y0 + row * (th + g)
        dark = (row + col) % 2 == 1
        fill, ink, sub, glyph = (INK, WHITE, PALE, SKY) if dark else (WHITE, INK, MUTED, BLUE)
        ops += [rect(f"tile-{i}", x, y, tw, th, fill, stroke=INK, stroke_width=2),
                icon(f"tile-{i}-icon", shape, x + 36, y + 36, 76, glyph),
                text(f"tile-{i}-title", title, x + 36, y + 150, 36, ink, DISPLAY),
                text(f"tile-{i}-guide", f"docs/{guide}.md", x + 36, y + 206, 20, sub, MONO)]
    return ops


def checks():
    ops = [page("checks", "09 · Check before you ship", "The measurable rules; run them before export."),
           *opener("checks", "09", "Check before\nyou ship",
                   "A check is a measurement, not an opinion. Ask for the ones that matter for this piece and "
                   "read what comes back.")]
    panel, h = code("check-code", ["$ vixl -p poster.vixl check --checks bounds contrast safe_area",
                                   "$ vixl -p deck.vixl check --checks deck --pages all"],
                    M, 860, CW - 12, size=26)
    ops += panel
    rows = [("bounds", "Nothing important falls off the canvas"),
            ("contrast", "Text is readable against what's behind it"),
            ("safe_area", "Key content clears platform overlays and trims"),
            ("fonts", "Every glyph comes from a real, embedded font"),
            ("min_font", "No text is too small for the output size"),
            ("print", "Ink limits, resolution, trim and bleed"),
            ("color_vision", "Meaning survives colour-vision differences"),
            ("accessibility", "Alt text, reading order and roles"),
            ("deck", "Every page of a deck, plus deck-wide rules"),
            ("placeholders", "No leftover [Label] or lorem ipsum")]
    ty = 860 + h + 90
    for i, (name, what) in enumerate(rows):
        y = ty + i * 76
        ops += [text(f"check-{i}-name", name, M, y, 30, DEEP, MONO),
                text(f"check-{i}-what", what, M + 380, y, 30, INK),
                rule(f"check-{i}-rule", M, y + 58, CW)]
    ops.append(prose("checks-note", "Thirty-four checks in all; `vixl check --help` lists them. A passing check "
                     "covers the rule you asked for, not every possible problem, so still look at the preview.",
                     M, ty + len(rows) * 76 + 40, CW, 29, MUTED))
    return ops


def export():
    ops = [page("export", "10 · Export", "Name the file people get back."),
           *opener("export", "10", "Export",
                   "Choose the format by where the work is going. Exports never overwrite an existing file "
                   "unless you say so.")]
    rows = [("PNG · WebP", "Screens and the web", "Transparency, any size"),
            ("JPEG · TIFF", "Photos and print rasters", "CMYK with your printer's ICC profile"),
            ("SVG", "Scalable web graphics", "Shapes, text and gradients as vectors"),
            ("PDF", "Print and documents", "Vector pages, real text, trim and bleed"),
            ("Fillable PDF", "Forms people fill in", "Real form fields over the artwork"),
            ("PPTX", "Presentations", "Editable text, charts and speaker notes"),
            ("HTML", "Present from a browser", "One file with a speaker view"),
            ("PSD", "Handoff to Photoshop", "Named pixel layers and groups"),
            ("WebP · GIF · MP4", "Motion", "Timelines; MP4 needs ffmpeg")]
    ty = 830
    ops += [rect("export-head", M, ty, CW, 70, INK),
            label("export-h1", "Format", M + 30, ty + 22, WHITE, 22),
            label("export-h2", "For", M + 440, ty + 22, WHITE, 22),
            label("export-h3", "What survives", M + 880, ty + 22, WHITE, 22)]
    for i, (fmt, use, keeps) in enumerate(rows):
        y = ty + 70 + i * 92
        if i % 2:
            ops.append(rect(f"export-band-{i}", M, y, CW, 92, TINT))
        ops += [text(f"export-{i}-fmt", fmt, M + 30, y + 26, 32, INK, DISPLAY),
                text(f"export-{i}-use", use, M + 440, y + 30, 28, INK),
                text(f"export-{i}-keeps", keeps, M + 880, y + 30, 26, MUTED)]
    end = ty + 70 + len(rows) * 92
    ops += [rule("export-end", M, end, CW, INK, 2)]
    panel, _ = code("export-code", ["$ vixl -p deck.vixl export deck.pdf",
                                    "$ vixl -p deck.vixl export deck.pptx",
                                    "$ vixl -p post.vixl export post.png --pages all"],
                    M, end + 80, CW - 12, size=26)
    ops += panel
    return ops


def trouble():
    ops = [page("trouble", "11 · When things go wrong", "Common symptoms and the fix."),
           *opener("trouble", "11", "When things\ngo wrong",
                   "Start with `vixl --version` and the exact error. Errors are structured: they name the "
                   "field and usually suggest the fix.")]
    rows = [("`vixl` is not found", "Reopen the terminal or activate the environment you installed into."),
            ("A command edits the wrong file", "Always pass `-p file.vixl`. MCP tools take `document=`."),
            ("Unknown operation or field", "Check `vixl schema NAME` and follow the error's suggestions."),
            ("Layer not found", "Inspect the layers and pages; use the stable ID if names change."),
            ("Text is cut off or tiny", "Inspect its bounds, give it a bigger box, review at real size."),
            ("Export refuses the file", "It won't overwrite. Pick a fresh name or pass overwrite."),
            ("PDF import or `serve` missing", "Install the `pdf` or `server` extra in the same environment.")]
    y = 900
    for i, (symptom, fix) in enumerate(rows):
        yy = y + i * 150
        ops += [icon(f"trouble-{i}-icon", "warning", M, yy + 4, 40, BLUE if i % 2 else INK),
                prose(f"trouble-{i}-symptom", f"**{symptom}**", M + 70, yy, 560, 30),
                prose(f"trouble-{i}-fix", fix, M + 660, yy, CW - 660, 29, MUTED),
                rule(f"trouble-{i}-rule", M, yy + 120, CW)]
    by = y + len(rows) * 150 + 30
    panel, _ = code("recover", ["# get a design back",
                                "$ vixl -p campaign.vixl undo",
                                "$ vixl -p campaign.vixl checkout approved-layout"], M, by, CW - 12, size=26)
    ops += panel
    return ops


def cheatsheet():
    ops = [page("cheat", "12 · Cheat sheet", "Daily commands, grouped."),
           text("cheat-title", "Cheat sheet", M - 4, 230, 104, INK, DISPLAY),
           prose("cheat-lead", "Add `-p file.vixl` to each. `vixl COMMAND --help` explains any of them.",
                 M, 380, CW, 36, MUTED)]
    groups = [("Documents", [("new 1080x1350 -o a.vixl", "Start a document"),
                             ("inspect", "What's in it"),
                             ("pages", "List pages and masters")]),
              ("Make", [("text add 'Hi' --name t", "Add text"),
                        ("shape rectangle --name r", "Add a shape"),
                        ("chart · table · diagram", "Data and structure")]),
              ("Arrange", [("align t center", "Align a layer"),
                           ("move t --x 40 --y 40", "Move it"),
                           ("group g a b", "Group a and b as g")]),
              ("History", [("undo · redo", "Step back and forward"),
                           ("checkpoint v1", "Name this moment"),
                           ("checkout v1", "Return to it")]),
              ("Review", [("check --checks contrast", "Measure"),
                          ("render --out p.png", "Preview"),
                          ("view", "Live review in a browser")]),
              ("Ship", [("export out.pdf", "Write a file"),
                        ("export s.png --pages all", "One image per page"),
                        ("mcp --workspace .", "Hand it to an agent")])]
    y0, colw = 520, 700
    for gi, (group, cmds) in enumerate(groups):
        col, row = gi % 2, gi // 2
        x, y = M + col * (colw + 0), y0 + row * 470
        ops += [label(f"cheat-{gi}-label", group, x, y), rule(f"cheat-{gi}-rule", x, y + 48, colw - 40, INK, 2)]
        for ci, (cmd, what) in enumerate(cmds):
            cy = y + 82 + ci * 120
            ops += [text(f"cheat-{gi}-{ci}-cmd", cmd, x, cy, 27, INK, MONO),
                    text(f"cheat-{gi}-{ci}-what", what, x, cy + 46, 26, MUTED)]
    return ops


def back():
    mw, mh = logo_size(3.2, "mark")
    return [dict(type="page", action="add", name="back", master="none", background=INK,
                 notes="Back cover and colophon.", variables={"section": "Colophon"}),
            *logo("back-mark", (W - mw) / 2, 430, 3.2, WHITE, REVERSE_RIPPLE, kind="mark"),
            boxed("back-line", "Ideas become editable.", 0, 430 + mh + 120, W, 86, WHITE, DISPLAY, "center"),
            boxed("back-links", "github.com/jxburros/Vixl  ·  docs/README.md", 0, 430 + mh + 270, W, 30, PALE,
                  MONO, "center"),
            rule("back-rule", M, H - 640, CW, "#3A4256", 2),
            label("colophon-label", "About this guide", M, H - 590, SKY, 22),
            prose("colophon", "This booklet is a Vixl document: every word is a live text layer, every mark a "
                  "path. It was built by `examples/build_user_guide.py`, checked for bounds, contrast and fonts, "
                  "and exported to PDF. Set in Inter Tight, Inter and JetBrains Mono.",
                  M, H - 535, CW, 30, PALE),
            *bands("back-bands", -60, H - 230, W + 120, 150, REVERSE_RIPPLE, unit=7)]


# Build --------------------------------------------------------------------------------------------
PAGES = [cover, contents, what_it_is, install, first_design, loop, anatomy, interfaces, agents, gallery,
         checks, export, trouble, cheatsheet, back]


def build(output, overwrite=True):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    project = Project(W, H, PAPER)
    project.apply([dict(type="canvas", dpi=200)])
    for family, weight, italic in [("Inter Tight", 800, False), ("Inter", 400, False), ("Inter", 600, False),
                                   ("Inter", 700, False), ("Inter", 400, True), ("JetBrains Mono", 500, False)]:
        install_font(project, family, weight, italic)
    project.apply(master())
    for make in PAGES:
        project.apply(make())
    project.apply([dict(type="page", action="select", page="cover")])
    report = project.check(checks=["bounds", "fonts", "contrast"], pages="all")
    project.save(output / "vixl-user-guide.vixl", overwrite=overwrite)
    project.export(output / "vixl-user-guide.pdf", overwrite=overwrite)
    contact_sheet(project, columns=5).save(output / "contact-sheet.png")
    project.export(output / "cover.png", page="cover", overwrite=overwrite)
    return project, report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="docs/user-guide")
    _, result = build(parser.parse_args().output)
    print(result if not result["passed"] else f"Built the user guide with Vixl {__version__}")
