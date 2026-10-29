"""Deterministic cue compositions compiled into ordinary editable layers and motion."""

from copy import deepcopy
from fnmatch import fnmatchcase
import random

from ...automation import bounded_object
from ...errors import require
from ...model import finite

MAX_COMPOSITIONS = 200
EDITABLE = {"x", "y", "width", "height", "rotation", "opacity", "text", "size", "color", "font",
            "fill", "stroke", "stroke_width", "text_layout", "align", "spacing", "effects", "styles"}


def select(project, timed, request):
    rules = request.get("compositions", [])
    require(isinstance(rules, list) and len(rules) <= 100, "compositions is a list of at most 100 rules")
    selected, counts = {}, {}
    occurrences, section_counts = [], {}
    for section in timed["sections"]:
        name = section["name"]
        section_counts[name] = section_counts.get(name, 0) + 1
        occurrences.append((section["start"], section_counts[name]))
    for r, rule in enumerate(rules):
        bounded_object(rule, {"match", "variant", "assign", "seed", "layout", "attach", "motion"}, "Unknown composition rule field")
        match = rule.get("match", {})
        bounded_object(match, {"section", "occurrence", "cue", "contains"}, "Unknown composition match field")
        for key in ("section", "contains"):
            require(key not in match or isinstance(match[key], str), f"Composition {key} must be text")
        for key in ("occurrence", "cue"):
            require(key not in match or type(match[key]) is int and match[key] >= (1 if key == "occurrence" else 0),
                    f"Composition {key} must be a valid index")
        require(rule.get("assign", "cycle") in ("cycle", "seeded"), "Composition assign must be cycle or seeded")
        require(type(rule.get("seed", 0)) is int, "Composition seed must be an integer")
        variants = rule.get("variant", {"layout": rule.get("layout", {"kind": "single"})})
        variants = variants if isinstance(variants, list) else [variants]
        require(1 <= len(variants) <= 32, "Composition needs 1–32 variants")
        for variant in variants:
            if isinstance(variant, str):
                require(project.layer(variant)["type"] == "group", "A composition variant must name a template group")
            else:
                bounded_object(variant, {"layout", "attach", "motion"}, "Unknown composition variant field")
        counts[r] = 0
        rng = random.Random(rule.get("seed", 0))
        for line in timed["lines"]:
            occurrence = next((number for start, number in reversed(occurrences) if start <= line["start"]), 1)
            if (line["index"] in selected or "section" in match and match["section"] != line.get("section") or
                    "occurrence" in match and match["occurrence"] != occurrence or
                    "cue" in match and match["cue"] != line["index"] or
                    "contains" in match and match["contains"].casefold() not in line["text"].casefold()):
                continue
            variant = rng.choice(variants) if rule.get("assign") == "seeded" else variants[counts[r] % len(variants)]
            counts[r] += 1
            spec = {key: deepcopy(rule[key]) for key in ("layout", "attach", "motion") if key in rule}
            if isinstance(variant, dict):
                spec.update(deepcopy(variant))
            else:
                spec["group"] = variant
            spec["occurrence"] = occurrence
            selected[line["index"]] = spec
    require(len(selected) <= MAX_COMPOSITIONS, f"At most {MAX_COMPOSITIONS} cue compositions per build", "resource_limit")
    return selected


def _phrases(line, kind):
    parts = [part.strip() for part in line["text"].split("|") if part.strip()]
    if kind != "single" and len(parts) == 1:
        words = line.get("words", [])
        if len(words) > 1:
            split = max(range(1, len(words)), key=lambda i: words[i]["time"] - words[i - 1].get("end", words[i - 1]["time"]))
            parts = [" ".join(w["text"] for w in words[:split]), " ".join(w["text"] for w in words[split:])]
        elif len(line["text"].split()) > 1:
            words = line["text"].split()
            split = (len(words) + 1) // 2
            parts = [" ".join(words[:split]), " ".join(words[split:])]
    return [" ".join(parts)] if kind == "single" else parts


def _descendants(project, group):
    from ...design import descendants
    ids = descendants(project, group["id"])
    return [layer for layer in project.state["layers"] if layer["id"] in ids]


