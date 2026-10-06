"""THE LAMPLIGHT FESTIVAL: a four-page A4 programme and a social set, built from Vixl 0.20.0
containers, use-case templates, hug stacks and seeded variety.

Run from the repo root:

    python explorations/14-festival-programme/build.py

The festival is the setting of 12-lamplighter-comic and 13-forty-three-film. All artwork in the
image slots is rendered here by Vixl: the comic's own scene functions draw the cover and product
photos, and three generated characters sit for their portrait photos. Nothing is imported.

* page 1: the print-flyer template (warm-editorial combination) with a filled photo slot. Palette
  roles are document-wide swatches, so one combination carries the whole booklet;
* page 2: section header, timeline steps, stats and hug-stack badge pills;
* page 3: profile containers in all three arrangements, circle-masked focal crops, a
  container-variant switch and a testimonial;
* page 4: pricing tiers (one resized and reflowed as the featured tier), product cards, a CTA and a
  hug-stack code window;
* social: the social-event-promo template in its three recommended palette/look combinations, and
  three seeded rolls of a link card, each with its seed and choices recorded.

Outputs go to explorations/14-festival-programme/output/.
"""

import json
import os
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "output"
os.environ.setdefault("VIXL_NO_UPDATE", "1")
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "src"))


from vixl import Project  # noqa: E402
from vixl.assets import add_image  # noqa: E402
from vixl.checks import check_design  # noqa: E402
from vixl.resources import TEMPLATES  # noqa: E402
from vixl.typefaces import install_font, roll_document  # noqa: E402

COMIC = runpy.run_path(str(ROOT / "explorations/12-lamplighter-comic/build.py"), run_name="comic")
W, H = 1240, 1754  # A4 at 150 dpi
M = 70
HEAD, BODY, MONO = "fraunces-700", "inter-400", "jetbrains-mono-500"
# The coffee palette's on-accent role measures 4.2:1 on its accent; small labels need 4.5:1.
BUTTON_INK = "#1E140C"
HEADING_SLOTS = {"title", "plan", "price", "value", "name"}


def fonts(p):
    install_font(p, "Fraunces", 700, role="heading")
    install_font(p, "Inter", 400, role="body")
    install_font(p, "Inter", 600)
    install_font(p, "JetBrains Mono", 500)


def art(p, image):
    return add_image(p, image)


def scene(name, w, h):
    project, _anchors = COMIC[name](w, h)
    return project.render()


def portrait(colors, background, seed_pose=0):
    """A head-and-shoulders 'photo' of a generated character on a lit backdrop."""
    p = Project(480, 480, background)
    p.apply([{"type": "gradient", "name": "backdrop", "width": 480, "height": 480, "direction": "radial",
              "stops": [{"offset": 0, "color": "#FFFFFF55"}, {"offset": 1, "color": "#00000000"}]},
             {"type": "character", "name": "sitter", "x": 110, "y": 70, "height": 760, "colors": colors},
             {"type": "character-pose", "target": "sitter", "angles": {"left-upper-arm": 10 + seed_pose}}],
            detail="brief")
    return p.render()


def restyle(p, prefix, page, button_ink=None):
    """Give every text layer in a container the document's heading or body face."""
    ops = []
    for layer in p.state["layers"]:
        if layer["type"] == "text" and layer["name"].startswith(prefix + "/"):
            slot = layer["name"].rsplit("/", 1)[1]
            op = {"type": "text", "target": layer["id"], "font": HEAD if slot in HEADING_SLOTS else BODY,
                  "page": page}
            if slot == "button" and button_ink:
                op["color"] = button_ink
            ops.append(op)
    if ops:
        p.apply(ops, detail="brief")


def pill(name, text, x, y, fg, bg, page, size=20):
    """A hug stack: the badge sizes itself to its label plus padding."""
    return [{"type": "text", "name": f"{name}-label", "text": text, "size": size, "font": "inter-600", "color": fg,
             "page": page},
            {"type": "stack", "name": name, "targets": [f"{name}-label"], "size": "hug", "background": bg,
             "radius": size, "padding": {"top": 6, "right": 16, "bottom": 8, "left": 16}, "page": page},
            {"type": "move", "target": name, "x": x, "y": y, "page": page}]


