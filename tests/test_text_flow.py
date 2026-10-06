"""Text flow: stories threaded through linked frames, columns, pages, shapes, rich text and re-flow."""

import io
import re

import numpy as np
import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.richtext import plain
from vixl.text import font_data, lines

PARAGRAPH = ("Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. "
             "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.")
STORY = "\n".join(f"{i}. {PARAGRAPH}" for i in range(1, 9))
LONG = "\n".join(f"{i}. {PARAGRAPH}" for i in range(1, 13))
COLUMNS = {"x": 40, "y": 40, "width": 822, "height": 300, "columns": 3, "gutter": 24}


def flow(text=STORY, size=(900, 600), **options):
    p = Project(*size, "white")
    result = p.apply([{"type": "text-flow", "name": "story", "text": text, "size": 15, **({**COLUMNS, **options})}], detail="compact")
    return p, result


def record(p, name="story"):
    return p.state["flows"][name]


def frames(p, name="story"):
    return [p.layer(i) for frame in record(p, name)["frames"] for i in frame["layers"]]


def assert_covers(rec):
    """Ranges are in order, separated only by whitespace, and start at the beginning of the story."""
    text, ranges = rec["text"], rec["ranges"]
    assert ranges[0][0] == 0
    for (a, b), (c, d) in zip(ranges, ranges[1:]):
        assert a <= b <= c <= d
        assert not text[b:c].strip(), f"only whitespace may fall between frames, not {text[b:c]!r}"
    last = max(b for _, b in ranges)
    assert text[last:].strip() == "" or rec["overflow"]["overflow"]
    placed = " ".join(text[a:b] for a, b in ranges)
    assert placed.split() == text[:last].split()


def test_slices_cover_the_story_exactly_once():
    p, result = flow(height=520)
    rec = record(p)
    assert not rec["overflow"]["overflow"] and result["text_flow"]["story"]["overflow"] is False
    assert_covers(rec)
    assert " ".join(f["text"] for f in frames(p)).split() == STORY.split()
    assert [len(f["text"]) for f in frames(p)] == [b - a for a, b in rec["ranges"]]
    for layer in frames(p):
        assert layer["type"] == "text" and layer["text_layout"] == {"width": layer["width"], "height": layer["height"]}
        assert "rich" not in layer and not layer["auto_size"]


def test_each_frame_wraps_like_the_continuous_text_would():
    # Frames of equal width: the lines of the slices, in order, are the lines of the whole story.
    p, _ = flow(height=520)
    layer = frames(p)[0]
    width, size, spacing = layer["width"], layer["size"], layer["spacing"]
    whole = lines(font_data(p, {**layer, "text": STORY}), STORY, size, width)
    pieces = [line for f in frames(p) if f["text"] for line in lines(font_data(p, f), f["text"], size, width)]
    assert pieces == whole, "the slices break exactly where the continuous text breaks"
    # and every frame's text really fits its box, by the same measure the bounds check uses
    assert p.check(checks=["bounds"])["issues"] == []
    assert spacing == 4


def test_overflow_is_reported_in_results_checks_and_warnings():
    p, result = flow(text=STORY * 3)
    summary = result["text_flow"]["story"]
    assert summary["overflow"] is True and summary["remaining_chars"] > 500 and summary["remaining_words"] > 80
    assert [f["layer"] for f in summary["frames"]] == ["story-1", "story-2", "story-3"]
    assert any("overflows" in w and str(summary["remaining_chars"]) in w for w in result["warnings"])
    issue = next(i for i in p.check()["issues"] if i["check"] == "flow")
    assert issue["severity"] == "error" and issue["remaining_chars"] == summary["remaining_chars"] and issue["layers"] == ["story-3"]
    # the remaining characters are exactly what no frame holds
    rec = record(p)
    assert rec["overflow"]["remaining_chars"] == len(rec["text"][rec["ranges"][-1][1]:].strip())
    # adding a frame fixes it, on request
    result = p.apply([{"type": "text-flow", "name": "story", "action": "add-frame", "x": 40, "y": 350, "width": 820, "height": 40}],
                     detail="compact")
    assert result["text_flow"]["story"]["remaining_chars"] < summary["remaining_chars"]
    assert len(frames(p)) == 4


