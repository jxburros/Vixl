"""Text flow: one story threaded through a chain of linked text frames.

A flow keeps its source text (plain, or rich with styled spans) in ``state["flows"][name]`` together
with the chain of frames. Each frame is an ordinary text layer whose text is the slice of the story
that fits it: the layer's ``text`` (and ``rich`` record) hold *the already laid-out slice*. PNG, SVG,
PDF and PPTX export therefore need nothing special: they draw several text boxes, exactly as they do
for any other text layers, and the slices wrap to the same lines the continuous text would have.

``reflow`` fills the frames in order. For each frame it finds the longest run of whole words that
still fits the frame when the frame's own text engine lays it out (the same functions the renderer
and the ``bounds`` check use), then applies the paragraph rules (keep paragraphs together, minimum
orphan and widow lines). What is left over after the last frame is reported as ``overflow`` with the
number of remaining characters. Editing the story, or changing a frame's size, font or size,
re-flows the chain at the end of the batch; ``text-flow reflow`` does it on demand.

Frames can sit on different pages of a multi-page document, one frame can hold several columns
(each column is a linked text layer), and a frame can follow a shape: its largest inscribed
rectangle, or one-line bands that follow the shape's outline.
"""

from bisect import bisect_right
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import math
import re
import unicodedata

from .errors import VixlError, require
from .model import finite, new_layer

TYPES = ("text-flow",)
ACTIONS = ("create", "set", "add-frame", "link", "unlink", "reflow", "style", "delete")
ALIGNS = ("left", "center", "right", "justify")
SHAPE_MODES = ("bands", "inscribed")
STYLE_KEYS = ("font", "size", "color", "align", "spacing", "line_height", "stroke_width", "stroke_color")
RICH_KEYS = ("line_height", "paragraph_spacing", "list_indent", "font_variants")
FORMAT_KEYS = ("bold", "italic", "underline", "strike", "color", "size", "highlight", "baseline", "tracking", "list", "level",
               "align", "space_before", "space_after", "indent", "number_start", "line_height", "paragraph_spacing",
               "list_indent")
MAX_FRAMES = 200
MAX_TEXT = 100000


def schemas(add):
    from .schema import S, N, B, enum

    int0 = {"type": "integer", "minimum": 0}
    frame = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "x": N, "y": N, "width": N, "height": N,
            "columns": {"type": "integer", "minimum": 1, "maximum": 12}, "gutter": N,
            "page": {"type": ["string", "integer"]},
            "layer": {"type": "string", "description": "An existing text layer to use as this frame (its box can be resized with x/y/width/height)."},
            "shape": {"type": "string", "description": "An existing shape layer to flow text into."},
            "mode": enum(*SHAPE_MODES), "inset": N,
        },
    }
    ref = {"type": ["string", "integer"], "description": "A frame number (1 is the first), or the ID or name of one of its layers."}
    props = {
        "action": enum(*ACTIONS), "name": S, "text": S, "markdown": S,
        "spans": {"type": "array", "items": {"type": "object"}, "maxItems": 4000},
        "paragraphs": {"anyOf": [{"type": "array", "items": {"type": "object"}}, {"type": "array", "items": int0}, {"enum": ["all"]}]},
        "target": S, "frames": {"type": "array", "items": frame, "maxItems": MAX_FRAMES},
        "frame": ref, "layers": {"type": "array", "items": S}, "after": ref, "before": ref,
        "x": N, "y": N, "width": N, "height": N, "columns": {"type": "integer", "minimum": 1, "maximum": 12}, "gutter": N,
        "page": {"type": ["string", "integer"]}, "shape": S, "mode": enum(*SHAPE_MODES), "inset": N,
        "font": S, "size": N, "color": S, "align": enum(*ALIGNS), "spacing": N, "line_height": N, "paragraph_spacing": N,
        "list_indent": N, "font_variants": {"type": "object"}, "stroke_width": N, "stroke_color": S,
        "keep_together": B, "keep_with_next": B, "orphans": int0, "widows": int0, "delete_frames": B,
        "match": S, "occurrence": {"anyOf": [{"type": "integer", "minimum": 1}, {"enum": ["all"]}]},
        "start": int0, "end": int0, "clear": B,
        "format": {"type": "object", "description": "action style: character and paragraph styles to apply, as in text-style "
                   "(bold, italic, underline, strike, color, size, highlight, baseline, tracking, list, level, align, "
                   "space_before, space_after, indent, number_start)."},
    }
    add("text-flow", props, ["name"])


def _all_layers(state):
    for layer in state.get("layers", []):
        yield layer, state.get("page")
    for page in state.get("pages") or []:
        for layer in (page.get("content") or {}).get("layers", []):
            yield layer, page["id"]


def locate(state, ident):
    """(layer, page id) of the layer with this ID, wherever it lives; (None, None) when it is gone."""
    for layer, page in _all_layers(state):
        if layer["id"] == ident:
            return layer, page
    return None, None


def find_layer(state, ref):
    """A layer by ID or name, preferring the active page."""
    matches = [(layer, page) for layer, page in _all_layers(state) if ref in (layer["id"], layer["name"])]
    require(matches, f"Layer {ref!r} does not exist", "layer_not_found", field="layers")
    return matches[0]


@contextmanager
def on_page(project, page):
    """Make ``page`` (a name, number or ID) the active page while creating layers on it."""
    from . import pages

    state = project.state
    if page is None or not pages.has_pages(state):
        require(page in (None, 1, "1") or not page, "This document has no pages; create one with page add", field="page")
        yield
        return
    record = pages.find_page(state, page)
    previous = state.get("page")
    pages.select(state, page=record["id"])
    try:
        yield
    finally:
        if previous and previous != state.get("page"):
            if previous.startswith(pages.MASTER_PREFIX):
                pages.select(state, master=previous[len(pages.MASTER_PREFIX):])
            else:
                pages.select(state, page=previous)


def _page_name(state, page_id):
    for page in state.get("pages") or []:
        if page["id"] == page_id:
            return page["name"]
    return None


# A story is plain text or rich spans, sliced by character.


