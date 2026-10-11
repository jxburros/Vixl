"""Alternative text, document and page language, reading order and the ``accessibility`` check.

A layer carries ``alt`` (what a meaningful image, frame, chart, link or group shows) or ``decorative: true``
(set with ``layer-intent``); layers with role ``decoration`` or ``background`` are decorative too. The
``accessibility`` operation sets the document's ``lang`` and ``title`` (``state["accessibility"]``) and, for
the active page, a description of the whole page (``page_alt``), its language when it differs
(``page_lang``) and an explicit reading order (``state["page_accessibility"]``, kept per page).

Exports carry them: HTML ``lang``, ``alt`` and ``aria-label``; SVG ``<title>``/``<desc>``, ``role="img"``
and ``aria-hidden`` for decorative layers; PowerPoint ``descr`` and the decorative flag; PDF ``/Lang`` and
``/Alt`` (or ``/Artifact``) marked content. A tagged PDF structure tree is not written.
"""

import re

from .errors import require

TYPES = ("accessibility",)
LANG = re.compile(r"[A-Za-z]{2,8}(-[A-Za-z0-9]{1,8})*")
MAX_ALT = 2000
DOCUMENT_FIELDS = ("lang", "title")
PAGE_FIELDS = ("alt", "lang", "reading_order")
# Layers whose meaning is in their pixels: they need alt text unless decorative.
IMAGE_TYPES = ("raster", "frame", "link", "pixel", "paint")
SCREEN_MIN_PX = 12
PRINT_MIN_PT = 8


def schemas(add):
    from .schema import S, field

    add("accessibility", {
        "lang": field(S, "Document language, a BCP 47 tag such as en, en-GB or fr-CA (HTML lang, PowerPoint text "
                      "language, PDF /Lang). An empty string clears it."),
        "title": {"type": "string", "maxLength": 500, "description": "Document title for HTML, PDF and SVG exports; "
                  "default the page's title layer."},
        "page_alt": {"type": "string", "maxLength": MAX_ALT, "description": "A description of the active page (or the "
                     "whole artwork of a one-page document) as one picture: HTML alt, SVG <desc>."},
        "page_lang": field(S, "Language of the active page when it differs from the document's."),
        "reading_order": {"type": "array", "items": S, "maxItems": 512, "description": "Layers of the active page in "
                          "the order a reader should meet them (HTML text layer and the reading-order check); an empty "
                          "list returns to top-to-bottom order."},
    })


def _lang(value, field):
    require(isinstance(value, str) and (value == "" or LANG.fullmatch(value)),
            f"{field} must be a BCP 47 language tag such as en, en-GB or fr-CA", field=field)
    return value


def execute(project, op):
    state = project.state
    document = dict(state.get("accessibility") or {})
    page = dict(state.get("page_accessibility") or {})
    if "lang" in op:
        document["lang"] = _lang(op["lang"], "lang")
    if "title" in op:
        document["title"] = op["title"].strip()
    if "page_alt" in op:
        page["alt"] = op["page_alt"].strip()
    if "page_lang" in op:
        page["lang"] = _lang(op["page_lang"], "page_lang")
    if "reading_order" in op:
        ids = [project.layer(ref)["id"] for ref in op["reading_order"]]
        require(len(set(ids)) == len(ids), "reading_order names a layer twice", field="reading_order")
        page["reading_order"] = ids
    document = {key: value for key, value in document.items() if value}
    page = {key: value for key, value in page.items() if value}
    if document:
        state["accessibility"] = document
    else:
        state.pop("accessibility", None)
    if page:
        state["page_accessibility"] = page
    else:
        state.pop("page_accessibility", None)


