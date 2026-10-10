"""The ``brand-board`` workflow: a brand guidelines document drawn from ``brand.json``.

One slide-sized page per topic, each built from the brand's data only: a cover (name, preset, first logo),
the palette (role swatches with hex values, extra approved colours, and the text/background contrast pairs
judged against ``minimum_contrast``), the type ladder in two pages (every text stage set in its own font,
size and line height, with the role and face it resolves to), the logos (on the light and dark brand colours,
with the clear-space zone drawn) and the rules (do and don't notes for whatever the brand constrains). The
result is an ordinary editable document; it exports to PDF, PPTX or HTML like any deck, and nothing is
overwritten unless ``overwrite`` is true.
"""

from pathlib import Path

from .errors import VixlError, require

FIELDS = {"output", "preset", "title", "document", "overwrite"}
FORMATS = {".pdf": "PDF", ".pptx": "PPTX", ".html": "HTML"}
W, H, M = 1920, 1080, 120
SPECIMEN = {"display": "Aa Display", "h1": "Heading one", "h2": "Heading two", "h3": "Heading three",
            "subtitle": "A subtitle that frames the page", "lead": "A lead paragraph opens the story.",
            "body": "Body copy carries the reading: steady, even and easy on the eye.",
            "caption": "Caption: a note that sits beside a picture", "citation": "Citation: Author, Title (2026)",
            "label": "Label"}
# Text on background pairs every brand guide states, as (foreground role, background role).
PAIRS = (("ink", "background"), ("muted", "background"), ("accent-text", "background"), ("on-accent", "accent"),
         ("ink", "surface"))


def field_types():
    path = {"type": "string", "description": "Workspace-relative path."}
    return {
        "output": {**path, "description": "The guidelines file: .pdf, .pptx or .html (one page per topic), or .vixl "
                   "for the editable document only."},
        "preset": {"type": "string", "description": "A preset from brand.json presets (default: the base brand)."},
        "title": {"type": "string", "description": "Cover title (default: the brand name, else 'Brand guidelines')."},
        "document": {**path, "description": "Also save the editable board as this .vixl."},
        "overwrite": {"type": "boolean", "default": False, "description": "Replace existing output files."},
    }


def _hex(value, state):
    from .design import resolve_color
    from .render import color

    r, g, b, _ = color(resolve_color(value, state))
    return f"#{r:02x}{g:02x}{b:02x}"


def _contrast(fg, bg, state):
    from .colors import contrast_ratio, parse

    return contrast_ratio(parse(_hex(fg, state))[:3], parse(_hex(bg, state))[:3])


def _text(name, text, x, y, *, stage="body", color="@ink", **extra):
    return {"type": "text", "name": name, "text": text, "x": round(x), "y": round(y), "stage": stage, "color": color,
            **extra}


def _heading(ops, page, title, kicker):
    ops.append({"type": "page", "action": "add", "name": page})
    ops.append({"type": "solid", "name": f"{page}-ground", "color": "@background"})
    ops.append(_text(f"{page}-kicker", kicker, M, M - 40, stage="label", color="@muted"))
    ops.append(_text(f"{page}-title", title, M, M, stage="h2"))


def _cover(ops, kit, title, logo_assets):
    ops.append({"type": "page", "action": "add", "name": "cover"})
    ops.append({"type": "solid", "name": "cover-ground", "color": "@background"})
    ops.append({"type": "shape", "shape": "rectangle", "name": "cover-band", "x": 0, "y": H - 160, "width": W,
                "height": 160, "fill": "@accent"})
    ops.append(_text("cover-title", title, M, H * 0.42, stage="display"))
    subtitle = "Brand guidelines" + (f" · {kit['preset']}" if kit.get("preset") else "")
    ops.append(_text("cover-subtitle", subtitle, M, H * 0.42 + 170, stage="subtitle", color="@muted"))
    if logo_assets:
        asset, (w, h) = logo_assets[0]
        scale = min(360 / w, 240 / h)
        ops.append({"type": "add", "name": "cover-logo", "asset": asset, "x": round(W - M - w * scale), "y": M,
                    "width": max(1, round(w * scale)), "height": max(1, round(h * scale))})


