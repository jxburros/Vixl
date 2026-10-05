"""Render post.html to post.png (1080x1350) with headless Chromium and check text margins."""
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
MARGIN = 60

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=1)
    page.goto((HERE / "post.html").as_uri())
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(300)
    fonts = page.evaluate("[...document.fonts].map(f => f.family + ' ' + f.weight + ' ' + f.status)")
    print("fonts:", fonts)
    # Tight boxes of the actual glyph runs (Range rects), not the padded block boxes.
    boxes = page.evaluate("""
      () => [...document.querySelectorAll('.kicker, .headline span, .when, .where, .pill, .url')].map(el => {
        const r = document.createRange(); r.selectNodeContents(el);
        const b = el.classList.contains('pill') ? el.getBoundingClientRect() : r.getBoundingClientRect();
        return {text: el.textContent, l: b.left, t: b.top, r: b.right, b: b.bottom};
      })
    """)
    ok = True
    for b in boxes:
        m = min(b["l"], b["t"], 1080 - b["r"], 1350 - b["b"])
        flag = "OK " if m >= MARGIN else "BAD"
        ok &= m >= MARGIN
        print(f"{flag} min-edge={m:6.1f}  [{b['l']:.0f},{b['t']:.0f},{b['r']:.0f},{b['b']:.0f}]  {b['text']}")
    page.screenshot(path=str(HERE / "post.png"), clip={"x": 0, "y": 0, "width": 1080, "height": 1350})
    browser.close()
    print("all text >= 60px from edges:", ok)
