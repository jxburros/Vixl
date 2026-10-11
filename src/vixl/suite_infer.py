"""Propose a tolerant starter suite from an approved document (workflow ``suite-infer``).

Every proposed rule comes from a measurement of the approved design with headroom, carries an explanation, and is
written relative to the canvas or to other layers where it can be, so the suite carries over to sibling sizes.
The result is returned for review; it is only saved when asked (``apply``) and never attached to the document.
"""

import math
import re

from .errors import require

MAX_TEXT_RULES = 12
MAX_PALETTE = 16


def _slug(name):
    return re.sub(r"[^\w-]+", "-", name).strip("-").lower() or "layer"


def _floor(value, step):
    return math.floor(value / step + 1e-9) * step


def _texts(project):
    """Visible content text layers that draw something, largest rendered size first: [(layer, size, text)]."""
    from .assurance import _rendered_size
    from .copy_checks import drawn_text, shown_layers
    from .render import resolved_layers

    shown = [layer for layer in shown_layers(project, "*", "text") if layer.get("role") != "background"]
    resolved = {item["id"]: item for item in resolved_layers(project)}
    texts = drawn_text(project, shown)
    found = []
    for layer in shown:
        text = texts.get(layer["id"], "")
        if text.strip():
            found.append((layer, _rendered_size(project, resolved[layer["id"]]), text))
    return sorted(found, key=lambda entry: -entry[1])


def _logo(project):
    from .copy_checks import shown_layers

    for layer in shown_layers(project):
        if "logo" in layer["name"].lower() and layer["type"] != "text":
            return layer
    return None


