"""Render infographic.html to PNG (1200x1800), SVG and PDF with headless Chromium (Playwright)."""
import json, pathlib, re, subprocess
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
FIX = HERE / "coffee-2025-corrected.csv"  # fixture with corrected Dec row
html = (HERE / "infographic.html").read_text()
embedded = re.search(r'<script id="csv" type="text/csv">\s*(.*?)\s*</script>', html, re.S).group(1)
assert embedded.strip() == FIX.read_text().strip(), "embedded CSV differs from corrected CSV"

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1200, "height": 1800}, device_scale_factor=1)
    pg.goto((HERE / "infographic.html").as_uri())
    pg.wait_for_timeout(300)
    pg.locator("#ig").screenshot(path=str(HERE / "infographic.png"))
    svg = pg.eval_on_selector("#ig", "e => new XMLSerializer().serializeToString(e)")
    (HERE / "infographic.svg").write_text('<?xml version="1.0" encoding="UTF-8"?>\n' + svg)
    pg.pdf(path=str(HERE / "infographic.pdf"), width="1200px", height="1800px",
           print_background=True, page_ranges="1")
    res = pg.evaluate("window.__results")
    # bar-scale check: every segment height must equal value/yMax*plotH
    rects = pg.eval_on_selector_all("rect[data-value]", "es => es.map(e => [+e.dataset.value, +e.getAttribute('height')])")
    b.close()

ratios = {round(h / v, 4) for v, h in rects}
print(json.dumps({k: res[k] for k in ("drinkTotals", "grand", "share", "ties")}, indent=1))
print("busiest", res["busiest"]["month"], res["busiest"]["total"], "| cold peak", res["coldPeak"]["month"], res["coldPeak"]["cold_brew"])
print("segments", len(rects), "px-per-cup ratios", ratios)
