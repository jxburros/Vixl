"""The fourteen shots of "The Stack". Each function returns a ``Scene``; times are milliseconds.

The score runs at 100 BPM (a beat is 600 ms, a bar 2.4 s) and every shot is a whole number of bars.
Every fact on screen comes from the four repositories' own READMEs, changelogs, docs and tests; the
README next to this folder lists the source of each one.
"""
from __future__ import annotations

from film import (BODY, CODE_KEY, CODE_NUM, CODE_STR, DEEP, GOOD, HEAD, HERE, INK, LINE, MOCK, MONO,
                  MUTED, ONYX, PANEL, PAPER, RUNTIME, SEMI, SKY, STUDIO, WHITE, Scene, backdrop, caption,
                  centered, chip, ellipse, exit_all, glow, group, headline, image, kicker, rect, rel, rich,
                  shadow, text)

BAD = "#FF6B6B"
BAR = 2400
DURATIONS = {"01-open": 3 * BAR, "02-title": 2 * BAR, "03-studio": 5 * BAR, "04-runtime": 5 * BAR,
             "05-onyx": 4 * BAR, "06-mock": 4 * BAR, "07-stack": 5 * BAR, "08-control": 4 * BAR,
             "09-journal": 5 * BAR, "10-loops": 5 * BAR, "11-lessons": 5 * BAR, "12-numbers": 3 * BAR,
             "13-vixl": 3 * BAR, "14-end": 3 * BAR}
# The journal pages, where the drums drop out and the keys hold whole bars.
QUIET = ("09-journal", "11-lessons")
REPOS = [("AI Server Studio", STUDIO), ("JX Runtime", RUNTIME), ("Onyx Engine", ONYX), ("Mock-LLM", MOCK)]
ASSETS = HERE / "assets"


def cuts():
    out, t = [], 0
    for ms in DURATIONS.values():
        out.append(t)
        t += ms
    return out, t


def quiet_spans():
    starts, _ = cuts()
    names = list(DURATIONS)
    return [(starts[names.index(n)], starts[names.index(n)] + DURATIONS[n]) for n in QUIET]


def panel(name, x, y, w, h, fill=DEEP, stroke=LINE):
    return [rect(name, x, y, w, h, fill, 22, stroke, 2), shadow(name, 40, 18, 0.4)]


def line(name, x1, y1, x2, y2, color=LINE, width=3):
    return {"type": "pen", "name": name, "points": [[x1, y1], [x2, y2]], "closed": False, "smooth": False,
            "fill": "none", "stroke": color, "stroke_width": width}


def draw_on(sc, name, t, dur=500):
    sc.keys(name, "trim_end", [(0, 0), (t, 0), (t + dur, 100)], "ease-out-cubic")


def terminal(sc, prefix, lines, x, y, w, t, step=420, size=26, gap=1.6):
    """A terminal panel whose lines (each [(text, colour), ...]) type in one after another."""
    h = round(90 + len(lines) * size * gap)
    sc.add(panel(f"{prefix}-panel", x, y, w, h))
    for i, c in enumerate(("#FF5F57", "#FEBC2E", "#28C840")):
        sc.add(ellipse(f"{prefix}-dot{i}", x + 32 + i * 26, y + 30, 14, 14, c))
    sc.fade(f"{prefix}-panel", t - 300, dur=350, rise=16)
    for i in range(3):
        sc.fade(f"{prefix}-dot{i}", t - 300, dur=350)
    names = []
    for i, spans in enumerate(lines):
        name = f"{prefix}-l{i}"
        sc.add(rich(name, spans, x + 32, y + 64 + i * size * gap, size, w - 64, WHITE, MONO, line_height=1.2))
        sc.words(name, t + i * step, "typewriter", "char", min(step - 60, 360))
        names.append(name)
    return [f"{prefix}-panel"] + [f"{prefix}-dot{i}" for i in range(3)] + names


def quote(sc, name, value, source, x, y, t, width=1680, color=WHITE, accent=SKY, size=34):
    sc.add(rect(f"{name}-bar", x, y, 6, round(size * 2.3), accent, 3))
    sc.add(rich(name, [(f"“{value}”", None)], x + 30, y - 4, size, width - 30, color, SEMI, line_height=1.15))
    sc.add(text(f"{name}-src", source, x + 30, y + round(size * 1.45), 22, MUTED, MONO))
    sc.fade(f"{name}-bar", t, dur=300)
    sc.words(name, t + 100, "fade-up", "word", 380, 35)
    sc.fade(f"{name}-src", t + 900, dur=350)
    return [f"{name}-bar", name, f"{name}-src"]


def chips_row(sc, prefix, labels, x, y, t, size=24, fg=WHITE, bg=PANEL, stroke=LINE, gap=14, stagger=110):
    names = []
    for i, label in enumerate(labels):
        w = round(len(label) * size * 0.58 + 44)
        name = f"{prefix}{i}"
        sc.add(chip(name, label, x, y, size=size, fg=fg, bg=bg, font=SEMI, stroke=stroke, width=w))
        sc.pop(name, t + i * stagger, 320, 0.7)
        names.append(name)
        x += w + gap
    return names


