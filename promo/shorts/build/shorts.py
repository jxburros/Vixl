"""The ten Vixl shorts. Each function returns a ``Short``; times are milliseconds.

Every short has the same four sections: a hook that names the problem, the feature in action with the
operations that produce it ("how it works"), three reasons it matters, and the end card. Where a feature can
run inside the build it does: the art on screen is that feature's output, and the numbers are read from it.
"""
from __future__ import annotations

import short  # noqa: F401  (puts promo/build on the path)
import inputs  # noqa: E402
import scenes as promo  # noqa: E402  promo/build/scenes.py: the festival poster from "Vixl in 60 seconds"
from short import (BAD, BLUE, BODY, CODE_KEY, CODE_NUM, CODE_STR, CORAL, DEEP, GOLD, GOOD, GUTTER, HEAD, INK, LILAC,
                   LINE, MINT, MONO, MUTED, PANEL, PAPER, SEMI, SKY, WHITE, W, Short, centered, chip, code_line,
                   ellipse, endcard, frame, group, headline, hook, how, image, op_spans, panel, rect,
                   rel, rich, shadow, tag, text, why)  # noqa: E402


def standard(action_end, why_len=4600, end_len=3000, hook_len=3000):
    return {"hook": (0, hook_len), "action": (hook_len, action_end),
            "why": (action_end, action_end + why_len), "end": (action_end + why_len, action_end + why_len + end_len)}


# ----------------------------------------------------------------------------------------------- 1
OPS01 = [("sky", [("type", "gradient"), ("name", "sky")]),
         ("sun", [("type", "shape"), ("shape", "ellipse")]),
         ("dunes", [("type", "pen"), ("name", "dunes")]),
         ("title", [("type", "text"), ("text", "SOLSTICE")]),
         ("dates", [("type", "text"), ("size", 30)]),
         ("badge", [("type", "shape"), ("shape", "star")]),
         ("look", [("type", "look"), ("look", "glow")])]


def s01_layers():
    sc = Short(1, "layers", "Real layers", standard(12600))
    frame(sc)
    hook(sc, "Ask an AI for a poster.", "You get a flat picture. One typo means starting over.",
         [("Vixl hands you the ", None), ("layers.", SKY)])
    t0, t1 = sc.sections["action"]
    tag(sc, "action", "IN ACTION", t0)
    headline(sc, "action", [("Your agent builds it ", None), ("layer by layer.", SKY)], t0 + 100)
    px, py, pw, ph = 240, 450, 600, 750
    sheets = promo.poster("p", px, py, pw, ph)
    sheets["sky2"] = [{"type": "gradient", "name": "p-sky2", "direction": "vertical", "x": px, "y": py,
                       "width": pw, "height": ph, "stops": [{"offset": o, "color": c} for o, c in promo.DAWN]}]
    sc.put("action", rect("artboard", px, py, pw, ph, DEEP), shadow("artboard", 50, 24, 0.5))
    times = {name: t0 + 700 + i * 520 for i, (name, _) in enumerate(OPS01)}
    order = ["sky", "sky2", "halo", "sun", "dunes-back", "dunes-front", "title", "dates", "badge"]
    t_open, t_close = t0 + 4700, t0 + 6500
    level = 0
    for name in order:
        ops = sheets[name]
        members = [op["name"] for op in ops if op["type"] not in ("group", "layer-intent")]
        if name == "badge":
            members = ["p-badge"]
        outline = f"sheet-{name}"
        sc.put("action", ops, rect(outline, px, py, pw, ph, "#6A9AFF08", 0, SKY, 2),
               group(f"g-{name}", members + [outline]))
        sc.keys(outline, "opacity", [(0, 0), (t_open, 0), (t_open + 400, 1), (t_close, 1), (t_close + 400, 0)])
        if name == "sky2":
            continue
        dy = (level - 4) * -62
        dx = (level - 4) * 18
        for prop, v in (("translate-x", dx), ("translate-y", dy)):
            sc.keys(f"g-{name}", prop, [(0, 0), (t_open, 0), (t_open + 700, v), (t_close, v), (t_close + 600, 0)],
                    "ease-in-out-cubic")
        sc.keys(f"g-{name}", "scale", [(0, 1), (t_open, 1), (t_open + 700, 0.66), (t_close, 0.66),
                                       (t_close + 600, 1)], "ease-in-out-cubic")
        level += 1
    sc.keys("artboard", "opacity", [(0, 1), (t_open, 1), (t_open + 400, 0), (t_close + 200, 0), (t_close + 600, 1)])
    for prop in ("translate-x", "translate-y", "scale"):
        for o in [o for o in sc.ops if o.get("target") == "g-sky" and o.get("property") == prop]:
            sc.ops.append({**o, "target": "g-sky2"})
    # The build: each sheet arrives with its operation.
    sc.keys("p-sky2", "opacity", [(0, 0), (t0 + 7600, 0), (t0 + 8200, 1)], "ease-in-out")
    sc.fade("p-sky", times["sky"], dur=500)
    sc.pop("p-sun", times["sun"], 600, 0.2)
    sc.slide("p-dunes-back", times["dunes"], dy=260, dur=800)
    sc.slide("p-dunes-front", times["dunes"] + 120, dy=220, dur=800)
    sc.fade("p-dunes-back", times["dunes"], dur=200)
    sc.fade("p-dunes-front", times["dunes"] + 120, dur=200)
    sc.words("p-title", times["title"], "pop", "char", 380, 50)
    sc.words("p-dates", times["dates"], "fade-up", "word", 400, 90)
    sc.pop("p-badge", times["badge"], 500, 0.1)
    sc.keys("p-badge", "rotation", [(0, -40), (times["badge"], -40), (times["badge"] + 600, 12)], "ease-out-back")
    sc.fade("p-halo", times["look"], dur=700)
    # The edit: one operation renames the festival; the text stays text.
    t_edit = t0 + 7600
    sc.key("p-title", "text", 0, "SOLSTICE")
    sc.key("p-title", "text", t_edit, "EQUINOX", "hold")
    sc.keys("p-title", "scale", [(t_edit, 1.14), (t_edit + 400, 1)], "ease-out-back")
    sc.keys("p-sun", "fill", [(t_edit, promo.SUN), (t_edit + 600, promo.SUN2)], "ease-in-out")
    lines = [op_spans(pairs) for _, pairs in OPS01]
    lines.append(op_spans([("type", "text-set"), ("target", "title"), ("text", "EQUINOX")]))
    names = how(sc, "action", lines, 1260, t0 + 400, size=24, stagger=520)
    sc.keys(names[-1], "opacity", [(0, 0), (t_edit - 300, 0), (t_edit, 1)])
    sc.add({"type": "shape", "shape": "rounded-rectangle", "name": "edit-hi", "x": GUTTER + 20,
            "y": 1260 + 64 + 7 * 36, "width": W - 2 * GUTTER - 40, "height": 40, "radius": 8, "fill": "#3575EE40"})
    sc.adopt("action", "edit-hi")
    sc.fade("edit-hi", t_edit - 300, dur=300)
    sc.put("action", chip("layers-chip", "9 layers · fanned out", 330, 1210 - 20, size=24, fg=WHITE,
                          bg="#141824D9", font=SEMI, width=420))
    sc.keys("layers-chip", "opacity", [(0, 0), (t_open + 300, 0), (t_open + 600, 1), (t_close, 1),
                                       (t_close + 300, 0)])
    sc.put("action", chip("edit-chip", "1 edit · not a new image", 330, 1190, size=24, fg=DEEP, bg=SKY, font=SEMI,
                          width=420))
    sc.pop("edit-chip", t_edit + 300, 400, 0.7)
    why(sc, [("Not a picture. ", None), ("A document.", SKY)], [
        ("Text stays text", "Fix a typo or rename the event with one operation, not a regenerated image."),
        ("Every layer has a name", "Your agent can target the sun, the title or the badge, and nothing else moves."),
        ("All or nothing, one undo", "Up to 10,000 operations apply atomically, so a batch never half-lands.")])
    endcard(sc, [("Ideas become ", None), ("editable.", SKY)], "Real layers you and your agent keep working on.")
    return sc



