"""``deck-from-markdown``: a Markdown file becomes a checked slide deck in one call.

``#`` and ``##`` headings (and ``---`` lines) start slides. Each slide picks a layout from what it holds:

* ``title`` — the first slide, when it is a ``#`` heading with at most two short lines under it (subtitle,
  caption): ``slide-title``;
* ``section`` — a heading with nothing under it: ``slide-title`` with the heading alone;
* ``quote`` — a slide that is one ``>`` quotation (an ``— Name`` line attributes it): ``quote-card``;
* ``content`` — anything else: ``slide-content`` for the heading, then the body as one Markdown rich-text box
  (lists, numbers, ``###`` sub-headings, ``**bold**``, ``*italic*`` …), a fenced ``csv`` block as a ``table``, a
  fenced ``chart`` block (CSV; ``chart line`` picks the kind) as a ``chart`` and ``![alt](image.png)`` as a frame.
  Text and a visual share the slide side by side.

Text in HTML comments, or after a ``Notes:`` line, becomes the page's speaker notes. Every page uses one master
(the deck background and a page number) and the same layout palette and seed, so the deck is consistent. The deck
checks run at the end and are reported. Re-running on an existing output rebuilds only the slides whose Markdown
changed, removes slides that were deleted from the Markdown, and leaves pages the workflow did not make alone.
"""

import hashlib
import json
import re

from .errors import require

ACTIONS = {"deck-from-markdown": ({"markdown", "output", "size", "palette", "seed", "fonts", "export", "overwrite",
                                  "check"}, {"markdown", "output"})}
FIELD_TYPES = {
    "markdown": {"type": "string", "description": "Workspace-relative Markdown file (.md)."},
    "output": {"type": "string", "description": "The deck document (.vixl). When it exists and was made by this "
               "workflow, only changed slides are rebuilt."},
    "size": {"type": "string", "default": "slide", "description": "Named slide size (slide, slide-4x3, slide-16x10, "
             "instagram-portrait …)."},
    "palette": {"type": "string", "description": "Layout palette for every slide (default: rolled once from seed)."},
    "seed": {"type": "integer", "default": 1, "description": "Layout seed shared by every slide."},
    "fonts": {"type": "string", "description": "Font pairing to install and use (vixl_font_pair names, or random); "
              "default: the workspace's brand.json fonts."},
    "export": {"type": "array", "items": {"type": "string", "enum": ["pptx", "pdf", "html", "png"]},
               "description": "Formats to export next to the deck (deck.pptx, deck.pdf, deck.html …)."},
    "overwrite": {"type": "boolean", "default": False, "description": "Replace a deck this workflow did not make, "
                  "and existing exports."},
    "check": {"type": "boolean", "default": True, "description": "Run the deck checks and report their findings."},
}
MAX_SLIDES = 200
FENCE = re.compile(r"^(```|~~~)\s*([\w-]*)\s*([\w-]*)\s*$")
IMAGE = re.compile(r"^!\[([^\]]*)\]\(([^)\s]+)\)\s*$")


def slug(text, taken):
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "slide"
    name, index = base, 2
    while name in taken:
        name, index = f"{base}-{index}", index + 1
    taken.add(name)
    return name


