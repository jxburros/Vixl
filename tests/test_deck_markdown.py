"""Markdown → slide deck (#170): one call builds a checked deck; re-running rebuilds only what changed."""

import io

import pytest
from PIL import Image

from vixl import Project
from vixl.deck_markdown import classify, split
from vixl.errors import VixlError
from vixl.interfaces import Session
from vixl.workflows import dispatch

NOTES = """# Tide Pool Nights
A summer music series
Harbour Arts · 2026

## Why the harbour
- Free concerts **every Friday**
- Food trucks and *local* makers
<!-- Mention the ferry schedule. -->

## Line-up

```csv
Date,Act,Genre
June 6,The Low Tides,Folk
June 13,Saltwater Brass,Jazz
```

## Attendance
Attendance has grown every year.

```chart line
Year,Visitors
2023,1200
2024,1850
```

Notes: Growth is mostly from families.

## Setting
![The stage at dusk](photo.png)

## In their words
> It felt like the whole town came out to listen.
— Maya, volunteer

# Thank you
"""


@pytest.fixture
def workspace(tmp_path):
    Image.new("RGB", (800, 600), "#2a9d8f").save(tmp_path / "photo.png")
    (tmp_path / "talk.md").write_text(NOTES, encoding="utf-8")
    return tmp_path


def test_split_and_classify():
    slides = split(NOTES)
    assert [s["title"] for s in slides] == ["Tide Pool Nights", "Why the harbour", "Line-up", "Attendance", "Setting",
                                           "In their words", "Thank you"]
    kinds = [classify(s, i == 0) for i, s in enumerate(slides)]
    assert kinds == ["title", "content", "content", "content", "content", "quote", "section"]
    assert slides[1]["notes"] == "Mention the ferry schedule." and slides[3]["notes"] == "Growth is mostly from families."
    assert [b["kind"] for b in slides[2]["blocks"]] == ["csv"] and slides[3]["blocks"][0]["info"] == "line"
    assert slides[4]["blocks"] == [{"kind": "image", "alt": "The stage at dusk", "path": "photo.png"}]
    assert split("intro\n\n---\n\nnext")[1]["body"] == ["next"]


def test_markdown_becomes_a_checked_deck_in_one_call(workspace):
    session = Session(workspace=workspace)
    result = dispatch(session, "deck-from-markdown", {"markdown": "talk.md", "output": "talk.vixl",
                                                      "export": ["pptx", "pdf"]})
    assert result["slides"] == 7 and [p["layout"] for p in result["pages"]][0] == "title"
    # Without an installed font pairing the fallback font is the only thing left to fix.
    assert {issue["check"] for issue in result["check"]["issues"] if issue["action"] == "fix"} <= {"fonts"}
    deck = Project.load(workspace / "talk.vixl")
    pages = {page["name"]: page for page in deck.state["pages"]}
    assert list(pages) == [p["page"] for p in result["pages"]]
    assert pages["why-the-harbour"]["notes"] == "Mention the ferry schedule."
    assert all(page.get("master") == "deck" for page in pages.values())
    deck._workspace = workspace
    deck.apply({"type": "page", "action": "select", "page": "line-up"})
    assert deck.layer("visual-1")["table"]["rows"][1] == ["June 6", "The Low Tides", "Folk"]
    deck.apply({"type": "page", "action": "select", "page": "attendance"})
    assert deck.layer("visual-1")["chart"]["kind"] == "line"
    deck.apply({"type": "page", "action": "select", "page": "why-the-harbour"})
    body = deck.layer("body")
    assert body["rich"] and any(span.get("bold") for span in body["rich"]["spans"])
    pptx = pytest.importorskip("pptx")
    presentation = pptx.Presentation(io.BytesIO((workspace / "talk.pptx").read_bytes()))
    assert len(presentation.slides) == 7
    assert any(shape.has_table for shape in presentation.slides[2].shapes)
    assert (workspace / "talk.pdf").exists()


def test_rerun_rebuilds_only_changed_slides(workspace):
    session = Session(workspace=workspace)
    dispatch(session, "deck-from-markdown", {"markdown": "talk.md", "output": "talk.vixl", "check": False})
    deck = Project.load(workspace / "talk.vixl")
    deck.apply({"type": "page", "action": "add", "name": "appendix"})  # a page made by hand
    deck.apply({"type": "page", "action": "select", "page": "setting"})
    kept_id = deck.layer("title")["id"]
    deck.save(workspace / "talk.vixl", overwrite=True)
    edited = NOTES.replace("- Food trucks and *local* makers", "- Food trucks, *local* makers and a night market")
    edited = edited.replace("## In their words\n> It felt like the whole town came out to listen.\n— Maya, volunteer\n", "")
    (workspace / "talk.md").write_text(edited, encoding="utf-8")
    result = dispatch(session, "deck-from-markdown", {"markdown": "talk.md", "output": "talk.vixl", "check": False})
    assert result["rebuilt"] == ["why-the-harbour"] and result["removed"] == ["in-their-words"]
    deck = Project.load(workspace / "talk.vixl")
    names = [page["name"] for page in deck.state["pages"]]
    assert "appendix" in names and "in-their-words" not in names
    deck.apply({"type": "page", "action": "select", "page": "setting"})
    assert deck.layer("title")["id"] == kept_id
    deck.apply({"type": "page", "action": "select", "page": "why-the-harbour"})
    assert "night market" in deck.layer("body")["text"]


def test_refuses_to_replace_other_documents_and_bad_input(workspace):
    session = Session(workspace=workspace)
    Project(100, 100).save(workspace / "other.vixl")
    with pytest.raises(VixlError, match="not made from"):
        dispatch(session, "deck-from-markdown", {"markdown": "talk.md", "output": "other.vixl"})
    (workspace / "empty.md").write_text("\n\n", encoding="utf-8")
    with pytest.raises(VixlError, match="no slides"):
        dispatch(session, "deck-from-markdown", {"markdown": "empty.md", "output": "e.vixl"})
    with pytest.raises(VixlError, match="not found"):
        dispatch(session, "deck-from-markdown", {"markdown": "missing.md", "output": "e.vixl"})
