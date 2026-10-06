"""Deck checks for multi-page documents: slides, carousels and booklets.

``check_deck`` runs the ordinary design checks on every page and then reviews the deck as a
whole, which no single-page check can see:

* ``title_position`` — titles on pages that share a master sit in the same place (the deck's
  first titled page, usually the cover, is exempt);
* ``type_scale`` — text sizes come from one scale (the document's character styles when it has
  them) without near-duplicates such as 30 and 32 px;
* ``words`` — no page carries more words than an audience can read while listening;
* ``min_font`` — page text is large enough when projected (in points on the exported slide);
* ``notes`` — speaker notes are not missing from a few pages of an annotated deck;
* ``empty`` — no page is blank apart from its master.
"""

import math
import re
from collections import Counter

from .errors import require

DECK_CHECKS = ("title_position", "type_scale", "words", "min_font", "notes", "empty")
TITLE_NAME = re.compile(r"(^|[-_ /])(title|heading|headline)($|[-_ /\d])", re.I)
CHROME_NAME = re.compile(r"(footer|footnote|page-?num|slide-?num|folio|source|credit|copyright|legal)", re.I)


def points_per_pixel(canvas):
    """Points per pixel on the exported page (PowerPoint and PDF use the same page size)."""
    if canvas.get("dpi"):
        return 72 / canvas["dpi"]
    # Screen documents export 7.5 inches tall (540 pt), PowerPoint's standard slide height.
    return 540 / canvas["height"]


def _master_ids(view):
    from .pages import master_content

    state = view.state
    record = next((p for p in state.get("pages") or [] if p["id"] == state.get("page")), None)
    if not record or not record.get("master") or record["master"] not in state.get("masters", {}):
        return set()
    return {layer["id"] for layer in master_content(view, record["master"]).get("layers", [])}


def text_sizes(view, layer):
    """[(size in px, characters)] for a text layer: one entry per span of rich text, after any
    shrink-to-fit."""
    from .richtext import active, fitted, styled_spans
    from .text import plan

    if active(layer):
        scale = fitted(view, layer).size_scale
        return [(span["size"] * scale, len(span["text"].strip())) for span in styled_spans(view, layer)
                if span["text"].strip()]
    return [(plan(view, layer).size, len(layer.get("text", "").strip()))]


def _canvas_info(view, layers=None):
    from .checks import canvas_projection
    from .render import resolve_layout, resolved_layers

    layers = layers if layers is not None else resolved_layers(view)
    resolved = {item["id"]: item for item in layers}
    local = resolve_layout(view, layers=layers)
    return resolved, canvas_projection(resolved, local)


def _visible(item, resolved):
    while item:
        if not item["visible"] or item["opacity"] <= 0:
            return False
        item = resolved.get(item.get("parent"))
    return True


def title_layer(view, layers=None, info=None):
    """The page's title: a text layer named title/heading/headline (the topmost if several), else
    the largest text whose top is in the upper 40% of the page. Master layers are never titles."""
    resolved, projection = info or _canvas_info(view, layers)
    masters = _master_ids(view)
    texts = [item for item in resolved.values() if item["type"] == "text" and item["id"] not in masters
             and item.get("text", "").strip() and _visible(item, resolved)]
    if not texts:
        return None
    bounds = projection["bounds"]
    named = [item for item in texts if TITLE_NAME.search(item["name"])]
    if named:
        return min(named, key=lambda item: (bounds[item["id"]][1], bounds[item["id"]][0]))
    height = view.state["canvas"]["height"]
    upper = [item for item in texts if bounds[item["id"]][1] < height * 0.4]
    if not upper:
        return None

    def size(item):
        return max(s for s, _ in text_sizes(view, item) or [(0, 0)]) * projection["scales"][item["id"]]

    best = max(upper, key=lambda item: (size(item), -bounds[item["id"]][1]))
    others = [size(item) for item in texts if item is not best]
    # A lone body paragraph near the top is not a title unless it is the biggest type on the page.
    if others and size(best) < max(others) * 0.999:
        return None
    return best