def _palette(ops, kit, state, minimum):
    from .brand import extra_colors, role_colors

    _heading(ops, "palette", "Colour", "Palette")
    roles = role_colors(kit)
    extras = extra_colors(kit)
    columns = max(1, len(roles))
    width = (W - 2 * M - (columns - 1) * 24) / columns
    for index, (role, value) in enumerate(roles.items()):
        x = M + index * (width + 24)
        ops.append({"type": "shape", "shape": "rectangle", "name": f"swatch-{role}", "x": round(x), "y": 280,
                    "width": round(width), "height": 220, "fill": f"@{role}", "stroke": "@muted", "stroke_width": 1})
        ops.append(_text(f"swatch-{role}-name", role, x, 516, stage="label"))
        ops.append(_text(f"swatch-{role}-hex", _hex(value, state), x, 548, stage="caption", color="@muted"))
    y = 620
    if extras:
        ops.append(_text("extra-heading", "Extra approved colours", M, y, stage="h3"))
        for index, (name, spec) in enumerate(list(extras.items())[:10]):
            x = M + index * 170
            ops.append({"type": "shape", "shape": "rectangle", "name": f"extra-{index + 1}", "x": x, "y": y + 60,
                        "width": 140, "height": 80, "fill": spec["color"], "stroke": "@muted", "stroke_width": 1})
            note = _hex(spec["color"], state) + (f" ≤{spec['max_fraction']:.0%}" if "max_fraction" in spec else "")
            ops.append(_text(f"extra-{index + 1}-name", name, x, y + 150, stage="caption"))
            ops.append(_text(f"extra-{index + 1}-hex", note, x, y + 176, stage="caption", color="@muted"))
        y += 240
    pairs = [(fg, bg) for fg, bg in PAIRS if fg in roles and bg in roles]
    if pairs:
        ops.append(_text("pairs-heading", f"Text contrast (minimum {minimum:g}:1)", M, y, stage="h3"))
        for index, (fg, bg) in enumerate(pairs):
            ratio = _contrast(roles[fg], roles[bg], state)
            x = M + index * 336
            ops.append({"type": "shape", "shape": "rectangle", "name": f"pair-{fg}-{bg}", "x": x, "y": y + 60,
                        "width": 312, "height": 96, "fill": f"@{bg}", "stroke": "@muted", "stroke_width": 1})
            ops.append(_text(f"pair-{fg}-{bg}-sample", "Aa", x + 20, y + 76, stage="h3", color=f"@{fg}"))
            verdict = "passes" if ratio >= minimum else "too low"
            ops.append(_text(f"pair-{fg}-{bg}-name", f"{fg} on {bg}", x, y + 168, stage="caption"))
            ops.append(_text(f"pair-{fg}-{bg}-ratio", f"{ratio:.1f}:1 {verdict}", x, y + 196, stage="caption",
                             color="@ink"))


def _type_pages(ops, project, kit):
    from .type_roles import STAGES, describe

    ladder = describe(project)
    fonts = project.state.get("fonts", {})
    for page, stages, title in (("type-headings", STAGES[:5], "Display and headings"),
                                ("type-text", STAGES[5:], "Text, captions and labels")):
        _heading(ops, page, title, "Typography")
        y = 280
        for stage in stages:
            item = ladder[stage]
            face = item["font"] if item["font"] in fonts else "proofing font"
            meta = (f"{stage} · role {item['font_role']} · {face} · {item['size']} px · line {item['line_height']}"
                    + (f" · {item['case']}case" if item.get("case") else ""))
            ops.append(_text(f"{page}-{stage}-meta", meta, M, y, stage="caption", color="@muted"))
            ops.append(_text(f"{page}-{stage}", SPECIMEN[stage], M, y + 32, stage=stage))
            y += 32 + item["size"] * 1.35 + 36


