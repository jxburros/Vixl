"""Build the autism & ADHD therapist presentation decks with the vixl CLI.

Usage: python build.py [--vixl PATH] [--only SLUG]

Each deck is written as an editable .vixl master plus .pdf, .pptx, .html and a
contact-sheet .png into decks/<slug>/.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from content import DECKS

HERE = Path(__file__).resolve().parent
W, H, M = 1920, 1080, 120

HEAD = "fraunces-600"
BODY = "lexend-400"
BOLD = "lexend-600"
FONTS = [("Fraunces", 600), ("Lexend", 400), ("Lexend", 600)]

# One type scale for every deck: small print, body, lead, display, title, cover, statistic.
SMALL, BODY_SIZE, LEAD, DISPLAY, TITLE, COVER, STAT = 24, 36, 44, 56, 68, 104, 190
ICON_BUBBLE = {56: 100, 68: 120, 104: 200}
FOOT_Y = 1000


def est_lines(text, size, width, factor=0.53):
    """Rough line count for wrapped text; used only to stack blocks vertically."""
    words, lines, cur = text.replace("**", "").split(), 1, 0.0
    for w in words:
        wlen = (len(w) + 1) * size * factor
        if cur + wlen > width and cur > 0:
            lines, cur = lines + 1, wlen
        else:
            cur += wlen
    return lines


class Deck:
    def __init__(self, spec):
        self.spec = spec
        self.t = spec["theme"]
        self.ops = []
        self.n = 0
        self.emoji = set()

    def op(self, **kw):
        self.ops.append({k: v for k, v in kw.items() if v is not None})

    def uid(self, base):
        self.n += 1
        return f"{base}-{self.n}"

    def intent(self, page, names, role):
        self.op(type="layer-intent", page=page, targets=names, role=role)

    # ---- primitives -------------------------------------------------------
    def rect(self, page, name, x, y, w, h, fill, radius=0, stroke=None, opacity=None):
        o = dict(type="shape", page=page, name=name, x=x, y=y, width=w, height=h, fill=fill,
                 shape="rounded-rectangle" if radius else "rectangle", opacity=opacity)
        if radius:
            o["radius"] = radius
        if stroke:
            o["stroke"], o["stroke_width"] = stroke, 2
        self.op(**o)

    def circle(self, page, name, x, y, d, fill, opacity=None):
        self.op(type="shape", shape="ellipse", page=page, name=name, x=x, y=y, width=d, height=d,
                fill=fill, opacity=opacity)

    def icon(self, page, emoji, x, y, glyph, bg):
        """Emoji artwork (a rendered image of Vixl's bundled emoji) centred in a round bubble."""
        d = ICON_BUBBLE[glyph]
        self.circle(page, self.uid("icon-bg"), x, y, d, bg)
        self.emoji.add(emoji)
        box = round(d * 0.78)
        self.op(type="add", page=page, name=self.uid("icon"), path=icon_path(emoji),
                x=x + (d - box) // 2, y=y + (d - box) // 2, width=box, height=box,
                credit="VIXL Line emoji (adapted from OpenMoji)", license="CC BY-SA 4.0")

    def text(self, page, name, text, x, y, size, font=BODY, color=None, align=None):
        self.op(type="text", page=page, name=name, text=text, x=x, y=y, size=size, font=font,
                color=color or self.t["ink"], align=align)

    def rich(self, page, name, md, x, y, width, size, font=BODY, color=None, align=None, lh=1.35, para=None):
        self.op(type="rich-text", page=page, name=name, markdown=md, x=x, y=y, width=width, size=size,
                font=font, color=color or self.t["ink"], line_height=lh, align=align, paragraph_spacing=para,
                font_variants={"bold": BOLD if font == BODY else HEAD})

    def pair(self, page, head, body, x, y, width, head_size, head_color, body_color, align=None,
             head_name=None, body_name=None, gap=16, body_size=BODY_SIZE, lh=1.35):
        """Heading over body text, auto-laid out so a wrapped heading pushes the body down."""
        h, b = head_name or self.uid("head"), body_name or self.uid("body")
        self.rich(page, h, head, x, y, width, head_size, HEAD, head_color, align, lh=1.12)
        self.rich(page, b, body, x, y, width, body_size, BODY, body_color, align, lh=lh)
        self.op(type="stack", page=page, name=self.uid("block"), targets=[h, b], gap=gap,
                direction="vertical", align={"center": "center"}.get(align, "start"))

    def title(self, page, text, color=None, bar=None):
        self.rect(page, self.uid("title-bar"), M, 92, 72, 10, bar or self.t["accent"], radius=5)
        self.text(page, "title", text, M, 122, TITLE, HEAD, color or self.t["ink"])

    def footer(self, page, color):
        """Footer for pages that drop the master because they have a coloured background."""
        self.text(page, "footer", self.spec["short"], M, FOOT_Y, SMALL, BODY, color)
        self.text(page, "page-number", "${page} / ${pages}", W - M - 90, FOOT_Y, SMALL, BODY, color)

    # ---- master -----------------------------------------------------------
    def master(self):
        t = self.t
        self.op(type="master", action="add", name="std", background=t["bg"])
        self.circle(None, "corner-dot", W - 150, 84, 46, t["accent_soft"])
        self.text(None, "footer", self.spec["short"], M, FOOT_Y, SMALL, BODY, t["muted"])
        self.text(None, "page-number", "${page} / ${pages}", W - M - 90, FOOT_Y, SMALL, BODY, t["muted"])

    # ---- slide templates --------------------------------------------------
    def s_cover(self, p, s):
        t = self.t
        self.op(type="page", action="set", page=p, master="none", background=t["bg"])
        self.circle(p, "art-disc", 1080, 130, 820, t["accent_soft"])
        self.circle(p, "art-ring", 1500, 640, 360, t["accent2_soft"])
        self.intent(p, ["art-disc", "art-ring"], "decoration")
        spots = [(1200, 220, 104), (1570, 300, 68), (1290, 560, 104), (1610, 650, 68)]
        for (x, y, g), e in zip(spots, s["icons"]):
            self.icon(p, e, x, y, g, t["surface"])
        self.text(p, "kicker", s["kicker"].upper(), M, 236, BODY_SIZE, BOLD, t["accent_ink"])
        self.pair(p, s["title"], s["subtitle"], M, 310, 960, COVER, t["ink"], t["muted"],
                  head_name="title", body_name="subtitle", gap=40, body_size=LEAD, lh=1.3)
        self.rect(p, "cover-rule", M, 930, 120, 6, t["accent"], radius=3)
        self.text(p, "footer", s.get("caption", "Presentation · 2026"), M, 962, SMALL, BODY, t["muted"])

    def s_cards(self, p, s):
        t = self.t
        self.title(p, s["title"])
        cards = s["cards"]
        if len(cards) == 3:
            cw, gap, y0, ch = 528, 48, 280, 640
            for i, (e, head, body) in enumerate(cards):
                x = M + i * (cw + gap)
                self.rect(p, self.uid("card"), x, y0, cw, ch, t["surface"], 36, t["line"])
                self.icon(p, e, x + 48, y0 + 48, 68, t["accent_soft"])
                self.pair(p, head, body, x + 48, y0 + 210, cw - 96, LEAD, t["ink"], t["muted"], gap=20)
        else:
            cw, ch, gap, y0 = 816, 320, 48, 268
            for i, (e, head, body) in enumerate(cards):
                x = M + (i % 2) * (cw + gap)
                y = y0 + (i // 2) * (ch + gap)
                self.rect(p, self.uid("card"), x, y, cw, ch, t["surface"], 32, t["line"])
                self.icon(p, e, x + 40, y + 44, 68, t["accent_soft"])
                self.pair(p, head, body, x + 190, y + 46, cw - 230, LEAD, t["ink"], t["muted"])

    def s_split(self, p, s):
        t = self.t
        self.title(p, s["title"])
        md = "\n".join(f"- {b}" for b in s["bullets"])
        self.rich(p, "body", md, M, 300, 880, LEAD, BODY, t["ink"], lh=1.3, para=28)
        px, py, pw, ph = 1110, 268, 690, 690
        self.rect(p, "panel", px, py, pw, ph, t["accent"], 40)
        self.icon(p, s["panel_icon"], px + 56, py + 56, 68, t["on_accent_soft"])
        self.pair(p, s["panel_head"], s["panel_body"], px + 56, py + 220, pw - 112, DISPLAY,
                  t["on_accent"], t["on_accent"], head_name="panel-head", body_name="panel-body", gap=24, lh=1.4)

    def s_stats(self, p, s):
        t = self.t
        self.title(p, s["title"])
        stats = s["stats"]
        cw = (W - 2 * M - 48 * (len(stats) - 1)) // len(stats)
        for i, (num, label) in enumerate(stats):
            x = M + i * (cw + 48)
            self.rect(p, self.uid("stat-card"), x, 280, cw, 560, t["surface"], 36, t["line"])
            self.text(p, self.uid("stat-num"), num, x + 64, 330, STAT, HEAD, t["accent_ink"])
            self.rect(p, self.uid("stat-rule"), x + 64, 570, 96, 8, t["accent"], radius=4)
            self.rich(p, self.uid("stat-label"), label, x + 64, 610, cw - 128, LEAD, BODY, t["ink"], lh=1.3)
        self.rich(p, "source", s["source"], M, 880, W - 2 * M, SMALL, BODY, t["muted"], lh=1.3)

    def s_idea(self, p, s):
        t = self.t
        self.op(type="page", action="set", page=p, master="none", background=t["accent"])
        self.circle(p, "idea-disc", -220, 620, 640, t["on_accent"], opacity=0.08)
        self.circle(p, "idea-disc-2", 1560, -160, 520, t["on_accent"], opacity=0.08)
        self.intent(p, ["idea-disc", "idea-disc-2"], "decoration")
        self.icon(p, s["icon"], (W - ICON_BUBBLE[68]) // 2, 190, 68, t["on_accent_soft"])
        self.text(p, "kicker", s.get("kicker", "KEY IDEA"), "center", 360, BODY_SIZE, BOLD, t["on_accent"])
        self.pair(p, s["text"], s.get("sub", ""), 210, 440, 1500, TITLE, t["on_accent"], t["on_accent"],
                  align="center", head_name="statement", body_name="subtitle", gap=40)
        self.footer(p, t["on_accent"])

    def s_steps(self, p, s):
        t = self.t
        self.title(p, s["title"])
        steps = s["steps"]
        n = len(steps)
        col = (W - 2 * M) / n
        d, cy = 132, 330
        self.rect(p, "steps-line", int(M + col / 2), cy + d // 2 - 4, int(col * (n - 1)), 8, t["accent_soft"], radius=4)
        self.intent(p, ["steps-line"], "decoration")
        for i, (head, body) in enumerate(steps):
            cx = M + col * i + col / 2
            dot = self.uid("step-dot")
            self.circle(p, dot, int(cx - d / 2), cy, d, t["accent"])
            self.op(type="text", page=p, name=self.uid("step-num"), text=str(i + 1), size=DISPLAY, font=HEAD,
                    color=t["on_accent"], within=dot)
            tw = int(col - 36)
            self.pair(p, head, body, int(cx - tw / 2), cy + d + 44, tw, LEAD, t["ink"], t["muted"],
                      align="center", gap=18)

    def s_compare(self, p, s):
        t = self.t
        self.title(p, s["title"])
        cw, y0, ch = 816, 272, 660
        for i, (icon, head, items, tone) in enumerate(s["columns"]):
            x = M + i * (cw + 48)
            self.rect(p, self.uid("col"), x, y0, cw, ch, t["surface"], 36, t["line"])
            band = t["accent"] if tone == "good" else t["warn"]
            self.rect(p, self.uid("col-band"), x, y0, cw, 150, band, 36)
            self.rect(p, self.uid("col-band-fix"), x, y0 + 110, cw, 40, band)
            self.icon(p, icon, x + 40, y0 + 25, 56, t["surface"])
            self.text(p, self.uid("col-head"), head, x + 170, y0 + 42, DISPLAY, HEAD,
                      t["on_accent"] if tone == "good" else t["on_warn"])
            md = "\n".join(f"- {b}" for b in items)
            self.rich(p, self.uid("col-body"), md, x + 48, y0 + 200, cw - 96, BODY_SIZE, BODY, t["ink"], lh=1.3, para=30)

    def s_closing(self, p, s):
        t = self.t
        self.op(type="page", action="set", page=p, master="none", background=t["ink"])
        self.circle(p, "close-disc", 1400, 480, 860, t["accent"], opacity=0.22)
        self.intent(p, ["close-disc"], "decoration")
        self.rect(p, "close-bar", M, 92, 72, 10, t["accent"], radius=5)
        self.text(p, "title", s["title"], M, 122, TITLE, HEAD, t["bg"])
        y = 290
        for i, item in enumerate(s["items"]):
            dot = self.uid("close-num")
            self.circle(p, dot, M, y, 88, t["accent"])
            self.op(type="text", page=p, name=self.uid("close-n"), text=str(i + 1), size=LEAD, font=HEAD,
                    color=t["on_accent"], within=dot)
            self.rich(p, self.uid("close-item"), item, M + 128, y + 14, 1500, LEAD, BODY, t["bg"], lh=1.3)
            y += max(1, est_lines(item, LEAD, 1500, 0.5)) * 58 + 76
        if s.get("note"):
            self.rich(p, "credit", s["note"], M, 900, 1500, SMALL, BODY, t["bg_muted"], lh=1.3)
        self.footer(p, t["bg_muted"])

    TEMPLATES = {"cover": s_cover, "cards": s_cards, "split": s_split, "stats": s_stats, "idea": s_idea,
                 "steps": s_steps, "compare": s_compare, "closing": s_closing}

    def build(self):
        self.master()
        for i, s in enumerate(self.spec["slides"]):
            p = f"{i + 1:02d}-{s['kind']}"
            self.op(type="page", action="add", name=p, master="std", notes=s["notes"])
            self.TEMPLATES[s["kind"]](self, p, s)
        return self.ops


def icon_path(emoji):
    return f"_icons/{'-'.join(f'{ord(c):x}' for c in emoji)}.png"


def render_icons(vixl, emoji, out):
    """Render each emoji with Vixl's bundled artwork onto a transparent 440 px canvas."""
    (out / "_icons").mkdir(exist_ok=True)
    for e in sorted(emoji):
        png = out / icon_path(e)
        tmp = out / "_icons" / "glyph.vixl"
        run(vixl, "new", "440x440", "-o", str(tmp), "--background", "transparent", cwd=out)
        run(vixl, "-p", str(tmp), "text", "add", e, "--name", "glyph", "--size", "400", "--x", "center",
            "--y", "center", cwd=out)
        run(vixl, "-p", str(tmp), "export", str(png), cwd=out)
        tmp.unlink()


def run(vixl, *args, cwd):
    r = subprocess.run([vixl, *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"vixl {' '.join(args)} failed:\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")
    return r.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vixl", default=shutil.which("vixl") or "vixl")
    ap.add_argument("--only")
    args = ap.parse_args()
    out_root = HERE / "decks"
    for spec in DECKS:
        if args.only and spec["slug"] != args.only:
            continue
        out = out_root / spec["slug"]
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True)
        slug = spec["slug"]
        doc = f"{slug}.vixl"
        run(args.vixl, "new", "slide", "-o", doc, "--background", spec["theme"]["bg"], cwd=out)
        for fam, wt in FONTS:
            run(args.vixl, "-p", doc, "font", "install", fam, "--weight", str(wt), cwd=out)
        deck = Deck(spec)
        ops = deck.build()
        render_icons(args.vixl, deck.emoji, out)
        (out / "ops.json").write_text(json.dumps(ops, indent=1))
        run(args.vixl, "-p", doc, "apply", "ops.json", cwd=out)
        os.remove(out / "ops.json")
        shutil.rmtree(out / "_icons")
        check = json.loads(run(args.vixl, "--json", "-p", doc, "check", "--checks", "deck", "--safe-area", "4%", cwd=out) or "{}")
        run(args.vixl, "-p", doc, "render", "--page", "all", "--columns", "3", "--out", f"{slug}-overview.png", cwd=out)
        for ext in ("pdf", "pptx", "html"):
            run(args.vixl, "-p", doc, "export", f"{slug}.{ext}", cwd=out)
        (out / "check.json").write_text(json.dumps(check, indent=1))
        print(slug, "passed" if check.get("passed") else "see check.json")


if __name__ == "__main__":
    main()
