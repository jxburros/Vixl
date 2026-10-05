"""Build T07 name badges: CSV -> HTML (badge.css) -> Chromium (Playwright) -> PNG + PDF."""
import csv, json, html, pathlib
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
CSV = HERE / "badges.csv"  # round 2: fixture copy + row 11 (Iris Van der Berg)
EVENT = "Harbor Makers Summit 2026"
DATES = "November 20–21, 2026 · Port Ellery"
ROLE = {"speaker": ("#f2a541", "#14263b"), "attendee": ("#a8d5c8", "#14263b"),
        "staff": ("#14263b", "#ffffff"), "sponsor": ("#6b3f69", "#ffffff")}

rows = list(csv.DictReader(open(CSV, encoding="utf-8", newline="")))
assert len(rows) == 11

def badge_html(r):
    bg, ink = ROLE.get(r["role"].strip().lower(), ROLE["attendee"])
    e = lambda s: html.escape(s, quote=True)
    company = f'<div class="fit company">{e(r["company"])}</div>' if r["company"].strip() else ""
    return f'''<div class="badge" style="--role:{bg};--ink:{ink}">
  <div class="event"><div class="fit event-name">{e(EVENT)}</div><div class="fit event-date">{e(DATES)}</div></div>
  <div class="names"><div class="fit first">{e(r["first_name"])}</div><div class="fit last">{e(r["last_name"])}</div>{company}</div>
  <div class="bar"><div class="fit role">{e(r["role"])}</div></div>
</div>'''

# Shrink any line wider than its box (min 40% of design size), then report geometry.
FIT_JS = """() => {
  const out = [];
  document.querySelectorAll('.badge').forEach((b, i) => {
    b.querySelectorAll('.fit').forEach(el => {
      const box = el.parentElement.clientWidth - 8;
      let fs = parseFloat(getComputedStyle(el).fontSize); const min = fs * 0.4;
      while (el.scrollWidth > box && fs > min) { fs -= 1; el.style.fontSize = fs + 'px'; }
    });
    const B = b.getBoundingClientRect(), s = 1200 / B.width;
    const rect = el => { const r = el.getBoundingClientRect();
      return [(r.left-B.left)*s, (r.top-B.top)*s, (r.right-B.left)*s, (r.bottom-B.top)*s]; };
    const items = {};
    for (const c of ['event-name','event-date','first','last','company','bar','role']) {
      const el = b.querySelector('.' + c); if (el) items[c] = {r: rect(el), fs: parseFloat(el.style.fontSize || getComputedStyle(el).fontSize)};
    }
    const n = b.querySelector('.names'); items.names = {r: rect(n)};
    out.push(items);
  });
  return out;
}"""

def page(body, extra_css=""):
    return f'''<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="badge.css"><style>{extra_css}</style></head><body>{body}</body></html>'''

def check(geo):
    """No text outside the badge or overlapping another block."""
    probs = []
    for i, g in enumerate(geo, 1):
        for k, v in g.items():
            x0, y0, x1, y1 = v["r"]
            if k != "names" and (x0 < -0.5 or y0 < -0.5 or x1 > 1200.5 or y1 > 900.5):
                probs.append(f"{i}:{k} out of badge {v['r']}")
        order = [k for k in ["event-date", "first", "last", "company", "bar"] if k in g]
        for a, b in zip(order, order[1:]):
            if g[a]["r"][3] > g[b]["r"][1] + 0.5:
                probs.append(f"{i}:{a} overlaps {b}")
        for k in ["first", "last", "company"]:
            if k in g and g[k]["r"][2] > 1130.5: probs.append(f"{i}:{k} too wide")
    return probs

# Letter imposition: 2 x 3 badges of 4 x 3 in, butted, centered -> margins 0.25 in (x), 1 in (y).
PRINT_CSS = """
@page{size:8.5in 11in;margin:0}
html,body{width:8.5in}
.sheet{position:relative;width:8.5in;height:11in;page-break-after:always;overflow:hidden}
.sheet:last-child{page-break-after:auto}
.slot{position:absolute;width:4in;height:3in;overflow:hidden}
.slot .badge{transform:scale(0.32);transform-origin:0 0}  /* 1200 css px -> 384 css px = 4 in */
.cm{position:absolute;background:#000}
"""

def sheet(badges):
    X0, Y0, W, H = 0.25, 1.0, 4.0, 3.0
    parts, n = [], len(badges)
    for k, b in enumerate(badges):
        c, r = k % 2, k // 2
        parts.append(f'<div class="slot" style="left:{X0+c*W}in;top:{Y0+r*H}in">{b}</div>')
    rows = (n + 1) // 2
    cols = 2 if n > 1 else 1
    gap, L, t = 0.04, 0.18, 0.0035   # offset from trim, mark length, ~0.25pt hairline
    xs = [X0 + c * W for c in range(cols + 1)]
    ys = [Y0 + r * H for r in range(rows + 1)]
    for x in xs:   # vertical marks above and below the grid
        parts.append(f'<div class="cm" style="left:{x-t/2}in;top:{ys[0]-gap-L}in;width:{t}in;height:{L}in"></div>')
        parts.append(f'<div class="cm" style="left:{x-t/2}in;top:{ys[-1]+gap}in;width:{t}in;height:{L}in"></div>')
    for y in ys:   # horizontal marks left and right of the grid
        parts.append(f'<div class="cm" style="left:{xs[0]-gap-L}in;top:{y-t/2}in;width:{L}in;height:{t}in"></div>')
        parts.append(f'<div class="cm" style="left:{xs[-1]+gap}in;top:{y-t/2}in;width:{L}in;height:{t}in"></div>')
    return '<div class="sheet">' + "".join(parts) + "</div>"

def main():
    items = [badge_html(r) for r in rows]
    (HERE / "badges").mkdir(exist_ok=True)
    with sync_playwright() as p:
        br = p.chromium.launch()
        pg = br.new_page(viewport={"width": 1200, "height": 900})
        # PNGs
        src = HERE / "_badges.html"
        src.write_text(page("".join(items), "body{width:1200px}"), encoding="utf-8")
        pg.goto(src.as_uri()); pg.evaluate("document.fonts.ready")
        geo = pg.evaluate(FIT_JS)
        probs = check(geo)
        for i, el in enumerate(pg.query_selector_all(".badge"), 1):
            el.screenshot(path=str(HERE / "badges" / f"badge-{i:02d}.png"))
        json.dump(geo, open(HERE / "_png_geometry.json", "w"), indent=1)
        # PDF
        sheets = [sheet(items[i:i + 6]) for i in range(0, len(items), 6)]
        psrc = HERE / "_print.html"
        psrc.write_text(page("".join(sheets), PRINT_CSS), encoding="utf-8")
        pg.goto(psrc.as_uri()); pg.evaluate("document.fonts.ready")
        pgeo = pg.evaluate(FIT_JS)
        probs += ["pdf " + x for x in check(pgeo)]
        pg.pdf(path=str(HERE / "badges-print.pdf"), width="8.5in", height="11in",
               print_background=True, margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
        br.close()
    print("problems:", probs or "none")
    for i, g in enumerate(geo, 1):
        print(i, rows[i-1]["first_name"], {k: round(v["fs"]) for k, v in g.items() if "fs" in v})

if __name__ == "__main__":
    main()
