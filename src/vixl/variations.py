"""The ``variations`` workflow: seeded rolls of the open document side by side, to choose one.

Each tile is the document with one seeded roll (palette, layout, fonts, look) applied to a copy, so the open
document never changes. The result is a contact sheet (a PNG in the workspace; the MCP tool returns it too) and,
per tile, the seed, what the roll chose, its finding counts and the ``roll`` step that makes it real: apply that
step to the document to keep the variation.
"""

from .errors import require

MIN_COUNT, MAX_COUNT = 2, 4
ACTIONS = {"variations": ({"count", "seeds", "locks", "slots", "purpose", "mood", "variety", "output", "overwrite",
                           "width", "columns"}, {"output"})}
SUMMARY = ("Render 2-4 seeded rolls of the open document on copies and write a labelled contact sheet; the document "
           "is unchanged. Each tile reports its seed and the roll step that applies it.")
FIELD_TYPES = {
    "count": {"type": "integer", "minimum": MIN_COUNT, "maximum": MAX_COUNT, "default": 3,
              "description": "How many variations to render when seeds is not given (fresh random seeds)."},
    "seeds": {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": 2**32 - 1},
              "minItems": MIN_COUNT, "maxItems": MAX_COUNT, "uniqueItems": True,
              "description": "The roll seeds to show, 2-4 of them (a tile each), instead of count fresh ones."},
    "locks": {"type": "object", "description": "Choices every variation keeps, as the roll step's locks: palette, "
                                                "layout, pairing, mode, look ... Lock the palette to compare layouts."},
    "slots": {"type": "object", "description": "The layout copy ({title, subtitle, body, label, cta, caption}); "
                                                "default: the copy of the document's current layout."},
    "purpose": {"type": "string", "description": "What the document is for (poster, social, slides ...); default: "
                                                  "the document's own."},
    "mood": {"type": "string", "description": "A mood word that steers the roll's palette and pairing."},
    "variety": {"type": "string", "enum": ["low", "medium", "high", "fixed"],
                "description": "How far the rolls may stray from the safe house style; default: the document's."},
    "output": {"type": "string", "description": "Workspace-relative .png path for the contact sheet."},
    "overwrite": {"type": "boolean", "default": False, "description": "Replace output when it exists."},
    "width": {"type": "integer", "minimum": 128, "maximum": 1200, "default": 480,
              "description": "Width in pixels of each tile; the height follows the canvas."},
    "columns": {"type": "integer", "minimum": 1, "maximum": MAX_COUNT,
                "description": "Tiles per row (default: all in one row up to 3, else 2)."},
}


def _seeds(request):
    from .typefaces import resolve_seed

    seeds, count = request.get("seeds"), request.get("count")
    if seeds is not None:
        require(isinstance(seeds, list) and MIN_COUNT <= len(seeds) <= MAX_COUNT and len(set(seeds)) == len(seeds)
                and all(type(seed) is int and 0 <= seed < 2**32 for seed in seeds),
                f"seeds is a list of {MIN_COUNT}-{MAX_COUNT} different integers from 0 to {2**32 - 1}", field="seeds")
        require(count in (None, len(seeds)), "count and seeds disagree; give one", field="count")
        return list(seeds)
    count = 3 if count is None else count
    require(type(count) is int and MIN_COUNT <= count <= MAX_COUNT, f"count is {MIN_COUNT}-{MAX_COUNT}", field="count")
    fresh = []
    while len(fresh) < count:
        seed = resolve_seed("random")
        if seed not in fresh:
            fresh.append(seed)
    return fresh


def _copy(project, request):
    """The layout copy to roll: the request's slots, else those of the document's stored layout."""
    from .layouts import CONTENT_KEYS

    slots = request.get("slots")
    if slots is None:
        recipe = (project.state.get("layout") or {}).get("recipe") or {}
        slots = {key: recipe[key] for key in CONTENT_KEYS if key in recipe}
    require(isinstance(slots, dict) and slots and set(slots) <= set(CONTENT_KEYS),
            "Give slots (title, subtitle, body, label, cta, caption ...): the document has no layout copy to reuse",
            field="slots", allowed=list(CONTENT_KEYS))
    return slots


def variations(session, request, document=None):
    """Run the workflow; see the module docstring. Returns ``{output, size, tiles, unchanged, note}``."""
    import io

    from .deck import tile_sheet
    from .production import write_bytes
    from .proxy import render_preview
    from .typefaces import roll_document

    output = request["output"]
    require(isinstance(output, str) and output.lower().endswith(".png"), "output is a .png path", field="output")
    overwrite = request.get("overwrite", False)
    require(type(overwrite) is bool, "overwrite is boolean", field="overwrite")
    destination = session.resolve(output)
    require(overwrite or not destination.exists(), f"{output} already exists; pass overwrite=true or choose another "
            "name", "exists", field="output")
    seeds = _seeds(request)
    width = request.get("width", 480)
    require(type(width) is int and 128 <= width <= 1200, "width is 128-1200", field="width")
    columns = request.get("columns", len(seeds) if len(seeds) <= 3 else 2)
    require(type(columns) is int and 1 <= columns <= MAX_COUNT, f"columns is 1-{MAX_COUNT}", field="columns")
    locks = request.get("locks")
    require(locks is None or isinstance(locks, dict), "locks is an object of roll choices", field="locks")

    with session.project(document=document) as source:
        original = source.clone()
    slots = _copy(original, request)
    canvas = original.state["canvas"]
    height = max(1, round(width * canvas["height"] / canvas["width"]))
    roll = {key: request[key] for key in ("purpose", "mood", "variety") if request.get(key) is not None}
    tiles, images, labels = [], [], []
    for number, seed in enumerate(seeds, 1):
        trial = original.clone()
        rolled = roll_document(trial, workspace=session.workspace, seed=seed, locks=locks, apply=True, slots=slots,
                               replace=True, **roll)
        direction = rolled["direction"]
        issues = trial.check()["issues"]
        tile = {
            "tile": number, "seed": seed,
            **{key: direction.get(key) for key in ("layout", "palette", "pairing", "mode", "look") if key in direction},
            "findings": {"fix": sum(1 for x in issues if x.get("action") == "fix"),
                         "review": sum(1 for x in issues if x.get("action") == "review")},
            "apply": {"type": "roll", "seed": seed, "replace": True, "slots": slots,
                      **({"locks": locks} if locks else {}), **roll},
        }
        tiles.append(tile)
        images.append(render_preview(trial, width, height).convert("RGBA").resize((width, height)))
        labels.append(f"{number}  seed {seed} · {direction.get('layout')} · {direction.get('palette')}")
    sheet = tile_sheet(images, labels, width=width, height=height, columns=columns)
    buffer = io.BytesIO()
    sheet.save(buffer, format="PNG")
    write_bytes(destination, buffer.getvalue(), replace=overwrite)
    return {
        "output": session.relative(destination), "size": list(sheet.size), "tiles": tiles, "unchanged": True,
        "note": "The document was not changed. To keep a variation, apply its 'apply' step "
                "(vixl_apply operations=[tile.apply]); the same seed gives the same result.",
    }


def dispatch(session, action, request, document=None):
    return variations(session, request, document)
