"""Editable comic pages: ordered panels, gutters, artwork slots, captions and dialogue."""

from .errors import require
from .model import new_layer

TYPES = ("comic-layout",)


def schemas(add):
    from .schema import S, enum

    register = add
    descriptions = {
        "panels": "Narrative sequence of panels with optional image, caption, dialogue and column span.",
        "columns": "Number of columns in the panel grid.",
        "reading_order": "Panel order across each row: ltr or rtl for manga.",
        "gutter": "Empty pixels separating adjacent panels.",
        "margin": "Outer page margin in pixels.",
        "caption_size": "Caption and dialogue type size in pixels.",
        "border": "Panel border color.",
        "border_width": "Panel border thickness in pixels.",
        "background": "Page paper color.",
        "name": "Prefix for generated panel layer names.",
    }

    def add(kind, properties, required):
        register(
            kind,
            {k: {**v, "description": descriptions[k]} for k, v in properties.items()},
            required,
            description="Compose an editable comic page with ordered panels, gutters, captions and speech bubbles.",
        )

    amount = {"type": "integer", "minimum": 0, "maximum": 200}
    dialogue = {
        "type": "object",
        "properties": {
            "text": S,
            "style": enum("speech", "thought", "shout", "whisper"),
            "x": {"type": "number", "minimum": 0, "maximum": 1},
            "y": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["text"],
        "additionalProperties": False,
    }
    panel = {
        "type": "object",
        "properties": {
            "name": S,
            "image": S,
            "caption": S,
            "span": {"type": "integer", "minimum": 1, "maximum": 6},
            "focal": {
                "type": "array",
                "items": {"type": "number", "minimum": 0, "maximum": 1},
                "minItems": 2,
                "maxItems": 2,
            },
            "dialogue": {"type": "array", "items": dialogue, "maxItems": 8},
        },
        "additionalProperties": False,
    }
    add(
        "comic-layout",
        {
            "name": S,
            "panels": {"type": "array", "items": panel, "minItems": 1, "maxItems": 24},
            "columns": {"type": "integer", "minimum": 1, "maximum": 6},
            "gutter": amount,
            "margin": amount,
            "reading_order": enum("ltr", "rtl"),
            "caption_size": {"type": "integer", "minimum": 8, "maximum": 120},
            "background": S,
            "border": S,
            "border_width": amount,
        },
        ["panels"],
    )


def execute(project, op):
    from .operations import execute as apply, append_layer
    from .text import measure, font_data

    cols = op.get("columns", 2)
    panels = op["panels"]
    gutter, margin = op.get("gutter", 20), op.get("margin", 30)
    w, h = (project.state["canvas"][k] for k in ("width", "height"))
    cursor, row, slots = 0, 0, []
    for panel in panels:
        span = panel.get("span", 1)
        require(span <= cols, "Panel span exceeds comic columns")
        if cursor + span > cols:
            cursor, row = 0, row + 1
        slots.append((row, cursor, span))
        cursor += span
    rows = row + 1
    cw, ch = (w - 2 * margin - (cols - 1) * gutter) / cols, (h - 2 * margin - (rows - 1) * gutter) / rows
    require(cw >= 100 and ch >= 100, "Comic panels are too small; enlarge canvas or reduce panel count")
    prefix = op.get("name", "comic")
    apply(
        project,
        {
            "type": "solid",
            "name": prefix + "/paper",
            "color": op.get("background", "#ffffff"),
            "width": w,
            "height": h,
        },
    )
    records = []
    for i, (panel, (row, col, span)) in enumerate(zip(panels, slots)):
        if op.get("reading_order", "ltr") == "rtl":
            col = cols - col - span
        x, y = round(margin + col * (cw + gutter)), round(margin + row * (ch + gutter))
        pw, ph = round(span * cw + (span - 1) * gutter), round(ch)
        name = prefix + "/" + panel.get("name", f"panel-{i + 1}")
        group = new_layer(name, "group", pw, ph, x=x, y=y, content_width=pw, content_height=ph)
        append_layer(project, group)
        created = []
        caption = panel.get("caption")
        reserve = 0
        if caption:
            size = op.get("caption_size", 20)
            layer = {"font": "DejaVuSans.ttf", "size": size, "text": caption}
            _, box = measure(font_data(project, layer), caption, size, 4, "left", pw - 24)
            reserve = round(box[3] - box[1]) + 24
            require(reserve < ph * 0.55, "Caption consumes too much panel space; shorten it or enlarge panel")
        apply(
            project,
            {
                "type": "image-slot",
                "name": name + "/art",
                "slot": f"panel-{i + 1}-art",
                "asset": panel.get("image", ""),
                "width": pw,
                "height": ph - reserve,
                "focal": panel.get("focal", [0.5, 0.5]),
            },
        )
        art = project.layer()
        art["parent"] = group["id"]
        created.append(art["id"])
        if caption:
            apply(
                project,
                {
                    "type": "solid",
                    "name": name + "/caption-background",
                    "color": "#ffffff",
                    "width": pw,
                    "height": reserve,
                    "y": ph - reserve,
                },
            )
            project.layer()["parent"] = group["id"]
            apply(
                project,
                {
                    "type": "text",
                    "name": name + "/caption",
                    "text": caption,
                    "size": size,
                    "color": "#111111",
                    "x": 12,
                    "y": ph - reserve + 12,
                },
            )
            caption_layer = project.layer()
            caption_layer["parent"] = group["id"]
            apply(
                project,
                {
                    "type": "text-layout",
                    "target": caption_layer["id"],
                    "width": pw - 24,
                    "height": reserve - 24,
                },
            )
        for j, speech in enumerate(panel.get("dialogue", [])):
            apply(
                project,
                {
                    "type": "speech-bubble",
                    "name": name + f"/dialogue-{j + 1}",
                    "text": speech["text"],
                    "anchor": art["id"],
                    "x": round(pw * speech.get("x", 0.08)),
                    "y": round(ph * speech.get("y", 0.08)),
                    "style": speech.get("style", "speech"),
                    "size": max(12, op.get("caption_size", 20)),
                    "max_width": max(80, round(pw * 0.75)),
                    "padding": 10,
                },
            )
            project.layer()["parent"] = group["id"]
        apply(
            project,
            {
                "type": "shape",
                "name": name + "/border",
                "shape": "rectangle",
                "fill": "transparent",
                "stroke": op.get("border", "#111111"),
                "stroke_width": op.get("border_width", 2),
                "width": pw,
                "height": ph,
            },
        )
        project.layer()["parent"] = group["id"]
        group["comic_panel"] = {"order": i + 1, "caption": caption or "", "art": art["id"]}
        records.append({"order": i + 1, "id": group["id"], "name": name, "bounds": [x, y, pw, ph]})
    project.state["comic"] = {
        "reading_order": op.get("reading_order", "ltr"),
        "gutter": gutter,
        "panels": records,
    }
