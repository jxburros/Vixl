"""Curated responsive container compositions and templates built from semantic slots."""

from copy import deepcopy


def text(slot, frame, size=24, color="@ink", **kw):
    return {
        "type": "text",
        "name": slot,
        "text": "${" + slot + "}",
        "size": size,
        "color": color,
        "frame": frame,
        "fit_text": True,
        "min_size": 12,
        **kw,
    }


def photo(slot, frame, **kw):
    return {
        "type": "image-slot",
        "name": slot,
        "slot": slot,
        "width": 200,
        "height": 140,
        "frame": frame,
        **kw,
    }


def shape(name, frame, kind="rectangle", fill="@accent", **kw):
    return {
        "type": "shape",
        "name": name,
        "shape": kind,
        "width": 20,
        "height": 20,
        "fill": fill,
        "frame": frame,
        **kw,
    }


def expand(containers, templates):
    definitions = {
        "stat": (
            {"value": "[Value]", "label": "[Metric]", "delta": ""},
            [
                text("value", [0.07, 0.12, 0.86, 0.35], 72),
                text("label", [0.07, 0.52, 0.86, 0.16], 24),
                text("delta", [0.07, 0.76, 0.86, 0.14], 18, "@muted", hide_if_empty=True),
            ],
        ),
        "testimonial": (
            {"quote": "[Quote]", "name": "[Name]", "role": "[Role]", "photo": ""},
            [
                text("quote", [0.07, 0.08, 0.86, 0.44], 30),
                photo("photo", [0.07, 0.65, 0.18, 0.27], mask_shape="circle"),
                text("name", [0.31, 0.64, 0.62, 0.13], 22),
                text("role", [0.31, 0.80, 0.62, 0.12], 16, "@muted"),
            ],
        ),
        "feature-icon": (
            {"title": "[Feature]", "body": "[Benefit]"},
            [
                shape("icon", [0.07, 0.10, 0.13, 0.20], "hexagon"),
                text("title", [0.27, 0.10, 0.66, 0.23], 30),
                text("body", [0.27, 0.40, 0.66, 0.45], 20),
            ],
        ),
        "cta": (
            {"title": "[Take the next step]", "button": "[Action]"},
            [
                text("title", [0.07, 0.12, 0.86, 0.38], 32),
                shape("button-background", [0.07, 0.63, 0.66, 0.27], "rounded-rectangle", radius=18),
                text("button", [0.11, 0.69, 0.58, 0.15], 22, "@on-accent", align="center"),
            ],
        ),
        "pricing-tier": (
            {
                "plan": "[Plan]",
                "price": "[Price]",
                "features": "[Feature one]\n[Feature two]",
                "button": "[Choose plan]",
            },
            [
                text("plan", [0.07, 0.06, 0.86, 0.13], 22),
                text("price", [0.07, 0.23, 0.86, 0.23], 44),
                text("features", [0.07, 0.50, 0.86, 0.24], 18),
                shape("button-background", [0.07, 0.80, 0.86, 0.15], "rounded-rectangle", radius=12),
                text("button", [0.10, 0.81, 0.80, 0.13], 18, "@on-accent", align="center"),
            ],
        ),
        "profile": (
            {"photo": "", "name": "[Name]", "title": "[Title]", "bio": "[Short biography]"},
            [
                photo("photo", [0.05, 0.08, 0.35, 0.84], mask_shape="rounded", radius=20),
                text("name", [0.46, 0.10, 0.49, 0.18], 28),
                text("title", [0.46, 0.33, 0.49, 0.14], 18, "@muted"),
                text("bio", [0.46, 0.54, 0.49, 0.35], 18),
            ],
        ),
        "timeline-step": (
            {"date": "[Date]", "title": "[Milestone]", "body": "[What happened]"},
            [
                shape("marker", [0.06, 0.09, 0.07, 0.105], "ellipse"),
                shape("stem", [0.09, 0.23, 0.01, 0.67]),
                text("date", [0.20, 0.08, 0.73, 0.14], 18, "@muted"),
                text("title", [0.20, 0.28, 0.73, 0.22], 30),
                text("body", [0.20, 0.57, 0.73, 0.34], 20),
            ],
        ),
        "list-block": (
            {"title": "[Heading]", "items": "[First item]\n[Second item]\n[Third item]"},
            [text("title", [0.07, 0.08, 0.86, 0.23], 30), text("items", [0.07, 0.40, 0.86, 0.50], 22)],
        ),
        "badge": (
            {"label": "[Label]"},
            [
                shape("badge", [0.07, 0.15, 0.86, 0.70], "capsule"),
                text("label", [0.15, 0.38, 0.70, 0.24], 32, "@on-accent", align="center"),
            ],
        ),
        "ribbon": (
            {"label": "[Award]"},
            [
                shape("ribbon", [0.07, 0.20, 0.86, 0.60], "chevron"),
                text("label", [0.17, 0.38, 0.57, 0.24], 30, "@on-accent", align="center"),
            ],
        ),
        "photo-caption": (
            {"photo": "", "caption": "[Caption]"},
            [photo("photo", [0.05, 0.05, 0.90, 0.66]), text("caption", [0.05, 0.78, 0.90, 0.16], 20)],
        ),
        "product-card": (
            {"photo": "", "name": "[Product]", "price": "[Price]", "tag": ""},
            [
                photo("photo", [0.05, 0.05, 0.50, 0.90]),
                text("name", [0.60, 0.10, 0.35, 0.30], 28),
                text("price", [0.60, 0.48, 0.35, 0.19], 26),
                text("tag", [0.60, 0.75, 0.35, 0.16], 16, "@muted", hide_if_empty=True),
            ],
        ),
        "section-header": (
            {"eyebrow": "[Section]", "title": "[Heading]"},
            [
                text("eyebrow", [0.07, 0.14, 0.86, 0.14], 18, "@muted"),
                text("title", [0.07, 0.38, 0.86, 0.34], 40),
                shape("rule", [0.07, 0.87, 0.86, 0.012]),
            ],
        ),
    }
    for name, (defaults, ops) in definitions.items():
        containers[name] = {
            "width": 480,
            "height": 320,
            "min_width": 240,
            "max_width": 8192,
            "min_height": 200,
            "max_height": 8192,
            "safe": True,
            "description": name.replace("-", " "),
            "defaults": defaults,
            "slots": {
                k: {"kind": "image" if k == "photo" else "text", "required": bool(v) or k == "photo"}
                for k, v in defaults.items()
            },
            "rules": {"layout": "free", "padding": 0, "contain": True},
            "operations": ops,
        }
    # Variants retain identical variable names and semantic children, while changing placement.
    for name in ("testimonial", "feature-icon", "profile", "product-card"):
        original = containers[name]["operations"]
        centered = deepcopy(original)
        text_ops = [op for op in centered if op["type"] == "text"]
        visual = [op for op in centered if op["type"] != "text"]
        for op in visual:
            op["frame"] = [0.38, 0.05, 0.24, 0.30]
        height = 0.52 / len(text_ops)
        for i, op in enumerate(text_ops):
            op["frame"] = [0.08, 0.41 + i * height, 0.84, height - 0.025]
            op["align"] = "center"
        split = deepcopy(original)
        text_ops = [op for op in split if op["type"] == "text"]
        for op in split:
            if op["type"] != "text":
                op["frame"] = [0.05, 0.08, 0.36, 0.84]
        height = 0.80 / len(text_ops)
        for i, op in enumerate(text_ops):
            op["frame"] = [0.47, 0.09 + i * height, 0.48, height - 0.04]
        containers[name]["variants"] = {
            "left": {"operations": original},
            "centered": {"operations": centered},
            "split": {"operations": split},
        }
    for name, item in containers.items():
        item.setdefault("safe", name != "badge-mark")
        item.setdefault("min_width", 240)
        item.setdefault("max_width", 8192)
        item.setdefault("min_height", 200)
        item.setdefault("max_height", 8192)
    combos = [
        {"name": "minimal-light", "palette": "slate", "look": "none", "mode": "light"},
        {"name": "bold-dark", "palette": "midnight", "look": "soft-shadow", "mode": "dark"},
        {"name": "warm-editorial", "palette": "coffee", "look": "paper", "mode": "light"},
    ]
    specs = [
        ("social-story", "social", 1080, 1920, 1, ["section-header", "photo-caption", "cta"], ["story"]),
        (
            "social-carousel",
            "social",
            1080,
            1080,
            1,
            ["section-header", "feature-icon", "cta"],
            ["instagram-square"],
        ),
        ("social-announcement", "social", 1080, 1080, 1, ["section-header", "cta"], ["instagram-square"]),
        (
            "social-event-promo",
            "social",
            1080,
            1350,
            1,
            ["section-header", "photo-caption", "cta"],
            ["instagram-portrait"],
        ),
        ("social-quote", "social", 1080, 1080, 1, ["testimonial"], ["instagram-square"]),
        ("marketing-hero", "marketing", 1440, 720, 2, ["section-header", "photo-caption"], ["web-hero"]),
        ("marketing-features", "marketing", 1440, 900, 3, ["feature-icon"] * 6, ["presentation"]),
        ("marketing-pricing", "marketing", 1440, 900, 3, ["pricing-tier"] * 3, ["presentation"]),
        ("marketing-testimonials", "marketing", 1440, 900, 2, ["testimonial"] * 4, ["presentation"]),
        ("marketing-launch", "marketing", 1440, 480, 2, ["section-header", "cta"], ["web-banner"]),
        ("print-flyer", "print", 1200, 1600, 1, ["section-header", "photo-caption", "cta"], ["a4"]),
        (
            "print-menu",
            "print",
            1200,
            1600,
            2,
            ["section-header", "list-block", "list-block", "list-block"],
            ["a4"],
        ),
        ("print-certificate", "print", 1600, 1200, 1, ["section-header", "badge", "cta"], ["a4"]),
        ("print-invitation", "print", 1200, 1600, 1, ["section-header", "photo-caption", "cta"], ["a5"]),
        ("print-postcard", "print", 1480, 1050, 2, ["photo-caption", "section-header"], ["a6"]),
        (
            "print-poster",
            "print",
            1200,
            1600,
            1,
            ["section-header", "photo-caption", "cta"],
            ["poster-18x24"],
        ),
        (
            "business-one-pager",
            "business",
            1200,
            1600,
            2,
            ["section-header", "stat", "feature-icon", "list-block", "testimonial", "cta"],
            ["a4"],
        ),
        (
            "business-case-study",
            "business",
            1200,
            1600,
            2,
            ["section-header", "photo-caption", "list-block", "stat"],
            ["a4"],
        ),
        ("business-invoice-header", "business", 1200, 400, 2, ["section-header", "list-block"], ["a4"]),
        ("business-report-cover", "business", 1200, 1600, 1, ["section-header", "photo-caption"], ["a4"]),
        ("slide-title", "slides", 1920, 1080, 1, ["section-header"], ["presentation"]),
        ("slide-section", "slides", 1920, 1080, 1, ["section-header"], ["presentation"]),
        ("slide-comparison", "slides", 1920, 1080, 2, ["list-block"] * 2, ["presentation"]),
        ("slide-timeline", "slides", 1920, 1080, 3, ["timeline-step"] * 3, ["presentation"]),
        ("slide-team", "slides", 1920, 1080, 3, ["profile"] * 3, ["presentation"]),
        ("slide-stat", "slides", 1920, 1080, 1, ["stat"], ["presentation"]),
    ]
    for name, category, w, h, cols, choices, sizes in specs:
        templates[name] = {
            "width": w,
            "height": h,
            "description": name.replace("-", " "),
            "category": category,
            "safe": True,
            "sizes": sizes,
            "combinations": deepcopy(combos),
            "grid": {"columns": cols, "resources": choices, "padding": 0.035, "gap": 0.025},
            "slots": {
                f"slot-{i + 1}": deepcopy(containers[c].get("slots", {})) for i, c in enumerate(choices)
            },
            "suites": {"container-layout": {"rules": [{"id": "containers", "kind": "container"}]}},
            "operations": [
                {"type": "container-place", "name": f"slot-{i + 1}", "resource": c}
                for i, c in enumerate(choices)
            ],
        }
        if name == "social-carousel":
            templates[name]["grid"]["pages"] = True
    for name, item in templates.items():
        if name.startswith("modular-"):
            choices = [o["resource"] for o in item["operations"] if o["type"] == "container-place"]
            item["grid"] = {"columns": item["width"] // 480, "resources": choices, "padding": 0, "gap": 0}
        item.setdefault("combinations", deepcopy(combos))
        item.setdefault("safe", True)
        item["operations"] = [op for op in item["operations"] if op["type"] != "palette-apply"]
    return containers, templates


def template_operations(project, item, op, values):
    """Resolve grid cells from the actual canvas, with per-slot values and optional pages."""
    import math
    from .errors import require

    if "grid" not in item:
        return deepcopy(item["operations"])
    grid = item["grid"]
    w, h = (project.state["canvas"][k] for k in ("width", "height"))
    cols = op.get("columns", grid["columns"])
    choices = grid["resources"]
    pages = grid.get("pages", False)
    if pages:
        cols = 1
    rows = 1 if pages else math.ceil(len(choices) / cols)
    pad, gap = round(min(w, h) * grid["padding"]), round(min(w, h) * grid["gap"])
    cw, ch = int((w - 2 * pad - (cols - 1) * gap) / cols), int((h - 2 * pad - (rows - 1) * gap) / rows)
    require(cw >= 240 and ch >= 200, "Template cells are too small; enlarge canvas or reduce columns")
    ops = []
    for i, resource in enumerate(choices):
        if pages and i:
            ops.append({"type": "page", "action": "add", "name": f"slide-{i + 1}"})
        if i == 0 or pages:
            ops.append(
                {"type": "solid", "name": "background", "color": "@background", "width": w, "height": h}
            )
        slot = f"slot-{i + 1}"
        variables = values.get(slot, {})
        require(isinstance(variables, dict), "Template slot values must be objects")
        ops.append(
            {
                "type": "container-place",
                "name": slot,
                "resource": resource,
                "width": cw,
                "height": ch,
                "x": pad + (0 if pages else i % cols) * (cw + gap),
                "y": pad + (0 if pages else i // cols) * (ch + gap),
                "variables": variables,
                "seed": op["seed"] + i if op["seed"] + i < 2**32 else i,
            }
        )
    return ops


def finish_template(project, look, existing):
    """Apply a template finish on every generated page and restore the selected page."""
    from .errors import require
    from .operations import execute
    from .pages import MASTER_PREFIX, select

    if look == "none":
        return
    require(
        look
        in (
            "soft-shadow",
            "paper",
            "grain",
            "outline",
            "gradient",
            "subtle-grain",
            "light-paper",
            "clean-flat",
        ),
        "Unknown template look",
    )
    active = project.state.get("page")
    views = [active] + [page["id"] for page in project.state.get("pages", []) if page["id"] != active]

    def activate(ident):
        if ident:
            select(project.state, master=ident[len(MASTER_PREFIX) :]) if ident.startswith(
                MASTER_PREFIX
            ) else select(project.state, page=ident)

    try:
        for ident in views:
            activate(ident)
            for layer in list(project.state["layers"]):
                background = look in ("paper", "grain", "subtle-grain", "light-paper")
                eligible = layer["name"] == "background" if background else "container" in layer
                if layer["id"] not in existing and eligible:
                    execute(project, {"type": "look", "target": layer["id"], "look": look, "amount": 0.15})
    finally:
        activate(active)