def _fit(project, text, width, height, low, high):
    project.apply({"type": "fit-text", "target": text["id"], "width": max(1, round(width)),
                   "height": max(1, round(height)), "minimum": low, "maximum": high})


def install(project, timed, roles, request):
    """Create each cue's static composition before the shared lyric timeline is written."""
    selected = select(project, timed, request)
    from ...render import resolve_layout
    made = []
    for line in timed["lines"]:
        if line["index"] not in selected:
            continue
        spec = selected[line["index"]]
        layout = spec.get("layout", {})
        if isinstance(layout, str):
            layout = {"kind": layout}
        bounded_object(layout, {"kind", "fit", "entrance", "unit", "x", "y", "width", "height", "gap"}, "Unknown phrase layout field")
        kind = layout.get("kind", "single")
        require(kind in ("single", "stack", "setup-payoff"), "Phrase layout kind must be single, stack or setup-payoff")
        fit = layout.get("fit", {})
        bounded_object(fit, {"min_size", "max_size"}, "Unknown composition fit field")
        low, high = fit.get("min_size", 12), fit.get("max_size", 72)
        require(type(low) is int and type(high) is int and 1 <= low <= high <= 4096, "Composition fit sizes must be 1–4096")
        prefix = f"composition-{line['index']:04d}"
        require(not any(layer["name"].startswith(prefix) for layer in project.state["layers"]), "Template uses reserved composition names")
        if "group" in spec:
            source = project.layer(spec["group"])
            old = {layer["id"]: layer["name"] for layer in _descendants(project, source)}
            project.apply({"type": "duplicate", "target": source["id"], "name": prefix})
            group = project.layer(prefix)
            children = _descendants(project, group)
            for child in children:
                original = child["name"].removeprefix(prefix + "/")
                child["name"] = prefix + "/" + old[original]
            texts = [child for child in children if child["type"] == "text"]
            require(texts, "A composition group needs at least one text layer")
            # A template group can contain labels; only its first text is the lyric placeholder.
            texts = texts[:1]
            bounds = resolve_layout(project)[texts[0]["id"]]
            texts[0]["text"] = " ".join(line["text"].replace("|", " ").split())
            texts[0].pop("spans", None)
            _fit(project, texts[0], bounds[2], bounds[3], low, high)
            project.layer(source["id"])["visible"] = False
        else:
            canvas = project.state["canvas"]
            x = finite(layout.get("x", canvas["width"] * .1), "layout.x", 0, canvas["width"])
            y = finite(layout.get("y", canvas["height"] * .2), "layout.y", 0, canvas["height"])
            width = finite(layout.get("width", canvas["width"] * .8), "layout.width", 1, canvas["width"] - x)
            height = finite(layout.get("height", canvas["height"] * .6), "layout.height", 1, canvas["height"] - y)
            phrases = _phrases(line, kind)
            gap = finite(layout.get("gap", min(16, height * .05)), "layout.gap", 0, height)
            each = (height - gap * (len(phrases) - 1)) / len(phrases)
            require(each >= 1, "Phrase layout has no room for its text")
            texts = []
            for i, phrase in enumerate(phrases):
                name = f"{prefix}/text-{i}"
                project.apply({"type": "duplicate", "target": roles["lyric"], "name": name})
                text = project.layer(name)
                text.pop("parent", None)
                text.pop("spans", None)
                text.update(text=phrase, x=x, y=y + (each + gap) * i, rotation=0, constraints={})
                maximum = max(low, round(high * .75)) if kind == "setup-payoff" and i == 0 else high
                _fit(project, text, width, each, low, maximum)
                texts.append(text)
            project.apply({"type": "group", "name": prefix, "targets": [text["id"] for text in texts]})
            group = project.layer(prefix)
        group["visible"] = True
        if spec.get("attach"):
            _attach(project, spec["attach"], group, texts[-1], prefix)
        line["composition"] = {"group": group["id"], "text_layers": [text["id"] for text in texts],
                               "text": " ".join(line["text"].replace("|", " ").split()),
                               "variant": spec.get("group", kind), "occurrence": spec["occurrence"], "section": line.get("section")}
        made.append((line, spec, layout))
    return made


