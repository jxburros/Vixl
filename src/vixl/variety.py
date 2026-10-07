"""Seeded sparse-brief choices and bounded workspace history, without network side effects."""

from collections import Counter
from copy import deepcopy
import json
import os
from pathlib import Path
import random

from . import house_style
from .errors import require
from .safe_catalog import SAFE_PALETTES

VARIETIES = ("low", "medium", "high", "fixed")


def font_next_step(project, seed):
    from .typefaces import roll_pairing

    pairing = project.state.get("design_defaults", {}).get("direction", {}).get("pairing")
    pairing = pairing if pairing and pairing != "workspace-brand" else roll_pairing(seed)[0]["name"]
    return {"pairing": pairing, "installed": False,
            "next_step": f"Install the selected fonts with vixl_font_pair(pairing='{pairing}') or vixl font pair {pairing}; "
                         "layout/template operations use the proofing fallback until fonts are explicitly installed."}


def settings(workspace=None):
    root = Path(workspace or Path.cwd()).resolve()
    path = root / ".vixl" / "variety.json"
    require(path.resolve().is_relative_to(root), "Variety settings must stay in the workspace", "forbidden")
    if not path.exists():
        return {}
    from .assets import read_bounded

    result = json.loads(read_bounded(path, 16384))
    require(isinstance(result, dict) and set(result) <= {"variety", "seed", "house_style"},
            "Variety settings accept variety, seed and house_style")
    require(result.get("variety", "medium") in VARIETIES, "Invalid workspace variety")
    from .house_style import versions

    require(result.get("house_style", versions()[-1]) in versions(),
            f"house_style must be one of {versions()} (the house-style version new documents use)")
    return result


def house_style_version(project=None, version=None, workspace=None):
    """The house-style version to roll with: an explicit one, then the document's stored one, then the
    workspace setting (``.vixl/variety.json`` ``house_style``), then the current version."""
    from . import house_style

    if version is None and project is not None:
        version = project.state.get("design_defaults", {}).get("house_style_version")
    if version is None:
        workspace = workspace or (getattr(project, "_workspace", None) if project else None)
        version = settings(workspace).get("house_style")
    version = version or house_style.VERSION
    require(version in house_style.versions(), f"house_style_version must be one of {house_style.versions()}",
            field="house_style_version")
    return version


def seed_for(project=None, seed=None, variety=None, workspace=None):
    from .typefaces import resolve_seed

    defaults = project.state.get("design_defaults", {}) if project else {}
    workspace = workspace or (getattr(project, "_workspace", None) if project else None)
    policy = settings(workspace)
    variety = variety or defaults.get("variety") or policy.get("variety", "medium")
    require(variety in VARIETIES, "variety must be low, medium, high or fixed", field="variety")
    if seed is None and variety == "fixed":
        seed = defaults.get("seed", policy.get("seed", 0))
    return resolve_seed(seed), variety


def history(workspace):
    """Read a short bounded history. History never affects an explicit seed."""
    if workspace is None:
        return []
    root = Path(workspace).resolve()
    path = root / ".vixl" / "rolls.json"
    require(path.resolve().is_relative_to(root), "Roll history must stay in the workspace", "forbidden")
    if not path.exists():
        return []
    from .assets import read_bounded

    value = json.loads(read_bounded(path, 262144))
    require(isinstance(value, list) and all(isinstance(v, dict) for v in value), "Invalid roll history")
    return value[-32:]


def remember(workspace, result):
    if workspace is None:
        return
    from .fileio import file_lock

    root = Path(workspace).resolve()
    path = root / ".vixl" / "rolls.json"
    require(path.resolve().is_relative_to(root), "Roll history must stay in the workspace", "forbidden")
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(str(path)):
        records = history(root)
        records.append({"seed": result["seed"], **result["direction"]})
        from .fileio import temporary

        fd, staged = temporary(path.parent, like=path if path.exists() else None)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(json.dumps(records[-32:], separators=(",", ":")).encode())
            os.replace(staged, path)
        finally:
            if os.path.exists(staged):
                os.unlink(staged)


def choose(rng, pool, recent, key, weights=None):
    """A weighted pick that avoids repeating recent choices. ``weights`` (name: weight) defaults to 1."""
    pool = list(pool)
    counts = Counter(str(row.get(key)) for row in recent)
    # Never repeat the immediately preceding choice when another safe choice is available.
    previous = str(recent[-1].get(key)) if recent else None
    available = [x for x in pool if str(x) != previous] or pool
    base = weights or {}
    return rng.choices(available, weights=[base.get(x, 1) / (1 + counts[str(x)]) ** 2 for x in available], k=1)[0]