def split(markdown):
    """Slides from Markdown: ``[{level, title, body: [lines], notes: [lines], blocks: [...]}]``."""
    slides, current, fence, notes_mode = [], None, None, False

    def start(level, title):
        nonlocal current, notes_mode
        current = {"level": level, "title": title.strip(), "body": [], "notes": [], "blocks": []}
        slides.append(current)
        notes_mode = False

    text = markdown.replace("\r\n", "\n")
    # Comments become notes wherever they are, even across lines.
    comments = []

    def stash(match):
        comments.append(match.group(1).strip())
        return f"{len(comments) - 1}"

    text = re.sub(r"<!--(.*?)-->", stash, text, flags=re.S)
    for line in text.split("\n"):
        if fence is not None:
            if FENCE.match(line.strip()) and line.strip().startswith(fence["marker"]) and not FENCE.match(line.strip()).group(2):
                current["blocks"].append({"kind": fence["kind"], "info": fence["info"], "text": "\n".join(fence["lines"])})
                fence = None
            else:
                fence["lines"].append(line)
            continue
        heading = re.match(r"^(#{1,2})\s+(.*\S)\s*$", line)
        if heading:
            start(len(heading.group(1)), heading.group(2))
            continue
        if re.fullmatch(r"\s*(-{3,}|\*{3,})\s*", line) and current is not None and (current["body"] or current["blocks"]):
            start(2, "")
            continue
        if current is None:
            if not line.strip():
                continue
            start(2, "")
        for index in map(int, re.findall(r"(\d+)", line)):
            current["notes"].append(comments[index])
        line = re.sub(r"\d+", "", line)
        if notes_mode:
            current["notes"].append(line)
            continue
        note = re.match(r"^\s*(?:speaker\s+)?notes?:\s*(.*)$", line, re.I)
        if note:
            notes_mode = True
            if note.group(1).strip():
                current["notes"].append(note.group(1))
            continue
        fenced = FENCE.match(line.strip())
        if fenced:
            fence = {"marker": fenced.group(1), "kind": fenced.group(2).lower() or "code", "info": fenced.group(3).lower(),
                     "lines": []}
            continue
        image = IMAGE.match(line.strip())
        if image:
            current["blocks"].append({"kind": "image", "alt": image.group(1), "path": image.group(2)})
            continue
        current["body"].append(line)
    if fence is not None and current is not None:
        current["blocks"].append({"kind": fence["kind"], "info": fence["info"], "text": "\n".join(fence["lines"])})
    for slide in slides:
        while slide["body"] and not slide["body"][-1].strip():
            slide["body"].pop()
        while slide["body"] and not slide["body"][0].strip():
            slide["body"].pop(0)
        slide["notes"] = "\n".join(line for line in slide["notes"]).strip()
    return [s for s in slides if s["title"] or s["body"] or s["blocks"]]


def classify(slide, first):
    body = [line for line in slide["body"] if line.strip()]
    if not body and not slide["blocks"]:
        return "title" if first and slide["level"] == 1 else "section"
    if first and slide["level"] == 1 and not slide["blocks"] and len(body) <= 2 and all(
            not re.match(r"\s*([-*+]|\d+[.)]|>)\s", line) and len(line) <= 120 for line in body):
        return "title"
    if not slide["blocks"] and body and all(line.lstrip().startswith(">") or re.match(r"\s*(—|--|-|~)\s*\w", line)
                                            for line in body) and body[0].lstrip().startswith(">"):
        return "quote"
    return "content"


def rows_from_csv(text, where):
    import csv
    import io

    rows = [row for row in csv.reader(io.StringIO(text.strip())) if row]
    require(rows and len(rows) >= 2, f"{where}: a csv block needs a header row and at least one row", field="markdown")
    width = len(rows[0])
    return [row + [""] * (width - len(row)) if len(row) < width else row[:width] for row in rows]


def numeric(rows):
    from .charts import cell_number

    out = [rows[0]]
    for i, row in enumerate(rows[1:], 1):
        out.append([row[0], *[cell_number(value, f"row {i}") for value in row[1:]]])
    return out


def fingerprint(slide, settings):
    data = json.dumps([slide, settings], sort_keys=True, default=str)
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def _bounds(project, name):
    from .render import resolve_layout

    layer = next((item for item in project.state["layers"] if item["name"] == name), None)
    return resolve_layout(project)[layer["id"]] if layer else None


