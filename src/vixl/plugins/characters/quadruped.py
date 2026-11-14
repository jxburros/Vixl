"""Four-legged characters: a side-view quadruped rig with walk, trot, gallop, jump and idle cycles.

The rig is the character rig (``character.bones``) with two additions the humanoid does not need: a bone
may attach to its parent at ``at`` (an offset from the parent's joint, so shoulders and hips sit at
different points of the body) and keeps the ``rest`` rotation its artwork was bound in. Joint angles are
then degrees from that bound pose, positive swinging the part's free end towards +x.

Cycles are written as ``joint:BONE`` keys on the character group (plus the body's rise and fall as
``translate-y``), so every key is an angle of a named joint and stays editable. The legs are solved so the
feet stay on the ground while they carry weight: each foot lands in turn, travels back under the body and
swings forward. A jump blends into whatever the joints were doing (``motion.blend_track``) and adds its
height on top of the gait's own rise and fall as an additive layer.
"""
import math

from ...errors import VixlError, require
from ...model import finite

LEGS = ("front-left", "front-right", "hind-left", "hind-right")
SEGMENTS = ("upper-leg", "lower-leg", "foot")
OPTIONAL = ("neck", "tail", "mane", "ear", "eye", "horn")
PARTS = ("body", "head", *OPTIONAL, *(f"{leg}-{segment}" for leg in LEGS for segment in SEGMENTS))
REQUIRED = ("body", "head", *(f"{leg}-{segment}" for leg in LEGS for segment in SEGMENTS[:2]))
UPPER = tuple(f"{leg}-upper-leg" for leg in LEGS)
CYCLES = ("walk", "trot", "gallop", "jump", "idle")
FACINGS = ("right", "left")
PARENTS = {"neck": ("body",), "head": ("neck", "body"), "tail": ("body",), "mane": ("neck", "body"),
           "ear": ("head",), "eye": ("head",), "horn": ("head",)}
# Where a bound part turns when it has no pivot of its own, as fractions of its box.
PIVOTS = {"body": (0.5, 0.5), "head": (0.5, 0.5), "eye": (0.5, 0.5), "neck": (0.5, 1), "ear": (0.5, 1), "horn": (0.5, 1)}
LIMITS = {"body": [-60, 60], "neck": [-70, 70], "head": [-60, 60], "tail": [-120, 120], "upper-leg": [-120, 120],
          "lower-leg": [-150, 150], "foot": [-100, 100]}

# Proportions in the animal's own units; the whole figure is scaled to the requested height.
# shoulder: height of the shoulder joint above the ground. Directions are degrees from straight down
# towards the head end (0 hangs, 90 points forward, 180 points up).
SPECIES = {
    "horse": {"body": (46, 21), "shoulder": 58, "upper": 0.52, "leg": 7, "foot": (8.5, 6), "hock": 0.16,
              "neck": (25, 11, 146), "head": (22, 10.5, 60), "tail": (30, 6, -23), "ear": (3.2, 8, 115),
              "mane": True, "colors": {"coat": "#9a6a44", "mane": "#3b2a20", "hoof": "#2b2320", "eye": "#1d1d1d"}},
    "unicorn": {"body": (46, 21), "shoulder": 58, "upper": 0.52, "leg": 7, "foot": (8.5, 6), "hock": 0.16,
                "neck": (25, 11, 146), "head": (22, 10.5, 60), "tail": (30, 6, -23), "ear": (3.2, 8, 115),
                "mane": True, "horn": True,
                "colors": {"coat": "#f4f1ea", "mane": "#d98bb8", "hoof": "#b9a88f", "eye": "#2a2238", "horn": "#f2c14e"}},
    "dog": {"body": (44, 18), "shoulder": 36, "upper": 0.5, "leg": 6, "foot": (8, 4), "hock": 0.2,
            "neck": (12, 10, 138), "head": (17, 11, 82), "tail": (22, 4, -128), "ear": (5.5, 9, -55),
            "colors": {"coat": "#c58f52", "mane": "#8a5a2b", "hoof": "#5a4632", "eye": "#1d1d1d"}},
    "cat": {"body": (40, 14), "shoulder": 28, "upper": 0.5, "leg": 5, "foot": (6, 3.5), "hock": 0.22,
            "neck": (7, 9, 150), "head": (13, 12, 86), "tail": (34, 3.5, -150), "ear": (5, 6, 100),
            "colors": {"coat": "#7d7f86", "mane": "#55575e", "hoof": "#55575e", "eye": "#2d3a1f"}},
}