def validate(project, state):
    for key, fields in (("accessibility", DOCUMENT_FIELDS), ("page_accessibility", PAGE_FIELDS)):
        record = state.get(key)
        if record is None:
            continue
        require(isinstance(record, dict) and set(record) <= set(fields), f"Invalid {key} record", "invalid_project")
        if "lang" in record:
            require(isinstance(record["lang"], str) and LANG.fullmatch(record["lang"]), f"Invalid {key} language",
                    "invalid_project")
        for text in ("title", "alt"):
            require(isinstance(record.get(text, ""), str), f"Invalid {key} {text}", "invalid_project")
    order = (state.get("page_accessibility") or {}).get("reading_order", [])
    ids = {layer["id"] for layer in state["layers"]}
    require(isinstance(order, list) and all(ident in ids for ident in order), "Reading order names a missing layer",
            "invalid_project")
    for layer in state["layers"]:
        if "alt" in layer:
            require(isinstance(layer["alt"], str) and 0 < len(layer["alt"]) <= MAX_ALT,
                    f"Invalid alt text on {layer['name']!r}", "invalid_project")
        require(isinstance(layer.get("decorative", False), bool), f"Invalid decorative flag on {layer['name']!r}",
                "invalid_project")


def set_alt(layer, op):
    """``layer-intent`` alt and decorative."""
    if "alt" in op:
        text = op["alt"].strip()
        require(len(text) <= MAX_ALT, f"alt is at most {MAX_ALT} characters", field="alt")
        require(not (text and layer["type"] == "text"), "A text layer is read as its own text; give alt to images, "
                "frames, charts, links and groups", field="alt")
        if text:
            layer["alt"] = text
            layer.pop("decorative", None)
        else:
            layer.pop("alt", None)
    if "decorative" in op:
        require(not (op["decorative"] and op.get("alt", "").strip()), "A layer is either described (alt) or "
                "decorative, not both", field="decorative")
        if op["decorative"]:
            layer["decorative"] = True
            layer.pop("alt", None)
        else:
            layer.pop("decorative", None)


def language(state):
    """The document language: the accessibility record, else the form settings; None when unset."""
    return (state.get("accessibility") or {}).get("lang") or (state.get("form") or {}).get("lang") or None


def page_language(view_state):
    return (view_state.get("page_accessibility") or {}).get("lang") or language(view_state)


def document_title(state):
    return (state.get("accessibility") or {}).get("title") or (state.get("form") or {}).get("title") or None


def page_alt(view_state):
    return (view_state.get("page_accessibility") or {}).get("alt") or None


def decorative(layer, index=None):
    """Marked decorative, or role decoration/background (the layer or a group above it)."""
    cursor = layer
    while cursor is not None:
        if cursor.get("decorative") or cursor.get("role") in ("decoration", "background"):
            return True
        cursor = index.get(cursor.get("parent")) if index is not None else None
    return False


def described(layer, index):
    """The alt text that covers a layer: its own or a group's above it."""
    cursor = layer
    while cursor is not None:
        if cursor.get("alt"):
            return cursor["alt"]
        cursor = index.get(cursor.get("parent"))
    return None


def needs_alt(layer, index):
    """Whether a layer is a meaningful image (or chart) with nothing describing it."""
    if layer["type"] not in IMAGE_TYPES and not (layer["type"] == "group" and layer.get("chart")):
        return False
    if decorative(layer, index) or described(layer, index):
        return False
    return not any(a.get("chart") for a in _ancestors(layer, index))


def _ancestors(layer, index):
    cursor = index.get(layer.get("parent"))
    while cursor is not None:
        yield cursor
        cursor = index.get(cursor.get("parent"))


def reading_order(view_state, items, bounds):
    """``items`` (layers) in the order a reader meets them: the page's explicit order first, then top to bottom
    and left to right (lines within half a line height count as one row)."""
    explicit = (view_state.get("page_accessibility") or {}).get("reading_order") or []
    rank = {ident: i for i, ident in enumerate(explicit)}
    first = sorted((item for item in items if item["id"] in rank), key=lambda item: rank[item["id"]])
    rest = [item for item in items if item["id"] not in rank]
    return first + visual_order(rest, bounds)


def visual_order(items, bounds):
    rows = []
    for item in sorted(items, key=lambda item: (bounds[item["id"]][1], bounds[item["id"]][0])):
        box = bounds[item["id"]]
        for row in rows:
            top, height = row[0]
            if abs(box[1] - top) <= max(4.0, min(height, box[3]) / 2):
                row[1].append(item)
                break
        else:
            rows.append(((box[1], box[3]), [item]))
    return [item for _, members in rows for item in sorted(members, key=lambda item: bounds[item["id"]][0])]