# ----------------------------------------------------------------------------------------------- 2
def s02_check():
    figures = inputs.contrast()
    before, needs = figures["before"], figures["needs"]
    sc = Short(2, "checked", "Checked before it ships", standard(11600))
    frame(sc)
    hook(sc, "AI makes it fast.", "It also ships text nobody can read, cut off at the edge.",
         [("Vixl ", None), ("checks the work.", SKY)])
    t0, t1 = sc.sections["action"]
    tag(sc, "action", "IN ACTION", t0)
    headline(sc, "action", [("Problems caught ", None), ("before anyone prints.", SKY)], t0 + 100)
    px, py, pw, ph = 290, 440, 500, 625
    sc.put("action", rect("canvas", px, py, pw, ph, DEEP), shadow("canvas", 50, 24, 0.5))
    sc.put("action", promo.flat(promo.poster("p", px, py, pw, ph, dates_color=promo.DIM_DATES)))
    sc.put("action", group("poster", [n for n in sc.members["action"] if n.startswith("p-")] + ["canvas"]))
    sc.pop("poster", t0 + 200, 500, 0.9)
    t_fix = t0 + 4600
    sc.keys("p-dates", "color", [(0, promo.DIM_DATES), (t_fix, promo.DIM_DATES), (t_fix + 400, WHITE)], "ease-in-out")
    s = pw / 640
    sc.put("action", rect("flag", px + 70 * s, py + 190 * s, pw - 140 * s, 60 * s, "#FF6B6B14", 8, BAD, 3))
    sc.keys("flag", "opacity", [(0, 0), (t0 + 1900, 0), (t0 + 2100, 1), (t0 + 2400, 0.4), (t0 + 2700, 1),
                                (t0 + 3000, 0.4), (t0 + 3300, 1)])
    sc.keys("flag", "stroke_color", [(t_fix, BAD), (t_fix + 300, GOOD)])
    sc.keys("flag", "fill", [(t_fix, "#FF6B6B14"), (t_fix + 300, "#5FD38D14")])
    sc.keys("flag", "opacity", [(t_fix + 1200, 1), (t_fix + 1700, 0)])
    # The report panel: the command, then one row per check.
    fx, fy, fw = GUTTER, 1110, W - 2 * GUTTER
    sc.put("action", panel("report", fx, fy, fw, 470))
    sc.fade("report", t0 + 600, dur=300)
    sc.put("action", text("cmd", "$ vixl -p poster.vixl check", fx + 34, fy + 26, 26, WHITE, MONO))
    sc.words("cmd", t0 + 800, "typewriter", "char", 600)
    rows = [("contrast", f"dates {before}:1, needs {needs}:1"), ("bounds", "every layer inside the canvas"),
            ("overlap", "title, dates and badge stay clear"), ("fonts", "Inter Tight and Inter embedded")]
    for i, (name, detail) in enumerate(rows):
        y = fy + 84 + i * 92
        bad = name == "contrast"
        r = f"r{i}"
        sc.put("action", rect(f"{r}-bg", fx + 24, y, fw - 48, 80, PANEL, 16),
               ellipse(f"{r}-dot", fx + 70, y + 40, 40, 40, BAD if bad else GOOD),
               rich(f"{r}-mark", "!" if bad else "✓", fx + 50, y + 24, 26, 40, DEEP, HEAD, "center", 1.2),
               text(f"{r}-name", name, fx + 110, y + 22, 30, WHITE, SEMI),
               text(f"{r}-detail", detail, fx + 290, y + 26, 25, BAD if bad else MUTED, BODY),
               group(r, [f"{r}-bg", f"{r}-dot", f"{r}-mark", f"{r}-name", f"{r}-detail"]))
        t = t0 + 1700 + i * 260
        sc.fade(r, t, dur=300)
        sc.slide(r, t, dx=50, dur=450)
    sc.keys("r0-dot", "fill", [(t_fix, BAD), (t_fix + 300, GOOD)])
    sc.key("r0-mark", "text", 0, "!")
    sc.key("r0-mark", "text", t_fix + 150, "✓", "hold")
    sc.key("r0-detail", "text", 0, f"dates {before}:1, needs {needs}:1")
    sc.key("r0-detail", "text", t_fix + 150, f"dates now clears {needs}:1", "hold")
    sc.keys("r0-detail", "color", [(t_fix, BAD), (t_fix + 300, MUTED)])
    sc.put("action", code_line("fix-op", op_spans([("type", "text-set"), ("target", "dates"), ("color", "white")]),
                               fx + 24, fy + 470 + 24, 24))
    sc.words("fix-op", t_fix - 1000, "typewriter", "char", 700)
    sc.put("action", chip("pass", "✓  4 of 4 checks pass", (W - 440) / 2, 1080 - 30, size=28, fg=DEEP, bg=GOOD,
                          font=SEMI, width=440))
    sc.pop("pass", t_fix + 1500, 450, 0.5)
    why(sc, [("Trust it ", None), ("before you ship it.", SKY)], [
        ("Measured, not eyeballed", f"Contrast is a ratio: this line read {before}:1 against a {needs}:1 minimum."),
        ("Your rules, too", "Write the brief as check suites: spacing, hierarchy, brand colours, bleed."),
        ("Fixed by the agent", "Findings come with the layer and a repair, so the agent fixes them first.")])
    endcard(sc, [("Design that ", None), ("checks itself.", SKY)], "Contrast, bounds, overlap, fonts and your own rules.")
    return sc