def code_window(name, lines, x, y, page):
    """Window chrome dots and code lines in nested hug stacks with a dark rounded background."""
    ops = []
    for i, color in enumerate(("#FF5F57", "#FEBC2E", "#28C840")):
        ops.append({"type": "shape", "shape": "ellipse", "name": f"{name}-dot-{i}", "width": 14, "height": 14,
                    "fill": color, "page": page})
    ops.append({"type": "stack", "name": f"{name}-chrome", "targets": [f"{name}-dot-{i}" for i in range(3)],
                "direction": "horizontal", "gap": 8, "size": "hug", "page": page})
    for i, (text, color) in enumerate(lines):
        ops.append({"type": "text", "name": f"{name}-line-{i}", "text": text, "font": MONO, "size": 19,
                    "color": color, "page": page})
    ops += [{"type": "stack", "name": name, "targets": [f"{name}-chrome", *[f"{name}-line-{i}" for i in
                                                                           range(len(lines))]],
             "direction": "vertical", "gap": 10, "size": "hug", "background": "#1B1E27", "radius": 14,
             "padding": {"top": 16, "right": 26, "bottom": 20, "left": 22}, "page": page},
            {"type": "move", "target": name, "x": x, "y": y, "page": page}]
    return ops


# Pages ---------------------------------------------------------------------------------------------------
def cover(p):
    page = "cover"
    p.apply({"type": "page", "action": "add", "name": page}, detail="brief")
    photo = art(p, scene("scene_dawn", 1120, 520))
    result = p.apply({"type": "template-apply", "name": "print-flyer", "seed": 7, "palette": "coffee",
                      "look": "paper", "mode": "light", "page": page, "variables": {
                          "slot-1": {"eyebrow": "PORT HALLORAN  ·  17–19 OCTOBER",
                                     "title": "The Lamplight Festival"},
                          "slot-2": {"photo": photo, "caption": "Forty-two gas lamps, lit by hand, one last time."},
                          "slot-3": {"title": "Three nights. One lighthouse.", "button": "Get a quay pass"}}},
                     detail="brief")
    for slot in ("slot-1", "slot-2", "slot-3"):
        restyle(p, slot, page, BUTTON_INK)
    p.apply([*pill("cover-free", "FREE ENTRY TO THE QUAY", M + 6, H - 90, "#3B2A1C", "#F6C453", page),
             *pill("cover-ages", "ALL AGES", M + 330, H - 90, "#FFFFFF", "#7A4E2D", page)], detail="brief")
    return result["template"]


PROGRAMME = [
    ("FRI 17 · 19:00", "The lamp walk", "Follow Wren along the quay as all forty-two lamps are lit by hand."),
    ("SAT 18 · 20:30", "Storm-light screening", "FORTY-THREE, the short film, projected on the harbour wall."),
    ("SUN 19 · 21:00", "The lighthouse lens", "Climb the tower and watch the Fresnel lens turn by clockwork."),
]


