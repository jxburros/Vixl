"""The editable Aetherling Spirits card template (750x1050 = 2.5x3.5 in at 300 dpi)."""

from vixl import Project
from vixl.typefaces import install_font

CW, CH = 750, 1050

DEFAULTS = {
    "name": "Cinderwisp",
    "cost": "1",
    "element": "Ember",
    "element_color": "#ff6b35",
    "element_dark": "#2a0905",
    "element_light": "#ffd166",
    "kind": "Spirit — Wisp",
    "rarity": "Common",
    "rarity_color": "#c9d1d9",
    "rarity_pips": "◆",
    "ability_name": "Kindle",
    "ability": "When Cinderwisp enters play, give another Ember spirit +1 ATK until end of turn.",
    "flavor": "“Follow the small light,” the old guides said. Few asked where it led.",
    "atk": "2",
    "def": "1",
    "spd": "4",
    "set_no": "001",
    "edition": "First Edition",
}

# Text boxes (x, y, w, h) shared by the template, the fit actions and the suites.
NAME_BOX = (70, 52, 520, 76)
ABILITY_BOX = (78, 738, 594, 104)
FLAVOR_BOX = (78, 853, 594, 60)


def install_fonts(project):
    install_font(project, "Cinzel", 700, role="heading")
    install_font(project, "EB Garamond", 400, role="body")
    install_font(project, "EB Garamond", 400, italic=True)


