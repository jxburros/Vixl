"""Writes Vixl operation files for the Tidewick & Co. mark (geometry in a 512 x 512 design grid)."""
import json, sys, os
OUT = os.path.dirname(os.path.abspath(__file__))
NAVY, AMBER, CREAM = "#14263b", "#f2a541", "#f7f1e5"
FLAME = "M262 92 C276 140 324 160 324 226 A68 68 0 0 1 188 226 C188 186 208 164 222 136 C238 154 244 166 244 184 C262 158 274 128 262 92 Z"
BEAMS = "M356 210 L462 186 L462 266 L356 242 Z M156 210 L50 186 L50 266 L156 242 Z"
W1 = "M118 342 C152.5 342 152.5 370 187 370 C221.5 370 221.5 342 256 342 C290.5 342 290.5 370 325 370 C359.5 370 359.5 342 394 342 A26.0 26.0 0 0 1 394 394 C359.5 394 359.5 422 325 422 C290.5 422 290.5 394 256 394 C221.5 394 221.5 422 187 422 C152.5 422 152.5 394 118 394 A26.0 26.0 0 0 1 118 342 Z"

def part(name, path, x, y, s, fill):
    return {"type": "shape", "shape": "path", "name": name, "path": path, "path_view": [512, 512],
            "x": x, "y": y, "width": s, "height": s, "fill": fill}

def mark(x, y, s, disc="${disc}", fg="${fg}", mono=False, with_disc=True):
    ops = []
    if with_disc:
        ops.append({"type": "shape", "shape": "ellipse", "name": "mark-disc", "x": x + s * 16 / 512,
                    "y": y + s * 16 / 512, "width": s * 480 / 512, "height": s * 480 / 512, "fill": disc})
    ops += [part("mark-flame", FLAME, x, y, s, fg), part("mark-beams", BEAMS, x, y, s, fg), part("mark-wave", W1, x, y, s, fg)]
    if mono:
        ops.append({"type": "pathfinder", "name": "mark-mono", "mode": "subtract",
                    "targets": ["mark-disc", "mark-flame", "mark-beams", "mark-wave"]})
    else:
        ops.append({"type": "group", "name": "mark", "targets": [o["name"] for o in ops]})
    return ops

def variables(disc, fg, ink, tag):
    return [{"type": "variable", "name": "disc", "value": disc}, {"type": "variable", "name": "fg", "value": fg},
            {"type": "variable", "name": "ink", "value": ink}, {"type": "variable", "name": "tag", "value": tag}]

def write(name, ops):
    with open(os.path.join(OUT, name), "w") as f:
        json.dump(ops, f, indent=1)

write("mark.json", variables(NAVY, AMBER, NAVY, NAVY) + mark(0, 0, 512))
write("mark-mono.json", variables("${ink}", AMBER, NAVY, NAVY) + mark(0, 0, 512, disc="${ink}", mono=True))
# app icon: navy full-bleed square, the lamp and water in amber; the disc is the square itself
write("app-icon.json", [{"type": "shape", "shape": "rectangle", "name": "tile", "x": 0, "y": 0,
                         "width": 1024, "height": 1024, "fill": NAVY}] + mark(112, 96, 800, fg=AMBER, with_disc=False))
print("ok")

def words(x, y_word, y_tag, size_word, size_tag, align="left"):
    return [{"type": "text", "name": "wordmark", "text": "Tidewick & Co.", "font": "heading", "size": size_word,
             "color": "${ink}", "x": x, "baseline_y": y_word, "align": align, "tracking": 0},
            {"type": "text", "name": "tagline", "text": "Coffee · Bakery · Harbor", "font": "body", "size": size_tag,
             "color": "${tag}", "x": x, "baseline_y": y_tag, "align": align, "tracking": round(size_tag * 0.12),
             "text_transform": "uppercase"}]

write("horizontal.json", variables(NAVY, AMBER, NAVY, NAVY) + mark(40, 40, 320) + words(400, 220, 296, 150, 40))  # canvas 1554 x 400
write("stacked.json", variables(NAVY, AMBER, NAVY, NAVY) + mark(410, 40, 320) + words(0, 507, 577, 140, 40)  # canvas 1140 x 627
      + [{"type": "align", "target": t, "alignment": "center-x", "relative_to": "canvas"} for t in ("wordmark", "tagline")])
