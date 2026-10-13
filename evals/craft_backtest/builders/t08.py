"""T08 infographic (1200 × 1800): a year of coffee at Tidewick.

The run's first batch, ``ops/T08-build-ops.json`` (copied from ``runs/T08/claude-V``), with the later edits the
report lists applied on top: rounded cards 180 px tall, labels and notes at 27 px, the bar chart 720 px tall
with font_size 27 and bar_gap 0.18, the donut at font_size 27 and the footnote at y 1700. The body size is the
27 px of the labels. The charts are drawn by today's chart engine, which sets their titles at x 76 (the
round-1 PNG has them at x 88): the same second left margin, 16 px in instead of 28."""

from ..kit import Doc, ops_file


def build():
    d = Doc(1200, 1800, "#f7f1e5", body=27)
    ops = ops_file("T08-build-ops.json")
    for op in ops:
        op.pop("font", None)
        if op.get("name", "").startswith("card"):
            op.update(shape="rounded-rectangle", height=180)
        if op.get("name", "").endswith(("-label", "-note")):
            op["size"] = 27
        if op.get("name") == "monthly":
            op.update(height=720, font_size=27, bar_gap=0.18)
        if op.get("name") == "share":
            op.update(font_size=27, number_format="#,##0")
        if op.get("name") == "footnote":
            op["y"] = 1700
    d.op(*ops)
    return {"T08-infographic": d.build()}