def test_short_stories_leave_trailing_frames_empty_with_a_warning():
    p, result = flow(text="One short paragraph.")
    assert result["text_flow"]["story"]["empty_frames"] == ["story-2", "story-3"]
    assert [f["text"] for f in frames(p)] == ["One short paragraph.", "", ""]
    messages = [i for i in p.check(checks=["flow"])["issues"]]
    assert [i["severity"] for i in messages] == ["warning", "warning"] and "empty" in messages[0]["message"]
    assert p.render().size == (900, 600)


def test_columns_and_gutter_inside_one_frame():
    p, _ = flow()
    boxes = [(f["x"], f["y"], f["width"], f["height"]) for f in frames(p)]
    assert [b[3] for b in boxes] == [300, 300, 300] and len({b[1] for b in boxes}) == 1
    assert boxes[0][0] == 40 and boxes[-1][0] + boxes[-1][2] == 862
    for a, b in zip(boxes, boxes[1:]):
        assert b[0] - (a[0] + a[2]) == 24
    assert sum(b[2] for b in boxes) + 2 * 24 == 822
    assert len(record(p)["frames"]) == 1 and len(record(p)["frames"][0]["layers"]) == 3
    # change the column count of that frame later: the chain keeps its place
    p.apply([{"type": "text-flow", "name": "story", "frame": 1, "columns": 2, "gutter": 40}])
    boxes = [(f["x"], f["width"]) for f in frames(p)]
    assert len(boxes) == 2 and boxes[1][0] - (boxes[0][0] + boxes[0][1]) == 40 and boxes[1][0] + boxes[1][1] == 862
    assert not any(layer["name"] == "story-3" for layer in p.state["layers"])
    assert_covers(record(p))


def test_existing_text_layers_can_be_adopted_and_linked():
    p = Project(900, 500, "white")
    p.apply([{"type": "text", "name": "intro", "text": STORY, "size": 16, "color": "#223344"},
             {"type": "text", "name": "side", "text": "placeholder", "size": 16, "x": 500, "y": 40}])
    p.apply([{"type": "text-flow", "name": "story", "target": "intro", "x": 40, "y": 40, "width": 400, "height": 400,
              "frames": [{"layer": "side", "width": 360, "height": 400}]}])
    assert [f["name"] for f in frames(p)] == ["intro", "side"]
    assert frames(p)[0]["color"] == "#223344" and frames(p)[0]["text_layout"]["width"] == 400
    assert frames(p)[1]["width"] == 360 and "placeholder" not in frames(p)[1]["text"]
    assert_covers(record(p))
    p.apply([{"type": "text", "name": "extra", "text": "x", "size": 16, "x": 40, "y": 450}])
    with pytest.raises(VixlError) as error:
        p.apply([{"type": "text-flow", "name": "story", "action": "link", "layers": ["extra"]}])
    assert "width and height" in str(error.value), "an auto-sized text layer needs a frame size to join a chain"
    p.apply([{"type": "text-flow", "name": "story", "action": "link", "layers": ["extra"], "width": 300, "height": 40}])
    assert [f["name"] for f in frames(p)][-1] == "extra" and p.layer("extra")["text_layout"] == {"width": 300, "height": 40}
    assert_covers(record(p))


def test_unlink_keeps_the_text_and_delete_can_remove_frames():
    p, _ = flow(height=520)
    before = [f["text"] for f in frames(p)]
    p.apply([{"type": "text-flow", "name": "story", "action": "unlink", "frame": "story-2"}])
    assert [f["name"] for f in frames(p)] == ["story-1", "story-3"]
    assert len(record(p)["frames"]) == 1, "a column leaves its frame; the others stay together"
    assert p.layer("story-2")["text"] == before[1], "the unlinked layer keeps the text it had"
    assert frames(p)[1]["text"] != before[2], "the rest of the chain re-flows around the gap"
    assert record(p)["overflow"]["overflow"]
    p.apply([{"type": "text-flow", "name": "story", "action": "link", "layers": ["story-2"], "before": "story-3"}])
    assert [f["name"] for f in frames(p)] == ["story-1", "story-2", "story-3"]
    assert [f["text"] for f in frames(p)] == before
    p.apply([{"type": "text-flow", "name": "story", "action": "delete"}])
    assert "flows" not in p.state and [f["text"] for f in [p.layer(n) for n in ("story-1", "story-2", "story-3")]] == before
    p.undo()
    assert "story" in p.state["flows"]
    p.apply([{"type": "text-flow", "name": "story", "action": "delete", "delete_frames": True}])
    assert p.state["layers"] == []