def _normalise_text(text):
    require(isinstance(text, str), "text must be text", field="text")
    text = text.replace("\r\n", "\n").replace("\r", "\n").expandtabs(4)
    require(len(text) <= MAX_TEXT, f"A flow holds at most {MAX_TEXT} characters", "resource_limit", field="text")
    return text


class Story:
    """Source text with its word boundaries, and optional rich spans and paragraph settings."""

    def __init__(self, text, rich=None):
        self.text, self.rich = text, rich
        self.ends = [i for i in range(1, len(text) + 1) if not text[i - 1].isspace() and (i == len(text) or text[i].isspace())]
        self.numbers = _numbering(rich) if rich else None

    def paragraph_of(self, position):
        return self.text.count("\n", 0, position)

    def is_heading(self, start, end, size):
        """Whether text[start:end] is one paragraph set entirely in bold, larger than the body text."""
        if self.rich is None or start >= end:
            return False
        cursor, seen = 0, False
        for span in self.rich["spans"]:
            lo, hi = max(start, cursor), min(end, cursor + len(span["text"]))
            cursor += len(span["text"])
            if lo < hi and span["text"][lo - (cursor - len(span["text"])):hi - (cursor - len(span["text"]))].strip():
                seen = True
                if not span.get("bold") or float(span.get("size", size)) < size * 1.1:
                    return False
        return seen

    def slice(self, a, b, size=48.0):
        """(text, rich slice or None) for characters [a, b); ``size`` is the frame's font size."""
        text = self.text[a:b]
        if self.rich is None:
            return text, None
        return text, _slice_rich(self.rich, self.text, a, b, self.numbers, size)


def _numbering(rich):
    """The number every numbered paragraph shows, so a slice can start counting where the story had got to."""
    counters, numbers = {}, []
    for settings in rich.get("paragraphs", []):
        kind, level = settings.get("list", "none"), settings.get("level", 0)
        if kind == "none":
            counters.clear()
            numbers.append(None)
            continue
        for key in [k for k in counters if k[0] > level or (k[0] == level and k[1] != kind)]:
            counters.pop(key)
        counters[(level, kind)] = counters.get((level, kind), settings.get("start", 1) - 1) + 1
        numbers.append(counters[(level, kind)] if kind == "number" else None)
    return numbers


def _slice_rich(rich, text, a, b, numbers, size):
    """Spans and paragraph settings for text[a:b]; a paragraph that continues from the previous frame
    loses its bullet or number (and keeps its indent) and its space before."""
    from .richtext import normalize_spans

    spans, cursor = [], 0
    for span in rich["spans"]:
        start, end = cursor, cursor + len(span["text"])
        cursor = end
        lo, hi = max(a, start), min(b, end)
        if lo < hi:
            spans.append({**span, "text": span["text"][lo - start:hi - start]})
    first = text.count("\n", 0, a)
    count = text.count("\n", a, b) + 1
    settings = rich.get("paragraphs", [])
    paragraphs = [deepcopy(settings[first + i]) if first + i < len(settings) else {} for i in range(count)]
    for i, item in enumerate(paragraphs):
        if item.get("list") == "number" and numbers and numbers[first + i]:
            item["start"] = numbers[first + i]
    if a > 0 and text[a - 1] != "\n":  # continues a paragraph that began in an earlier frame
        item = paragraphs[0]
        if item.get("list", "none") != "none":
            # The marker's room becomes plain indent, so the continuation lines up with the first lines.
            item["indent"] = item.get("indent", 0) + float(rich.get("list_indent") or size * 1.4)
            item.pop("list", None)
            item.pop("start", None)
        item["space_before"] = 0
    result = {"spans": normalize_spans(spans), "paragraphs": paragraphs}
    for key in RICH_KEYS:
        if key in rich:
            result[key] = deepcopy(rich[key])
    return result


class Oracle:
    """How much of the story fits a frame: asks the same layout code that draws the frame."""

    def __init__(self, project, story, layer, shared=None):
        self.project, self.story, self.layer = project, story, layer
        self.width, self.height = layer["width"], layer["height"]
        self.cache = {}
        self.shared = {} if shared is None else shared  # wrapped paragraphs, reused by frames of the same width and style
        self.rich = story.rich is not None
        self.size = float(layer.get("size", 48))
        self.spacing = float(layer.get("spacing", 4))
        if not self.rich:
            from .text import face, font_data

            self.data = font_data(project, {**layer, "text": story.text})
            outline = face(self.data)[0]
            factor = self.size / outline["head"].unitsPerEm
            self.line = (outline["hhea"].ascent - outline["hhea"].descent) * factor + self.spacing

    def metrics(self, a, b):
        """(bottom of the last line in px, lines in each paragraph) for text[a:b] laid out in this frame."""
        key = (a, b)
        if key not in self.cache:
            text, rich = self.story.slice(a, b, self.size)
            if rich is None:
                counts = [self.paragraph_lines(paragraph) for paragraph in text.split("\n")]
                bottom = sum(counts) * self.line - self.spacing
            else:
                from .richtext import layout

                synthetic = {**self.layer, "text": text, "rich": rich}
                result = layout(self.project, synthetic)
                counts = [0] * (text.count("\n") + 1)
                for top, baseline, height, paragraph, descent in result.lines:
                    counts[min(paragraph, len(counts) - 1)] += 1
                top, _, height, _, _ = result.lines[-1]
                bottom = top + height + self.layer.get("stroke_width", 0)
            self.cache[key] = (bottom, counts)
        return self.cache[key]

    def paragraph_lines(self, paragraph):
        key = (self.layer.get("font"), self.size, self.width, paragraph)
        if key not in self.shared:
            from .text import lines

            self.shared[key] = len(lines(self.data, paragraph, self.size, self.width))
        return self.shared[key]

    def limit(self):
        return self.height + (0.5 if self.rich else 0.01)

    def fits(self, a, b):
        return self.metrics(a, b)[0] <= self.limit()

    def counts(self, a, b):
        return self.metrics(a, b)[1]

    def estimate(self):
        """A first guess at how many characters fit, to start the search near the answer."""
        lines = max(1.0, math.floor((self.height + self.spacing) / max(1.0, self.size * 1.25)))
        return max(8, int(lines * self.width / max(1.0, self.size * 0.5)))


def _skip_space(text, position):
    while position < len(text) and text[position].isspace():
        position += 1
    return position