def infer(project, name="inferred"):
    """{suite, explanations} proposed from ``project`` as approved: hierarchy, contrast for each text role, placement
    and order relations, palette, required layers and copy-length limits."""
    from .assurance import _contrast, digest, rule_result, validate_suite
    from .copy_checks import count_characters
    from .spatial import canvas_boxes, relation

    canvas = project.state["canvas"]
    width, height = canvas["width"], canvas["height"]
    short = min(width, height)
    tolerance = max(1, round(0.02 * short))
    boxes = canvas_boxes(project)
    texts = _texts(project)
    rules, notes = [], {}

    def add(rule, why):
        rules.append(rule)
        notes[rule["id"]] = why

    # Hierarchy: one text layer per distinct size step, most to least important.
    chain = []
    for layer, size, _ in texts:
        if not chain or size <= chain[-1][1] / 1.1:
            chain.append((layer, size))
        if len(chain) == 4:
            break
    if len(chain) >= 2:
        steps = [a[1] / b[1] for a, b in zip(chain, chain[1:])]
        ratio = max(1.0, _floor(min(steps) * 0.9, 0.05))
        add({"id": "hierarchy", "kind": "hierarchy", "targets": [layer["name"] for layer, _ in chain],
             "ratio": round(ratio, 2)},
            f"Rendered sizes {', '.join(f'{size:.0f}' for _, size in chain)} px step down by at least "
            f"{min(steps):.2f}x; the rule asks for {ratio:.2f}x (10% headroom).")
        for (a, _), (b, _) in zip(chain, chain[1:]):
            found = relation(boxes[a["id"]], boxes[b["id"]], tolerance)
            position = next((p for p in ("above", "below", "left-of", "right-of") if p in found["positions"]), None)
            if position:
                align = [edge for edge in ("left", "center-x", "right") if edge in found["alignments"]][:1]
                add({"id": f"order-{_slug(a['name'])}-{_slug(b['name'])}", "kind": "relation", "target": a["name"],
                     "to": b["name"], "position": position, **({"align": align} if align else {}),
                     "tolerance": tolerance},
                    f"{a['name']!r} sits {position} {b['name']!r}" + (f" with {align[0]} edges aligned" if align else "")
                    + f" (tolerance {tolerance} px, 2% of the shorter side).")

    # Placement of the headline and the logo against the canvas.
    key_layers = ([texts[0][0]] if texts else []) + ([_logo(project)] if _logo(project) else [])
    for layer in key_layers:
        box = boxes[layer["id"]]
        found = relation(box, (0, 0, width, height), tolerance)
        align = [edge for edge in ("center-x", "center-y") if edge in found["alignments"]]
        if "inside" in found["positions"]:
            add({"id": f"place-{_slug(layer['name'])}", "kind": "relation", "target": layer["name"], "to": "canvas",
                 "position": "inside", **({"align": align} if align else {}), "tolerance": tolerance},
                f"{layer['name']!r} lies inside the canvas" + (f", centred ({', '.join(align)})" if align else "")
                + "; relative to the canvas, so it holds at other sizes.")
        add({"id": f"has-{_slug(layer['name'])}", "kind": "count", "target": layer["name"], "minimum": 1},
            f"{layer['name']!r} is a required element: it must exist and be visible.")

    # Contrast for each text role, at the WCAG level (3:1 for large text) unless the approved design is lower.
    for layer, size, _ in texts[:MAX_TEXT_RULES]:
        try:
            passed, detail = _contrast(project, {"target": layer["id"], "minimum": 1})
        except Exception:
            continue
        actual = max(detail["actual"], detail.get("outline", 0))
        wcag = 3.0 if size >= 24 else 4.5
        minimum = min(wcag, _floor(actual, 0.1))
        rule = {"id": f"contrast-{_slug(layer['name'])}", "kind": "contrast", "target": layer["name"],
                "minimum": round(minimum, 1)}
        why = f"Measured {actual:.2f}:1; the rule asks for {minimum:.1f}:1"
        if minimum < wcag:
            rule["severity"] = "warning"
            why += f" (below the WCAG {wcag:g}:1 for this size, so it only needs review)"
        add(rule, why + ".")

    # Copy length: the approved copy plus headroom; never empty.
    for layer, _, text in texts[:MAX_TEXT_RULES]:
        characters = count_characters(text)
        limit = max(characters + 5, math.ceil(characters * 1.25))
        add({"id": f"copy-{_slug(layer['name'])}", "kind": "text", "target": layer["name"], "min_characters": 1,
             "max_characters": limit},
            f"{layer['name']!r} has {characters} characters; the rule allows up to {limit} (25% or 5 more).")

    if texts:
        add({"id": "text-count", "kind": "count", "target": "*", "layer_type": "text", "minimum": len(texts)},
            f"{len(texts)} text layers draw copy; at least that many must remain.")

    palette = _palette(project)
    if palette:
        from .palette_checks import measure

        try:
            report = measure(project, colors=palette, tolerance=24, max_fraction=1)
        except Exception:
            report = None
        if report and report["outside_fraction"] <= 0.25:
            fraction = min(1.0, round(report["outside_fraction"] * 1.5 + 0.02, 3))
            add({"id": "palette", "kind": "palette", "colors": palette, "tolerance": 24, "max_fraction": fraction},
                f"{len(palette)} colours are in use; {report['outside_fraction']:.1%} of drawn pixels fall outside "
                f"them (anti-aliasing, images), so up to {fraction:.1%} may.")

    suite = {"version": 1, "description": f"Inferred from an approved {width}x{height} design; review before use.",
             "rules": rules}
    # Keep only rules the approved design itself passes.
    kept, dropped = [], []
    for rule in rules:
        try:
            passed, _ = rule_result(project, rule)
        except Exception:
            passed = False
        (kept if passed else dropped).append(rule)
    suite["rules"] = kept
    require(kept, "Nothing measurable to infer: add text or named layers to the approved design")
    validate_suite(suite)
    return {"name": name, "suite": suite, "suite_hash": digest(suite),
            "explanations": [{"id": rule["id"], "kind": rule["kind"], "measured": notes[rule["id"]]} for rule in kept],
            **({"dropped": [rule["id"] for rule in dropped]} if dropped else {})}


def _palette(project):
    """Distinct solid colours the design paints with (canvas, fills, strokes, text), as #rrggbb."""
    from .copy_checks import shown_layers
    from .design import resolve_color
    from .render import color, resolved_layers

    colors = []

    def take(value):
        if not isinstance(value, str):
            return
        try:
            rgba = color(resolve_color(value, project.state))
        except Exception:
            return
        if rgba[3]:
            hexa = "#%02x%02x%02x" % tuple(rgba[:3])
            if hexa not in colors:
                colors.append(hexa)

    take(project.state["canvas"].get("background"))
    ids = {layer["id"] for layer in shown_layers(project)}
    for layer in resolved_layers(project):
        if layer["id"] not in ids:
            continue
        for key in ("color", "fill", "stroke", "stroke_color", "start", "end"):
            take(layer.get(key))
        for stop in layer.get("stops") or []:
            take(stop.get("color"))
    return colors[:MAX_PALETTE] if len(colors) >= 2 else None


LOOSER = {"maximum", "max_characters", "max_words", "max_fraction", "tolerance"}
TIGHTER_MIN = {"minimum", "ratio", "min_characters", "min_words"}