def _attach(project, spec, group, text, prefix):
    from ...render import resolve_layout, resolved_layers
    from ...text_metrics import inspect_text
    from ...affine import layer_matrix
    from ...checks import group_matrix
    bounded_object(spec, {"symbol", "to", "gap", "width"}, "Unknown composition attachment field")
    require(isinstance(spec.get("symbol"), str), "Attachment symbol names a saved object")
    anchor = spec.get("to", "baseline")
    require(anchor in ("baseline", "cap-height", "ink-right"), "Attachment to must be baseline, cap-height or ink-right")
    gap = finite(spec.get("gap", 8), "attachment.gap", 0, 1000)
    layers = resolved_layers(project)
    resolved = next(layer for layer in layers if layer["id"] == text["id"])
    bounds = resolve_layout(project, layers=layers)
    x, y, w, h = bounds[text["id"]]
    metrics = inspect_text(project, resolved, bounds[text["id"]])
    require(metrics.get("baseline") is not None, "Attachment text needs measurable ink and a baseline")
    baseline = metrics.get("baselines", [metrics["baseline"]])[-1]
    ix, iy, iw, ih = metrics["ink_bounds"]
    # Attachment points use the same parent transform as the rendered text, including nested variants.
    matrix = group_matrix(resolved, {layer["id"]: layer for layer in layers}, bounds)
    anchor_y = baseline if anchor == "baseline" else metrics["baseline"] - metrics["cap_height"] if anchor == "cap-height" else iy + ih / 2
    px, py, _ = matrix @ layer_matrix(resolved, bounds[text["id"]]) @ [ix + iw + gap - x, anchor_y - y, 1]
    name = prefix + "/attachment"
    project.apply({"type": "object-place", "name": spec["symbol"], "name_as": name, "x": px, "y": py,
                   **({"width": spec["width"]} if "width" in spec else {})})
    attachment = project.layer(name)
    if anchor == "baseline":
        attachment["y"] -= resolve_layout(project)[attachment["id"]][3]
    project.apply({"type": "reparent", "targets": [attachment["id"]], "into": group["id"], "keep": "appearance"})


