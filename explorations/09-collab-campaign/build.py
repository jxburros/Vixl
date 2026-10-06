"""Exploration 09 — a multi-format bike-share launch campaign built by collaborating "agents".

Run from the repository root:

    python explorations/09-collab-campaign/build.py

Everything is written into explorations/09-collab-campaign/output/ (wiped at start).
The simulated team:

* illustration-agent — draws the neutral hero illustration and the logo badge with Vixl itself
* art-director      — writes brand.json v0, rolls six directions with `vixl roll`, renders a
                      contact sheet, picks one, re-rolls with --lock, then writes brand.json v1
* layout-agent      — applies principled layouts (every slot filled) to seven named sizes,
                      plus artboards and adapt-layout
* copy-agent /      — fork the master, make independent and deliberately conflicting edits;
  design-agent        the art director previews merges, resolves conflicts explicitly and
                      merges with expected_head
* producer          — group-defines the campaign across all size documents, pushes a shared
                      headline + accent swatch through group-apply gated by suites, checks,
                      reviews notes and history, exports finals and the overview sheet
"""

import base64
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
WS = OUT / "workspace"  # the shared agent workspace (brand.json, .vixl documents, groups, branches)
FINAL = OUT / "final"
REPORTS = OUT / "reports"
PREVIEW = OUT / "previews"

if OUT.exists():
    shutil.rmtree(OUT)
for d in (WS, FINAL, REPORTS, PREVIEW):
    d.mkdir(parents=True)

# Keep user-level resources inside this exploration so nothing leaks into ~/.config.
os.environ["VIXL_RESOURCES"] = str(WS / "user-resources.json")
os.environ["VIXL_NO_UPDATE"] = "1"

from vixl import Project  # noqa: E402  (import after env is set)
from vixl.interfaces import Session  # noqa: E402
from vixl.typefaces import pair_fonts  # noqa: E402
from vixl.workflows import dispatch  # noqa: E402
from vixl.errors import VixlError  # noqa: E402

SESSION = Session(workspace=WS)
LOG = []  # chronological record of what each agent did


def note(agent, what, **data):
    entry = {"agent": agent, "what": what, **data}
    LOG.append(entry)
    print(f"[{agent}] {what}", flush=True)
    return entry


def report(name, data):
    (REPORTS / name).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data


def vixl(*args, doc=None, check=True, parse=True):
    """Run the real `vixl` CLI inside the workspace (so brand.json applies) and parse JSON."""
    cmd = ["vixl", "--json"]
    if doc:
        cmd += ["-p", str(doc)]
    cmd += [str(a) for a in args]
    proc = subprocess.run(cmd, cwd=WS, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}\n{proc.stdout}\n{proc.stderr}")
    out = proc.stdout.strip() or proc.stderr.strip()
    if parse:
        try:
            return json.loads(out), proc.returncode
        except json.JSONDecodeError:
            return out, proc.returncode
    return out, proc.returncode


def wf(action, request, document=None):
    """Workflow dispatcher (same code path as `vixl workflow` / `vixl_workflow`)."""
    return dispatch(SESSION, action, request, document)


def close(doc):
    try:
        SESSION.close(doc)
    except VixlError:
        pass


def apply(doc, ops, **kw):
    return SESSION.apply(ops, document=doc, **kw)


def snap_centred_text(doc):
    """Workaround for a Vixl 0.20.0 bug: contrast cannot measure text whose box lands on a half
    pixel ("Could not measure 'cta': boolean index did not match ..."), which a suite reports as
    needs_review. Labels centred on a button with an odd size difference land there, so nudge
    their centre constraints by half a pixel onto whole pixels."""
    with SESSION.project(document=doc) as p:
        layers = p.inspect()["layers"]
    names = {l["id"]: l["name"] for l in layers}
    ops = []
    for layer in layers:
        cons = layer.get("constraints") or {}
        x, y = (layer.get("resolved_bounds") or [0, 0])[:2]
        if layer["type"] != "text" or (x == int(x) and y == int(y)) or not {"center-x", "center-y"} & set(cons):
            continue
        fixed = {}
        for axis, value in cons.items():
            ref, _, edge = value.partition(".")
            off = "+0.5" if axis in ("center-x", "center-y") and (x if axis == "center-x" else y) != int(
                x if axis == "center-x" else y) else ""
            fixed[axis] = f"{names.get(ref, ref)}.{edge}{off}"
        ops += [{"type": "unconstrain", "target": layer["name"]},
                {"type": "constrain", "target": layer["name"], "constraints": fixed}]
    if ops:
        apply(doc, ops)


def cli_apply(doc, ops):
    """`vixl -p DOC apply ops.json` — the CLI path accepts registered `font` names, which the
    Session/MCP/REST service boundary rejects (see README findings)."""
    tmp = WS / f".ops-{Path(doc).stem}.json"
    tmp.write_text(json.dumps({"operations": ops}), encoding="utf-8")
    try:
        out, _ = vixl("apply", tmp, doc=doc)
    finally:
        tmp.unlink()
    return out


def unique_names(ops):
    n = 0
    for op in ops:
        if "name" not in op:
            n += 1
            op["name"] = f"{op['type']}-{n}"
    return ops


# ---------------------------------------------------------------------------------------------
# Brief and copy deck
# ---------------------------------------------------------------------------------------------
BRIEF = {
    "client": "Loop — Riverside city bike share",
    "goal": "Launch 400 e-bikes at 60 docks on June 1; drive app installs.",
    "tone": "Friendly, civic, confident.",
}
COPY = {
    "title": "Ride the Loop",
    "subtitle": "400 bikes. 60 docks. One city.",
    "label": "Launching June 1",
    "cta": "Get the app",
    "body": "First 30 minutes free\nDocks every 400 m\nUnlock with your phone",
    "caption": "loopbikes.city",
    "items": "Bikes: 400\nDocks: 60\nFirst ride: Free",
}

INK, CREAM, MUTED, SURF = "#14213D", "#F6F1E7", "#4A5468", "#E9E1CF"


