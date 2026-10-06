"""Task-focused discovery derived from the canonical operation and workflow catalogs."""

import re

from .model import Limits

TOPICS = {
    "text": (
        "text rich font layout stack container caption bubble",
        ["docs/text-flow.md", "docs/containers-and-templates.md"],
    ),
    "drawing": (
        "shape pen path stroke distort organic irregular tear pattern texture clone paint",
        ["docs/drawing.md"],
    ),
    "animation": (
        "motion animate keyframe timeline character rig ik scene camera particle cut-paper viseme",
        ["docs/animation-authoring.md"],
    ),
    "film": ("film video audio caption", ["docs/production.md"]),
    "layout": (
        "layout container template stack fit align distribute spatial grid snap guide comic",
        ["docs/sizes-and-layouts.md"],
    ),
    "color": ("palette color swatch look style lighting", ["docs/color-and-print.md"]),
    "export": ("export film merge form", ["docs/releases.md"]),
}
GOTCHAS = [
    "x/y are parent-local pixels unless move (or shape/text/solid/gradient with target) uses space=canvas; "
    "pivot units=canvas takes a document point. Width/height percentages use the parent box.",
    "SVG path coordinates are literal local pixels, not normalized to width/height; without width/height a path's "
    "box reaches its farthest point; path-fit scales the geometry.",
    "Opacity is 0-1 everywhere (opacity, keyframes, layer-style, creation fields); '70%' is read as 0.7, 70 is an error.",
    "Per-layer operations take targets: [...] to apply to several layers; group/align/distribute treat targets jointly.",
    "font accepts a registered name or heading/body role. Import/install fonts before applying text batches.",
    "Batches are atomic; dry_run validates without changing the document. Use history begin/commit for several batches.",
    "Use layer-intent allow_crop=true for intentional bleed. Summary diagnostics offer bounded full detail with pagination.",
    "For motion, check sampled frames and film-preview with the camera before a full export; start at draft quality.",
]


def lookup(topic=None, *, fields=False):
    from .schema import operation_schema
    from .workflows import describe

    catalog = {
        entry["properties"]["type"]["const"]: entry
        for entry in operation_schema()["properties"]["operations"]["items"]["oneOf"]
    }
    workflows = describe()["actions"]
    if not topic:
        return {
            "topics": {name: words for name, (words, _) in TOPICS.items()},
            "gotchas": GOTCHAS,
            "limits": {"operations_per_batch": Limits().max_operations},
            "next": "vixl_capabilities(topic, fields=true), then vixl_operation_schema(types=[...]) for exact constraints.",
        }
    requested = set(re.findall(r"[a-z]+", topic.lower()))
    chosen = [
        name for name, (words, _) in TOPICS.items() if name in requested or requested & set(words.split())
    ]
    tokens = requested | {word for name in chosen for word in TOPICS[name][0].split()}

    def relevant(name):
        return bool(set(name.split("-")) & tokens)

    operations = {
        name: {
            "summary": spec.get("description", ""),
            **({"fields": list(spec["properties"]), "required": spec["required"]} if fields else {}),
        }
        for name, spec in catalog.items()
        if relevant(name)
    }
    return {
        "topic": topic,
        "topics": chosen,
        "operations": operations,
        "workflows": {name: spec["summary"] for name, spec in workflows.items() if relevant(name)},
        "guidance": sorted({path for name in chosen for path in TOPICS[name][1]}),
        "gotchas": GOTCHAS,
        "limits": {"operations_per_batch": Limits().max_operations},
        "next": "vixl_operation_schema(types=[...]) returns exact constraints and examples.",
    }
