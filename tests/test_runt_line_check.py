"""check flags display text whose wrapped last line is one short word (#532)."""

from vixl import Project


def runts(project):
    return [i for i in project.check()["issues"] if i.get("code") == "runt"]


def headline(width, size=54, text=None, **extra):
    p = Project(1584, 396, "#0A090C")
    if text is None:
        p.apply({"type": "rich-text", "name": "head", "size": size, "color": "#F1EEE9", "x": 40, "y": 40,
                 "width": width, "line_height": 1.0,
                 "spans": [{"text": "Local models, "}, {"text": "safe to share.", "color": "#FF2D55"}], **extra})
    else:
        p.apply({"type": "text", "name": "head", "text": text, "size": size, "color": "#F1EEE9", "x": 40, "y": 40})
        p.apply({"type": "text-layout", "target": "head", "width": width})
    return p


def test_rich_headline_with_a_lone_last_word_is_flagged_for_review():
    [finding] = runts(headline(640))
    assert finding["check"] == "legibility" and finding["action"] == "review"
    assert finding["layers"] == ["head"] and finding["line"] == "share."
    assert "widen the box" in finding["message"]


def test_plain_headline_is_flagged_too():
    [finding] = runts(headline(640, text="Local models, safe to share."))
    assert finding["line"] == "share."


def test_balanced_or_unwrapped_text_is_not_flagged():
    assert not runts(headline(1400))  # one line
    assert not runts(headline(460, text="Local models,\nsafe to share."))  # explicit break
    assert not runts(headline(520, text="Local models are safe to share"))  # two long lines


def test_short_last_line_under_a_fifth_is_flagged_even_with_two_words():
    p = headline(900, text="A very long headline that runs to I a")
    [finding] = runts(p)
    assert finding["share"] < 0.2


def test_body_text_is_exempt():
    assert not runts(headline(250, size=16, text="Local models, safe to share."))