def journal_page(sc, title, t=0):
    """A sheet of paper with a ruled margin; returns its layer names."""
    x, y, w, h = 150, 60, 1620, 960
    sc.add(rect("page", x, y, w, h, PAPER, 14), shadow("page", 60, 24, 0.5))
    sc.add(line("margin", x + 170, y, x + 170, y + h, "#E4A6A6", 2))
    for i in range(1, 14):
        sc.add(line(f"rule{i}", x + 20, y + 70 + i * 64, x + w - 20, y + 70 + i * 64, "#DCD4C2", 1))
    sc.add(text("page-kicker", "DEV JOURNAL", x + 200, y + 50, 22, "#A1622F", MONO))
    sc.add(rich("page-title", title, x + 200, y + 84, 54, w - 260, INK, HEAD))
    rules = [f"rule{i}" for i in range(1, 14)]
    for name in ["page", "margin"] + rules:
        sc.fade(name, t, dur=400)
    sc.keys("page", "translate-y", [(0, 40), (t, 40), (t + 600, 0)], "ease-out-cubic")
    sc.fade("page-kicker", t + 200, dur=300)
    sc.words("page-title", t + 300, "typewriter", "char", 700)
    return ["page", "margin", "page-kicker", "page-title"] + rules


# ----------------------------------------------------------------------------------------------- 1
def s01_open():
    sc = Scene("01-open", DURATIONS["01-open"])
    sc.add(backdrop(glow_at=(1500, 300)))
    sc.add(chip("date", "dev journal  ·  2026-10-12", 120, 150, size=24, fg=SKY, bg="#3575EE26", font=MONO))
    sc.fade("date", 200, dur=300)
    lines = [("l1", [("Four repositories.", None)], 300, 600, 100),
             ("l2", [("One stack.", None)], 420, 1500, 100),
             ("l3", [("The AI on your machine should answer to ", None), ("you.", SKY)], 600, 2700, 60)]
    for name, spans, y, t, size in lines:
        sc.add(rich(name, spans, 120, y, size, 1000, WHITE, HEAD, line_height=1.1))
        sc.words(name, t, "fade-up", "word", 500, 90)
    term = terminal(sc, "ls", [
        [("$ ", MUTED), ("ls ~/code", WHITE)],
        [("AI-Server-Studio/", STUDIO)],
        [("JX-Runtime/", RUNTIME)],
        [("Onyx-Engine/", ONYX)],
        [("Mock-LLM/", MOCK)],
    ], 1180, 330, 600, 1000, step=480, size=30)
    exit_all(sc, ["date", "l1", "l2", "l3"] + term, 6600)
    return sc


# ----------------------------------------------------------------------------------------------- 2
def s02_title():
    sc = Scene("02-title", DURATIONS["02-title"])
    sc.add(backdrop(glow_at=(520, 540), glow2_at=(1500, 900)))
    names = []
    for i, (label, color) in enumerate(REPOS):
        y = 250 + i * 150
        name = f"block{i}"
        sc.add(rect(f"{name}-bg", 180, y, 680, 120, f"{color}2E", 20, color, 3),
               rich(f"{name}-label", label, 180, y + 36, 44, 680, color, HEAD, "center"),
               group(name, [f"{name}-bg", f"{name}-label"]))
        t = 150 + (3 - i) * 260  # bottom block lands first
        sc.keys(name, "translate-y", [(0, -500), (t, -500), (t + 520, 0)], "ease-out-back")
        sc.fade(name, t, dur=250)
        names.append(name)
    sc.add(rich("title", [("The ", None), ("Stack", SKY)], 1000, 360, 150, 820, WHITE, HEAD))
    sc.words("title", 1300, "pop", "word", 450, 160)
    sc.add(rich("sub", "How four local-first projects fit together, and build each other.", 1004, 560, 40, 780,
                MUTED, BODY, line_height=1.25))
    sc.words("sub", 1900, "fade-up", "word", 400, 40)
    exit_all(sc, names + ["title", "sub"], 4300)
    return sc