# ----------------------------------------------------------------------------------------------- 3
def s03_sizes():
    cards = inputs.cards()
    sc = Short(3, "every-size", "One design, every size", standard(12200))
    frame(sc)
    hook(sc, "One post. Then a story.", "Then a thumbnail. Each one rebuilt by hand, or stretched until it breaks.",
         [("Design once. ", None), ("Ship every size.", SKY)])
    t0, t1 = sc.sections["action"]
    tag(sc, "action", "IN ACTION", t0)
    headline(sc, "action", [("Recomposed for each size, ", None), ("not stretched.", SKY)], t0 + 100)
    cx, cy = W / 2, 790
    big = {"post": (640, 640), "story": (382, 680), "video": (920, 518)}
    labels = {"post": "1080 × 1080  ·  feed post", "story": "1080 × 1920  ·  story",
              "video": "1280 × 720  ·  video thumbnail"}
    starts = {"post": t0 + 500, "story": t0 + 2700, "video": t0 + 4900}
    t_row = t0 + 7000
    for i, key in enumerate(("post", "story", "video")):
        w, h = big[key]
        name = f"big-{key}"
        sc.put("action", image(name, rel(cards[key]["path"]), cx - w / 2, cy - h / 2, w, h, 16, "fill"),
               shadow(f"{name}-base", 50, 22, 0.5))
        t = starts[key]
        end = starts[("post", "story", "video")[i + 1]] if i < 2 else t_row
        sc.keys(name, "scale", [(0, 0.8), (t, 0.8), (t + 550, 1), (end, 1), (end + 450, 0.85)], "ease-out-back")
        sc.keys(name, "opacity", [(0, 0), (t, 0), (t + 300, 1), (end, 1), (end + 400, 0)])
        lab = f"lab-{key}"
        sc.put("action", centered(lab, labels[key], cy + 360, 30, MUTED, MONO))
        sc.keys(lab, "opacity", [(0, 0), (t + 200, 0), (t + 500, 1), (end, 1), (end + 300, 0)])
    # All three side by side.
    row = [("post", 300, 300), ("story", 169, 300), ("video", 400, 225)]
    x = (W - sum(w for _, w, _ in row) - 50) / 2
    for i, (key, w, h) in enumerate(row):
        name = f"small-{key}"
        sc.put("action", image(name, rel(cards[key]["path"]), x, cy - h / 2, w, h, 10, "fill"),
               shadow(f"{name}-base", 30, 12, 0.5))
        sc.pop(name, t_row + 200 + i * 160, 450, 0.6)
        c = f"cap-{key}"
        sc.put("action", rich(c, f"{cards[key]['width']}×{cards[key]['height']}", x, cy + 170, 22, w, MUTED, MONO,
                              "center"))
        sc.fade(c, t_row + 400 + i * 160, dur=300)
        x += w + 25
    sc.put("action", chip("ok", "✓  check: 0 fixes at every size", (W - 520) / 2, cy + 230, size=26, fg=DEEP, bg=GOOD,
                          font=SEMI, width=520))
    sc.pop("ok", t_row + 900, 400, 0.6)
    how(sc, "action", [[("$ vixl layout apply split-screen", WHITE)],
                       [("$ vixl adapt-layout --size story --recompose", WHITE)],
                       [("$ vixl adapt-layout --size youtube-thumbnail --recompose", WHITE)]],
        1300, t0 + 600, size=24, stagger=2200)
    why(sc, [("One master. ", None), ("Every channel.", SKY)], [
        ("Recomposed, not cropped", "The layout is rebuilt for each shape, so nothing is squashed or cut off."),
        ("Checked at every size", "Each copy runs through check, so small text and clipped layers get caught."),
        ("Still editable", "Every size is its own layered document: PNG, SVG or PDF, plus the master.")])
    endcard(sc, [("Every size. ", None), ("One design.", SKY)], "Feed posts, stories, thumbnails, banners and slides.")
    return sc