def _fill(story, oracle, a, whole_words):
    """The end of the longest slice starting at ``a`` that fits the frame (``a`` when nothing fits)."""
    text, ends = story.text, story.ends
    first = bisect_right(ends, a)
    if first >= len(ends):
        return a
    last = len(ends) - 1
    if not oracle.fits(a, ends[first]):
        if whole_words:
            return a
        # One word wider (or taller) than the frame: break it where it still fits.
        low, high = a, ends[first]
        while high - low > 1:
            middle = (low + high) // 2
            if oracle.fits(a, middle):
                low = middle
            else:
                high = middle
        while low > a and low < len(text) and unicodedata.combining(text[low]):
            low -= 1
        return low
    # Search the word ends for the last one that fits. The height of the slice grows about linearly with its
    # length, so interpolating on the measured heights needs far fewer layouts than plain bisection (a rich
    # layout is not cheap); every third step bisects, which keeps the worst case logarithmic.
    limit = oracle.limit()
    low, bottom_low = first, oracle.metrics(a, ends[first])[0]
    high, bottom_high = None, None
    guess = max(first + 1, min(last, bisect_right(ends, a + oracle.estimate()) - 1))
    step = 0
    while True:
        if high is None:
            if low >= last:
                return ends[last]
            if step == 0:
                index = guess
            else:
                reach = (ends[low] - a) * min(4.0, limit / max(bottom_low, 1e-6))
                index = max(low + 1, min(last, bisect_right(ends, a + reach) - 1))
        else:
            if high - low <= 1:
                break
            if step % 3 == 2:
                index = (low + high) // 2
            else:
                fraction = min(0.95, max(0.05, (limit - bottom_low) / max(bottom_high - bottom_low, 1e-6)))
                index = bisect_right(ends, ends[low] + (ends[high] - ends[low]) * fraction)
                index = max(low + 1, min(high - 1, index))
        bottom = oracle.metrics(a, ends[index])[0]
        if bottom <= limit:
            low, bottom_low = index, bottom
        else:
            high, bottom_high = index, bottom
        step += 1
    return ends[low]


def _adjust(story, oracle, a, e, options):
    """Move the end of a slice so the paragraph rules hold: keep paragraphs together, minimum orphan and
    widow lines, and no heading left alone at the bottom of a frame."""
    text, ends = story.text, story.ends
    e = _split_rules(story, oracle, a, e, options)
    while options.get("keep_with_next") and a < e < len(text):
        ps = text.rfind("\n", 0, e) + 1
        pe = text.find("\n", e)
        pe = len(text) if pe < 0 else pe
        index = bisect_right(ends, ps) - 1
        if text[e:pe].strip() or ps <= a or index < 0 or ends[index] <= a or not story.is_heading(ps, e, oracle.size):
            break
        e = ends[index]
    return e


def _split_rules(story, oracle, a, e, options):
    """Keep-together, orphan and widow rules for a slice that ends inside a paragraph."""
    text, ends = story.text, story.ends
    if e >= len(text) or e <= a:
        return e
    keep, orphans, widows = options["keep_together"], options["orphans"], options["widows"]
    ps = text.rfind("\n", 0, e) + 1
    pe = text.find("\n", e)
    pe = len(text) if pe < 0 else pe
    began_here = ps >= a
    movable = began_here and ps > a

    def before_paragraph():
        index = bisect_right(ends, ps) - 1
        return ends[index] if index >= 0 and ends[index] > a else e

    if not text[e:pe].strip():
        return e  # the paragraph ends here
    if not (keep or orphans > 1 or widows > 1):
        return e

    k = oracle.counts(a, e)[-1]
    rest = _skip_space(text, e)
    m = oracle.counts(rest, pe)[0]
    if keep and movable and oracle.fits(ps, pe):
        return before_paragraph()
    if orphans > 1 and movable and k < orphans:
        return before_paragraph()
    if widows > 1 and m < widows:
        target = k - (widows - m)
        floor = orphans if began_here else 1
        if target >= max(1, floor):
            lo = bisect_right(ends, max(ps, a))
            hi = bisect_right(ends, e - 1)
            candidates = [x for x in ends[lo:hi] if a < x < e]
            best = None
            low, high = 0, len(candidates) - 1
            while low <= high:
                middle = (low + high) // 2
                if oracle.counts(a, candidates[middle])[-1] <= target:
                    best, low = candidates[middle], middle + 1
                else:
                    high = middle - 1
            if best is not None:
                return best
        elif movable:
            return before_paragraph()
    return e


def _slots(state, rec):
    """[(layer, page id)] for the chain's frames in order; frames whose layer is gone are left out."""
    slots = []
    for frame in rec["frames"]:
        for ident in frame["layers"]:
            layer, page = locate(state, ident)
            if layer is not None:
                slots.append((layer, page))
    return slots


def _story(rec):
    return Story(rec["text"], rec.get("rich"))


def _signature(state, rec):
    parts = [rec["text"], json.dumps(rec.get("rich"), sort_keys=True), rec.get("keep_together"), rec.get("keep_with_next"),
             rec.get("orphans"), rec.get("widows"), rec.get("whole_words")]
    for layer, page in _slots(state, rec):
        parts.append([layer["id"], layer["width"], layer["height"], layer.get("font"), layer.get("size"), layer.get("spacing"),
                      layer.get("align"), layer.get("stroke_width"), layer.get("text"), json.dumps(layer.get("rich"), sort_keys=True)])
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def reflow(project, name):
    """Fill the chain's frames with the story and record where it ended."""
    state = project.state
    rec = state["flows"][name]
    story = _story(rec)
    slots = _slots(state, rec)
    options = {"keep_together": bool(rec.get("keep_together")), "orphans": int(rec.get("orphans", 1)),
               "widows": int(rec.get("widows", 1)), "keep_with_next": bool(rec.get("keep_with_next", True))}
    ranges, position, shared = [], 0, {}
    for index, (layer, page) in enumerate(slots):
        a = position if index == 0 else _skip_space(story.text, position)
        if a >= len(story.text) or not story.text[a:].strip():
            ranges.append([a if a < len(story.text) else len(story.text)] * 2)
            continue
        oracle = Oracle(project, story, layer, shared)
        end = _fill(story, oracle, a, bool(rec.get("whole_words", {}).get(layer["id"])))
        end = _adjust(story, oracle, a, end, options)
        ranges.append([a, end])
        position = end
    for (layer, _), (a, b) in zip(slots, ranges):
        text, rich = story.slice(a, b, float(layer.get("size", 48))) if b > a else ("", None)
        layer["text"] = text
        if rich is None:
            layer.pop("rich", None)
        else:
            layer["rich"] = rich
        layer["text_layout"] = {"width": layer["width"], "height": layer["height"]}
        layer["auto_size"] = False
    remaining = story.text[position:].strip() if slots else story.text.strip()
    rec["ranges"] = ranges
    rec["frames_text"] = [layer["id"] for layer, _ in slots]
    rec["overflow"] = {"overflow": bool(remaining), "remaining_chars": len(remaining),
                       "remaining_words": len(remaining.split()), "from": position if remaining else None}
    rec["signature"] = _signature(state, rec)
    return rec["overflow"]