# ----------------------------------------------------------------------------------------------- 3
def s03_studio():
    sc = Scene("03-studio", DURATIONS["03-studio"])
    sc.add(backdrop(glow_at=(1500, 250)))
    kicker(sc, "01  ·  AI SERVER STUDIO", STUDIO)
    headline(sc, [("One permissioned gateway ", None), ("for your private AI server.", STUDIO)])
    sc.add({"type": "frame", "name": "logo", "path": rel(ASSETS / "ai-server-studio-logo.png"), "x": 120,
            "y": 300, "width": 760, "height": 110, "fit": "fit"})
    sc.fade("logo", 700, dur=500, rise=16)
    facts = [("f0", "TypeScript · Express · SQLite · React · SSE"),
             ("f1", "web :8721 · backend :8720 · docker :8722"),
             ("f2", "Ollama · llama.cpp · vLLM · LM Studio · JX Runtime …")]
    for i, (name, value) in enumerate(facts):
        caption(sc, name, value, 124, 450 + i * 46, 1300 + i * 250, 26)
    sc.add(text("modes-label", "SEVEN WAYS TO WORK", 124, 640, 22, STUDIO, MONO))
    sc.fade("modes-label", 2400, dur=300)
    modes = chips_row(sc, "mode", ["Chat", "Code", "Create", "Intern", "Plan", "Job", "Browser"], 120, 684, 2600,
                      size=22)
    # Right: the gateway in miniature, devices in, engines out, cloud off until asked.
    gx, gy, gw = 1380, 560, 130
    sc.add(rect("gw", gx - gw, gy - 80, 2 * gw, 160, PANEL, 24, STUDIO, 3), shadow("gw", 40, 16, 0.4),
           centered("gw-label", "Gateway", gy - 40, 40, WHITE, HEAD, x=gx - gw, width=2 * gw),
           centered("gw-sub", "the only door", gy + 14, 24, MUTED, BODY, x=gx - gw, width=2 * gw))
    for name in ("gw", "gw-label", "gw-sub"):
        sc.pop(name, 1000, 450, 0.8)
    side = []
    for i, label in enumerate(("laptop", "desktop", "phone")):
        y = gy - 150 + i * 150
        sc.add(chip(f"dev{i}", label, 980, y - 24, size=22, fg=WHITE, bg=PANEL, font=SEMI, stroke=LINE, width=150))
        sc.add(line(f"in{i}", 1130, y, gx - gw, gy, LINE, 3))
        sc.fade(f"dev{i}", 1500 + i * 150, dur=300)
        draw_on(sc, f"in{i}", 1700 + i * 150)
        side += [f"dev{i}", f"in{i}"]
    for i, label in enumerate(("local models", "documents · memory", "tools · agents")):
        y = gy - 150 + i * 150
        sc.add(chip(f"eng{i}", label, 1640, y - 24, size=22, fg=WHITE, bg=PANEL, font=SEMI, stroke=LINE, width=230))
        sc.add(line(f"out{i}", gx + gw, gy, 1640, y, STUDIO, 3))
        sc.fade(f"eng{i}", 2300 + i * 150, dur=300)
        draw_on(sc, f"out{i}", 2100 + i * 150)
        side += [f"eng{i}", f"out{i}"]
    sc.add(chip("cloud", "cloud: off until you say so", 1170, 800, size=22, fg=MUTED, bg=DEEP, font=MONO,
                stroke=LINE, width=420))
    sc.fade("cloud", 3200, dur=400)
    q = quote(sc, "q", "Cloud escalation is always opt-in, always logged, always user-controlled.",
              "AI Server Studio · development-docs/coreIdentity.md", 120, 880, 4800, accent=STUDIO, size=36)
    exit_all(sc, ["kicker", "headline", "logo", "f0", "f1", "f2", "modes-label", "gw", "gw-label", "gw-sub", "cloud"]
             + modes + side + q, 11400)
    return sc


# ----------------------------------------------------------------------------------------------- 4
def s04_runtime():
    sc = Scene("04-runtime", DURATIONS["04-runtime"])
    sc.add(backdrop(glow_at=(400, 300), glow2_at=(1600, 900)))
    kicker(sc, "02  ·  JX RUNTIME", RUNTIME)
    headline(sc, [("The runtime executes. ", None), ("The application decides.", RUNTIME)])
    term = terminal(sc, "t", [
        [("$ ", MUTED), ("jx-runtime serve", WHITE)],
        [("✓ ", GOOD), ("listening on :8712 · OpenAI-compatible", MUTED)],
        [("GET  ", CODE_KEY), ("/v1/models", CODE_STR)],
        [("POST ", CODE_NUM), ("/v1/chat/completions", CODE_STR)],
        [("POST ", CODE_NUM), ("/v1/embeddings", CODE_STR)],
        [("GET  ", CODE_KEY), ("/runtime/audit", CODE_STR)],
        [("GET  ", CODE_KEY), ("/.well-known/jx-runtime", CODE_STR)],
    ], 120, 300, 820, 900, step=380, size=27)
    sc.add(text("sec-label", "SECURITY, ON BY DEFAULT", 1060, 300, 22, RUNTIME, MONO))
    sc.fade("sec-label", 2000, dur=300)
    cards = []
    items = [("scoped access keys", "jxr_…"), ("TLS with a pinnable fingerprint", "--tls"),
             ("pairing codes for a new device", "JX-XXXX-XXXX"), ("audit log · metrics · diagnostics", "/runtime/*")]
    for i, (label, code) in enumerate(items):
        y = 350 + i * 96
        name = f"sec{i}"
        sc.add(rect(f"{name}-bg", 1060, y, 740, 78, PANEL, 16, LINE, 2),
               ellipse(f"{name}-dot", 1100, y + 39, 16, 16, RUNTIME),
               text(f"{name}-label", label, 1130, y + 22, 27, WHITE, SEMI),
               rich(f"{name}-code", [(code, CODE_STR)], 1060, y + 26, 22, 715, MUTED, MONO, "right"),
               group(name, [f"{name}-bg", f"{name}-dot", f"{name}-label", f"{name}-code"]))
        sc.fade(name, 2200 + i * 300, dur=350)
        sc.slide(name, 2200 + i * 300, dx=60)
        cards.append(name)
    sc.add(text("be-label", "RUNS THE ENGINE YOU CHOOSE", 1060, 750, 22, RUNTIME, MONO))
    sc.fade("be-label", 3900, dur=300)
    backends = chips_row(sc, "be", ["llama.cpp", "Onyx", "MLX", "vLLM", "mock"], 1060, 794, 4100, size=24)
    q = quote(sc, "q", "Every automatic decision comes with a readable reason.", "JX Runtime · README.md",
              120, 920, 5800, accent=RUNTIME)
    exit_all(sc, ["kicker", "headline", "sec-label", "be-label"] + term + cards + backends + q, 11400)
    return sc