def animate(project, timed, roles, made):
    """Add cue visibility, kinetic entrances and bounded part motion after the main timeline exists."""
    from ...timeline import execute_timeline as execute
    from ...kinetic import PRESETS
    from .lyrics import section_match
    normal = {roles["lyric"], *roles.get("lyrics", {}).values()}
    for source in {spec["group"] for _, spec, _ in made if "group" in spec}:
        ident = project.layer(source)["id"]
        project.state["timeline"]["tracks"] = [track for track in project.state["timeline"]["tracks"]
                                                if not (track["target"] == ident and track["property"] == "visible")]
        execute(project, {"type": "keyframe", "target": ident, "property": "visible", "time": 0, "value": False})
    for ident in normal:
        track = next((track for track in project.state["timeline"]["tracks"]
                      if track["target"] == ident and track["property"] == "visible"), None)
        if track is None or not any(key["time"] == 0 for key in track["keys"]):
            execute(project, {"type": "keyframe", "target": ident, "property": "visible", "time": 0,
                              "value": project.layer(ident)["visible"]})
    for line, spec, layout in made:
        composition = line["composition"]
        group = composition["group"]
        for time, value in ((0, False), (line["show"], True), (line["hide"], False)):
            execute(project, {"type": "keyframe", "target": group, "property": "visible", "time": time, "value": value})
        for ident in normal:
            execute(project, {"type": "keyframe", "target": ident, "property": "visible", "time": line["show"], "value": False})
            next_line = next((item for item in timed["lines"] if item["index"] == line["index"] + 1), None)
            if next_line and "composition" not in next_line:
                variant = section_match(roles.get("lyrics", {}), next_line.get("section"))
                chosen = roles.get("lyrics", {}).get(variant, roles["lyric"])
                execute(project, {"type": "keyframe", "target": chosen, "property": "visible", "time": next_line["show"], "value": True})
        entrance = layout.get("entrance", "fade-up")
        require(entrance in PRESETS, "Unknown composition kinetic entrance")
        unit = layout.get("unit", "line")
        require(unit in ("word", "line"), "Composition unit must be word or line")
        span = max(1, min(300, (line["hide"] - line["show"]) // 3))
        for ident in composition["text_layers"]:
            # A zero stagger bounds every entrance inside its cue, even for long wrapped text.
            project.apply({"type": "text-animate", "target": ident, "unit": unit, "preset": entrance,
                           "start": line["show"], "duration": span, "stagger": 0})
        line["settled"] = line["show"] + span
        if spec.get("motion"):
            _parts(project, line, spec["motion"])
    return sum(len(track["keys"]) for track in project.state["timeline"]["tracks"])


def _parts(project, line, spec):
    bounded_object(spec, {"parts", "span"}, "Unknown composition motion field")
    parts = spec.get("parts", {})
    require(isinstance(parts, dict) and len(parts) <= 32, "Motion parts is a map of up to 32 name patterns")
    require(spec.get("span", "cue") in ("cue", "entrance"), "Motion span must be cue or entrance")
    group = project.layer(line["composition"]["group"])
    children = _descendants(project, group)
    start = line["show"]
    end = line["settled"] if spec.get("span") == "entrance" else line["hide"]
    for pattern, motion in parts.items():
        require(isinstance(pattern, str), "Part pattern must be text")
        bounded_object(motion, {"preset", "amplitude"}, "Unknown part motion field")
        preset = motion.get("preset", "flicker")
        require(preset in ("flicker", "hover", "wiggle"), "Part motion preset is flicker, hover or wiggle")
        amount = finite(motion.get("amplitude", 2), "motion.amplitude", 0, 10)
        targets = [layer["id"] for layer in children if fnmatchcase(layer["name"].removeprefix(group["name"] + "/"), pattern)]
        require(targets, f"Part pattern {pattern!r} matches no composition layers")
        project.apply({"type": "motion", "recipe": "wiggle" if preset == "flicker" else preset,
                       "targets": targets, "property": "translate-y", "amount": amount,
                       "start": start, "duration": max(10, end - start), "seed": line["index"], "samples": 16})


def baseline(project):
    return {layer["name"]: {field: deepcopy(layer[field]) for field in EDITABLE if field in layer}
            for layer in project.state["layers"] if layer["name"].startswith("composition-")}


def approved_overrides(project):
    from .verification import _review
    decision = _review(project)["status"]
    if decision != "approved":
        if decision == "changes_requested":
            return {}
        return {item["name"]: {"fields": deepcopy(item["fields"]), "remove": list(item.get("remove", []))}
                for item in project.state.get("lyric_build", {}).get("overrides", {}).values()}
    old = project.state.get("lyric_build", {}).get("composition_baseline", {})
    return {name: {"fields": {field: value for field, value in values.items() if old[name].get(field) != value},
                   "remove": sorted(set(old[name]) - set(values))}
            for name, values in baseline(project).items() if name in old}


def restore(project, overrides):
    applied = {}
    for layer in project.state["layers"]:
        entry = overrides.get(layer["name"])
        if entry and (entry["fields"] or entry.get("remove")):
            layer.update(deepcopy(entry["fields"]))
            for field in entry.get("remove", []):
                layer.pop(field, None)
            applied[layer["id"]] = {"name": layer["name"], **deepcopy(entry)}
    return applied


def preview(request, root, limits=None):
    """Reuse the film preview writer for one built cue, without rebuilding or exporting a full song."""
    from ...project import Project
    from ..film.film import local_path, preview as film_preview
    bounded_object(request, {"build", "cue", "output"}, "Unknown cue preview field")
    for key in ("build", "output"):
        require(isinstance(request.get(key), str) and request[key], f"Cue preview needs {key}", field=key)
    project = Project.load(local_path(root, request["build"]), limits=limits)
    windows = project.state.get("lyric_build", {}).get("cue_windows", [])
    cue = request.get("cue")
    require(type(cue) is int and 0 <= cue < len(windows), "cue must index a built lyric line", field="cue")
    window = windows[cue]
    canvas, timeline = project.state["canvas"], project.state["timeline"]
    spec = {"version": 1, "width": canvas["width"], "height": canvas["height"], "fps": timeline["fps"],
            "quality": "draft", "shots": [{"source": request["build"], "duration": timeline["duration"]}]}
    output = local_path(root, request["output"])
    options = {"time": window["settled"]} if output.suffix.lower() == ".png" else {"start": window["show"], "end": window["hide"]}
    return film_preview(spec, root, output, limits=limits, **options)
