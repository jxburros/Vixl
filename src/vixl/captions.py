"""Editable speech/thought balloons and styled timeline/film caption overlays."""
from copy import copy, deepcopy
import math
from .errors import require
from .model import finite

TYPES = ("speech-bubble", "caption")


def schemas(add):
    from .motion_schema import documented
    add = documented(add)
    from .schema import S, N
    common = {"name": S, "text": S, "font": S, "size": {"type": "integer", "minimum": 1, "maximum": 4096}, "color": S, "x": N, "y": N, "max_width": N, "padding": N}
    add("speech-bubble", {**common, "anchor": S, "style": {"enum": ["speech", "thought", "shout", "whisper"]}, "fill": S, "stroke": S}, ["text", "anchor"])
    add("caption", {**common, "start": N, "end": N, "style": {"type": "object"}, "box": {"type": ["object", "boolean"]}, "animation": {"enum": ["none", "fade", "typewriter"]}}, ["text"])


def validate_caption(caption):
    allowed = {"name", "text", "start", "end", "x", "y", "size", "color", "font", "style", "box", "animation", "max_width", "padding"}
    require(isinstance(caption, dict) and not set(caption) - allowed, "Unknown caption field")
    require(isinstance(caption.get("text"), str) and len(caption["text"]) <= 10000, "Caption text must have at most 10000 characters")
    require(caption.get("animation", "none") in ("none", "fade", "typewriter"), "Unknown caption animation")
    style = caption.get("style", {})
    require(isinstance(style, dict) and set(style) <= {"bold", "italic", "underline", "tracking", "align", "stroke_width", "stroke_color"}, "Invalid caption style")
    for key in ("bold", "italic", "underline"):
        require(key not in style or isinstance(style[key], bool), f"Caption {key} must be boolean")
    if "align" in style:
        require(style["align"] in ("left", "center", "right"), "Invalid caption alignment")
    if "tracking" in style:
        finite(style["tracking"], "caption tracking", -100, 100)
    if "stroke_width" in style:
        finite(style["stroke_width"], "caption stroke width", 0, 64)
    box = caption.get("box", False)
    require(isinstance(box, (bool, dict)), "Caption box must be boolean or settings")
    if isinstance(box, dict):
        require(set(box) <= {"color", "radius", "padding", "opacity"}, "Unknown caption box field")
        for key in ("radius", "padding"):
            if key in box:
                finite(box[key], key, 0, 1000)
        if "opacity" in box:
            finite(box["opacity"], "box opacity", 0, 1)
    for key in ("x", "y"):
        if key in caption:
            finite(caption[key], key, -1e6, 1e6)
    finite(caption.get("size", 40), "caption size", 1, 4096)
    finite(caption.get("max_width", 1000), "caption width", 1, 16384)
    finite(caption.get("padding", 12), "caption padding", 0, 1000)
    if "start" in caption or "end" in caption:
        require("start" in caption and "end" in caption, "Caption needs both start and end")
        finite(caption["start"], "caption start", 0, 600000)
        finite(caption["end"], "caption end", 0, 600000)
        require(caption["end"] > caption["start"], "Caption end must follow start")


def _text(project, name, text, op, width):
    from .operations import execute as apply
    style = op.get("style", {}) if isinstance(op.get("style"), dict) else {}
    span = {"text": text, **{k: v for k, v in style.items() if k in ("bold", "italic", "underline", "tracking")}}
    apply(project, {"type": "rich-text", "name": name, "spans": [span], "font": op.get("font", "DejaVuSans.ttf"), "size": op.get("size", 24),
                    "color": op.get("color", "#17202a"), "width": max(1, round(width)), "align": style.get("align", "left"), "fit": True})
    layer = project.layer()
    for key in ("stroke_width", "stroke_color"):
        if key in style:
            layer[key] = style[key]
    return layer