# ----------------------------------------------------------------------------------------------- 5
def s05_onyx():
    sc = Scene("05-onyx", DURATIONS["05-onyx"])
    sc.add(backdrop(glow_at=(1400, 500), glow2_at=(300, 900)))
    kicker(sc, "03  ·  ONYX ENGINE", ONYX)
    headline(sc, [("One process. One model. ", None), ("No surprises.", ONYX)])
    facts = ["C++ on a pinned, vendored llama.cpp",
             "OpenAI-compatible /v1, streaming with usage",
             "tool calls · json_schema output · batching",
             "CUDA · Vulkan · Metal · ROCm"]
    names = []
    for i, value in enumerate(facts):
        name = f"f{i}"
        sc.add(ellipse(f"{name}-dot", 134, 336 + i * 70, 14, 14, ONYX),
               text(name, value, 160, 318 + i * 70, 32, WHITE, BODY))
        sc.fade(f"{name}-dot", 700 + i * 260, dur=300)
        sc.fade(name, 700 + i * 260, dur=350, rise=12)
        names += [name, f"{name}-dot"]
    # Right: dual-engine mode, the same models served by two engines side by side.
    sc.add(rect("models", 1180, 300, 520, 90, PANEL, 18, LINE, 2),
           centered("models-label", "~/models  (shared)", 326, 30, MUTED, MONO, x=1180, width=520))
    sc.fade("models", 1200, dur=350)
    sc.fade("models-label", 1200, dur=350)
    for i, (label, port, color) in enumerate((("llama.cpp", ":8712", RUNTIME), ("Onyx Engine", ":8713", ONYX))):
        x = 1130 + i * 330
        name = f"eng{i}"
        sc.add(rect(f"{name}-bg", x, 520, 290, 160, f"{color}22", 22, color, 3),
               centered(f"{name}-label", label, 556, 34, WHITE, HEAD, x=x, width=290),
               centered(f"{name}-port", port, 614, 30, color, MONO, x=x, width=290),
               group(name, [f"{name}-bg", f"{name}-label", f"{name}-port"]),
               line(f"{name}-link", 1440, 390, x + 145, 520, color, 3))
        sc.pop(name, 1900 + i * 350, 420, 0.7)
        draw_on(sc, f"{name}-link", 1700 + i * 350)
        names += [name, f"{name}-link"]
    caption(sc, "cmd", "$ jx-runtime dual-engine setup", 1130, 720, 2800, 26, SKY)
    caption(sc, "cmd-note", "compare engines on your own GPU", 1130, 762, 3000, 24)
    q = quote(sc, "q", "onyx-engine never fetches a remote or local resource on a request's behalf.",
              "Onyx Engine · README.md", 120, 880, 4300, accent=ONYX)
    exit_all(sc, ["kicker", "headline", "models", "models-label", "cmd", "cmd-note"] + names + q, 9000)
    return sc


# ----------------------------------------------------------------------------------------------- 6
def s06_mock():
    sc = Scene("06-mock", DURATIONS["06-mock"])
    sc.add(backdrop(glow_at=(1500, 350)))
    kicker(sc, "04  ·  MOCK-LLM", MOCK)
    headline(sc, [("A test double for the contract. ", None), ("Not a model.", MOCK)])
    req = terminal(sc, "req", [
        [("POST ", CODE_NUM), ("/v1/chat/completions", CODE_STR)],
        [("X-Mock-Scenario: ", CODE_KEY), ("flaky-then-fine", CODE_STR)],
        [("model: ", CODE_KEY), ("mock-1", CODE_STR)],
    ], 120, 300, 760, 700, step=350, size=27)
    attempts = [("503", "service_unavailable", BAD), ("503", "service_unavailable", BAD), ("200", "ok", GOOD)]
    rows = []
    for i, (status, code, color) in enumerate(attempts):
        y = 320 + i * 100
        name = f"try{i}"
        sc.add(rect(f"{name}-bg", 1000, y, 800, 80, PANEL, 16, LINE, 2),
               text(f"{name}-n", f"attempt {i + 1}", 1030, y + 24, 26, MUTED, MONO),
               text(f"{name}-status", status, 1260, y + 18, 36, color, HEAD),
               text(f"{name}-code", code, 1360, y + 24, 26, WHITE, MONO),
               group(name, [f"{name}-bg", f"{name}-n", f"{name}-status", f"{name}-code"]))
        sc.fade(name, 1900 + i * 650, dur=300)
        sc.slide(name, 1900 + i * 650, dx=50)
        rows.append(name)
    caption(sc, "assert", "assert attempts == 3   ✓", 1000, 640, 3900, 28, GOOD)
    caption(sc, "nolist", "A test should not need:", 120, 770, 4500, 26, MUTED, BODY)
    needs = chips_row(sc, "need", ["an API key", "a downloaded model", "a GPU", "internet", "paid tokens", "luck"],
                      120, 816, 4700, size=24, fg=MOCK, bg=f"{MOCK}1F", stroke=None)
    caption(sc, "loud", "Unmatched requests fail loudly. Never a silent happy path.", 120, 930, 6000, 28, WHITE,
            SEMI)
    exit_all(sc, ["kicker", "headline", "assert", "nolist", "loud"] + req + rows + needs, 9000)
    return sc