def programme(p):
    page = "programme"
    p.apply([{"type": "page", "action": "add", "name": page},
             {"type": "solid", "name": "programme-paper", "color": "#FBF6EC", "width": W, "height": H, "page": page},
             {"type": "container-place", "name": "prog-header", "resource": "section-header", "x": M, "y": M,
              "width": W - 2 * M, "height": 220, "seed": 3, "page": page,
              "variables": {"eyebrow": "PROGRAMME", "title": "Three nights of lamplight"}}], detail="brief")
    restyle(p, "prog-header", page, BUTTON_INK)
    y = 320
    for i, (date, title, body) in enumerate(PROGRAMME):
        name = f"step-{i}"
        p.apply({"type": "container-place", "name": name, "resource": "timeline-step", "x": M, "y": y,
                 "width": 700, "height": 250, "seed": 3, "page": page,
                 "variables": {"date": date, "title": title, "body": body}}, detail="brief")
        restyle(p, name, page, BUTTON_INK)
        y += 270
    stats = [("42", "gas lamps"), ("1", "lighthouse"), ("3", "nights")]
    for i, (value, label) in enumerate(stats):
        name = f"stat-{i}"
        p.apply({"type": "container-place", "name": name, "resource": "stat", "x": 820, "y": 320 + i * 270,
                 "width": 350, "height": 250, "seed": 3, "page": page,
                 "variables": {"value": value, "label": label}}, detail="brief")
        restyle(p, name, page, BUTTON_INK)
    badges = [("FREE", "#FFFFFF", "#7A4E2D"), ("STEP-FREE QUAY", "#3B2A1C", "#EBD9BD"),
              ("BRING A LANTERN", "#3B2A1C", "#EBD9BD"), ("RAIN OR SHINE", "#FFFFFF", "#2F4A3A")]
    ops, x = [], M
    for i, (label, fg, bg) in enumerate(badges):
        ops += pill(f"badge-{i}", label, x, 1170, fg, bg, page)
        x += 40 + len(label) * 13
    p.apply(ops, detail="brief")
    p.apply({"type": "container-place", "name": "prog-list", "resource": "list-block", "x": M, "y": 1260,
             "width": W - 2 * M, "height": 380, "seed": 3, "page": page,
             "variables": {"title": "Good to know",
                           "items": "Lamps are lit at dusk; arrive ten minutes early\n"
                                    "The tower climb has 134 steps and no lift\n"
                                    "Gas lamps are hot: keep small hands at a distance"}}, detail="brief")
    restyle(p, "prog-list", page, BUTTON_INK)


PEOPLE = [
    ("Wren Halloran", "Lamplighter", "Has lit Port Halloran's lamps for thirty-one years.",
     {"outfit": "#2F4A3A", "skin": "#C99A74", "hair": "#1F2B3A"}, "#3E5A78", "left", [0.5, 0.3]),
    ("Mara Quill", "Lighthouse keeper", "Keeps the Fresnel lens turning, storm or calm.",
     {"outfit": "#7A2E2E", "skin": "#8D5A3B", "hair": "#2A1A12"}, "#6E4A3A", "centered", [0.5, 0.28]),
    ("Tomas Reyes", "Electric company engineer", "Wired the new lights, then kept a lamp for himself.",
     {"outfit": "#3A4C7A", "skin": "#E2B48C", "hair": "#6B4A2B"}, "#2F4A3A", "split", [0.5, 0.3]),
]


def people(p):
    page = "people"
    p.apply([{"type": "page", "action": "add", "name": page},
             {"type": "solid", "name": "people-paper", "color": "#F3F5F8", "width": W, "height": H, "page": page},
             {"type": "container-place", "name": "people-header", "resource": "section-header", "x": M, "y": M,
              "width": W - 2 * M, "height": 200, "seed": 5, "page": page,
              "variables": {"eyebrow": "THE KEEPERS", "title": "Meet the people behind the light"}}],
            detail="brief")
    restyle(p, "people-header", page, BUTTON_INK)
    y = 300
    for i, (name, title, bio, colors, backdrop, variant, focal) in enumerate(PEOPLE):
        photo = art(p, portrait(colors, backdrop, i * 15))
        ident = f"person-{i}"
        # Every person starts in the left arrangement; container-variant then switches arrangement
        # while keeping the photo, the copy and the group's identity.
        p.apply({"type": "container-place", "name": ident, "resource": "profile", "variant": "left", "x": M,
                 "y": y, "width": W - 2 * M, "height": 330, "seed": 5, "page": page,
                 "variables": {"photo": photo, "name": name, "title": title, "bio": bio}}, detail="brief")
        if variant != "left":
            p.apply({"type": "container-variant", "target": ident, "variant": variant, "page": page},
                    detail="brief")
        restyle(p, ident, page, BUTTON_INK)
        y += 360
    quote = art(p, portrait({"outfit": "#B5651D", "skin": "#C99A74", "hair": "#4A2F22"}, "#B08A5A", 30))
    p.apply({"type": "container-place", "name": "testimonial", "resource": "testimonial", "variant": "split",
             "x": M, "y": 1390, "width": W - 2 * M, "height": 290, "seed": 5, "page": page,
             "variables": {"quote": "“I came for the lamps and stayed for the storm.”",
                           "name": "Ada, age 9", "role": "Festival regular", "photo": quote}}, detail="brief")
    restyle(p, "testimonial", page, BUTTON_INK)