def template_ops(art_asset):
    ops = []
    for k, v in DEFAULTS.items():
        ops.append({"type": "variable", "name": k, "value": v})
    ops.append({"type": "variable", "name": "art", "value": art_asset})
    ops += [
        # Fixed swatches. (Variable-driven swatches -- {"color": "${element_color}"} -- are accepted by
        # the swatch op but every later use of them fails validation; see README Findings. So element
        # colors use ${...} directly in color fields instead.)
        {"type": "swatch", "name": "ink", "color": "#fff8ec"},
        {"type": "swatch", "name": "ink-dark", "color": "#14100c"},
        {"type": "swatch", "name": "parchment", "color": "#f4ead2"},
        # Character + paragraph styles.
        {"type": "style-define", "name": "card-name", "settings": {"size": 50, "color": "@ink"}},
        {"type": "style-define", "name": "rules", "settings": {"size": 27, "color": "@ink-dark"}},
        {"type": "style-define", "name": "flavor", "settings": {"size": 24, "color": "#5b4a36"}},
        {"type": "style-define", "name": "stat", "settings": {"size": 44, "color": "@ink"}},
        {"type": "style-define", "name": "label", "settings": {"size": 25, "color": "${element_light}"}},
        {"type": "style-define", "name": "type-line", "settings": {"size": 26, "color": "@ink"}},
        {"type": "style-define", "name": "centered", "kind": "paragraph", "settings": {"align": "center", "spacing": 2}},
        {"type": "style-define", "name": "right", "kind": "paragraph", "settings": {"align": "right"}},
        {"type": "style-define", "name": "body-para", "kind": "paragraph", "settings": {"align": "left", "spacing": 3}},
        # Frame.
        {"type": "shape", "name": "frame", "shape": "rounded-rectangle", "radius": 40, "width": CW, "height": CH,
         "x": 0, "y": 0, "fill": "${element_color}"},
        {"type": "layer-style", "target": "frame", "name": "gradient-overlay",
         "settings": {"direction": "angled", "angle": 60,
                      "stops": [{"offset": 0, "color": "${element_light}"}, {"offset": 0.45, "color": "${element_color}"},
                                {"offset": 1, "color": "${element_color}"}]}},
        {"type": "shape", "name": "panel", "shape": "rounded-rectangle", "radius": 26, "width": CW - 44,
         "height": 982, "x": 22, "y": 22, "fill": "${element_dark}"},
        {"type": "gradient", "name": "panel-glow", "direction": "radial", "width": CW - 44, "height": 982,
         "x": 22, "y": 22, "stops": [{"offset": 0, "color": "alpha(${element_color}, 0.35)"},
                                     {"offset": 1, "color": "alpha(${element_dark}, 0)"}]},
        {"type": "clip", "target": "panel-glow", "base": "panel"},
        # Name bar.
        {"type": "shape", "name": "name-bar", "shape": "rounded-rectangle", "radius": 44, "width": 670,
         "height": 92, "x": 40, "y": 44, "fill": "alpha(#000000, 0.45)", "stroke": "${element_color}", "stroke_width": 3},
        {"type": "text", "name": "card-name", "text": "${name}", "font": "heading", "x": NAME_BOX[0],
         "y": NAME_BOX[1] + 8},
        {"type": "style-apply", "target": "card-name", "name": "card-name"},
        {"type": "text-layout", "target": "card-name", "width": NAME_BOX[2], "height": NAME_BOX[3], "fit": True},
        {"type": "layer-style", "target": "card-name", "name": "drop-shadow",
         "settings": {"color": "#000000", "dx": 0, "dy": 3, "blur": 4, "opacity": 0.8}},
        # Cost gem (hexagon polygon).
        {"type": "shape", "name": "cost-gem", "shape": "polygon", "sides": 6, "width": 96, "height": 96,
         "x": 608, "y": 42, "fill": "${element_color}", "stroke": "${element_light}", "stroke_width": 4},
        {"type": "layer-style", "target": "cost-gem", "name": "gradient-overlay",
         "settings": {"start": "${element_dark}", "end": "#000000"}},
        {"type": "layer-style", "target": "cost-gem", "name": "outer-glow",
         "settings": {"color": "${element_color}", "blur": 14, "opacity": 0.9}},
        {"type": "text", "name": "cost", "text": "${cost}", "font": "heading", "x": 608, "y": 58},
        {"type": "style-apply", "target": "cost", "name": "stat"},
        {"type": "style-apply", "target": "cost", "name": "centered", "kind": "paragraph"},
        {"type": "text-layout", "target": "cost", "width": 96, "height": 60},
        {"type": "layer-style", "target": "cost", "name": "stroke", "settings": {"color": "#000000", "width": 3}},
        # Art window: a frame bound to the ${art} image variable.
        {"type": "frame", "name": "art", "asset": art_asset, "width": 662, "height": 452, "x": 44, "y": 150,
         "fit": "fill"},
        {"type": "replace-contents", "target": "art", "variable": "art"},
        {"type": "layer-style", "target": "art", "name": "stroke", "settings": {"color": "${element_light}", "width": 4}},
        {"type": "layer-style", "target": "art", "name": "drop-shadow",
         "settings": {"color": "#000000", "dy": 6, "blur": 12, "opacity": 0.7}},
        # Type line.
        {"type": "shape", "name": "type-bar", "shape": "rounded-rectangle", "radius": 30, "width": 670,
         "height": 64, "x": 40, "y": 620, "fill": "alpha(#000000, 0.5)", "stroke": "${element_color}", "stroke_width": 3},
        {"type": "text", "name": "type-line", "text": "${element} · ${kind}", "font": "heading", "x": 70,
         "y": 634},
        {"type": "style-apply", "target": "type-line", "name": "type-line"},
        {"type": "text-layout", "target": "type-line", "width": 470, "height": 40, "fit": True},
        # Rarity badge: an 8-point star with the rarity color + pips.
        {"type": "shape", "name": "rarity-badge", "shape": "star", "sides": 8, "inner_radius": 0.55, "width": 104,
         "height": 104, "x": 600, "y": 600, "fill": "${rarity_color}", "stroke": "#ffffff", "stroke_width": 3},
        {"type": "layer-style", "target": "rarity-badge", "name": "outer-glow",
         "settings": {"color": "${rarity_color}", "blur": 18}},
        {"type": "shape", "name": "rarity-core", "shape": "polygon", "sides": 4, "width": 40, "height": 40,
         "x": 632, "y": 632, "fill": "${element_dark}"},
        {"type": "text", "name": "rarity", "text": "${rarity_pips} ${rarity}", "font": "body", "x": 330, "y": 686},
        {"type": "style-apply", "target": "rarity", "name": "label"},
        {"type": "style-apply", "target": "rarity", "name": "right", "kind": "paragraph"},
        {"type": "text-layout", "target": "rarity", "width": 262, "height": 28},
        # Rules box.
        {"type": "shape", "name": "rules-box", "shape": "rounded-rectangle", "radius": 18, "width": 640,
         "height": 200, "x": 55, "y": 716, "fill": "@parchment", "stroke": "${element_color}", "stroke_width": 3},
        {"type": "layer-style", "target": "rules-box", "name": "drop-shadow",
         "settings": {"color": "#000000", "dy": 4, "blur": 10, "opacity": 0.6}},
        {"type": "text", "name": "ability", "text": "${ability_name} — ${ability}", "font": "eb-garamond-400",
         "x": ABILITY_BOX[0], "y": ABILITY_BOX[1]},
        {"type": "style-apply", "target": "ability", "name": "rules"},
        {"type": "style-apply", "target": "ability", "name": "body-para", "kind": "paragraph"},
        {"type": "text-layout", "target": "ability", "width": ABILITY_BOX[2], "height": ABILITY_BOX[3], "fit": True},
        {"type": "shape", "name": "rule-divider", "shape": "line", "width": 520, "height": 2, "x": 115, "y": 846,
         "stroke": "alpha(#5b4a36, 0.5)", "stroke_width": 2},
        {"type": "text", "name": "flavor", "text": "${flavor}", "font": "eb-garamond-400-italic",
         "x": FLAVOR_BOX[0], "y": FLAVOR_BOX[1]},
        {"type": "style-apply", "target": "flavor", "name": "flavor"},
        {"type": "style-apply", "target": "flavor", "name": "body-para", "kind": "paragraph"},
        {"type": "text-layout", "target": "flavor", "width": FLAVOR_BOX[2], "height": FLAVOR_BOX[3], "fit": True},
    ]
    # Stat pills.
    for i, (key, label) in enumerate((("atk", "ATK"), ("def", "DEF"), ("spd", "SPD"))):
        x = 92 + i * 196
        ops += [
            {"type": "shape", "name": f"{key}-pill", "shape": "capsule", "width": 172, "height": 62, "x": x,
             "y": 928, "fill": "alpha(#000000, 0.55)", "stroke": "${element_color}", "stroke_width": 3},
            {"type": "text", "name": f"{key}-label", "text": label, "font": "body", "x": x + 20, "y": 945},
            {"type": "style-apply", "target": f"{key}-label", "name": "label"},
            {"type": "text", "name": f"{key}-value", "text": "${" + key + "}", "font": "heading", "x": x + 78,
             "y": 931},
            {"type": "style-apply", "target": f"{key}-value", "name": "stat"},
            {"type": "style-apply", "target": f"{key}-value", "name": "centered", "kind": "paragraph"},
            {"type": "text-layout", "target": f"{key}-value", "width": 76, "height": 56},
        ]
    ops += [
        {"type": "text", "name": "footer", "text": "AETHERLING SPIRITS · ${set_no}/013 · ${edition}",
         "font": "body", "x": 0, "y": 1010, "size": 25, "color": "#1a1208"},
        {"type": "constrain", "target": "footer", "constraints": {"center-x": "canvas.center-x"}},
    ]
    # Holo-foil layers (hidden in the "standard" comp).
    ops += [
        {"type": "gradient", "name": "holo-art", "direction": "angled", "angle": 35, "width": 662, "height": 452,
         "x": 44, "y": 150, "stops": [
             {"offset": 0.0, "color": "#ff5f6d"}, {"offset": 0.2, "color": "#ffc371"},
             {"offset": 0.4, "color": "#7cffcb"}, {"offset": 0.6, "color": "#4facfe"},
             {"offset": 0.8, "color": "#c471f5"}, {"offset": 1.0, "color": "#ff5f6d"}]},
        {"type": "blend", "target": "holo-art", "value": "overlay"},
        {"type": "opacity", "target": "holo-art", "value": 0.85},
        {"type": "shape", "name": "holo-sparkle", "shape": "star", "sides": 4, "inner_radius": 0.18, "width": 26,
         "height": 26, "x": 70, "y": 176, "fill": "#ffffff"},
        {"type": "repeat", "target": "holo-sparkle", "count": 6, "dx": 112, "dy": 70},
        {"type": "layer-style", "target": "holo-sparkle", "name": "outer-glow",
         "settings": {"color": "#ffffff", "blur": 10}},
        {"type": "opacity", "target": "holo-sparkle", "value": 0.85},
        {"type": "gradient", "name": "holo-frame", "direction": "angled", "angle": 120, "width": CW, "height": CH,
         "stops": [{"offset": 0.0, "color": "#ff5f6d55"}, {"offset": 0.2, "color": "#ffc37199"},
                   {"offset": 0.38, "color": "#7cffcbcc"}, {"offset": 0.5, "color": "#ffffffee"},
                   {"offset": 0.62, "color": "#4facfecc"}, {"offset": 0.8, "color": "#c471f599"},
                   {"offset": 1.0, "color": "#ff5f6d55"}]},
        {"type": "clip", "target": "holo-frame", "base": "frame"},
        {"type": "blend", "target": "holo-frame", "value": "screen"},
        {"type": "reorder", "target": "holo-frame", "below": "panel"},
    ]
    return ops


def build_template(art_asset_bytes):
    """Create the template project. art_asset_bytes: PNG bytes for the default art."""
    from vixl.assets import add_encoded

    project = Project(CW, CH, "#00000000")
    project.apply({"type": "canvas", "dpi": 300}, detail="compact")
    install_fonts(project)
    asset, _ = add_encoded(project, art_asset_bytes)
    project.apply(template_ops(asset), detail="compact")
    # Comps: "standard" hides every holo layer; "holo" shows them and adds a rarity-tinted rim glow.
    holo = ["holo-art", "holo-sparkle", "holo-frame"]
    project.apply([{"type": "hide", "target": t} for t in holo] + [{"type": "comp-save", "name": "standard"}],
                  detail="compact")
    project.apply([{"type": "show", "target": t} for t in holo] + [
        {"type": "layer-style", "target": "panel", "name": "outer-glow",
         "settings": {"color": "${rarity_color}", "blur": 16, "opacity": 0.9}},
        {"type": "comp-save", "name": "holo"},
        {"type": "comp-apply", "name": "standard"},
    ], detail="compact")
    return project