# Per gait: the share of the cycle each foot is on the ground, when each foot lands (in cycles), the swing
# of the stride in degrees, how high a swinging foot lifts (share of the leg), the body's rise and fall
# (share of the height, beats per cycle, the phase of its highest point) and its tilt in degrees.
GAITS = {
    "walk": {"duty": 0.62, "land": {"hind-left": 0.0, "front-left": 0.25, "hind-right": 0.5, "front-right": 0.75},
             "amount": 14, "lift": 0.1, "bob": (0.0, 2, 0.25), "tilt": (1.0, 0.0), "nod": 3, "period": 1000},
    "trot": {"duty": 0.42, "land": {"hind-left": 0.0, "front-right": 0.0, "hind-right": 0.5, "front-left": 0.5},
             "amount": 20, "lift": 0.18, "bob": (0.02, 2, 0.35), "tilt": (1.5, 0.0), "nod": 2, "period": 640},
    "gallop": {"duty": 0.28, "land": {"hind-left": 0.0, "hind-right": 0.1, "front-left": 0.42, "front-right": 0.52},
               "amount": 28, "lift": 0.26, "bob": (0.06, 1, 0.9), "tilt": (6.0, 0.2), "nod": 5, "period": 480},
    "idle": {"duty": 1.0, "land": {leg: 0.0 for leg in LEGS}, "amount": 0, "lift": 0, "bob": (0.006, 1, 0.375),
             "tilt": (0.0, 0.0), "nod": 2, "period": 2400},
}
# Where in the stride a leg's joints are keyed: five points from landing to lift-off (the foot stays on the
# ground between them), then three points of the swing.
STANCE_POINTS = (0, 0.25, 0.5, 0.75, 1)
FLIGHT = 0.15  # the weight of the gait's own rise against the legs that carry the body
SWING_POINTS = (0.25, 0.5, 0.75)
BODY_POINTS = 12

# The jump as poses across its window: crouch, push off, tuck, reach, land. Angles are degrees from the
# rest pose for an animal facing right.
JUMP_AT = (0.18, 0.34, 0.52, 0.72, 0.88)
JUMP = {
    "body": (-4, 16, 5, -13, -6), "neck": (-8, 10, 4, -8, -14), "head": (5, -6, -2, 6, 8), "tail": (10, -22, 14, 22, 28),
    "front-upper-leg": (4, 36, 42, 34, -6), "front-lower-leg": (-10, -72, -100, -18, -8), "front-foot": (4, 30, 44, 4, 4),
    "hind-upper-leg": (24, -42, -20, 30, 12), "hind-lower-leg": (36, 6, 72, 34, 22), "hind-foot": (-16, -24, -34, -14, -10),
}
JUMP_LAG = 0.03  # the far legs follow the near ones by this share of the window


def _darker(project, color, share=0.24):
    from ...design import resolve_color
    from ...render import color as parse

    r, g, b = parse(resolve_color(color, project.state))[:3]
    return "#{:02x}{:02x}{:02x}".format(*(round(v * (1 - share)) for v in (r, g, b)))


def _towards(point, direction, distance):
    rad = math.radians(direction)
    return point[0] + math.sin(rad) * distance, point[1] + math.cos(rad) * distance


def _across(point, direction, distance):
    """``distance`` to the back (upper) side of a part pointing in ``direction``."""
    rad = math.radians(direction)
    return point[0] + math.cos(rad) * distance, point[1] - math.sin(rad) * distance


