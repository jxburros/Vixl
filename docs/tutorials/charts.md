# Build an editable chart

[Documentation home](../README.md) · [Forms and decks](forms-and-decks.md)

![Vixl bar chart of illustrative completed-task counts: Draft 24, Review 38, Refine 52, Deliver 68](../assets/generated/chart.png)

Vixl can build charts from text and shapes. This example is a horizontal bar chart with
ordinary editable layers; it does not require a chart-specific operation or an AI provider.
The numbers are illustrative, not Vixl performance measurements.

## Map data to geometry

| Category | Tasks | Bar width at 9 px/task |
| --- | --- | --- |
| Draft | 24 | 216 px |
| Review | 38 | 342 px |
| Refine | 52 | 468 px |
| Deliver | 68 | 612 px |

All bars begin at x=210; their widths encode values from a zero baseline. The 720 px
track represents 80 tasks. Categories and numeric labels add explicit meaning so the
viewer need not judge color alone. Change the scale if the largest value exceeds 80.

```bash
vixl new 1060x595 --background '#f5f3ec' -o chart.vixl
vixl -p chart.vixl apply docs/assets/generated/chart.json
vixl -p chart.vixl check --checks bounds contrast
vixl -p chart.vixl export chart.png
vixl -p chart.vixl export chart.svg
```

The [recipe](../assets/generated/chart.json) has separate names for bars, tracks, categories
and values. An excerpt for Draft:

```json
{"type": "shape", "shape": "rounded-rectangle", "name": "bar-0",
 "x": 210, "y": 160, "width": 216, "height": 48, "fill": "#235cdb", "radius": 6}
```

## Generate from your own data

Run this Python example in a fresh directory. It makes the value-to-width mapping explicit
and avoids deriving geometry by eyeballing a screenshot.

```python
from vixl import Project

data = [("Draft", 24), ("Review", 38), ("Refine", 52), ("Deliver", 68)]
assert all(0 < value <= 80 for _, value in data)
p = Project(900, 450, background="#ffffff")
ops = []
for i, (label, value) in enumerate(data):
    y = 40 + i * 90
    ops.extend([
        {"type": "text", "name": f"label-{i}", "text": label,
         "x": 30, "y": y, "size": 24, "color": "#18283b"},
        {"type": "shape", "shape": "rectangle", "name": f"bar-{i}",
         "x": 180, "y": y, "width": value * 7, "height": 40, "fill": "#235cdb"},
        {"type": "text", "name": f"value-{i}", "text": str(value),
         "x": 770, "y": y, "size": 24, "color": "#18283b"},
    ])
p.apply(ops)
p.save("data-chart.vixl")
p.export("data-chart.svg", svg_policy="strict")
```

This compact example handles positive values within its stated range. Zero values need a
label without a zero-width shape; negative values need a baseline and signed mapping;
logarithmic axes need a different transformation. Add a source, units and date for real
data. Vixl does not choose statistical scales or validate your dataset automatically.

## Update and reuse

Changing a number requires changing both the bar width and its label. Batch the edits so
they cannot disagree. For example, replacing Draft's count with 30:

```json
{"operations": [
  {"type": "resize", "target": "bar-0", "width": 270, "height": 48},
  {"type": "text-set", "target": "value-0", "text": "30"}
]}
```

Use SVG for supported scalable geometry, PNG for consistent pixels, or reuse the same
operations on a slide page. The [generated deck](../assets/generated/slides.pptx) uses
these counts with actual editable PowerPoint shapes and text. See [export behavior](../exporting.md)
for appearance fallbacks and [color checks](../color-and-print.md) for accessible palettes.
