"""Render post.html -> post.png (1080x1350) and story.html -> story.png (1080x1920)
with headless Chromium, and check the text safe areas.
post: every text run >= 60 px from every edge.
story: every text run >= 60 px from the sides and outside the top 250 px and bottom 250 px."""
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
JOBS = [
    # (html, png, width, height, side margin, top margin, bottom margin)
    ("post.html", "post.png", 1080, 1350, 60, 60, 60),
    ("story.html", "story.png", 1080, 1920, 60, 250, 250),
]

with sync_playwright() as p:
    browser = p.chromium.launch()
    for html, png, W, H, side, top, bottom in JOBS:
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        page.goto((HERE / html).as_uri())
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(300)
        fonts = page.evaluate("[...document.fonts].map(f => f.family + ' ' + f.weight + ' ' + f.status)")
        print(f"== {html} -> {png}  fonts:", fonts)
        # Tight boxes of the actual glyph runs (Range rects), not the padded block boxes.
        boxes = page.evaluate("""
          () => [...document.querySelectorAll('.kicker, .headline span, .host, .when, .where, .pill, .url')].map(el => {
            const r = document.createRange(); r.selectNodeContents(el);
            const b = el.classList.contains('pill') ? el.getBoundingClientRect() : r.getBoundingClientRect();
            return {text: el.textContent, l: b.left, t: b.top, r: b.right, b: b.bottom};
          })
        """)
        ok = True
        for b in boxes:
            gaps = {"left": b["l"] - side, "right": W - b["r"] - side,
                    "top": b["t"] - top, "bottom": H - b["b"] - bottom}
            worst = min(gaps, key=gaps.get)
            good = gaps[worst] >= 0
            ok &= good
            print(f"{'OK ' if good else 'BAD'} slack={gaps[worst]:6.1f} ({worst})  "
                  f"[{b['l']:.0f},{b['t']:.0f},{b['r']:.0f},{b['b']:.0f}]  {b['text']}")
        page.screenshot(path=str(HERE / png), clip={"x": 0, "y": 0, "width": W, "height": H})
        page.close()
        print(f"{png}: all text inside safe area:", ok)
    browser.close()