def execute(project, op):
    from .operations import execute as apply
    if op["type"] == "caption":
        caption = {k: v for k, v in op.items() if k not in ("type", "target")}
        validate_caption(caption)
        return apply_caption(project, caption, None)
    text = op["text"]
    require(isinstance(text, str) and len(text) <= 10000, "Bubble text must have at most 10000 characters")
    anchor = project.layer(op["anchor"])
    name = op.get("name", f"bubble-{len(project.state['layers'])}")
    padding = finite(op.get("padding", 16), "padding", 0, 1000)
    width = finite(op.get("max_width", min(320, project.state["canvas"]["width"])), "max_width", 16, 16384)
    require(width > 2 * padding, "Bubble width must leave room for text after padding")
    layer = _text(project, name + "/text", text, op, width - 2 * padding)
    # Tighten short text while preserving measured wrapping for long phrases.
    from .richtext import layout as layout_rich
    measured = layout_rich(project, layer)
    ink_width = measured.box[2]
    w, h = min(width, max(1, ink_width) + 2 * padding), layer["height"] + 2 * padding
    layer["width"] = max(1, math.ceil(w - 2 * padding))
    layer["text_layout"]["width"] = layer["width"]
    x, y = op.get("x", 0), op.get("y", 0)
    layer.update(x=x + padding, y=y + padding)
    text_id = layer["id"]
    style = op.get("style", "speech")
    require(style in ("speech", "thought", "shout", "whisper"), "Unknown bubble style")
    shape = "ellipse" if style == "thought" else "star" if style == "shout" else "rounded-rectangle"
    body = {"type": "shape", "name": name + "/body", "shape": shape, "x": x, "y": y, "width": round(w), "height": round(h), "fill": op.get("fill", "white"), "stroke": op.get("stroke", "#17202a"), "stroke_width": 1 if style == "whisper" else 2, "radius": 16}
    if style == "shout":
        body.update(sides=14, inner_radius=0.87)
    if style == "whisper":
        body["dash"] = "dashed"
    apply(project, body)
    body_id = project.layer()["id"]
    apply(project, {"type": "shape", "name": name + "/tail", "shape": "path", "path": "M0 0 L1 1 L2 0 Z", "width": 2, "height": 2, "x": x, "y": y,
                    "fill": body["fill"], "stroke": body["stroke"], "stroke_width": body["stroke_width"]})
    tail_id = project.layer()["id"]
    if style == "whisper":
        project.layer()["dash"] = "dashed"
    apply(project, {"type": "reorder", "target": text_id, "above": tail_id})
    apply(project, {"type": "group", "name": name, "targets": [body_id, tail_id, text_id]})
    group = project.layer()
    group["bubble"] = {"anchor": anchor["id"], "text": text_id, "body": body_id, "tail": tail_id, "style": style, "padding": padding, "tail_width": 7}
    return group


def apply_caption(project, caption, now=None, scale=1, index=0):
    """Build an editable overlay. Film callers supply frame time; document callers keep timing."""
    from .operations import execute as apply
    validate_caption(caption)
    canvas = project.state["canvas"]
    name = caption.get("name", f"caption-{index}")
    text = caption["text"]
    alpha = 1
    if now is not None and "start" in caption:
        span = caption["end"] - caption["start"]
        progress = max(0, min(1, (now - caption["start"]) / span))
        if caption.get("animation") == "typewriter":
            text = text[:math.ceil(len(text) * min(1, progress / 0.8))]
        if caption.get("animation") == "fade":
            fade = min(200, span / 4)
            alpha = max(0, min(1, (now - caption["start"]) / fade, (caption["end"] - now) / fade))
    box = caption.get("box", False)
    settings = box if isinstance(box, dict) else {}
    padding = settings.get("padding", caption.get("padding", 12)) * scale if box else 0
    x = caption.get("x", 20) * scale
    y = caption.get("y", canvas["height"] / scale - 80) * scale
    width = min(canvas["width"] - x, caption.get("max_width", canvas["width"] / scale - 40) * scale)
    require(width > 2 * padding, "Caption box leaves no room for text")
    layer = _text(project, name + "/text", text, {**caption, "size": max(1, round(caption.get("size", 40) * scale)), "color": caption.get("color", "white")}, width - padding * 2)
    layer.update(x=x + padding, y=y + padding)
    text_id = layer["id"]
    targets = [text_id]
    if box:
        apply(project, {"type": "shape", "name": name + "/box", "shape": "rounded-rectangle", "width": max(1, round(width)), "height": max(1, round(layer["height"] + padding * 2)), "x": x, "y": y, "fill": settings.get("color", "#101828"), "radius": settings.get("radius", 8) * scale, "stroke_width": 0})
        project.layer()["opacity"] = settings.get("opacity", 0.85)
        targets.insert(0, project.layer()["id"])
        apply(project, {"type": "reorder", "target": text_id, "above": targets[0]})
    apply(project, {"type": "group", "name": name, "targets": targets})
    group = project.layer()
    group["opacity"] = alpha
    group["caption"] = {**caption, "text_layer": text_id}
    if now is None and "start" in caption:
        from .timeline import execute_timeline
        for time, value in ((0, False), (caption["start"], True), (caption["end"], False)):
            execute_timeline(project, {"type": "keyframe", "target": group["id"], "property": "visible", "time": time, "value": value})
        if caption.get("animation") == "fade":
            fade = min(200, (caption["end"] - caption["start"]) / 4)
            for time, opacity in ((caption["start"], 0), (caption["start"] + fade, 1), (caption["end"] - fade, 1), (caption["end"], 0)):
                execute_timeline(project, {"type": "keyframe", "target": group["id"], "property": "opacity", "time": time, "value": opacity})
    return group