def build_slide(project, session, slide, kind, number, settings, report):
    """Add one slide's layers to the active page."""
    canvas = project.state["canvas"]
    W, H = canvas["width"], canvas["height"]
    base = {"type": "layout-apply", "seed": settings["seed"], "transparent": True, "unfilled": "omit",
            "base_size": settings["body_size"], **({"palette": settings["palette"]} if settings.get("palette") else {})}
    body = [line for line in slide["body"] if line.strip()]
    if kind == "title":
        result = project.apply({**base, "name": "slide-title", "title": slide["title"] or "Untitled",
                                **({"subtitle": body[0].strip()} if body else {}),
                                **({"caption": body[1].strip()} if len(body) > 1 else {})}, detail="brief")
        return result
    if kind == "section":
        return project.apply({**base, "name": "slide-title", "title": slide["title"] or "—"}, detail="brief")
    if kind == "quote":
        quote = " ".join(line.lstrip()[1:].strip() for line in body if line.lstrip().startswith(">"))
        credit = next((re.sub(r"^\s*(—|--|-|~)\s*", "", line) for line in body if not line.lstrip().startswith(">")), None)
        return project.apply({**base, "name": "quote-card", "title": quote, **({"subtitle": credit} if credit else {})},
                             detail="brief")
    result = project.apply({**base, "name": "slide-content", "title": slide["title"] or " "}, detail="brief")
    # The layout's own image placeholder is not used: visuals are placed in the content area below.
    blanks = [item["layer"] for item in (result.get("layout") or {}).get("blanks", [])]
    blanks = [ident for ident in blanks if any(layer["name"] == ident or layer["id"] == ident
                                               for layer in project.state["layers"])]
    if blanks:
        project.apply({"type": "remove", "targets": blanks})
    margin = round((result.get("layout") or {}).get("margin", W * 0.05))
    title = _bounds(project, "title")
    top = round(title[1] + title[3] + max(24, H * 0.04)) if title else margin * 2
    bottom = H - margin - round(H * 0.06)
    left, width = margin, W - 2 * margin
    visuals = [block for block in slide["blocks"] if block["kind"] in ("csv", "table", "chart", "image")]
    code = [block for block in slide["blocks"] if block["kind"] not in ("csv", "table", "chart", "image")]
    text = "\n".join(slide["body"])
    if code:
        text += "".join("\n" + "\n".join(f"[{line or ' '}]{{font=body}}" for line in block["text"].split("\n"))
                        for block in code)
    gap = round(W * 0.03)
    text_box = visual_box = None
    if text.strip() and visuals:
        half = (width - gap) // 2
        text_box = (left, top, half, bottom - top)
        visual_box = (left + half + gap, top, width - half - gap, bottom - top)
    elif text.strip():
        text_box = (left, top, width, bottom - top)
    elif visuals:
        visual_box = (left, top, width, bottom - top)
    ops = []
    size = settings["body_size"]
    ink = "@ink" if "ink" in project.state.get("swatches", {}) else None
    if text_box:
        ops.append({"type": "rich-text", "name": "body", "markdown": text.strip(), "x": text_box[0], "y": text_box[1],
                    "width": text_box[2], "height": text_box[3], "size": size, "fit": True,
                    **({"color": ink} if ink else {})})
    if visual_box:
        x, y, w, h = visual_box
        share = (h - gap * (len(visuals) - 1)) // max(1, len(visuals))
        for index, block in enumerate(visuals):
            box_y = y + index * (share + gap)
            name = f"visual-{index + 1}"
            if block["kind"] in ("csv", "table"):
                rows = rows_from_csv(block["text"], f"slide {number}")
                ops.append({"type": "table", "name": name, "x": x, "y": box_y, "width": w, "table": rows,
                            "font_size": settings["table_size"], **({"text_color": ink} if ink else {})})
            elif block["kind"] == "chart":
                rows = numeric(rows_from_csv(block["text"], f"slide {number}"))
                ops.append({"type": "chart", "name": name, "x": x, "y": box_y, "width": w, "height": share,
                            "table": rows, "kind": block["info"] or "bar", "font_size": settings["chart_size"],
                            **({"text_color": ink} if ink else {})})
            else:
                from .assets import add_encoded, read_bounded

                path = session.resolve(block["path"])
                require(path.is_file(), f"slide {number}: image {block['path']!r} not found in the workspace",
                        "not_found", field="markdown")
                asset, _ = add_encoded(project, read_bounded(path, project.limits.max_asset_bytes))
                ops.append({"type": "frame", "name": name, "asset": asset, "x": x, "y": box_y, "width": w,
                            "height": share, "fit": "fit"})
    if ops:
        project.apply(ops)
        for op in ops:
            if op["type"] == "table":
                table = project.layer(op["name"])
                if table["height"] > visual_box[3]:
                    report.append(f"slide {number}: the table is taller than the slide's content area")
    return result


