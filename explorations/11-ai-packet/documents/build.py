"""AI literacy packet -- professional documents slice, built with Vixl 0.23.

Run from the repository root:

    python explorations/11-ai-packet/documents/build.py            # everything
    python explorations/11-ai-packet/documents/build.py deck form   # some parts

Outputs land in explorations/11-ai-packet/documents/out/ (each part's files are
replaced on every run). Sources (.vixl) are kept next to their exports.

Content notes: every factual statement (dates, names, quotes) is a well-known,
checkable fact. The only chart numbers are explicitly labelled "illustrative".
"""

import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
OUT.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("VIXL_NO_UPDATE", "1")

from vixl import Project  # noqa: E402
from vixl.typefaces import install_font, pair_fonts  # noqa: E402

# ----------------------------------------------------------------------------------
# Shared brand: one palette and one type pairing for the whole packet
# ----------------------------------------------------------------------------------
PAIRING = "lexend-atkinson"          # Lexend 600 headings + Atkinson Hyperlegible Next body
BRAND = {
    "paper": "#f6f4ee",
    "surface": "#e9e5d9",
    "ink": "#17203a",
    "muted": "#535a70",
    "accent": "#2f55c9",
    "amber": "#d9822b",
    "teal": "#0f7d73",
    "rose": "#c2415b",
}
PALETTE_OPS = [
    {"type": "palette-define", "name": "packet",
     "colors": [BRAND["paper"], BRAND["surface"], BRAND["ink"], BRAND["muted"], BRAND["accent"],
                BRAND["amber"], BRAND["teal"]]},
    {"type": "palette-apply", "name": "packet",
     "roles": {"background": BRAND["paper"], "surface": BRAND["surface"], "ink": BRAND["ink"],
               "muted": BRAND["muted"], "accent": BRAND["accent"], "accent-text": BRAND["accent"],
               "on-accent": "#ffffff"}},
    {"type": "swatch", "name": "amber", "color": BRAND["amber"]},
    {"type": "swatch", "name": "amber-text", "color": "#a65d17"},
    {"type": "swatch", "name": "teal", "color": BRAND["teal"]},
    {"type": "swatch", "name": "rose", "color": BRAND["rose"]},
]

TIMINGS = {}


def log(*a):
    print(*a, flush=True)


class timed:
    def __init__(self, label):
        self.label = label

    def __enter__(self):
        self.t = time.perf_counter()

    def __exit__(self, *exc):
        TIMINGS[self.label] = round(time.perf_counter() - self.t, 2)
        log(f"  [{TIMINGS[self.label]:6.2f}s] {self.label}")


def fresh(path):
    path = Path(path)
    if path.exists():
        path.unlink()
    return path


def summarize(report, label):
    """Print every finding of a check report compactly; return the list of issues."""
    issues = report.get("issues", report.get("findings", []))
    by = {}
    for i in issues:
        by.setdefault(i.get("action", i.get("severity", "?")), []).append(i)
    log(f"  check {label}: " + (", ".join(f"{k}={len(v)}" for k, v in by.items()) or "clean"))
    for i in issues:
        log(f"    - [{i.get('action', '?')}/{i.get('check', i.get('type', '?'))}] "
            f"{i.get('layer', i.get('page', ''))}: {str(i.get('message', ''))[:220]}")
    return issues


def run_cli(*args, cwd=None):
    t = time.perf_counter()
    r = subprocess.run(["vixl", *map(str, args)], cwd=cwd or OUT, capture_output=True, text=True)
    dt = time.perf_counter() - t
    if r.returncode != 0:
        log("CLI FAILED:", " ".join(map(str, args)), "\n", r.stdout[-3000:], r.stderr[-3000:])
        raise SystemExit(1)
    return r.stdout, dt


def pdf_pages_to_png(pdf, stem, scale=1.0):
    """Render PDF pages to PNG with pypdfium2 so the export itself can be inspected."""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(pdf))
    outs = []
    for i in range(len(doc)):
        img = doc[i].render(scale=scale).to_pil()
        out = OUT / "_inspect" / f"{stem}-p{i + 1}.png"
        out.parent.mkdir(exist_ok=True)
        img.save(out)
        outs.append(out)
    return outs


def brand_document(**create):
    info = {}
    # workspace_fonts=False: the rolled pairing would be embedded and then replaced by ours.
    create.setdefault("workspace_fonts", False)
    p = Project.new(**create, report=info, workspace=str(OUT))
    pair_fonts(p, PAIRING)
    install_font(p, "Lexend", 400)                     # lexend-400 for light headings
    install_font(p, "Atkinson Hyperlegible Next", 700)  # real bold for rich text
    install_font(p, "Atkinson Hyperlegible Next", 400, italic=True)
    p.apply(PALETTE_OPS)
    # palette-apply sets the role swatches but leaves the rolled canvas colour alone.
    p.apply([{"type": "canvas", "background": "@background"}])
    return p, info


# ----------------------------------------------------------------------------------
# 1. AI 101 slide deck
# ----------------------------------------------------------------------------------
W, H = 1920, 1080
M = 128          # side margin
FOOT_Y = 940     # footer baseline area; the slide size has a 96 px safe area
CONTENT_BOTTOM = 900


def slide_title(page, eyebrow, title, eyebrow_color="@accent"):
    return [
        {"type": "rich-text", "page": page, "name": "eyebrow", "markdown": f"[{eyebrow.upper()}]{{tracking=3}}",
         "size": 40, "font": "body", "color": eyebrow_color, "x": M, "y": 112},
        {"type": "text", "page": page, "name": "title", "text": title, "size": 78, "font": "heading",
         "color": "@ink", "x": M, "y": 168},
    ]