# ----------------------------------------------------------------------------------------------- 7
def s07_stack():
    sc = Scene("07-stack", DURATIONS["07-stack"])
    sc.add(backdrop(glow_at=(700, 600), glow2_at=(1600, 200)))
    kicker(sc, "HOW IT FITS")
    headline(sc, [("One request, ", None), ("top to bottom.", SKY)])
    cx = 640
    names = []

    def tier(name, label, sub, y, color, w=760, t=0):
        sc.add(rect(f"{name}-bg", cx - w / 2, y, w, 110, f"{color}22", 22, color, 3),
               centered(f"{name}-label", label, y + 18, 38, WHITE, HEAD, x=cx - w / 2, width=w),
               centered(f"{name}-sub", sub, y + 66, 22, color, MONO, x=cx - w / 2, width=w),
               group(name, [f"{name}-bg", f"{name}-label", f"{name}-sub"]))
        sc.pop(name, t, 450, 0.85)
        names.append(name)

    devs = chips_row(sc, "dev", ["laptop", "desktop", "phone"], cx - 300, 290, 500, size=24)
    tier("studio", "AI Server Studio", "gateway · routing · audit  :8721", 400, STUDIO, t=900)
    tier("jx", "JX Runtime", "models · keys · TLS · pairing  :8712", 610, RUNTIME, t=1500)
    engines = [("llama.cpp", RUNTIME), ("Onyx", ONYX), ("MLX · vLLM", MUTED), ("mock", MOCK)]
    for i, (label, color) in enumerate(engines):
        x = cx - 380 + i * 196
        name = f"e{i}"
        sc.add(rect(f"{name}-bg", x, 830, 176, 84, f"{color}22", 18, color, 3),
               centered(f"{name}-label", label, 856, 28, WHITE, SEMI, x=x, width=176),
               group(name, [f"{name}-bg", f"{name}-label"]))
        sc.pop(name, 2100 + i * 120, 380, 0.8)
        sc.add(line(f"e{i}-link", cx, 720, x + 88, 830, LINE, 3))
        draw_on(sc, f"e{i}-link", 2000 + i * 120)
        names += [name, f"e{i}-link"]
    sc.add(line("s-link", cx, 510, cx, 610, LINE, 3), line("d-link", cx, 337, cx, 400, LINE, 3))
    draw_on(sc, "d-link", 800)
    draw_on(sc, "s-link", 1400)
    sc.add(text("mock-pkg", "→ Mock-LLM (.jxmock, test-only)", cx + 210, 930, 22, MOCK, MONO))
    sc.fade("mock-pkg", 2900, dur=300)
    # A request travels down to Onyx and the answer streams back up.
    sc.add(ellipse("packet", cx, 315, 26, 26, SKY), glow("packet-glow", cx, 315, 120, SKY, "88"),
           group("pk", ["packet-glow", "packet"]))
    path = [(3400, 0, 0), (3900, 0, 140), (4500, 0, 350), (5100, 0, 560), (5500, -50, 560)]
    sc.keys("pk", "opacity", [(0, 0), (3300, 0), (3400, 1), (6800, 1), (7000, 0)])
    sc.keys("pk", "translate-x", [(t, dx) for t, dx, _ in path] + [(6800, 0)], "ease-in-out")
    sc.keys("pk", "translate-y", [(t, dy) for t, _, dy in path] + [(6800, -20)], "ease-in-out")
    sc.keys("pk", "scale", [(5500, 1), (5800, 1.6), (6100, 1)], "ease-out-cubic")
    notes = [("n0", "Studio speaks OpenAI /v1 to JX,", 3500), ("n1", "plus /runtime/* for discovery, pairing", 3500),
             ("n2", "and load/unload; it can even start JX", 3500), ("n3", "in --managed mode.", 3500),
             ("n4", "JX spawns the engine, health-checks it", 5000), ("n5", "and streams tokens back up.", 5000),
             ("n6", "Swap the engine. Nothing above changes.", 7000)]
    for i, (name, value, t) in enumerate(notes):
        y = 400 + i * 50 + (40 if i >= 4 else 0) + (60 if i >= 6 else 0)
        sc.add(text(name, value, 1180, y, 30, WHITE if i == 6 else MUTED, SEMI if i == 6 else BODY))
        sc.fade(name, t + (i % 4) * 150, dur=350, rise=10)
    # Onyx swaps for llama.cpp under the packet, to make the point.
    sc.keys("e1-bg", "scale", [(7000, 1), (7300, 1.12), (7700, 1)], "ease-out-back")
    sc.keys("e0-bg", "scale", [(7300, 1), (7600, 1.12), (8000, 1)], "ease-out-back")
    exit_all(sc, ["kicker", "headline", "d-link", "s-link", "mock-pkg"] + devs + names + [n for n, _, _ in notes],
             11400)
    return sc