# ---------------------------------------------------------------------------------------------------------------
# The check


def check(candidate, resolved, layers, texts, bounds, text_scales, issue):
    """The accessibility findings beyond contrast and colour vision (which ``check_design`` runs alongside)."""
    state = candidate.state
    index = resolved
    if not language(state):
        issue("accessibility", "warning", "The document language is not set: HTML exports say lang=\"en\" and "
              "PowerPoint en-US by default. Set it with {type: accessibility, lang: 'en-GB'} (any BCP 47 tag)",
              [], action="fix", code="language")
    for item in layers:
        layer = resolved[item["id"]]
        if needs_alt(layer, index):
            what = "chart" if layer.get("chart") else "image" if layer["type"] in ("raster", "frame") else layer["type"]
            issue("accessibility", "warning",
                  f"{item['name']!r} is a meaningful {what} with no alt text; describe it with {{type: layer-intent, "
                  f"target: {item['name']!r}, alt: '…'}} or mark it decorative: true", [item], action="fix",
                  code="missing-alt")
    canvas = state["canvas"]
    dpi = canvas.get("dpi")
    small = []
    for item in texts:
        layer = resolved[item["id"]]
        px = layer.get("size", 0) * text_scales.get(item["id"], 1)
        if dpi:
            points = px * 72 / dpi
            if points < PRINT_MIN_PT:
                small.append((item, f"{points:.1f} pt (print minimum {PRINT_MIN_PT} pt)"))
        elif px < SCREEN_MIN_PX:
            small.append((item, f"{px:.1f} px (screen minimum {SCREEN_MIN_PX} px)"))
    for item, size in small[:20]:
        issue("accessibility", "warning", f"{item['name']!r} is {size}; enlarge it for readers with low vision",
              [item], action="review", code="text-size")
    from .charts import series_colors

    for group, series in series_colors(candidate, resolved):
        if group.get("color_vision_safe") or len(series) < 2:
            continue
        labelled = any(layer.get("parent") == group["id"] and str(layer.get("chart_part", "")).startswith(
            ("value-", "slice-label-")) for layer in resolved.values())
        if not labelled:
            issue("accessibility", "warning",
                  f"{group['name']!r} tells its {len(series)} series apart by colour alone; add value labels "
                  "(chart value_labels), direct labels or patterns, then mark it layer-intent color_vision_safe",
                  [group], action="review", code="color-only-chart")
    readable = [item for item in texts if (item.get("text") or "").strip()]
    if len(readable) > 1 and not (state.get("page_accessibility") or {}).get("reading_order"):
        stacked = [item for item in layers if item in readable]
        visual = visual_order(readable, bounds)
        rank = {item["id"]: i for i, item in enumerate(visual)}
        for before, after in zip(stacked, stacked[1:]):
            if rank[after["id"]] < rank[before["id"]] - 1 or (rank[after["id"]] < rank[before["id"]] and
                                                                bounds[after["id"]][1] + bounds[after["id"]][3]
                                                                <= bounds[before["id"]][1]):
                issue("accessibility", "warning",
                      f"Exports read {before['name']!r} before {after['name']!r} (stacking order), but {after['name']!r} "
                      "comes first on the page. Reorder the layers, or set {type: accessibility, reading_order: [...]} "
                      "for HTML (PowerPoint and PDF read in stacking order)", [before, after], action="review",
                      code="reading-order")
                break


def compile_command(cmd, args):
    """``vixl accessibility --lang en-GB [--title T] [--page-alt TEXT] [--page-lang L] [--reading-order A B …]``."""
    if cmd not in TYPES:
        return None
    from .commands import Parser

    p = Parser(prog="vixl accessibility")
    p.add_argument("--lang")
    p.add_argument("--title")
    p.add_argument("--page-alt")
    p.add_argument("--page-lang")
    p.add_argument("--reading-order", nargs="*")
    return {"type": cmd, **{k: v for k, v in vars(p.parse_args(args)).items() if v is not None}}
