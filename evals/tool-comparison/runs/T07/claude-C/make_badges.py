#!/usr/bin/env python3
"""Generate conference name badges (PNG) and a print PDF from badges.csv.
Usage: python3 make_badges.py [path/to/badges.csv]
"""
import csv, os, sys
from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "../../../fixtures/badges.csv")
OUT_PNG = os.path.join(HERE, "badges")
OUT_PDF = os.path.join(HERE, "badges-print.pdf")

EVENT = "Harbor Makers Summit 2026"
DATES = "November 20–21, 2026 · Port Ellery"
W, H, DPI = 1200, 900, 300
MARGIN = 72                      # 0.24 in side margin for text
BAR_H = 200
INK = (20, 38, 59)               # navy text on white
MUTED = (84, 98, 115)
ROLE_COLORS = {"speaker": "#f2a541", "attendee": "#a8d5c8",
               "staff": "#14263b", "sponsor": "#e2725b"}

LATIN_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
LATIN_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
CJK = "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf"   # fallback for glyphs DejaVu lacks
_cmaps = {}
def cmap(path):
    if path not in _cmaps:
        _cmaps[path] = set(TTFont(path, fontNumber=0).getBestCmap())
    return _cmaps[path]

def font_for(text, bold=True):
    base = LATIN_BOLD if bold else LATIN_REG
    if all(ord(c) in cmap(base) for c in text):
        return base
    if all(ord(c) in cmap(CJK) for c in text):
        return CJK
    raise SystemExit(f"No font covers all glyphs of {text!r}")

def hex2rgb(h):
    h = h.lstrip("#"); return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def lum(rgb):
    def ch(c):
        c /= 255; return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb); return 0.2126*r + 0.7152*g + 0.0722*b

def contrast(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True); return (la + 0.05) / (lb + 0.05)

def fit(draw, text, path, size, max_w, min_size=24):
    """Largest font <= size whose rendered width fits max_w."""
    while size >= min_size:
        f = ImageFont.truetype(path, size)
        l, t, r, b = draw.textbbox((0, 0), text, font=f)
        if r - l <= max_w:
            return f
        size -= 2
    raise SystemExit(f"Cannot fit {text!r}")

def draw_line(draw, y_top, text, font, fill):
    """Draw text centred horizontally with its ink top at y_top; return ink bottom."""
    l, t, r, b = draw.textbbox((0, 0), text, font=font)
    x = (W - (r - l)) / 2 - l
    draw.text((x, y_top - t), text, font=font, fill=fill)
    return y_top + (b - t)

def make_badge(row):
    first, last = row["first_name"].strip(), row["last_name"].strip()
    role, company = row["role"].strip(), row["company"].strip()
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    max_w = W - 2 * MARGIN

    # Header: event + dates, small
    f_ev = ImageFont.truetype(LATIN_BOLD, 40)
    f_dt = ImageFont.truetype(LATIN_REG, 30)
    y = draw_line(d, 52, EVENT, f_ev, INK)
    y = draw_line(d, y + 14, DATES, f_dt, MUTED)
    d.line([(MARGIN, y + 26), (W - MARGIN, y + 26)], fill=(210, 216, 222), width=3)
    header_bottom = y + 26

    # Name block, vertically centred between header rule and bar
    f_first = fit(d, first, font_for(first), 190, max_w)
    f_last = fit(d, last, font_for(last), 104, max_w)
    lines = [(first, f_first, INK, 0), (last, f_last, INK, 22)]
    if company:
        f_co = fit(d, company, font_for(company, bold=False), 54, max_w)
        lines.append((company, f_co, MUTED, 34))
    heights = []
    for text, f, _, gap in lines:
        l, t, r, b = d.textbbox((0, 0), text, font=f); heights.append(b - t + gap)
    # use a fixed nominal ascent box so first-name size changes don't jitter layout much
    total = sum(heights)
    area_top, area_bot = header_bottom + 20, H - BAR_H - 20
    assert total <= area_bot - area_top, (first, total)
    y = area_top + (area_bot - area_top - total) / 2
    for (text, f, col, gap) in lines:
        y = draw_line(d, y + gap, text, f, col)

    # Role bar
    bar = hex2rgb(ROLE_COLORS.get(role.lower(), ROLE_COLORS["attendee"]))
    txt = (255, 255, 255) if contrast(bar, (255, 255, 255)) > contrast(bar, INK) else INK
    d.rectangle([0, H - BAR_H, W, H], fill=bar)
    label = role.upper()
    f_role = fit(d, label, font_for(label), 104, max_w)
    l, t, r, b = d.textbbox((0, 0), label, font=f_role)
    draw_line(d, H - BAR_H + (BAR_H - (b - t)) / 2, label, f_role, txt)
    return img, contrast(bar, txt)

def make_pdf(paths):
    PW, PH = letter
    bw, bh = 4 * inch, 3 * inch
    cols, rows = 2, 3
    x0 = (PW - cols * bw) / 2
    y0 = (PH - rows * bh) / 2
    c = canvas.Canvas(OUT_PDF, pagesize=letter)
    c.setTitle(f"{EVENT} badges"); c.setAuthor("make_badges.py")
    for p in range(0, len(paths), cols * rows):
        chunk = paths[p:p + cols * rows]
        for i, path in enumerate(chunk):
            col, r = i % cols, i // cols
            x = x0 + col * bw
            y = PH - y0 - (r + 1) * bh
            c.drawImage(path, x, y, bw, bh)
        # crop marks at every cut line, in the margins outside the grid
        c.setLineWidth(0.5); c.setStrokeColorRGB(0, 0, 0)
        gap, ln = 3, 12
        xs = [x0 + k * bw for k in range(cols + 1)]
        ys = [y0 + k * bh for k in range(rows + 1)]
        top, bot, left, right = PH - y0, y0, x0, x0 + cols * bw
        for x in xs:
            c.line(x, top + gap, x, top + gap + ln)
            c.line(x, bot - gap, x, bot - gap - ln)
        for y in ys:
            c.line(left - gap, y, left - gap - ln, y)
            c.line(right + gap, y, right + gap + ln, y)
        c.showPage()
    c.save()

def main():
    os.makedirs(OUT_PNG, exist_ok=True)
    with open(CSV, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    paths = []
    for i, row in enumerate(rows, 1):
        img, cr = make_badge(row)
        path = os.path.join(OUT_PNG, f"badge-{i:02d}.png")
        img.save(path, dpi=(DPI, DPI))
        paths.append(path)
        print(f"{path}: {row['first_name']} {row['last_name']} ({row['role']}) bar contrast {cr:.2f}:1")
    make_pdf(paths)
    print(OUT_PDF)

if __name__ == "__main__":
    main()