# ----------------------------------------------------------------------------------------------- 8
def s08_control():
    sc = Scene("08-control", DURATIONS["08-control"])
    sc.add(backdrop(glow_at=(960, 300), glow2_at=(960, 1000)))
    kicker(sc, "MORE CONTROL")
    headline(sc, [("Your machine. Your models. ", None), ("Your rules.", SKY)])
    cards = [
        ("Local by default", "Cloud is opt-in, logged and budgeted. Nothing leaves without a yes.", [STUDIO, RUNTIME]),
        ("Explicit, not silent", "A model you chose is never swapped. Automatic picks say why.", [STUDIO, RUNTIME]),
        ("Safe out of the box", "Keys, TLS and pairing are on from the start. Test models are off.", [RUNTIME, MOCK]),
        ("Fails loudly", "Unsupported models are refused. Unmatched mocks are errors.", [ONYX, MOCK]),
    ]
    names = []
    for i, (title, body, colors) in enumerate(cards):
        x, y, w, h = 120 + i * 430, 340, 400, 520
        name = f"c{i}"
        parts = [rect(f"{name}-bg", x, y, w, h, PANEL, 24, LINE, 2)]
        for k, color in enumerate(colors):
            parts.append(rect(f"{name}-bar{k}", x + 30 + k * 60, y + 36, 48, 10, color, 5))
        parts += [rich(f"{name}-title", title, x + 30, y + 80, 42, w - 60, WHITE, HEAD, line_height=1.05),
                  rich(f"{name}-body", body, x + 30, y + 220, 28, w - 60, MUTED, BODY, line_height=1.35)]
        sc.add(parts, shadow(f"{name}-bg", 40, 18, 0.35))
        sc.add(group(name, [p["name"] for p in parts]))
        sc.fade(name, 900 + i * 450, dur=400)
        sc.slide(name, 900 + i * 450, dy=60)
        names.append(name)
    key, x = [], 120
    for i, (label, color) in enumerate(REPOS):
        w = round(len(label) * 20 * 0.58 + 44)
        sc.add(chip(f"key{i}", label, x, 920, size=20, fg=DEEP, bg=color, font=SEMI, width=w))
        sc.pop(f"key{i}", 3600 + i * 110, 320, 0.7)
        key.append(f"key{i}")
        x += w + 14
    exit_all(sc, ["kicker", "headline"] + names + key, 9000)
    return sc


# ----------------------------------------------------------------------------------------------- 9
JOURNAL = [
    ("2026-05-07", STUDIO, "AI Server Studio's changelog begins: one gateway in front of local models."),
    ("2026-08-09", RUNTIME, "JX Runtime 1.0, \"the first complete runtime\", shaped by what Studio needs."),
    ("2026-08-25", RUNTIME, "Recovery day: three model families won't load, and 8B models crawl at CPU speed."),
    ("2026-08-26", MOCK, "Mock-LLM starts: tests shouldn't need a GPU, a key, or luck."),
    ("2026-08-30", ONYX, "Onyx Engine's first commit. Version 0.1.0 ships two days later."),
    ("2026-09-07", SKY, "Onyx 0.3.1, JX Runtime 1.4.4 and jx-mock-llm 0.2.1 all ship the same day."),
    ("2026-10-11", STUDIO, "AI Server Studio Alpha 0.7.3."),
]


def s09_journal():
    sc = Scene("09-journal", DURATIONS["09-journal"])
    sc.add(rect("bg", 0, 0, 1920, 1080, DEEP))
    names = journal_page(sc, "How they built each other")
    for i, (date, color, entry) in enumerate(JOURNAL):
        y = 60 + 70 + (i + 2) * 64 + 14 + i * 36
        t = 1200 + i * 1250
        sc.add(rect(f"j{i}-tag", 200, y + 8, 12, 30, color, 4),
               text(f"j{i}-date", date, 228, y + 6, 26, "#8A7F6A", MONO),
               rich(f"j{i}-text", entry, 440, y, 32, 1300, INK, BODY, line_height=1.2))
        sc.fade(f"j{i}-tag", t, dur=250)
        sc.fade(f"j{i}-date", t, dur=250)
        sc.words(f"j{i}-text", t + 150, "typewriter", "char", 800)
        names += [f"j{i}-tag", f"j{i}-date", f"j{i}-text"]
    exit_all(sc, names, 11400)
    return sc