def build_deck():
    log("== deck")
    src = fresh(OUT / "ai-101-deck.vixl")
    with timed("deck: create + fonts"):
        p, info = brand_document(purpose="slides", seed=101)
    log("  creation:", json.dumps(info.get("creation"))[:300])
    ops = [
        {"type": "type-scale", "base": 40, "ratio": 1.25},   # 32 40 50 62 78 98 122
        # --- masters ---------------------------------------------------------------
        {"type": "master", "action": "add", "name": "std", "background": "@background"},
        {"type": "solid", "name": "rail", "color": "@accent", "x": 0, "y": 0, "width": 16, "height": H},
        {"type": "solid", "name": "footer-rule", "color": "@surface", "x": M, "y": FOOT_Y - 14,
         "width": W - 2 * M, "height": 2},
        {"type": "text", "name": "footer", "text": "AI 101  ·  A practical introduction", "size": 26,
         "font": "body", "color": "@muted", "x": M, "y": FOOT_Y},
        {"type": "text", "name": "page-number", "text": "${page} / ${pages}", "size": 26, "font": "body",
         "color": "@muted", "x": W - M - 120, "y": FOOT_Y},
        {"type": "constrain", "target": "page-number", "constraints": {"right": f"canvas.right-{M}"}},
        {"type": "master", "action": "add", "name": "dark", "background": "@ink"},
        {"type": "solid", "name": "rail", "color": "@amber", "x": 0, "y": 0, "width": 16, "height": H},
        {"type": "text", "name": "page-number", "text": "${page} / ${pages}", "size": 26, "font": "body",
         "color": "#aab2c8", "x": W - M - 120, "y": FOOT_Y},
        {"type": "constrain", "target": "page-number", "constraints": {"right": f"canvas.right-{M}"}},
    ]
    r = p.apply(ops, detail="compact")
    if r.get("warnings"):
        log("  master warnings:", r["warnings"])

    pages = []

    # --- 1 cover ---------------------------------------------------------------------
    pages.append([
        {"type": "page", "action": "add", "name": "cover", "master": "dark",
         "notes": "Welcome. This is a 30-minute, no-jargon introduction. Ask everyone to keep one task "
                  "from their own work in mind; we will try it at the end."},
        {"type": "rich-text", "page": "cover", "name": "eyebrow", "markdown": "[WORKSHOP  ·  SESSION 1]{tracking=4}",
         "size": 40, "font": "body", "color": "#9fb4ff", "x": M, "y": 270},
        {"type": "text", "page": "cover", "name": "title", "text": "AI 101", "size": 200,
         "font": "heading", "color": "#ffffff", "x": M - 10, "y": 330},
        {"type": "text", "page": "cover", "name": "subtitle",
         "text": "What it is, how it works, and how to use it well",
         "size": 62, "font": "lexend-400", "color": "#e7eaf3", "x": M, "y": 590},
        {"type": "solid", "page": "cover", "name": "cover-rule", "color": "@amber", "x": M, "y": 720,
         "width": 160, "height": 8},
        {"type": "text", "page": "cover", "name": "presenter",
         "text": "Teach  ·  Explore  ·  Demystify  ·  Try it", "size": 40, "font": "body",
         "color": "#aab2c8", "x": M, "y": 770},
    ])

    # --- 2 what we mean by AI (nested boxes) --------------------------------------------
    pg = [
        {"type": "page", "action": "add", "name": "terms", "master": "std",
         "notes": "Nested boxes: every large language model is generative AI, every generative model is "
                  "machine learning, and machine learning is one way of doing AI. In everyday speech "
                  "people say 'AI' for all of them."},
        *slide_title("terms", "Start here", "What we mean by “AI”"),
    ]
    nest = [("ai", "Artificial intelligence", "computers doing tasks we link with human thinking", "@surface", "@ink"),
            ("ml", "Machine learning", "learns patterns from examples, not hand-written rules", "#d9dff2", "@ink"),
            ("gen", "Generative AI", "creates new text, images, audio or code", "#b7c5ee", "@ink"),
            ("llm", "Large language models", "e.g. ChatGPT, Claude, Gemini", "@accent", "#ffffff")]
    top, band, pad_x, pad_b = 320, 100, 56, 28
    total_h = 520
    for i, (key, name, desc, fill, color) in enumerate(nest):
        bx = M + i * pad_x
        by_ = top + i * band
        bw = W - 2 * M - 2 * i * pad_x
        bh = total_h - i * (band + pad_b)
        pg += [
            {"type": "shape", "page": "terms", "shape": "rectangle", "name": f"{key}-box",
             "x": bx, "y": by_, "width": bw, "height": bh, "fill": fill},
            {"type": "rich-text", "page": "terms", "name": f"{key}-text",
             "markdown": f"**{name}**  [— {desc}]{{color={'#e7eaf3' if key == 'llm' else BRAND['muted']}}}",
             "size": 40, "color": color, "font": "body", "x": bx + 36, "y": by_ + 30},
        ]
    pages.append(pg)

    # --- 3 a short history ---------------------------------------------------------------
    hist = [("1956", "“Artificial intelligence” named at Dartmouth"),
            ("1997", "Deep Blue beats chess champion Kasparov"),
            ("2012", "AlexNet sparks the deep-learning boom"),
            ("2016", "AlphaGo beats Go champion Lee Sedol"),
            ("2017", "The Transformer architecture is published"),
            ("2022", "ChatGPT brings chatbots to everyone")]
    pg = [
        {"type": "page", "action": "add", "name": "history", "master": "std",
         "notes": "AI is not new: the field is about 70 years old. 1956: the Dartmouth summer workshop. "
                  "1997: IBM Deep Blue. 2012: AlexNet wins ImageNet. 2016: DeepMind AlphaGo. 2017: "
                  "'Attention Is All You Need'. November 2022: ChatGPT. What changed recently is scale "
                  "(data and computing power) plus the Transformer."},
        *slide_title("history", "Not as new as it looks", "Seventy years in six moments"),
        {"type": "solid", "page": "history", "name": "timeline-rule", "color": "@ink", "x": M, "y": 494,
         "width": W - 2 * M, "height": 4},
    ]
    colw = (W - 2 * M) / 6
    for i, (year, text) in enumerate(hist):
        cx = round(M + i * colw)
        last = year == "2022"
        pg += [
            {"type": "shape", "page": "history", "shape": "ellipse", "name": f"dot-{year}", "x": cx,
             "y": 480, "width": 32, "height": 32, "fill": "@amber" if last else "@accent"},
            {"type": "text", "page": "history", "name": f"year-{year}", "text": year, "size": 62,
             "font": "heading", "color": "@amber-text" if last else "@accent", "x": cx, "y": 380},
            {"type": "rich-text", "page": "history", "name": f"event-{year}", "markdown": text, "size": 36,
             "font": "body", "color": "@ink", "x": cx, "y": 550, "width": round(colw) - 36},
        ]
    pages.append(pg)

    # --- 4 diagram: how an LLM answers -----------------------------------------------------
    nodes = [{"id": "Prompt", "label": "Your prompt", "kind": "terminator"},
             {"id": "Tok", "label": "Split into tokens"},
             {"id": "Model", "label": "Score every possible next token"},
             {"id": "Add", "label": "Add one likely token"},
             {"id": "Done", "label": "Done?", "kind": "decision"},
             {"id": "Answer", "label": "Answer", "kind": "terminator"}]
    edges = [["Prompt", "Tok"], ["Tok", "Model"], ["Model", "Add"], ["Add", "Done"],
             {"from": "Done", "to": "Model", "label": "no, repeat", "from_port": "bottom", "to_port": "bottom"},
             {"from": "Done", "to": "Answer", "label": "yes"}]
    pages.append([
        {"type": "page", "action": "add", "name": "how-it-works", "master": "std", "transition": "fade",
         "notes": "The model never looks an answer up. It splits your prompt into tokens, scores every "
                  "possible next token, adds a likely one, and repeats until it decides to stop. That is "
                  "why answers sound fluent even when they are wrong."},
        *slide_title("how-it-works", "Under the hood", "How a language model answers"),
        {"type": "diagram", "page": "how-it-works", "name": "llm-flow", "nodes": nodes, "edges": edges,
         "direction": "LR", "x": M, "y": 330, "width": W - 2 * M, "height": 380, "font": "body",
         "size": 33, "rank_gap": 40},
        {"type": "rich-text", "page": "how-it-works", "name": "flow-caption",
         "markdown": "A **token** is a chunk of text, often part of a word. The loop runs once per token, "
                     "so a long answer is thousands of small predictions.",
         "size": 40, "font": "body", "color": "@muted", "x": M, "y": 760, "width": 1500},
    ])

    # --- 5 chart: next-token probabilities --------------------------------------------------
    pages.append([
        {"type": "page", "action": "add", "name": "next-token", "master": "std",
         "notes": "Illustrative numbers, not measured from a real model. The point: the model holds a "
                  "probability for every possible continuation, and sampling picks among them. A higher "
                  "'temperature' setting makes less likely words get picked more often."},
        *slide_title("next-token", "One step, up close", "“The cat sat on the …”"),
        {"type": "rich-text", "page": "next-token", "name": "chart-intro",
         "markdown": "Every candidate word gets a probability. The model then picks one: usually a "
                     "likely word, not always the top one.",
         "size": 40, "font": "body", "color": "@ink", "x": M, "y": 340, "width": 560},
        {"type": "rich-text", "page": "next-token", "name": "source",
         "markdown": "*Illustrative numbers for teaching, not output from a real model.*",
         "size": 32, "font": "body", "color": "@muted", "x": M, "y": 760, "width": 560},
        {"type": "chart", "page": "next-token", "name": "probs", "kind": "horizontal-bar",
         "x": 790, "y": 320, "width": 1002, "height": 580,
         "subtitle": "Next-word probability (illustrative)", "bar_gap": 0.35,
         "categories": ["mat", "floor", "sofa", "bed", "windowsill", "anything else"],
         "series": [{"name": "Probability", "values": [0.41, 0.18, 0.12, 0.08, 0.05, 0.16]}],
         "number_format": "0%", "colors": ["@accent"], "font_size": 42},
    ])

    # --- 6 strengths and limits ----------------------------------------------------------
    good = ("**Good at**\n- Drafting and rewriting\n- Summarising long documents\n"
            "- Explaining at your level\n- Brainstorming options\n- Writing and fixing code")
    weak = ("**Watch out for**\n- Confident mistakes\n- Out-of-date knowledge\n"
            "- Arithmetic without tools\n- Bias learned from data\n- Facts it cannot check")
    card_w = (W - 2 * M - 48) // 2
    pages.append([
        {"type": "page", "action": "add", "name": "strengths", "master": "std",
         "notes": "Confident mistakes are often called 'hallucinations'. Use it like a fast, well-read "
                  "assistant whose work you review, not like an oracle."},
        *slide_title("strengths", "Know the tool", "Strengths and limits"),
        {"type": "shape", "page": "strengths", "shape": "rectangle", "name": "good-card", "x": M, "y": 330,
         "width": card_w, "height": 480, "fill": "@surface"},
        {"type": "solid", "page": "strengths", "name": "good-bar", "color": "@teal", "x": M, "y": 330,
         "width": card_w, "height": 12},
        {"type": "rich-text", "page": "strengths", "name": "good-list", "markdown": good, "size": 40,
         "font": "body", "color": "@ink", "x": M + 56, "y": 386, "width": card_w - 112, "paragraph_spacing": 10},
        {"type": "shape", "page": "strengths", "shape": "rectangle", "name": "weak-card", "x": M + card_w + 48,
         "y": 330, "width": card_w, "height": 480, "fill": "@surface"},
        {"type": "solid", "page": "strengths", "name": "weak-bar", "color": "@rose", "x": M + card_w + 48,
         "y": 330, "width": card_w, "height": 12},
        {"type": "rich-text", "page": "strengths", "name": "weak-list", "markdown": weak, "size": 40,
         "font": "body", "color": "@ink", "x": M + card_w + 104, "y": 386, "width": card_w - 112,
         "paragraph_spacing": 10},
    ])

    # --- 7 quote ----------------------------------------------------------------------------
    pages.append([
        {"type": "page", "action": "add", "name": "quote", "master": "dark", "transition": "fade",
         "notes": "The closing line of Turing's 1950 paper in the journal Mind, the paper that proposed "
                  "the 'imitation game', now called the Turing test."},
        {"type": "text", "page": "quote", "name": "quote-mark", "text": "“", "size": 300,
         "font": "heading", "color": "@amber", "x": M - 12, "y": 110},
        {"type": "rich-text", "page": "quote", "name": "title",
         "markdown": "We can only see a short distance ahead, but we can see plenty there that needs to be done.",
         "size": 78, "font": "lexend-400", "color": "#ffffff", "x": M, "y": 350, "width": 1480,
         "line_height": 1.25},
        {"type": "text", "page": "quote", "name": "attribution",
         "text": "Alan Turing, “Computing Machinery and Intelligence”, 1950", "size": 40,
         "font": "body", "color": "#aab2c8", "x": M, "y": 760},
    ])

    # --- 8 prompting (2 x 2) ----------------------------------------------------------------
    tips = [("1", "Give context", "Who you are, who it is for, what you know."),
            ("2", "Be specific", "Length, format and tone: “5 bullets for a manager”."),
            ("3", "Show an example", "Paste a sample of the style you want."),
            ("4", "Iterate", "Treat the first answer as a draft.")]
    pg = [
        {"type": "page", "action": "add", "name": "prompting", "master": "std",
         "notes": "Live demo idea: ask for 'a summary', then for 'a 5-bullet summary for a busy manager, "
                  "plain language, flag anything uncertain'. Compare the two."},
        *slide_title("prompting", "Get better answers", "Four habits of a good prompt"),
    ]
    tw, th, gap = (W - 2 * M - 40) // 2, 260, 36
    for i, (n, head, body) in enumerate(tips):
        x = M + (i % 2) * (tw + 40)
        y = 330 + (i // 2) * (th + gap)
        pg += [
            {"type": "shape", "page": "prompting", "shape": "rectangle", "name": f"tip-{n}-card", "x": x,
             "y": y, "width": tw, "height": th, "fill": "@surface"},
            {"type": "text", "page": "prompting", "name": f"tip-{n}-num", "text": n, "size": 122,
             "font": "heading", "color": "@accent", "x": x + 48, "y": y + 50},
            {"type": "text", "page": "prompting", "name": f"tip-{n}-head", "text": head, "size": 50,
             "font": "heading", "color": "@ink", "x": x + 170, "y": y + 52},
            {"type": "rich-text", "page": "prompting", "name": f"tip-{n}-body", "markdown": body, "size": 40,
             "font": "body", "color": "@ink", "x": x + 170, "y": y + 126, "width": tw - 220},
        ]
    pages.append(pg)

    # --- 9 use it well + try this week ----------------------------------------------------
    pages.append([
        {"type": "page", "action": "add", "name": "use-it-well", "master": "std",
         "notes": "Close with the homework: pick one low-risk task, ask three different ways, and note "
                  "what worked on the 'My first AI experiment' worksheet."},
        *slide_title("use-it-well", "Your turn", "Use it well, starting this week"),
        {"type": "rich-text", "page": "use-it-well", "name": "rules",
         "markdown": "**Check** facts, numbers and quotes.\n"
                     "**Protect** personal and confidential data.\n"
                     "**Say so** when AI helped with shared work.\n"
                     "**Stay in charge:** you own the result.",
         "size": 50, "font": "body", "color": "@ink", "x": M, "y": 340, "width": 980,
         "paragraph_spacing": 28},
        {"type": "shape", "page": "use-it-well", "shape": "rectangle", "name": "try-card", "x": 1180,
         "y": 330, "width": W - M - 1180, "height": 420, "fill": "@accent"},
        {"type": "rich-text", "page": "use-it-well", "name": "try-text",
         "markdown": "**Try this week**\n1. Pick one low-risk task.\n2. Ask three different ways.\n"
                     "3. Note what worked.",
         "size": 40, "font": "body", "color": "#ffffff", "x": 1236, "y": 386, "width": W - M - 1180 - 112,
         "paragraph_spacing": 22},
    ])

    # --- 10 hidden backup ------------------------------------------------------------------
    pages.append([
        {"type": "page", "action": "add", "name": "backup-terms", "master": "std", "hidden": True,
         "notes": "Backup slide for vocabulary questions. Hidden: left out of PDF/HTML and not counted."},
        *slide_title("backup-terms", "Backup", "Words you will hear"),
        {"type": "rich-text", "page": "backup-terms", "name": "terms-list",
         "markdown": "**Token**: a chunk of text, often part of a word.\n"
                     "**Training**: tuning a model on example data.\n"
                     "**Prompt**: the instructions and context you give.\n"
                     "**Hallucination**: a fluent answer that is not true.\n"
                     "**Context window**: how much text it can consider at once.",
         "size": 40, "font": "body", "color": "@ink", "x": M, "y": 340, "width": 1500,
         "paragraph_spacing": 18},
    ])

    with timed("deck: build pages"):
        for i, batch in enumerate(pages, 1):
            r = p.apply(batch, detail="compact")
            if r.get("warnings"):
                log(f"  page {i} warnings:", r["warnings"])
            if r.get("diagram"):
                log("  diagram:", json.dumps(r["diagram"])[:300])
    p.save(str(src))
    return p, src


def finish_deck(p, src):
    with timed("deck: check --checks deck"):
        rep = p.check(checks=["deck"])
    summarize(rep, "deck")
    # A small requirement suite per content page (the page must be active for a suite).
    suite = {"description": "AI 101 slide requirements", "rules": [
        {"id": "title-contrast", "kind": "contrast", "target": "title", "minimum": 4.5},
        {"id": "title-dominates", "kind": "hierarchy", "targets": ["title", "eyebrow"], "ratio": 1.25},
        {"id": "title-inside-safe", "kind": "relation", "target": "title", "to": "canvas", "position": "inside",
         "minimum": 96}]}
    chart_suite = {"description": "Chart numbers are labelled illustrative", "rules": [
        {"id": "illustrative-note", "kind": "count", "target": "source", "minimum": 1, "maximum": 1}]}
    view = p.clone()
    for page in ("terms", "history", "how-it-works", "next-token", "strengths", "prompting", "use-it-well"):
        view.apply([{"type": "page", "action": "select", "page": page}])
        res = view.check_suite(suite)
        bad = [x for x in res.get("results", []) if x.get("status") != "passed"]
        if page == "next-token":
            bad += [x for x in view.check_suite(chart_suite).get("results", []) if x.get("status") != "passed"]
        log(f"  suite {page}: " + ("passed" if not bad else "; ".join(f"{x['id']}={x['status']}" for x in bad)))
    with timed("deck: contact sheet"):
        p.export(str(OUT / "_inspect" / "deck-sheet.png"), page="all", width=640, columns=3, overwrite=True)
    exports = {}
    for ext in ("pdf", "pptx", "html"):
        out = OUT / f"ai-101-deck.{ext}"
        with timed(f"deck: export {ext}"):
            text, _ = run_cli("-p", src.name, "export", out.name, "--overwrite")
        rep = json.loads(text)
        keep = {k: rep[k] for k in ("page_size", "content", "raster_fallbacks", "warnings", "charts",
                                    "fonts_not_embedded", "slides", "notes", "bytes") if k in rep}
        log(f"  {ext}:", json.dumps(keep)[:900])
        exports[ext] = out
    return exports


# ----------------------------------------------------------------------------------
# 2. Two-page Letter handout: "What is AI, really?"
# ----------------------------------------------------------------------------------
ARTICLE = """## The short answer
Artificial intelligence (AI) is a broad name for computer systems that do things we usually link with human thinking: recognising speech, translating, spotting patterns, writing. Most of what people call AI today is *machine learning*: instead of following rules a programmer wrote by hand, the system learns patterns from a very large number of examples.
## How the learning works
Imagine building a spam filter. Rather than listing every spammy phrase, you show the system thousands of emails labelled “spam” or “not spam”. It adjusts millions of internal numbers, called *parameters*, until its guesses match the labels as often as possible. That adjustment is called *training*. Once trained, the same model can judge emails it has never seen.
## What makes chatbots different
Large language models (LLMs), the technology behind chatbots such as ChatGPT, Claude and Gemini, are trained on a huge amount of text with one simple goal: predict the next piece of text. A piece is called a *token*, often a word or part of a word. To answer you, the model predicts one token, adds it to the conversation and repeats, thousands of times. Further training with human feedback teaches it to follow instructions and to decline some requests.
## Why it can be wrong
An LLM produces the most plausible continuation, not a checked fact, so it can state false things fluently. These errors are often called *hallucinations*. Its knowledge stops at a training cut-off unless it is connected to search or to your documents, and it can repeat biases found in the text it learned from. None of this makes the tool useless. It means the output is a draft for you to review.
## What it is not
Today’s AI systems do not understand the world the way people do, have no feelings and have no goals of their own. They are powerful pattern machines. Treat one like a fast, well-read assistant: excellent at first drafts, explanations and options, and in need of a human editor.
## Getting started well
Pick a task where a mistake is cheap: summarising a public article, brainstorming names for a project, or explaining a concept at your level. Give context, say what format you want, and ask follow-up questions. Check anything factual before you use it, and keep personal or confidential information out of tools your organisation has not approved."""

GLOSSARY = [
    ("Algorithm", "a precise set of steps a computer follows."),
    ("Machine learning", "learning patterns from examples instead of hand-written rules."),
    ("Model", "the trained system that makes predictions."),
    ("Parameters", "the internal numbers training adjusts; large models have billions."),
    ("Training data", "the examples a model learns from."),
    ("Token", "a chunk of text, often part of a word."),
    ("Prompt", "the instructions and context you give a model."),
    ("Context window", "how much text a model can consider at once."),
    ("Hallucination", "a fluent answer that is not true."),
    ("Bias", "unfair patterns a model picks up from its data."),
]

RESOURCE_URL = "https://www.elementsofai.com/"


def build_handout():
    log("== handout")
    src = fresh(OUT / "what-is-ai-handout.vixl")
    with timed("handout: create + fonts"):
        p, info = brand_document(purpose="document", seed=202)
    log("  creation:", json.dumps(info.get("creation"))[:400])
    cw, ch = p.state["canvas"]["width"], p.state["canvas"]["height"]   # 2550 x 3300 at 300 dpi
    m = 225                      # 0.75 in margins
    inner = cw - 2 * m
    body = 44                    # about 10.5 pt at 300 dpi
    gutter = 75
    colw = (inner - gutter) // 2
    ops = [
        {"type": "type-scale", "base": body, "ratio": 1.25},
        {"type": "master", "action": "add", "name": "page", "background": "@background"},
        {"type": "solid", "name": "top-bar", "color": "@accent", "x": 0, "y": 0, "width": cw, "height": 36},
        {"type": "solid", "name": "footer-rule", "color": "@surface", "x": m, "y": ch - 210, "width": inner,
         "height": 3},
        {"type": "text", "name": "footer", "size": 35, "font": "body", "color": "@muted", "x": m, "y": ch - 180,
         "text": "AI literacy packet  ·  Handout 1: What is AI, really?"},
        {"type": "text", "name": "page-number", "size": 35, "font": "body", "color": "@muted", "x": cw - m - 200,
         "y": ch - 180, "text": "Page ${page} of ${pages}"},
        {"type": "constrain", "target": "page-number", "constraints": {"right": f"canvas.right-{m}"}},
        {"type": "page", "action": "add", "name": "p1", "master": "page"},
        {"type": "rich-text", "name": "eyebrow", "markdown": "[AI LITERACY PACKET  ·  HANDOUT 1]{tracking=4}",
         "size": 44, "font": "body", "color": "@accent", "x": m, "y": 230},
        {"type": "text", "name": "title", "text": "What is AI, really?", "size": 172, "font": "heading",
         "color": "@ink", "x": m - 6, "y": 300},
        {"type": "rich-text", "name": "standfirst", "font": "lexend-400", "size": 69, "color": "@ink",
         "markdown": "A plain-language guide to what today’s AI does, how it learns, where it goes "
                     "wrong, and how to start using it well.",
         "x": m, "y": 530, "width": 2000, "line_height": 1.3},
        # the diagram band
        {"type": "shape", "shape": "rectangle", "name": "diagram-panel", "x": m, "y": 800, "width": inner,
         "height": 660, "fill": "@surface"},
        {"type": "text", "name": "diagram-title", "text": "From examples to answers", "size": 55,
         "font": "heading", "color": "@ink", "x": m + 60, "y": 850},
        {"type": "rich-text", "name": "diagram-caption", "size": body, "font": "body", "color": "@muted",
         "markdown": "Top row: **training**, done once by the developer. Bottom row: what happens "
                     "**each time you ask**.", "x": m + 60, "y": 930, "width": inner - 120},
        {"type": "diagram", "name": "two-phases", "direction": "LR", "font": "body", "size": 30,
         "x": m + 60, "y": 1040, "width": inner - 120, "height": 380,
         "nodes": [{"id": "examples", "label": "Example text", "kind": "database"},
                   {"id": "adjust", "label": "Adjust parameters"},
                   {"id": "model", "label": "Trained model", "color": "@accent"},
                   {"id": "prompt", "label": "Your prompt", "kind": "terminator"},
                   {"id": "draft", "label": "Draft answer"},
                   {"id": "check", "label": "You check it", "kind": "terminator"}],
         "edges": [["examples", "adjust"], ["adjust", "model"], ["prompt", "model"], ["model", "draft"],
                   ["draft", "check"]]},
        # the article flows through two columns on each page
        {"type": "text-flow", "name": "article", "markdown": ARTICLE, "size": body, "font": "body",
         "color": "@ink", "keep_together": False, "orphans": 2, "widows": 2,
         # paragraph_spacing > 0 makes the flow overfill frames (see NOTES.md); headings separate sections
         # spacing 2: a markdown flow otherwise sets about 2x leading (see NOTES.md)
         "spacing": 2,
         "frames": [{"x": m, "y": 1560, "width": inner, "height": ch - 210 - 80 - 1560, "columns": 2,
                     "gutter": gutter, "page": "p1"}]},
    ]
    # A space_before on the headings would also apply when a heading starts a column, pushing
    # that column's first line below its neighbour's (see NOTES.md), so headings stay tight.
    with timed("handout: page 1"):
        r = p.apply(ops, detail="compact")
    log("  flow p1:", json.dumps(r.get("text_flow"))[:500])
    log("  diagram:", json.dumps(r.get("diagram"))[:400])
    if r.get("warnings"):
        log("  warnings:", r["warnings"])

    gl_md = "\n".join(f"**{t}**: {d}" for t, d in GLOSSARY)
    ops2 = [
        {"type": "page", "action": "add", "name": "p2", "master": "page"},
        {"type": "text-flow", "name": "article", "action": "add-frame", "x": m, "y": 230, "width": inner,
         "height": 700, "columns": 2, "gutter": gutter, "page": "p2"},
        {"type": "shape", "page": "p2", "shape": "rectangle", "name": "glossary-panel", "x": m, "y": 950,
         "width": colw + 40, "height": 1800, "fill": "@surface"},
        {"type": "text", "page": "p2", "name": "glossary-title", "text": "Glossary", "size": 69, "font": "heading",
         "color": "@ink", "x": m + 60, "y": 1010},
        {"type": "rich-text", "page": "p2", "name": "glossary", "markdown": gl_md, "size": body, "font": "body",
         "color": "@ink", "x": m + 60, "y": 1130, "width": colw - 80, "paragraph_spacing": 22},
        {"type": "text", "page": "p2", "name": "next-title", "text": "Keep exploring", "size": 69,
         "font": "heading", "color": "@ink", "x": m + colw + gutter + 40, "y": 1010},
        {"type": "rich-text", "page": "p2", "name": "next-body", "size": body, "font": "body", "color": "@ink",
         "markdown": "**Elements of AI** is a free online course for non-experts, created by the University "
                     "of Helsinki and MinnaLearn. No maths or programming needed.\n"
                     "Scan the code or visit [elementsofai.com]{color=@accent bold}",
         "x": m + colw + gutter + 40, "y": 1130, "width": colw - 40, "paragraph_spacing": 22},
        {"type": "qr", "page": "p2", "name": "course-qr", "data": RESOURCE_URL, "size": 520, "error": "M",
         "x": m + colw + gutter + 40, "y": 1520},
        {"type": "shape", "page": "p2", "shape": "rectangle", "name": "try-panel", "x": m + colw + gutter + 40,
         "y": 2140, "width": colw - 40, "height": 610, "fill": "@accent"},
        {"type": "rich-text", "page": "p2", "name": "try-body", "size": body, "font": "body", "color": "#ffffff",
         "markdown": "**Try it in five minutes**\n1. Ask an AI tool to explain a topic you know well.\n"
                     "2. Spot one thing it got wrong or left out.\n3. Ask it to fix that, and compare.",
         "x": m + colw + gutter + 100, "y": 2200, "width": colw - 160, "paragraph_spacing": 16},
    ]
    with timed("handout: page 2"):
        r = p.apply(ops2, detail="compact")
    log("  flow p2:", json.dumps(r.get("text_flow"))[:600])
    if r.get("warnings"):
        log("  warnings:", r["warnings"])
    # Fit both panels on page 2 to the taller of the glossary text and the QR column.
    gb = p.inspect("glossary")["resolved_bounds"]
    tb = p.inspect("try-body")["resolved_bounds"]
    bottom = max(gb[1] + gb[3], tb[1] + tb[3]) + 70
    p.apply([{"type": "resize", "page": "p2", "target": "glossary-panel", "width": colw + 40, "height": bottom - 950},
             {"type": "resize", "page": "p2", "target": "try-panel", "width": colw - 40, "height": bottom - 2140}])
    strip_y = bottom + 70
    p.apply([
        {"type": "solid", "page": "p2", "name": "trust-rule", "color": "@amber", "x": m, "y": strip_y,
         "width": 12, "height": ch - 300 - strip_y},
        {"type": "text", "page": "p2", "name": "trust-title", "text": "Before you trust an answer, ask:",
         "size": 55, "font": "heading", "color": "@ink", "x": m + 60, "y": strip_y},
        {"type": "rich-text", "page": "p2", "name": "trust-body", "size": body, "font": "body", "color": "@ink",
         "markdown": "1. Where could this be wrong?\n2. How can I check it?\n3. What happens if it is wrong?",
         "x": m + 60, "y": strip_y + 90, "width": inner - 60, "paragraph_spacing": 8},
    ])
    p.save(str(src))
    return p, src


def finish_handout(p, src):
    with timed("handout: check"):
        rep = p.check(checks=["bounds", "overlap", "contrast", "fonts", "flow", "diagram", "codes", "blanks"])
    summarize(rep, "handout (page 1)")
    rep = p.check(page="p2", checks=["bounds", "overlap", "contrast", "fonts", "flow", "codes", "blanks"])
    summarize(rep, "handout (page 2)")
    p.export(str(OUT / "_inspect" / "handout-sheet.png"), page="all", width=900, columns=2, overwrite=True)
    out = OUT / "what-is-ai-handout.pdf"
    with timed("handout: export vector pdf"):
        text, _ = run_cli("-p", src.name, "export", out.name, "--overwrite")
    rep = json.loads(text)
    log("  pdf:", json.dumps({k: rep.get(k) for k in ("page_size", "content", "raster_fallbacks", "bytes")}))
    pdf_pages_to_png(out, "handout-pdf", scale=1.0)


# ----------------------------------------------------------------------------------
# 3. Fillable worksheet: "My first AI experiment", filled from a CSV
# ----------------------------------------------------------------------------------
FORM_ROWS = [
    {"full_name": "Priya Raman", "team_code": "OP-114", "date": "2026-10-12", "tool": "Claude",
     "task": "Summarise a 12-page public consultation into five bullet points for my manager.",
     "risk": "low",
     "prompt_first": "Summarise this document.",
     "prompt_better": "You are helping a busy operations manager. Summarise the attached public consultation in "
                      "five plain-language bullets, then list two questions it leaves open. Flag anything you are unsure of.",
     "what_changed": "The second prompt gave a usable summary first time. It flagged one statistic it could not verify; "
                     "the source showed a different figure, so I corrected it.",
     "rating": "4", "minutes_saved": "35", "checked_facts": "yes", "no_personal_data": "yes", "use_again": "yes"},
    {"full_name": "Marcus Lee", "team_code": "FN-207", "date": "2026-10-13", "tool": "ChatGPT",
     "task": "Draft three subject lines for the quarterly newsletter.",
     "risk": "low",
     "prompt_first": "Write subject lines for our newsletter.",
     "prompt_better": "Write six subject lines under 50 characters for a finance team newsletter about new expense rules. "
                      "Friendly, no puns, no exclamation marks.",
     "what_changed": "Adding the audience and the constraints removed the generic options. I combined two of them.",
     "rating": "5", "minutes_saved": "15", "checked_facts": "yes", "no_personal_data": "yes", "use_again": "yes"},
    {"full_name": "Ana Souza", "team_code": "HR-031", "date": "2026-10-14", "tool": "Gemini",
     "task": "Explain the difference between machine learning and rules-based automation for a training slide.",
     "risk": "medium",
     "prompt_first": "What is machine learning?",
     "prompt_better": "Explain machine learning versus rules-based automation to new staff with no technical background, "
                      "in under 120 words, with one everyday example of each.",
     "what_changed": "Much clearer. I still rewrote the example to match our own systems and asked IT to review it.",
     "rating": "4", "minutes_saved": "20", "checked_facts": "yes", "no_personal_data": "yes", "use_again": "no"},
]


def build_form():
    log("== form")
    src = fresh(OUT / "first-ai-experiment-form.vixl")
    with timed("form: create + fonts"):
        p, info = brand_document(purpose="form", seed=303)
    log("  creation:", json.dumps(info.get("creation"))[:300])
    cw, ch = p.state["canvas"]["width"], p.state["canvas"]["height"]
    m = 225
    inner = cw - 2 * m
    lab = 38          # label size (about 9 pt)
    fh = 100          # single-line field height (24 pt)
    ops = [
        {"type": "form", "title": "My first AI experiment", "lang": "en-US", "entry_font": "embed"},
        {"type": "solid", "name": "top-bar", "color": "@accent", "x": 0, "y": 0, "width": cw, "height": 36},
        {"type": "rich-text", "name": "eyebrow", "markdown": "[AI LITERACY PACKET  ·  WORKSHEET]{tracking=4}",
         "size": 40, "font": "body", "color": "@accent", "x": m, "y": 200},
        {"type": "text", "name": "title", "text": "My first AI experiment", "size": 120, "font": "heading",
         "color": "@ink", "x": m - 4, "y": 262},
        {"type": "rich-text", "name": "intro", "size": 44, "font": "body", "color": "@muted",
         "markdown": "Pick one low-risk task, try two prompts, and note what changed. Type in this PDF or print it.",
         "x": m, "y": 430, "width": inner},
    ]
    y = 560

    def section(num, title):
        nonlocal y
        ops.extend([
            {"type": "solid", "name": f"sec-{num}-rule", "color": "@ink", "x": m, "y": y, "width": inner, "height": 4},
            {"type": "text", "name": f"sec-{num}-title", "text": f"{num}  {title}", "size": 50, "font": "heading",
             "color": "@ink", "x": m, "y": y + 24},
        ])
        y += 110

    def label(name, text, x, yy):
        ops.append({"type": "text", "name": name, "text": text, "size": lab, "font": "body", "color": "@ink",
                    "x": x, "y": yy})

    def field(name, kind, x, yy, w, h, label_layer, **kw):
        op = {"type": "field", "name": name, "kind": kind, "label_layer": label_layer, "x": x, "y": yy,
              "width": w, "height": h, "size": 40, "font": "body", "color": "@ink",
              "appearance": {"style": "box", "fill": "#ffffff", "stroke": BRAND["muted"], "stroke_width": 3}}
        op.update(kw)
        ops.append(op)

    col2 = m + inner // 2 + 30
    half = inner // 2 - 30
    third = (inner - 2 * 60) // 3
    # 1 About you
    section(1, "About you")
    label("name-label", "Full name *", m, y); label("team-label", "Team code (e.g. OP-114) *", col2, y)
    field("full_name", "text", m, y + 52, half, fh, "name-label", required=True, max_length=40)
    field("team_code", "text", col2, y + 52, half, fh, "team-label", required=True, max_length=6,
          pattern="[A-Z]{2}-[0-9]{3}", message="Two capital letters, a hyphen and three digits, e.g. OP-114")
    y += 52 + fh + 50
    label("date-label", "Date", m, y); label("tool-label", "Tool you used", col2, y)
    field("date", "date", m, y + 52, half, fh, "date-label", format={"display": "MM/DD/YYYY"})
    field("tool", "dropdown", col2, y + 52, half, fh, "tool-label", editable=True,
          options=["ChatGPT", "Claude", "Gemini", "Microsoft Copilot", "Other"])
    y += 52 + fh + 70
    # 2 Plan
    section(2, "Plan")
    label("task-label", "What task will you try? Keep it low-risk.", m, y)
    field("task", "multiline", m, y + 52, inner, 170, "task-label", max_length=160, required=True)
    y += 52 + 170 + 40
    ops.append({"type": "text", "name": "risk-label", "text": "If the AI gets it wrong, how much does it matter?",
                "size": lab, "font": "body", "color": "@ink", "x": m, "y": y})
    rx = m
    for opt, text in (("low", "Hardly at all"), ("medium", "Somewhat: I will check carefully"),
                      ("high", "A lot: pick another task")):
        ops.append({"type": "field", "name": f"risk-{opt}", "key": "risk", "kind": "radio", "option": opt,
                    "label": text, "x": rx, "y": y + 58, "width": 56, "height": 56,
                    **({"group_label": "How much a mistake matters"} if opt == "low" else {}),
                    "appearance": {"style": "box", "fill": "#ffffff", "stroke": BRAND["muted"], "stroke_width": 3,
                                   "mark": "dot", "mark_color": BRAND["accent"]}})
        ops.append({"type": "text", "name": f"risk-{opt}-text", "text": text, "size": lab, "font": "body",
                    "color": "@ink", "x": rx + 76, "y": y + 64})
        rx += {"low": 430, "medium": 840, "high": 0}[opt]
    y += 58 + 56 + 70
    # 3 Try
    section(3, "Try")
    label("p1-label", "Your first prompt, exactly as you typed it", m, y)
    field("prompt_first", "multiline", m, y + 52, inner, 170, "p1-label", max_length=160)
    y += 52 + 170 + 40
    label("p2-label", "Your improved prompt: add context, format, an example", m, y)
    field("prompt_better", "multiline", m, y + 52, inner, 240, "p2-label", max_length=260)
    y += 52 + 240 + 70
    # 4 Reflect
    section(4, "Reflect")
    label("changed-label", "What changed, and what did you have to fix?", m, y)
    field("what_changed", "multiline", m, y + 52, inner, 240, "changed-label", max_length=260)
    y += 52 + 240 + 40
    label("rating-label", "Usefulness, 1 to 5", m, y)
    label("minutes-label", "Minutes saved (estimate)", m + third + 60, y)
    field("rating", "number", m, y + 52, third, fh, "rating-label", format={"decimals": 0, "min": 1, "max": 5},
          message="Enter a whole number from 1 to 5")
    field("minutes_saved", "number", m + third + 60, y + 52, third, fh, "minutes-label",
          format={"decimals": 0, "min": 0, "max": 600})
    cx = m + 2 * (third + 60)
    for i, (key, text) in enumerate((("checked_facts", "I checked the facts"),
                                     ("no_personal_data", "I kept personal data out"),
                                     ("use_again", "I would use it again"))):
        yy = y + i * 64
        ops.append({"type": "field", "name": key, "kind": "checkbox", "label": text, "x": cx, "y": yy + 4,
                    "width": 50, "height": 50,
                    "appearance": {"style": "box", "fill": "#ffffff", "stroke": BRAND["muted"], "stroke_width": 3,
                                   "mark": "check", "mark_color": BRAND["accent"]}})
        ops.append({"type": "text", "name": f"{key}-text", "text": text, "size": lab, "font": "body",
                    "color": "@ink", "x": cx + 70, "y": yy + 8})
    y += 52 + fh + 60
    ops += [
        {"type": "solid", "name": "footer-rule", "color": "@surface", "x": m, "y": ch - 210, "width": inner,
         "height": 3},
        {"type": "text", "name": "footer", "size": 35, "font": "body", "color": "@muted", "x": m, "y": ch - 180,
         "text": "AI literacy packet  ·  Keep this sheet; bring it to session 2."},
    ]
    # Explicit tab order: reading order would visit the checkboxes (which start higher) before
    # the rating and minutes fields to their left.
    order = ["full_name", "team_code", "date", "tool", "task", "risk", "prompt_first", "prompt_better",
             "what_changed", "rating", "minutes_saved", "checked_facts", "no_personal_data", "use_again"]
    for op in ops:
        if op["type"] == "field":
            op["tab"] = order.index(op.get("key", op["name"])) + 1
    ops[0]["tab_order"] = "explicit"
    log(f"  layout ends at y={y} (footer rule at {ch - 210})")
    with timed("form: build"):
        r = p.apply(ops, detail="compact")
    if r.get("warnings"):
        log("  warnings:", r["warnings"])
    p.save(str(src))
    return p, src


def finish_form(p, src):
    with timed("form: check --checks form --sample worst"):
        rep = p.check(checks=["form"], sample="worst")
    summarize(rep, "form (worst)")
    with timed("form: check design"):
        rep = p.check()
    summarize(rep, "form (default checks)")
    run_cli("-p", src.name, "render", "--show-fields", "--out", "_inspect/form-fields.png", "--overwrite")
    out = OUT / "first-ai-experiment-form.pdf"
    with timed("form: export fillable pdf"):
        text, _ = run_cli("-p", src.name, "export", out.name, "--fillable", "--overwrite")
    rep = json.loads(text)
    log("  fillable:", json.dumps({k: rep.get(k) for k in ("fields", "entry_font", "warnings", "bytes")})[:700])
    # the CSV and the form-fill workflow
    data = OUT / "form-responses.csv"
    with data.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(FORM_ROWS[0]))
        w.writeheader()
        w.writerows(FORM_ROWS)
    combined = fresh(OUT / "form-responses-filled.pdf")
    req = OUT / "_form-fill-request.json"
    req.write_text(json.dumps({"data": data.name, "dry_run": True}))
    text, dt = run_cli("-p", src.name, "workflow", "form-fill", "--request", req.name)
    log(f"  form-fill dry run ({dt:.2f}s):", text[:600].replace("\n", " "))
    req.write_text(json.dumps({"data": data.name, "combine": combined.name}))
    with timed("form: form-fill workflow (3 rows, combined)"):
        text, dt = run_cli("-p", src.name, "workflow", "form-fill", "--request", req.name)
    log("  form-fill:", text[:600].replace("\n", " "))
    req.unlink()
    pdf_pages_to_png(combined, "form-filled", scale=1.0)
    pdf_pages_to_png(out, "form-blank", scale=1.0)