def orientation(width, height):
    """The canvas shape the layouts use: wide, landscape, square, portrait or tall."""
    aspect = width / height
    return ("wide" if aspect >= 2.2 else "tall" if aspect <= 0.45 else "landscape" if aspect > 1.15
            else "portrait" if aspect < 0.87 else "square")


def tier_weights(variety, moods=()):
    """Tier weights for a variety level; expressive moods lean bold, quiet moods lean safe."""
    from . import house_style

    weights = dict(house_style.level(variety)["tiers"])
    tuning = house_style.moods()
    moods = set(moods or ())
    for group in ("expressive", "quiet"):
        if moods & set(tuning[group]):
            scale = tuning[f"{group}_tier_scale"]
            weights = {tier: value * scale.get(tier, 1) for tier, value in weights.items()}
    return {tier: value for tier, value in weights.items() if value > 0}


def pick_tier(rng, variety, moods=()):
    weights = tier_weights(variety, moods)
    tiers = [tier for tier in ("safe", "bold", "avant-garde") if tier in weights]
    return rng.choices(tiers, weights=[weights[tier] for tier in tiers], k=1)[0]


def tier_pool(kind, tier, purpose, fits=lambda name: True):
    """Sorted entries of ``kind`` in ``tier`` (as ``purpose`` sees them) that ``fits`` accepts. When the tier
    has none, the next quieter tier is used, then the bolder ones; ``explicit`` entries are never rolled."""
    from . import house_style

    order = {"safe": ("safe", "bold", "avant-garde"), "bold": ("bold", "safe", "avant-garde"),
             "avant-garde": ("avant-garde", "bold", "safe")}[tier]
    names = house_style.entries(kind)
    for candidate in order:
        pool = sorted(name for name in names if house_style.tier_of(kind, name, purpose) == candidate and fits(name))
        if pool:
            return pool
    return []


def _weighted(rng, weights):
    names = sorted(name for name, value in weights.items() if value > 0)
    return rng.choices(names, weights=[weights[name] for name in names], k=1)[0]


def dimensions(rng, pairing, variety="medium", *, tier="safe", purpose=None, moods=(), recommend=None):
    """The finishing choices of a roll: component, motif, look and its amount, style, corner, margin and
    background treatment, from the house style for this tier, level and purpose."""
    from . import house_style
    from .resources import catalog

    recommend = recommend or {}
    entries = catalog("containers")
    containers = sorted(name for name, item in entries.items() if item.get("safe")) or sorted(entries)
    container = rng.choice(containers)
    variants = entries[container].get("variants") or {"default": {}}
    settings = house_style.level(variety)
    profile = house_style.profile(purpose)
    tuning = house_style.moods()
    rank = {"safe": 0, "bold": 1, "avant-garde": 2}

    def mood_weight(meta):
        return tuning["match_weight"] if set(moods) & set(meta.get("mood", [])) else 1

    look_meta = house_style.entries("looks")
    looks = {name: weight * mood_weight(look_meta.get(name, {})) * (3 if name in recommend.get("looks", []) else 1)
             for name, weight in profile["look"]["weights"].items()
             if name == "none" or rank.get(house_style.tier_of("looks", name, purpose), 9) <= rank[tier]}
    look = _weighted(rng, looks or {"none": 1})
    amount = 0 if look == "none" else round(profile["look"]["amount"] * settings["look_scale"], 3)
    style_meta = house_style.entries("styles")
    styles = tier_pool("styles", tier, purpose)
    prefer = set(profile["styles"]["prefer"]) | set(recommend.get("styles", []))
    editorial = bool({"editorial", "academic", "classic"} & set(pairing.get("mood", [])))
    style = _weighted(rng, {name: (profile["styles"]["weight"] if name in prefer else 1) * mood_weight(style_meta[name])
                            * (3 if editorial and name == "editorial" else 1) for name in styles})
    treatments = profile["treatments"].get(variety if variety != "fixed" else "medium") or settings["treatments"]
    craft = house_style.craft()
    return {"container": container, "container_variant": rng.choice(sorted(variants)),
            "motif": _weighted(rng, settings["motifs"]),
            "look": look,
            "look_amount": amount,
            "style": style,
            "weight_contrast": "strong" if pairing["heading"]["weight"] - pairing["body"]["weight"] >= 300 else "moderate",
            "margin": rng.choice(craft["margins"]),
            "corner": style_meta[style].get("corner", craft["corner"]),
            "background_treatment": _weighted(rng, treatments),
            "color_assignment": "light"}