def layout(species):
    """The standard animal's parts in its own units, facing right with the ground at y=0 (up is negative):
    ``[{part, shape, role, joint, size, pivot, direction, radius}]`` in stacking order. ``direction`` is
    where the part's lower edge points from its joint, in degrees from straight down towards +x."""
    spec = SPECIES[species]
    length, depth = spec["body"]
    foot_w, foot_h = spec["foot"]
    shoulder = (0.34 * length, -spec["shoulder"])
    hip = (-0.34 * length, -spec["shoulder"] - 0.05 * depth)
    centre = (0, -spec["shoulder"] - 0.12 * depth)
    parts = []

    def limb(name, role, start, end, width):
        dx, dy = end[0] - start[0], end[1] - start[1]
        height = math.hypot(dx, dy) + 0.5 * width
        parts.append({"part": name, "shape": "rectangle", "role": role, "joint": start, "size": (width, height),
                      "pivot": (0.5, 0.25 * width / height), "direction": math.degrees(math.atan2(dx, dy)), "radius": width / 2})

    def leg(name, role, top, shift):
        front = name.startswith("front")
        top = (top[0] + shift, top[1])
        reach = -foot_h - top[1]
        if front:
            knee, ankle = (top[0], top[1] + reach * spec["upper"]), (top[0], -foot_h)
        else:
            knee, ankle = (top[0] - spec["hock"] * reach, top[1] + 0.55 * reach), (top[0] - 0.03 * reach, -foot_h)
        limb(f"{name}-upper-leg", role, top, knee, spec["leg"] * (1.25 if front else 1.4))
        limb(f"{name}-lower-leg", role, knee, ankle, spec["leg"] * 0.8)
        parts.append({"part": f"{name}-foot", "shape": "rectangle", "role": "hoof", "joint": ankle,
                      "size": (foot_w, foot_h / 0.9), "pivot": (0.42, 0.1), "direction": 0, "radius": foot_h * 0.3})

    leg("hind-left", "far", hip, 0.07 * length)
    leg("front-left", "far", shoulder, 0.07 * length)
    tail_len, tail_w, tail_dir = spec["tail"]
    parts.append({"part": "tail", "shape": "rectangle", "role": "mane", "joint": (-0.46 * length, centre[1] - 0.2 * depth),
                  "size": (tail_w, tail_len), "pivot": (0.5, 0.05), "direction": tail_dir, "radius": tail_w / 2})
    neck_len, neck_w, neck_dir = spec["neck"]
    base = (0.38 * length, centre[1] - 0.18 * depth)
    if spec.get("mane"):
        parts.append({"part": "mane", "shape": "rectangle", "role": "mane", "joint": _across(base, neck_dir, 0.4 * neck_w),
                      "size": (0.5 * neck_w, 1.05 * neck_len), "pivot": (0.5, 0.05), "direction": neck_dir, "radius": 0.25 * neck_w})
    limb("neck", "coat", base, _towards(base, neck_dir, neck_len), neck_w)
    parts.append({"part": "body", "shape": "ellipse", "role": "coat", "joint": centre, "size": (length, depth),
                  "pivot": (0.5, 0.5), "direction": 0})
    head_len, head_w, head_dir = spec["head"]
    crown = _towards(base, neck_dir, neck_len)
    ear_w, ear_h, ear_turn = spec["ear"]
    # Triangles point up in their own box, so they turn about their lower edge: the tip points away from it.
    parts.append({"part": "ear", "shape": "triangle", "role": "coat", "joint": _across(_towards(crown, head_dir, 0.04 * head_len), head_dir, 0.36 * head_w),
                  "size": (ear_w, ear_h), "pivot": (0.5, 0.92), "direction": head_dir + ear_turn - 180})
    parts.append({"part": "head", "shape": "ellipse", "role": "coat", "joint": crown, "size": (head_w, head_len),
                  "pivot": (0.5, 0.22), "direction": head_dir})
    eye = 0.2 * head_w
    parts.append({"part": "eye", "shape": "ellipse", "role": "eye", "joint": _across(_towards(crown, head_dir, 0.2 * head_len), head_dir, 0.14 * head_w),
                  "size": (eye, eye), "pivot": (0.5, 0.5), "direction": 0})
    if spec.get("horn"):
        parts.append({"part": "horn", "shape": "triangle", "role": "horn", "joint": _across(_towards(crown, head_dir, 0.22 * head_len), head_dir, 0.4 * head_w),
                      "size": (0.3 * head_w, 0.85 * head_len), "pivot": (0.5, 0.95), "direction": head_dir + 92 - 180})
    leg("hind-right", "coat", hip, 0)
    leg("front-right", "coat", shoulder, 0)
    return parts


def _corners(part):
    (jx, jy), (w, h), (px, py) = part["joint"], part["size"], part["pivot"]
    rad = math.radians(part["direction"])
    co, si = math.cos(rad), math.sin(rad)
    for cx, cy in ((0, 0), (w, 0), (w, h), (0, h)):
        dx, dy = cx - px * w, cy - py * h
        yield jx + dx * co + dy * si, jy - dx * si + dy * co


def standard(project, op):
    """Draw the standard animal of a species and rig it."""
    from ...operations import execute as apply

    species = op.get("species", "horse")
    require(species in SPECIES, f"species must be {', '.join(SPECIES)}", field="species")
    facing = op.get("facing", "right")
    require(facing in FACINGS, "facing must be right or left", field="facing")
    name = op["name"]
    height = finite(op.get("height", 320), "height", 40, 8192)
    colors = {**SPECIES[species]["colors"], **op.get("colors", {})}
    colors.setdefault("far", _darker(project, colors["coat"]))
    colors.setdefault("horn", "#f2c14e")
    parts = layout(species)
    points = [point for part in parts for point in _corners(part)]
    left, top = min(x for x, _ in points), min(y for _, y in points)
    right = max(x for x, _ in points)
    factor = height / (max(y for _, y in points) - top)
    mirror = facing == "left"
    made = {}
    for part in parts:
        (jx, jy), (w, h), (px, py) = part["joint"], part["size"], part["pivot"]
        direction = part["direction"]
        jx = (right - jx if mirror else jx - left) * factor
        jy = (jy - top) * factor
        if mirror:
            px, direction = 1 - px, -direction
        w, h = max(1, w * factor), max(1, h * factor)
        apply(project, {"type": "shape", "shape": part["shape"], "name": f"{name}/{part['part']}", "x": jx - px * w, "y": jy - py * h,
                        "width": w, "height": h, "fill": colors[part["role"]], "stroke_width": 0,
                        **({"radius": part["radius"] * factor} if part.get("radius") else {})})
        layer = project.layer()
        layer.update(character_part=part["part"], character_color=part["role"], pivot=[px, py], rotation=-direction % 360)
        made[part["part"]] = layer["id"]
    apply(project, {"type": "group", "name": name, "targets": list(made.values())})
    group = project.layer()
    group.update(x=op.get("x", 0), y=op.get("y", 0))
    group["character"] = {"version": 1, "plan": "quadruped", "species": species, "facing": facing, "parts": made, "bones": {}}
    auto_rig(project, group)
    project.state["active_layer"] = group["id"]
    return group