def tickets(p):
    page = "tickets"
    p.apply([{"type": "page", "action": "add", "name": page},
             {"type": "solid", "name": "tickets-paper", "color": "#FBF6EC", "width": W, "height": H, "page": page},
             {"type": "container-place", "name": "tickets-header", "resource": "section-header", "x": M, "y": M,
              "width": W - 2 * M, "height": 200, "seed": 3, "page": page,
              "variables": {"eyebrow": "TICKETS & SHOP", "title": "Choose your pass"}}], detail="brief")
    restyle(p, "tickets-header", page, BUTTON_INK)
    tiers = [("Quay walk", "Free", "Friday lamp walk\nHarbour screening"),
             ("Keeper's pass", "£12", "All three nights\nLighthouse climb\nReserved seat"),
             ("Patron", "£40", "Keeper's pass\nSigned film print\nLight a lamp yourself")]
    cw = (W - 2 * M - 2 * 30) / 3
    for i, (plan, price, features) in enumerate(tiers):
        name = f"tier-{i}"
        p.apply({"type": "container-place", "name": name, "resource": "pricing-tier", "x": M + i * (cw + 30),
                 "y": 310, "width": round(cw), "height": 470, "seed": 3, "page": page,
                 "variables": {"plan": plan, "price": price, "features": features, "button": "Book"}},
                detail="brief")
    # The featured tier grows taller; its content reflows into the new box instead of stretching.
    p.apply([{"type": "resize", "target": "tier-1", "height": 520, "anchor": "top", "page": page},
             {"type": "container-reflow", "target": "tier-1", "page": page}], detail="brief")
    for i in range(3):
        restyle(p, f"tier-{i}", page, BUTTON_INK)
    p.apply(pill("featured", "MOST POPULAR", M + cw + 30 + 24, 272, "#FFFFFF", "#7A4E2D", page), detail="brief")
    products = [("scene_lens", "Fresnel lens print", "£25", "NEW"), ("scene_flame", "Lantern-light mug", "£14", "")]
    for i, (fn, name, price, tag) in enumerate(products):
        photo = art(p, scene(fn, 600, 600))
        ident = f"product-{i}"
        p.apply({"type": "container-place", "name": ident, "resource": "product-card", "variant": "left",
                 "x": M + i * (W - 2 * M + 30) / 2, "y": 840, "width": round((W - 2 * M - 30) / 2), "height": 300,
                 "seed": 3, "page": page, "variables": {"photo": photo, "name": name, "price": price, "tag": tag}},
                detail="brief")
        restyle(p, ident, page, BUTTON_INK)
    p.apply({"type": "container-place", "name": "tickets-cta", "resource": "cta", "x": M, "y": 1180,
             "width": 560, "height": 300, "seed": 3, "page": page,
             "variables": {"title": "Passes go on sale 1 October", "button": "lamplight.example/tickets"}},
            detail="brief")
    restyle(p, "tickets-cta", page, BUTTON_INK)
    p.apply(code_window("rebuild", [("# rebuild this programme", "#7F8AA3"),
                                    ("python explorations/", "#E8E2CF"),
                                    ("  14-festival-programme/build.py", "#E8E2CF"),
                                    ("→ 4 pages · 7 photos · 0 imports", "#9FE3B4")], 680, 1210, page),
            detail="brief")