# ----------------------------------------------------------------------------------------------- 4
def s04_print():
    run = inputs.badges()
    sc = Short(4, "print-run", "Spreadsheet to print run", standard(11800))
    frame(sc)
    hook(sc, "200 name badges.", "Each with its own name and QR code. Copy and paste until midnight?",
         [("A spreadsheet in. ", None), ("A print run out.", SKY)])
    t0, t1 = sc.sections["action"]
    tag(sc, "action", "IN ACTION", t0)
    headline(sc, "action", [("Every badge different. ", None), ("Every QR code real.", SKY)], t0 + 100)
    sc.put("action", panel("csv", GUTTER, 430, W - 2 * GUTTER, 360))
    sc.put("action", text("csv-title", "people.csv", GUTTER + 34, 452, 22, MUTED, MONO))
    sc.fade("csv", t0 + 200, dur=300)
    sc.fade("csv-title", t0 + 300, dur=300)
    rows = [[(",".join(run["csv"][0]), CODE_KEY)]]
    rows += [[(r[0], CODE_NUM), (",", WHITE), (r[1], CODE_STR), (",", WHITE), (r[2], WHITE)] for r in run["csv"][1:6]]
    rows.append([(f"… {run['rows'] - 5} more rows", MUTED)])
    for i, spans in enumerate(rows):
        name = f"row{i}"
        sc.put("action", code_line(name, spans, GUTTER + 34, 500 + i * 40, 25))
        sc.fade(name, t0 + 500 + i * 130, dur=250)
    sc.put("action", text("cmd", "$ vixl workflow merge-impose", GUTTER, 820, 28, WHITE, MONO))
    sc.words("cmd", t0 + 1700, "typewriter", "char", 700)
    sw, sh = 400, 518
    layout = [(3, 380, 900, 8), (2, 330, 915, -6), (1, 300, 920, 0)]
    for i, (page, x, y, rot) in enumerate(layout):
        key = f"sheet{page}"
        sc.put("action", image(key, rel(run["sheets"][page - 1]), x, y, sw, sh, 6, "fit", "#FFFFFF"),
               shadow(f"{key}-base", 50, 22, 0.55))
        t = t0 + 2600 + i * 240
        sc.pop(key, t, 560, 0.7)
        sc.keys(key, "rotation", [(0, rot * 2), (t, rot * 2), (t + 700, rot)], "ease-out-cubic")
        sc.keys(key, "translate-y", [(0, 160), (t, 160), (t + 700, 0)], "ease-out-expo")
    sc.keys("sheet1", "scale", [(t0 + 3800, 1), (t1, 1.08)], "ease-in-out")
    stat = f"{run['rows']} rows · {run['pages']} sheets · {run['errors']} errors"
    sc.put("action", chip("stat", stat, (W - 620) / 2, 1500, size=28, fg=WHITE, bg="#3575EED9", font=SEMI, width=620))
    sc.pop("stat", t0 + 4400, 450, 0.9)
    why(sc, [("Data in, ", None), ("press-ready out.", SKY)], [
        ("Every row checked", f"{run['valid']} of {run['rows']} rows valid before a single sheet is printed."),
        ("Ready for the press", "Imposed on letter sheets with crop marks, registration and a slug line."),
        ("Change the CSV, rerun", "Fix one name and regenerate the run; the template stays one editable design.")])
    endcard(sc, [("Merge. Impose. ", None), ("Print.", SKY)], "Badges, certificates, labels and cards from a spreadsheet.")
    return sc


# ----------------------------------------------------------------------------------------------- 5
def s05_sketch():
    paths, report = inputs.sketch()
    sc = Short(5, "sketch", "Sketch to vectors", standard(11800))
    frame(sc)
    hook(sc, "A sketch on paper.", "Hours of redrawing it line by line before you can use it.",
         [("Snap it. ", None), ("Get vectors.", SKY)])
    t0, t1 = sc.sections["action"]
    tag(sc, "action", "IN ACTION", t0)
    headline(sc, "action", [("A phone photo becomes ", None), ("clean, editable lines.", SKY)], t0 + 100)
    x, y, w, h = GUTTER, 450, W - 2 * GUTTER, 690
    steps = [("photo", "1  photo", t0 + 300), ("cleaned", "2  vectorize", t0 + 2600),
             ("finished", "3  fill", t0 + 4900)]
    for i, (key, label, t) in enumerate(steps):
        name = f"img-{key}"
        sc.put("action", image(name, rel(paths[key]), x, y, w, h, 20, "fit", PAPER))
        if i == 0:
            sc.add(shadow(f"{name}-base", 50, 22, 0.5))
            sc.pop(name, t, 520, 0.9)
        else:
            sc.keys(name, "opacity", [(0, 0), (t, 0), (t + 600, 1)], "ease-in-out")
        cw = 280
        cname = f"step-{key}"
        sc.put("action", chip(cname, label, GUTTER + i * (cw + 40), 1170, size=24, fg=WHITE, bg=PANEL, font=MONO,
                              width=cw + (40 if i == 2 else 0) - (20 if i == 2 else 0), stroke=LINE))
        sc.fade(cname, t0 + 300 + i * 120, dur=300)
        sc.keys(f"{cname}-bg", "fill", [(0, PANEL), (t, PANEL), (t + 300, BLUE)])
    kept = f"{report['preserved']:.0%}"
    how(sc, "action", [op_spans([("type", "drawing"), ("action", "import")]),
                       op_spans([("type", "drawing"), ("action", "vectorize")]),
                       op_spans([("type", "drawing"), ("action", "straighten")]),
                       op_spans([("type", "drawing"), ("action", "fill")])], 1270, t0 + 600, size=25, stagger=1150)
    sc.put("action", chip("stat", f"{kept} of lines kept · {report['strokes']} strokes · tilt fixed "
                                  f"{abs(report['tilt_corrected']):g}°", GUTTER, 1590 - 0, size=24, fg=WHITE,
                          bg="#3575EED9", font=SEMI, width=W - 2 * GUTTER))
    sc.pop("stat", t0 + 6400, 450, 0.9)
    why(sc, [("Your hand. ", None), ("Clean files.", SKY)], [
        ("Keeps your line", f"The vectors follow the drawing: {kept} of the original strokes survive the cleanup."),
        ("Straightened for you", "Tilt, gaps and wobble are corrected; closed shapes can be filled with one point."),
        ("Ready for anything", "Recolour, resize and export SVG or PDF. No tracing by hand.")])
    endcard(sc, [("From paper to ", None), ("vectors.", SKY)], "Logos, icons, comics and diagrams from a sketch.")
    return sc


