"""Generate the Tidewick coffee infographic (PNG 1200x1800, SVG, PDF) with matplotlib.

Run: python3 make_infographic.py   (from any directory)
"""
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MultipleLocator

HERE = Path(__file__).resolve().parent
CSV = HERE.parents[2] / "fixtures" / "coffee-2025.csv"

NAVY, AMBER, SEAFOAM, CORAL, CREAM = "#14263b", "#f2a541", "#a8d5c8", "#e2725b", "#f7f1e5"
MUTED = "#5b6573"
GRID = "#e2d9c6"

DRINKS = ["flat_white", "drip", "cold_brew", "tea"]
LABELS = {"flat_white": "Flat white", "drip": "Drip", "cold_brew": "Cold brew", "tea": "Tea"}
COLORS = {"flat_white": NAVY, "drip": AMBER, "cold_brew": SEAFOAM, "tea": CORAL}
FULL_MONTH = dict(zip(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"]))

# ---------- data ----------
with open(CSV, newline="", encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))
months = [r["month"] for r in rows]
data = {d: [int(r[d]) for r in rows] for d in DRINKS}
month_tot = [sum(data[d][i] for d in DRINKS) for i in range(len(months))]
drink_tot = {d: sum(data[d]) for d in DRINKS}
grand = sum(month_tot)
assert grand == sum(drink_tot.values())
busy_i = max(range(len(months)), key=lambda i: month_tot[i])
cb_i = max(range(len(months)), key=lambda i: data["cold_brew"][i])
share = {d: 100.0 * drink_tot[d] / grand for d in DRINKS}

print("grand total", grand)
print("busiest", months[busy_i], month_tot[busy_i])
print("cold brew peak", months[cb_i], data["cold_brew"][cb_i])
print("drink totals", drink_tot)
print("shares", {d: f"{share[d]:.1f}" for d in DRINKS})
print("month totals", dict(zip(months, month_tot)))

# ---------- figure ----------
W, H = 1200, 1800
plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "svg.fonttype": "none",  # keep text as text in the SVG
    "pdf.fonttype": 42,
})
fig = plt.figure(figsize=(W / 100, H / 100), dpi=100, facecolor=CREAM)


def px(x, y):
    """pixel coords from top-left -> figure fraction"""
    return x / W, 1 - y / H


def text(x, y, s, **kw):
    fx, fy = px(x, y)
    fig.text(fx, fy, s, **kw)


def axes_px(left, top, width, height, **kw):
    return fig.add_axes([left / W, 1 - (top + height) / H, width / W, height / H], **kw)


M = 80  # side margin

# Header band
hdr = axes_px(0, 0, W, 250)
hdr.set_axis_off()
hdr.add_patch(plt.Rectangle((0, 0), 1, 1, clip_on=False, color=NAVY, transform=hdr.transAxes))
text(M, 118, "A Year of Coffee at Tidewick", fontsize=40, fontweight="bold", color=CREAM, va="baseline")
text(M, 178, "Cups sold per month, 2025", fontsize=22, color=AMBER, va="baseline")

# ---------- callouts ----------
cards = [
    (f"{grand:,}", "cups sold in 2025", "Total"),
    (f"{month_tot[busy_i]:,}", f"cups in {FULL_MONTH[months[busy_i]]}", "Busiest month"),
    (f"{data['cold_brew'][cb_i]:,}", f"cold brews in {FULL_MONTH[months[cb_i]]}", "Cold brew peak"),
]
gap = 30
cw = (W - 2 * M - 2 * gap) / 3
ctop, ch = 300, 170
for k, (big, small, kicker) in enumerate(cards):
    x0 = M + k * (cw + gap)
    ax = axes_px(x0, ctop, cw, ch)
    ax.set_axis_off()
    ax.add_patch(plt.Rectangle((0, 0), 1, 1, clip_on=False, facecolor="white", edgecolor=GRID, lw=1.5,
                               transform=ax.transAxes))
    accent = SEAFOAM if k == 2 else AMBER
    ax.add_patch(plt.Rectangle((0, 0), 0.03, 1, clip_on=False, facecolor=accent, edgecolor="none",
                               transform=ax.transAxes))
    text(x0 + 30, ctop + 42, kicker.upper(), fontsize=13, fontweight="bold", color=MUTED)
    text(x0 + 30, ctop + 112, big, fontsize=40, fontweight="bold", color=NAVY)
    text(x0 + 30, ctop + 148, small, fontsize=15, color=NAVY)

