"""Portable standard-part characters, constrained planar rigs and retargetable cycles."""
from copy import deepcopy
import math
from .errors import require
from .model import finite, uid

TYPES = ("character", "character-save", "character-load", "character-rig", "character-pose", "character-ik", "character-cycle", "character-lipsync")
PARTS = ("torso", "head", "left-eye", "right-eye", "left-brow", "right-brow", "mouth", "hair",
         "left-upper-arm", "left-lower-arm", "left-hand", "right-upper-arm", "right-lower-arm", "right-hand",
         "left-upper-leg", "left-lower-leg", "left-foot", "right-upper-leg", "right-lower-leg", "right-foot", "accessories")
REQUIRED = ("torso", "head", "left-eye", "right-eye", "mouth", "left-upper-arm", "left-lower-arm", "left-hand", "right-upper-arm", "right-lower-arm", "right-hand", "left-upper-leg", "left-lower-leg", "left-foot", "right-upper-leg", "right-lower-leg", "right-foot")
VISEMES = ("rest", "A", "E", "O", "U", "M", "F", "L")


def schemas(add):
    from .motion_schema import documented
    add = documented(add)
    from .schema import S, N
    obj = {"type": "object"}
    time = {"type": ["string", "number"]}
    add("character", {"name": S, "x": N, "y": N, "height": {"type": "integer", "minimum": 40, "maximum": 8192}, "colors": obj, "parts": {"type": "object", "additionalProperties": S}}, ["name"])
    add("character-save", {"name": S}, ["name"])
    add("character-load", {"name": S, "template": S, "source": S, "x": N, "y": N, "scale": N, "colors": obj, "outfit": obj}, ["name"], anyOf=[{"required": ["template"]}, {"required": ["source"]}])
    add("character-rig", {"bones": obj}, ["bones"])
    add("character-pose", {"angles": {"type": "object", "additionalProperties": N}}, ["angles"])
    add("character-ik", {"chain": {"type": "array", "items": S, "minItems": 2, "maxItems": 2}, "point": {"type": "array", "items": N, "minItems": 2, "maxItems": 2}, "bend": {"enum": [-1, 1]}}, ["chain", "point"])
    add("character-cycle", {"cycle": {"enum": ["walk", "run", "idle", "ride", "react"]}, "start": time, "duration": time, "period": N, "amount": N, "samples": {"type": "integer", "minimum": 4, "maximum": 120}}, ["cycle"])
    add("character-lipsync", {"text": S, "start": time, "duration": time, "cues": {"type": "array", "maxItems": 1000, "items": {"type": "object", "properties": {"time": N, "viseme": {"enum": list(VISEMES)}}, "required": ["time", "viseme"], "additionalProperties": False}}}, anyOf=[{"required": ["text"]}, {"required": ["cues"]}])


