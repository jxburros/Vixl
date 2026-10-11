"""HTML presenter: a multi-page document as one self-contained slide show.

``export deck.html`` writes a single file that opens in any browser and presents without a server
or a network: every page is an inline SVG (the ordinary SVG export, so text is outlines that stay
crisp at any size) or, with ``slide_images="png"``, an embedded PNG. The page scales each slide to the
window at the document's aspect ratio, moves between slides with the keyboard, taps, swipes and
``#3`` links, shows an overview grid, plays the pages' CSS transitions, prints one slide per page
and opens a speaker view (notes, next slide, timer) in a second window.

The file makes no requests and loads no scripts: one inline style block and one inline script,
named by hash in a Content-Security-Policy. Hidden pages are left out. The output is a pure
function of the document, so the same input always gives the same bytes.
"""

import base64
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from html import escape

from .errors import require
from .presenter_client import CHROME, SCRIPT, STYLE

THEMES = ("dark", "light", "auto")
SLIDE_IMAGES = ("svg", "png")
OPTIONS = ("theme", "notes", "slide_images", "start", "title")
WARN_BYTES = 24 * 1024 * 1024
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
GENERIC_PAGE = re.compile(r"page-\d+")
URL_REF = re.compile(r"url\(#([^)]+)\)")


def parse_options(value):
    """Validated presenter options from ``True`` or a dict (see ``OPTIONS``), with defaults filled in."""
    if value is None or value is True:
        value = {}
    require(isinstance(value, dict), "presenter is true, false or an object of options", field="presenter")
    unknown = sorted(set(value) - set(OPTIONS))
    require(not unknown, f"Unknown presenter option {', '.join(unknown)}; options: {', '.join(OPTIONS)}", field="presenter")
    options = {"theme": "dark", "notes": True, "slide_images": "svg", "start": 1, "title": None, **value}
    require(options["theme"] in THEMES, f"theme must be one of {', '.join(THEMES)}", field="presenter")
    require(options["slide_images"] in SLIDE_IMAGES, "slide_images must be svg or png", field="presenter")
    require(isinstance(options["notes"], bool), "notes must be true or false", field="presenter")
    start = options["start"]
    require(isinstance(start, str) and start or isinstance(start, int) and not isinstance(start, bool),
            "start is a slide number or a page name", field="presenter")
    require(options["title"] is None or isinstance(options["title"], str) and len(options["title"]) <= 200,
            "title must be text up to 200 characters", field="presenter")
    return options


def wants_presenter(presenter, *, html, paged, page=None):
    """Whether an export is a presentation: HTML output of a multi-page document (unless one page was
    asked for), or any HTML export with ``presenter`` true or a dict of options; ``False`` opts out."""
    if presenter is None:
        return bool(html and paged and page is None)
    if presenter is False:
        return False
    require(html, "presenter applies to HTML export (a .html file)", field="presenter")
    return True


def print_size(canvas):
    """Printed slide size in inches: the physical size of canvases with a dpi, else 7.5 inches tall
    (PowerPoint's standard slide height) at the canvas's aspect ratio."""
    width, height = canvas["width"], canvas["height"]
    if canvas.get("dpi"):
        return round(width / canvas["dpi"], 3), round(height / canvas["dpi"], 3)
    return round(7.5 * width / height, 3), 7.5


def style(canvas):
    inches = print_size(canvas)
    return (STYLE.replace("@@AW@@", str(canvas["width"])).replace("@@AH@@", str(canvas["height"]))
            .replace("@@PW@@", f"{inches[0]:g}").replace("@@PH@@", f"{inches[1]:g}"))


def text(value):
    """HTML-escaped text without the control characters HTML and screen readers cannot use."""
    return escape("".join(c for c in str(value) if c in "\t\n\r" or ord(c) >= 32 and ord(c) not in (0x7F, 0xFFFE, 0xFFFF)))


