"""Offline tour of reusable design, tests, plugins and multi-agent branch/merge."""

import argparse
import json
from pathlib import Path

from PIL import Image

from vixl import Project
from vixl.interfaces import Session
from vixl.resources import create_template, BUILTINS
from vixl.workflows import dispatch
from vixl.imports import import_document


def build(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (output / "campaign.vixl").exists():
        raise SystemExit("Choose a fresh output directory; the demo preserves existing projects.")
    project = create_template("modular-split", workspace=output, palette="ocean", look="none", seed=0)
    project.apply(
        [
            {"type": "text-set", "target": "slot-1/title", "text": "New directions"},
            {"type": "text-set", "target": "slot-1/body", "text": "Reusable design. Shared ideas."},
            {"type": "container-reflow", "target": "slot-1"},
            {"type": "container-swap", "target": "slot-2", "resource": "organic-mark"},
            {
                "type": "pen",
                "name": "flourish",
                "points": [[40, 230], [150, 210], [280, 250], [410, 220]],
                "stroke": "@accent",
                "stroke_width": 5,
            },
        ]
    )
    project.save(output / "campaign.vixl")
    session = Session("campaign.vixl", workspace=output)
    dispatch(session, "shape-save", {"target": "flourish", "name": "signature"})
    # This composition uses antialiased type and curves; allow up to 2% intermediate edge pixels.
    session.apply(
        {
            "type": "suite-set",
            "name": "palette",
            "suite": {
                "rules": [
                    {
                        "id": "palette",
                        "kind": "palette",
                        "colors": BUILTINS["palettes"]["ocean"],
                        "tolerance": 8,
                        "max_fraction": 0.02,
                    }
                ]
            },
        }
    )
    dispatch(session, "suite-use", {"name": "no-placeholders"})
    custom = {
        "rules": [
            {"id": "canvas-width", "kind": "property", "target": "canvas", "field": "width", "expected": 960}
        ]
    }
    dispatch(session, "resource-save", {"kind": "suites", "name": "campaign-size", "value": custom})
    dispatch(session, "suite-use", {"name": "campaign-size"})
    for branch in ("copy-agent", "art-agent"):
        dispatch(session, "branch-fork", {"branch": branch, "output": branch + ".vixl", "author": branch})
    session.apply(
        {"type": "text-set", "target": "slot-1/body", "text": "Made together. Ready to reuse."},
        document="copy-agent.vixl",
    )
    session.apply({"type": "move", "target": "flourish", "y": -4}, document="art-agent.vixl")
    for branch in ("copy-agent", "art-agent"):
        report = dispatch(session, "branch-merge", {"branch": branch, "dry_run": False})
        assert report["can_merge"], report
    dispatch(
        session,
        "plugin-install",
        {
            "manifest": {
                "name": "demo",
                "version": "1.0.0",
                "api_version": 1,
                "resources": {"palettes": {"demo-ink": ["#003049", "#edf6f9"]}},
            }
        },
    )
    session.create("reuse.vixl", 960, 320, "#edf6f9")
    session.apply(
        {"type": "shape-place", "resource": "signature", "name": "signature", "width": 960, "height": 320}
    )
    dispatch(
        session,
        "group-define",
        {
            "name": "launch",
            "documents": ["campaign.vixl", "reuse.vixl"],
            "shared": {"variables": {"campaign": "New directions"}},
        },
    )
    dispatch(session, "group-apply", {"name": "launch", "dry_run": False})
    reports = {
        name: dispatch(session, "check", {"suite": name}, "campaign.vixl")
        for name in ("palette", "no-placeholders", "container-layout", "campaign-size")
    }
    assert all(report["passed"] for report in reports.values()), reports
    with session.project(document="campaign.vixl") as final:
        final.export(output / "campaign.png")
        final.export(output / "campaign.html")
    previews = []
    for name in BUILTINS["workflows"]:
        p = Project(200, 160, "#101828")
        p.apply(
            {
                "type": "shape",
                "shape": "heart",
                "name": "artwork",
                "x": 45,
                "y": 25,
                "width": 110,
                "height": 100,
                "fill": "#83c5be",
            }
        )
        p.save(output / (name + ".vixl"))
        dispatch(session, "effect-run", {"name": name}, name + ".vixl")
        with session.project(document=name + ".vixl") as effected:
            previews.append(effected.render())
    sheet = Image.new("RGBA", (200 * len(previews), 160))
    for index, preview in enumerate(previews):
        sheet.paste(preview, (index * 200, 0))
    sheet.save(output / "effect-workflows.png")
    imported = Project(120, 80)
    import_document(
        imported,
        b'<svg width="120" height="80"><defs><linearGradient id="g"><stop stop-color="red"/><stop offset="1" stop-color="blue"/></linearGradient></defs><rect width="120" height="80" rx="20" fill="url(#g)"/></svg>',
        "svg",
        svg_mode="appearance",
    )
    imported.save(output / "imported.vixl")
    (output / "checks.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
    return reports


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="examples/output/studio")
    args = parser.parse_args()
    reports = build(args.output)
    print(
        json.dumps(
            {
                "output": str(Path(args.output).resolve()),
                "checks": {k: v["status"] for k, v in reports.items()},
            }
        )
    )
