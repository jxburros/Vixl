"""Build a checked campaign and motion demo without an AI provider."""

import argparse
from pathlib import Path

from vixl import Project
from vixl.production import Library, capture_recipe, run
from vixl.film import export as export_film
from vixl.timeline import export_timeline


def build(directory):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    project = Project(800, 500, "#102030")
    project.apply(
        [
            {"type": "variable", "name": "accent", "value": "#38d9a9"},
            {
                "type": "text",
                "name": "eyebrow",
                "text": "VIXL / CREATIVE AUTOMATION",
                "size": 20,
                "x": 50,
                "y": 55,
                "color": "#a6bdd4",
            },
            {
                "type": "text",
                "name": "title",
                "text": "Make once. Create more.",
                "size": 70,
                "x": 50,
                "y": 135,
                "color": "white",
            },
            {
                "type": "text",
                "name": "caption",
                "text": "One recipe. Checked variations. Reusable motion.",
                "size": 23,
                "x": 50,
                "y": 350,
                "color": "#a6bdd4",
            },
            {
                "type": "shape",
                "name": "accent",
                "shape": "rectangle",
                "width": 700,
                "height": 5,
                "x": 50,
                "y": 410,
                "fill": "${accent}",
            },
            {
                "type": "shape",
                "name": "logo",
                "shape": "ellipse",
                "width": 28,
                "height": 28,
                "x": 720,
                "y": 50,
                "fill": "white",
            },
            {
                "type": "fit-text",
                "target": "title",
                "width": 690,
                "height": 180,
                "minimum": 40,
                "maximum": 70,
            },
            {
                "type": "action-define",
                "name": "fit-title",
                "action": {
                    "operations": [
                        {
                            "type": "fit-text",
                            "target": "title",
                            "width": 690,
                            "height": 180,
                            "minimum": 40,
                            "maximum": 70,
                        }
                    ]
                },
            },
            {
                "type": "suite-set",
                "name": "delivery",
                "suite": {
                    "rules": [
                        {"id": "fit", "kind": "text-fit", "target": "title", "minimum": 40},
                        {"id": "logo", "kind": "assert", "expression": "layer.logo.bounds within canvas"},
                    ]
                },
            },
            {"type": "suite-capture", "name": "brand", "targets": ["logo"]},
            {"type": "role-set", "name": "headline", "targets": ["title"]},
            {
                "type": "motion-define",
                "name": "entry",
                "motion": {"steps": [{"role": "headline", "preset": "fade-in", "duration": 700}]},
            },
        ]
    )
    template = capture_recipe(
        project,
        {
            "version": 1,
            "inputs": {
                "title": {"type": "string", "default": "Make once. Create more.", "maxLength": 100},
                "accent": {"type": "color", "default": "#38d9a9"},
            },
            "actions": ["fit-title"],
            "examples": [{"title": "A complete creative production workflow."}],
        },
        {"title": {"target": "title", "field": "text"}},
    )
    template.save(directory / "campaign-recipe.vixl")
    result = run(
        template,
        {
            "rows": [
                {"title": "Make once. Create more."},
                {"title": "Every variation, checked."},
                {"title": "Set your ideas in motion."},
            ],
            "matrix": {"accent": ["#38d9a9", "#ff9770"]},
            "workers": 2,
        },
        directory / "campaign",
    )
    assert result["status"] == "completed", result
    motion = project.clone()
    motion.apply(
        [{"type": "timeline-set", "duration": 1800, "fps": 20}, {"type": "motion-apply", "name": "entry"}]
    )
    motion.path, motion._revision = None, None
    motion.save(directory / "motion.vixl")
    export_timeline(motion, directory / "promo.webp", scale=0.75)
    export_film(
        {
            "width": 800,
            "height": 500,
            "fps": 12,
            "shots": [
                {"source": "motion.vixl", "duration": 1800},
                {
                    "source": "campaign-recipe.vixl",
                    "duration": 1200,
                    "transition": 250,
                    "variables": {"title": "Ready for the next idea.", "accent": "#ff9770"},
                    "camera": {"from": [0.5, 0.5, 1], "to": [0.5, 0.5, 1.05]},
                },
            ],
        },
        directory,
        directory / "film.zip",
    )
    Library(directory / "library").save(
        template, "campaign", "Checked campaign and reusable headline motion", ["campaign", "motion"]
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="examples/output/production")
    print(build(parser.parse_args().output)["status"])
