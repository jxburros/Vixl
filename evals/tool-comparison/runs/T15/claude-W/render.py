#!/usr/bin/env python3
"""Render tile.png, preview-3x3.png and mug-wrap.png in headless Chromium."""
import os, pathlib
from playwright.sync_api import sync_playwright

D = pathlib.Path(__file__).resolve().parent
svg = (D / "tile.svg").read_text()
uri = "data:image/svg+xml;base64," + __import__("base64").b64encode(svg.encode()).decode()

def page_html(w, h, inner, extra_css=""):
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
html,body{{margin:0;padding:0;width:{w}px;height:{h}px;overflow:hidden;background:#f7f1e5}}
{extra_css}</style></head><body>{inner}</body></html>"""

tile_html = page_html(1024, 1024, svg)
grid_html = page_html(3072, 3072, '<div style="width:3072px;height:3072px;'
                      f'background:url({uri}) 0 0/1024px 1024px repeat"></div>')
# mug: pattern centred on the wrap so the label sits over a tile centre;
# background-position:center puts a tile centre at the wrap centre.
mug_css = """
.wrap{position:relative;width:2550px;height:1050px;background-image:url(%s);
 background-size:1024px 1024px;background-repeat:repeat;background-position:center center}
.label{position:absolute;left:975px;top:375px;width:600px;height:300px;box-sizing:border-box;
 background:#f7f1e5;border-radius:40px;border:6px solid #14263b;
display:flex;align-items:center;justify-content:center}
.label span{font-family:'P052','URW Palladio L','Palatino',serif;font-weight:700;font-size:118px;
 color:#14263b;letter-spacing:2px;line-height:1}
""" % uri
mug_html = page_html(2550, 1050, '<div class="wrap"><div class="label"><span>Tidewick</span></div></div>', mug_css)

with sync_playwright() as p:
    b = p.chromium.launch()
    for name, html, w, h in [("tile.png", tile_html, 1024, 1024),
                             ("preview-3x3.png", grid_html, 3072, 3072),
                             ("mug-wrap.png", mug_html, 2550, 1050)]:
        pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
        pg.set_content(html)
        pg.wait_for_timeout(300)
        pg.screenshot(path=str(D / name), full_page=False, omit_background=False)
        pg.close()
        print("wrote", name)
    b.close()