def refresh(project):
    """After a batch: forget deleted frames, and re-flow every chain whose story or frames changed.
    Returns the names of the flows that were re-flowed."""
    state = project.state
    flows = state.get("flows")
    reflowed = []
    if not flows:
        return reflowed
    alive = {layer["id"] for layer, _ in _all_layers(state)}
    for name, rec in flows.items():
        for frame in rec["frames"]:
            frame["layers"] = [i for i in frame["layers"] if i in alive]
        rec["frames"] = [f for f in rec["frames"] if f["layers"]]
        if rec.get("signature") != _signature(state, rec):
            reflow(project, name)
            reflowed.append(name)
    return reflowed


def _default_color(state):
    from .colors import parse
    from .design import resolve_color

    try:
        background = parse(resolve_color(state["canvas"].get("background", "white"), state))
    except VixlError:
        return "#111111"
    if background[3] < 0.1:
        return "#111111"
    return "#111111" if (0.2126 * background[0] + 0.7152 * background[1] + 0.0722 * background[2]) > 0.45 else "#ffffff"


def _style_from(project, op, rec_style=None):
    """The shared look of the frames: font, size, colour, alignment, leading, outline."""
    from .render import resolve_font

    style = dict(rec_style or {})
    if "font" in op:
        font, role = resolve_font(project, op["font"])
        from .operations import embed_font_file

        holder = {"font": font}
        embed_font_file(project, holder)
        style["font"] = holder["font"]
        style.pop("font_role", None)
        if role:
            style["font_role"] = role
    for key in ("size", "color", "align", "spacing", "stroke_width", "stroke_color", "line_height"):
        if key in op:
            style[key] = op[key]
    if "font" not in style:
        if (project.state.get("typography") or {}).get("body"):
            font, role = resolve_font(project, "body")
            style["font"], style["font_role"] = font, role
        else:
            style["font"] = "DejaVuSans.ttf"
    style.setdefault("size", 18)
    style.setdefault("color", _default_color(project.state))
    style.setdefault("align", "left")
    finite(style["size"], "size", 1, 4096)
    if "spacing" in style:
        finite(style["spacing"], "spacing", 0, 1000)
    if "line_height" in style:
        finite(style["line_height"], "line_height", 0.5, 5)
    if "stroke_width" in style:
        finite(style["stroke_width"], "stroke_width", 0, 100)
    from .design import resolve_color
    from .render import color

    color(resolve_color(style["color"], project.state))
    return style


def _plain_spacing(project, style):
    """Extra leading for plain frames: ``spacing`` px, or what ``line_height`` (a factor of the size) asks for."""
    if "spacing" in style:
        return style["spacing"]
    if "line_height" in style:
        from .text import face, font_data

        data = font_data(project, {"font": style["font"], "text": "x"})
        outline = face(data)[0]
        natural = (outline["hhea"].ascent - outline["hhea"].descent) * style["size"] / outline["head"].unitsPerEm
        return max(0, round(style["size"] * style["line_height"] - natural))
    return 4


def _new_frame_layer(project, name, style, rect, parent=None):
    from .operations import append_layer

    x, y, w, h = rect
    w, h = max(1, int(round(w))), max(1, int(round(h)))
    layer = new_layer(name, "text", w, h, text="", font=style["font"], size=style["size"], color=style["color"],
                      align=style["align"] if style["align"] != "justify" else "left", spacing=_plain_spacing(project, style),
                      auto_size=False, text_layout={"width": w, "height": h})
    if style.get("font_role"):
        layer["font_role"] = style["font_role"]
    for key in ("stroke_width", "stroke_color"):
        if key in style:
            layer[key] = style[key]
    layer["x"], layer["y"] = float(x), float(y)
    if parent:
        layer["parent"] = parent
    append_layer(project, layer)
    return layer


def _column_rects(x, y, width, height, columns, gutter):
    """Rectangles of equal columns inside a frame; spare pixels go to the first columns."""
    require(width > columns * 8 + gutter * (columns - 1), "The frame is too narrow for its columns and gutter", field="width")
    usable = width - gutter * (columns - 1)
    base, extra = divmod(int(usable), columns)
    rects, cursor = [], float(x)
    for i in range(columns):
        w = base + (1 if i < extra else 0)
        rects.append((cursor, float(y), w, height))
        cursor += w + gutter
    return rects


def _free_name(state, base):
    taken = {layer["name"] for layer, _ in _all_layers(state)} | {layer["id"] for layer, _ in _all_layers(state)}
    index = 1
    while f"{base}-{index}" in taken:
        index += 1
    return f"{base}-{index}"