# ----------------------------------------------------------------------------------------------- 6
DIAGRAM = "idea -> sketch -> layers -> check -> ship\ncheck -> fix -> layers"


def s06_diagram():
    sc = Short(6, "diagram", "Text to diagram", standard(11400))
    frame(sc)
    hook(sc, "Diagrams take forever.", "Boxes, arrows, nudging lines so nothing crosses.",
         [("Type the flow. ", None), ("Get the diagram.", SKY)])
    t0, t1 = sc.sections["action"]
    tag(sc, "action", "IN ACTION", t0)
    headline(sc, "action", [("One line of text, ", None), ("laid out and routed.", SKY)], t0 + 100)
    sc.put("action", panel("src", GUTTER, 430, W - 2 * GUTTER, 150))
    sc.fade("src", t0 + 100, dur=300)
    for i, line in enumerate(DIAGRAM.split("\n")):
        sc.put("action", text(f"src{i}", line, GUTTER + 34, 462 + i * 50, 28, CODE_STR, MONO))
        sc.words(f"src{i}", t0 + 400 + i * 800, "typewriter", "char", 700)
    sc.add({"type": "diagram-from-text", "name": "dg", "text": DIAGRAM, "x": GUTTER, "y": 620, "width": W - 2 * GUTTER,
            "height": 920, "direction": "TB", "routing": "curved", "theme": "dark", "node_color": PANEL,
            "edge_color": SKY, "text_color": WHITE, "font": SEMI, "size": 30, "stroke_width": 3, "margin": 10, "fit": "contain", "rank_gap": 60,
            "node_gap": 50})
    sc.adopt("action", "dg")
    nodes = ["idea", "sketch", "layers", "check", "fix", "ship"]
    for i, node in enumerate(nodes):
        t = t0 + 2200 + i * 200
        sc.pop(f"dg/{node}", t, 380, 0.5)
        sc.fade(f"dg/{node}.label", t + 80, dur=250)
    edges = ["idea->sketch", "sketch->layers", "layers->check", "check->ship", "check->fix", "fix->layers"]
    for i, edge in enumerate(edges):
        t = t0 + 2500 + i * 200
        sc.fade(f"dg/{edge}", t, dur=300)
        sc.keys(f"dg/{edge}", "trim_end", [(0, 0), (t, 0), (t + 450, 100)], "ease-out-cubic")
    t_style = t0 + 5200
    for i, node in enumerate(nodes):
        sc.keys(f"dg/{node}", "fill", [(0, PANEL), (t_style + i * 80, PANEL), (t_style + 300 + i * 80, BLUE)],
                "ease-in-out")
    sc.keys("dg/check", "scale", [(t_style + 800, 1), (t_style + 1000, 1.12), (t_style + 1250, 1)], "ease-out-cubic")
    sc.put("action", code_line("restyle", op_spans([("type", "shape"), ("targets", "[…]"), ("fill", "@brand")]),
                               GUTTER, 1570, 24))
    sc.words("restyle", t_style - 600, "typewriter", "char", 500)
    why(sc, [("Diagrams that ", None), ("stay editable.", SKY)], [
        ("Layout and routing done", "Nodes are placed and edges routed so lines do not cross boxes."),
        ("Every node is a layer", "Restyle, recolour or animate any node or edge with one operation."),
        ("Change the text, redraw", "Add a step to the line and the diagram lays itself out again.")])
    endcard(sc, [("Type it. ", None), ("See it.", SKY)], "Flowcharts, org charts, timelines and maps.")
    return sc


# ----------------------------------------------------------------------------------------------- 7
def s07_chart():
    cx, cy, cw, ch = GUTTER + 20, 470, W - 2 * GUTTER - 40, 700
    data = inputs.chart(cx, cy, cw, ch)
    sc = Short(7, "charts", "Charts that stay data", standard(11600))
    frame(sc)
    hook(sc, "A chart in a picture.", "One number is wrong and the whole image has to be redone.",
         [("Charts that stay ", None), ("data.", SKY)])
    t0, t1 = sc.sections["action"]
    tag(sc, "action", "IN ACTION", t0)
    headline(sc, "action", [("Fix one number. ", None), ("The chart follows.", SKY)], t0 + 100)
    sc.put("action", panel("chart-bg", GUTTER, 440, W - 2 * GUTTER, 760))
    sc.fade("chart-bg", t0 + 100, dur=300)
    sc.put("action", data["op"])
    sc.pop("sales", t0 + 400, 600, 0.85)
    t_fix = t0 + 3800
    before, after = data["before"], data["after"]
    for name, old in before.items():
        if name == "sales" or old["type"] == "group":
            continue
        new = after.get(name)
        if new is None:
            sc.keys(name, "opacity", [(t_fix, 1), (t_fix + 300, 0)])
            continue
        for prop in ("x", "y", "width", "height"):
            if old.get(prop) != new.get(prop):
                sc.keys(name, prop, [(0, old[prop]), (t_fix, old[prop]), (t_fix + 900, new[prop])],
                        "ease-in-out-cubic")
        if old.get("text") != new.get("text"):
            sc.key(name, "text", 0, old["text"])
            sc.key(name, "text", t_fix + 450, new["text"], "hold")
    sc.put("action", rect("hi", cx + after["sales/bar Espresso Apr"]["x"] - 10, cy, 92, ch - 70, "#FFFFFF10", 12, SKY, 3))
    sc.keys("hi", "opacity", [(0, 0), (t_fix - 400, 0), (t_fix - 100, 1), (t_fix + 1600, 1), (t_fix + 2000, 0)])
    how(sc, "action", [op_spans([("type", "chart"), ("kind", "bar"), ("title", "Cups sold")]),
                       [("$ vixl chart-data --target sales --set Apr:Espresso=2400", WHITE)],
                       [("$ vixl export deck.pptx", WHITE)]], 1250, t0 + 600, size=24, stagger=1900)
    native = "native chart" if data["native_charts"] == 1 else f"{data['native_charts']} native charts"
    sc.put("action", chip("pptx", f"deck.pptx · {native} · data table inside", GUTTER, 1555, size=24, fg=WHITE,
                          bg="#3575EED9", font=SEMI, width=W - 2 * GUTTER))
    sc.pop("pptx", t0 + 5600, 450, 0.9)
    why(sc, [("Numbers, ", None), ("not pixels.", SKY)], [
        ("One edit, everything moves", "Scale, ticks, bars, labels and legend update together, on the same layers."),
        ("Real PowerPoint charts", "Export to PPTX and the chart is native, with its data table embedded."),
        ("Bound to your CSV", "Point a chart at a file; fix a row and reload instead of redrawing.")])
    endcard(sc, [("Charts you can ", None), ("still edit.", SKY)], "Bar, line, area, pie and donut charts.")
    return sc