def contact_sheet(project, pages=None, *, width=480, columns=None, labels=True, include_hidden=True, variables=None):
    """One image with every page side by side (labelled with its number and name), for reviewing
    a deck at a glance."""
    from PIL import Image, ImageDraw, ImageFont

    from .pages import find_page, page_list
    from .proxy import scaled_project
    from .render import render, view_page

    require(project.state.get("pages"), "This document has no pages", field="page")
    records = [find_page(project.state, ref, "pages") for ref in pages] if pages else page_list(project, include_hidden)
    require(records, "No pages to show", field="pages")
    canvas = project.state["canvas"]
    width = int(max(64, min(1600, width)))
    height = max(1, round(width * canvas["height"] / canvas["width"]))
    columns = int(columns or min(4, len(records)))
    require(1 <= columns <= 16, "columns must be 1–16", field="columns")
    rows = math.ceil(len(records) / columns)
    gap, label = 16, (24 if labels else 0)
    font = ImageFont.load_default(size=15)
    total_w, total_h = columns * width + (columns + 1) * gap, rows * (height + label) + (rows + 1) * gap
    project.limits.size(total_w, total_h)
    sheet = Image.new("RGBA", (total_w, total_h), (226, 226, 230, 255))
    draw = ImageDraw.Draw(sheet)
    for index, record in enumerate(records):
        row, column = divmod(index, columns)
        x, y = gap + column * (width + gap), gap + row * (height + label + gap)
        view = view_page(project, record["id"])
        proxy = scaled_project(view, width / canvas["width"]) if width < canvas["width"] * 0.75 else None
        image = (render(proxy, variables) if proxy is not None else render(view, variables)).convert("RGBA")
        image = image.resize((width, height), Image.Resampling.LANCZOS)
        backdrop = Image.new("RGBA", image.size, (255, 255, 255, 255))
        sheet.paste(Image.alpha_composite(backdrop, image), (x, y + label))
        draw.rectangle((x - 1, y + label - 1, x + width, y + label + height), outline=(160, 160, 168, 255))
        if labels:
            number = project.state["pages"].index(record) + 1
            text = f"{number}  {record['name']}" + ("  (hidden)" if record.get("hidden") else "") + (
                "  · notes" if record.get("notes") else "")
            draw.text((x, y + 3), text, fill=(40, 40, 48, 255), font=font)
    return sheet


def _cluster(values, tolerance):
    """Group sorted numbers that sit within ``tolerance`` of their neighbour."""
    groups = []
    for value in sorted(values):
        if groups and value - groups[-1][-1] <= tolerance:
            groups[-1].append(value)
        else:
            groups.append([value])
    return groups