def _inscribed(project, layer):
    """The largest axis-aligned rectangle that fits inside a shape layer, in the layer's parent coordinates."""
    import numpy as np

    from .render import layer_image, resolve_layout

    bounds = resolve_layout(project)[layer["id"]]
    image = layer_image(project, layer, bounds)
    scale = max(1.0, max(image.size) / 160)
    small = image.getchannel("A").resize((max(1, round(image.width / scale)), max(1, round(image.height / scale))))
    mask = np.asarray(small) > 127
    rows, cols = mask.shape
    heights = np.zeros(cols, dtype=int)
    best = (0, 0, 0, 0, 0)  # area, row, col, h, w
    for r in range(rows):
        heights = np.where(mask[r], heights + 1, 0)
        stack = []
        for c in range(cols + 1):
            h = heights[c] if c < cols else 0
            start = c
            while stack and stack[-1][1] >= h:
                s, hh = stack.pop()
                area = hh * (c - s)
                if area > best[0]:
                    best = (area, r - hh + 1, s, hh, c - s)
                start = s
            stack.append((start, h))
    require(best[0] > 0, f"Shape {layer['name']!r} has no filled area to flow text into", field="shape")
    _, r, c, h, w = best
    return (bounds[0] + c * scale, bounds[1] + r * scale, w * scale, h * scale), (bounds, mask, scale)


def _band_rects(project, layer, style, inset):
    """One-line rectangles following a shape's outline, top to bottom."""
    from .text import face, font_data

    rect, (bounds, mask, scale) = _inscribed(project, layer)
    data = font_data(project, {"font": style["font"], "text": "x"})
    outline = face(data)[0]
    natural = (outline["hhea"].ascent - outline["hhea"].descent) * style["size"] / outline["head"].unitsPerEm
    spacing = _plain_spacing(project, style)
    pitch = natural + spacing
    height = math.ceil(natural)
    rows, cols = mask.shape
    rects, y = [], 0.0
    while y + natural <= rows * scale and len(rects) < 120:
        top, bottom = int(y / scale), max(int(y / scale) + 1, math.ceil((y + natural) / scale))
        band = mask[top:min(bottom, rows)]
        if band.size:
            filled = band.all(axis=0)
            runs, start = [], None
            for c in range(cols + 1):
                on = c < cols and filled[c]
                if on and start is None:
                    start = c
                if not on and start is not None:
                    runs.append((start, c))
                    start = None
            if runs:
                left, right = max(runs, key=lambda run: run[1] - run[0])
                x0, x1 = bounds[0] + left * scale + inset, bounds[0] + right * scale - inset
                if x1 - x0 >= style["size"] * 4:
                    rects.append((x0, bounds[1] + y, x1 - x0, height))
        y += pitch
    require(rects, f"Shape {layer['name']!r} is too small for lines of {style['size']} px text", field="shape")
    return rects


def _make_frames(project, name, rec, spec):
    """Create the layer(s) for one frame spec; returns the frame record."""
    state = project.state
    style = rec["style"]
    if spec.get("layer"):
        layer, page = find_layer(state, spec["layer"])
        require(layer["type"] == "text", f"Layer {spec['layer']!r} is not a text layer", field="layer")
        for key in ("x", "y", "width", "height"):
            if key in spec:
                layer[key] = spec[key] if key in ("x", "y") else int(spec[key])
        box = layer.get("text_layout") or {}
        require("width" in box or "width" in spec, f"Give the width and height of the frame for text layer {spec['layer']!r}", field="width")
        layer["text_layout"] = {"width": layer["width"], "height": layer["height"]}
        layer["auto_size"] = False
        return {"layers": [layer["id"]], "gutter": 0}
    page = spec.get("page")
    if spec.get("shape"):
        shape, shape_page = find_layer(state, spec["shape"])
        require(shape["type"] in ("shape", "solid", "frame", "group", "raster", "pathfinder"), "shape must be a shape layer", field="shape")
        inset = float(spec.get("inset", 0))
        bands = spec.get("mode", "bands") == "bands"
        if bands:
            rects = _band_rects(project, shape, style, inset)
        else:
            x, y, w, h = _inscribed(project, shape)[0]
            rects = [(x + inset, y + inset, w - 2 * inset, h - 2 * inset)]
        page = page if page is not None else shape_page
        parent = shape.get("parent")
        ids = []
        with on_page(project, page):
            for rect in rects:
                ids.append(_new_frame_layer(project, _free_name(state, name), style, rect, parent)["id"])
        if bands:  # a one-line band never splits a word that is too wide for it; the word moves on
            for ident in ids:
                rec.setdefault("whole_words", {})[ident] = True
        return {"layers": ids, "gutter": 0, "shape": shape["id"]}
    for key in ("x", "y", "width", "height"):
        require(key in spec, f"A frame needs {key} (or a layer or shape to follow)", field=key)
    columns = int(spec.get("columns", 1))
    gutter = float(spec.get("gutter", round(style["size"] * 1.5) if columns > 1 else 0))
    rects = _column_rects(spec["x"], spec["y"], spec["width"], spec["height"], columns, gutter)
    ids = []
    with on_page(project, page):
        for rect in rects:
            ids.append(_new_frame_layer(project, _free_name(state, name), style, rect)["id"])
    return {"layers": ids, "gutter": gutter}


def _frame_specs(op):
    specs = [deepcopy(f) for f in op.get("frames") or []]
    inline = {k: op[k] for k in ("x", "y", "width", "height", "columns", "gutter", "page", "shape", "mode", "inset") if k in op}
    if inline and not specs and (("width" in inline and "height" in inline) or "shape" in inline):
        specs.append(inline)
    return specs


def _story_from(project, op, style, rec=None, adopted=None):
    """(text, rich) for the operation's text, markdown, spans or an adopted layer; None when it carries none."""
    from .richtext import _make_rich, plain

    given = [k for k in ("text", "markdown", "spans") if k in op]
    require(len(given) <= 1, "Pass one of text, markdown or spans", field=given[1] if len(given) > 1 else None)
    if adopted is not None and not given:
        rich = deepcopy(adopted.get("rich")) if adopted.get("rich") else None
        if rich:
            from .richtext import active

            if not active(adopted):
                rich = None
        return _normalise_text(adopted["text"]), rich
    if "text" in op:
        return _normalise_text(op["text"]), None
    if given:
        rich = _make_rich(project, {k: v for k, v in op.items() if k in ("markdown", "spans", "paragraphs") or k in RICH_KEYS},
                          float(style["size"]))
        text = plain(rich)
        converted = _normalise_text(text)
        require(converted == text, "Rich flows cannot contain tab characters; use spaces", field="spans")
        return text, rich
    return None