def document_defaults(project, *, seed=None, variety=None, workspace=None, purpose=None, house_style_version=None):
    """Roll and store a new document's ``design_defaults``: the seed, variety level, purpose (explicit, else
    from the named size), the rolled direction and the ``house_style_version`` that made it. The stored
    direction is what later layouts inherit, so a changed house style never reaches existing documents."""
    from .house_style import resolve_purpose
    from .typefaces import roll_document

    if workspace is not None:
        project._workspace = str(Path(workspace).resolve())
    purpose, source = resolve_purpose(purpose, size=project.state.get("canvas", {}).get("size"))
    result = roll_document(project, workspace=workspace, seed=seed, variety=variety, purpose=purpose,
                           house_style_version=house_style_version)
    project.state["design_defaults"] = {"seed": result["seed"], "variety": result["variety"],
                                        "house_style_version": result["house_style_version"],
                                        **({"purpose": result.get("purpose") or purpose} if purpose else {}),
                                        **({"purpose_source": source} if purpose else {}),
                                        "direction": deepcopy(result["direction"])}
    record_as_creation(project, "Choose reproducible design defaults")
    return project.state["design_defaults"]


def record_as_creation(project, label):
    """Fold changes into a fresh document's first revision, or record them as ``label``."""
    initial = project.nodes.get(project.head, {})
    if (project.path is None and len(project.nodes) == 1 and initial.get("parent") is None
            and not initial.get("operations") and not project.checkpoints and not project.transaction):
        # Like Project.sized, choices made during construction belong to creation, so the
        # first user edit remains the first undoable step. Saved/edited documents keep history.
        first = initial.get("label", "Create document")
        project.nodes, project.head, project._head_state, project.branches = {}, None, None, {}
        project._verified = set()
        project._record([], first)
    else:
        project._record([], label)


def sparse_options(project, op, *, keys=("palette", "look")):
    """Explicit choices and brand always win; document defaults carry the chosen seed."""
    result = deepcopy(op)
    defaults = project.state.get("design_defaults", {})
    seed = op.get("seed")
    if seed is None and defaults:
        seed = defaults["seed"]
    seed, variety = seed_for(project, seed, op.get("variety"))
    result["seed"] = seed
    rng = random.Random(seed)
    direction = defaults.get("direction", {}) if op.get("seed") is None else {}
    for key in keys:
        if key in result:
            continue
        if key in direction:
            result[key] = deepcopy(direction[key])
        elif key == "palette":
            result[key] = rng.choice(sorted(SAFE_PALETTES))
        elif key == "look":
            result[key] = rng.choice(["none", "soft-shadow", "grain", "paper"] if variety == "high" else ["none", "soft-shadow"])
    return result


