"""Editing the text of a rich-text layer without flattening its formatting.

``text-set`` replaces a layer's plain text. A layer with a ``rich`` record keeps its paragraph
settings (lists, alignment, spacing) and character styles (bold, tracking, fonts, colours…) where
the new text still has the structure they belong to: lines are matched first, so bullets and
indents stay with their line, and inside a line words are matched, so unchanged words keep their
styles while new words take the style of the text they replace, or of the text before them, as
typing in an editor does. What cannot carry over is reported back to the caller.
"""

from copy import deepcopy
import difflib
import re

from .notices import warn
from .richtext import active, normalize_spans

WORDS = re.compile(r"\s+|\w+|[^\w\s]")
MAX_CELLS = 4_000_000  # old × new lines (or words) compared before the whole block is replaced instead
OVERRIDES = ("color", "size", "font")


def _describe(style):
    """``bold+tracking 6`` for a span style or ``bullet list+level 1`` for paragraph settings."""
    return "+".join(k if v is True else f"{v} list" if k == "list" else k if k == "font" else f"{k} {v}"
                    for k, v in sorted(style.items(), key=lambda item: item[0] != "list"))


def _signature(style):
    return frozenset((k, repr(v)) for k, v in style.items())


def _split(rich):
    """Old lines as ``[(char, style)]`` and the style of the newline that follows each line."""
    lines, breaks = [[]], []
    for span in rich["spans"]:
        style = {k: v for k, v in span.items() if k != "text"}
        for char in span["text"]:
            if char == "\n":
                breaks.append(style)
                lines.append([])
            else:
                lines[-1].append((char, style))
    return lines, breaks


def _pair_lines(old, new):
    """One ``(old line, template, paired)`` per new line, and the old lines that have no successor.
    A paired line keeps its own styles; a template only lends its paragraph settings and style."""
    if len(old) * len(new) > MAX_CELLS:
        codes = [("replace", 0, len(old), 0, len(new))]
    else:
        codes = difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes()
    plan, removed = [], []
    for tag, i1, i2, j1, j2 in codes:
        if tag == "equal":
            plan += [(i1 + k, i1 + k, True) for k in range(j2 - j1)]
        elif tag == "replace":
            for k in range(j2 - j1):
                plan.append((i1 + k, i1 + k, True) if i1 + k < i2 else (None, i2 - 1, False))
            removed += list(range(i1 + (j2 - j1), i2))
        elif tag == "insert":
            template = i1 - 1 if i1 else (0 if old else None)
            plan += [(None, template, False)] * (j2 - j1)
        else:
            removed += list(range(i1, i2))
    return plan, removed


def _carry_line(old_chars, new_line, lost):
    """Styles for ``new_line``'s characters from the old line's, matching words."""
    old_text = "".join(char for char, _ in old_chars)
    old_words, new_words = WORDS.findall(old_text), WORDS.findall(new_line)
    starts = [0]
    for word in old_words:
        starts.append(starts[-1] + len(word))
    if len(old_words) * len(new_words) > MAX_CELLS:
        codes = [("replace", 0, len(old_words), 0, len(new_words))]
    else:
        codes = difflib.SequenceMatcher(None, old_words, new_words, autojunk=False).get_opcodes()
    out = []
    for tag, i1, i2, j1, j2 in codes:
        fresh = "".join(new_words[j1:j2])
        if tag == "equal":
            out += old_chars[starts[i1]:starts[i2]]
            continue
        replaced = old_chars[starts[i1]:starts[i2]]
        if tag == "insert":
            at = starts[i1]
            style = old_chars[at - 1][1] if at else old_chars[at][1] if old_chars else {}
        else:
            style = replaced[0][1] if tag == "replace" else None
        out += [(char, style) for char in fresh]
        for char, own in replaced:  # old styles that the new words do not repeat
            if own and own != style:
                lost.append((own, char))
    return out


def _lost_styles(lost, kept):
    """``["bold+tracking 6 on 'SUMMER'"]``: dropped styles that no remaining text uses."""
    runs = []
    for style, char in lost:
        if _signature(style) in kept:
            continue
        if runs and runs[-1][0] == style:
            runs[-1][1] += char
        else:
            runs.append([style, char])
    seen, report = set(), []
    for style, text in runs:
        text = text.strip()
        if text and (key := (_signature(style), text)) not in seen:
            seen.add(key)
            report.append(f"{_describe(style)} on {text[:24]!r}")
    return report


def replace_text(layer, new):
    """Set a text layer's text to ``new``, keeping what formatting still applies. Returns the
    warnings about formatting that could not be kept."""
    if not active(layer):
        layer.pop("rich", None)
        layer["text"] = new
        return []
    rich = layer["rich"]
    old_lines, breaks = _split(rich)
    new_lines = new.split("\n")
    paragraphs = rich.get("paragraphs") or []
    plan, removed = _pair_lines(["".join(c for c, _ in line) for line in old_lines], new_lines)
    lost, spans, settings = [], [], []
    for j, (source, template, paired) in enumerate(plan):
        chars = _carry_line(old_lines[source], new_lines[j], lost) if paired else None
        if chars is None:
            seed = old_lines[template][0][1] if template is not None and old_lines[template] else {}
            chars = [(char, seed) for char in new_lines[j]]
        spans += [{"text": char, **style} for char, style in chars]
        if j < len(plan) - 1:
            if paired and source < len(breaks):
                spans.append({"text": "\n", **breaks[source]})
            else:
                spans.append({"text": "\n", **(chars[-1][1] if chars else {})})
        para = deepcopy(paragraphs[template]) if template is not None and template < len(paragraphs) else {}
        if not paired:
            para.pop("start", None)
        settings.append(para)
    fresh = {**rich, "spans": normalize_spans(spans), "paragraphs": settings}
    layer["rich"], layer["text"] = fresh, new
    kept = {_signature({k: v for k, v in span.items() if k != "text"}) for span in fresh["spans"]}
    dropped = _lost_styles(lost, kept)
    for index in removed:
        for style in [paragraphs[index]] if index < len(paragraphs) else []:
            if style and _signature(style) not in {_signature(p) for p in settings}:
                dropped.append(f"paragraph settings {_describe(style)} of removed line {index + 1}")
    return dropped


def override_warnings(layer, op):
    """Warnings for layer-level colour, size, font or alignment that rich text overrides: spans
    and paragraphs that set their own value keep it, so the change does not reach them."""
    rich = layer.get("rich")
    if not rich or not active(layer):
        return []
    messages = []
    for key in OVERRIDES:
        if key in op:
            count = sum(1 for span in rich["spans"] if key in span and span["text"].strip())
            if count:
                messages.append(f"{count} span(s) set their own {key} and keep it")
    if "align" in op:
        count = sum(1 for para in rich.get("paragraphs", []) if "align" in para)
        if count:
            messages.append(f"{count} paragraph(s) set their own align and keep it")
    return messages


def report(project, layer, dropped, overridden):
    """Queue the result warnings for a ``text-set`` on a rich layer."""
    name = layer["name"]
    if dropped:
        warn(project, f"text-set on {name!r} kept the formatting that still applies; dropped: {'; '.join(dropped)}. "
                      "Use rich-text to rebuild formatted content.")
    if overridden:
        warn(project, f"text-set on {name!r} changed the layer default, but {'; '.join(overridden)}. "
                      "Use text-style (without match/start/end) to restyle all of the text.")
