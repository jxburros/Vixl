"""Chromium through Playwright: render an HTML snippet at an exact pixel size and read back what the
page measured (character positions, line boxes).

Playwright is an eval dependency only (``pip install playwright``); the browser itself is found by
Playwright, else at ``VIXL_PARITY_CHROMIUM`` or ``/opt/pw-browsers/chromium``."""

import base64
import io
import json
import os
from pathlib import Path

from PIL import Image

FALLBACK = "/opt/pw-browsers/chromium"

# Runs after the web fonts load. Elements with data-baseline get their first baseline moved to that
# y; then elements with data-transform get that transform (after the baselines are measured upright);
# elements with data-measure report each character's box (layout positions, before raster).
SCRIPT = """
<script>
document.fonts.ready.then(() => {
  const out = {};
  for (const el of document.querySelectorAll('[data-baseline]')) {
    const probe = document.createElement('span');
    probe.style.cssText = 'display:inline-block;width:0;height:0;vertical-align:baseline';
    el.insertBefore(probe, el.firstChild);
    const offset = probe.getBoundingClientRect().top - el.getBoundingClientRect().top;
    probe.remove();
    el.style.top = (parseFloat(el.dataset.baseline) - offset) + 'px';
  }
  for (const el of document.querySelectorAll('[data-transform]')) el.style.transform = el.dataset.transform;
  for (const el of document.querySelectorAll('[data-measure]')) {
    const chars = [];
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let node, index = 0;
    while ((node = walker.nextNode())) {
      for (let i = 0; i < node.length; i++) {
        const range = document.createRange();
        range.setStart(node, i); range.setEnd(node, i + 1);
        const r = range.getBoundingClientRect();
        chars.push({i: index++, c: node.data[i], x: r.left, y: r.top, w: r.width, h: r.height});
      }
    }
    out[el.dataset.measure] = chars;
  }
  window.__parity = out;
  requestAnimationFrame(() => requestAnimationFrame(() => { window.__ready = true; }));
});
</script>
"""


def font_face(path, family="Parity"):
    data = base64.b64encode(Path(path).read_bytes()).decode()
    return f"@font-face{{font-family:{family};src:url(data:font/ttf;base64,{data})}}"


def page(body, width, height, background, css="", fonts=()):
    faces = "".join(font_face(path, family) for family, path in fonts)
    return (
        "<!doctype html><html><head><meta charset='utf-8'><style>"
        f"{faces}html,body{{margin:0;padding:0;width:{width}px;height:{height}px;overflow:hidden;"
        f"background:{background}}}.a{{position:absolute;margin:0;padding:0}}"
        f".t{{position:absolute;white-space:pre;margin:0;padding:0;font-kerning:normal}}{css}"
        f"</style></head><body>{body}{SCRIPT}</body></html>"
    )


class Chromium:
    """A headless Chromium session. ``hinting`` is Chromium's --font-render-hinting (none keeps glyph
    outlines unhinted, the closest to how Vixl draws text)."""

    def __init__(self, hinting="none"):
        self.hinting = hinting
        self._playwright = self.browser = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        args = [f"--font-render-hinting={self.hinting}", "--force-color-profile=srgb", "--hide-scrollbars"]
        try:
            self.browser = self._playwright.chromium.launch(args=args)
        except Exception:
            executable = os.environ.get("VIXL_PARITY_CHROMIUM", FALLBACK)
            self.browser = self._playwright.chromium.launch(args=args, executable_path=executable)
        return self

    def __exit__(self, *exc):
        if self.browser:
            self.browser.close()
        if self._playwright:
            self._playwright.stop()

    @property
    def version(self):
        return self.browser.version

    def render(self, html, width, height):
        """``(image, measurements)`` for a full page of ``width`` x ``height`` CSS pixels at 1x."""
        context = self.browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=1)
        try:
            tab = context.new_page()
            tab.set_content(html)
            tab.wait_for_function("window.__ready === true", timeout=30000)
            measured = tab.evaluate("JSON.stringify(window.__parity || {})")
            png = tab.screenshot(clip={"x": 0, "y": 0, "width": width, "height": height}, animations="disabled")
        finally:
            context.close()
        return Image.open(io.BytesIO(png)).convert("RGB"), json.loads(measured)