# ---------------------------------------------------------------------------------------------
# Phase 0 — illustration-agent: hero art and logo, drawn with Vixl
# ---------------------------------------------------------------------------------------------
def illustration(w=1200, h=1200, seed=7):
    import random

    rng = random.Random(seed)
    p = Project(w, h, INK)
    ops = [
        {"type": "shape", "shape": "ellipse", "name": "moon", "x": int(w * 0.56), "y": int(h * 0.10),
         "width": int(w * 0.34), "height": int(w * 0.34), "fill": SURF},
    ]
    x, i = 0, 0
    while x < w:
        bw, bh = rng.randint(60, 140), rng.randint(int(h * 0.18), int(h * 0.42))
        ops.append({"type": "shape", "shape": "rectangle", "name": f"tower-{i}", "x": x, "y": int(h * 0.62) - bh,
                    "width": bw, "height": bh + 10, "fill": "#2A3756"})
        x += bw + rng.randint(0, 12)
        i += 1
    x, i = -20, 0
    while x < w:
        bw, bh = rng.randint(80, 170), rng.randint(int(h * 0.10), int(h * 0.28))
        top = int(h * 0.66) - bh
        ops.append({"type": "shape", "shape": "rectangle", "name": f"block-{i}", "x": x, "y": top,
                    "width": bw, "height": bh + 10, "fill": MUTED})
        for wy in range(top + 20, int(h * 0.66) - 10, 34):
            for wx in range(x + 14, x + bw - 20, 30):
                if rng.random() < 0.45:
                    ops.append({"type": "shape", "shape": "rectangle", "x": wx, "y": wy, "width": 12, "height": 16,
                                "fill": SURF})
        x += bw + rng.randint(6, 20)
        i += 1
    ops.append({"type": "shape", "shape": "rectangle", "name": "street", "x": 0, "y": int(h * 0.66), "width": w,
                "height": h - int(h * 0.66), "fill": "#0E172C"})
    for k in range(0, w, 120):
        ops.append({"type": "shape", "shape": "rectangle", "x": k, "y": int(h * 0.86), "width": 60, "height": 8,
                    "fill": MUTED})
    r, cy, lx, rx = int(w * 0.15), int(h * 0.80), int(w * 0.30), int(w * 0.72)
    for nm, cx in (("wheel-rear", lx), ("wheel-front", rx)):
        ops.append({"type": "shape", "shape": "ellipse", "name": nm, "x": cx - r, "y": cy - r, "width": 2 * r,
                    "height": 2 * r, "fill": "transparent", "stroke": CREAM, "stroke_width": 18})
        ops.append({"type": "shape", "shape": "ellipse", "x": cx - 14, "y": cy - 14, "width": 28, "height": 28,
                    "fill": CREAM})
    bb, seat, head = (int(w * 0.48), cy), (int(w * 0.42), int(cy - r * 1.35)), (int(w * 0.66), int(cy - r * 1.45))
    line = {"type": "pen", "smooth": False, "stroke": CREAM, "stroke_width": 16, "fill": "transparent"}
    ops += [
        {**line, "name": "stays", "points": [[lx, cy], list(bb), list(seat), [lx, cy]]},
        {**line, "name": "top-tube", "points": [list(seat), list(head), list(bb)]},
        {**line, "name": "fork", "points": [list(head), [rx, cy]]},
        {**line, "name": "bars", "points": [list(head), [head[0] - 10, head[1] - 60], [head[0] + 60, head[1] - 80]],
         "stroke_width": 14},
        {"type": "shape", "shape": "capsule", "name": "saddle", "x": seat[0] - 60, "y": seat[1] - 40, "width": 120,
         "height": 30, "fill": CREAM},
        {"type": "shape", "shape": "ellipse", "name": "crank", "x": bb[0] - 30, "y": bb[1] - 30, "width": 60,
         "height": 60, "fill": "transparent", "stroke": CREAM, "stroke_width": 10},
    ]
    p.apply(unique_names(ops))
    return p


def logo_badge():
    """Round badge: orange disc, cream ring and 'loop' set in the brand heading face."""
    p = Project(240, 240, "transparent")
    pair_fonts(p, "work-sans-bitter")
    p.apply([
        {"type": "shape", "shape": "ellipse", "name": "disc", "x": 0, "y": 0, "width": 240, "height": 240,
         "fill": "#E04A1F"},
        {"type": "shape", "shape": "ellipse", "name": "ring", "x": 18, "y": 18, "width": 204, "height": 204,
         "fill": "transparent", "stroke": CREAM, "stroke_width": 8},
        {"type": "text", "name": "word", "text": "loop", "font": p.state["typography"]["heading"], "size": 78,
         "color": "#0A0F1E"},
        {"type": "align", "target": "word", "alignment": "center"},
    ])
    return p


def phase0():
    ill = illustration()
    ill.save(WS / "hero-illustration.vixl")
    ill.export(WS / "hero-illustration.png")
    badge = logo_badge()
    badge.save(WS / "logo-badge.vixl")
    badge.export(WS / "logo-badge.png")
    note("illustration-agent", "drew hero-illustration.vixl and logo-badge.vixl with shapes and pen paths")


# ---------------------------------------------------------------------------------------------
# Phase 1 — art-director: brand v0, six rolls, contact sheet, pick + lock, brand v1
# ---------------------------------------------------------------------------------------------
LAYOUT_SLOTS = None


def layout_slots(name):
    global LAYOUT_SLOTS
    if LAYOUT_SLOTS is None:
        LAYOUT_SLOTS, _ = vixl("layouts")
        LAYOUT_SLOTS = LAYOUT_SLOTS["layouts"]
    return list(LAYOUT_SLOTS[name]["slots"])


def import_asset(doc, png, name):
    """Embed an image and return its asset id; the temporary layer is removed by the caller."""
    data = Path(png).read_bytes()
    return SESSION.import_image(data, name=name, document=doc)


COPY_BY_LAYOUT = {
    "big-number": {"title": "400", "label": "E-bikes on the street", "subtitle": "Docked across Riverside from June 1",
                   "body": "Loop Bike Share · loopbikes.city"},
    "quote-card": {"title": "The whole city, ten minutes away.", "subtitle": "Loop Bike Share · June 1"},
    "bento-grid": {"label": "400", "caption": "e-bikes"},
    "product-card": {"title": "Loop e-bike", "body": "First 30 minutes free", "label": "New",
                     "caption": "Free first ride"},
    "thumbnail-bold": {"title": "RIDE THE LOOP", "label": "June 1"},
    "event-poster": {"label": "June 1 · 9 AM", "body": "Riverside Plaza launch ride\nFree helmets and coffee\nFirst 30 minutes free"},
    "framed": {"title": "Loop Bike Share", "subtitle": "400 bikes for one city", "body": "June 1", "label": "Launch",
               "caption": "loopbikes.city"},
}


def copy_for(layout):
    return {**COPY, **COPY_BY_LAYOUT.get(layout, {})}


def write_brand(version, **extra):
    logo = base64.b64encode((WS / "logo-badge.png").read_bytes()).decode()
    brand = {
        "name": "Loop Bike Share",
        "minimum_contrast": 4.5,
        "required_elements": ["logo"],
        "logos": [{"name": "logo", "data_base64": logo, "x": 40, "y": 40}],
        **extra,
    }
    (WS / "brand.json").write_text(json.dumps(brand, indent=2), encoding="utf-8")
    shown = {**brand, "logos": [{**brand["logos"][0], "data_base64": f"<{len(logo)} base64 chars>"}]}
    report(f"brand-{version}.json", shown)
    return brand


