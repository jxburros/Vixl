"""Long words break in linear time and wrap exactly as before (#335)."""

from pathlib import Path

import pytest

from vixl import Project
from vixl import text as text_module
from vixl.text import clusters, lines, shape, words_of

FONT = (Path(__file__).resolve().parents[1] / "src" / "vixl" / "data" / "DejaVuSans.ttf").read_bytes()


def reference_lines(data, text, size, width):
    """The wrapping algorithm before #335: every candidate line is shaped again."""
    result = []
    for paragraph in text.expandtabs(4).split("\n"):
        line = ""
        for word in words_of(paragraph):
            proposed = line + word
            if shape(data, proposed, size)[1] <= width:
                line = proposed
                continue
            if word.isspace():
                line = proposed
                continue
            if line:
                result.append(line.rstrip(" "))
            line = ""
            for char in clusters(data, word):
                if line and shape(data, line + char, size)[1] > width:
                    result.append(line)
                    line = ""
                line += char
        result.append(line)
    return result


TEXTS = [
    "a" * 700,
    "x" * 3 + " " + "W" * 400 + " end",
    "AVAVAVAVTTyyffiffl" * 30,  # kerning pairs and ligatures inside one long word
    "Supercalifragilisticexpialidocious" * 12 + " and then some ordinary words",
    "naïve café résumé " + "é" * 150 + "é" * 120,  # precomposed and combining accents
    "abc" + "שלום" * 40 + "def" * 50,  # a word that mixes right-to-left text
    "12345" * 80 + "αβγδε" * 40,  # digits next to Greek
    "w" * 90 + "‍" + "w" * 90,
    "tab\tseparated" * 40,
    "short words only, nothing to break here at all",
]


@pytest.mark.parametrize("text", TEXTS)
@pytest.mark.parametrize("width", [1, 37, 120, 333])
def test_long_words_wrap_exactly_as_before(text, width):
    for size in (8, 17):
        assert lines(FONT, text, size, width) == reference_lines(FONT, text, size, width)


def test_long_words_wrap_exactly_as_before_with_fallback_fonts():
    data = (bytes(bytearray(FONT)), FONT)  # a two-font chain
    for text in TEXTS[:4]:
        assert lines(data, text, 11, 90) == reference_lines(data, text, 11, 90)


def test_a_long_word_is_measured_once_per_line_not_once_per_character(monkeypatch):
    calls = []
    original = text_module.shape
    monkeypatch.setattr(text_module, "shape", lambda *a: calls.append(len(a[1])) or original(*a))
    text_module.advance.cache_clear()
    text_module._prefix_widths.cache_clear()
    word = "m" * 6000
    wrapped = lines(FONT, word, 10, 200)
    assert "".join(wrapped) == word and len(wrapped) > 100
    # The old algorithm shaped about len(word) × line length / 2 characters (about 1.7 million here).
    assert sum(calls) < 20 * len(word)


def test_text_flow_of_one_long_word_matches_the_story():
    p = Project(900, 600, "white")
    word = "a" * 9000
    p.apply({"type": "text-flow", "name": "s", "text": word, "size": 8, "x": 0, "y": 0, "width": 900,
             "height": 600, "columns": 3}, detail="brief")
    frames = [layer for layer in p.state["layers"] if layer["type"] == "text"]
    assert "".join(layer["text"].replace("\n", "") for layer in frames) == word[:sum(
        len(layer["text"].replace("\n", "")) for layer in frames)]
    assert len(frames) == 3 and all(layer["text"] for layer in frames)


def test_ink_bounds_match_parsing_each_glyph_path():
    from fontTools.misc.transform import Transform
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.svgLib.path import parse_path

    from vixl.render import resolve_layout, resolved_layers
    from vixl.text import plan
    from vixl.text_metrics import _PLAIN

    p = Project(800, 400, "white")
    p.apply([{"type": "text", "name": "t", "text": "Ink AVAWAY fiffl\nsecond line", "size": 37, "color": "black",
              "x": 10.5, "y": 20}])
    layer = next(item for item in resolved_layers(p) if item["name"] == "t")
    boxes = []
    for path, matrix in plan(p, layer).paths:
        pen = BoundsPen(None)
        parse_path(path, TransformPen(pen, Transform(*matrix)))
        if pen.bounds:
            boxes.append(pen.bounds)
    left, top = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x, y = resolve_layout(p)[layer["id"]][:2]
    expected = [x + left, y + top, max(b[2] for b in boxes) - left, max(b[3] for b in boxes) - top]
    _PLAIN.clear()
    assert p.inspect("t")["ink_bounds"] == expected


def reference_script_tags(chars):
    """Script resolution before #335 (it scanned to the right for every common character)."""
    from fontTools.unicodedata import script

    tags = [script(char) for char in chars]
    common = ("Zyyy", "Zinh", "Zzzz")
    for i, tag in enumerate(tags):
        if tag in common:
            left = next((tags[j] for j in range(i - 1, -1, -1) if tags[j] not in common), None)
            right = next((tags[j] for j in range(i + 1, len(tags)) if tags[j] not in common), None)
            tags[i] = left or right or "Latn"
    return tags


RUN_TEXTS = [*TEXTS, " ", "123 456", "(hello) [world]!", "é̂", "x‍y", "soft­hyphen",
             "﻿bom", "mixed English العربية ١٢٣ text", "Ελληνικά 2024 και English", "日本語のテキスト 123",
             "a‮evil‬ b", "⁧isolate⁩", "tab\tand paragraph", "😀 emoji 👍🏽 text",
             "Ж" * 30 + "1" * 30 + "q" * 30]


@pytest.mark.parametrize("text", RUN_TEXTS)
def test_runs_without_the_bidi_algorithm_match_it(text):
    from vixl.text import UnsupportedText, bidi_runs, runs, script_tags

    assert script_tags(list(text)) == reference_script_tags(list(text))
    try:
        expected = bidi_runs(text)
    except UnsupportedText:
        with pytest.raises(UnsupportedText):
            runs(text)
        return
    assert runs(text) == expected


def test_script_resolution_is_linear_in_a_run_of_digits():
    import time

    from vixl.text import script_tags

    start = time.perf_counter()
    assert set(script_tags(list("7" * 100000))) == {"Latn"}
    assert time.perf_counter() - start < 10  # The old resolution scanned the rest of the run for each digit.