def _apply_rich_options(rec, op):
    """Line height, paragraph spacing and justification for rich flows."""
    rich = rec.get("rich")
    style = rec["style"]
    if style.get("align") == "justify" and rich is None:
        rich = rec["rich"] = {"spans": [{"text": rec["text"]}], "paragraphs": [{} for _ in range(rec["text"].count("\n") + 1)]}
    if rich is None:
        return
    for key in RICH_KEYS:
        if key in op and key != "font_variants":
            rich[key] = op[key]
    if "line_height" in style and "line_height" not in rich:
        rich["line_height"] = style["line_height"]
    if style.get("align") == "justify":
        for item in rich["paragraphs"]:
            item.setdefault("align", "justify")
    elif style.get("align") in ("left", "center", "right") and "align" in op:
        for item in rich["paragraphs"]:
            item["align"] = style["align"]


def _options_from(op, rec):
    for key in ("keep_together", "keep_with_next"):
        if key in op:
            rec[key] = bool(op[key])
    for key in ("orphans", "widows"):
        if key in op:
            require(isinstance(op[key], int) and 0 <= op[key] <= 20, f"{key} must be a whole number of lines (0–20)", field=key)
            rec[key] = op[key]


def execute(project, op):
    state = project.state
    flows = state.setdefault("flows", {})
    name = op["name"]
    require(re.fullmatch(r"[\w-]{1,100}", name), "Flow names use 1–100 letters, numbers, underscores or hyphens", field="name")
    action = op.get("action") or ("set" if name in flows else "create")
    if action != "create":
        close = [] if name in flows else __import__("difflib").get_close_matches(name, list(flows), 3, 0.5)
        require(name in flows, f"Unknown text flow {name!r}" + (f"; did you mean {' or '.join(map(repr, close))}?" if close else
                                                                  f". Flows: {', '.join(flows) or 'none'}"), field="name")
    if action == "create":
        _create(project, name, op)
    elif action == "delete":
        _delete(project, name, op)
    else:
        rec = flows[name]
        if action == "set":
            _set(project, name, rec, op)
        elif action == "add-frame":
            _add_frames(project, name, rec, op)
        elif action == "link":
            _link(project, name, rec, op)
        elif action == "unlink":
            _unlink(project, name, rec, op)
        elif action == "style":
            _style(project, rec, op)
        reflow(project, name)
    if not state["flows"]:
        state.pop("flows")


def _create(project, name, op):
    state = project.state
    flows = state["flows"]
    require(name not in flows, f"Text flow {name!r} already exists; change it with action set", field="name")
    adopted = None
    if op.get("target"):
        adopted, _ = find_layer(state, op["target"])
        require(adopted["type"] == "text", "target must be a text layer", field="target")
    base = {}
    if adopted is not None:
        base = {k: adopted[k] for k in ("font", "size", "color", "align", "spacing", "stroke_width", "stroke_color", "font_role") if k in adopted}
    style = _style_from(project, op, base)
    story = _story_from(project, op, style, adopted=adopted)
    require(story is not None, "Pass the story as text, markdown or spans (or target: an existing text layer)", field="text")
    rec = {"text": story[0], "style": style, "frames": [], "keep_together": False, "orphans": 1, "widows": 1}
    if story[1]:
        rec["rich"] = story[1]
    _options_from(op, rec)
    _apply_rich_options(rec, op)
    flows[name] = rec
    specs = _frame_specs(op) if adopted is None else [
        {"layer": adopted["id"], **{k: op[k] for k in ("x", "y", "width", "height") if k in op}},
        *_frame_specs({"frames": op.get("frames")})]
    for layer_ref in op.get("layers") or []:
        specs.append({"layer": layer_ref})
    require(specs, "Give the frame(s): frames, or x, y, width and height, or a shape or layers to follow", field="frames")
    for spec in specs:
        rec["frames"].append(_make_frames(project, name, rec, spec))
    _check_limits(project, rec)


def _check_limits(project, rec):
    total = sum(len(f["layers"]) for f in rec["frames"])
    require(total <= MAX_FRAMES, f"A flow holds at most {MAX_FRAMES} frames", "resource_limit", field="frames")


def _frame_index(state, rec, ref, field="frame"):
    """Index into rec["frames"] for a 1-based number or a layer ID/name."""
    frames = rec["frames"]
    if isinstance(ref, int) and not isinstance(ref, bool):
        require(1 <= ref <= len(frames), f"Frame number must be 1–{len(frames)}", field=field)
        return ref - 1
    if isinstance(ref, str) and ref.isdigit():
        return _frame_index(state, rec, int(ref), field)
    layer, _ = find_layer(state, ref)
    for index, frame in enumerate(frames):
        if layer["id"] in frame["layers"]:
            return index
    raise VixlError("invalid_operation", f"Layer {ref!r} is not a frame of this flow", field=field)


def _set(project, name, rec, op):
    state = project.state
    if any(k in op for k in STYLE_KEYS):
        rec["style"] = _style_from(project, op, rec["style"])
        for layer, _ in _slots(state, rec):
            style = rec["style"]
            layer.update(font=style["font"], size=style["size"], color=style["color"],
                         align=style["align"] if style["align"] != "justify" else "left", spacing=_plain_spacing(project, style))
            layer.pop("font_role", None)
            if style.get("font_role"):
                layer["font_role"] = style["font_role"]
            for key in ("stroke_width", "stroke_color"):
                if key in style:
                    layer[key] = style[key]
    story = _story_from(project, op, rec["style"])
    if story is not None:
        rec["text"] = story[0]
        rec.pop("rich", None)
        if story[1]:
            rec["rich"] = story[1]
    _options_from(op, rec)
    _apply_rich_options(rec, op)
    if "frame" in op and any(k in op for k in ("x", "y", "width", "height", "columns", "gutter")):
        _reshape(project, name, rec, op)
    elif any(k in op for k in ("x", "y", "width", "height", "columns", "gutter")) and "frame" not in op:
        require(len(rec["frames"]) == 1, "Say which frame to change with frame (1 is the first)", field="frame")
        _reshape(project, name, rec, {**op, "frame": 1})
    if op.get("frames"):
        for spec in _frame_specs(op):
            rec["frames"].append(_make_frames(project, name, rec, spec))
    _check_limits(project, rec)