def apply_all_slots(doc, args, layout, *, image=True):
    """Run a `vixl ... --set` command with every content slot; on unused_slot keep only the used ones.

    `vixl layout show` lists slots per layout, but which ones are read depends on the canvas, so
    we offer everything and let the structured `unused_slot` error tell us what to drop.
    """
    sets = copy_for(layout)
    if image:
        sets["image"] = import_asset(doc, WS / "hero-illustration.png", "hero-src")["asset"]
    dropped = []
    for _ in range(4):
        cmd = list(args)
        for k, v in sets.items():
            cmd += ["--set", f"{k}={v}"]
        out, code = vixl(*cmd, doc=doc, check=False)
        if code == 0:
            break
        err = out if isinstance(out, dict) else {}
        if err.get("error") != "unused_slot":
            raise RuntimeError(out)
        dropped += [k for k in sets if k not in err.get("suggestions", [])]
        sets = {k: v for k, v in sets.items() if k in err.get("suggestions", [])}
    else:
        raise RuntimeError(f"could not fill {layout} on {doc}")
    if image:
        apply(doc, [{"type": "remove", "target": "hero-src"}])
        close(doc)
    return out, sets, dropped


def roll_into(doc, seed, locks=(), purpose="social", mood="friendly"):
    """Preview with `vixl roll`, then commit with `vixl roll --apply`, every slot filled.

    The preview reads the document's canvas and brand, so it picks the same layout as `--apply`.
    """
    base = ["roll", "--for", purpose, "--mood", mood, "--seed", seed]
    for lock in locks:
        base += ["--lock", lock]
    preview, _ = vixl(*base, doc=doc)
    layout = preview["direction"]["layout"]
    applied, sets, dropped = apply_all_slots(doc, base + ["--apply"], layout)
    got = applied["applied"]["layout"]["name"]
    assert got == layout, (seed, layout, got)
    return applied, sets, dropped


ROLL_SEEDS = [11, 23, 42, 57, 64, 88]
LOCKED_SEEDS = [101, 202, 303, 404]


def phase1():
    write_brand("v0")
    note("art-director", "wrote brand.json v0: contrast floor 4.5, required logo, no palette/pairing yet")
    rolls = []
    for seed in ROLL_SEEDS:
        doc = f"roll-{seed}.vixl"
        vixl("new", "instagram-portrait", "-o", doc)
        direction, sets, dropped = roll_into(doc, seed)
        png = PREVIEW / f"roll-{seed}.png"
        vixl("render", "--out", png, doc=doc)
        d = direction["direction"]
        rolls.append({"seed": seed, "doc": doc, "png": png.name, **d, "slots": sorted(sets), "rejected_by_canvas": dropped,
                      "unfilled": direction["applied"].get("unfilled_slots", [])})
        note("art-director", f"roll seed {seed}: {d['layout']} / {d['pairing']} / {d['palette']} / {d['mode']}")
    report("rolls.json", rolls)
    contact_sheet(rolls, OUT / "01-contact-sheet.png", "LOOP · six rolled directions",
                  "vixl roll --for social --mood friendly --seed N  ·  instagram-portrait  ·  every slot filled")

    # The art director likes seed 11: Poppins/Lora + the ocean palette next to the orange badge,
    # but wants a light ground for print. Lock those choices and re-roll only the composition.
    locks = ["pairing=poppins-lora", "palette=ocean", "mode=light"]
    note("art-director", "picked seed 11; re-rolling compositions with --lock " + " --lock ".join(locks))
    locked = []
    for seed in LOCKED_SEEDS:
        doc = f"locked-{seed}.vixl"
        vixl("new", "instagram-portrait", "-o", doc)
        direction, sets, dropped = roll_into(doc, seed, locks=locks)
        png = PREVIEW / f"locked-{seed}.png"
        vixl("render", "--out", png, doc=doc)
        d = direction["direction"]
        locked.append({"seed": seed, "doc": doc, "png": png.name, **d, "slots": sorted(sets),
                       "swatches": direction["applied"]["changes"].get("swatches")})
        note("art-director", f"locked re-roll {seed}: {d['layout']} / {d['type_scale']} / {d['accent']}")
    report("locked-rolls.json", locked)
    contact_sheet(locked, OUT / "02-locked-rerolls.png", "LOOP · locked re-rolls",
                  "--lock pairing=poppins-lora --lock palette=ocean --lock mode=light", cols=4)
    return rolls, locked