def standard(project, op):
    from .operations import execute as apply
    name = op["name"]
    height = op.get("height", 320)
    finite(height, "height", 40, 8192)
    factor = height / 320
    colors = {"skin": "#f3bd95", "outfit": "#5079b8", "hair": "#493025", "eyes": "#202938", **op.get("colors", {})}
    # The canonical body is 160×320. Limbs have proximal pivots and rear-to-front order.
    boxes = {
        "left-upper-leg": (51, 180, 23, 57, "outfit"), "left-lower-leg": (52, 235, 21, 55, "skin"), "left-foot": (43, 284, 31, 18, "eyes"),
        "right-upper-leg": (86, 180, 23, 57, "outfit"), "right-lower-leg": (87, 235, 21, 55, "skin"), "right-foot": (87, 284, 31, 18, "eyes"),
        "left-upper-arm": (27, 108, 20, 49, "outfit"), "left-lower-arm": (27, 155, 18, 44, "skin"), "left-hand": (25, 195, 22, 24, "skin"),
        "right-upper-arm": (112, 108, 20, 49, "outfit"), "right-lower-arm": (114, 155, 18, 44, "skin"), "right-hand": (112, 195, 22, 24, "skin"),
        "torso": (45, 101, 70, 92, "outfit"), "head": (43, 20, 75, 85, "skin"), "hair": (41, 15, 79, 31, "hair"),
        "left-eye": (59, 53, 9, 12, "eyes"), "right-eye": (91, 53, 9, 12, "eyes"),
        "left-brow": (55, 45, 17, 3, "hair"), "right-brow": (87, 45, 17, 3, "hair"), "mouth": (70, 79, 22, 7, "eyes"),
    }
    parts = {}
    for part, (x, y, w, h, role) in boxes.items():
        apply(project, {"type": "shape", "shape": "ellipse" if part in ("head", "left-eye", "right-eye", "mouth", "left-hand", "right-hand") else "rectangle",
                       "name": f"{name}/{part}", "x": round(x * factor), "y": round(y * factor), "width": max(1, round(w * factor)), "height": max(1, round(h * factor)), "fill": colors[role], "stroke_width": 0})
        layer = project.layer()
        layer.update(character_part=part, character_color=role, pivot=[0.5, 0] if "arm" in part or "leg" in part else [0.5, 0.5])
        parts[part] = layer["id"]
    apply(project, {"type": "group", "name": name, "targets": list(parts.values())})
    group = project.layer()
    group.update(x=op.get("x", 0), y=op.get("y", 0), character={"version": 1, "parts": parts, "bones": {}})
    bones = {}
    for side in ("left", "right"):
        for limb in ("arm", "leg"):
            upper, lower = f"{side}-upper-{limb}", f"{side}-lower-{limb}"
            end = f"{side}-" + ("hand" if limb == "arm" else "foot")
            a, b, c = [project.layer(parts[p]) for p in (upper, lower, end)]
            bones[upper] = {"layer": a["id"], "origin": [a["x"] + a["width"] / 2, a["y"]], "length": b["y"] - a["y"], "angle": 0, "limits": [-100, 100]}
            bones[lower] = {"layer": b["id"], "parent": upper, "length": c["y"] - b["y"], "angle": 0, "limits": [-150, 150]}
            bones[end] = {"layer": c["id"], "parent": lower, "length": c["height"], "angle": 0, "limits": [-70, 70]}
            c["pivot"] = [0.5, 0]
    group["character"]["bones"] = bones
    pose(project, group, {})
    project.state["active_layer"] = group["id"]
    return group


def rig(project, target):
    group = project.layer(target)
    require(group["type"] == "group" and "character" in group, "Target must be a standard character")
    return group


def pose(project, group, angles):
    bones = group["character"]["bones"]
    require(set(angles) <= set(bones), "Pose references an unknown bone")
    solved = {}
    pending = set()
    def visit(name):
        require(name not in pending, "Rig parent cycle")
        if name in solved:
            return solved[name]
        pending.add(name)
        bone = bones[name]
        lo, hi = bone.get("limits", [-180, 180])
        angle = max(lo, min(hi, finite(angles.get(name, bone.get("angle", 0)), "joint angle", -3600, 3600)))
        bone["angle"] = angle
        parent = bone.get("parent")
        if parent:
            require(parent in bones, f"Unknown parent bone: {parent}")
            origin, parent_angle, length = visit(parent)
            rad = math.radians(parent_angle)
            origin = [origin[0] + math.sin(rad) * length, origin[1] + math.cos(rad) * length]
            angle += parent_angle
        else:
            origin = bone.get("origin", [0, 0])
        length = finite(bone["length"], "bone length", 0.01, 1e6)
        layer = project.layer(bone["layer"])
        px, py = layer.get("pivot", [0.5, 0])
        layer.update(x=origin[0] - px * layer["width"], y=origin[1] - py * layer["height"], rotation=-angle, constraints={})
        solved[name] = (origin, angle, length)
        pending.remove(name)
        return solved[name]
    for name in bones:
        visit(name)
    return solved