# ---------------------------------------------------------------------------------------------- 10
def s10_loops():
    sc = Scene("10-loops", DURATIONS["10-loops"])
    sc.add(backdrop(glow_at=(560, 600), glow2_at=(1500, 300)))
    kicker(sc, "EACH ONE TESTS THE OTHERS")
    headline(sc, [("They keep each other ", None), ("honest.", SKY)])
    nodes = {"studio": ("Studio", STUDIO, 560, 380), "jx": ("JX Runtime", RUNTIME, 860, 640),
             "onyx": ("Onyx", ONYX, 560, 900), "mock": ("Mock-LLM", MOCK, 260, 640)}
    edges = [("studio", "jx", 1400), ("jx", "onyx", 1600), ("mock", "jx", 1800), ("studio", "mock", 2000)]
    hot = {"studio-jx": STUDIO, "jx-onyx": ONYX, "mock-jx": MOCK, "studio-mock": MUTED}
    names = []
    for a, b, t in edges:
        name = f"edge-{a}-{b}"
        # Studio's move to Mock-LLM is planned, not done: its edge stays faint.
        sc.add(line(name, *_ends(nodes, f"{a}-{b}"), LINE if a != "studio" or b != "mock" else "#3C445880", 4))
        draw_on(sc, name, t)
        sc.add(line(f"{name}-hot", *_ends(nodes, f"{a}-{b}"), hot[f"{a}-{b}"], 7))  # lit by its claim below
        names.append(name)
    for i, (key, (label, color, x, y)) in enumerate(nodes.items()):
        name = f"node-{key}"
        sc.add(rect(f"{name}-bg", x - 130, y - 44, 260, 88, DEEP, 44, color, 4),
               centered(f"{name}-label", label, y - 20, 32, WHITE, HEAD, x=x - 130, width=260),
               group(name, [f"{name}-bg", f"{name}-label"]))
        sc.pop(name, 800 + i * 150, 400, 0.6)
        names.append(name)
    # Each claim lights its edge in turn.
    claims = [
        ("studio-jx", STUDIO, "Studio sets JX's requirements, then tests the real thing every night.",
         "a mock is not sufficient evidence on its own", ".github/workflows/live-runtime-integration.yml · Studio"),
        ("jx-onyx", ONYX, "JX installs Onyx at a pinned release and checks it against published checksums.",
         "in place of a third-party llama-server binary", "docs/jx-runtime-integration.md · Onyx"),
        ("mock-jx", MOCK, "Mock-LLM's tests run JX Runtime's own stream observer over the mock's bytes.",
         "A change in either repo that breaks the pairing fails here.", "tests/contract.test.js · Mock-LLM"),
        ("studio-mock", MUTED, "Next: Studio's tests on Mock-LLM, with one base-URL change.",
         "a test should not need an API key, a downloaded model, a GPU", "mock-llm-provider-spec.md · Mock-LLM"),
    ]
    for i, (edge, color, claim, said, source) in enumerate(claims):
        t0 = 2600 + i * 2100
        t1 = t0 + 1950
        e = f"edge-{edge}"
        sc.keys(f"{e}-hot", "opacity", [(0, 0), (t0, 0), (t0 + 250, 1), (t1 - 200, 1), (t1 + 50, 0.0)])
        cn, qn, sn = f"claim{i}", f"said{i}", f"src{i}"
        sc.add(rich(cn, claim, 1160, 360, 40, 660, WHITE, HEAD, line_height=1.15),
               rich(qn, [(f"“{said}”", color if color != MUTED else WHITE)], 1160, 620, 30, 660, WHITE, SEMI,
                    line_height=1.25),
               text(sn, source, 1160, 790, 20, MUTED, MONO))
        last = i == len(claims) - 1
        for n, d in ((cn, 0), (qn, 300), (sn, 500)):
            frames = [(0, 0), (t0 + d, 0), (t0 + d + 300, 1)]
            if not last:
                frames += [(t1 - 150, 1), (t1, 0)]
            sc.keys(n, "opacity", frames, "ease-out-cubic")
        sc.keys(cn, "translate-y", [(0, 16), (t0, 16), (t0 + 400, 0)], "ease-out-cubic")
        if last:  # earlier claims have already faded; an exit key would bring them back
            names += [cn, qn, sn]
    exit_all(sc, ["kicker", "headline"] + names, 11400)
    return sc


def _ends(nodes, edge):
    a, b = edge.split("-")
    return nodes[a][2], nodes[a][3], nodes[b][2], nodes[b][3]


# ---------------------------------------------------------------------------------------------- 11
LESSONS = [
    (ONYX, "ONYX ENGINE", "A bare make -j started ~170 compilers on a 16 GB box. The OOM killer took the build, "
                          "and the JX Runtime running next to it.", "Now: one job per CPU."),
    (MOCK, "MOCK-LLM", "A mock shaped to fit one app can only prove that app is compatible with itself.",
     "Now: a generic engine, and a separate JX package."),
    (RUNTIME, "JX RUNTIME", "A later step assuming an earlier one worked is how the original fault stayed hidden.",
     "Now: every step ends with a check and a STOP."),
]


def s11_lessons():
    sc = Scene("11-lessons", DURATIONS["11-lessons"])
    sc.add(rect("bg", 0, 0, 1920, 1080, DEEP))
    names = journal_page(sc, "Lessons, written down")
    for i, (color, repo, lesson, after) in enumerate(LESSONS):
        y = 330 + i * 230
        t = 1200 + i * 3000
        sc.add(rect(f"k{i}-tag", 200, y + 6, 12, 150, color, 4),
               text(f"k{i}-repo", repo, 232, y, 22, "#8A7F6A", MONO),
               rich(f"k{i}-text", lesson, 232, y + 36, 34, 1450, INK, SEMI, line_height=1.2),
               text(f"k{i}-after", after, 232, y + 132, 26, "#3E7A4F", MONO))
        sc.fade(f"k{i}-tag", t, dur=250)
        sc.fade(f"k{i}-repo", t, dur=250)
        sc.words(f"k{i}-text", t + 150, "fade-up", "word", 380, 45)
        sc.fade(f"k{i}-after", t + 1900, dur=350, rise=8)
        names += [f"k{i}-tag", f"k{i}-repo", f"k{i}-text", f"k{i}-after"]
    exit_all(sc, names, 11400)
    return sc