def test_shape_frames_follow_the_outline():
    p = Project(900, 700, "white")
    p.apply([{"type": "shape", "shape": "ellipse", "name": "disc", "x": 50, "y": 50, "width": 500, "height": 500, "fill": "#e8f0fe"},
             {"type": "shape", "shape": "star", "name": "star", "x": 600, "y": 50, "width": 260, "height": 260, "fill": "#fff3d1"}])
    p.apply([{"type": "text-flow", "name": "round", "text": STORY, "size": 15, "align": "center", "frames": [{"shape": "disc", "inset": 6}]},
             {"type": "text-flow", "name": "boxed", "text": STORY, "size": 13, "frames": [{"shape": "star", "mode": "inscribed"}]}])
    bands = frames(p, "round")
    assert len(bands) > 10
    widths = [b["width"] for b in bands]
    assert max(widths) > widths[0] * 1.3 and max(widths) > widths[-1] * 1.3, "lines are widest at the middle of a disc"
    disc = p.layer("disc")
    cx, cy, radius = disc["x"] + 250, disc["y"] + 250, 250
    for band in bands:
        for x, y in ((band["x"], band["y"]), (band["x"] + band["width"], band["y"] + band["height"])):
            assert (x - cx) ** 2 + (y - cy) ** 2 <= (radius + 2) ** 2, "every band lies inside the disc"
    box = frames(p, "boxed")[0]
    star = p.layer("star")
    assert star["x"] <= box["x"] and box["x"] + box["width"] <= star["x"] + star["width"]
    assert star["y"] <= box["y"] and box["y"] + box["height"] <= star["y"] + star["height"]
    assert all(f["text"] for f in bands[:5])
    with pytest.raises(VixlError):
        p.apply([{"type": "text-flow", "name": "tiny", "text": STORY, "size": 90, "frames": [{"shape": "star"}]}])


def test_editing_the_story_reflows_the_frames():
    p, _ = flow(height=520)
    ids = [f["id"] for f in frames(p)]
    p.apply([{"type": "text-flow", "name": "story", "text": "Short now."}])
    assert [f["text"] for f in frames(p)] == ["Short now.", "", ""]
    assert [f["id"] for f in frames(p)] == ids
    result = p.apply([{"type": "text-flow", "name": "story", "text": STORY * 2}], detail="compact")
    assert result["text_flow"]["story"]["overflow"] is True
    assert_covers(record(p))
    p.apply([{"type": "text-flow", "name": "story", "size": 11, "text": STORY}])
    assert not record(p)["overflow"]["overflow"] and all(f["size"] == 11 for f in frames(p))


def test_resizing_or_restyling_a_frame_reflows_the_chain_automatically():
    p, _ = flow(height=520)
    first = frames(p)[0]["text"]
    result = p.apply([{"type": "resize", "target": "story-1", "height": 200}], detail="compact")
    assert frames(p)[0]["text"] != first and len(frames(p)[0]["text"]) < len(first)
    assert "story" in result["text_flow"], "re-flows triggered by other operations are reported too"
    assert_covers(record(p))
    p.apply([{"type": "text-layout", "target": "story-1", "width": 300, "height": 200}])
    assert frames(p)[0]["text_layout"] == {"width": 300, "height": 200}
    assert_covers(record(p))
    before = [f["text"] for f in frames(p)]
    p.apply([{"type": "text-set", "target": "story-2", "size": 22}])
    assert [f["text"] for f in frames(p)] != before
    assert_covers(record(p))
    # moving a frame changes nothing, so nothing is re-flowed
    marker = record(p)["signature"]
    p.apply([{"type": "move", "target": "story-1", "x": 60}])
    assert record(p)["signature"] == marker