def check_deck(project, *, checks=None, safe_area=None, min_contrast=None, pages=None, min_font=None, max_words=None,
               include_hidden=False, profile=None, thumbnail_width=None, min_thumbnail_text=10):
    """Run the design checks on every page and the deck checks across pages.

    ``checks`` mixes design check names (default: the standard set) with deck check names
    (default: all of them). ``min_font`` is in points on the exported slide; ``max_words`` counts
    the words on a page excluding its master and speaker notes."""
    from .checks import CHECKS, OPTIONAL_CHECKS, check_design
    from .pages import find_page, page_list
    from .render import view_page

    require(project.state.get("pages"), "The deck checks need a document with pages; add them with page add",
            field="checks")
    canvas = project.state["canvas"]
    profile = profile or ("phone" if canvas.get("size") in ("instagram-portrait", "instagram-square", "instagram-story") else "projected")
    require(profile in ("projected", "screen", "phone"), "deck profile must be projected, screen or phone", field="profile")
    defaults = {"projected": (18, 60, 320), "screen": (14, 250, 1280), "phone": (12, 150, 540)}[profile]
    min_font = defaults[0] if min_font is None else min_font
    max_words = defaults[1] if max_words is None else max_words
    # The thumbnail legibility check judges a social post, not a projected slide: ``min_font``
    # replaces it unless it is asked for by name.
    checks = list(checks) if checks else [c for c in CHECKS if c != "legibility"] + list(DECK_CHECKS)
    if profile != "projected" and checks == [c for c in CHECKS if c != "legibility"] + list(DECK_CHECKS):
        checks.remove("type_scale")
    unknown = sorted(set(checks) - set(CHECKS + OPTIONAL_CHECKS + DECK_CHECKS))
    require(not unknown, f"Unknown check(s) {unknown}; available: {', '.join(CHECKS + OPTIONAL_CHECKS + DECK_CHECKS)}",
            field="checks")
    require(isinstance(min_font, (int, float)) and 4 <= min_font <= 200, "min_font must be 4–200 points", field="min_font")
    require(isinstance(max_words, int) and 1 <= max_words <= 10000, "max_words must be 1–10000", field="max_words")
    design = [c for c in checks if c not in DECK_CHECKS]
    deck = [c for c in checks if c in DECK_CHECKS]
    records = [find_page(project.state, ref, "pages") for ref in pages] if pages else page_list(project, include_hidden)
    require(records, "No pages to check", field="pages")
    pt = points_per_pixel(canvas)
    font_scale = pt if profile == "projected" else defaults[2] / canvas["width"]
    issues, summaries = [], []

    def issue(check, severity, message, page=None, layers=(), **extra):
        issues.append({"check": check, "severity": severity, **({"page": page} if page else {}),
                       "layers": list(layers), "message": message, **extra})

    titles, sizes, notes = {}, Counter(), {}
    for number, record in enumerate(records, 1):
        label = record["name"]
        if design:
            thumb = thumbnail_width
            if thumb is None and profile != "projected":
                thumb = 320 if profile == "phone" and number == 1 else defaults[2]
            result = check_design(project, checks=design, safe_area=safe_area, min_contrast=min_contrast,
                                  page=record["id"], thumbnail_width=thumb, min_thumbnail_text=min_thumbnail_text)
            for item in result["issues"]:
                # The same finding on several pages (usually a master layer or a document-wide
                # setting such as fonts) is reported once with every page it affects.
                same = next((x for x in issues if x.get("pages") and x["check"] == item["check"]
                             and x["message"] == item["message"] and x["layers"] == item["layers"]), None)
                if same:
                    same["pages"].append(label)
                else:
                    issues.append({**item, "pages": [label]})
            summaries.append({"page": label, "passed": result["passed"], "errors": result["errors"],
                              "warnings": result["warnings"]})
        if not deck:
            continue
        view = view_page(project, record["id"])
        resolved, projection = _canvas_info(view)
        masters = _master_ids(view)
        own = [item for item in resolved.values() if item["id"] not in masters and _visible(item, resolved)]
        texts = [item for item in own if item["type"] == "text" and item.get("text", "").strip()]
        words = sum(len(re.findall(r"\w+", item.get("text", ""))) for item in texts)
        notes[label] = bool(record.get("notes", "").strip())
        if "empty" in deck and not [item for item in own if item["type"] != "group"]:
            issue("empty", "warning", f"Page {label!r} has no content of its own", label)
        if "words" in deck and words > max_words:
            issue("words", "warning", f"Page {label!r} carries {words} words (more than {max_words}); move detail to the "
                  "speaker notes or split the page", label, [item["name"] for item in texts], words=words)
        title = title_layer(view, info=(resolved, projection))
        if title:
            x, y, w, h = projection["bounds"][title["id"]]
            align = title.get("align", "left")
            anchor = x + w / 2 if align == "center" else x + w if align == "right" else x
            titles[label] = {"layer": title["name"], "x": anchor, "y": y, "align": align, "master": record.get("master"),
                             "number": number}
        for item in texts:
            scale = projection["scales"][item["id"]]
            chrome = CHROME_NAME.search(item["name"])
            for size, count in text_sizes(view, item):
                px = round(size * scale * 2) / 2
                sizes[px] += count
                if "min_font" in deck and not chrome and px * font_scale < min_font - 0.05:
                    display = (f"{px * pt:.1f} pt when projected (below {min_font} pt)" if profile == "projected" else
                               f"{px * font_scale:.1f} px at {defaults[2]} px {profile} width (below {min_font} px)")
                    issue("min_font", "warning",
                          f"{item['name']!r} on page {label!r} is {display}; "
                          f"use at least {min_font / font_scale:.0f} px on this canvas", label, [item["name"]],
                          points=round(px * pt, 1), pixels=px)
                    break

    if "title_position" in deck and len(titles) > 1:
        tolerance_x, tolerance_y = canvas["width"] * 0.015, canvas["height"] * 0.015
        groups = {}
        for label, info in titles.items():
            groups.setdefault(info["master"], []).append((label, info))
        first = min(info["number"] for info in titles.values())
        for master, members in groups.items():
            if len(members) > 2 and members[0][1]["number"] == first:
                members = members[1:]  # The opening (cover) page is laid out on its own.
            if len(members) < 2:
                continue
            for axis, tolerance in (("x", tolerance_x), ("y", tolerance_y)):
                clusters = _cluster([info[axis] for _, info in members], tolerance)
                if len(clusters) < 2:
                    continue
                main = max(clusters, key=len)
                if len(main) * 2 <= len(members) and len(clusters) > 2:
                    issue("title_position", "warning",
                          f"Titles on {len(members)} pages sit at {len(clusters)} different {'left edges' if axis == 'x' else 'heights'}; "
                          "give them one position (a master or a guide)", None,
                          [info["layer"] for _, info in members], master=master)
                    continue
                for label, info in members:
                    if info[axis] not in main:
                        reference = round(sum(main) / len(main))
                        issue("title_position", "warning",
                              f"The title on page {label!r} sits at {'x' if axis == 'x' else 'y'} {round(info[axis])} where the "
                              f"other titles sit at {reference}", label, [info["layer"]], expected=reference,
                              actual=round(info[axis]))

    if "type_scale" in deck and sizes:
        styled = sorted({float(s["size"]) for s in project.state.get("character_styles", {}).values() if "size" in s})
        distinct = sorted(sizes)
        if styled:
            off = [size for size in distinct if not any(abs(size - s) <= 0.5 for s in styled)]
            if off:
                issue("type_scale", "warning",
                      f"Text sizes {', '.join(f'{s:g}' for s in off)} px are not on the document's type scale "
                      f"({', '.join(f'{s:g}' for s in styled)} px)", None, sizes=off, scale=styled)
        near = [(a, b) for a, b in zip(distinct, distinct[1:]) if b / a < 1.1]
        for a, b in near:
            rare = a if sizes[a] <= sizes[b] else b
            issue("type_scale", "warning",
                  f"Text sizes {a:g} and {b:g} px are almost the same; use one of them (the {rare:g} px text is rarer)",
                  None, sizes=[a, b])
        if len(distinct) > 6:
            issue("type_scale", "warning",
                  f"The deck uses {len(distinct)} text sizes ({', '.join(f'{s:g}' for s in distinct)} px); "
                  "five or six steps of one scale read as a system", None, sizes=distinct)

    if "notes" in deck and notes:
        missing = [label for label, has in notes.items() if not has]
        if missing and len(missing) < len(notes):
            issue("notes", "warning",
                  f"{len(missing)} of {len(notes)} pages have no speaker notes ({', '.join(missing[:12])})", None,
                  pages=missing)

    from .checks import tally

    return {
        **tally(issues),
        "issues": issues,
        "checked": {"checks": checks, "pages": len(records), "profile": profile,
                    "min_font_pt" if profile == "projected" else "min_font_px": min_font, "max_words": max_words,
                    "thumbnail_width": thumbnail_width, "display_width": defaults[2], "points_per_pixel": round(pt, 4)},
        "pages": summaries,
    }