def execute(project, op):
    from .operations import execute as apply
    kind = op["type"]
    if kind == "character":
        if "parts" not in op:
            return standard(project, op)
        require(set(op["parts"]) <= set(PARTS) | {f"viseme-{v}" for v in VISEMES}, "Unknown standard character part")
        parts = {part: project.layer(ref)["id"] for part, ref in op["parts"].items()}
        require(all(part in parts for part in REQUIRED), "Character is missing required standard parts")
        require(len(set(parts.values())) == len(parts), "Each character part needs its own layer")
        apply(project, {"type": "group", "name": op["name"], "targets": list(parts.values())})
        project.layer()["character"] = {"version": 1, "parts": parts, "bones": {}}
        for axis in ("x", "y"):
            if axis in op:
                project.layer()[axis] = op[axis]
        for part, ident in parts.items():
            project.layer(ident).update(character_part=part, pivot=[0.5, 0] if "arm" in part or "leg" in part else [0.5, 0.5])
        return
    if kind == "character-load":
        if "source" in op:
            from .film import local_path
            root = getattr(project, "_workspace", None)
            require(root is not None, "Character imports need a project workspace")
            template = op.get("template", op["name"] + "-imported")
            import_character(project, local_path(root, op["source"]), template)
            op = {**op, "template": template}
        library = project.state.get("character_library", {})
        require(op["template"] in library, "Unknown character template; save one with character-save")
        snapshot = deepcopy(library[op["template"]])
        mapping = {layer["id"]: uid("lyr") for layer in snapshot}
        from .operations import append_layer
        for layer in snapshot:
            old = layer["id"]
            layer["id"] = mapping[old]
            layer["name"] = op["name"] if "character" in layer else f"{op['name']}/{layer.get('character_part', old)}"
            if layer.get("parent"):
                layer["parent"] = mapping.get(layer["parent"])
            if layer.get("clip") in mapping:
                layer["clip"] = mapping[layer["clip"]]
            for anchor, expression in list(layer.get("constraints", {}).items()):
                if isinstance(expression, str):
                    for previous, replacement in mapping.items():
                        if expression.startswith(previous + "."):
                            layer["constraints"][anchor] = replacement + expression[len(previous):]
                            break
            if "character" in layer:
                layer["character"]["parts"] = {p: mapping[i] for p, i in layer["character"]["parts"].items()}
                for bone in layer["character"]["bones"].values():
                    bone["layer"] = mapping[bone["layer"]]
                layer.update(x=op.get("x", 0), y=op.get("y", 0))
                scale = finite(op.get("scale", 1), "scale", 0.01, 100)
                layer.update(width=max(1, round(layer["width"] * scale)), height=max(1, round(layer["height"] * scale)))
                root = layer
            role = layer.get("character_color")
            if role in op.get("colors", {}):
                layer["fill"] = op["colors"][role]
            if layer.get("character_part") in op.get("outfit", {}):
                layer["fill"] = op["outfit"][layer["character_part"]]
            append_layer(project, layer)
        project.state["active_layer"] = root["id"]
        return
    group = rig(project, op.get("target"))
    character = group["character"]
    if kind == "character-save":
        from .design import descendants, named
        ids = descendants(project, group["id"]) | {group["id"]}
        layers = deepcopy([layer for layer in project.state["layers"] if layer["id"] in ids])
        for layer in layers:
            if layer["id"] == group["id"]:
                layer.pop("parent", None)
        project.state.setdefault("character_library", {})[named(op["name"])] = layers
    elif kind == "character-rig":
        require(1 <= len(op["bones"]) <= 64, "Rig needs 1–64 bones")
        bones = deepcopy(op["bones"])
        for name, bone in bones.items():
            require(isinstance(bone, dict) and set(bone) <= {"part", "layer", "parent", "origin", "length", "limits", "angle"}, "Invalid bone fields")
            part = bone.pop("part", name)
            bone["layer"] = project.layer(bone.get("layer", character["parts"].get(part)))["id"]
            require(bone["layer"] in character["parts"].values(), "Bone must belong to the character")
            limits = bone.get("limits", [-180, 180])
            require(isinstance(limits, list) and len(limits) == 2 and limits[0] <= limits[1], "Joint limits need [min,max]")
            for value in limits:
                finite(value, "joint limit", -3600, 3600)
            if "origin" in bone:
                require(isinstance(bone["origin"], list) and len(bone["origin"]) == 2, "Bone origin is [x,y]")
                for value in bone["origin"]:
                    finite(value, "bone origin", -1e6, 1e6)
            require("length" in bone, "Bone needs length")
            project.layer(bone["layer"])["pivot"] = [0.5, 0]
        character["bones"] = bones
        pose(project, group, {})
    elif kind == "character-pose":
        pose(project, group, op["angles"])
    elif kind == "character-ik":
        upper, lower = op["chain"]
        bones = character["bones"]
        require(upper in bones and lower in bones and bones[lower].get("parent") == upper, "IK needs a parent-child two-bone chain")
        current = pose(project, group, {})
        origin, _, a = current[upper]
        b = bones[lower]["length"]
        x, y = op["point"]
        finite(x, "IK x", -1e6, 1e6)
        finite(y, "IK y", -1e6, 1e6)
        dx, dy = x - origin[0], y - origin[1]
        d = max(1e-9, min(a + b, max(abs(a - b), math.hypot(dx, dy))))
        bend = op.get("bend", 1)
        elbow = bend * math.acos(max(-1, min(1, (d * d - a * a - b * b) / (2 * a * b))))
        shoulder = math.atan2(dx, dy) - math.atan2(b * math.sin(elbow), a + b * math.cos(elbow))
        parent = bones[upper].get("parent")
        pose(project, group, {upper: math.degrees(shoulder) - (current[parent][1] if parent else 0), lower: math.degrees(elbow)})
    elif kind == "character-cycle":
        cycle(project, group, op)
    else:
        lipsync(project, group, op)