def test_removing_a_frame_layer_or_its_page_reflows_without_it():
    p, _ = flow(height=520)
    p.apply([{"type": "remove", "target": "story-2"}])
    assert [f["name"] for f in frames(p)] == ["story-1", "story-3"]
    assert record(p)["overflow"]["overflow"]
    assert_covers(record(p))


def test_reflow_action_and_directly_edited_frames():
    p, _ = flow(height=520)
    p.apply([{"type": "text-set", "target": "story-1", "text": "Edited by hand"}])
    assert frames(p)[0]["text"] != "Edited by hand", "the flow owns its frames' text"
    p.state["flows"]["story"]["signature"] = "stale"
    p.apply([{"type": "text-flow", "name": "story", "action": "reflow"}])
    assert record(p)["signature"] != "stale"
    assert_covers(record(p))
    layer = p.layer("story-1")
    layer["text"] = "Edited behind the engine's back"
    assert any("edited directly" in i["message"] for i in p.check(checks=["flow"])["issues"])


def paragraphs_at_frame_ends(p):
    """For every frame boundary inside a paragraph: (lines the paragraph has at the end of the frame, lines it has in the next)."""
    rec = record(p)
    out = []
    ids = rec["frames_text"]
    for index, ((a, b), (c, d)) in enumerate(zip(rec["ranges"], rec["ranges"][1:])):
        if b < len(rec["text"]) and c < d and "\n" not in rec["text"][b:c]:
            last, first = p.layer(ids[index]), p.layer(ids[index + 1])
            out.append((len(lines(font_data(p, last), last["text"].split("\n")[-1], last["size"], last["width"])),
                        len(lines(font_data(p, first), first["text"].split("\n")[0], first["size"], first["width"]))))
    return out


BODY = "\n".join(" ".join(f"word{i}x{j}" for j in range(16 + 2 * i)) for i in range(14))


def split_flow(height, **rules):
    p = Project(940, 300, "white")
    frame = {"y": 20, "width": 260, "height": height}
    p.apply([{"type": "text-flow", "name": "story", "text": BODY, "size": 14, "frames": [{**frame, "x": 20}, {**frame, "x": 320}, {**frame, "x": 620}],
              **rules}])
    return p


def test_orphan_and_widow_rules_change_where_paragraphs_split():
    height = next(h for h in range(100, 260, 7) if min((min(pair) for pair in paragraphs_at_frame_ends(split_flow(h))), default=9) == 1)
    plain_split = split_flow(height)
    assert min(min(pair) for pair in paragraphs_at_frame_ends(plain_split)) == 1, "without rules a single line is left alone"
    ruled = split_flow(height, orphans=2, widows=2)
    ends = paragraphs_at_frame_ends(ruled)
    assert ends and all(last >= 2 and first >= 2 for last, first in ends), ends
    assert_covers(record(ruled))
    assert [f["text"] for f in frames(ruled)] != [f["text"] for f in frames(plain_split)]