# ----------------------------------------------------------------------------------
# 4. One-page A4 policy checklist, print-ready, CMYK PDF
# ----------------------------------------------------------------------------------
CHECKLIST = {
    "Before you start": [
        "Use a tool your organisation has approved for the task.",
        "Decide what a good result looks like and who will check it.",
        "Remove names, contact details and client or patient data.",
    ],
    "While you work": [
        "Give context and ask for sources or reasoning you can verify.",
        "Treat every answer as a draft, not a decision.",
        "Stop if the output is offensive, biased or off-topic.",
    ],
    "Before you share": [
        "Check facts, figures, quotes and links against the source.",
        "Make sure the final wording and judgement are yours.",
        "Say that AI helped, where your team expects it.",
    ],
}
TRAFFIC = [
    ("teal", "GREEN", "Public", "Published web pages, press releases, general questions with no "
     "private detail. Fine in approved tools."),
    ("amber-text", "AMBER", "Internal", "Drafts, internal processes, figures that are not sensitive. "
     "Approved tools only, with care."),
    ("rose", "RED", "Confidential", "Names, health or HR records, client data, passwords, "
     "unreleased results. Never in AI tools unless your policy explicitly allows it."),
]


def build_policy():
    log("== policy")
    src = fresh(OUT / "responsible-ai-checklist.vixl")
    with timed("policy: create + fonts"):
        p, info = brand_document(size="a4", bleed=True, seed=404)
    c = p.state["canvas"]
    log("  canvas:", {k: c.get(k) for k in ("width", "height", "dpi", "bleed", "safe", "physical")})
    b = c["bleed"]                       # 35.5 px (3 mm)
    tw, th = 2480, 3508                  # A4 trim at 300 dpi
    x0 = round(b + 177)                  # 15 mm margins
    inner = tw - 2 * 177
    body = 42                            # 10 pt
    ops = [
        {"type": "type-scale", "base": body, "ratio": 1.25},
        {"type": "solid", "name": "hero", "color": "@ink", "x": 0, "y": 0, "width": c["width"], "height": round(b + 760)},
        {"type": "rich-text", "name": "eyebrow", "markdown": "[AI LITERACY PACKET  ·  WORKPLACE CHECKLIST]{tracking=4}",
         "size": 42, "font": "body", "color": "#9fb4ff", "x": x0, "y": round(b + 190)},
        {"type": "text", "name": "title", "text": "Responsible AI use at work", "size": 133, "font": "heading",
         "color": "#ffffff", "x": x0 - 4, "y": round(b + 250)},
        {"type": "rich-text", "name": "subtitle", "font": "lexend-400", "size": 58, "color": "#e7eaf3",
         "markdown": "Nine habits and one rule for everyday use of AI tools. A starting point: "
                     "adapt it to your organisation’s own policy.",
         "x": x0, "y": round(b + 450), "width": inner - 200, "line_height": 1.3},
        {"type": "solid", "name": "hero-accent", "color": "@amber", "x": x0, "y": round(b + 680), "width": 200,
         "height": 10},
        # The traffic-light rule
        {"type": "text", "name": "rule-title", "text": "The traffic-light rule for data", "size": 66,
         "font": "heading", "color": "@ink", "x": x0, "y": round(b + 880)},
        {"type": "rich-text", "name": "rule-intro", "size": body, "font": "body", "color": "@muted",
         "markdown": "Before you paste anything into an AI tool, decide which colour it is.",
         "x": x0, "y": round(b + 975), "width": inner},
    ]
    cardw = (inner - 2 * 50) // 3
    cy = round(b + 1060)
    for i, (sw, tag, head, text) in enumerate(TRAFFIC):
        x = x0 + i * (cardw + 50)
        ops += [
            {"type": "shape", "shape": "rectangle", "name": f"light-{tag.lower()}-card", "x": x, "y": cy,
             "width": cardw, "height": 600, "fill": "@surface"},
            {"type": "solid", "name": f"light-{tag.lower()}-bar", "color": f"@{sw}", "x": x, "y": cy,
             "width": cardw, "height": 16},
            {"type": "shape", "shape": "ellipse", "name": f"light-{tag.lower()}-dot", "x": x + 50, "y": cy + 70,
             "width": 64, "height": 64, "fill": f"@{sw}"},
            {"type": "rich-text", "name": f"light-{tag.lower()}-tag", "markdown": f"[{tag}]{{tracking=3}}",
             "size": body, "font": "heading", "color": f"@{sw}", "x": x + 140, "y": cy + 80},
            {"type": "text", "name": f"light-{tag.lower()}-head", "text": head, "size": 53, "font": "heading",
             "color": "@ink", "x": x + 50, "y": cy + 170},
            {"type": "rich-text", "name": f"light-{tag.lower()}-text", "markdown": text, "size": body,
             "font": "body", "color": "@ink", "x": x + 50, "y": cy + 250, "width": cardw - 100},
        ]
    # The checklist
    ly = cy + 600 + 130
    ops += [
        {"type": "text", "name": "list-title", "text": "Nine habits", "size": 66, "font": "heading",
         "color": "@ink", "x": x0, "y": ly},
        {"type": "rich-text", "name": "list-intro", "size": body, "font": "body", "color": "@muted",
         "markdown": "Tick them off until they are automatic.", "x": x0, "y": ly + 95, "width": inner},
    ]
    ly += 200
    colw = (inner - 2 * 60) // 3
    for i, (head, items) in enumerate(CHECKLIST.items()):
        x = x0 + i * (colw + 60)
        ops += [
            {"type": "solid", "name": f"col-{i}-rule", "color": "@accent", "x": x, "y": ly, "width": colw, "height": 6},
            {"type": "text", "name": f"col-{i}-head", "text": head, "size": 53, "font": "heading", "color": "@ink",
             "x": x, "y": ly + 36},
        ]
        iy = ly + 140
        for j, item in enumerate(items):
            ops += [
                {"type": "shape", "shape": "rectangle", "name": f"box-{i}-{j}", "x": x, "y": iy + 6,
                 "width": 44, "height": 44, "fill": "#ffffff", "stroke": "@ink", "stroke_width": 4},
                {"type": "rich-text", "name": f"item-{i}-{j}", "markdown": item, "size": body, "font": "body",
                 "color": "@ink", "x": x + 74, "y": iy, "width": colw - 74},
            ]
            iy += 240
    fy = ly + 140 + 3 * 240 + 40
    ops += [
        {"type": "shape", "shape": "rectangle", "name": "doubt-panel", "x": x0, "y": fy, "width": inner,
         "height": 230, "fill": "@accent"},
        {"type": "rich-text", "name": "doubt-text", "size": 53, "font": "body", "color": "#ffffff",
         "markdown": "**When in doubt, leave it out.** Ask your manager or your data-protection lead "
                     "before you paste it.",
         "x": x0 + 70, "y": fy + 50, "width": inner - 140},
        {"type": "text", "name": "footer", "size": 33, "font": "body", "color": "@muted", "x": x0,
         "y": round(b + th - 150),
         "text": "AI literacy packet  ·  Responsible AI use at work  ·  Review this checklist every six months."},
    ]
    with timed("policy: build"):
        r = p.apply(ops, detail="compact")
    if r.get("warnings"):
        log("  warnings:", r["warnings"])
    p.save(str(src))
    return p, src