# ----------------------------------------------------------------------------------------------- 8
PIXEL_PALETTE = {".": "transparent", "k": "#1A1F2B", "s": SKY, "w": "#FFFFFF", "b": BLUE, "y": GOLD, "r": CORAL}
ROBOT = [".....kk.....", ".....yk.....", "..kkkkkkkk..", ".kssssssssk.", ".kswwsswwsk.", ".kswksswksk.",
         ".kssssrsssk.", "..kkkkkkkk..", ".kbbbbbbbbk.", "kbbbyybbbbbk", "kbkbbbbbbkbk", ".kkbbbbbbkk.",
         "..kkkkkkkk.."]
LEGS = [["..kbk..kbk..", "..kbk..kbk..", ".kkkk..kkkk."],
        ["..kbk..kbk..", ".kkkk..kbk..", ".......kkkk."],
        ["..kbk..kbk..", "..kbk..kbk..", ".kkkk..kkkk."],
        ["..kbk..kbk..", "..kbk..kkkk.", ".kkkk......."]]
GRASS = ["gggggggggggggggg", "gGggggGgggggGggg", "dddddddddddddddd", "dDddddddDddddddd"]


def pixel_spans(row):
    spans = []
    for ch in row:
        colour = PIXEL_PALETTE[ch] if ch != "." else "#4A5368"
        if spans and spans[-1][1] == colour:
            spans[-1] = (spans[-1][0] + ch, colour)
        else:
            spans.append((ch, colour))
    return spans


def s08_pixel():
    sc = Short(8, "pixel-art", "Pixel art that walks", standard(11400))
    frame(sc)
    hook(sc, "Game sprites by hand.", "Pixel by pixel, frame by frame, then a sprite sheet on top.",
         [("Type the rows. ", None), ("It walks.", SKY)])
    t0, t1 = sc.sections["action"]
    tag(sc, "action", "IN ACTION", t0)
    headline(sc, "action", [("Sprites from rows of text, ", None), ("animated.", SKY)], t0 + 100)
    rows = ROBOT + LEGS[0]
    sc.put("action", panel("rows-panel", GUTTER, 440, 400, 640))
    sc.fade("rows-panel", t0 + 100, dur=300)
    for i, row in enumerate(rows):
        name = f"rw{i}"
        sc.put("action", code_line(name, pixel_spans(row), GUTTER + 40, 470 + i * 36, 28, 340))
        sc.fade(name, t0 + 300 + i * 60, dur=200)
    scale, x, y = 30, 560, 520
    frames = []
    for i, legs in enumerate(LEGS):
        name = f"robot{i}"
        sc.put("action", {"type": "pixel-art", "name": name, "x": x, "y": y, "palette": PIXEL_PALETTE,
                          "rows": ROBOT + legs})
        sc.add({"type": "scale", "target": name, "factor": scale})
        frames.append(name)
    step, start = 150, t0 + 1800
    for i, name in enumerate(frames):
        sc.key(name, "visible", 0, i == 0)
        t, k = start, 0
        while t < t1:
            sc.key(name, "visible", t, k % 4 == i, "hold")
            t += step
            k += 1
    sc.put("action", group("robot", frames))
    sc.pop("robot", t0 + 1500, 450, 0.3)
    ground_pal = {"g": "#4FBF6A", "G": "#7EDB8E", "d": "#7A5236", "D": "#5E3E28"}
    tiles = []
    for i in range(7):
        name = f"tile{i}"
        sc.put("action", {"type": "pixel-art", "name": name, "x": 520 + i * 96, "y": y + 16 * scale,
                          "palette": ground_pal, "rows": GRASS})
        sc.add({"type": "scale", "target": name, "factor": 6})
        tiles.append(name)
    sc.put("action", group("ground", tiles))
    sc.fade("ground", t0 + 1500, dur=300)
    period = 4 * step
    t = start
    while t < t1:
        sc.key("ground", "translate-x", t, 0, "hold")
        sc.key("ground", "translate-x", t + period - 1, -96, "linear")
        t += period
    sheet = []
    for i, legs in enumerate(LEGS):
        name = f"sheet{i}"
        sc.put("action", {"type": "pixel-art", "name": name, "x": 560 + i * 110, "y": 1150, "palette": PIXEL_PALETTE,
                          "rows": ROBOT + legs})
        sc.add({"type": "scale", "target": name, "factor": 7})
        sc.pop(name, t0 + 3600 + i * 140, 350, 0.4)
        sheet.append(name)
    sc.put("action", text("sheet-label", "walk-sheet.png · 4 frames", 560, 1290, 22, MUTED, MONO))
    sc.fade("sheet-label", t0 + 4200, dur=300)
    how(sc, "action", [op_spans([("type", "pixel-art"), ("rows", "[..kk.., ..]")]),
                       op_spans([("type", "keyframe"), ("property", "visible"), ("time", 150)]),
                       [("$ vixl export-animation --out walk.gif", WHITE)]], 1350, t0 + 900, size=24, stagger=1200)
    why(sc, [("Game art ", None), ("in minutes.", SKY)], [
        ("Crisp at any scale", "Pixel art stays on its grid; scale it up 30 times and every edge is sharp."),
        ("Readable source", "The sprite is rows of letters an agent can write, diff and recolour."),
        ("Ready for the engine", "Walk cycles export as GIF, APNG and sprite sheets with JSON frame data.")])
    endcard(sc, [("Pixels, ", None), ("in motion.", SKY)], "Sprites, tiles, walk cycles and sheets.")
    return sc