def _reshape(project, name, rec, op):
    """Move, resize or re-split one frame (its columns) without losing its place in the chain."""
    state = project.state
    index = _frame_index(state, rec, op["frame"])
    frame = rec["frames"][index]
    layers = [locate(state, i) for i in frame["layers"]]
    layers = [(layer, page) for layer, page in layers if layer is not None]
    require(layers, "That frame has no layers left", field="frame")
    first, page = layers[0]
    x = op.get("x", min(layer["x"] for layer, _ in layers))
    y = op.get("y", first["y"])
    width = op.get("width", max(layer["x"] + layer["width"] for layer, _ in layers) - min(layer["x"] for layer, _ in layers))
    height = op.get("height", first["height"])
    columns = int(op.get("columns", len(layers)))
    gutter = float(op.get("gutter", frame.get("gutter", 0)))
    rects = _column_rects(x, y, width, height, columns, gutter)
    style = rec["style"]
    keep = [layer for layer, _ in layers[:columns]]
    for layer, rect in zip(keep, rects):
        layer["x"], layer["y"], layer["width"], layer["height"] = float(rect[0]), float(rect[1]), int(rect[2]), int(rect[3])
        layer["text_layout"] = {"width": layer["width"], "height": layer["height"]}
    ids = [layer["id"] for layer in keep]
    if columns > len(layers):
        with on_page(project, page):
            for rect in rects[len(layers):]:
                ids.append(_new_frame_layer(project, _free_name(state, name), style, rect, first.get("parent"))["id"])
    elif columns < len(layers):
        from .operations import execute as apply

        for layer, _ in layers[columns:]:
            with on_page(project, locate(state, layer["id"])[1]):
                apply(project, {"type": "remove", "target": layer["id"]})
    frame["layers"], frame["gutter"] = ids, gutter


def _position(state, rec, ref, after, field):
    """Index in rec["frames"] to insert at, before or after a frame (number) or a layer. A layer inside a
    frame of several columns splits that frame there, so the chain order is kept exactly."""
    index = _frame_index(state, rec, ref, field)
    whole = isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit())
    if whole:
        return index + 1 if after else index
    frame = rec["frames"][index]
    at = frame["layers"].index(find_layer(state, ref)[0]["id"]) + (1 if after else 0)
    if 0 < at < len(frame["layers"]):
        rec["frames"].insert(index + 1, {**frame, "layers": frame["layers"][at:]})
        frame["layers"] = frame["layers"][:at]
        return index + 1
    return index + 1 if at else index


def _add_frames(project, name, rec, op):
    state = project.state
    layers = list(op.get("layers") or [])
    specs = [] if layers and not op.get("frames") else _frame_specs(op)
    geometry = {k: op[k] for k in ("x", "y", "width", "height") if k in op}
    if geometry and len(layers) == 1 and not specs:
        specs.append({"layer": layers.pop(), **geometry})  # size a single linked layer as it joins the chain
    specs += [{"layer": layer_ref} for layer_ref in layers]
    require(specs, "Give the frame to add: x, y, width and height, or frames, a shape, or layers", field="frames")
    position = len(rec["frames"])
    if "after" in op:
        position = _position(state, rec, op["after"], True, "after")
    elif "before" in op:
        position = _position(state, rec, op["before"], False, "before")
    for spec in specs:
        rec["frames"].insert(position, _make_frames(project, name, rec, spec))
        position += 1
    _check_limits(project, rec)


def _link(project, name, rec, op):
    require(op.get("layers"), "Pass layers: the text layers to link into the chain", field="layers")
    _add_frames(project, name, rec, {"layers": op["layers"], **{k: op[k] for k in ("after", "before", "x", "y", "width", "height") if k in op}})


def _unlink(project, name, rec, op):
    """Take frames out of the chain. The layers stay, holding the text they have now; ``delete_frames`` removes them."""
    from .operations import execute as apply

    state = project.state
    refs = list(op.get("layers") or [])
    if "frame" in op:
        refs.append(op["frame"])
    require(refs, "Say which frame to unlink: frame (a number, or a layer) or layers", field="frame")
    released = []
    for ref in refs:
        whole = isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit())
        index = _frame_index(state, rec, ref)
        frame = rec["frames"][index]
        if whole:
            released += frame["layers"]
            rec["frames"].pop(index)
        else:
            ident = find_layer(state, ref)[0]["id"]
            frame["layers"].remove(ident)
            released.append(ident)
            if not frame["layers"]:
                rec["frames"].pop(index)
    for ident in released:
        layer, page = locate(state, ident)
        rec.get("whole_words", {}).pop(ident, None)
        if layer is not None and op.get("delete_frames"):
            with on_page(project, page):
                apply(project, {"type": "remove", "target": ident})


def _style(project, rec, op):
    """Style words or paragraphs of the story with the ``text-style`` fields."""
    from .richtext import execute as rich_execute

    style = rec["style"]
    state = project.state
    temporary = new_layer("~flow-source", "text", 10, 10, text=rec["text"], font=style["font"], size=style["size"],
                          color=style["color"], align="left", spacing=4, auto_size=False)
    if rec.get("rich"):
        temporary["rich"] = deepcopy(rec["rich"])
    state["layers"].append(temporary)
    try:
        formats = dict(op.get("format") or {})
        unknown = sorted(set(formats) - set(FORMAT_KEYS))
        require(not unknown, f"Unknown format field(s) {', '.join(unknown)}; use {', '.join(FORMAT_KEYS)}", field="format")
        require(formats or op.get("clear"), "Nothing to style: pass format {bold: true, color: …} (and match, start/end or paragraphs)",
                field="format")
        if "align" in formats:
            formats["paragraph_align"] = formats.pop("align")
        request = {k: op[k] for k in ("match", "occurrence", "start", "end", "paragraphs", "clear") if k in op}
        rich_execute(project, {**formats, **request, "type": "text-style", "target": temporary["id"]})
        rec["rich"] = deepcopy(temporary["rich"])
        rec["text"] = temporary["text"]
    finally:
        state["layers"] = [x for x in state["layers"] if x["id"] != temporary["id"]]


def _delete(project, name, op):
    from .operations import execute as apply

    state = project.state
    rec = state["flows"].pop(name)
    if op.get("delete_frames"):
        for layer, page in _slots(state, rec):
            with on_page(project, page):
                apply(project, {"type": "remove", "target": layer["id"]})