def finish_policy(p, src):
    with timed("policy: check --checks print"):
        text, _ = run_cli("-p", src.name, "check", "--checks", "print")
    summarize(json.loads(text), "policy print")
    with timed("policy: check default"):
        rep = p.check()
    summarize(rep, "policy default")
    p.export(str(OUT / "_inspect" / "policy.png"), overwrite=True)
    out = OUT / "responsible-ai-checklist-cmyk.pdf"
    with timed("policy: export cmyk pdf"):
        text, _ = run_cli("-p", src.name, "export", out.name, "--cmyk", "--overwrite")
    rep = json.loads(text)
    log("  cmyk pdf:", json.dumps({k: rep.get(k) for k in ("page_size", "content", "content_reason", "color_space",
                                                            "raster_fallbacks", "warnings", "bytes")})[:700])
    pdf_pages_to_png(out, "policy-cmyk", scale=1.0)


# ----------------------------------------------------------------------------------
# 5. Certificate merged from a CSV with merge-impose
# ----------------------------------------------------------------------------------
CERT_ROWS = [
    {"name": "Priya Raman", "cohort": "Operations", "date": "October 14, 2026"},
    {"name": "Marcus Lee", "cohort": "Finance", "date": "October 14, 2026"},
    {"name": "Ana Souza", "cohort": "People & Culture", "date": "October 15, 2026"},
    {"name": "Dr. Oluwaseun Adebayo-Whitfield", "cohort": "Research", "date": "October 15, 2026"},
]


