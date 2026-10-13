"""Generate the inputs the shorts show by running the real Vixl features.

Nothing here is mocked up: the contrast figures come from ``check``, the three card sizes from
``adapt-layout`` with ``recompose``, the badge run from ``merge-impose``, the sketch from the drawing
pipeline, and the chart's before and after from ``chart`` and ``chart-data``. Outputs go to ``work/``,
which is not committed; the scenes embed what they use.
"""
from __future__ import annotations

import importlib.util
import re
import sys
import zipfile
from functools import cache

import scenes as promo
from short import HERE, WHITE, WORK
from vixl import Project
from vixl.image_import import import_image_from
from vixl.typefaces import install_font

import kit

IDT = HERE.parent / "it-does-that" / "build"


def _it_does_that_assets():
    """The badge run and sketch pipeline from "It does that?", loaded by path (both films have assets.py)."""
    sys.path.append(str(IDT))  # its film.py, after our own folders
    spec = importlib.util.spec_from_file_location("idt_assets", IDT / "assets.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@cache
def contrast():
    """The real contrast check on the festival poster with its dim dates line, then on the fixed poster."""
    sc = kit.Scene("contrast-probe", 1000)
    sc.add(promo.flat(promo.poster("p", 0, 0, 640, 800, dates_color=promo.DIM_DATES)))
    report = sc.project().check(checks=["contrast"])
    issue = next(i for i in report["issues"] if i["check"] == "contrast" and "'p-dates'" in i["message"])
    before = re.search(r"contrast is ([\d.]+):1", issue["message"]).group(1)
    needs = re.search(r"needs ([\d.]+):1", issue["message"]).group(1)
    fixed = kit.Scene("contrast-probe", 1000)
    fixed.add(promo.flat(promo.poster("p", 0, 0, 640, 800, dates_color=WHITE)))
    checks = ["bounds", "overlap", "contrast", "fonts"]
    report = fixed.project().check(checks=checks)
    fixes = [i for i in report["issues"] if i["action"] == "fix"]
    if fixes:
        raise RuntimeError(f"The fixed poster should pass every check: {fixes}")
    return {"before": before, "needs": needs, "checks": checks}


CARD = {"title": "Launch day", "subtitle": "Ideas become editable.", "label": "VIXL 0.26", "cta": "Try it free"}
SIZES = [("post", None), ("story", "story"), ("video", "youtube-thumbnail")]


@cache
def cards():
    """One layout-built card, recomposed by ``adapt-layout`` for a story and a 16:9 thumbnail."""
    p = Project(1080, 1080, "#252B39")
    install_font(p, "Inter Tight", 800, role="heading")
    install_font(p, "Inter", 400, role="body")
    picture = import_image_from(p, path=str(kit.ROOT / "explorations/05-generative-painting/output/painting.jpg"),
                                name="picture")
    p.apply([{"type": "delete", "target": "picture"}], detail="brief")
    p.apply([{"type": "layout-apply", "name": "split-screen", "seed": 3, "unfilled": "omit", "mode": "dark", "accent": "rule",
              "palette": ["#252B39", "#2F3647", "#FFFFFF", "#AEB7CA", "#3575EE"], "font": "inter-400",
              "display_font": "inter-tight-800", "base_size": 38, "image": picture["asset"], **CARD}], detail="brief")
    out = {}
    for key, size in SIZES:
        doc = p.clone()
        if size:
            doc.apply([{"type": "adapt-layout", "size": size, "recompose": True}], detail="brief")
        issues = [i for i in doc.check()["issues"] if i["action"] == "fix"]
        if issues:
            raise RuntimeError(f"The {key} card should pass check: {issues}")
        path = WORK / f"card-{key}.png"
        path.unlink(missing_ok=True)
        doc.export(str(path))
        c = doc.state["canvas"]
        out[key] = {"path": path, "width": c["width"], "height": c["height"]}
    return out


@cache
def badges():
    return _it_does_that_assets().badges()


@cache
def sketch():
    return _it_does_that_assets().sketch()


CHART = {"type": "chart", "name": "sales", "kind": "bar", "title": "Cups sold", "number_format": "#,##0",
         "categories": ["Jan", "Feb", "Mar", "Apr"],
         "series": [{"name": "Espresso", "values": [1200, 1100, 1250, 900], "color": "#3575EE"},
                    {"name": "Latte", "values": [800, 760, 820, 1300], "color": "#FFC94D"}]}
CHART_FIX = {"type": "chart-data", "target": "sales", "set": [{"category": "Apr", "series": "Espresso", "value": 2400}]}


@cache
def chart(x, y, w, h):
    """The chart before and after one ``chart-data`` edit, layer by layer, plus a real PPTX export of it."""
    op = {**CHART, "x": x, "y": y, "width": w, "height": h, "text_color": "#FFFFFF", "font_size": 26}
    p = Project(1080, 1920, "#252B39")
    install_font(p, "Inter", 600)
    p.apply([op], detail="brief")
    before = {layer["name"]: layer for layer in p.state["layers"]}
    after_doc = p.clone()
    after_doc.apply([CHART_FIX], detail="brief")
    after = {layer["name"]: layer for layer in after_doc.state["layers"]}
    deck = WORK / "chart.pptx"
    deck.unlink(missing_ok=True)
    after_doc.export(str(deck))
    with zipfile.ZipFile(deck) as z:
        charts = [n for n in z.namelist() if re.fullmatch(r"ppt/charts/chart\d+\.xml", n)]
        embedded = [n for n in z.namelist() if n.startswith("ppt/embeddings/")]
    return {"op": op, "before": before, "after": after, "native_charts": len(charts), "embedded": len(embedded)}