# ---------- legend (shared) ----------
def legend_row(y):
    x = M
    for d in DRINKS:
        ax = axes_px(x, y - 11, 22, 22)
        ax.set_axis_off()
        ax.add_patch(plt.Rectangle((0, 0), 1, 1, clip_on=False, facecolor=COLORS[d], edgecolor=NAVY, lw=0.6,
                                   transform=ax.transAxes))
        text(x + 32, y, LABELS[d], fontsize=16, color=NAVY, va="center")
        x += 32 + len(LABELS[d]) * 10 + 50


# ---------- stacked bar chart ----------
text(M, 540, "Cups sold by month", fontsize=24, fontweight="bold", color=NAVY, va="baseline")
legend_row(585)
bar = axes_px(M + 70, 630, W - 2 * M - 70, 520)
bar.set_facecolor(CREAM)
bottom = [0] * len(months)
xs = range(len(months))
for d in DRINKS:
    bar.bar(xs, data[d], bottom=bottom, color=COLORS[d], width=0.72, label=LABELS[d],
            edgecolor=CREAM, linewidth=0.8, zorder=3)
    bottom = [b + v for b, v in zip(bottom, data[d])]
for i, t in enumerate(month_tot):
    bar.text(i, t + 40, f"{t:,}", ha="center", va="bottom", fontsize=11.5, color=NAVY,
             fontweight="bold")
bar.set_ylim(0, 3500)
bar.yaxis.set_major_locator(MultipleLocator(500))
bar.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{int(v):,}"))
bar.set_xticks(list(xs), months)
bar.set_xlim(-0.6, len(months) - 0.4)
bar.tick_params(axis="both", labelsize=14, colors=NAVY, length=0)
bar.grid(axis="y", color=GRID, lw=1, zorder=0)
for s in ("top", "right", "left"):
    bar.spines[s].set_visible(False)
bar.spines["bottom"].set_color(NAVY)
bar.set_ylabel("Cups", fontsize=14, color=MUTED, labelpad=10)

# ---------- share of year ----------
text(M, 1255, "Share of the year by drink", fontsize=24, fontweight="bold", color=NAVY, va="baseline")
text(M, 1292, f"Percent of all {grand:,} cups sold in 2025", fontsize=15, color=MUTED, va="baseline")

order = sorted(DRINKS, key=lambda d: -drink_tot[d])
donut = axes_px(M, 1320, 380, 380)
donut.pie([drink_tot[d] for d in order], colors=[COLORS[d] for d in order], startangle=90,
          counterclock=False, wedgeprops=dict(width=0.38, edgecolor=CREAM, linewidth=3))
donut.set_aspect("equal")
donut.text(0, 0.08, f"{grand:,}", ha="center", va="center", fontsize=24, fontweight="bold", color=NAVY)
donut.text(0, -0.16, "cups", ha="center", va="center", fontsize=14, color=MUTED)

# table of shares to the right of the donut
tx = M + 450
row_h = 82
for k, d in enumerate(order):
    y = 1365 + k * row_h
    sw = axes_px(tx, y - 16, 32, 32)
    sw.set_axis_off()
    sw.add_patch(plt.Rectangle((0, 0), 1, 1, clip_on=False, facecolor=COLORS[d], edgecolor=NAVY, lw=0.6,
                               transform=sw.transAxes))
    text(tx + 50, y, LABELS[d], fontsize=20, color=NAVY, va="center")
    text(tx + 330, y, f"{share[d]:.1f}%", fontsize=24, fontweight="bold", color=NAVY,
         va="center", ha="right")
    text(W - M, y, f"{drink_tot[d]:,} cups", fontsize=16, color=MUTED, va="center", ha="right")

# ---------- footnote ----------
line = axes_px(M, 1735, W - 2 * M, 1)
line.set_axis_off()
line.axhline(0.5, color=GRID, lw=1.5)
text(M, 1770, "Fictional data, made for testing.", fontsize=14, color=MUTED, va="baseline",
     style="italic")
text(W - M, 1770, "Source: coffee-2025.csv", fontsize=14, color=MUTED, va="baseline", ha="right")

for ext in ("png", "svg", "pdf"):
    fig.savefig(HERE / f"infographic.{ext}", dpi=100, facecolor=CREAM)
print("done")
