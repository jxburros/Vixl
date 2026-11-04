"""Task-focused discovery derived from the canonical operation and workflow catalogs."""

import re

from .model import Limits

# topic -> (words that select it and its operations, guidance names readable with vixl_reference(NAME))
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
    "atmosphere": ("atmosphere reflection haze fog mist star stars string lights bokeh water motif motifs",
                   ["motifs", "natural-color-light"]),
    "film": ("film video audio caption", ["film-review", "audio-composition"]),
    "layout": (
        "layout container template stack flex flexbox css fit align distribute spatial grid snap guide comic adapt "
        "responsive",
        ["layout", "stacks", "overall", "finishing"],
    ),
    "color": ("palette color swatch look style lighting", ["color", "natural-color-light", "accessibility"]),
    "export": ("export film merge form", ["print"]),
    "testing": ("test tests testing suite suites check assert verify qa baseline capture critique polish finishing",
                ["testing", "finishing", "accessibility"]),
    "objects": ("object objects part parts kind subject isolate taxonomy mascot", ["multi-part-objects",
                                                                                  "anatomy-proportions"]),
    "accessibility": ("accessibility alt language reading", ["accessibility"]),
}
# Each gotcha carries the topics it applies to; ``lookup(topic)`` returns only the matching ones (#615).
GOTCHAS = [
    {"topics": ["layout", "text", "drawing", "shapes", "animation", "objects"],
     "text": "x/y are parent-local pixels unless move (or shape/text/solid/gradient with target) uses space=canvas; "
             "pivot units=canvas takes a document point. Width/height percentages use the parent box."},
    {"topics": ["drawing", "shapes"],
     "text": "SVG path coordinates are literal local pixels, not normalized to width/height; without width/height a "
             "path's box reaches its farthest point; path-fit scales the geometry."},
    {"topics": ["color", "animation", "text", "drawing", "shapes", "atmosphere"],
     "text": "Opacity is 0-1 everywhere (opacity, keyframes, layer-style, creation fields); '70%' is read as 0.7, 70 "
             "is an error."},
    {"topics": ["layout", "text", "drawing", "shapes", "color", "objects"],
     "text": "Per-layer operations take targets: [...] to apply to several layers; group/align/distribute treat "
             "targets jointly."},
    {"topics": ["text"],
     "text": "font accepts a registered name or heading/body role. Import/install fonts before applying text batches."},
    {"topics": ["layout", "text", "drawing", "testing", "export", "objects"],
     "text": "Batches are atomic; dry_run validates without changing the document. Use history begin/commit for "
             "several batches."},
    {"topics": ["layout", "export", "testing", "accessibility"],
     "text": "Use layer-intent allow_crop=true for intentional bleed. Summary diagnostics offer bounded full detail "
             "with pagination."},
    {"topics": ["animation", "film"],
     "text": "For motion, check sampled frames and film-preview with the camera before a full export; start at draft "
             "quality."},
    {"topics": ["animation"],
     "text": "Loops: motion recipes take period, stagger and many targets in one operation; a duration that is a whole "
             "number of periods returns every track to its frame-0 value."},
    {"topics": ["animation", "drawing"],
     "text": "No expression language: generate repetition with keyframes sample {fn: sin|triangle|noise, period, "
             "amplitude, step_ms}, motion recipe wiggle (amount, frequency, samples) or line-boil, and "
             "repeat/radial-repeat per-step fields with seeded jitter; scatter/pattern-scatter with merge: true keep "
             "many copies to a few layers."},
]


def gotchas(topics=None, words=()):
    """The gotcha texts for ``topics`` (any match) or whose text mentions one of ``words``; every text when
    ``topics`` is None."""
    if topics is None:
        return [entry["text"] for entry in GOTCHAS]
    wanted = set(topics)
    requested = {stem(word) for word in words}
    found = []
    for entry in GOTCHAS:
        own = {stem(word) for word in re.findall(r"[a-z]+", entry["text"].lower())}
        if wanted & set(entry["topics"]) or (requested and requested & own and not wanted):
            found.append(entry["text"])
    return found