# Social set -----------------------------------------------------------------------------------------------
def social():
    results = []
    combos = [("minimal-light", "slate", "none", "light"), ("bold-dark", "midnight", "soft-shadow", "dark"),
              ("warm-editorial", "coffee", "paper", "light")]
    for label, palette, look, mode in combos:
        p = Project.sized("instagram-portrait", "#ffffff")
        fonts(p)
        photo = art(p, scene("scene_storm", 1000, 600))
        names = sorted(TEMPLATES["social-event-promo"]["slots"])
        variables = social_copy(names, photo)
        result = p.apply({"type": "template-apply", "name": "social-event-promo", "seed": 21, "palette": palette,
                          "look": look, "mode": mode, "variables": variables}, detail="brief")
        for slot in names:
            restyle(p, slot, None)
        path = OUT / "social" / f"event-promo-{label}.png"
        p.render().save(path)
        findings = check_design(p, checks=["bounds", "contrast", "blanks", "fonts"])
        results.append({"file": str(path.relative_to(HERE)), "template": result["template"],
                        "check": {"passed": findings["passed"], "errors": findings["errors"],
                                  "warnings": findings["warnings"]}})
    # Three seeded rolls of a link card: the curated pools choose palette, pairing and layout.
    for seed in (3, 14, 27):
        p = Project.sized("og-image", "#ffffff")
        roll = roll_document(p, seed=seed, apply=True, purpose="event",
                             slots={"title": "The Lamplight Festival", "subtitle": "Three nights of hand-lit lamps",
                                    "label": "17–19 OCTOBER"})
        path = OUT / "social" / f"link-card-roll-{seed}.png"
        p.render().save(path)
        findings = check_design(p, checks=["bounds", "contrast", "blanks", "fonts"])
        results.append({"file": str(path.relative_to(HERE)), "seed": seed,
                        "check": {"passed": findings["passed"], "errors": findings["errors"],
                                  "warnings": findings["warnings"]},
                        "choices": {k: roll.get(k) for k in ("palette", "font_pairing", "layout", "style", "finish")
                                    if k in roll} or roll.get("direction") or roll.get("choices")})
    return results


TEMPLATE_COPY = {"title": "The Lamplight Festival", "subtitle": "17–19 October · Port Halloran",
                 "eyebrow": "THIS WEEKEND", "date": "17–19 OCT", "body": "Forty-two gas lamps, lit by hand.",
                 "caption": "Forty-two gas lamps, lit by hand.", "button": "Get a quay pass",
                 "label": "FREE ENTRY", "value": "42", "quote": "Some lights you keep by hand.",
                 "name": "Wren Halloran", "role": "Lamplighter", "items": "Lamp walk\nScreening\nLighthouse",
                 "plan": "Keeper's pass", "price": "£12", "features": "All three nights", "tag": "NEW",
                 "bio": "Lamplighter for 31 years.", "delta": ""}


def social_copy(slots, photo):
    spec = TEMPLATES["social-event-promo"]["slots"]
    copy = {slot: {field: photo if kind["kind"] == "image" else TEMPLATE_COPY.get(field, field.title())
                   for field, kind in spec[slot].items()} for slot in slots}
    if "title" in copy.get(slots[-1], {}):
        copy[slots[-1]]["title"] = "Three nights. One lighthouse."
    return copy


def main():
    (OUT / "social").mkdir(parents=True, exist_ok=True)
    p = Project(W, H, "#ffffff")
    fonts(p)
    template = cover(p)
    programme(p)
    people(p)
    tickets(p)
    p.save(OUT / "lamplight-programme.vixl")
    pages = ["cover", "programme", "people", "tickets"]
    for page in pages:
        p.render(page=page).save(OUT / f"programme-{page}.png")
    p.export(OUT / "lamplight-programme.pdf", overwrite=True)
    p.export(OUT / "lamplight-programme-spread.png", page="all", overwrite=True)
    checks = {page: check_design(p, page=page, checks=["bounds", "contrast", "blanks", "fonts", "overlap"])
              for page in pages}
    (OUT / "lamplight-programme.check.json").write_text(json.dumps(checks, indent=2, default=str))
    social_results = social()
    (OUT / "social" / "social.json").write_text(json.dumps(social_results, indent=2, default=str))
    (OUT / "choices.json").write_text(json.dumps({"cover_template": template}, indent=2, default=str))
    for page, result in checks.items():
        print(page, result["passed"], result["errors"], result["warnings"])
    for item in social_results:
        print(item["file"], item.get("check") or item.get("choices"))


if __name__ == "__main__":
    main()