def _logos(ops, kit, logo_assets):
    if not logo_assets:
        return
    rules = kit.get("logo") or {}
    _heading(ops, "logos", "Logo", "Logo")
    clear = rules.get("clear_space", 0)
    count = min(len(logo_assets), 3)
    cell = (W - 2 * M) / count
    for index, (asset, (w, h)) in enumerate(logo_assets[:count]):
        name = kit["logos"][index]["name"]
        for row, ground in enumerate(("@background", "@ink")):
            top = 270 + row * 330
            x0 = M + index * cell
            ops.append({"type": "shape", "shape": "rectangle", "name": f"logo-{index + 1}-ground-{row + 1}",
                        "x": round(x0), "y": top, "width": round(cell - 24), "height": 300, "fill": ground,
                        "stroke": "@muted", "stroke_width": 1})
            box_h = 300 - 2 * 40
            scale = min((cell - 24 - 80) / (w * (1 + 2 * clear)), box_h / (h * (1 + 2 * clear)))
            lw, lh = w * scale, h * scale
            lx, ly = x0 + (cell - 24 - lw) / 2, top + (300 - lh) / 2
            if clear:
                space = clear * lh
                ops.append({"type": "shape", "shape": "rectangle", "name": f"logo-{index + 1}-clear-{row + 1}",
                            "x": round(lx - space), "y": round(ly - space), "width": round(lw + 2 * space),
                            "height": round(lh + 2 * space), "fill": "none", "stroke": "@accent", "stroke_width": 2})
            ops.append({"type": "add", "name": f"logo-{index + 1}-on-{row + 1}", "asset": asset, "x": round(lx),
                        "y": round(ly), "width": max(1, round(lw)), "height": max(1, round(lh))})
        ops.append(_text(f"logo-{index + 1}-name", name, M + index * cell, 920, stage="label"))
    notes = []
    if clear:
        notes.append(f"Clear space: {clear:g} × the logo height on every side (outlined).")
    for key, label in (("min_size", "Minimum height"), ("min_width", "Minimum width")):
        if key in rules:
            value = rules[key]
            notes.append(f"{label}: {value if isinstance(value, str) else f'{value:g} px'}.")
    if notes:
        ops.append(_text("logo-notes", " ".join(notes), M, 960, stage="caption", color="@muted"))


def rules(kit, state):
    """``(do, dont)`` notes for what the brand constrains."""
    from .brand import extra_colors, font_specs, role_colors

    do, dont = [], []
    specs = font_specs(kit)
    faces = [spec.get("name") or spec.get("family") for spec in specs.values()]
    if kit.get("pairing"):
        faces.append(f"the {kit['pairing']} pairing")
    if faces:
        do.append(f"Set type in {', '.join(faces)}, by role: {', '.join(specs) or 'heading and body'}.")
    allowed = (kit.get("fonts") or {}).get("allowed")
    if allowed:
        dont.append(f"Use any family other than {', '.join(allowed)}.")
    roles = role_colors(kit)
    if roles:
        do.append(f"Colour with the palette roles ({', '.join(roles)})"
                  + (f" and the extra colours ({', '.join(extra_colors(kit))})" if extra_colors(kit) else "") + ".")
    colors = kit.get("colors") or {}
    if colors.get("strict"):
        tolerance = colors.get("tolerance", 0)
        dont.append("Use a colour outside the palette" + (f" (more than {tolerance:g} away per channel)" if tolerance
                                                           else "") + ".")
    for name, spec in extra_colors(kit).items():
        if "max_fraction" in spec:
            dont.append(f"Let {name} cover more than {spec['max_fraction']:.0%} of a design.")
    minimum = kit.get("minimum_contrast", 4.5)
    do.append(f"Keep text contrast at {minimum:g}:1 or more.")
    for fg, bg in PAIRS:
        if fg in roles and bg in roles and _contrast(roles[fg], roles[bg], state) < minimum:
            dont.append(f"Set {fg} text on {bg} ({_contrast(roles[fg], roles[bg], state):.1f}:1).")
    logo = kit.get("logo") or {}
    if logo.get("clear_space"):
        do.append(f"Keep {logo['clear_space']:g} × the logo height clear around the logo.")
    for key, label in (("min_size", "tall"), ("min_width", "wide")):
        if key in logo:
            value = logo[key]
            dont.append(f"Set the logo less than {value if isinstance(value, str) else f'{value:g} px'} {label}.")
    if kit.get("required_elements"):
        do.append(f"Include {', '.join(kit['required_elements'])} in every design.")
    return do, dont


def _rules_page(ops, kit, state):
    do, dont = rules(kit, state)
    _heading(ops, "rules", "Do and don't", "Rules")
    for column, (title, items) in enumerate((("Do", do), ("Don't", dont))):
        x = M + column * (W - 2 * M) / 2
        ops.append(_text(f"rules-{column + 1}-title", title, x, 280, stage="h3"))
        if items:
            ops.append({"type": "rich-text", "name": f"rules-{column + 1}", "markdown": "\n".join(f"- {item}" for item in items),
                        "x": round(x), "y": 350, "width": round((W - 2 * M) / 2 - 60), "color": "@ink"})