def prepare_bubbles(project):
    """Return a rendering copy so moving anchors never mutate authored bubble geometry."""
    bubbles = [layer for layer in project.state["layers"] if "bubble" in layer]
    if not bubbles:
        return project
    from .render import resolve_layout
    candidate = copy(project)
    candidate.state = deepcopy(project.state)
    bounds = resolve_layout(candidate)
    from .spatial import canvas_boxes
    from .affine import layer_matrix, matrix
    from .checks import group_matrix
    import numpy as np
    world = canvas_boxes(candidate)
    index = {layer["id"]: layer for layer in candidate.state["layers"]}
    for old in bubbles:
        group = candidate.layer(old["id"])
        settings = group["bubble"]
        ids = {layer["id"] for layer in candidate.state["layers"]}
        if settings["anchor"] not in ids:
            continue
        ax, ay, aw, ah = world[settings["anchor"]]
        transform = group_matrix(group, index, bounds) @ layer_matrix(group, bounds[group["id"]]) @ matrix(group["width"] / group["content_width"], 0, 0, group["height"] / group["content_height"])
        tip = (np.linalg.inv(transform) @ [ax + aw / 2, ay + ah / 2, 1])[:2].tolist()
        body = candidate.layer(settings["body"])
        w, h = body["width"], body["height"]
        center = [w / 2, h / 2]
        dx, dy = tip[0] - center[0], tip[1] - center[1]
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            dx = 1
        factor = min(w / 2 / abs(dx) if dx else math.inf, h / 2 / abs(dy) if dy else math.inf)
        base = [center[0] + dx * min(1, factor), center[1] + dy * min(1, factor)]
        length = math.hypot(dx, dy)
        tail_width = settings.get("tail_width", 7)
        normal = [-dy / length * tail_width, dx / length * tail_width]
        pts = [[base[0] + normal[0], base[1] + normal[1]], tip, [base[0] - normal[0], base[1] - normal[1]]]
        ox, oy = math.floor(min(p[0] for p in pts) - 2), math.floor(min(p[1] for p in pts) - 2)
        tw, th = max(1, math.ceil(max(p[0] for p in pts) - ox + 2)), max(1, math.ceil(max(p[1] for p in pts) - oy + 2))
        path = "M" + " L".join(f"{p[0] - ox:g} {p[1] - oy:g}" for p in pts) + " Z"
        if settings["style"] == "thought":
            # Three separate thought dots, decreasing towards the speaker.
            circles = []
            for fraction, radius in ((0.25, 5), (0.55, 3.5), (0.85, 2)):
                radius *= tail_width / 7
                cx = base[0] + (tip[0] - base[0]) * fraction - ox
                cy = base[1] + (tip[1] - base[1]) * fraction - oy
                circles.append(f"M{cx-radius:g} {cy:g} a{radius:g} {radius:g} 0 1 0 {2*radius:g} 0 a{radius:g} {radius:g} 0 1 0 {-2*radius:g} 0 Z")
            path = " ".join(circles)
        candidate.layer(settings["tail"]).update(x=ox, y=oy, width=tw, height=th, path_view=[tw, th], path=path)
    return candidate


def findings(project):
    from .spatial import canvas_boxes
    bounds = canvas_boxes(project)
    result = []
    canvas = project.state["canvas"]
    for layer in project.state["layers"]:
        kind = "bubble" if "bubble" in layer else "caption" if "caption" in layer else None
        if not kind:
            continue
        text_id = layer["bubble"]["text"] if kind == "bubble" else layer["caption"]["text_layer"]
        text_layer = project.layer(text_id)
        from .richtext import layout
        measured = layout(project, text_layer)
        if measured.box[2] > text_layer["width"] + .5 or measured.height > text_layer["height"] + .5:
            result.append({"check": "captions", "severity": "error", "layer": layer["id"], "code": "text-clipping", "message": "Text exceeds the measured bubble/caption box; enlarge the box or reduce the type size."})
        x, y, w, h = bounds[layer["id"]]
        if x < 0 or y < 0 or x + w > canvas["width"] or y + h > canvas["height"]:
            result.append({"check": "captions", "severity": "warning", "layer": layer["id"], "code": "text-overflow", "message": f"{kind.title()} text box extends beyond the canvas; move it or reduce width/font size."})
        if kind == "bubble" and layer[kind]["anchor"] not in bounds:
            result.append({"check": "captions", "severity": "error", "layer": layer["id"], "message": "Speech bubble anchor was removed."})
    return result