def run(session, request):
    from .project import Project

    for key in ("overwrite", "check"):
        require(type(request.get(key, True)) is bool, f"{key} must be true or false", field=key)
    source = session.resolve(request["markdown"])
    require(source.is_file(), f"Markdown file not found in the workspace: {request['markdown']}", "not_found",
            field="markdown")
    from .assets import read_bounded

    markdown = read_bounded(source, 4 * 1024 * 1024).decode("utf-8-sig")
    slides = split(markdown)
    require(slides, "The Markdown has no slides: start each with a # or ## heading", field="markdown")
    require(len(slides) <= MAX_SLIDES, f"A deck holds at most {MAX_SLIDES} slides", "resource_limit", field="markdown")
    output = session.resolve(request["output"])
    require(output.suffix.lower() == ".vixl", "output is a .vixl document", field="output")
    overwrite = request.get("overwrite", False)
    formats = [f.lower().lstrip(".") for f in request.get("export", [])]
    require(all(f in ("pptx", "pdf", "html", "png") for f in formats), "export lists pptx, pdf, html or png",
            field="export")
    require(isinstance(request.get("seed", 1), int), "seed is a whole number", field="seed")
    existing = None
    if output.exists():
        existing = Project.load(output, limits=session.limits)
        require(existing.state.get("deck_markdown") or overwrite, f"{request['output']} exists and was not made from "
                "Markdown; set overwrite=true to replace it, or choose another output", field="output")
        if not existing.state.get("deck_markdown"):
            existing = None
    project = existing or Project(1920, 1080, "#ffffff", limits=session.limits)
    project._workspace = session.workspace
    record = project.state.get("deck_markdown") or {}
    settings = {"seed": request.get("seed", record.get("seed", 1)), "palette": request.get("palette", record.get("palette"))}
    notes_out = {}
    created = existing is None
    if created:
        project.apply({"type": "canvas", "size": request.get("size", "slide")})
        from .brand import apply_workspace_fonts

        fonts = {"workspace": apply_workspace_fonts(project, session.workspace)}
        if request.get("fonts"):
            from .typefaces import pair_fonts

            fonts["pairing"] = pair_fonts(project, request["fonts"])
        notes_out["fonts"] = {k: v for k, v in fonts.items() if v}
    canvas = project.state["canvas"]
    W, H = canvas["width"], canvas["height"]
    from .deck import points_per_pixel

    pt = points_per_pixel(canvas)
    # Body text, tables and chart labels stay above the deck check's 18 pt minimum on the exported slide (a chart
    # sets its smallest labels a step below its font_size).
    settings["body_size"] = max(round(20 / pt), round(H * 0.037))
    settings["table_size"] = settings["body_size"]
    settings["chart_size"] = round(settings["table_size"] * 1.25)
    taken = set()
    plan = []
    for number, slide in enumerate(slides, 1):
        kind = classify(slide, number == 1)
        name = slug(slide["title"] or f"slide-{number}", taken)
        plan.append((name, kind, slide, fingerprint({**slide, "kind": kind, "notes": ""},
                                                    {k: settings[k] for k in ("seed", "body_size")})))
    previous = record.get("pages", {})
    pages = {page["name"] for page in project.state.get("pages", [])}
    findings = []
    rebuilt, kept = [], []
    masters = project.state.get("masters") or {}
    if created or "deck" not in (masters if isinstance(masters, dict) else {m.get("name") for m in masters}):
        from .sizes import safe_sides

        project.apply({"type": "master", "action": "add", "name": "deck"})
        project.apply({"type": "text", "name": "page-number", "text": "${pages} / ${pages}",
                       "size": max(round(16 / pt), round(H * 0.022)), "color": "#6b7280"})
        number_layer = project.layer("page-number")
        right, bottom = safe_sides(canvas)[2:]
        project.apply({"type": "move", "target": "page-number",
                       "x": W - max(right, round(W * 0.04)) - number_layer["width"] * 2,
                       "y": H - max(bottom, round(H * 0.04)) - number_layer["height"]})
        project.apply({"type": "text-set", "target": "page-number", "text": "${page} / ${pages}"})
    first_layout = None
    for index, (name, kind, slide, digest) in enumerate(plan):
        if name in pages and previous.get(name) == digest:
            project.apply({"type": "page", "action": "set", "page": name, "notes": slide["notes"] or ""})
            kept.append(name)
            continue
        if name in pages:
            project.apply({"type": "page", "action": "select", "page": name})
            top = [layer["id"] for layer in project.state["layers"] if not layer.get("parent")]
            if top:
                project.apply({"type": "remove", "targets": top})
            project.apply({"type": "page", "action": "set", "page": name, "notes": slide["notes"] or "", "master": "deck"})
        else:
            project.apply({"type": "page", "action": "add", "name": name, "master": "deck",
                           **({"notes": slide["notes"]} if slide["notes"] else {})})
            pages.add(name)
        result = build_slide(project, session, slide, kind, index + 1, settings, findings)
        layout = (result or {}).get("layout") or {}
        if first_layout is None and layout:
            first_layout = layout
            settings["palette"] = settings.get("palette") or layout.get("palette")
        rebuilt.append(name)
    # Slides deleted from the Markdown go; pages made by hand stay.
    gone = [name for name in previous if name not in {p[0] for p in plan} and name in pages]
    for name in gone:
        project.apply({"type": "page", "action": "remove", "page": name})
    order = [p[0] for p in plan]
    for position, name in enumerate(order, 1):
        project.apply({"type": "page", "action": "move", "page": name, "index": position})
    blank = [page["name"] for page in project.state.get("pages", []) if page["name"] not in order
             and page["name"] not in previous and created]
    for name in blank:  # the starting page a new document had
        project.apply({"type": "page", "action": "remove", "page": name})
    if first_layout:
        roles = {role["role"]: role["color"] for role in first_layout.get("roles", [])}
        if roles.get("background"):
            project.apply({"type": "master", "action": "set", "name": "deck", "background": roles["background"]})
        if roles.get("muted"):
            master_number = {"type": "master", "action": "select", "name": "deck"}
            project.apply([master_number, {"type": "text-set", "target": "page-number", "color": roles["muted"]}])
    project.apply({"type": "page", "action": "select", "page": order[0]})
    project.state["deck_markdown"] = {"source": session.relative(source), "seed": settings["seed"],
                                      "palette": settings.get("palette"),
                                      "pages": {name: digest for name, _, _, digest in plan}}
    project.path, project._revision = output, None
    session.make_parent(output)
    project.save(output, overwrite=True if existing is not None or overwrite else False)
    summary = {"output": session.relative(output), "slides": len(plan),
               "pages": [{"page": name, "layout": kind, "notes": bool(slide["notes"])} for name, kind, slide, _ in plan],
               "rebuilt": rebuilt, "kept": kept, **({"removed": gone} if gone else {}),
               **({"warnings": findings} if findings else {}), **notes_out}
    if request.get("check", True):
        from .deck import check_deck

        checked = check_deck(project)
        issues = checked.get("issues", [])
        summary["check"] = {"passed": checked.get("passed"), "fix": sum(1 for i in issues if i.get("action") == "fix"),
                            "review": sum(1 for i in issues if i.get("action") == "review"),
                            "issues": [{k: i[k] for k in ("check", "severity", "message", "action", "pages") if k in i}
                                       for i in issues][:40]}
    if formats:
        from .export_batch import export_batch
        from .mcp_tools import export_file

        targets = [{"path": session.relative(output.with_suffix("." + f)), "document": session.relative(output)}
                   for f in formats]
        summary["exports"] = export_batch(session, export_file, targets, overwrite=overwrite)["results"]
    return summary


def dispatch(session, action, request, document=None):
    return run(session, request)