def contact_sheet(rolls, path, title, subtitle, cols=3, cell=(432, 540), pad=36, header=150):
    """Compose a captioned contact sheet as a Vixl document (frames + text)."""
    rows = (len(rolls) + cols - 1) // cols
    W = cols * cell[0] + (cols + 1) * pad
    H = header + rows * (cell[1] + 92) + pad
    sheet = Project(W, H, "#101522")
    pair_fonts(sheet, "work-sans-bitter")
    typo = sheet.state["typography"]
    ops = [
        {"type": "text", "name": "sheet-title", "text": title, "font": typo["heading"],
         "size": 54, "color": CREAM, "x": pad, "y": 38},
        {"type": "text", "name": "sheet-sub", "text": subtitle,
         "font": typo["body"], "size": 22, "color": "#9AA3B5", "x": pad, "y": 104},
    ]
    for i, r in enumerate(rolls):
        cx = pad + (i % cols) * (cell[0] + pad)
        cy = header + (i // cols) * (cell[1] + 92)
        asset = sheet.apply({"type": "add", "path": str(PREVIEW / r["png"]), "name": f"cell-{i}"})
        ops_cell = [
            {"type": "resize", "target": f"cell-{i}", "width": cell[0], "height": cell[1]},
            {"type": "move", "target": f"cell-{i}", "x": cx, "y": cy},
            {"type": "text", "name": f"cap-{i}", "text": f"seed {r['seed']} · {r['layout']}",
             "font": typo["heading"], "size": 24, "color": CREAM, "x": cx, "y": cy + cell[1] + 14},
            {"type": "text", "name": f"cap2-{i}", "text": f"{r['pairing']} · {r['palette'] if isinstance(r['palette'], str) else 'brand'} · {r['mode']}",
             "font": typo["body"], "size": 19, "color": "#9AA3B5", "x": cx, "y": cy + cell[1] + 50},
        ]
        sheet.apply(ops_cell)
    sheet.apply(ops)
    sheet.save(WS / "contact-sheet.vixl")
    sheet.export(path)
    return path


# ---------------------------------------------------------------------------------------------
# Phase 2 — layout-agent: brand v1 and seven named sizes, every slot filled
# ---------------------------------------------------------------------------------------------
# name -> (named size, extra `vixl new` flags, layout, layout seed)
SIZES = {
    "ig-portrait": ("instagram-portrait", [], "golden-section", None),  # master: from the locked roll
    "ig-story": ("instagram-story", [], "story-vertical", 7),
    "yt-thumb": ("youtube-thumbnail", [], "thumbnail-bold", 3),
    "yt-banner": ("youtube-banner", [], "banner", 5),
    "leaderboard": ("leaderboard", [], "banner", 2),
    "med-rect": ("medium-rectangle", [], "hero-statement", 4),
    "flyer": ("letter", ["--bleed"], "event-poster", 9),
}
MASTER = "ig-portrait.vixl"


def phase2(locked):
    pick = next(r for r in locked if r["seed"] == 101)
    brand = write_brand("v1", palette=pick["swatches"], pairing="poppins-lora")
    note("art-director", "wrote brand.json v1: ocean/light roles from locked roll 101 + poppins-lora", palette=brand["palette"])
    made = {}
    for key, (size, flags, layout, seed) in SIZES.items():
        doc = f"{key}.vixl"
        vixl("new", size, *flags, "-o", doc)
        wants_image = "image" in layout_slots(layout)
        if seed is None:  # master: replay the chosen roll, now constrained by brand v1
            args = ["roll", "--for", "social", "--mood", "friendly", "--seed", 101, "--lock", "layout=golden-section",
                    "--lock", "mode=light", "--apply"]
        else:
            args = ["layout", "apply", layout, "--seed", seed]
        out, sets, dropped = apply_all_slots(doc, args, layout, image=wants_image)
        made[key] = {"doc": doc, "size": size, "layout": layout, "slots": sorted(sets), "dropped": dropped}
        note("layout-agent", f"{doc}: {size} + {layout}, slots {sorted(sets)}")
    report("sizes.json", made)
    return made


def hero_asset(doc):
    info = import_asset(doc, WS / "hero-illustration.png", "hero-src")
    return info["asset"]


def polish(sizes):
    """layout-agent refinement: logo placement per canvas, extra artwork, centre safe zones."""
    for key in SIZES:
        doc = f"{key}.vixl"
        with SESSION.project(document=doc) as p:
            heading = p.state["typography"]["heading"]
            body = p.state["typography"]["body"]
        logo = lambda x, y, s: [{"type": "resize", "target": "logo", "width": s, "height": s},
                                {"type": "move", "target": "logo", "x": x, "y": y}]
        ops = []
        if key == "ig-portrait":
            ops = logo(60, 60, 132) + [
                {"type": "text", "name": "stat", "text": "400", "font": heading, "size": 170, "color": "@accent",
                 "x": 700, "y": 1010},
                {"type": "text", "name": "stat-caption", "text": "e-bikes · 60 docks", "font": body, "size": 26,
                 "color": "@muted", "x": 708, "y": 1190},
            ]
        elif key == "ig-story":
            ops = logo(668, 1560, 140)
        elif key == "yt-thumb":
            ops = logo(1090, 530, 150) + [
                {"type": "text-set", "target": "cta", "size": 36},
                {"type": "resize", "target": "cta-button", "width": 200, "height": 76},
                {"type": "constrain", "target": "cta", "constraints": {"center-x": "cta-button.center-x",
                                                                        "center-y": "cta-button.center-y"}},
            ]
        elif key == "yt-banner":
            asset = hero_asset(doc)
            ops = [
                {"type": "remove", "target": "hero-src"},
                {"type": "frame", "name": "hero-right", "asset": asset, "x": 2100, "y": 0, "width": 460,
                 "height": 1440, "fit": "fill"},
                {"type": "frame", "name": "hero-left", "asset": asset, "x": 0, "y": 0, "width": 460,
                 "height": 1440, "fit": "fill"},
                {"type": "fit-text", "target": "headline", "width": 960, "height": 150, "minimum": 60, "maximum": 126},
                {"type": "fit-text", "target": "subtitle", "width": 960, "height": 50, "minimum": 28, "maximum": 40},
                {"type": "move", "target": "headline", "x": 760, "y": 560},
                {"type": "move", "target": "subtitle", "x": 764, "y": 735},
                {"type": "move", "target": "cta-button", "x": 1740, "y": 610},
                {"type": "move", "target": "cta", "x": 1781, "y": 632},
            ] + logo(560, 560, 170) + [{"type": "top", "target": "logo"}]
        elif key == "leaderboard":
            ops = logo(10, 10, 70) + [
                {"type": "move", "target": "headline", "x": 96, "y": 24},
                {"type": "move", "target": "subtitle", "x": 96, "y": 53},
            ]
        elif key == "med-rect":
            # adapt-layout only moves its targets, so the logo must be part of the stack. First try
            # the stack as the layout made it: adapt-layout should refuse (it does not shrink copy).
            stack = ["logo", "label", "headline", "subtitle", "cta-group", "caption"]
            close(doc)
            cli_apply(doc, logo(10, 10, 30) + [
                {"type": "group", "targets": ["cta-button", "cta"], "name": "cta-group"},
                {"type": "hide", "target": "accent"},
            ])
            try:
                cli_apply(doc, [{"type": "adapt-layout", "targets": stack, "width": 300, "height": 250,
                                 "margin": 14, "gap": 6}])
                refused = None
            except RuntimeError as exc:
                refused = str(exc).split("\n", 1)[1].strip()
            note("layout-agent", "adapt-layout on the untouched med-rect stack", refused=refused)
            report("adapt-layout-refusal.json", {"request": stack, "result": refused})
            ops = [{"type": "text-set", "target": t, "align": "left"} for t in ("label", "headline", "subtitle", "caption")] + [
                {"type": "text-set", "target": "label", "color": "@ink"},
                {"type": "text-set", "target": "caption", "color": "@ink"},
                # fit-text, not text-set size: these sit in fixed text boxes (see README findings)
                {"type": "fit-text", "target": "label", "width": 272, "height": 14, "minimum": 9, "maximum": 10},
                {"type": "fit-text", "target": "caption", "width": 272, "height": 14, "minimum": 9, "maximum": 10},
                {"type": "fit-text", "target": "headline", "width": 272, "height": 44, "minimum": 24, "maximum": 33},
                {"type": "fit-text", "target": "subtitle", "width": 272, "height": 20, "minimum": 10, "maximum": 13},
                {"type": "adapt-layout", "targets": stack, "width": 300, "height": 250, "margin": 14, "gap": 6},
                {"type": "frame", "name": "hero-strip", "asset": hero_asset(doc), "x": 0, "y": 186, "width": 300,
                 "height": 64, "fit": "fill"},
                {"type": "remove", "target": "hero-src"},
            ]
        elif key == "flyer":
            asset = hero_asset(doc)
            ops = [
                {"type": "remove", "target": "hero-src"},
                {"type": "frame", "name": "hero", "asset": asset, "x": 131, "y": 480, "width": 2364, "height": 1440,
                 "fit": "fill"},
            ] + logo(2195, 110, 300)
        close(doc)
        cli_apply(doc, ops)
        note("layout-agent", f"polished {doc} ({len(ops)} ops)")


def artboards():
    """Leaderboard doc grows two artboards; constraints keep the row aligned on every board."""
    doc = "leaderboard.vixl"
    ops = [
        {"type": "constrain", "target": "logo", "constraints": {"left": "canvas.left+10", "center-y": "canvas.center-y"}},
        {"type": "constrain", "target": "headline", "constraints": {"left": "logo.right+16", "bottom": "canvas.center-y+2"}},
        {"type": "constrain", "target": "subtitle", "constraints": {"left": "logo.right+16", "top": "canvas.center-y+8"}},
        {"type": "constrain", "target": "cta-button", "constraints": {"right": "canvas.right-11", "center-y": "canvas.center-y"}},
        {"type": "constrain", "target": "cta", "constraints": {"center-x": "cta-button.center-x", "center-y": "cta-button.center-y"}},
        {"type": "artboard", "name": "large-leaderboard", "width": 970, "height": 90, "background": "@background"},
        {"type": "artboard", "name": "billboard", "preset": "billboard", "background": "@background"},
    ]
    cli_apply(doc, ops)
    boards = []
    for board in ("large-leaderboard", "billboard"):
        out = PREVIEW / f"artboard-{board}.png"
        vixl("render", "--artboard", board, "--out", out, doc=doc)
        chk, _ = vixl("check", "--artboard", board, doc=doc, check=False)
        boards.append({"board": board, "png": out.name, "check": chk})
    note("layout-agent", "added artboards large-leaderboard + billboard to leaderboard.vixl")
    report("artboards.json", boards)
    return boards


# ---------------------------------------------------------------------------------------------
# Phase 3 — collaboration: fork, conflicting edits, previews, explicit resolutions, guarded merge
# ---------------------------------------------------------------------------------------------
def layer_id(doc, name):
    with SESSION.project(document=doc) as p:
        return next(l["id"] for l in p.state["layers"] if l["name"] == name)


def phase3():
    vixl("checkpoint", "layout-approved", doc=MASTER)
    note("art-director", "checkpoint layout-approved on the master")
    forks = {}
    for agent in ("copy-agent", "design-agent"):
        forks[agent] = wf("branch-fork", {"branch": agent, "output": f"{agent}.vixl", "author": agent},
                          document=MASTER)
        note(agent, f"forked {MASTER} -> {agent}.vixl")

    # copy-agent: words only
    apply("copy-agent.vixl", [
        {"type": "text-set", "target": "headline", "text": "Your city, on a Loop"},
        {"type": "text-set", "target": "label", "text": "LAUNCHING JUNE 1 · RIVERSIDE"},
        {"type": "text-set", "target": "body", "text": "400 e-bikes. 60 docks. First ride free."},
        {"type": "text-set", "target": "cta", "text": "Download Loop"},
    ])
    note("copy-agent", "rewrote headline, kicker, body and CTA")
    # design-agent: look — and, deliberately, also the headline words (house style: uppercase)
    apply("design-agent.vixl", [
        {"type": "text-set", "target": "headline", "text": "RIDE THE LOOP", "color": "@accent"},
        {"type": "text-set", "target": "stat", "color": "@ink"},
        {"type": "move", "target": "logo", "x": 888, "y": 60},
        {"type": "layer-style", "target": "cta-button", "name": "drop-shadow",
         "settings": {"blur": 10, "dy": 6, "opacity": 0.35}},
        {"type": "text-set", "target": "cta", "text": "GET THE APP"},
    ])
    note("design-agent", "uppercased + recoloured headline, moved logo, CTA shadow and CTA caps")
    # meanwhile the art director touches the master's kicker -> a three-way conflict for copy-agent
    apply(MASTER, [{"type": "text-set", "target": "label", "text": "LAUNCHING SATURDAY JUNE 1"}])
    close(MASTER)
    note("art-director", "edited the master kicker after the forks (creates a 3-way conflict)")

    merges = {}
    # --- copy-agent: preview, resolve the kicker in favour of the copywriter, merge with expected_head
    pre = wf("branch-merge", {"branch": "copy-agent"}, document=MASTER)
    merges["copy-agent.preview"] = pre
    note("art-director", f"preview copy-agent merge: {len(pre['conflicts'])} conflict(s)",
         paths=[c["path"] for c in pre["conflicts"]])
    res = {c["path"]: "theirs" for c in pre["conflicts"]}
    pre2 = wf("branch-merge", {"branch": "copy-agent", "resolutions": res}, document=MASTER)
    merges["copy-agent.resolved-preview"] = {k: v for k, v in pre2.items() if k != "changes"}
    done = wf("branch-merge", {"branch": "copy-agent", "resolutions": res, "dry_run": False,
                               "expected_head": pre2["source_head"]}, document=MASTER)
    merges["copy-agent.merge"] = {k: v for k, v in done.items() if k != "changes"}
    note("art-director", "merged copy-agent", resolutions=res)

    # --- design-agent: preview now conflicts with the merged copy
    pre = wf("branch-merge", {"branch": "design-agent"}, document=MASTER)
    merges["design-agent.preview"] = pre
    note("art-director", f"preview design-agent merge: {len(pre['conflicts'])} conflict(s)",
         paths=[c["path"] for c in pre["conflicts"]])
    # Words belong to copy (ours = master, which now holds the copy edits); styling to design.
    # The auto-sized CTA also reports its derived `width` as a separate conflict; it must follow the
    # same side as the text, otherwise the stored width disagrees with the words.
    res = {}
    for c in pre["conflicts"]:
        res[c["path"]] = "ours" if c["path"].rsplit("/", 1)[-1] in ("text", "width", "height") else "theirs"
    pre2 = wf("branch-merge", {"branch": "design-agent", "resolutions": res}, document=MASTER)
    stale_head = pre2["source_head"]
    # Somebody nudges the master between review and merge: expected_head must reject the merge.
    apply(MASTER, [{"type": "text-set", "target": "stat-caption", "text": "e-bikes · 60 docks · 1 city"}])
    close(MASTER)
    try:
        wf("branch-merge", {"branch": "design-agent", "resolutions": res, "dry_run": False,
                            "expected_head": stale_head}, document=MASTER)
        merges["design-agent.stale"] = "UNEXPECTED: merged with a stale head"
    except VixlError as exc:
        merges["design-agent.stale"] = {"error": exc.code, "message": str(exc)}
        note("art-director", f"stale expected_head rejected: {exc.code}")
    pre3 = wf("branch-merge", {"branch": "design-agent", "resolutions": res}, document=MASTER)
    done = wf("branch-merge", {"branch": "design-agent", "resolutions": res, "dry_run": False,
                               "expected_head": pre3["source_head"]}, document=MASTER)
    merges["design-agent.merge"] = {k: v for k, v in done.items() if k != "changes"}
    merges["design-agent.resolutions"] = res
    note("art-director", "merged design-agent", resolutions=res)
    merges["branches"] = wf("branch-list", {})
    report("merges.json", merges)
    close(MASTER)
    vixl("render", "--out", PREVIEW / "p3-master-merged.png", doc=MASTER)
    return merges


# ---------------------------------------------------------------------------------------------
# Phase 3b — review notes on the merged master, repair, resolve
# ---------------------------------------------------------------------------------------------
def phase3b():
    chk, _ = vixl("check", doc=MASTER, check=False)
    report("master-check-after-merge.json", chk)
    notes_added = []
    for text in (
        "Merged headline 'Your city, on a Loop' now runs into the 400 stat — move the stat down/right.",
        "CTA 'Download Loop' is wider than its button (check: cta contrast error where it spills). Resize the button.",
        "Stat caption reads well; keep '1 city'.",
    ):
        out, _ = vixl("notes", "add", text, doc=MASTER)
        notes_added.append(out["notes"][-1])
    note("art-director", f"review: master check after merge passed={chk['passed']}, added {len(notes_added)} notes")
    open_notes, _ = vixl("notes", "list", doc=MASTER)
    # layout-agent reads the notes before revising (vixl_review_notes / `vixl notes list`)
    with SESSION.project(document=MASTER) as p:
        cta = next(l for l in p.inspect()["layers"] if l["name"] == "cta")
    close(MASTER)
    pad = 31
    cli_apply(MASTER, [
        {"type": "text-set", "target": "stat", "size": 132},
        {"type": "move", "target": "stat", "x": 722, "y": 1092},
        {"type": "move", "target": "stat-caption", "x": 726, "y": 1238},
        {"type": "resize", "target": "cta-button", "width": cta["resolved_bounds"][2] + 2 * pad, "height": 63},
    ])
    chk2, _ = vixl("check", doc=MASTER, check=False)
    for n in notes_added[:2]:
        vixl("notes", "resolve", n["id"], doc=MASTER)
    final_notes, _ = vixl("notes", "list", doc=MASTER)
    report("review-notes.json", {"after_merge_check": {"passed": chk["passed"], "issues": chk["issues"]},
                                 "notes_opened": open_notes, "after_fix_check": {"passed": chk2["passed"], "issues": chk2["issues"]},
                                 "notes_final": final_notes})
    note("layout-agent", f"fixed review notes; master check passed={chk2['passed']}; resolved 2/3 notes")
    vixl("render", "--out", PREVIEW / "p3-master-repaired.png", doc=MASTER)


# ---------------------------------------------------------------------------------------------
# Phase 4 — producer: custom suites, campaign group, gated group-apply
# ---------------------------------------------------------------------------------------------
# Viewing width used for thumbnail legibility, per format (the default 320px suits feeds, not ads).
VIEW_WIDTH = {"ig-portrait": 540, "ig-story": 540, "yt-thumb": 640, "yt-banner": 1280, "leaderboard": 728,
              "med-rect": 300, "flyer": None}
YT_MOBILE = [[0, 0, 2560, 508], [0, 931, 2560, 509], [0, 0, 507, 1440], [2053, 0, 507, 1440]]
SUITES = ["loop-accessible", "loop-delivery", "loop-legible", "no-placeholders"]


def phase4():
    starters = wf("resource-list", {"kind": "suites"})
    wf("resource-save", {"kind": "suites", "name": "loop-accessible", "value": {
        "description": "Loop: WCAG text contrast (brand floor 4.5) and colour-vision safety.",
        "rules": [{"id": "contrast", "kind": "design", "options": {"checks": ["contrast", "color_vision"]}}]}})
    wf("resource-save", {"kind": "suites", "name": "loop-delivery", "value": {
        "description": "Loop: nothing cut off, no blanks, real fonts, brand policy, logo present and inside.",
        "rules": [
            {"id": "design", "kind": "design", "options": {"checks": ["bounds", "blanks", "fonts", "brand"]}},
            {"id": "logo", "kind": "assert", "expression": "layer.logo.bounds within canvas"},
            {"id": "logo-clear", "kind": "design", "options": {"checks": ["overlap"], "targets": ["logo", "headline"]}},
            {"id": "opaque", "kind": "alpha", "maximum": 0},
        ]}})
    note("producer", "saved workspace suites loop-accessible + loop-delivery",
         starters=[s_["name"] if isinstance(s_, dict) else s_ for s_ in starters.get("resources", starters.get("suites", []))]
         if isinstance(starters, dict) else starters)
    docs = [f"{k}.vixl" for k in SIZES]
    for key in SIZES:
        doc = f"{key}.vixl"
        snap_centred_text(doc)
        wf("suite-use", {"name": "loop-accessible"}, document=doc)
        wf("suite-use", {"name": "loop-delivery"}, document=doc)
        wf("suite-use", {"name": "no-placeholders"}, document=doc)
        legible = {"checks": ["legibility"]}
        if VIEW_WIDTH[key]:
            legible["thumbnail_width"] = VIEW_WIDTH[key]
        with SESSION.project(document=doc) as p:
            texts = [l["name"] for l in p.state["layers"] if l["type"] == "text" and l["name"] != "headline"]
        rules = [{"id": "legible", "kind": "design", "options": legible},
                 {"id": "headline-size", "kind": "text-fit", "target": "headline", "minimum": 18}]
        # every other text layer must fit too
        rules += [{"id": f"fit-{t}", "kind": "text-fit", "target": t, "minimum": 8} for t in texts]
        if key == "yt-banner":
            rules.append({"id": "mobile-safe", "kind": "design", "options": {
                "checks": ["safe_area"], "avoid": YT_MOBILE, "targets": ["headline", "subtitle", "cta", "logo"]}})
        ops = [{"type": "suite-set", "name": "loop-legible", "suite": {"rules": rules}},
               # bind the headline to a campaign variable so the group can drive it
               {"type": "variable", "name": "headline", "value": "Ride the Loop"},
               {"type": "variable", "name": "headline_caps", "value": "RIDE THE LOOP"}]
        apply(doc, ops)
        with SESSION.project(document=doc) as p:
            current = next(l["text"] for l in p.state["layers"] if l["name"] == "headline")
            hl = next(l for l in p.inspect()["layers"] if l["name"] == "headline")
        x, y, w, h = hl["resolved_bounds"]
        size = hl["size"]
        # Per-document action: refit the headline into the box the layout gave it.
        apply(doc, [{"type": "action-define", "name": "fit-headline", "action": {"operations": [
            {"type": "fit-text", "target": "headline", "width": w, "height": h,
             "minimum": max(12, int(size * 0.45)), "maximum": size}]}}])
        var = "${headline_caps}" if current.isupper() else "${headline}"
        value = current if current.isupper() else current
        apply(doc, [{"type": "variable", "name": "headline" if var == "${headline}" else "headline_caps", "value": value},
                    {"type": "text-set", "target": "headline", "text": var}])
        close(doc)
    note("producer", "attached 4 suites to every size; headline bound to ${headline}/${headline_caps}")

    group = wf("group-define", {"name": "loop-launch", "documents": docs, "shared": {
        "variables": {"headline": "Ride the Loop", "headline_caps": "RIDE THE LOOP"}}})
    attempts = []
    candidates = [
        ("pale accent", {"variables": {"headline": "Your city, on a Loop", "headline_caps": "YOUR CITY, ON A LOOP"},
                         "swatches": {"accent": "#7FC8D0", "accent-text": "#7FC8D0"}}),
        ("long headline", {"variables": {"headline": "Your whole city, ten minutes away, on a Loop",
                                         "headline_caps": "YOUR WHOLE CITY, TEN MINUTES AWAY"},
                           "swatches": {"accent": "#B83512", "accent-text": "#B83512"}}),
        ("final", {"variables": {"headline": "Your city, on a Loop", "headline_caps": "YOUR CITY, ON A LOOP"},
                   "swatches": {"accent": "#B83512", "accent-text": "#B83512"}}),
    ]
    published = None
    candidates.append(("final, flyer refit", candidates[-1][1]))
    for label, shared in candidates:
        if label == "final, flyer refit":
            # producer: the flyer headline must stop short of the logo; redefine its action box
            with SESSION.project(document="flyer.vixl") as p:
                lay = {l["name"]: l for l in p.inspect()["layers"]}
            hx, hy, hw, hh = lay["headline"]["resolved_bounds"]
            width = lay["logo"]["resolved_bounds"][0] - hx - 60
            apply("flyer.vixl", [{"type": "action-define", "name": "fit-headline", "action": {"operations": [
                {"type": "fit-text", "target": "headline", "width": width, "height": hh, "minimum": 90,
                 "maximum": lay["headline"]["size"]}]}}])
            close("flyer.vixl")
            note("producer", f"redefined flyer fit-headline box to {width}px so the headline clears the logo")
        if label == "final":  # (brand v2 is written once; the refit retry reuses it)
            # The brand itself moves to the warmer accent, so the brand check accepts it.
            brand = json.loads((WS / "brand.json").read_text())
            brand["palette"].update(shared["swatches"])
            write_brand("v2", palette=brand["palette"], pairing=brand["pairing"])
            note("art-director", "brand.json v2: accent + accent-text -> #B83512 (rust)")
        wf("group-define", {"name": "loop-launch", "documents": docs, "shared": shared})
        try:
            res = wf("group-apply", {"name": "loop-launch", "suites": SUITES, "dry_run": False,
                                     "operations": [{"type": "action-apply", "name": "fit-headline"}]})
            attempts.append({"attempt": label, "shared": shared, "published": True,
                             "documents": [{"document": r["document"],
                                            "checks": {SUITES[i]: c["status"] for i, c in enumerate(r["checks"])}}
                                           for r in res.get("report", [])]})
            published = label
            note("producer", f"group-apply '{label}': published to {len(docs)} documents")
            break
        except VixlError as exc:
            d = exc.details
            failed = [{"suite": SUITES[i], "status": c["status"],
                       "failures": [slim(r) for r in c["results"] if r["status"] != "passed"]}
                      for i, c in enumerate(d.get("checks", [])) if not c["passed"]]
            attempts.append({"attempt": label, "shared": shared, "published": False, "error": exc.code, "message": str(exc),
                             "blocked_by": d.get("document"), "failed_suites": failed})
            note("producer", f"group-apply '{label}' blocked by {d.get('document')}: {exc.code}")
    report("group-apply.json", {"group": wf("group-show", {"name": "loop-launch"}), "attempts": attempts})
    assert published, attempts
    return attempts


def slim(rule_result):
    """Keep a failing rule result readable: id, status and the first few issue messages."""
    out = {"id": rule_result["id"], "status": rule_result["status"]}
    issues = rule_result.get("issues") or (rule_result.get("actual") or {}).get("issues") if isinstance(
        rule_result.get("actual"), dict) or rule_result.get("issues") else None
    if issues:
        out["issues"] = [i.get("message") for i in issues][:5]
    else:
        out["detail"] = {k: v for k, v in rule_result.items() if k not in ("id", "status", "severity", "time")}
    return out


def run_suites(tag):
    table = {}
    for key in SIZES:
        doc = f"{key}.vixl"
        table[key] = {}
        for suite in SUITES:
            r = wf("check", {"suite": suite}, document=doc)
            table[key][suite] = r["status"]
        close(doc)
    report(f"suites-{tag}.json", table)
    return table


# ---------------------------------------------------------------------------------------------
# Phase 5 — history on the master: checkpoints, undo/redo, an in-document branch, compare
# ---------------------------------------------------------------------------------------------
def stat_size():
    with SESSION.project(document=MASTER) as p:
        size = next(l["size"] for l in p.state["layers"] if l["name"] == "stat")
    close(MASTER)
    return size


def phase5():
    h = {}
    vixl("checkpoint", "group-published", doc=MASTER)
    # undo / redo of a bad tweak
    cli_apply(MASTER, [{"type": "text-set", "target": "stat", "size": 300}])
    tweak, _ = vixl("check", doc=MASTER, check=False)
    h["tweak"] = {"stat_size": stat_size(), "check_passed": tweak["passed"],
                  "issues": [i["message"] for i in tweak["issues"] if i["severity"] == "error"]}
    vixl("undo", doc=MASTER)
    h["after_undo"] = stat_size()
    vixl("redo", doc=MASTER)
    h["after_redo"] = stat_size()
    vixl("undo", doc=MASTER)
    h["after_second_undo"] = stat_size()
    note("producer", f"undo/redo: stat {h['tweak']['stat_size']} -> {h['after_undo']} -> {h['after_redo']} -> {h['after_second_undo']}")
    # an in-document branch for a night edition
    vixl("branch", "night-edition", doc=MASTER)
    cli_apply(MASTER, [
        {"type": "swatch", "name": "background", "color": "#0B1B2B"},
        {"type": "swatch", "name": "surface", "color": "#16304A"},
        {"type": "swatch", "name": "ink", "color": "#EDF6F9"},
        {"type": "swatch", "name": "muted", "color": "#AFC3D0"},
        {"type": "swatch", "name": "accent", "color": "#E2572B"},
        {"type": "swatch", "name": "accent-text", "color": "#F4845F"},
        {"type": "swatch", "name": "on-accent", "color": "#0B1B2B"},
    ])
    vixl("checkpoint", "night-v1", doc=MASTER)
    night, _ = vixl("check", doc=MASTER, check=False)
    h["night_check"] = {"passed": night["passed"], "errors": [i["message"] for i in night["issues"] if i["severity"] == "error"]}
    vixl("export", OUT / "night-edition.png", doc=MASTER)
    vixl("checkout", "main", doc=MASTER)
    back, _ = vixl("check", doc=MASTER, check=False)
    h["back_on_main_check_passed"] = back["passed"]
    vixl("compare", "layout-approved", "group-published", "--out", PREVIEW / "compare-approved-vs-published.png",
         doc=MASTER)
    vixl("compare", "group-published", "night-v1", "--out", PREVIEW / "compare-day-vs-night.png", doc=MASTER)
    hist = SESSION.history(document=MASTER)
    close(MASTER)
    h["branches"] = hist["branches"]
    h["checkpoints"] = hist["checkpoints"]
    h["current_branch"] = hist["branch"]
    h["revisions"] = len(hist["nodes"])
    h["nodes"] = [{"id": n["id"], "label": n.get("label"),
                   "ops": [o.get("type") for o in (n.get("operations") or [])]} for n in hist["nodes"]]
    report("history.json", h)
    note("producer", f"history: {h['revisions']} revisions, branches {sorted(h['branches'])}, "
                     f"checkpoints {sorted(h['checkpoints'])}")
    return h


# ---------------------------------------------------------------------------------------------
# Phase 6 — final gate, exports and the overview sheet
# ---------------------------------------------------------------------------------------------
def phase6():
    table = run_suites("final")
    assert all(v == "passed" for row in table.values() for v in row.values()), table
    print_check, _ = vixl("check", "--checks", "print", "safe_area", doc="flyer.vixl", check=False)
    report("flyer-print-check.json", print_check)
    files = {}
    for key in SIZES:
        doc = f"{key}.vixl"
        out = FINAL / f"{key}.png"
        if key == "flyer":  # 2626x3376 at 300 dpi; a half-scale proof keeps the repo light
            vixl("export", out, "--scale", "0.5", doc=doc)
        else:
            vixl("export", out, doc=doc)
        files[key] = out
    for board in ("large-leaderboard", "billboard"):
        out = FINAL / f"leaderboard-artboard-{board}.png"
        vixl("export", out, "--artboard", board, doc="leaderboard.vixl")
        files[board] = out
    note("producer", f"exported {len(files)} finals; all 4 suites passed on all 7 sizes")
    overview(files)
    return files


def overview(files):
    W, H = 2400, 1990
    sheet = Project(W, H, "#0B1220")
    pair_fonts(sheet, "poppins-lora")
    typo = sheet.state["typography"]
    cells = [  # key, x, y, w, h, caption
        ("ig-portrait", 60, 200, 576, 720, "instagram-portrait · golden-section (master, merged)"),
        ("ig-story", 676, 200, 405, 720, "instagram-story · story-vertical"),
        ("flyer", 1121, 200, 560, 720, "letter + bleed · event-poster"),
        ("med-rect", 1721, 200, 600, 500, "medium-rectangle · hero-statement + adapt-layout"),
        ("yt-thumb", 60, 1040, 800, 450, "youtube-thumbnail · thumbnail-bold"),
        ("yt-banner", 900, 1040, 800, 450, "youtube-banner · banner (centre safe zone)"),
        ("leaderboard", 60, 1620, 1092, 135, "leaderboard · banner"),
        ("billboard", 1200, 1620, 970, 250, "billboard artboard of leaderboard.vixl"),
    ]
    ops = [
        {"type": "text", "name": "title", "text": "Loop — campaign overview", "font": typo["heading"], "size": 64,
         "color": "#EDF6F9", "x": 60, "y": 50},
        {"type": "text", "name": "sub", "text": "7 named sizes + 2 artboards · one group · 4 suites passed on every document"
                                                 " · headline and accent pushed with group-apply",
         "font": typo["body"], "size": 26, "color": "#AFC3D0", "x": 62, "y": 135},
    ]
    sheet.apply(ops)
    for i, (key, x, y, w, h, cap) in enumerate(cells):
        sheet.apply([
            {"type": "frame", "name": f"cell-{key}", "path": str(files[key]), "x": x, "y": y, "width": w,
             "height": h, "fit": "fit"},
            {"type": "text", "name": f"cap-{key}", "text": cap, "font": typo["body"], "size": 22,
             "color": "#AFC3D0", "x": x, "y": y + h + 14},
        ])
    sheet.save(WS / "overview.vixl")
    sheet.export(OUT / "00-overview.png")


def render_all(tag):
    for key in SIZES:
        vixl("render", "--out", PREVIEW / f"{tag}-{key}.png", doc=f"{key}.vixl")


if __name__ == "__main__":
    phase0()
    rolls, locked = phase1()
    if "--stop-after-rolls" in sys.argv:
        sys.exit(0)
    sizes = phase2(locked)
    polish(sizes)
    artboards()
    render_all("p2")
    if "--stop-after-sizes" in sys.argv:
        sys.exit(0)
    merges = phase3()
    phase3b()
    if "--stop-after-merge" in sys.argv:
        sys.exit(0)
    attempts = phase4()
    table = run_suites("after-group")
    print(json.dumps(table, indent=1))
    render_all("p4")
    if "--stop-after-group" in sys.argv:
        sys.exit(0)
    phase5()
    phase6()
    report("agent-log.json", LOG)
    # Keep the output small: exploratory roll documents and intermediate previews are summarised in
    # reports/ and the contact sheets; the campaign documents, forks and branch bases stay.
    for pattern in ("roll-*.vixl", "locked-*.vixl", "contact-sheet.vixl", "overview.vixl"):
        for f in WS.glob(pattern):
            f.unlink()
    for pattern in ("p2-*.png", "p4-*.png", "roll-*.png", "locked-*.png"):
        for f in PREVIEW.glob(pattern):
            f.unlink()
    # `vixl new -o` silently records an absolute per-directory default project; don't ship it.
    (WS / ".vixl-session.json").unlink(missing_ok=True)
    print("done")
