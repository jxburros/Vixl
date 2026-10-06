"""Rebuild the documentation illustrations with Vixl, without network or AI services.

Run from the repository root: python examples/build_documentation.py
Every illustration includes an editable document and its canonical operation list.
"""

import argparse
import json
from pathlib import Path

from vixl import Project, __version__
from vixl.deck import contact_sheet as page_sheet
from vixl.timeline import export_timeline

INK = "#18283b"
MUTED = "#4d6175"
PAPER = "#f5f3ec"
BLUE = "#235cdb"
TEAL = "#087f78"
ORANGE = "#bd491c"


def text(name, value, x, y, size=24, color=INK):
    return dict(type="text", name=name, text=value, x=x, y=y, size=size, color=color)


def box(name, x, y, w, h, fill, radius=16):
    return dict(type="shape", shape="rounded-rectangle", name=name, x=x, y=y,
                width=w, height=h, fill=fill, radius=radius)


def heading(title, subtitle):
    return [text("heading", title, 48, 32, 38), text("subtitle", subtitle, 48, 88, 20, MUTED)]


def build(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    records = []

    def save(name, width, height, ops, description, **extras):
        project = Project(width, height, PAPER)
        project.apply(ops)
        project.save(output / f"{name}.vixl")
        project.export(output / f"{name}.png", alpha="auto")
        (output / f"{name}.json").write_text(json.dumps({"operations": ops}, indent=2) + "\n")
        report = project.check(checks=["bounds"])
        if report["issues"]:
            raise RuntimeError(f"{name}: {report['issues']}")
        # Confirm that the portable master can be loaded and rendered independently.
        loaded = Project.load(output / f"{name}.vixl")
        if loaded.render().tobytes() != project.render().tobytes():
            raise RuntimeError(f"{name}: saved document changed its rendering")
        records.append(dict(name=name, description=description, size=[width, height],
                            version=__version__, bounds=report, **extras))
        return project

    ops = heading("From brief to deliverable", "One editable document. A repeatable review loop.")
    steps = [("01", "Create", "Size + palette", BLUE), ("02", "Apply", "Atomic operations", TEAL),
             ("03", "Inspect", "Layers + bounds", BLUE), ("04", "Check", "Explicit rules", TEAL),
             ("05", "Preview", "Visual review", BLUE), ("06", "Export", "Right format", ORANGE)]
    for i, (number, label, detail, color) in enumerate(steps):
        x = 48 + i * 198
        ops += [box(f"card-{i}", x, 160, 176, 190, "#ffffff"),
                text(f"number-{i}", number, x + 18, 178, 20, color),
                text(f"label-{i}", label, x + 18, 223, 28),
                text(f"detail-{i}", detail, x + 18, 288, 15, MUTED)]
        if i < 5:
            ops += [text(f"arrow-{i}", "→", x + 179, 224, 22, MUTED)]
    ops += [box("review-loop", 48, 388, 1166, 64, "#e3eee9"),
            text("review-note", "Revise after checks or preview → inspect, check and preview again", 70, 405, 22)]
    save("workflow", 1260, 490, ops, "Creation and visual review loop")

    ops = heading("Inside an editable design", "Names identify layers; constraints describe relationships.")
    ops += [box("poster-bg", 48, 148, 570, 430, INK),
            dict(type="shape", shape="ellipse", name="orb", x=368, y=208, width=190, height=190, fill="#f5a56a"),
            text("poster-label", "FIELD NOTES / 01", 78, 179, 17, "#c1d4e5"),
            text("poster-title", "MAKE\nSOMETHING", 78, 265, 44, "#ffffff"),
            text("poster-date", "FRIDAY · 19:00", 78, 490, 22, "#ffffff")]
    rows = [("title", "Editable text, not baked pixels"), ("orb", "Procedural ellipse + solid fill"),
            ("poster-bg", "Independent background shape"), ("Layout", "Origin: top-left; units: pixels"),
            ("History", "Save checkpoints before big edits")]
    for i, (label, detail) in enumerate(rows):
        y = 157 + i * 82
        ops += [text(f"layer-{i}", label, 678, y, 25, BLUE),
                text(f"meaning-{i}", detail, 678, y + 36, 20, MUTED)]
    save("document-anatomy", 1180, 630, ops, "Real text and shape layers alongside explanatory labels")

    ops = heading("Make a chart from ordinary layers", "Illustrative data: completed tasks, not measured Vixl performance.")
    values = [("Draft", 24), ("Review", 38), ("Refine", 52), ("Deliver", 68)]
    for i, (label, value) in enumerate(values):
        y = 160 + i * 88
        ops += [text(f"category-{i}", label, 48, y + 12, 24),
                box(f"track-{i}", 210, y, 720, 48, "#e4e7e7", 6),
                box(f"bar-{i}", 210, y, value * 9, 48, BLUE if i < 3 else TEAL, 6),
                text(f"value-{i}", str(value), 958, y + 8, 26)]
    ops += [text("chart-note", "Scale: 9 px per task · Baseline: 0 · Bar widths are data × scale", 48, 535, 20, MUTED)]
    save("chart", 1060, 595, ops, "An editable horizontal bar chart with explicit illustrative data", data=dict(values))

    ops = heading("Reusable campaign, changing copy", "Variables replace content while keeping the composition.")
    ops += [dict(type="variable", name="headline", value="OPEN STUDIO"),
            dict(type="variable", name="date", value="FRIDAY / 19:00"),
            box("campaign-card", 48, 145, 964, 375, INK),
            dict(type="shape", shape="ellipse", name="campaign-orb", x=739, y=197,
                 width=190, height=190, fill="#f5a56a"),
            text("campaign-kicker", "VIXL / COMMUNITY SERIES", 80, 176, 20, "#c1d4e5"),
            text("campaign-title", "${headline}", 80, 270, 56, "#ffffff"),
            text("campaign-date", "${date}", 80, 439, 26, "#ffffff")]
    project = save("campaign", 1060, 570, ops, "Variable-driven campaign master")
    project.export(output / "campaign-variant.png",
                   variables={"headline": "NIGHT SCHOOL", "date": "SATURDAY / 20:00"}, alpha="auto")

    ops = heading("Paint and procedural forms", "Editable strokes and a seeded organic shape; no image provider.")
    ops += [dict(type="paint-layer", name="watercolor"),
            dict(type="paint", target="watercolor", brush="watercolor",
                 path="M70 245 C220 130 350 370 540 240", size=54, color=BLUE, seed=7),
            dict(type="paint-layer", name="ink"),
            dict(type="paint", target="ink", brush="ink",
                 path="M70 355 C230 230 350 470 540 350", size=8, color=INK, seed=7),
            dict(type="organic", preset="sunflower", name="bloom", x=700, y=165,
                 width=260, height=280, seed=7),
            text("paint-label", "Watercolor + ink", 70, 477, 24),
            text("organic-label", "Seeded sunflower", 700, 477, 24)]
    save("paint-organic", 1060, 560, ops, "Actual editable brush strokes and organic generator")

    ops = [dict(type="canvas", size="letter", dpi=100, background="#ffffff"),
           text("title", "Studio registration", 60, 58, 36),
           text("intro", "A real fillable PDF, built from field layers.", 60, 120, 22, MUTED),
           text("name-label", "Full name", 60, 215, 22),
           dict(type="field", name="full_name", label_layer="name-label", kind="text",
                x=60, y=254, width=730, height=64, required=True, size=24),
           text("email-label", "Email", 60, 365, 22),
           dict(type="field", name="email", label_layer="email-label", kind="text", format="email",
                x=60, y=404, width=730, height=64, required=True, size=24),
           dict(type="field", name="newsletter", kind="checkbox", label="Send me studio news",
                x=60, y=530, width=28, height=28),
           text("newsletter-label", "Send me studio news", 105, 530, 22),
           text("form-footer", "Keep this editable master; export copies for attendees.", 60, 975, 20, MUTED)]
    project = save("registration", 850, 1100, ops, "Letter-size form with text and checkbox fields")
    project.export(output / "registration.pdf", fillable=True)
    project.export(output / "registration-filled.png",
                   values={"full_name": "Ada Lovelace", "email": "ada@example.com", "newsletter": True})

    ops = [dict(type="page", action="add", name="cover", notes="Introduce the editable workflow."),
           *heading("Design once. Export many ways.", "Vixl / an editable slide deck"),
           box("cover-panel", 48, 160, 964, 280, INK),
           text("cover-title", "Text. Shapes. Data.", 80, 215, 54, "#ffffff"),
           text("cover-body", "A portable document becomes slides, images or PDF.", 80, 325, 24, "#c1d4e5"),
           dict(type="page", action="add", name="results", notes="All numbers are illustrative."),
           *heading("Results at a glance", "Illustrative tasks completed in four stages"),
           *[op for op in records_chart_ops(values)]]
    project = save("slides", 1060, 595, ops, "Two real pages with speaker notes and editable chart layers")
    page_sheet(project).save(output / "slides.png")
    project.export(output / "slides.pdf")
    project.export(output / "slides.pptx")

    ops = heading("Animate a layer", "A 2-second translation; export works offline as animated WebP.")
    ops += [box("motion-track", 48, 188, 964, 100, "#e4e7e7"),
            box("moving-card", 68, 202, 160, 72, TEAL),
            dict(type="animate", target="moving-card", property="translate-x", to=760,
                 duration="2s", easing="ease-in-out"),
            text("motion-caption", "Resting state is editable; time selects a rendered pose.", 48, 355, 24)]
    project = save("motion", 1060, 450, ops, "Keyframe translation on a real editable layer")
    export_timeline(project, output / "motion.webp", fps=12, overwrite=True)
    for index, time in enumerate((0, 1, 2)):
        project.export(output / f"motion-{index}.png", time=f"{time}s", alpha="auto")

    (output / "manifest.json").write_text(json.dumps(records, indent=2) + "\n")
    print(f"Built {len(records)} editable illustrations with Vixl {__version__} in {output.resolve()}")


def records_chart_ops(values):
    """Use the same data in the deck, with names scoped to its own page."""
    for i, (label, value) in enumerate(values):
        y = 160 + i * 88
        yield text(f"category-{i}", label, 48, y + 12, 24)
        yield box(f"bar-{i}", 210, y, value * 9, 48, TEAL, 6)
        yield text(f"value-{i}", str(value), 958, y + 8, 24)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="docs/assets/generated")
    build(parser.parse_args().output)