def report(project, operations, reflowed=()):
    """Per-flow summary for operation results: overflow, remaining characters and each frame's share."""
    state = project.state
    names = []
    for op in operations:
        if op["type"] == "text-flow" and op["name"] not in names:
            names.append(op["name"])
    names += [n for n in reflowed if n not in names]
    result = {}
    for name in names:
        rec = state.get("flows", {}).get(name)
        if rec is None:
            result[name] = {"deleted": True}
            continue
        frames = []
        for (layer, page), (a, b) in zip(_slots(state, rec), rec.get("ranges", [])):
            frames.append({"layer": layer["name"], "chars": b - a, **({"page": _page_name(state, page)} if page else {})})
        info = {"frames": frames, **rec["overflow"], "rich": bool(rec.get("rich"))}
        info["empty_frames"] = [f["layer"] for f in frames if not f["chars"]]
        result[name] = info
    return result


def warnings(project, summary):
    """Plain-language warnings for an operation result."""
    messages = []
    for name, info in summary.items():
        if info.get("overflow"):
            messages.append(f"Text flow {name!r} overflows its last frame: {info['remaining_chars']} characters "
                            f"({info['remaining_words']} words) do not fit. Add a frame (text-flow add-frame), enlarge the frames, "
                            "or shorten the text.")
    return messages


def validate(state):
    flows = state.get("flows")
    if flows is None:
        return
    require(isinstance(flows, dict) and len(flows) <= 256, "Invalid text flow registry", "invalid_project")
    for name, rec in flows.items():
        require(isinstance(name, str) and isinstance(rec, dict), "Invalid text flow", "invalid_project")
        require(isinstance(rec.get("text"), str) and len(rec["text"]) <= MAX_TEXT, "Invalid text flow text", "invalid_project")
        require(isinstance(rec.get("style"), dict), "Invalid text flow style", "invalid_project")
        frames = rec.get("frames")
        require(isinstance(frames, list) and sum(len(f.get("layers", [])) for f in frames if isinstance(f, dict)) <= MAX_FRAMES
                and all(isinstance(f, dict) and isinstance(f.get("layers"), list) and all(isinstance(i, str) for i in f["layers"])
                        for f in frames), "Invalid text flow frames", "invalid_project")
        if rec.get("rich") is not None:
            from .richtext import validate_rich

            validate_rich(rec["rich"], state, rec["text"])
        for key in ("orphans", "widows"):
            require(isinstance(rec.get(key, 1), int) and 0 <= rec.get(key, 1) <= 20, f"Invalid {key}", "invalid_project")


def check_flows(project, resolved, issue):
    """Overflow, empty and edited frames, frames too small for a line (called by ``check_design``)."""
    state = project.state
    for name, rec in (state.get("flows") or {}).items():
        here = [resolved[i] for frame in rec["frames"] for i in frame["layers"] if i in resolved]
        if not here:
            continue
        overflow = rec.get("overflow", {})
        ranges = dict(zip(rec.get("frames_text", []), rec.get("ranges", [])))
        story = _story(rec)
        if overflow.get("overflow"):
            issue("flow", "error", f"Text flow {name!r} overflows: {overflow['remaining_chars']} characters "
                  f"({overflow['remaining_words']} words) do not fit its {sum(len(f['layers']) for f in rec['frames'])} frames; "
                  "add a frame with text-flow add-frame, enlarge a frame, or shorten the text", [here[-1]],
                  remaining_chars=overflow["remaining_chars"])
        for layer in here:
            span = ranges.get(layer["id"])
            if span is None:
                continue
            expected = story.text[span[0]:span[1]]
            if "${" not in expected and layer.get("text", "") != expected:
                issue("flow", "warning", f"{layer['name']!r} was edited directly; the next re-flow of {name!r} will overwrite it "
                      "(edit the story with text-flow set or style)", [layer])
            elif not expected and overflow.get("overflow"):
                issue("flow", "error", f"Frame {layer['name']!r} of {name!r} is too small to hold a line of text", [layer])
            elif not expected:
                issue("flow", "warning", f"Frame {layer['name']!r} of {name!r} is empty: the story ended before it", [layer])


def compile_command(cmd, args):
    if cmd != "text-flow":
        return None
    import json as _json

    from .commands import Parser

    p = Parser(prog="vixl text-flow")
    p.add_argument("action", choices=list(ACTIONS))
    p.add_argument("name")
    p.add_argument("--text")
    p.add_argument("--markdown")
    p.add_argument("--target")
    p.add_argument("--frames", type=_json.loads, help='JSON frames: [{"x": 60, "y": 80, "width": 480, "height": 600, "columns": 2}]')
    p.add_argument("--frame", type=lambda v: int(v) if v.isdigit() else v)
    p.add_argument("--layers", nargs="+")
    p.add_argument("--after", type=lambda v: int(v) if v.isdigit() else v)
    p.add_argument("--before", type=lambda v: int(v) if v.isdigit() else v)
    p.add_argument("--page")
    p.add_argument("--shape")
    p.add_argument("--mode", choices=list(SHAPE_MODES))
    for key in ("font", "color", "stroke-color", "match"):
        p.add_argument("--" + key)
    p.add_argument("--align", choices=list(ALIGNS))
    for key in ("x", "y", "width", "height", "gutter", "size", "spacing", "line-height", "paragraph-spacing", "inset", "stroke-width"):
        p.add_argument("--" + key, type=float)
    for key in ("columns", "orphans", "widows"):
        p.add_argument("--" + key, type=int)
    p.add_argument("--format", type=_json.loads, help='JSON styles for action style, e.g. {"bold": true, "color": "#c00"}')
    for flag in ("keep-together", "keep-with-next", "delete-frames", "clear"):
        p.add_argument("--" + flag, action="store_true", default=None)
    data = {k: v for k, v in vars(p.parse_args(args)).items() if v is not None}
    for key in ("text", "markdown"):
        if key in data:
            data[key] = data[key].replace("\\n", "\n")
    for key in ("x", "y", "width", "height"):
        if key in data and float(data[key]).is_integer() and key in ("width", "height"):
            data[key] = int(data[key])
    return {"type": "text-flow", **data}