# ----------------------------------------------------------------------------------------------- 9
def s09_forms():
    sc = Short(9, "forms", "Fillable forms", standard(11600))
    frame(sc)
    hook(sc, "A sign-up form as a PDF.", "People print it, scribble on it, scan it back. Half the emails bounce.",
         [("Forms people ", None), ("can fill in.", SKY)])
    t0, t1 = sc.sections["action"]
    tag(sc, "action", "IN ACTION", t0)
    headline(sc, "action", [("Real fields, ", None), ("with validation built in.", SKY)], t0 + 100)
    x0, y0, w0 = GUTTER, 440, W - 2 * GUTTER
    sc.put("action", rect("paper", x0, y0, w0, 780, PAPER, 22), shadow("paper", 50, 22, 0.5))
    sc.put("action", text("form-title", "Workshop sign-up", x0 + 50, y0 + 44, 46, INK, HEAD))
    box = {"style": "box", "fill": "#FFFFFF", "stroke": "#C3C9D6", "stroke_width": 2, "radius": 8}
    fw = w0 - 100
    fields = [("name", "text", "Full name", x0 + 50, y0 + 170, fw, 64, {}),
              ("email", "text", "Email", x0 + 50, y0 + 290, fw, 64, {"format": "email"}),
              ("date", "date", "Date", x0 + 50, y0 + 410, fw / 2 - 20, 64, {}),
              ("size", "dropdown", "T-shirt", x0 + 50 + fw / 2 + 20, y0 + 410, fw / 2 - 20, 64,
               {"options": ["S", "M", "L", "XL"]})]
    form = ["paper", "form-title"]
    for key, kind, label, x, y, w, h, extra in fields:
        sc.put("action", text(f"lbl-{key}", label, x, y - 38, 24, "#5A6377", SEMI),
               {"type": "field", "kind": kind, "name": f"f-{key}", "key": key, "label": label, "x": x, "y": y,
                "width": round(w), "height": h, "appearance": box, **extra})
        form += [f"lbl-{key}", f"f-{key}"]
    sc.put("action", {"type": "field", "kind": "checkbox", "name": "f-slides", "key": "slides",
                      "label": "Send me the slides", "x": x0 + 50, "y": y0 + 520, "width": 44, "height": 44,
                      "appearance": {**box, "mark": "check"}},
           text("lbl-slides", "Send me the slides", x0 + 112, y0 + 527, 28, INK, BODY),
           {"type": "field", "kind": "signature", "name": "f-sig", "key": "signature", "label": "Signature",
            "x": x0 + 50, "y": y0 + 620, "width": fw, "height": 100, "required": True,
            "appearance": {"style": "underline", "stroke": "#8A93A6", "stroke_width": 2}},
           text("lbl-sig", "Signature *", x0 + 50, y0 + 728, 22, "#5A6377", SEMI))
    form += ["f-slides", "lbl-slides", "f-sig", "lbl-sig"]
    sc.put("action", group("form", form))
    sc.pop("form", t0 + 200, 600, 0.9)
    values = [("v-name", "Ada Okafor", x0 + 68, y0 + 186, t0 + 1000),
              ("v-date", "14 / 11 / 2026", x0 + 68, y0 + 426, t0 + 4200),
              ("v-size", "M", x0 + 68 + fw / 2 + 20, y0 + 426, t0 + 4700)]
    for name, value, x, y, t in values:
        sc.put("action", text(name, value, x, y, 30, INK, BODY))
        sc.words(name, t, "typewriter", "char", 400 if len(value) > 2 else 120)
    sc.put("action", text("v-email", "ada@northwind", x0 + 68, y0 + 306, 30, INK, BODY))
    sc.words("v-email", t0 + 1700, "typewriter", "char", 450)
    t_bad, t_ok = t0 + 2400, t0 + 3500
    sc.key("v-email", "text", 0, "ada@northwind")
    sc.key("v-email", "text", t_ok, "ada@northwind.press", "hold")
    sc.put("action", rect("email-bad", x0 + 48, y0 + 288, fw + 4, 68, "transparent", 9, BAD, 3))
    sc.keys("email-bad", "opacity", [(0, 0), (t_bad, 0), (t_bad + 150, 1), (t_ok, 1), (t_ok + 100, 0)])
    sc.put("action", text("email-msg", "Enter a valid email address", x0 + w0 - 420, y0 + 254, 22, BAD, SEMI))
    sc.keys("email-msg", "opacity", [(0, 0), (t_bad, 0), (t_bad + 150, 1), (t_ok, 1), (t_ok + 100, 0)])
    sc.put("action", text("email-ok", "✓", x0 + w0 - 90, y0 + 298, 40, GOOD, HEAD))
    sc.pop("email-ok", t_ok + 100, 300, 0.3)
    sc.put("action", {"type": "pen", "name": "tick", "points": [[x0 + 60, y0 + 543], [x0 + 70, y0 + 555],
                                                                 [x0 + 86, y0 + 530]],
                      "closed": False, "smooth": False, "fill": "none", "stroke": INK, "stroke_width": 5})
    sc.pop("tick", t0 + 5100, 250, 0.3)
    sig = [[90, 700], [110, 655], [128, 700], [150, 660], [172, 696], [205, 672], [236, 690], [268, 660],
           [290, 694], [340, 678]]
    sc.put("action", {"type": "pen", "name": "sig", "points": [[x0 + a, y0 + b] for a, b in sig], "closed": False,
                      "smooth": True, "fill": "none", "stroke": "#1E3A8A", "stroke_width": 4})
    sc.keys("sig", "trim_end", [(0, 0), (t0 + 5400, 0), (t0 + 6100, 100)], "ease-in-out")
    how(sc, "action", [op_spans([("type", "field"), ("kind", "text"), ("format", "email")]),
                       [("$ vixl export form.pdf --fillable", WHITE)]], 1270, t0 + 800, size=25, stagger=1500)
    sc.put("action", chip("fields", "text · email · date · dropdown · checkbox · signature", GUTTER, 1500, size=24,
                          fg=WHITE, bg="#3575EED9", font=MONO, width=W - 2 * GUTTER))
    sc.pop("fields", t0 + 6500, 400, 0.9)
    why(sc, [("Paperwork, ", None), ("minus the paper.", SKY)], [
        ("Real AcroForm fields", "Opens in any PDF reader: tab order, required marks and dropdowns work."),
        ("Validation built in", "Email and date rules catch typos while the form is being filled in."),
        ("Fill it from data", "Pass values and Vixl fills the form for you, one PDF per row if you like.")])
    endcard(sc, [("Forms that ", None), ("just work.", SKY)], "Sign-ups, invoices, applications and waivers.")
    return sc