def apply_direction(project, builder, direction):
    """Apply restrained geometry/finish choices to the editable scaffold."""
    from .operations import execute
    from .styles import apply_operations

    if direction.get("place_container"):
        _compose_component(project, builder, direction)
    before = {layer["id"] for layer in project.state["layers"] if layer["name"] not in builder.created}
    own = [layer for layer in project.state["layers"] if layer["id"] not in before]
    background = next((layer for layer in own if layer["name"] == builder.name("background")), None)
    treatment = direction.get("background_treatment", "flat")
    require(treatment in ("flat", "gradient", "split", "pattern"), "Unknown background treatment", field="direction")
    if background and treatment == "gradient":
        background.update(type="gradient", start="@background", end="@surface", direction="vertical")
        background.pop("color", None)
    elif background and treatment in ("split", "pattern"):
        name = builder.name("background-detail")
        if treatment == "split":
            operation = {"type": "shape", "name": name, "shape": "rectangle", "x": builder.W * 0.72,
                         "y": 0, "width": round(builder.W * 0.28), "height": builder.H, "fill": "@surface"}
        else:
            operation = {"type": "shape", "name": name, "shape": "ellipse", "x": builder.W * 0.90,
                         "y": builder.T, "width": max(2, builder.unit // 3), "height": max(2, builder.unit // 3), "fill": "@muted"}
        execute(project, operation)
        detail = project.layer()
        if treatment == "pattern":
            execute(project, {"type": "repeat", "target": detail["id"], "count": 8, "dy": builder.ch / 9})
        detail.update(role="decoration", opacity=0.25)
        project.state["layers"].remove(detail)
        project.state["layers"].insert(project.state["layers"].index(background) + 1, detail)
        builder.created.append(name)
    # A direction without a corner (an older or hand-written one) takes the house corner, sharp (E8).
    corner = direction.get("corner") or house_style.rule("corner")
    scale = house_style.rule("corner_scale")
    require(corner in scale, "Unknown corner style", field="direction")
    for layer in own:
        if layer.get("shape") in ("rectangle", "rounded-rectangle") and layer is not background:
            amount = scale[corner]
            radius = min(layer["width"], layer["height"]) * amount
            layer.update(shape="rounded-rectangle" if radius else "rectangle", radius=radius)
    motif = direction.get("motif", "none")
    require(motif in ("none", "rule", "ellipse", "rectangle"), "Unknown motif", field="direction")
    if motif != "none":
        size = max(3, round(builder.unit))
        name = builder.name("direction-motif")
        execute(project, {"type": "shape", "shape": "ellipse" if motif == "ellipse" else "rectangle", "name": name,
                          "x": builder.R - size, "y": builder.T / 2, "width": size,
                          "height": max(2, size // 4) if motif == "rule" else size, "fill": "@accent"})
        project.layer().update(role="decoration")
        builder.created.append(name)
    look = direction.get("look", "none")
    if look != "none":
        # Directions rolled before house-style version 2 carry no amount and keep their faint 0.1.
        amount = direction.get("look_amount", house_style.legacy(1)["look_amount"])
        for layer, color in _look_targets(project, builder, own, background, look):
            execute(project, {"type": "look", "target": layer["id"], "look": look, "amount": amount,
                              **({"color": color} if color else {})})
    if direction.get("style"):
        for operation in apply_operations(direction["style"], palette=False):
            execute(project, operation)


def _look_targets(project, builder, own, background, look):
    """Where a rolled look goes: texture looks on the background; shadow, outline and glow looks on the solid
    shapes (buttons, panels, blocks; not hairline rules or full-canvas fields), where they read as a finish
    without touching the text."""
    from . import house_style

    meta = house_style.entries("looks").get(look, {})
    if meta.get("target", "background" if look in ("grain", "paper", "subtle-grain", "light-paper") else "shapes") == "background":
        return [(background, None)] if background else []
    minimum = max(4, builder.unit)
    shapes = [layer for layer in own if layer.get("type") == "shape" and layer is not background
              and layer.get("shape") in ("rectangle", "rounded-rectangle", "ellipse")
              and min(layer.get("width", 0), layer.get("height", 0)) >= minimum
              and layer.get("width", 0) * layer.get("height", 0) < builder.W * builder.H * 0.6]
    # The house shadow is a solid offset in the ink colour, so it reads in light and dark mode alike.
    color = "@ink" if look in ("hard-shadow", "outline") else None
    return [(layer, color) for layer in shapes]


def _compose_component(project, builder, direction):
    """An explicitly selected component replaces the scaffold's text block, retaining all copy."""
    from .operations import execute
    from .resources import get

    item = get("containers", direction["container"], workspace=getattr(project, "_workspace", None))
    variables = {key: ("" if isinstance(value, str) and value.startswith("[") else value)
                 for key, value in item.get("defaults", {}).items()}
    content = {key: builder.op[key] for key in ("title", "subtitle", "body", "label", "cta", "caption", "items")
               if builder.op.get(key)}
    remaining = dict(content)
    slots = list(variables)
    # Semantic matches first; otherwise the first component copy slot receives the title.
    aliases = {"name": "title", "value": "title", "quote": "title", "plan": "title", "button": "cta",
               "bio": "body", "features": "items", "price": "caption", "date": "label", "role": "subtitle"}
    for slot in slots:
        key = slot if slot in content else aliases.get(slot)
        if key in remaining:
            variables[slot] = remaining.pop(key)
    if "title" in remaining:
        slot = next((key for key in slots if key not in ("ink", "accent", "photo") and not variables[key]), None)
        if slot:
            variables[slot] = remaining.pop("title")
    background_name = builder.name("background")
    doomed = [layer["id"] for layer in project.state["layers"]
              if layer["name"] in builder.created and layer["name"] != background_name]
    for ident in doomed:
        if any(layer["id"] == ident for layer in project.state["layers"]):
            execute(project, {"type": "remove", "target": ident})
    builder.created = [background_name] if any(layer["name"] == background_name for layer in project.state["layers"]) else []
    width = max(item.get("min_width", 1), round(builder.cw))
    width = min(item.get("max_width", 16384), width)
    height = min(round(builder.ch * (0.6 if remaining else 0.9)), round(width * item["height"] / item["width"]))
    height = max(item.get("min_height", 1), height)
    height = min(item.get("max_height", 16384), height)
    name = builder.name("component")
    before = {layer["id"] for layer in project.state["layers"]}
    execute(project, {"type": "container-place", "name": name, "resource": direction["container"],
                      "variant": direction["container_variant"], "variables": variables,
                      "width": width, "height": height, "x": builder.L, "y": builder.T, "seed": builder.seed})
    builder.created.extend(layer["name"] for layer in project.state["layers"] if layer["id"] not in before)
    y = builder.T + height + builder.unit * 2
    for key, value in remaining.items():
        name = builder.name("component-" + key)
        size = max(10, min(builder.sizes["body"], round((builder.B - y) / max(1, len(remaining)) / 1.5)))
        execute(project, {"type": "text", "name": name, "text": str(value), "size": size,
                          "x": builder.L, "y": y, "color": "@ink", "font": builder.font or "DejaVuSans.ttf"})
        builder.created.append(name)
        y += project.layer()["height"] + builder.unit