def bind(project, op):
    """Bind supplied artwork (``parts``: standard part name -> layer) as a quadruped and rig it from the
    layers as drawn: each part turns about its pivot (set one with the pivot operation; legs, tail and
    mane default to the middle of their top edge, neck, ears and horn to the middle of their bottom
    edge, body, head and eye to their centre)."""
    from ...operations import execute as apply

    unknown = sorted(set(op["parts"]) - set(PARTS))
    require(not unknown, f"Unknown quadruped part(s) {', '.join(unknown)}; parts: {', '.join(PARTS)}", field="parts",
            allowed=list(PARTS))
    parts = {part: project.layer(ref)["id"] for part, ref in op["parts"].items()}
    missing = [part for part in REQUIRED if part not in parts]
    require(not missing, f"A quadruped needs {', '.join(missing)} (required: {', '.join(REQUIRED)})", field="parts", missing=missing)
    require(len(set(parts.values())) == len(parts), "Each character part needs its own layer", field="parts")
    facing = op.get("facing", "right")
    require(facing in FACINGS, "facing must be right or left", field="facing")
    for part, ident in parts.items():
        layer = project.layer(ident)
        if layer.get("pivot") is None:
            apply(project, {"type": "pivot", "target": ident, "value": list(PIVOTS.get(part, (0.5, 0)))})
        layer["character_part"] = part
    apply(project, {"type": "group", "name": op["name"], "targets": list(parts.values())})
    group = project.layer()
    for axis in ("x", "y"):
        if axis in op:
            group[axis] = op[axis]
    group["character"] = {"version": 1, "plan": "quadruped", "facing": facing, "parts": parts, "bones": {}}
    if "species" in op:
        require(op["species"] in SPECIES, f"species must be {', '.join(SPECIES)}", field="species")
        group["character"]["species"] = op["species"]
    auto_rig(project, group)
    project.state["active_layer"] = group["id"]
    return group


def _parent(part, parts):
    if part == "body":
        return None
    for leg in LEGS:
        if part.startswith(leg):
            return {"upper-leg": "body", "lower-leg": f"{leg}-upper-leg", "foot": f"{leg}-lower-leg"}[part[len(leg) + 1:]]
    return next(name for name in PARENTS[part] if name in parts)


def auto_rig(project, group):
    """Bones for every part from the layers as they stand: the joint is the part's pivot point, ``at`` its
    offset from the parent's joint and ``rest`` the rotation it was drawn with."""
    from ...render import rest_size
    from .characters import pose

    parts = group["character"]["parts"]
    joints, layers = {}, {}
    for part, ident in parts.items():
        layer = project.layer(ident)
        w, h = rest_size(layer)
        px, py = layer.get("pivot") or (0.5, 0.5)
        joints[part], layers[part] = (layer["x"] + px * w, layer["y"] + py * h), layer
    bones = {}
    for part in sorted(parts, key=lambda name: (name != "body", _depth(name, parts))):
        layer, parent = layers[part], _parent(part, parts)
        kind = next((key for key in LIMITS if part == key or part.endswith(key)), None)
        children = [joints[other] for other in parts if other != part and _parent(other, parts) == part]
        w, h = rest_size(layer)
        length = max([math.dist(joints[part], child) for child in children] or [h * (1 - (layer.get("pivot") or (0.5, 0))[1])])
        bone = {"layer": layer["id"], "length": max(0.01, length), "angle": 0, "rest": layer.get("rotation", 0),
                "limits": list(LIMITS.get(kind, [-60, 60]))}
        if parent:
            bone.update(parent=parent, at=[joints[part][0] - joints[parent][0], joints[part][1] - joints[parent][1]])
        else:
            bone["origin"] = list(joints[part])
        bones[part] = bone
    group["character"]["bones"] = bones
    pose(project, group, {})


