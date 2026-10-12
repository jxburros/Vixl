import json
D = "evals/tool-comparison/runs/T04/claude-V/round2/src/"
NAVY, AMBER, CREAM = "#14263b", "#f2a541", "#f7f1e5"
ON_CREAM = {"disc": NAVY, "fg": AMBER, "ink": NAVY, "tag": NAVY}
ON_NAVY = {"disc": AMBER, "fg": NAVY, "ink": CREAM, "tag": AMBER}
ops = [{"type": "shape", "shape": "rectangle", "name": "navy-half", "x": 0, "y": 600, "width": 1600, "height": 600, "fill": NAVY}]
def link(name, src, x, y, w, h, v):
    return {"type": "link", "name": name, "source": D + src, "x": x, "y": y, "width": w, "height": h, "fit": "fit", "variables": v}
def label(name, text, x, y, color):
    return {"type": "text", "name": name, "text": text, "font": "body", "size": 18, "color": color, "x": x, "y": y, "tracking": 1}
for half, y0, v, lc in (("cream", 0, ON_CREAM, NAVY), ("navy", 600, ON_NAVY, CREAM)):
    mono = {"ink": NAVY} if half == "cream" else {"ink": CREAM}
    ops += [
        link(f"{half}-horizontal", "logo-horizontal.vixl", 60, y0 + 50, 760, 245, v),
        label(f"{half}-label-horizontal", "Horizontal lockup", 60, y0 + 305, lc),
        link(f"{half}-mark", "mark.vixl", 60, y0 + 350, 200, 200, v),
        label(f"{half}-label-mark", "Mark", 60, y0 + 560, lc),
        link(f"{half}-mono", "mark-mono.vixl", 300, y0 + 350, 200, 200, mono),
        label(f"{half}-label-mono", "Mark, one colour" + (" (navy)" if half == "cream" else " (cream knockout)"), 300, y0 + 560, lc),
        link(f"{half}-mark-64", "mark.vixl", 560, y0 + 486, 64, 64, v),
        link(f"{half}-mark-32", "mark.vixl", 648, y0 + 518, 32, 32, v),
        link(f"{half}-mark-16", "mark.vixl", 704, y0 + 534, 16, 16, v),
        label(f"{half}-label-sizes", "64 / 32 / 16 px, actual size", 560, y0 + 560, lc),
        link(f"{half}-stacked", "logo-stacked.vixl", 1080, y0 + 50, 460, 335, v),
        label(f"{half}-label-stacked", "Stacked lockup", 1080, y0 + 395, lc),
    ]
ops += [link("cream-app-icon", "app-icon.vixl", 1080, 430, 120, 120, {}),
        label("cream-label-app-icon", "App icon", 1080, 560, NAVY)]
json.dump(ops, open("sheet.json", "w"), indent=1)