def inline_svg(data, prefix):
    """The SVG export as an inline ``<svg>`` fragment: ids (and every reference to them) get a per-slide
    prefix so gradients, masks and filters of different slides cannot collide in one document, and the
    fixed pixel size gives way to the slide's box. Returns (markup, raster fallbacks)."""
    root = ET.fromstring(data)
    fallbacks = []
    for meta in root.findall(f"{{{SVG_NS}}}metadata"):
        try:
            fallbacks = json.loads(meta.text)["vixl"]["raster_fallbacks"]
        except (TypeError, ValueError, KeyError):
            fallbacks = []
        root.remove(meta)
    for element in root.iter():
        for key, value in list(element.attrib.items()):
            if key == "id":
                element.set(key, prefix + value)
            elif "url(#" in value:
                element.set(key, URL_REF.sub(lambda match: f"url(#{prefix}{match.group(1)})", value))
            elif key in ("href", XLINK_HREF) and value.startswith("#"):
                element.set(key, "#" + prefix + value[1:])
    for key in ("width", "height"):
        root.attrib.pop(key, None)
    root.set("preserveAspectRatio", "xMidYMid meet")
    root.set("aria-hidden", "true")
    root.set("focusable", "false")
    # The HTML parser puts <svg> in the SVG namespace itself, so the file needs no URL at all.
    return ET.tostring(root, encoding="unicode").replace(f' xmlns="{SVG_NS}"', "", 1), fallbacks


def reading_text(view, variables=None):
    """(title, other lines) of a page as a reader meets it: its title, then the page description (accessibility
    page_alt), then the rest of its own text and the alt text of its images in reading order (the page's explicit
    reading_order, else top to bottom). Master layers and footer-like layers are chrome and are left out."""
    from .accessibility import page_alt, reading_order
    from .deck import CHROME_NAME, _master_ids, _visible, title_layer
    from .render import resolve_layout, resolved_layers
    from .spatial import canvas_boxes

    layers = resolved_layers(view, variables)
    resolved = {item["id"]: item for item in layers}
    bounds = resolve_layout(view, layers=layers)
    canvas = canvas_boxes(view, layers=layers, local=bounds)
    title = title_layer(view, layers)
    masters = _master_ids(view)
    readable = []
    for item in layers:
        words = " ".join((item.get("text") or "").split()) if item["type"] == "text" else ""
        if (not (words or item.get("alt")) or item is title or item["id"] in masters or CHROME_NAME.search(item["name"])
                or not _visible(item, resolved)):
            continue
        readable.append(item)
    lines = [(item.get("text") or "").strip() if item["type"] == "text" else item["alt"]
             for item in reading_order(view.state, readable, canvas)]
    summary = page_alt(view.state)
    return (" ".join(title["text"].split()) if title else ""), ([summary] if summary else []) + lines


def slide_markup(number, total, record, view, media, notes, current, variables=None):
    """(the slide's ``<section>``, its title text): the picture, a visually hidden text layer for screen
    readers, and the speaker notes."""
    title, lines = reading_text(view, variables)
    transition = record.get("transition", "none")
    name = record["name"]
    caption = title or ("" if GENERIC_PAGE.fullmatch(name) or name == "1" else name)
    label = f"Slide {number} of {total}" + (f": {caption}" if caption else "")
    readable = ([f"<h2>{text(title)}</h2>"] if title else [])
    readable += [f"<p>{text(line)}</p>" for chunk in lines for line in chunk.splitlines() if line.strip()]
    from .accessibility import language, page_language

    lang = page_language(view.state)
    attrs = (f'id="slide-{number}" data-n="{number}" data-name="{text(name)}" data-transition="{text(transition)}" '
             f'role="group" aria-roledescription="slide" aria-label="{text(label)}"'
             + (f' lang="{text(lang)}"' if lang and lang != language(view.state) else ""))
    note = f'<aside class="notes" hidden>{text(notes)}</aside>' if notes else ""
    return (f'<section class="slide{" is-cur" if current else ""}" {attrs}>{media}'
            f'<div class="sr" dir="auto">{"".join(readable)}</div>{note}</section>\n'), title


