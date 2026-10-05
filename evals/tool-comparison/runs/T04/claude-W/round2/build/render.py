import os, io
from playwright.sync_api import sync_playwright
from PIL import Image
D = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); B = os.path.join(D, "build")
os.makedirs(os.path.join(B, "px"), exist_ok=True)
def shot(page, svgpath, size, out, transparent=True):
    svg = open(svgpath).read()
    page.set_viewport_size({"width": size, "height": size})
    page.set_content(f'<html><body style="margin:0;background:transparent"><img src="data:image/svg+xml;base64,{__import__("base64").b64encode(svg.encode()).decode()}" style="width:{size}px;height:{size}px;display:block"></body></html>')
    page.screenshot(path=out, omit_background=transparent)
with sync_playwright() as p:
    br = p.chromium.launch(); pg = br.new_page()
    J = lambda *a: os.path.join(*a)
    for s in (16, 32, 64):
        shot(pg, J(D, "mark.svg"), s, J(B, "px", f"mark-{s}.png"))
        shot(pg, J(D, "mark-mono.svg"), s, J(B, "px", f"mono-{s}.png"))
        shot(pg, J(B, "mark-reverse.svg"), s, J(B, "px", f"rev-{s}.png"))
        shot(pg, J(B, "mark-mono-reverse.svg"), s, J(B, "px", f"monorev-{s}.png"))
    for s in (16, 32, 48):
        shot(pg, J(B, "icon-tile.svg"), s, J(B, "px", f"fav-{s}.png"), transparent=False)
    shot(pg, J(B, "app-icon.svg"), 1024, J(B, "app-raw.png"), transparent=False)
    pg.set_viewport_size({"width": 1600, "height": 1200})
    pg.goto("file://" + J(B, "sheet.html")); pg.wait_for_timeout(300)
    pg.screenshot(path=J(D, "logo-sheet.png"))
    br.close()
Image.open(J(B, "app-raw.png")).convert("RGB").save(J(D, "app-icon-1024.png"))
imgs = [Image.open(J(B, "px", f"fav-{s}.png")).convert("RGBA") for s in (16, 32, 48)]
imgs[2].save(J(D, "favicon.ico"), format="ICO", sizes=[(16,16),(32,32),(48,48)], append_images=imgs[:2])
print("done")