def build_document(workspace, *, preset=None, title=None, limits=None):
    """The editable brand board for the workspace brand (and ``preset``), and a report."""
    from .assets import add_encoded
    from .brand import embedded, extra_colors, load, register_fonts, role_colors
    from .project import Project
    from .variety import record_as_creation

    kit = load(workspace, preset)
    require(kit, "brand-board needs a brand.json in the workspace", field="preset")
    report = {"brand": kit.get("name"), **({"preset": preset} if preset else {})}
    project = Project.sized("slide", role_colors(kit).get("background", "#ffffff"), limits=limits, design=False)
    project._workspace = Path(workspace)
    candidate = project.clone()
    candidate.state.setdefault("swatches", {}).update({"background": "#ffffff", "surface": "#eeeeee", "ink": "#111111",
                                                       "muted": "#555555", "accent": "#0044aa",
                                                       "accent-text": "#0044aa", "on-accent": "#ffffff"})
    candidate.state["swatches"].update(role_colors(kit))
    candidate.state["swatches"].update({name: spec["color"] for name, spec in extra_colors(kit).items()})
    if preset:
        candidate.state["brand_preset"] = preset
    try:
        report["fonts"] = register_fonts(candidate, kit)
    except VixlError as exc:
        report["fonts_error"] = f"{exc}; the board uses the proofing font for the roles it could not install"
    logo_assets = []
    for spec in kit.get("logos", []):
        try:
            asset, image = add_encoded(candidate, embedded(spec["data_base64"]))
            logo_assets.append((asset, image.size))
        except VixlError as exc:
            report.setdefault("skipped", []).append(f"logo {spec['name']}: {exc}")
    project.__dict__.update(candidate.__dict__)
    record_as_creation(project, "Brand board setup")
    state = project.state
    ops = []
    _cover(ops, kit, title or kit.get("name") or "Brand guidelines", logo_assets)
    _palette(ops, kit, state, kit.get("minimum_contrast", 4.5))
    project.apply(ops, detail="compact")
    ops = []
    _type_pages(ops, project, kit)
    _logos(ops, kit, logo_assets)
    _rules_page(ops, kit, state)
    project.apply(ops, detail="compact")
    from .pages import page_list

    report["pages"] = [page["name"] for page in page_list(project)]
    return project, report


def build(session, request, document=None):
    unknown = sorted(set(request) - FIELDS)
    require(not unknown, f"Unknown brand-board field(s) {unknown}", field=unknown[0] if unknown else None)
    output = request.get("output")
    require(isinstance(output, str) and Path(output).suffix.lower() in (*FORMATS, ".vixl"),
            "output is a .pdf, .pptx, .html or .vixl path", field="output")
    for field in ("preset", "title", "document"):
        require(request.get(field) is None or isinstance(request[field], str), f"{field} must be text", field=field)
    require(type(request.get("overwrite", False)) is bool, "overwrite must be boolean", field="overwrite")
    overwrite = request.get("overwrite", False)
    destination = session.resolve(output)
    source = session.resolve(request["document"]) if request.get("document") else None
    if source is not None:
        require(source.suffix.lower() == ".vixl", "document must be a .vixl path", field="document")
    for path, field in ((destination, "output"), (source, "document")):
        if path is not None:
            require(overwrite or not path.exists(), f"{session.relative(path)} exists; set overwrite=true or choose "
                    "another path", field=field)
    project, report = build_document(session.workspace, preset=request.get("preset"), title=request.get("title"),
                                     limits=session.limits)
    written = []
    for path in (source, destination if destination.suffix.lower() == ".vixl" else None):
        if path is not None:
            session.make_parent(path)
            if path.exists():
                path.unlink()
            project.path, project._revision = None, None
            project.save(path)
            written.append(session.relative(path))
    if destination.suffix.lower() in FORMATS:
        session.make_parent(destination)
        project.export(destination, format=FORMATS[destination.suffix.lower()], overwrite=overwrite)
        written.append(session.relative(destination))
    return {**report, "output": session.relative(destination), "files": written}