def cycle(project, group, op):
    from .timeline import _timeline, parse_time, execute_timeline
    timeline = _timeline(project)
    start = parse_time(op.get("start", 0), timeline["duration"], timeline.get("markers"))
    duration = parse_time(op.get("duration", 1000), timeline["duration"], timeline.get("markers"))
    period = finite(op.get("period", 500 if op["cycle"] == "run" else 1000), "cycle period", 50, 600000)
    amplitude = finite(op.get("amount", 30), "cycle amplitude", 0, 90)
    count = op.get("samples", min(60, max(8, math.ceil(duration / period * 24))))
    from copy import copy
    candidate = copy(project)
    candidate.state = deepcopy(project.state)
    cg = candidate.layer(group["id"])
    bones = cg["character"]["bones"]
    require(bones, "Character needs a rig before applying a cycle")
    require((count + 1) * len(bones) * 3 <= 8192, "Cycle exceeds key budget; use fewer samples")
    for i in range(count + 1):
        phase = math.tau * duration * i / count / period
        angles = {}
        for bone in bones:
            side = 1 if bone.startswith("left") else -1
            if op["cycle"] in ("walk", "run"):
                sign = -1 if "arm" in bone else 1
                angles[bone] = sign * side * amplitude * math.sin(phase) if "upper" in bone else max(0, side * amplitude * math.sin(phase + 0.8)) if "lower" in bone else 0
            elif op["cycle"] == "idle":
                angles[bone] = 2 * math.sin(phase + (0.5 if "lower" in bone else 0))
            elif op["cycle"] == "ride":
                angles[bone] = (45 if "upper-leg" in bone else -70 if "lower-leg" in bone else 10) + 3 * math.sin(phase)
            else:
                u = i / count
                angles[bone] = side * amplitude * (-0.2 * math.sin(math.pi * u / 0.2) if u < 0.2 else math.sin(math.pi * (u - 0.2) / 0.8))
        pose(candidate, cg, angles)
        for bone in bones.values():
            layer = candidate.layer(bone["layer"])
            for prop in ("rotation", "x", "y"):
                execute_timeline(project, {"type": "keyframe", "target": layer["id"], "property": prop, "time": start + round(duration * i / count), "value": layer[prop]})