def _depth(part, parts):
    depth = 0
    while part != "body":
        part, depth = _parent(part, parts), depth + 1
    return depth


def _turned(vector, angle):
    """``vector`` carried by a joint turned ``angle`` degrees (positive swings straight-down towards +x)."""
    rad = math.radians(angle)
    co, si = math.cos(rad), math.sin(rad)
    return vector[0] * co + vector[1] * si, -vector[0] * si + vector[1] * co


def _direction(vector):
    return math.degrees(math.atan2(vector[0], vector[1]))


def _wrap(angle):
    return (angle + 180) % 360 - 180


class Rig:
    """The rest geometry a cycle needs: where the body's joint sits, and for each leg the shoulder's
    offset on the body, the two segment lengths, their rest directions and which way the knee folds."""

    def __init__(self, project, group):
        from ...render import rest_size

        character = group["character"]
        self.bones = bones = character["bones"]
        self.sign = -1 if character.get("facing") == "left" else 1
        self.height = max(1.0, group.get("content_height", group["height"]))
        rest = {}

        def joint(name):
            if name not in rest:
                bone = bones[name]
                if bone.get("parent"):
                    origin = joint(bone["parent"])
                    at = bone.get("at") or (0, bones[bone["parent"]]["length"])
                    rest[name] = (origin[0] + at[0], origin[1] + at[1])
                else:
                    rest[name] = tuple(bone.get("origin", (0, 0)))
            return rest[name]

        self.body = joint("body")
        self.legs = {}
        for leg in LEGS:
            upper, lower, foot = (f"{leg}-{segment}" for segment in SEGMENTS)
            shoulder, knee = joint(upper), joint(lower)
            if foot in bones:
                tip = joint(foot)
            else:
                layer = project.layer(bones[lower]["layer"])
                reach = rest_size(layer)[1] * (1 - (layer.get("pivot") or (0.5, 0))[1])
                tip = _towards(knee, -bones[lower].get("rest", 0), reach)
            first, second = (knee[0] - shoulder[0], knee[1] - shoulder[1]), (tip[0] - knee[0], tip[1] - knee[1])
            fold = _wrap(_direction(second) - _direction(first))
            default = self.sign * (-1 if leg.startswith("front") else 1)
            self.legs[leg] = {"at": (shoulder[0] - self.body[0], shoulder[1] - self.body[1]), "tip": tip,
                              "a": max(0.01, math.hypot(*first)), "b": max(0.01, math.hypot(*second)),
                              "first": _direction(first), "second": _direction(second),
                              "bend": (1 if fold > 0 else -1) if abs(fold) > 3 else default, "foot": foot in bones}

    def solve_leg(self, leg, tilt, target):
        """Joint angles (degrees from rest) that put the leg's ankle on ``target`` with the body tilted
        ``tilt`` degrees: ``(upper, lower, turn)`` where ``turn`` is how far the lower leg has turned in all."""
        data = self.legs[leg]
        offset = _turned(data["at"], tilt)
        dx, dy = target[0] - self.body[0] - offset[0], target[1] - self.body[1] - offset[1]
        a, b = data["a"], data["b"]
        distance = max(abs(a - b) + 1e-6, min(0.999 * (a + b), math.hypot(dx, dy)))
        knee = data["bend"] * math.acos(max(-1, min(1, (distance * distance - a * a - b * b) / (2 * a * b))))
        upper = math.atan2(dx, dy) - math.atan2(b * math.sin(knee), a + b * math.cos(knee))
        upper, knee = math.degrees(upper), math.degrees(knee)
        return _wrap(upper - data["first"] - tilt), _wrap(knee - (data["second"] - data["first"])), _wrap(upper + knee - data["second"])

    def need(self, leg, along):
        """How far the body must come down for the leg to keep its foot on the ground ``along`` px ahead
        of where it stands at rest, the leg as long as it is in the rest pose."""
        data = self.legs[leg]
        dx = data["tip"][0] - self.body[0] - data["at"][0]
        dy = data["tip"][1] - self.body[1] - data["at"][1]
        reach = math.hypot(dx, dy)
        across = min(abs(dx + self.sign * along), 0.95 * reach)
        return dy - math.sqrt(reach * reach - across * across)

    def stride(self, amount):
        front = self.legs["front-right"]
        return min(0.8, math.sin(math.radians(amount))) * (front["a"] + front["b"])


