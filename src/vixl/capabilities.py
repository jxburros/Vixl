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
    "testing": ("test tests testing suite suites check assert verify qa baseline capture", ["testing", "accessibility"]),
    "objects": ("object objects part parts kind subject isolate taxonomy mascot", ["multi-part-objects",
                                                                                  "anatomy-proportions"]),
    "accessibility": ("accessibility alt language reading", ["accessibility"]),
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
    words = re.findall(r"[a-z]+", topic.lower())
    requested = set(words)
    chosen = [
        name for name, (vocabulary, _) in TOPICS.items() if name in requested or requested & set(vocabulary.split())
    ]
    # Rank by the word that matched: the asked-for words first, then each topic's words in their listed order, so
    # "pen" lists pen, shape and path operations before oil-paint (matched only through the topic's "paint").
    order = list(dict.fromkeys(words + [word for name in chosen for word in TOPICS[name][0].split()]))
    rank = {word: index for index, word in enumerate(order)}

    def relevant(name):
        return bool(set(name.split("-")) & rank.keys())

    def score(name):
        return (name not in requested, min(rank[part] for part in name.split("-") if part in rank))

    operations = {
        name: {
            "summary": catalog[name].get("description", ""),
            **({"fields": list(catalog[name]["properties"]), "required": catalog[name]["required"]} if fields else {}),
        }
        for name in sorted((name for name in catalog if relevant(name)), key=score)
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
    if "objects" in chosen:
        from .objects import taxonomy

        extra["objects"] = (
            "Declare a group as one object: {type: object, target: GROUP, kind: dog}; name parts with {type: object, "
            "action: part, target: LAYER, part: leg, side: left}. Paths (dog/head, person/guitar/neck) work wherever a "
            "layer name does; edit-layers selects with where.object, where.object_kind and where.part. "
            "vixl_document_inspect(object=NAME|'*') returns the object tree with missing required parts; "
            "vixl_render_preview(isolate=[NAME] or ['object:KIND'], views=['parts'], exploded=true) shows each part; "
            "vixl_export_file(isolate=[NAME]) exports it alone (.vixl: a portable object for object-place source=). "
            "object-save/object-place reuse an editable object. vixl_resource_get(kind='objects', name=KIND) reads a "
            "kind; vixl_resource_add(kind='objects') adds one.")
        extra["taxonomy"] = taxonomy()
    if "accessibility" in chosen:
        extra["accessibility"] = (
            "layer-intent alt (or decorative: true) on images, frames, charts, links and object groups; "
            "{type: accessibility, lang, title, page_alt, page_lang, reading_order}; vixl_check(checks=[accessibility]) "
            "bundles contrast and color_vision with missing alt, language, small text, colour-only charts and reading "
            "order. Exports carry alt and language; a tagged PDF structure tree is not written.")
    if "testing" in chosen:
        from .effect_workflows import SUITES
        from .workflow_schema import RULE_KINDS

        extra["suite_rules"] = list(RULE_KINDS)
        extra["starter_suites"] = {name: suite["description"] for name, suite in SUITES.items()}
        extra["testing"] = ("Attach suites with suite-set (or workflow suite-use for a starter), run them with "
                            "vixl_operations_apply(suites=true) or vixl_workflow('check', {suite}), and before every "
                            "preview. vixl_workflow_schema().definitions.suite types every rule field.")
    return {
        "topic": topic,
        "topics": chosen,
        **extra,
        "operations": operations,
        "workflows": {name: workflows[name]["summary"] for name in sorted(filter(relevant, workflows), key=score)},
        "guidance": list(dict.fromkeys(name for topic in chosen for name in TOPICS[topic][1])),
        "read_guidance": "vixl_guide(brief=NAME) returns a guidance text",
        "gotchas": GOTCHAS,
        "limits": {"operations_per_batch": Limits().max_operations},
        "next": "vixl_operation_schema(types=[...]) returns exact constraints and examples.",
    }