# ---------------------------------------------------------------------------------------------- 12
STATS = [("2,279", "JX Runtime tests", RUNTIME), ("844", "Studio test files", STUDIO),
         ("205", "Mock-LLM tests", MOCK), ("17", "Studio audit reports", STUDIO),
         ("5", "engines JX can run", RUNTIME), ("3,105", "lines of C++ in Onyx Engine", ONYX)]


def s12_numbers():
    sc = Scene("12-numbers", DURATIONS["12-numbers"])
    sc.add(backdrop(glow_at=(960, 500)))
    kicker(sc, "BY THE NUMBERS")
    headline(sc, [("May to October 2026. ", None), ("Written down as it happened.", SKY)])
    names = []
    for i, (value, label, color) in enumerate(STATS):
        x, y = 120 + (i % 3) * 570, 320 + (i // 3) * 270
        name = f"s{i}"
        sc.add(rect(f"{name}-bg", x, y, 540, 240, PANEL, 22, LINE, 2),
               text(f"{name}-v", value, x + 36, y + 30, 100, color, HEAD),
               text(f"{name}-l", label, x + 40, y + 170, 30, MUTED, BODY),
               group(name, [f"{name}-bg", f"{name}-v", f"{name}-l"]))
        sc.pop(name, 600 + i * 160, 420, 0.8)
        names.append(name)
    caption(sc, "agents", "Built alongside AI coding agents. The changelogs record what changed, "
                          "and what is still unverified.", 120, 900, 2400, 26, MUTED, BODY)
    exit_all(sc, ["kicker", "headline", "agents"] + names, 6700)
    return sc


# ---------------------------------------------------------------------------------------------- 13
def s13_vixl():
    sc = Scene("13-vixl", DURATIONS["13-vixl"])
    sc.add(backdrop(glow_at=(1400, 500)))
    kicker(sc, "ONE MORE THING")
    headline(sc, [("And this film? ", None), ("Vixl made it.", SKY)])
    sc.add(image("still", rel(ASSETS / "studio-intro-still.png"), 1000, 330, 800, 450))
    sc.add(shadow("still", 50, 22, 0.5))
    sc.fade("still", 700, dur=500)
    sc.slide("still", 700, dx=80)
    caption(sc, "still-cap", "AI Server Studio's own intro film: also Vixl", 1000, 800, 1300, 22)
    lines = [("v0", "Every frame is an editable Vixl document."),
             ("v1", "The music is a Vixl document too."),
             ("v2", "Every fact on screen is cited in its README.")]
    for i, (name, value) in enumerate(lines):
        sc.add(rich(name, value, 120, 350 + i * 140, 40, 780, WHITE, SEMI, line_height=1.2))
        sc.words(name, 1100 + i * 700, "fade-up", "word", 400, 50)
    exit_all(sc, ["kicker", "headline", "still", "still-cap", "v0", "v1", "v2"], 6700)
    return sc


# ---------------------------------------------------------------------------------------------- 14
URLS = [("github.com/jxburros/AI-Server-Studio", STUDIO), ("github.com/jxburros/JX-Runtime", RUNTIME),
        ("github.com/JX-Holdings-LLC/Onyx-Engine", ONYX), ("github.com/JX-Holdings-LLC/Mock-LLM", MOCK)]


def s14_end():
    sc = Scene("14-end", DURATIONS["14-end"])
    sc.add(backdrop(glow_at=(960, 400), glow2_at=(960, 1000)))
    for i, (_, color) in enumerate(REPOS):
        name = f"bar{i}"
        sc.add(rect(name, 660 + i * 156, 170, 132, 18, color, 9))
        sc.pop(name, 100 + i * 120, 380, 0.3)
    sc.add(centered("line", [("Own the ", None), ("whole stack.", SKY)], 250, 120))
    sc.words("line", 500, "fade-up", "word", 500, 140)
    sc.add(centered("sub", "Your machine. Your models. Your rules.", 410, 40, MUTED, BODY))
    sc.words("sub", 1100, "fade-up", "word", 400, 70)
    for i, (url, color) in enumerate(URLS):
        x, y = 620, 530 + i * 64
        sc.add(rect(f"u{i}-dot", x - 28, y + 14, 14, 14, color, 7), text(f"u{i}", url, x, y, 30, WHITE, MONO))
        sc.fade(f"u{i}-dot", 1700 + i * 180, dur=300)
        sc.fade(f"u{i}", 1700 + i * 180, dur=350, rise=10)
    sc.add(centered("made", "Made with Vixl  ·  github.com/jxburros/Vixl", 920, 26, MUTED, MONO))
    sc.fade("made", 2800, dur=500)
    return sc


def all_scenes():
    return [s01_open(), s02_title(), s03_studio(), s04_runtime(), s05_onyx(), s06_mock(), s07_stack(),
            s08_control(), s09_journal(), s10_loops(), s11_lessons(), s12_numbers(), s13_vixl(), s14_end()]