def _stride(gait, leg, u, stride, reach):
    """Where a leg's foot is at phase ``u``: ``(along, lift, level, load)``: px ahead of its rest place,
    px off the ground, how flat the foot is held (1 on the ground) and the share of weight it carries."""
    duty = gait["duty"]
    local = (u - gait["land"][leg]) % 1
    if local < duty:
        return stride * (1 - 2 * local / duty), 0.0, 1.0, math.sin(math.pi * local / duty)
    swing = (local - duty) / (1 - duty)
    return (stride * (-1 + (1 - math.cos(math.pi * swing))), gait["lift"] * reach * math.sin(math.pi * swing),
            1 - 0.5 * math.sin(math.pi * swing), 0.0)


def _body(rig, name, u, amount):
    """The body's drop (px, positive down) and tilt (degrees) at phase ``u``. The body rides on the legs
    that carry it: it comes down as they spread and rises over a leg that stands under it, and with no
    foot on the ground (a gallop's suspension) it rises by the gait's bob."""
    gait = GAITS[name]
    amplitude, beats, peak = gait["bob"]
    if gait["duty"] >= 1:
        drop = amplitude * rig.height * (1 - math.cos(math.tau * beats * (u - peak))) / 2
    else:
        stride = rig.stride(amount)
        total, weight = -FLIGHT * amplitude * rig.height, FLIGHT
        for leg in rig.legs:
            along, _, _, load = _stride(gait, leg, u, stride, 0)
            total, weight = total + load * rig.need(leg, along), weight + load
        drop = total / weight
    size, crest = gait["tilt"]
    # The body rocks with the stride: a longer stride (amount) rocks it further.
    tilt = rig.sign * size * amount / gait["amount"] * math.cos(math.tau * (u - crest)) if gait["amount"] else 0.0
    return drop, tilt


def gait_pose(rig, name, u, amount):
    """Every joint's angle and the body's drop (px, positive down) at phase ``u`` (cycles) of a gait. The
    body's drop and tilt are keyed BODY_POINTS times a stride and run straight between those keys; the
    legs are solved against that, so a foot on the ground stays there between the body's keys too."""
    gait = GAITS[name]
    sign = rig.sign
    step = math.floor(u * BODY_POINTS)
    share = u * BODY_POINTS - step
    before, after = _body(rig, name, step / BODY_POINTS, amount), _body(rig, name, (step + 1) / BODY_POINTS, amount)
    drop, tilt = (a + (b - a) * share for a, b in zip(before, after))
    _, beats, peak = gait["bob"]
    nod = gait["nod"] * math.sin(math.tau * beats * (u - peak))
    angles = {"body": tilt, "neck": -0.6 * tilt + sign * nod, "head": -0.5 * sign * nod,
              "tail": sign * (6 + 2 * gait["nod"]) * math.sin(math.tau * (u - 0.15)) + 0.4 * tilt}
    stride = rig.stride(amount)
    for leg, data in rig.legs.items():
        along, lift, level, _ = _stride(gait, leg, u, stride, data["a"] + data["b"])
        target = (data["tip"][0] + sign * along, data["tip"][1] - drop - lift)
        upper, lower, turn = rig.solve_leg(leg, tilt, target)
        angles[f"{leg}-upper-leg"], angles[f"{leg}-lower-leg"] = upper, lower
        angles[f"{leg}-foot"] = _wrap(-level * turn)
    return {bone: value for bone, value in angles.items() if bone in rig.bones}, drop


def _phases(bone, gait):
    """The phases of a stride at which a bone is keyed. Every bone is also keyed where the stride starts,
    so the key a loop needs at its seam is one every stride has."""
    for leg in LEGS:
        if bone.startswith(leg) and gait["duty"] < 1:
            duty = gait["duty"]
            points = [*(duty * point for point in STANCE_POINTS), *(duty + (1 - duty) * point for point in SWING_POINTS)]
            return sorted({0.0, *((gait["land"][leg] + point) % 1 for point in points)})
    return [k / BODY_POINTS for k in range(BODY_POINTS)]


def _clear(track, start, end):
    if track:
        track["keys"] = [key for key in track["keys"] if not start <= key["time"] <= end]