def combine(inferences, members, run):
    """One suite from several approved members: the rules every member proposed (by id and kind), with each limit
    set to the strictest value every member still meets, then only the rules every member passes."""
    first = inferences[0]
    common = [rule for rule in first["suite"]["rules"]
              if all(any(other["id"] == rule["id"] and other["kind"] == rule["kind"] for other in item["suite"]["rules"])
                     for item in inferences[1:])]
    merged = []
    for rule in common:
        rule = dict(rule)
        for item in inferences[1:]:
            other = next(r for r in item["suite"]["rules"] if r["id"] == rule["id"])
            for key, value in other.items():
                if key in LOOSER and isinstance(value, (int, float)):
                    rule[key] = max(rule.get(key, value), value)
                elif key in TIGHTER_MIN and isinstance(value, (int, float)):
                    rule[key] = min(rule.get(key, value), value)
                elif key == "severity" and value == "warning":
                    rule["severity"] = "warning"
                elif key == "colors":
                    rule["colors"] = list(dict.fromkeys([*rule.get("colors", []), *value]))[:64]
        merged.append(rule)
    holds = [rule for rule in merged if all(run(member, rule) for member in members)]
    dropped = sorted({rule["id"] for item in inferences for rule in item["suite"]["rules"]} - {r["id"] for r in holds})
    notes = {}
    for item in inferences:
        for entry in item["explanations"]:
            notes.setdefault(entry["id"], []).append(entry["measured"])
    return holds, dropped, notes


def dispatch(session, request, document=None):
    """Workflow ``suite-infer``: propose a suite from the open document (or every member of ``from_group``);
    ``apply`` saves it as a library suite named ``name`` and ``group`` makes that group inherit it."""
    from .assurance import digest, rule_result, validate_suite
    from .design import named
    from .project import Project
    from .resources import catalog, register

    name = named(request.get("name", "inferred"))
    for field in ("apply", "replace"):
        require(type(request.get(field, False)) is bool, f"{field} must be true or false", field=field)
    if request.get("group"):
        require(request.get("apply"), "group needs apply: true (the group inherits the saved library suite)",
                field="group")
    if request.get("from_group"):
        from .production import read_json

        path = session.resolve(f".vixl-groups/{named(request['from_group'])}.json")
        require(path.exists(), f"Unknown project group: {request['from_group']}", field="from_group")
        members = []
        for relative in read_json(path)["documents"]:
            member = Project.load(session.resolve(relative), limits=session.limits)
            member._workspace = session.workspace
            members.append(member)
        inferences = [infer(member, name) for member in members]

        def run(member, rule):
            try:
                return bool(rule_result(member, rule)[0])
            except Exception:
                return False

        rules, dropped, notes = combine(inferences, members, run)
        require(rules, "No rule holds for every member of the group")
        suite = {"version": 1, "description": f"Inferred from the {len(members)} approved members of group "
                                              f"{request['from_group']}; review before use.", "rules": rules}
        validate_suite(suite)
        result = {"name": name, "suite": suite, "suite_hash": digest(suite), "members": len(members),
                  "explanations": [{"id": rule["id"], "kind": rule["kind"], "measured": " | ".join(notes[rule["id"]])}
                                   for rule in rules],
                  **({"dropped": dropped} if dropped else {})}
    else:
        with session.project(document=document) as project:
            project = project.clone()
        result = infer(project, name)
    result["applied"] = False
    if request.get("apply"):
        exists = name in catalog("suites", workspace=session.workspace)
        require(not exists or request.get("replace"), f"A suite named {name!r} already exists; pass replace: true "
                "or choose another name", "output_exists", field="name")
        register("suites", name, result["suite"], workspace=session.workspace)
        result["applied"] = True
        if request.get("group"):
            result["group"] = inherit(session, request["group"], name)
    result["note"] = ("Review each rule against its explanation: delete what the family need not share and tighten "
                      "what it must. " + ("Saved as a library suite; documents attach it with suite-use (reference: "
                                          "true) or inherit it through a group or brand.json suites."
                                          if result["applied"] else "Save it with apply: true, or attach it to one "
                                          "document with suite-set."))
    return result


def inherit(session, group, suite):
    """Add a library suite to a project group's inherited ``suites``."""
    from .design import named
    from .fileio import file_lock
    from .production import read_json, write_json

    path = session.resolve(f".vixl-groups/{named(group)}.json")
    require(path.exists(), f"Unknown project group: {group}", field="group")
    with session._mutex, file_lock(str(path)):
        value = read_json(path)
        suites = value.get("suites", [])
        if suite not in suites:
            require(len(suites) < 32, "A group inherits at most 32 suites", field="group")
            value["suites"] = [*suites, suite]
            write_json(path, value)
    return {"name": value["name"], "suites": value["suites"]}
