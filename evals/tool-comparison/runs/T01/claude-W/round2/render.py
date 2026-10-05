from pathlib import Path
from playwright.sync_api import sync_playwright
here = Path(__file__).parent.resolve()
svg = (here/"picture.svg").read_text()
html = f"<!doctype html><html><head><style>html,body{{margin:0;padding:0;background:#000}}svg{{display:block}}</style></head><body>{svg}</body></html>"
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width":2400,"height":1600}, device_scale_factor=1)
    pg.set_content(html)
    pg.screenshot(path=str(here/"_raw.png"), full_page=False)
    b.close()