def cycle(project, group, op):
    """character-cycle for a quadruped: walk, trot, gallop and idle as joint keys, jump as a blend."""
    from ...timeline import _note, _timeline, _track, execute_timeline, parse_time

    name = op["cycle"]
    bones = group["character"]["bones"]
    missing = [bone for bone in ("body", *UPPER, *(f"{leg}-lower-leg" for leg in LEGS)) if bone not in bones]
    if name not in CYCLES or missing:
        raise VixlError("invalid_operation", f"cycle: {group['name']!r} is a quadruped; its cycles are {', '.join(CYCLES)}"
                        + (f", and its rig has no {', '.join(missing)}" if missing else ""), field="cycle",
                        character=group["name"], suggestions=list(CYCLES), missing=missing)
    timeline = _timeline(project)
    start = parse_time(op.get("start", 0), timeline["duration"], timeline.get("markers"))
    if name == "jump":
        return jump(project, group, op, start)
    gait = GAITS[name]
    rest = max(10, timeline["duration"] - start)
    duration = parse_time(op.get("duration", rest), timeline["duration"], timeline.get("markers"))
    require(duration >= 10, "Cycle duration must be at least 10 ms", field="duration")
    period = finite(op.get("period", gait["period"]), "cycle period", 50, 600000)
    amount = finite(op.get("amount", gait["amount"]), "cycle amplitude", 0, 60)
    if timeline.get("loop_mode") == "seamless" and start + duration == timeline["duration"]:
        # A gait that runs to the loop end closes only after whole strides.
        whole = max(1, round(duration / period))
        if abs(duration / whole - period) > 1e-9:
            _note(project, f"{name} period {period:g} -> {duration / whole:g} ms, so {whole} whole stride(s) close the "
                  f"{duration} ms loop")
            period = duration / whole
    rig = Rig(project, group)
    end = start + duration
    strides = math.ceil(duration / period) + 1
    require(strides * (len(bones) + 1) * BODY_POINTS <= 8192, "Cycle exceeds the key budget; use a longer period or a "
            "shorter duration", "resource_limit", field="duration")
    solved = {}

    def at(time):
        if time not in solved:
            solved[time] = gait_pose(rig, name, (time - start) / period, amount)
        return solved[time]

    def times(phases):
        found = {start, end}
        for n in range(-1, strides):
            for phase in phases:
                time = round(start + (n + phase) * period)
                if start < time < end:
                    found.add(time)
        return sorted(found)

    extend = op.get("extend", True)
    driven = [bone for bone in gait_pose(rig, name, 0, amount)[0]]
    for bone in driven:
        prop = "joint:" + bone
        _clear(_track(timeline, group["id"], prop, create=False), start, end)
        for time in times(_phases(bone, gait)):
            execute_timeline(project, {"type": "keyframe", "target": group["id"], "property": prop, "time": time,
                                       "value": round(at(time)[0][bone], 3), "extend": extend})
    _clear(_track(timeline, group["id"], "translate-y", create=False), start, end)
    for time in times([k / BODY_POINTS for k in range(BODY_POINTS)]):
        execute_timeline(project, {"type": "keyframe", "target": group["id"], "property": "translate-y", "time": time,
                                   "value": round(at(time)[1], 3), "extend": extend})


def jump(project, group, op, start):
    """One jump over ``duration``: crouch, push off, tuck, reach and land. Each joint eases from what it
    was doing at the start of the window through the jump's poses and back to what it would be doing at
    the end, and the height of the leap is an additive layer (``jump``) on the group's translate-y, summed
    with the rise and fall of the gait underneath."""
    from ...motion import blend_track
    from ...timeline import _timeline, _track, execute_timeline, parse_time

    timeline = _timeline(project)
    duration = parse_time(op.get("duration", 1000), timeline["duration"], timeline.get("markers"))
    require(duration >= 100, "A jump needs at least 100 ms", field="duration")
    character = group["character"]
    bones = character["bones"]
    sign = -1 if character.get("facing") == "left" else 1
    height = max(1.0, group.get("content_height", group["height"]))
    leap = finite(op.get("amount", 0.45 * height), "jump height", 0, 1e5)
    extend = op.get("extend", True)
    for bone in bones:
        row = JUMP.get(bone)
        lag = 0.0
        for leg in LEGS:
            if bone.startswith(leg):
                row = JUMP.get(("front" if leg.startswith("front") else "hind") + bone[len(leg):])
                lag = JUMP_LAG if leg.endswith("left") else 0.0
        if row is None:
            continue
        lo, hi = bones[bone].get("limits", [-180, 180])
        poses = [{"at": at + lag, "value": min(hi, max(lo, sign * value))} for at, value in zip(JUMP_AT, row)]
        blend_track(project, group["id"], "joint:" + bone, {"start": start, "duration": duration, "poses": poses}, extend)
    track = _track(timeline, group["id"], "translate-y", create=False)
    for extra in (track or {}).get("add", []):
        if extra["layer"] == "jump":
            extra["keys"] = [key for key in extra["keys"] if not start <= key["time"] <= start + duration] or \
                [{"time": start, "value": 0}]
    dip = 0.04 * height
    for at, value, easing in ((0, 0, "ease-in-out"), (JUMP_AT[0], dip, "ease-in"), (JUMP_AT[1], -0.12 * leap, "ease-out"),
                              (JUMP_AT[2], -leap, "ease-in"), (JUMP_AT[4], 0.6 * dip, "ease-out"), (1, 0, None)):
        execute_timeline(project, {"type": "keyframe", "target": group["id"], "property": "translate-y", "mode": "add",
                                   "additive": "jump", "time": start + round(at * duration), "value": round(value, 3),
                                   "extend": extend, **({"easing": easing} if easing else {})})