def export_presenter(project, *, pages=None, options=None, variables=None, svg_policy="appearance", scale=1,
                     report=None):
    """The document as one HTML presentation; returns the bytes. ``pages`` picks and orders pages (hidden
    pages are skipped unless named); ``options`` are ``theme``, ``notes``, ``slide_images``, ``start`` and
    ``title`` (see ``parse_options``); ``scale`` sizes ``slide_images="png"`` slides. ``report`` receives
    the slide count, notes count, raster fallbacks per slide and any warnings."""
    from .model import finite
    from .pages import find_page, page_list
    from .render import view_page
    from .svg import export_svg

    state = project.state
    opts = parse_options(options)
    finite(scale, "scale", 0.01, 16)
    require(svg_policy == "appearance" or opts["slide_images"] == "svg", "Strict SVG policy requires SVG slides",
            field="svg_policy")
    if state.get("pages"):
        records = [find_page(state, ref, "pages") for ref in pages] if pages else page_list(project, include_hidden=False)
        require(records, "No pages to present (every page is hidden)", field="pages")
    else:
        require(pages in (None, [], [1], ["1"]), "This document has no pages", field="pages")
        records = [{"id": None, "name": "1"}]
    start = opts["start"]
    if isinstance(start, str) and not start.isdigit():
        wanted = find_page(state, start, "presenter")
        found = [i for i, record in enumerate(records, 1) if record is wanted]
        require(found, f"Page {start!r} is not among the presented pages", field="presenter")
        start = found[0]
    start = int(start)
    require(1 <= start <= len(records), f"start must be 1–{len(records)}", field="presenter")

    slides, fallbacks, titles, noted, size = [], {}, [], 0, 0
    for number, record in enumerate(records, 1):
        view = view_page(project, record["id"]) if record["id"] else project
        if opts["slide_images"] == "png":
            png = project.export(format="PNG", page=record["id"], scale=scale, variables=variables, alpha="auto")
            media = (f'<img src="data:image/png;base64,{base64.b64encode(png).decode("ascii")}" alt="" '
                     'decoding="sync" draggable="false">')
        else:
            media, problems = inline_svg(export_svg(view, variables=variables, svg_policy=svg_policy), f"s{number}-")
            if problems:
                fallbacks[str(number)] = problems
        notes = (record.get("notes") or "") if opts["notes"] else ""
        noted += bool(notes)
        markup, title = slide_markup(number, len(records), record, view, media, notes, number == start, variables)
        slides.append(markup)
        titles.append(title)
        size += len(markup)
        require(size <= project.limits.max_project_bytes, "The presentation exceeds the size limit; use fewer pages, "
                "slide_images=svg or a smaller scale", "resource_limit")

    from .accessibility import document_title, language

    title = opts["title"] or document_title(state) or next((t for t in titles if t), "") or "Presentation"
    css = style(state["canvas"])
    deck = hashlib.sha256("".join(slides).encode("utf-8", "replace")).hexdigest()[:12]
    policy = ("default-src 'none'; img-src data:; style-src 'sha256-%s'; script-src 'sha256-%s'; base-uri 'none'; "
              "form-action 'none'" % (_hash(css), _hash(SCRIPT)))
    html = "".join([
        "<!doctype html>\n",
        f'<html lang="{text(language(state) or "en")}" data-theme="{opts["theme"]}" data-deck="{deck}" '
        f'data-start="{start}">\n',
        '<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n',
        f'<meta http-equiv="Content-Security-Policy" content="{policy}">\n',
        f"<title>{text(title)}</title>\n<style>{css}</style></head>\n<body>\n",
        f'<main class="deck" id="deck" aria-label="{text(title)}"><h1 class="sr">{text(title)}</h1>',
        '<div class="stage" id="stage">\n', *slides,
        '<div class="zone zone-prev" data-go="prev" aria-hidden="true"></div>'
        '<div class="zone zone-next" data-go="next" aria-hidden="true"></div></div></main>',
        CHROME, f"<script>{SCRIPT}</script>\n</body></html>\n",
    ])
    data = html.encode("utf-8", "replace")
    require(len(data) <= project.limits.max_project_bytes, "The presentation exceeds the size limit; use fewer pages, "
            "slide_images=svg or a smaller scale", "resource_limit")
    if report is not None:
        warnings = []
        if len(data) > WARN_BYTES:
            warnings.append(f"The presentation is {len(data) / 1048576:.1f} MiB; browsers open large files slowly. "
                            "Use slide_images=svg, a smaller scale or fewer image-heavy slides")
        report.update(slides=len(records), slide_images=opts["slide_images"], notes=noted, raster_fallbacks=fallbacks)
        if warnings:
            report["warnings"] = [*report.get("warnings", []), *warnings]
    return data


def _hash(content):
    return base64.b64encode(hashlib.sha256(content.encode("utf-8")).digest()).decode("ascii")