def build_certificate():
    log("== certificate")
    src = fresh(OUT / "certificate-template.vixl")
    with timed("certificate: create + fonts"):
        p, info = brand_document(width=2400, height=1500, dpi=300, seed=505)
    log("  canvas:", {k: p.state["canvas"].get(k) for k in ("width", "height", "dpi", "safe")})
    W2, H2 = 2400, 1500
    cx = {"center-x": "canvas.center-x"}
    ops = [
        {"type": "variable", "name": "name", "value": "Sample Participant"},
        {"type": "variable", "name": "cohort", "value": "Sample cohort"},
        {"type": "variable", "name": "date", "value": "January 1, 2026"},
        {"type": "shape", "shape": "rectangle", "name": "frame-outer", "x": 70, "y": 70, "width": W2 - 140,
         "height": H2 - 140, "fill": "none", "stroke": "@accent", "stroke_width": 10},
        {"type": "shape", "shape": "rectangle", "name": "frame-inner", "x": 100, "y": 100, "width": W2 - 200,
         "height": H2 - 200, "fill": "none", "stroke": "@accent", "stroke_width": 3},
        {"type": "rich-text", "name": "eyebrow", "markdown": "[CERTIFICATE OF COMPLETION]{tracking=8}", "size": 44,
         "font": "body", "color": "@accent", "x": 0, "y": 210},
        {"type": "constrain", "target": "eyebrow", "constraints": cx},
        {"type": "text", "name": "title", "text": "AI Literacy — Completed", "size": 120, "font": "heading",
         "color": "@ink", "x": 0, "y": 290},
        {"type": "constrain", "target": "title", "constraints": cx},
        {"type": "text", "name": "certifies", "text": "This certifies that", "size": 48, "font": "body",
         "color": "@muted", "x": 0, "y": 500},
        {"type": "constrain", "target": "certifies", "constraints": cx},
        {"type": "text", "name": "recipient", "text": "${name}", "size": 150, "font": "lexend-400",
         "color": "@ink", "x": 300, "y": 580, "align": "center"},
        {"type": "text-layout", "target": "recipient", "width": 1800, "height": 200, "fit": True},
        {"type": "solid", "name": "name-rule", "color": "@amber", "x": 700, "y": 800, "width": 1000, "height": 6},
        {"type": "rich-text", "name": "completed", "size": 48, "font": "body", "color": "@ink", "align": "center",
         "markdown": "has completed **AI 101: a practical introduction**, covering how AI works,\n"
                     "how to prompt well and how to use it responsibly.",
         "x": 300, "y": 850, "width": 1800, "line_height": 1.4},
        {"type": "solid", "name": "sig-rule-left", "color": "@ink", "x": 300, "y": 1200, "width": 700, "height": 3},
        {"type": "text", "name": "sig-left", "text": "Workshop facilitator", "size": 38, "font": "body",
         "color": "@muted", "x": 300, "y": 1220},
        {"type": "text", "name": "cohort-line", "text": "${cohort|default:Open cohort}  ·  ${date}",
         "size": 44, "font": "lexend-400", "color": "@ink", "x": 1400, "y": 1140},
        {"type": "constrain", "target": "cohort-line", "constraints": {"right": "canvas.right-300"}},
        {"type": "solid", "name": "sig-rule-right", "color": "@ink", "x": 1400, "y": 1200, "width": 700, "height": 3},
        {"type": "text", "name": "sig-right", "text": "Cohort and date", "size": 38, "font": "body",
         "color": "@muted", "x": 1400, "y": 1220},
        {"type": "constrain", "target": "sig-right", "constraints": {"right": "canvas.right-300"}},
        {"type": "shape", "shape": "ellipse", "name": "seal", "x": 1120, "y": 1110, "width": 160, "height": 160,
         "fill": "@accent"},
        {"type": "text", "name": "seal-text", "text": "AI\n101", "size": 44, "font": "heading", "color": "#ffffff",
         "align": "center", "within": "seal"},
    ]
    with timed("certificate: build"):
        r = p.apply(ops, detail="compact")
    if r.get("warnings"):
        log("  warnings:", r["warnings"])
    p.save(str(src))
    return p, src


