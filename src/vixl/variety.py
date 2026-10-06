"""Seeded sparse-brief choices and bounded workspace history, without network side effects."""

from collections import Counter
from copy import deepcopy
import json
import os
from pathlib import Path
import random

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
    require(isinstance(result, dict) and set(result) <= {"variety", "seed"}, "Variety settings accept variety and seed")
    require(result.get("variety", "medium") in VARIETIES, "Invalid workspace variety")
    return result


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


def choose(rng, pool, recent, key):
    pool = list(pool)
    counts = Counter(str(row.get(key)) for row in recent)
    # Never repeat the immediately preceding choice when another safe choice is available.
    previous = str(recent[-1].get(key)) if recent else None
    available = [x for x in pool if str(x) != previous] or pool
    return rng.choices(available, weights=[1 / (1 + counts[str(x)]) ** 2 for x in available], k=1)[0]


def dimensions(rng, pairing, variety="medium"):
    from .resources import catalog

    entries = catalog("containers")
    containers = sorted(name for name, item in entries.items() if item.get("safe")) or sorted(entries)
    editorial = bool({"editorial", "academic", "classic"} & set(pairing.get("mood", [])))
    container = rng.choice(containers)
    variants = entries[container].get("variants") or {"default": {}}
    return {"container": container, "container_variant": rng.choice(sorted(variants)),
            "motif": rng.choice(["none", "rule", "ellipse", "rectangle"] if variety == "high" else ["none", "rule", "ellipse"]),
            "look": rng.choice(["none", "soft-shadow"] if variety in ("low", "fixed") else ["none", "soft-shadow", "subtle-grain", "light-paper"]),
            "style": "editorial" if editorial else rng.choice(["minimalist", "corporate-flat"]),
            "weight_contrast": "strong" if pairing["heading"]["weight"] - pairing["body"]["weight"] >= 300 else "moderate",
            "margin": rng.choice([0.07, 0.085, 0.10]),
            "corner": rng.choice(["sharp", "soft"] if editorial else ["sharp", "soft", "round", "pill"]),
            "background_treatment": rng.choice(["flat", "gradient"] if variety != "high" else ["flat", "gradient", "split", "pattern"]),
            "color_assignment": rng.choice(["light", "light", "dark"])}


def document_defaults(project, *, seed=None, variety=None, workspace=None):
    from .typefaces import roll_document

    if workspace is not None:
        project._workspace = str(Path(workspace).resolve())
    result = roll_document(project, workspace=workspace, seed=seed, variety=variety)
    project.state["design_defaults"] = {"seed": result["seed"], "variety": result["variety"],
                                        "direction": deepcopy(result["direction"])}
    initial = project.nodes.get(project.head, {})
    if (project.path is None and len(project.nodes) == 1 and initial.get("parent") is None
            and not initial.get("operations") and not project.checkpoints and not project.transaction):
        # Like Project.sized, choices made during construction belong to creation, so the
        # first user edit remains the first undoable step. Saved/edited documents keep history.
        label = initial.get("label", "Create document")
        project.nodes, project.head, project._head_state, project.branches = {}, None, None, {}
        project._verified = set()
        project._record([], label)
    else:
        project._record([], "Choose reproducible design defaults")
    return project.state["design_defaults"]


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
    corner = direction.get("corner", "soft")
    require(corner in ("sharp", "soft", "round", "pill"), "Unknown corner style", field="direction")
    for layer in own:
        if layer.get("shape") in ("rectangle", "rounded-rectangle") and layer is not background:
            amount = {"sharp": 0, "soft": 0.08, "round": 0.25, "pill": 0.5}[corner]
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
        targets = ([background] if look in ("grain", "paper", "subtle-grain", "light-paper") else
                   [layer for layer in own if layer.get("shape") == "rounded-rectangle"])
        for layer in targets:
            if layer:
                execute(project, {"type": "look", "target": layer["id"], "look": look, "amount": 0.1})
    if direction.get("style"):
        for operation in apply_operations(direction["style"], palette=False):
            execute(project, operation)


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