# ----------------------------------------------------------------------------------------------- 10
LANES = [("kick", CORAL), ("snare", GOLD), ("bass", BLUE), ("keys", SKY), ("bells", LILAC), ("whoosh", MINT)]


def s10_motion():
    import score

    sec = standard(11800)
    sc = Short(10, "motion", "Motion and sound", sec)
    total = sc.duration
    frame(sc)
    hook(sc, "Video is its own app.", "Export the design, open an editor, find music, start again for every change.",
         [("Animate it ", None), ("in the document.", SKY)])
    t0, t1 = sc.sections["action"]
    tag(sc, "action", "IN ACTION", t0)
    headline(sc, "action", [("This short is a ", None), ("Vixl document.", SKY)], t0 + 100)
    # The timeline of this very short: its sections as clips, the playhead where the frame actually is.
    px, py, pw = GUTTER, 430, W - 2 * GUTTER
    sc.put("action", panel("tl", px, py, pw, 400))
    sc.put("action", text("tl-title", f"{sc.name}.vixl · timeline · {total / 1000:g} s", px + 34, py + 24, 22, MUTED,
                          MONO))
    sc.fade("tl", t0 + 100, dur=300)
    sc.fade("tl-title", t0 + 200, dur=300)
    rx, rw = px + 170, pw - 200
    colours = {"hook": CORAL, "action": BLUE, "why": GOLD, "end": MINT}
    for i, (name, (a, b)) in enumerate(sec.items()):
        y = py + 80 + i * 74
        sc.put("action", text(f"tl-{name}", name, px + 34, y + 12, 26, colours[name], MONO),
               rect(f"tl-{name}-clip", rx + a / total * rw, y, (b - a) / total * rw - 4, 52, f"{colours[name]}55", 10,
                    colours[name], 2))
        for k in range(5):
            kx = rx + (a + (b - a) * (k + 0.5) / 5) / total * rw
            sc.put("action", {"type": "shape", "shape": "polygon", "sides": 4, "name": f"tl-{name}-k{k}",
                              "x": round(kx - 9), "y": y + 17, "width": 18, "height": 18, "fill": WHITE})
        for n in (f"tl-{name}", f"tl-{name}-clip") + tuple(f"tl-{name}-k{k}" for k in range(5)):
            sc.fade(n, t0 + 400 + i * 150, dur=300)
    # The score of this short as a piano roll.
    ry = py + 440
    sc.put("action", panel("roll", px, ry, pw, 430))
    sc.put("action", text("roll-title", "score.vixl · audio-track × 8 · synthesized", px + 34, ry + 24, 22, MUTED,
                          MONO))
    sc.fade("roll", t0 + 900, dur=300)
    sc.fade("roll-title", t0 + 1000, dur=300)
    by_name = {op["name"]: op for op in score.tracks(sc)}
    lane_h = 55
    for i, (lane, colour) in enumerate(LANES):
        notes = by_name[lane]["notes"]
        ly = ry + 70 + i * lane_h
        sc.put("action", text(f"lane{i}", lane, px + 34, ly + 12, 22, colour, MONO))
        lo, hi = min(n["midi"] for n in notes), max(n["midi"] for n in notes)
        names = []
        for j, n in enumerate(notes):
            y = ly + 6 + (1 - (n["midi"] - lo) / max(1, hi - lo)) * (lane_h - 22)
            name = f"n{i}-{j}"
            sc.add(rect(name, rx + n["start"] / total * rw, y, max(3, n["duration"] / total * rw), 7, colour, 2))
            names.append(name)
        sc.put("action", group(f"lane{i}-notes", names))
        sc.fade(f"lane{i}", t0 + 1100 + i * 100, dur=250)
        sc.fade(f"lane{i}-notes", t0 + 1150 + i * 100, dur=300)
    for name, top, height in (("ph-tl", py + 70, 310), ("ph-roll", ry + 60, 350)):
        sc.put("action", rect(name, rx, top, 4, height, WHITE, 2))
        sc.keys(name, "translate-x", [(0, 0), (total, rw)], "linear")
        sc.fade(name, t0 + 1500, dur=300)
    how(sc, "action", [op_spans([("type", "keyframe"), ("property", "scale"), ("time", 1800)]),
                       op_spans([("type", "audio-track"), ("synth", "bell"), ("notes", "[…]")]),
                       [("$ vixl workflow film-export", WHITE)]], 1330, t0 + 2400, size=24, stagger=1200)
    why(sc, [("Design and motion, ", None), ("one file.", SKY)], [
        ("Keyframes on any property", "Position, colour, text and visibility, with easing, recipes and text animation."),
        ("Sound from notes", "A synthesizer writes the score as audio tracks you can edit like any layer."),
        ("Every format out", "MP4, WebM, GIF, WebP and APNG, rendered from the same master.")])
    endcard(sc, [("Make it ", None), ("move.", SKY)], "Loops, launches, lyric videos and films.")
    return sc


SHORTS = [s01_layers, s02_check, s03_sizes, s04_print, s05_sketch, s06_diagram, s07_chart, s08_pixel, s09_forms,
          s10_motion]