def stem(word):
    """``word`` without a plural ending ("charts" -> "chart", "boxes" -> "box", "suites" -> "suite"), applied to
    both the request and each vocabulary so whole words match in either number."""
    if len(word) > 4 and word.endswith("es") and word[:-2].endswith(("x", "z", "ch", "sh", "ss")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def topics():
    """TOPICS plus the topics plugins contribute through their manifest's ``capabilities`` key."""
    from .plugins import manifests

    merged = dict(TOPICS)
    for manifest in manifests():
        for name, (vocabulary, guidance) in manifest.get("capabilities", {}).items():
            merged[name] = (vocabulary, list(guidance))
    return merged


def lookup(topic=None, *, fields=False, limit=5):
    """Discovery for ``topic``: the matching operations ranked by keyword score (the first ``limit``; ``more``
    counts the rest; ``limit=None`` lists all), workflows, the topic's gotchas, guidance names and, with
    ``fields``, each operation's fields plus the top operation's brief schema and example."""
    from .schema import operation_schema
    from .workflows import describe

    catalog = {
        entry["properties"]["type"]["const"]: entry
        for entry in operation_schema()["properties"]["operations"]["items"]["oneOf"]
    }
    workflows = describe()["actions"]
    known = topics()
    if not topic:
        return {
            "topics": {name: words for name, (words, _) in known.items()},
            "gotchas": gotchas(),
            "limits": {"operations_per_batch": Limits().max_operations},
            "next": "vixl_reference('capabilities', name=TOPIC, fields=true), then vixl_reference('operations', name=[...]) for exact constraints.",
        }
    words = [stem(word) for word in re.findall(r"[a-z]+", topic.lower())]
    requested = set(words)
    chosen = [
        name for name, (vocabulary, _) in known.items()
        if stem(name) in requested or requested & {stem(word) for word in vocabulary.split()}
    ]
    # Keyword score: the asked-for words weigh most, then each topic's words in their listed order, so "pen" lists
    # pen, shape and path operations before oil-paint (matched only through the topic's "paint"); a name that is
    # itself an asked-for word comes first, and a name matching several words outranks one matching one.
    order = list(dict.fromkeys(words + [stem(word) for name in chosen for word in known[name][0].split()]))
    weight = {word: len(order) - index for index, word in enumerate(order)}

    def score(name):
        """Higher sorts first: an asked-for name, then the best-weighted matching part; simpler names break ties."""
        parts = [stem(part) for part in name.split("-")]
        matched = [weight[part] for part in parts if part in weight]
        if not matched:
            return None
        return (stem(name) in requested, max(matched), -len(parts))

    ranked = sorted((name for name in catalog if score(name)), key=lambda name: (*[-x for x in score(name)], name))
    shown = ranked if limit is None else ranked[:max(int(limit), 0)]
    operations = {
        name: {
            "summary": catalog[name].get("description", ""),
            **({"fields": list(catalog[name]["properties"]), "required": catalog[name]["required"]} if fields else {}),
        }
        for name in shown
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
            "vixl_document(action='inspect', object=NAME|'*') returns the object tree with missing required parts; "
            "vixl_render(isolate=[NAME] or ['object:KIND'], views=['parts'], exploded=true) shows each part; "
            "vixl_export(isolate=[NAME]) exports it alone (.vixl: a portable object for object-place source=). "
            "object-save/object-place reuse an editable object. vixl_reference('objects', name=KIND) reads a "
            "kind with its build block (approach, placements, a working example batch); vixl_apply(workflow="
            "'object-plan', request={kind, height, apply}) scaffolds one as named placeholder parts; {type: object, "
            "action: outline, target: NAME, outline: silhouette|parts|none} applies its outline policy; vixl_check measures "
            "declared objects against their kind (the object check: parts, gaps, proportions, mirrored pairs, "
            "layering; stylized: true skips proportions, depth: far|near orders side-view limbs); "
            "vixl_apply(workflow='resource-save', request={kind: 'objects', name, value}) adds a kind.")
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
                            "vixl_apply(suites=true) or vixl_apply(workflow='check', request={suite}), and before every "
                            "preview. vixl_reference('workflows', name='check').definitions.suite types every rule field.")
    if fields and shown:
        from .schema_docs import schema_brief

        extra["top_operation"] = schema_brief(catalog[shown[0]])
    workflow_names = sorted((name for name in workflows if score(name)),
                            key=lambda name: (*[-x for x in score(name)], name))
    return {
        "topic": topic,
        "topics": chosen,
        **extra,
        "operations": operations,
        **({"more": len(ranked) - len(shown)} if len(ranked) > len(shown) else {}),
        "workflows": {name: workflows[name]["summary"] for name in workflow_names},
        "guidance": list(dict.fromkeys(name for topic in chosen for name in known[topic][1])),
        "read_guidance": "vixl_reference(NAME) returns a guidance text",
        "gotchas": gotchas(chosen, words),
        "limits": {"operations_per_batch": Limits().max_operations},
        "next": "vixl_reference('operations', name=[...]) returns exact constraints and examples"
                + ("; limit=N or limit=null lists more operations." if len(ranked) > len(shown) else "."),
    }
