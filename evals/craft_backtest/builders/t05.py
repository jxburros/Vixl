"""T05 slide deck, slide 4 "What worked" (1920 × 1080).

The run's batches (``build-ops.json``, ``polish-ops.json``) restyle a deck made by ``deck-from-markdown`` and
need its masters, so they do not apply on their own. This slide is placed by hand from ``deck.pdf`` page 4
(960 × 540 pt, so canvas = 2 × pt) and the report (title 90 px at x 120, y 128 with a coral bar above it;
the footer of the ``deck`` master: amber dot, "Tidewick Café", a sea-foam rule and ``N / 6`` on the right).
Slide 4 stands for the content slides: the footer defect the judges named is the same on slides 2-5."""

from ..kit import Doc

NAVY, CREAM, AMBER, FOAM, CORAL = "#14263b", "#f7f1e5", "#f2a541", "#a8d5c8", "#e2725b"


def build():
    d = Doc(1920, 1080, CREAM, body=54)
    d.rect("title-bar", 120, 100, 80, 8, CORAL)
    d.text("title", "What worked", 120, 128, 90, NAVY)
    bullets = ("Thursday open mics doubled evening\nsales", "Cold brew on tap from April to\nSeptember",
               "A pre-order pickup shelf shortened\nmorning queues")
    for i, (y, line) in enumerate(zip((330, 516, 704), bullets)):
        d.text(f"bullet-{i + 1}", "• " + line.replace("\n", "\n   "), 160, y, 54, NAVY, line_height=1.3)
    d.rect("year-panel", 1440, 128, 360, 752, FOAM, radius=30)
    d.centered("year", "2025", 440, 125, NAVY, left=1440, right=1800)
    d.rect("footer-rule", 120, 922, 1680, 2, FOAM)
    d.ellipse("footer-dot", 120, 952, 12, 12, AMBER)
    d.text("footer-name", "Tidewick Café", 146, 940, 24, NAVY)
    d.text("page-number", "4 / 6", 1644, 940, 24, NAVY, align="right", width=120)
    return {"T05-slide-4": d.build()}
