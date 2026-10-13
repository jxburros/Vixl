"""T03 print poster (tabloid with bleed, 3375 × 5175 at 300 dpi): Harbor Lights night market.

The scene is the run's own operation batches (``ops/T03-scene-ops.json`` and ``ops/T03-reflection-ops.json``,
copied from ``runs/T03/claude-V``): sky, quay skyline, lantern strings and water reflections. The text was
added in later batches that were not kept, so it is placed by hand at the ink positions measured in
``poster-preview.png`` (half scale, trimmed: canvas = 2 × preview + 37.5 px bleed) with the sizes the report
gives (title 390, date 140, subtitle 108, list 104, details 80, credit 66)."""

from ..kit import Doc, ops_file

CREAM, AMBER, MIST = "#fbf1df", "#f2c46b", "#d9d4cc"


def _y(preview):
    return round(2 * preview + 37.5)


def build():
    d = Doc(3375, 5175, "#0b1426", body=80)
    d.op(*ops_file("T03-scene-ops.json"), *ops_file("T03-reflection-ops.json"))
    trim = {"left": 37.5, "right": 3337.5}
    d.centered("kicker", "PORT ELLERY QUAY", _y(741), 80, AMBER, **trim)
    d.centered("title", "Harbor Lights", _y(821), 390, CREAM, **trim)
    d.centered("subtitle", "A winter night market on the water", _y(1076), 108, MIST, **trim)
    d.centered("date", "Saturday, December 5, 2026 · 4–10 pm", _y(1191), 140, AMBER, **trim)
    d.text("highlights", "• Lantern parade at 6 pm\n• Forty local makers\n• Hot cider & roasted chestnuts\n"
           "• Live brass band", 2 * 464 + 37.5, _y(1970), 104, CREAM, line_height=1.5)
    d.centered("details", "Free entry · All ages · portellery.example", _y(2341), 80, AMBER, **trim)
    d.centered("credit", "Presented by Tidewick Café", _y(2406), 66, MIST, **trim)
    return {"T03-poster": d.build()}