def finish_certificate(p, src):
    rep = p.check()
    summarize(rep, "certificate template")
    p.export(str(OUT / "_inspect" / "certificate-template.png"), overwrite=True)
    data = OUT / "certificate-names.csv"
    with data.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(CERT_ROWS[0]))
        w.writeheader()
        w.writerows(CERT_ROWS)
    out = fresh(OUT / "certificates-print.pdf")
    sheet = fresh(OUT / "certificates-sheet.vixl")
    common = [src.name, "--data", data.name, "--size", "letter", "--cols", "1", "--rows", "2", "--gutter", "0.25",
              "--slug", "AI 101 certificates  {page}/{pages}  rows {first}-{last}", "--check", "design"]
    text, dt = run_cli("merge", *common, "--out", out.name, "--dry-run")
    rep = json.loads(text)
    log(f"  merge dry run ({dt:.2f}s):", json.dumps({k: rep.get(k) for k in ("layout", "report", "warnings")})[:900])
    with timed("certificate: merge-impose (4 rows, 2 sheets)"):
        text, dt = run_cli("merge", *common, "--out", out.name, "--sheet-document", sheet.name)
    rep = json.loads(text)
    log("  merge keys:", sorted(rep))
    log("  merge:", json.dumps({k: v for k, v in rep.items() if k not in ("report", "layout")})[:900])
    pdf_pages_to_png(out, "certificates", scale=1.0)


if __name__ == "__main__":
    parts = sys.argv[1:] or ["deck", "handout", "form", "policy", "certificate"]
    if "deck" in parts:
        finish_deck(*build_deck())
    if "handout" in parts:
        finish_handout(*build_handout())
    if "form" in parts:
        finish_form(*build_form())
    if "policy" in parts:
        finish_policy(*build_policy())
    if "certificate" in parts:
        finish_certificate(*build_certificate())
    log("timings:", TIMINGS)