def lipsync(project, group, op):
    from .timeline import _timeline, parse_time, execute_timeline
    timeline = _timeline(project)
    start = parse_time(op.get("start", 0), timeline["duration"], timeline.get("markers"))
    length = parse_time(op.get("duration", 1000), timeline["duration"], timeline.get("markers"))
    require(length >= 10, "Lip sync duration must be at least 10 ms")
    parts = group["character"]["parts"]
    mouth = project.layer(parts["mouth"])
    if "cues" in op:
        cues = op["cues"]
    else:
        text = op["text"]
        require(0 < len(text) <= 1000, "Lip sync text must have 1–1000 characters")
        def viseme(char):
            return "A" if char in "a" else "E" if char in "ei" else "O" if char in "o" else "U" if char in "uw" else "M" if char in "bmp" else "F" if char in "fv" else "L" if char in "ltdn" else "rest"
        cues = [{"time": length * i / len(text), "viseme": viseme(char)} for i, char in enumerate(text.lower())]
    cues = [*cues, {"time": length, "viseme": "rest"}]
    dimensions = {"rest": (1, 1), "A": (1.2, 2.8), "E": (1.5, 1.7), "O": (0.7, 3), "U": (0.6, 2.2), "M": (1, 0.35), "F": (1.1, 0.65), "L": (0.9, 1.8)}
    for cue in cues:
        time = start + finite(cue["time"], "viseme time", 0, length)
        require(cue["viseme"] in VISEMES, "Unknown viseme")
        variants = {v: parts[f"viseme-{v}"] for v in VISEMES if f"viseme-{v}" in parts}
        if variants:
            # Partial sets fall back to the base mouth; complete sets can use drawn phonemes.
            for v, ident in variants.items():
                execute_timeline(project, {"type": "keyframe", "target": ident, "property": "visible", "time": time, "value": v == cue["viseme"]})
            execute_timeline(project, {"type": "keyframe", "target": mouth["id"], "property": "visible", "time": time, "value": cue["viseme"] not in variants})
        sx, sy = dimensions[cue["viseme"]]
        for prop, value in (("scale-x", sx), ("scale-y", sy)):
            execute_timeline(project, {"type": "keyframe", "target": mouth["id"], "property": prop, "time": time, "value": value, "easing": "hold"})


def findings(project):
    result = []
    ids = {layer["id"] for layer in project.state["layers"]}
    for layer in project.state["layers"]:
        if "character" not in layer:
            continue
        parts = layer["character"].get("parts", {})
        missing = [p for p in REQUIRED if p not in parts or parts[p] not in ids]
        if missing:
            result.append({"check": "character", "severity": "error", "layer": layer["id"], "message": "Missing character parts: " + ", ".join(missing)})
        for name, bone in layer["character"].get("bones", {}).items():
            lo, hi = bone.get("limits", [-180, 180])
            if not lo <= bone.get("angle", 0) <= hi:
                result.append({"check": "character", "severity": "error", "layer": layer["id"], "message": f"Bone {name} exceeds joint limits"})
    return result


def export_character(project, target, path):
    """Save only a character's artwork/resources in a fresh portable .vixl document."""
    from .project import Project
    from .design import descendants
    from .validation import check_state
    from pathlib import Path
    require(Path(path).suffix.lower() == '.vixl', 'Character assets use the .vixl extension')
    require(not Path(path).exists(), 'Character output already exists')
    group = rig(project, target)
    ids = descendants(project, group['id']) | {group['id']}
    width, height = max(1, math.ceil(group['width'])), max(1, math.ceil(group['height']))
    candidate = Project(width, height, limits=project.limits)
    # Keep design resources without carrying unrelated scene layers, sound or history.
    for key in ('fonts', 'font_fallbacks', 'swatches', 'palettes', 'character_styles', 'paragraph_styles', 'variables', 'symbols', 'brushes'):
        if key in project.state:
            candidate.state[key] = deepcopy(project.state[key])
    candidate.state['layers'] = deepcopy([layer for layer in project.state['layers'] if layer['id'] in ids])
    candidate.state['active_layer'] = group['id']
    saved_group = candidate.layer(group['id'])
    saved_group.update(x=0, y=0, constraints={})
    saved_group.pop('parent', None)
    candidate.assets = dict(project.assets)
    check_state(candidate, candidate.state)
    candidate._record([], 'Export reusable character')
    candidate.save(path)
    return {'output': str(path), 'character': group['name'], 'parts': sorted(group['character']['parts'])}


def import_character(project, path, name):
    """Import a portable character asset as a library template, without instantiating it."""
    from .project import Project
    from .design import descendants, named
    from .render import resolved_layers
    source = Project.load(path, limits=project.limits)
    groups = [layer for layer in source.state['layers'] if 'character' in layer]
    require(len(groups) == 1, 'Character asset must contain exactly one standard character')
    group = groups[0]
    ids = descendants(source, group['id']) | {group['id']}
    # Resolve palette tokens and variables in the source context before importing them.
    layers = deepcopy([layer for layer in resolved_layers(source) if layer['id'] in ids])
    for layer in layers:
        if layer['id'] == group['id']:
            layer.pop('parent', None)
            layer.update(x=0, y=0, constraints={})
    project.assets.update(source.assets)
    project.state.setdefault('character_library', {})[named(name)] = layers
    return {'template': name, 'parts': sorted(group['character']['parts'])}
