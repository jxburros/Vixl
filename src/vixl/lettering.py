"""Layer-level tracking, text case and hanging punctuation.

``tracking`` (pixels between characters), ``text_transform`` (``uppercase``, ``lowercase``,
``capitalize``, ``small-caps``) and ``hanging_punctuation`` belong to the text layer, not to a span of
fixed text, so they apply to whatever the layer holds: text changed by keyframes, typewriter or
captions, and ``${variable}`` values.

All are applied to the drawn view of a layer, never to its stored text: ``apply`` runs on every
resolved copy (render, checks, inspect and every export), and ``view`` gives the same view of a stored
layer to the measurement paths that read stored layers (auto-size, text boxes, fit-text). Tracked text,
small caps and hanging punctuation are laid out by the rich-text engine, which is where letter
spacing, per-glyph sizes and text that reaches past its box live; text without a rich record (or whose
record no longer matches the text, as after a text keyframe) gets a one-span record whose line pitch
and box match the plain engine's. Small caps mark the drawn copy's spans ``small_caps``; the stored
text keeps its case.
"""

import re

from .errors import require
from .model import finite

TRANSFORMS = ("none", "uppercase", "lowercase", "capitalize", "small-caps")
FIELDS = ("tracking", "text_transform", "hanging_punctuation")
MAX_TRACKING = 1000
# A letter that starts a word: the previous character is not part of a word (apostrophes are, so
# "don't" stays "Don't").
_WORD = re.compile(r"[\w'’]")


def validate(layer):
    """Check the layer's tracking, text_transform and hanging_punctuation; all are optional."""
    if "tracking" in layer:
        finite(layer["tracking"], "tracking", -MAX_TRACKING, MAX_TRACKING)
    if "text_transform" in layer:
        require(layer["text_transform"] in TRANSFORMS,
                f"text_transform must be one of {', '.join(TRANSFORMS)}", field="text_transform",
                allowed=list(TRANSFORMS))
    if "hanging_punctuation" in layer:
        require(isinstance(layer["hanging_punctuation"], bool), "hanging_punctuation must be true or false",
                field="hanging_punctuation")


def store(layer, op):
    """Copy tracking, text_transform and hanging_punctuation from an operation to a text layer; 0, 'none' and
    false remove them."""
    for key, neutral in (("tracking", 0), ("text_transform", "none"), ("hanging_punctuation", False)):
        if key in op:
            if op[key] == neutral:
                layer.pop(key, None)
            else:
                layer[key] = op[key]
    validate(layer)


def _hangs(layer):
    """Whether hanging punctuation can move something in the layer's text (else its layout is unchanged). Text
    with ``${variables}`` still to fill might. A line with tab stops is set by its stops and does not hang."""
    if not layer.get("hanging_punctuation") or layer.get("tabs"):
        return False
    from .richtext import hangable

    text = layer.get("text", "")
    return "${" in text or hangable(text, layer.get("align", "left"))


def styled(layer):
    """Whether the layer has tracking, a text case or hanging punctuation to apply."""
    return bool(layer.get("tracking")) or layer.get("text_transform", "none") != "none" or _hangs(layer)


def cased_pieces(pieces, mode):
    """Apply a text case to consecutive strings (rich spans) as if they were one text, so a word
    split across spans is capitalised once."""
    if mode == "uppercase":
        return [piece.upper() for piece in pieces]
    if mode == "lowercase":
        return [piece.lower() for piece in pieces]
    if mode != "capitalize":
        return list(pieces)
    result, previous = [], ""
    for piece in pieces:
        out = []
        for char in piece:
            out.append(char.upper() if char.isalpha() and not _WORD.match(previous or " ") else char)
            previous = char
        result.append("".join(out))
    return result


def cased(text, mode):
    return cased_pieces([text], mode)[0]


def apply(layer):
    """Apply tracking, text case and hanging punctuation to a resolved text layer (one whose ``${variables}`` are
    filled), in place."""
    if layer.get("type") != "text" or not styled(layer):
        return layer
    from .richtext import active, paragraph_count, plain

    mode = layer.get("text_transform", "none")
    if (layer.get("tracking") or mode == "small-caps" or _hangs(layer)) and not active(layer):
        previous = layer.get("rich") or {}
        rich = {"spans": [{"text": layer["text"]}], "paragraphs": [{} for _ in range(paragraph_count(layer["text"]))]}
        if previous.get("line_basis") == "size":
            rich.update(line_height=previous.get("line_height", 1.2), line_basis="size")
        else:
            # The plain engine's pitch: the font's own line height plus the layer's spacing.
            rich["line_height"] = 1.0
        # And the plain engine's box (top at the ink), so adding tracking does not move the text.
        rich["ink_box"] = True
        layer["rich"] = rich
    if mode == "small-caps":
        for span in layer["rich"]["spans"]:
            span["small_caps"] = True
    elif mode != "none":
        if active(layer):
            spans = layer["rich"]["spans"]
            for span, text in zip(spans, cased_pieces([span["text"] for span in spans], mode)):
                span["text"] = text
            layer["text"] = plain(layer["rich"])
        else:
            layer["text"] = cased(layer["text"], mode)
    return layer


def view(project, layer, variables=None):
    """The layer as it is drawn, for code that measures stored layers: ``${variables}`` filled, then
    tracking, text case and hanging punctuation applied. Layers without any are returned unchanged."""
    if layer.get("type") != "text" or not styled(layer):
        return layer
    from copy import deepcopy

    from .variables import RESOLVED

    copy = {**layer}
    if copy.get("rich"):
        copy["rich"] = deepcopy(copy["rich"])
    if not copy.get(RESOLVED):
        from .render import document_variables, substitute
        from .richtext import fill_variables

        values = {**document_variables(project), **(variables or {})}
        copy["text"] = substitute(copy.get("text", ""), values)
        if copy.get("rich"):
            fill_variables(copy["rich"], values)
        copy[RESOLVED] = True
    return apply(copy)