def foot_contacts(project, group, start=0, end=None, step=10):
    """When each foot is on the ground between ``start`` and ``end``: ``{leg: [(from_ms, to_ms), ...]}``,
    read from the rendered pose (the lowest point of the foot, or of the lower leg without one)."""
    from ...spatial import canvas_boxes
    from ...timeline import default_timeline, project_at

    timeline = project.state.get("timeline") or default_timeline()
    end = timeline["duration"] if end is None else end
    parts = group["character"]["parts"]
    tips = {leg: parts.get(f"{leg}-foot", parts[f"{leg}-lower-leg"]) for leg in LEGS}
    samples = []
    for time in range(start, end + 1, step):
        boxes = canvas_boxes(project_at(project, time))
        samples.append((time, {leg: boxes[ident][1] + boxes[ident][3] for leg, ident in tips.items()}))
    ground = max(bottom for _, bottoms in samples for bottom in bottoms.values())
    slack = max(2.0, 0.02 * max(1.0, group.get("content_height", group["height"])))
    contacts = {leg: [] for leg in LEGS}
    for leg in LEGS:
        began = None
        for time, bottoms in samples:
            down = bottoms[leg] >= ground - slack
            if down and began is None:
                began = time
            if not down and began is not None:
                contacts[leg].append((began, time - step))
                began = None
        if began is not None:
            contacts[leg].append((began, samples[-1][0]))
    return contacts


def expected_joints(group):
    """Where the rig puts each bone's joint and how far it turns its layer, from the bones' current angles."""
    bones = group["character"]["bones"]
    solved = {}

    def visit(name):
        if name not in solved:
            bone = bones[name]
            angle = bone.get("angle", 0)
            if bone.get("parent") in bones:
                origin, turned = visit(bone["parent"])
                offset = _turned(bone["at"], turned) if "at" in bone else _turned((0, bones[bone["parent"]]["length"]), turned)
                solved[name] = ((origin[0] + offset[0], origin[1] + offset[1]), turned + angle)
            else:
                solved[name] = (tuple(bone.get("origin", (0, 0))), angle)
        return solved[name]

    for name in bones:
        visit(name)
    return solved


def findings(project, group):
    """A quadruped's parts stay on their joints: a part moved or animated on its own (its x, y or rotation
    instead of the character's joints) leaves the body it should hang from."""
    from ...render import rest_size
    from ...timeline import default_timeline, project_at

    character = group["character"]
    ids = {layer["id"] for layer in project.state["layers"]}
    parts = character.get("parts", {})
    missing = [part for part in REQUIRED if part not in parts or parts[part] not in ids]
    if missing:
        return [{"check": "character", "severity": "error", "layer": group["id"],
                 "message": "Missing character parts: " + ", ".join(missing)}]
    bones = character.get("bones", {})
    owned = {bone["layer"]: name for name, bone in bones.items()}
    timeline = project.state.get("timeline") or default_timeline()
    moved = {track["target"] for track in timeline.get("tracks", [])
             if track["target"] in owned and track["property"] in ("x", "y", "translate-x", "translate-y", "rotation") and track["keys"]}
    times = [None] + ([round(timeline["duration"] * n / 6) for n in range(7)] if moved else [])
    worst = {}
    for time in times:
        frame = project if time is None else project_at(project, time)
        rig = frame.layer(group["id"])
        for name, (origin, turned) in expected_joints(rig).items():
            bone = rig["character"]["bones"][name]
            if bone["layer"] not in ids:
                continue
            layer = frame.layer(bone["layer"])
            w, h = rest_size(layer)
            px, py = layer.get("pivot") or (0.5, 0)
            off = math.dist(origin, (layer["x"] + px * w, layer["y"] + py * h))
            turn = abs(_wrap(layer.get("rotation", 0) - (bone.get("rest", 0) - turned)))
            if off > 1.5 or turn > 1:
                worst[name] = max(worst.get(name, (0, 0, 0)), (off, turn, time or 0))
    result = []
    for name, (off, turn, time) in worst.items():
        result.append({"check": "character", "severity": "warning", "layer": group["id"], "code": "joint-detached",
                       "message": f"{group['name']!r}: {name} is {off:.0f} px off its joint"
                                  + (f" and turned {turn:.0f} degrees from its pose" if turn > 1 else "")
                                  + (f" at {time / 1000:g}s" if time else "")
                                  + ", so the animal comes apart there. Move and animate the character's joints "
                                    "(character-pose, character-cycle, joint:BONE keys) instead of the part's own x, y "
                                    "or rotation; character-pose with no angles puts every part back on its joint."})
    return result
