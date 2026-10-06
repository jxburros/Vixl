"""Task-focused discovery derived from the canonical operation and workflow catalogs."""

import re

from .model import Limits

# topic -> (words that select it and its operations, guidance names readable with vixl_guide(brief=NAME))
TOPICS = {
    "text": ("text rich font layout stack container caption bubble", ["typography", "layout"]),
    "drawing": (
        "shape pen path stroke distort organic irregular tear pattern texture clone paint repeat scatter fur plush "
        "seamless tile",
        ["scatter", "imperfection", "drawn-textures", "illustration-perspective", "brush", "multi-part-objects"],
    ),
    "animation": (
        "motion animate keyframe keyframes timeline character rig ik pivot loop stagger cycle scene camera particle "
        "cut-paper viseme wiggle boil sample wave",
        ["looping-motion", "scatter", "natural-motion", "character-rigging", "motion", "cut-paper", "audio-composition"],
    ),
    "shapes": ("shape shapes heart bubble badge star content", []),
    "film": ("film video audio caption", ["film-review", "audio-composition"]),
    "layout": (
        "layout container template stack fit align distribute spatial grid snap guide comic",
        ["layout", "overall"],
    ),
    "color": ("palette color swatch look style lighting", ["color", "natural-color-light", "accessibility"]),
    "export": ("export film merge form", ["print"]),
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
    "Loops: motion recipes take period, stagger and many targets in one operation; a duration that is a whole number of "
    "periods returns every track to its frame-0 value.",
    "No expression language: generate repetition with keyframes sample {fn: sin|triangle|noise, period, amplitude, "
    "step_ms}, motion recipe wiggle (amount, frequency, samples) or line-boil, and repeat/radial-repeat per-step "
    "fields with seeded jitter; scatter/pattern-scatter with merge: true keep many copies to a few layers.",
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
    extra = {}
    if "shapes" in chosen:
        from .shape_catalog import SHAPE_PARAMETERS

        extra["shape_parameters"] = {kind: list(keys) for kind, keys in SHAPE_PARAMETERS.items()}
        extra["content_boxes"] = (
            "inspect reports content_bounds (canvas space) for shapes whose usable inner area is smaller than "
            "their box: a speech bubble's body, a badge or star centre, a ring/frame opening, a device screen. "
            "Centre text there with text within=SHAPE, place within=SHAPE (anchor, margin) or align "
            "relative_to=SHAPE box=content."
        )
    return {
        "topic": topic,
        "topics": chosen,
        **extra,
        "operations": operations,
        "workflows": {name: spec["summary"] for name, spec in workflows.items() if relevant(name)},
        "guidance": list(dict.fromkeys(name for topic in chosen for name in TOPICS[topic][1])),
        "read_guidance": "vixl_guide(brief=NAME) returns a guidance text",
        "gotchas": GOTCHAS,
        "limits": {"operations_per_batch": Limits().max_operations},
        "next": "vixl_operation_schema(types=[...]) returns exact constraints and examples.",
    }
