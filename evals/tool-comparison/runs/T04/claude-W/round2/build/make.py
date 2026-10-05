# -*- coding: utf-8 -*-
import os
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
OUT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAVY, AMBER, CREAM = "#14263b", "#f2a541", "#f7f1e5"

def text_path(fontfile, text, size, x, y, tracking=0.0):
    f = TTFont(fontfile); gs = f.getGlyphSet(); cmap = f.getBestCmap()
    upm = f['head'].unitsPerEm; s = size / upm
    pen = SVGPathPen(gs); cx = 0.0
    for ch in text:
        g = cmap[ord(ch)]
        tp = TransformPen(pen, (s, 0, 0, -s, x + cx, y))
        gs[g].draw(tp)
        cx += gs[g].width * s + tracking * size
    width = cx - tracking * size
    return pen.getCommands(), width

FLAME = "M38 1.5C33 9 45 15.5 45 27A13 13 0 0 1 19 27C19 15 31 11 38 1.5Z"
RAYS = "M5 25H11M53 25H59M9.5 11.5L14 15.5M54.5 11.5L50 15.5"
WAVES = ["M6 48q6.5-6 13 0t13 0t13 0t13 0", "M6 59q6.5-6 13 0t13 0t13 0t13 0"]

def mark(flame, wave, tx=0, ty=0, sc=1):
    w = "".join(f'<path d="{d}" fill="none" stroke="{wave}" stroke-width="6.5" stroke-linecap="round" stroke-linejoin="round"/>' for d in WAVES)
    r = f'<path d="{RAYS}" fill="none" stroke="{flame}" stroke-width="4.5" stroke-linecap="round"/>'
    return f'<g transform="translate({tx} {ty}) scale({sc})">{r}<path d="{FLAME}" fill="{flame}"/>{w}</g>'

SERIF = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

def svg(w, h, body, title, bg=None):
    b = f'<rect width="{w}" height="{h}" fill="{bg}"/>' if bg else ""
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}"><title>{title.replace("&", "&amp;")}</title>{b}{body}</svg>\n'

def horizontal(word, tag, flame, wave, bg=None):
    # mark 64 units scaled to 112 tall; wordmark cap ~ 66
    sc = 112/64
    wx = 24 + 64*sc + 26
    wp, ww = text_path(SERIF, "Tidewick & Co.", 84, wx, 82)
    tp, tw = text_path(SANS, "COFFEE · BAKERY · HARBOR", 19.5, wx + 3, 120, tracking=0.16)
    W = round(wx + max(ww, tw + 3) + 24); H = 160
    body = mark(flame, wave, 24, 24, sc) + f'<path d="{wp}" fill="{word}"/><path d="{tp}" fill="{tag}"/>'
    return svg(W, H, body, "Tidewick & Co. logo, horizontal", bg)

def stacked(word, tag, flame, wave, bg=None):
    wp0, ww = text_path(SERIF, "Tidewick & Co.", 84, 0, 0)
    tp0, tw = text_path(SANS, "COFFEE · BAKERY · HARBOR", 19.5, 0, 0, tracking=0.16)
    W = round(max(ww, tw) + 64); H = 330
    sc = 128/64
    body = mark(flame, wave, (W - 128)/2, 24, sc)
    wp, _ = text_path(SERIF, "Tidewick & Co.", 84, (W - ww)/2, 248)
    tp, _ = text_path(SANS, "COFFEE · BAKERY · HARBOR", 19.5, (W - tw)/2, 290, tracking=0.16)
    body += f'<path d="{wp}" fill="{word}"/><path d="{tp}" fill="{tag}"/>'
    return svg(W, H, body, "Tidewick & Co. logo, stacked", bg)

files = {
  "logo-horizontal.svg": horizontal(NAVY, NAVY, AMBER, NAVY),
  "logo-stacked.svg": stacked(NAVY, NAVY, AMBER, NAVY),
  "mark.svg": svg(64, 64, mark(AMBER, NAVY), "Tidewick & Co. mark"),
  "mark-mono.svg": svg(64, 64, mark(NAVY, NAVY), "Tidewick & Co. mark, navy"),
  # reversed variants for dark backgrounds (sheet use + bonus)
  "build/logo-horizontal-reverse.svg": horizontal(CREAM, CREAM, AMBER, CREAM),
  "build/logo-stacked-reverse.svg": stacked(CREAM, CREAM, AMBER, CREAM),
  "build/mark-reverse.svg": svg(64, 64, mark(AMBER, CREAM), "Tidewick & Co. mark, reversed"),
  "build/mark-mono-reverse.svg": svg(64, 64, mark(CREAM, CREAM), "Tidewick & Co. mark, cream"),
  # favicon / app icon art: mark on cream tile, slightly padded
  "build/icon-tile.svg": svg(64, 64, f'<rect width="64" height="64" fill="{CREAM}"/>' + mark(AMBER, NAVY, 4, 3.5, 56/64), "Tidewick & Co. icon"),
  "build/app-icon.svg": svg(1024, 1024, f'<rect width="1024" height="1024" fill="{NAVY}"/>' + mark(AMBER, CREAM, 512-320, 512-320, 640/64), "Tidewick & Co. app icon"),
}
for k, v in files.items():
    open(os.path.join(OUT, k), "w").write(v)
print("ok")