def test_keep_together_never_splits_a_paragraph_that_fits_a_frame():
    split_somewhere = [h for h in range(110, 260, 9) if paragraphs_at_frame_ends(split_flow(h))]
    assert split_somewhere, "the plain flow splits paragraphs at these heights"
    for height in split_somewhere:
        kept = split_flow(height, keep_together=True)
        for layer in frames(kept):
            assert not layer["text"].startswith(" ")
        # only a paragraph taller than a whole frame still has to be split
        capacity = int((height + 4) // (14 * 1.164 + 4))
        assert all(last + first > capacity for last, first in paragraphs_at_frame_ends(kept)), (height, paragraphs_at_frame_ends(kept))
        assert_covers(record(kept))


def test_a_heading_is_not_left_alone_at_the_bottom_of_a_frame():
    md = "# Title\n" + "\n".join(f"## Part {i}\n" + PARAGRAPH for i in range(1, 6))
    p = Project(700, 500, "white")
    p.apply([{"type": "text-flow", "name": "story", "markdown": md, "size": 16,
              "frames": [{"x": 20, "y": 20, "width": 320, "height": 330}, {"x": 360, "y": 20, "width": 320, "height": 330}]}])
    rec = record(p)
    for (a, b) in rec["ranges"][:-1]:
        last_paragraph = rec["text"][a:b].split("\n")[-1]
        assert not last_paragraph.startswith("Part") and last_paragraph != "Title", last_paragraph
    p.apply([{"type": "text-flow", "name": "story", "keep_with_next": False}])
    assert record(p)["keep_with_next"] is False


RICH = ("# Report\n" + "".join(
    f"Section {i} has **bold** words, *italic* words and a [red phrase]{{color=#cc0000}} that must survive the split. "
    "It keeps going so that the paragraph is split between frames at least once.\n"
    "- bullet one with a long enough text to wrap around the narrow column\n- bullet two\n"
    "1. numbered one with a long enough text to wrap around the narrow column\n2. numbered two\n3. numbered three\n" for i in range(1, 5)))


def char_styles(rich):
    return [(ch, tuple(sorted((k, v) for k, v in span.items() if k != "text"))) for span in rich["spans"] for ch in span["text"]]


def test_rich_text_spans_survive_splitting():
    p = Project(800, 500, "white")
    p.apply([{"type": "page", "action": "add", "name": "one"}])
    result = p.apply([{"type": "text-flow", "name": "story", "markdown": RICH, "size": 16,
                       "frames": [{"x": 20, "y": 20, "width": 340, "height": 420}, {"x": 400, "y": 20, "width": 340, "height": 420}]}],
                     detail="compact")
    assert result["text_flow"]["story"]["rich"] is True
    rec = record(p)
    assert_covers(rec)
    source = char_styles(rec["rich"])
    text = rec["text"]
    rebuilt = []
    for (a, b), layer in zip(rec["ranges"], frames(p)):
        assert layer["rich"] and plain(layer["rich"]) == layer["text"] == text[a:b]
        rebuilt.append(char_styles(layer["rich"]))
        assert len(layer["rich"]["paragraphs"]) == layer["text"].count("\n") + 1
        assert layer["rich"]["paragraphs"] is not rec["rich"]["paragraphs"]
    flat = [c for frame in rebuilt for c in frame]
    expected = [source[i] for (a, b) in rec["ranges"] for i in range(a, b)]
    assert flat == expected, "every character keeps its style in the frame it lands in"
    assert any(("color", "#cc0000") in styles for _, styles in flat) and any(("bold", True) in styles for _, styles in flat)
    # frames render rich text through the normal path
    assert (np.asarray(p.render().convert("L")) < 128).sum() > 2000
    # the continuation of a numbered or bulleted paragraph does not repeat its marker, numbers carry on
    second = frames(p)[1]["rich"]["paragraphs"]
    assert second[0].get("list", "none") in ("none", "bullet", "number")
    numbers = [item.get("start") for item in second if item.get("list") == "number"]
    assert all(isinstance(n, int) and n >= 1 for n in numbers)


def test_continued_list_item_keeps_its_indent_but_not_its_marker():
    items = "\n".join(f"- {PARAGRAPH}" for _ in range(3))
    for height in range(120, 330, 10):
        p = Project(700, 500, "white")
        p.apply([{"type": "text-flow", "name": "story", "markdown": items, "size": 16,
                  "frames": [{"x": 20, "y": 20, "width": 300, "height": height}, {"x": 340, "y": 20, "width": 300, "height": 330}]}])
        rec = record(p)
        (a, b), (c, d) = rec["ranges"][:2]
        if "\n" not in rec["text"][b:c] and rec["text"][b:c].strip() == "" and 0 < b < c < d:
            first = frames(p)[1]["rich"]["paragraphs"][0]
            assert "list" not in first and first["indent"] > 0 and first["space_before"] == 0
            assert frames(p)[0]["rich"]["paragraphs"][-1]["list"] == "bullet"
            return
    pytest.fail("no height splits a bullet between the frames")


def test_style_action_edits_the_story_not_the_frames():
    p, _ = flow(height=520)
    result = p.apply([{"type": "text-flow", "name": "story", "action": "style", "match": "consectetur", "occurrence": "all",
                       "format": {"bold": True, "color": "#cc0000"}}], detail="compact")
    assert result["text_flow"]["story"]["rich"] is True
    rec = record(p)
    assert sum(1 for span in rec["rich"]["spans"] if span.get("bold") and span["text"] == "consectetur") == 8
    assert any(layer.get("rich") for layer in frames(p))
    assert_covers(rec)
    with pytest.raises(VixlError) as error:
        p.apply([{"type": "text-flow", "name": "story", "action": "style", "match": "x", "format": {"glow": True}}])
    assert error.value.details["field"] == "format"
    p.apply([{"type": "text-flow", "name": "story", "text": STORY}])
    assert "rich" not in record(p) and all("rich" not in layer for layer in frames(p))


def test_justified_flows_use_rich_paragraphs():
    p, _ = flow(align="justify")
    assert all(item["align"] == "justify" for item in record(p)["rich"]["paragraphs"])
    assert_covers(record(p))


def test_a_flow_continues_onto_other_pages_and_every_export_agrees():
    pypdf = pytest.importorskip("pypdf")
    p = Project(700, 500, "white")
    p.apply([{"type": "page", "action": "add", "name": "one"}])
    p.apply([{"type": "text-flow", "name": "story", "text": LONG, "size": 14, "frames": [{"x": 30, "y": 30, "width": 640, "height": 440}]}])
    p.apply([{"type": "page", "action": "add", "name": "two"}])
    result = p.apply([{"type": "text-flow", "name": "story", "action": "add-frame", "x": 30, "y": 30, "width": 640, "height": 440, "page": "two"}],
                     detail="compact")
    summary = result["text_flow"]["story"]
    assert [f["page"] for f in summary["frames"]] == ["one", "two"] and not summary["overflow"]
    assert p.state["page"] == next(pg["id"] for pg in p.state["pages"] if pg["name"] == "two"), "the page that was active stays active"
    assert_covers(record(p))
    words = LONG.split()
    report = {}
    data = p.export(format="PDF", report=report)
    reader = pypdf.PdfReader(io.BytesIO(data))
    assert len(reader.pages) == 2 and report["raster_fallbacks"] == {}
    pdf_words = " ".join(page.extract_text() for page in reader.pages).split()
    assert pdf_words == words, "selectable PDF text is the story, in order, across the pages"
    # the PNG of each page shows its own frame, and re-flow after an edit changes both pages together
    first, second = (np.asarray(p.render(page=n).convert("L")) < 128 for n in (1, 2))
    assert first.sum() > 3000 and second.sum() > 3000
    p.apply([{"type": "page", "action": "select", "page": "one"}, {"type": "text-flow", "name": "story", "size": 20}])
    assert p.state["page"] != next(pg["id"] for pg in p.state["pages"] if pg["name"] == "two")
    assert record(p)["overflow"]["overflow"]
    assert_covers(record(p))
    pptx = pytest.importorskip("pptx")
    deck = pptx.Presentation(io.BytesIO(p.export(format="PPTX")))
    texts = [" ".join(sh.text_frame.text for sh in slide.shapes if sh.has_text_frame) for slide in deck.slides]
    assert len(texts) == 2 and all(texts)
    svg = p.export(format="SVG")
    assert svg.count(b"<path") > 100


def test_rich_pdf_text_matches_the_story_too():
    pypdf = pytest.importorskip("pypdf")
    p = Project(700, 500, "white")
    p.apply([{"type": "page", "action": "add", "name": "one"}])
    p.apply([{"type": "text-flow", "name": "story", "markdown": RICH, "size": 16, "frames": [{"x": 20, "y": 20, "width": 320, "height": 440},
                                                                                           {"x": 360, "y": 20, "width": 320, "height": 440}]}])
    pdf = pypdf.PdfReader(io.BytesIO(p.export(format="PDF"))).pages[0].extract_text()
    shown = re.sub(r"[•◦▪‣]|\d+\.\s", " ", pdf).split()
    story = record(p)["text"].split()
    covered = [w for w in story if w in shown]
    assert len(covered) >= len(story) - len(story) // 10, "the PDF carries the story's words"
    assert "Report" in pdf and "red" in pdf


def test_errors_and_schema():
    p = Project(600, 400, "white")
    for bad, needle in (
        ({"type": "text-flow", "name": "s", "x": 0, "y": 0, "width": 200, "height": 100}, "story as text"),
        ({"type": "text-flow", "name": "s", "text": "hi"}, "Give the frame"),
        ({"type": "text-flow", "name": "s", "text": "hi", "frames": [{"x": 0, "y": 0, "width": 40, "height": 100, "columns": 4}]}, "too narrow"),
        ({"type": "text-flow", "name": "s", "action": "reflow"}, "Unknown text flow"),
        ({"type": "text-flow", "name": "s", "text": "a", "markdown": "b", "x": 0, "y": 0, "width": 200, "height": 100}, "one of text"),
        ({"type": "text-flow", "name": "bad name", "text": "a", "x": 0, "y": 0, "width": 200, "height": 100}, "Flow names"),
    ):
        with pytest.raises(VixlError) as error:
            p.apply([bad])
        assert needle in str(error.value), (bad, str(error.value))
    assert p.state["layers"] == [] and "flows" not in p.state
    with pytest.raises(VixlError) as error:
        p.apply([{"type": "text-flow", "name": "s", "text": "hi", "x": 0, "y": 0, "width": 200, "height": 100, "colour": "red"}])
    assert "colour" in str(error.value) or "color" in str(error.value)
    p.apply([{"type": "text-flow", "name": "s", "text": "hi", "x": 0, "y": 0, "width": 200, "height": 100}])
    with pytest.raises(VixlError) as error:
        p.apply([{"type": "text-flow", "name": "ss", "action": "reflow"}])
    assert "did you mean 's'" in str(error.value)
    with pytest.raises(VixlError):
        p.apply([{"type": "text-flow", "name": "s", "action": "create", "text": "x", "x": 0, "y": 0, "width": 50, "height": 50}])


def test_cli_command_and_document_round_trip(tmp_path):
    from vixl.commands import compile_command

    op = compile_command('text-flow create story --text "One\\nTwo" --x 10 --y 20 --width 300 --height 200 --columns 2 --gutter 16 '
                         '--orphans 2 --keep-together --size 14')
    assert op == {"type": "text-flow", "action": "create", "name": "story", "text": "One\nTwo", "x": 10.0, "y": 20.0, "width": 300, "height": 200,
                  "columns": 2, "gutter": 16.0, "orphans": 2, "keep_together": True, "size": 14.0}
    p = Project(900, 400, "white")
    p.apply([compile_command('text-flow create story --text "' + STORY.replace("\n", "\\n") + '" --x 40 --y 40 --width 820 --height 300 --columns 3')])
    path = tmp_path / "flow.vixl"
    p.save(path)
    loaded = Project.load(path)
    assert record(loaded)["ranges"] == record(p)["ranges"]
    ids = [f["id"] for f in frames(loaded)]
    loaded.apply([{"type": "text-flow", "name": "story", "text": STORY[:200]}])
    assert [f["id"] for f in frames(loaded)] == ids and frames(loaded)[0]["text"] == STORY[:200]
    assert p.check(checks=["flow"])["checked"]["checks"] == ["flow"]


def test_flow_check_is_part_of_the_default_checks_and_history_works():
    p, _ = flow(text=STORY * 3)
    report = p.check()
    assert "flow" in report["checked"]["checks"] and any(i["check"] == "flow" for i in report["issues"])
    p.undo()
    assert "flows" not in p.state and p.state["layers"] == []
    from vixl.changes import summarize

    p.redo()
    assert summarize(p)["flows"] == ["story"]
