"""Editable promo compositions, drawn natively for each delivery aspect ratio."""

FORMATS = {"square": (1080, 1080), "story": (1080, 1920), "wide": (1920, 1080)}
TREATMENTS = {
    "kinetic": ("Oversized type and staggered opposing slides", "slide-in-left", "slide-in-right"),
    "editorial": ("Quiet editorial framing with a drawn rule", "fade-in", "fade-in"),
    "neon": ("Outlined orbit and floating geometric accents", "pop-in", "slide-in-up"),
    "spotlight": ("Product-style stage with an expanding halo", "zoom-out", "fade-in"),
    "split": ("Two-column comparison with opposing entrances", "slide-in-left", "slide-in-right"),
    "stat": ("Large statistic card with a rising reveal", "slide-in-up", "fade-in"),
}


def builtins():
    templates = {}
    for style, (description, entrance, secondary) in TREATMENTS.items():
        for format_name, (w, h) in FORMATS.items():
            unit = min(w, h)
            margin = round(unit * .08)
            content = []

            def shape(name, kind, x, y, width, height, fill="${accent}", **extra):
                content.append({"type": "shape", "shape": kind, "name": name, "x": round(x), "y": round(y),
                                "width": round(width), "height": round(height), "fill": fill, **extra})

            def text(name, value, x, y, width, size, color="${foreground}"):
                content.extend([
                    {"type": "text", "name": name, "text": "${" + value + "}", "x": round(x), "y": round(y),
                     "size": round(size), "color": color},
                    {"type": "text-layout", "target": name, "width": round(width)},
                    {"type": "fit-text", "target": name, "width": round(width), "height": round(h * (.08 if name == "promo-cta" else .22)),
                     "minimum": round(size * .45), "maximum": round(size)},
                ])

            title_y, subtitle_y = h * .28, h * .57
            text_width = w - 2 * margin
            if style == "kinetic":
                shape("promo-bar", "rectangle", margin, h * .16, unit * .22, unit * .018)
                shape("promo-block", "rectangle", w - margin - unit * .09, h * .77, unit * .09, unit * .09)
            elif style == "editorial":
                shape("promo-rule", "rectangle", margin, h * .19, text_width, unit * .005)
                shape("promo-side", "rectangle", margin, title_y, unit * .008, h * .38)
                margin += round(unit * .04)
                text_width = w - 2 * margin
            elif style == "neon":
                shape("promo-orbit", "ellipse", w - unit * .39, h * .04, unit * .18, unit * .18,
                      "transparent", stroke="${accent}", stroke_width=8)
                shape("promo-dot", "ellipse", margin, h * .75, unit * .045, unit * .045)
            elif style == "spotlight":
                shape("promo-halo", "ellipse", (w - unit * .6) / 2, (h - unit * .6) / 2,
                      unit * .6, unit * .6, "transparent", stroke="${accent}", stroke_width=16)
            elif style == "split":
                if w > h:
                    shape("promo-divider", "rectangle", w * .5, h * .22, unit * .006, h * .44)
                    text_width = w * .5 - margin * 1.5
                    subtitle_y = title_y
                else:
                    shape("promo-divider", "rectangle", margin, h * .5, text_width, unit * .006)
            elif style == "stat":
                shape("promo-card", "rectangle", margin, h * .16, text_width, h * .34,
                      "${accent}", radius=24)
                title_y = h * .21

            text("promo-title", "title", margin, title_y, text_width, unit * (.12 if style in ("kinetic", "stat") else .075),
                 "${on_accent}" if style == "stat" else "${foreground}")
            text("promo-subtitle", "subtitle", w * .5 + margin * .5 if style == "split" and w > h else margin,
                 subtitle_y, text_width, unit * .036)
            text("promo-cta", "cta", margin, h * .84, w - 2 * margin, unit * .032)
            names = [op["name"] for op in content if "name" in op]
            motion = [
                {"type": "group", "name": "promo-content", "targets": names},
                {"type": "timeline-set", "duration": 6000, "fps": 30, "loop_mode": "seamless"},
                {"type": "animate-preset", "target": "promo-title", "preset": entrance, "duration": 700, "easing": "ease-in-out", "close": True},
                {"type": "animate-preset", "target": "promo-subtitle", "preset": secondary,
                 "start": 350, "duration": 650, "easing": "ease-in-out", "close": True},
                {"type": "animate-preset", "target": "promo-cta", "preset": "fade-in",
                 "start": 950, "duration": 500, "easing": "ease-in-out", "close": True},
            ]
            decoration = {"kinetic": ("promo-bar", "slide-in-left"), "editorial": ("promo-rule", "draw-on"),
                          "neon": ("promo-orbit", "float"), "spotlight": ("promo-halo", "pulse"),
                          "split": ("promo-divider", "draw-on"), "stat": ("promo-card", "pop-in")}[style]
            motion.append({"type": "animate-preset", "target": decoration[0], "preset": decoration[1],
                           "duration": 6000 if style in ("neon", "spotlight") else 800,
                           "easing": "ease-in-out", "close": style not in ("neon", "spotlight")})
            # A shared fade gives the composition a quiet background at the loop boundary.
            motion.extend([
                {"type": "keyframe", "target": "promo-content", "property": "opacity", "time": 0, "value": 0, "easing": "ease-in-out"},
                {"type": "keyframe", "target": "promo-content", "property": "opacity", "time": 900, "value": 1},
                {"type": "keyframe", "target": "promo-content", "property": "opacity", "time": 5100, "value": 1, "easing": "ease-in-out"},
                {"type": "keyframe", "target": "promo-content", "property": "opacity", "time": 6000, "value": 0},
            ])
            name = f"video-promo-{style}" + ("" if format_name == "square" else f"-{format_name}")
            templates[name] = {
                "description": f"{description}; editable six-second {format_name} promo loop.",
                "width": w, "height": h, "background": "transparent", "proportional": True,
                "blanks": {"title": "[Your headline]", "subtitle": "[The benefit]", "cta": "[Next step]"},
                "roll": {"background": "background", "foreground": "ink", "accent": "accent", "on_accent": "on-accent"},
                "operations": [{"type": "solid", "name": "promo-background", "color": "${background}",
                                "width": w, "height": h}, *content, *motion],
            }
    return templates
