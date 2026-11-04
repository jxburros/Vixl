"""Small, stable-ID edit summaries; full snapshots remain an explicit option."""

TEXT_METRICS = ("ink_bounds", "line_bounds", "baseline", "baselines", "ascent", "descent", "cap_height", "x_height", "metrics_space")
# Brief detail keeps the metrics needed to align text; detail=compact or an inspect gives the rest.
BRIEF_TEXT_METRICS = ("ink_bounds", "baseline")
BRIEF_DECIMALS = 2
# Layers whose children are generated for them: a brief apply result and a collapsed inspect summarise the
# children at the parent with a count instead of listing each one.
GENERATOR_KEYS = (("chart", "chart"), ("table", "table"), ("container", "container"))


def generator_kind(layer, state=None, *, objects=False):
    """What generates ``layer``'s children: chart, table, container or diagram (from the document's diagram
    records); with ``objects`` also an object group. None for an ordinary layer."""
    if not isinstance(layer, dict):
        return None
    for key, kind in GENERATOR_KEYS:
        if key in layer:
            return kind
    if state is not None and layer["id"] in {(rec or {}).get("group") for rec in (state.get("diagrams") or {}).values()}:
        return "diagram"
    if objects and layer.get("type") == "group" and layer.get("object"):
        return "object"
    return None


def ack(result, head=None):
    """detail=ack: ``{ok, head, changed: N, warnings}`` from a brief apply result; ``changed`` counts every added,
    changed and removed layer, including the ones a brief result left out, and the children summarised at a
    parent."""
    changes = result.get("changes") or {}
    layers = changes.get("layers") or {}
    changed = len(layers)
    for entry in layers.values():
        changed += sum(entry.get(key, 0) for key in ("children_added", "children_changed", "children_removed"))
    for key in ("layers_omitted", "changed_omitted", "removed_omitted"):
        changed += (changes.get(key) or {}).get("count", 0)
    summary = {"ok": bool(result.get("success", True)), "head": head if head is not None else result.get("head"),
               "changed": changed, "warnings": list(result.get("warnings") or [])}
    for key in ("dry_run", "proposal_id", "outcome", "report_path", "steps_omitted"):
        if result.get(key) not in (None, False):
            summary[key] = result[key]
    for key in ("check", "suites"):
        if isinstance(result.get(key), dict):
            summary[key] = _review_summary(key, result[key])
    return summary


def _review_summary(kind, value):
    if kind == "check":
        issues = value.get("issues") or []
        return {"passed": value.get("passed"), "findings": len(issues),
                **({"fix": sum(1 for i in issues if i.get("action") == "fix")} if issues else {})}
    return {name: (item.get("status") if isinstance(item, dict) else item) for name, item in value.items()}


REPORT_FINDINGS = 10  # a bounded summary keeps this many findings; report_path holds them all


def report_summary(kind, result):
    """The bounded summary returned beside ``report_path``: a check keeps its verdict, counts and the first
    REPORT_FINDINGS findings; an apply result keeps the ack summary plus the omitted-finding count."""
    if kind == "check":
        issues = result.get("issues") or []
        summary = {key: result[key] for key in ("passed", "verdict", "outcome", "counts", "pagination", "repairs")
                   if key in result}
        summary["findings"] = len(issues)
        summary["issues"] = issues[:REPORT_FINDINGS]
        if len(issues) > REPORT_FINDINGS:
            summary["issues_omitted"] = len(issues) - REPORT_FINDINGS
        if isinstance(result.get("suites"), dict):
            summary["suites"] = _review_summary("suites", result["suites"])
        return summary
    summary = ack(result)
    issues = (result.get("check") or {}).get("issues") or []
    if issues:
        summary["check"]["issues"] = issues[:REPORT_FINDINGS]
        if len(issues) > REPORT_FINDINGS:
            summary["check"]["issues_omitted"] = len(issues) - REPORT_FINDINGS
    for key in ("normalized", "next_steps", "unfilled_slots", "font_install"):
        if result.get(key):
            summary[key] = result[key]
    return summary


def compact_changes(before, after):
    changes = {}
    for key in (
        "canvas",
        "selection",
        "variables",
        "active_layer",
        "presets",
        "swatches",
        "palettes",
        "active_palette",
        "containers",
        "character_styles",
        "paragraph_styles",
        "artboards",
        "luts",
        "comps",
        "guides",
        "grids",
        "symbols",
        "design_guidance",
        "fonts",
        "typography",
        "template",
        "brushes",
        "form",
        "palette_roles",
        "style",
    ):
        if before.get(key) != after.get(key):
            changes[key] = after.get(key)
    if before.get("layout") != after.get("layout") and after.get("layout"):
        changes["layout"] = {k: v for k, v in after["layout"].items() if k != "layers"}
    for key in ("suites", "roles", "motions", "actions"):
        if before.get(key) != after.get(key):
            changes[key] = {"names": sorted(after.get(key, {}))}
    if before.get("recipe") != after.get("recipe"):
        changes["recipe"] = {"inputs": sorted(after.get("recipe", {}).get("inputs", {}))}
    if before.get("timeline") != after.get("timeline"):
        timeline = after.get("timeline") or {}
        changes["timeline"] = {
            "duration": timeline.get("duration"),
            "fps": timeline.get("fps"),
            "tracks": [f"{t['target']}.{t['property']} ({len(t['keys'])} keys)" for t in timeline.get("tracks", [])],
            **({"markers": timeline["markers"]} if timeline.get("markers") else {}),
        }
    if before.get("animation") != after.get("animation"):
        previous = {f["name"]: f for f in before.get("animation", {}).get("frames", [])}
        current = {f["name"]: f for f in after.get("animation", {}).get("frames", [])}
        changes["animation"] = {
            "loop": after.get("animation", {}).get("loop", 0),
            "frames": [{"name": name, "duration": f["duration"]} for name, f in current.items()],
            "changed": [name for name, f in current.items() if previous.get(name) != f],
            "removed": [name for name in previous if name not in current],
        }
        if before.get("animation", {}).get("animations") != after.get("animation", {}).get("animations"):
            from .animation_sets import summaries

            changes["animation"]["animations"] = summaries(after.get("animation", {}))
    if before.get("pages") != after.get("pages") or before.get("masters") != after.get("masters"):
        changes["pages"] = [{k: v for k, v in page.items() if k in ("number", "name", "layers", "master", "active", "hidden")}
                            for page in after.get("pages") or []]
        if after.get("masters"):
            changes["masters"] = sorted(after["masters"])
    if before.get("page") != after.get("page"):
        # A different page is active: report it instead of every layer as added or removed.
        changes["page"] = after.get("page")
        changes["layers"] = {layer["id"]: _brief(layer) for layer in after["layers"][:40]}
        return changes
    old = {layer["id"]: layer for layer in before["layers"]}
    new = {layer["id"]: layer for layer in after["layers"]}
    layers = {}
    for ident in [*new, *(i for i in old if i not in new)]:
        if ident not in old:
            layers[ident] = {"added": True, **_brief(new[ident], TEXT_METRICS)}
        elif ident not in new:
            layers[ident] = {"removed": True, "name": old[ident]["name"]}
        else:
            # New values only: the caller already knows what it changed from.
            delta = {
                ("bounds" if key == "resolved_bounds" else key): new[ident].get(key)
                for key in [*new[ident], *(k for k in old[ident] if k not in new[ident])]
                if old[ident].get(key) != new[ident].get(key)
            }
            if "strokes" in delta:
                # Stroke points can be long; report counts and the newest stroke's brush.
                strokes = delta.pop("strokes") or []
                delta["strokes"] = {"count": len(strokes), **({"last": _stroke(strokes[-1])} if strokes else {})}
            if delta:
                layers[ident] = delta
    if layers:
        changes["layers"] = layers
    survivors = [ident for ident in old if ident in new]
    if [ident for ident in new if ident in old] != survivors:
        changes["layer_order"] = list(new)
    return changes


def brief_changes(before, after):
    """The leanest summary: which layers were added, removed or changed and where they ended up
    (``bounds``), without new field values. The caller knows what it asked for; read a layer
    with vixl_document(action='inspect'), or use detail=compact for the new values. Numbers are
    rounded to BRIEF_DECIMALS and a text layer carries only BRIEF_TEXT_METRICS."""
    changes, other = {}, []
    current = {layer["id"]: layer for layer in after["layers"]}
    previous = {layer["id"]: layer for layer in before["layers"]}
    for key, value in compact_changes(before, after).items():
        if key == "layers":
            layers = {}
            for ident, delta in value.items():
                if delta.get("added"):
                    layers[ident] = {k: delta[k] for k in ("added", "name", "type", "bounds", "content_bounds", *BRIEF_TEXT_METRICS)
                                     if k in delta}
                elif delta.get("removed"):
                    layers[ident] = delta
                else:
                    layers[ident] = {"changed": sorted(k for k in delta if k not in ("bounds", "canvas_bounds", "content_bounds",
                                                                                     "path_nodes", *TEXT_METRICS)),
                                     **{key: delta[key] for key in (*BRIEF_TEXT_METRICS, "content_bounds") if key in delta},
                                     **({"bounds": delta["bounds"]} if "bounds" in delta else {})}
                layers[ident].update(_grouped(current.get(ident), current))
                layers[ident] = _rounded(layers[ident])
            _fold_generated(layers, current, previous, after)
            changes["layers"] = layers
        elif key in ("canvas", "active_layer", "page", "selection"):
            changes[key] = value
        elif key == "layer_order":
            changes[key] = "changed"
        else:
            other.append(key)
    if other:
        changes["also_changed"] = sorted(other)
    return changes


def _fold_generated(layers, current, previous, after):
    """Children generated by a chart, table, container or diagram are summarised at the parent: the parent's
    entry (made when the batch did not touch the parent itself) carries ``generated`` and counts of the children
    added, changed and removed, with a few names."""
    folded = {}
    for ident, entry in list(layers.items()):
        layer = current.get(ident) or previous.get(ident) or {}
        parent = layer.get("parent")
        if not parent or ident == parent:
            continue
        kind = generator_kind(current.get(parent) or previous.get(parent), after)
        if kind is None:
            continue
        state = "added" if entry.get("added") else "removed" if entry.get("removed") else "changed"
        record = folded.setdefault(parent, {"kind": kind, "added": [], "changed": [], "removed": []})
        record[state].append(entry.get("name") or layer.get("name") or ident)
        del layers[ident]
    for parent, record in folded.items():
        entry = layers.get(parent)
        if entry is None:
            layer = current.get(parent) or previous.get(parent) or {}
            entry = layers[parent] = {"name": layer.get("name", parent), "type": layer.get("type", "group"), "changed": []}
        entry["generated"] = record["kind"]
        names = []
        for state in ("added", "changed", "removed"):
            if record[state]:
                entry[f"children_{state}"] = len(record[state])
                names.extend(record[state])
        entry["children_sample"] = names[:5]


def _rounded(value):
    """``value`` with every float rounded to BRIEF_DECIMALS (a float that rounds to a whole number becomes an int)."""
    if isinstance(value, float):
        number = round(value, BRIEF_DECIMALS)
        return int(number) if number.is_integer() else number
    if isinstance(value, list | tuple):
        return [_rounded(item) for item in value]
    if isinstance(value, dict):
        return {key: _rounded(item) for key, item in value.items()}
    return value


CONDENSE = 12  # brief detail lists at most this many new children of one group (a star field adds hundreds)
BRIEF_LIMIT = 25  # brief detail lists at most this many added layers in all (a batch can add thousands)
BRIEF_LIMIT_CHANGED = 50  # and at most this many changed, and this many removed, layers
MORE = "detail='compact' or vixl_document(action='layers')"


def condense(result):
    """Brief detail: a new group with more than CONDENSE new children (stars, scatter, string lights, a
    radial repeat) is listed with a count and a few names instead of every child, and its ``groups`` record
    without each member's offset, so one call does not return tens of thousands of tokens. Inspect the group,
    or use detail=compact, for every child."""
    layers = (result.get("changes") or {}).get("layers") or {}
    children = {}
    for ident, entry in layers.items():
        if entry.get("added") and entry.get("parent") in layers and layers[entry["parent"]].get("added"):
            children.setdefault(entry["parent"], []).append(ident)
    for group, members in children.items():
        if len(members) <= CONDENSE:
            continue
        names = [layers[ident]["name"] for ident in members]
        for ident in members:
            del layers[ident]
        layers[group].update(children_added=len(names), children_sample=names[:5])
    for record in result.get("groups", []):
        if isinstance(record, dict) and len(record.get("members", {})) > CONDENSE:
            names = list(record.pop("members"))
            record.update(member_count=len(names), members_sample=names[:5])
    if layers:
        _cap(result["changes"], layers)
    if len(result.get("defaults") or []) > BRIEF_LIMIT:
        # One record per layer that took a house default (stage, line height, fill).
        result["defaults_omitted"] = len(result["defaults"]) - BRIEF_LIMIT
        result["defaults"] = result["defaults"][:BRIEF_LIMIT]
    return result


def _cap(changes, layers):
    """Keep the first BRIEF_LIMIT added and BRIEF_LIMIT_CHANGED changed and removed layers; the rest are
    counted under ``layers_omitted``, ``changed_omitted`` and ``removed_omitted``."""
    kinds = {"added": [], "changed": [], "removed": []}
    for ident, entry in layers.items():
        kinds["added" if entry.get("added") else "removed" if entry.get("removed") else "changed"].append(ident)
    for kind, limit, key in (("added", BRIEF_LIMIT, "layers_omitted"), ("changed", BRIEF_LIMIT_CHANGED, "changed_omitted"),
                             ("removed", BRIEF_LIMIT_CHANGED, "removed_omitted")):
        dropped = kinds[kind][limit:]
        if not dropped:
            continue
        by_parent = {}
        for ident in dropped:
            parent = layers[ident].get("parent_name") or layers[ident].get("parent") or "(top)"
            by_parent[parent] = by_parent.get(parent, 0) + 1
        sample = [layers[ident].get("name", ident) for ident in dropped[:5]]
        for ident in dropped:
            del layers[ident]
        changes[key] = {"count": len(dropped), "by_parent": by_parent, "sample": sample, "more": MORE}


def _grouped(layer, layers):
    """A grouped layer's ``bounds`` are local to its group: name the group and add canvas bounds."""
    if not layer or not layer.get("parent"):
        return {}
    parent = layers.get(layer["parent"])
    return {"parent": layer["parent"], **({"parent_name": parent["name"]} if parent else {}), "coordinate_space": "parent",
            **({"canvas_bounds": [round(v, 2) for v in layer["canvas_bounds"]]} if "canvas_bounds" in layer else {})}


def _stroke(stroke):
    return {
        "brush": stroke["brush"],
        "points": len(stroke["points"]),
        "size": stroke["size"],
        "color": stroke.get("color", "black"),
        **({"mode": stroke["mode"]} if stroke.get("mode", "paint") != "paint" else {}),
    }


def _brief(layer, metrics=BRIEF_TEXT_METRICS):
    """One-line description of a layer: identity, kind, geometry and the main content field. A text layer carries
    the ``metrics`` named (the alignment metrics by default; TEXT_METRICS for every measured one)."""
    result = {"name": layer["name"], "type": layer["type"]}
    if "resolved_bounds" in layer:
        result["bounds"] = list(layer["resolved_bounds"])
    if layer["type"] == "text":
        for key in metrics:
            if key in layer:
                result[key] = layer[key]
        text = layer.get("text", "")
        result["text"] = text if len(text) <= 80 else text[:77] + "..."
        result["size"] = layer.get("size")
    if layer["type"] == "shape":
        result["shape"] = layer.get("shape")
        if "content_bounds" in layer:
            result["content_bounds"] = layer["content_bounds"]
    if layer["type"] == "paint":
        result["strokes"] = len(layer.get("strokes", []))
    if layer["type"] == "link":
        result.update({key: layer[key] for key in ("source", "artboard", "source_page") if key in layer})
    for key in ("color", "fill"):
        if key in layer:
            result[key] = layer[key]
    if layer.get("parent"):
        result["parent"] = layer["parent"]
    if not layer.get("visible", True):
        result["visible"] = False
    if layer.get("opacity", 1) != 1:
        result["opacity"] = layer["opacity"]
    if layer.get("blend", "normal") != "normal":
        result["blend"] = layer["blend"]
    if layer.get("rotation"):
        result["rotation"] = layer["rotation"]
    if layer.get("effects"):
        result["effects"] = [effect["name"] for effect in layer["effects"]]
    if layer.get("styles"):
        result["styles"] = sorted(layer["styles"])
    if layer.get("mask"):
        result["mask"] = True
    if layer.get("clip"):
        result["clip"] = layer["clip"]
    if layer.get("constraints"):
        result["constraints"] = layer["constraints"]
    provenance = layer.get("provenance") or {}
    source = provenance.get("source")
    if isinstance(source, dict) and source.get("url"):
        result["source_url"] = source["url"]
    for key in ("credit", "license"):
        if provenance.get(key):
            result[key] = provenance[key]
    # layer-intent settings, so an agent can see why a check exempts a layer.
    for key in ("role", "tags", "detached_ok", "allow_crop", "color_vision_safe", "waive", "literal_text", "alt", "decorative",
                "priority", "focal"):
        if layer.get(key):
            result[key] = layer[key]
    from .objects import brief as object_brief

    result.update(object_brief(layer))
    return result


INSPECT_LIMIT = 200  # layers one inspect lists by default; offset pages through the rest
LAYER_FIELDS = ("id", "name", "type")  # always kept when ``fields`` projects the entries


def summarize(project, target=None, *, offset=0, limit=INSPECT_LIMIT, fields=None, collapse=False, filter=None,
              since=None):
    """Token-light document description for agents (see inspect() for every stored field). The layer list is
    filtered (``filter``: {type, name (a glob), parent (a layer or "none" for top-level layers)}), collapsed
    (``collapse``: the children of charts, tables, diagrams, containers and object groups become ``children: N``
    at the parent), restricted to the layers changed since a revision (``since``: a head from an earlier result;
    removed layers are listed under ``removed``), paged (``offset``, ``limit``; ``next_offset`` is null at the
    end) and projected (``fields``: the keys to keep, besides id, name and type). Text layers carry
    ``ink_bounds`` and ``baseline``; the full metrics are in inspect(). Numbers are rounded to two decimals."""
    from .errors import require

    state = project.inspect()
    if target:
        ident = project.layer(target)["id"]
        layer = next(item for item in state["layers"] if item["id"] == ident)
        return _rounded({"id": ident, **_brief(layer)})
    require(isinstance(offset, int) and offset >= 0, "offset is a whole number", field="offset")
    require(isinstance(limit, int) and limit >= 1, "limit is a positive whole number", field="limit")
    canvas = state["canvas"]
    result = {
        "canvas": {
            "width": canvas["width"],
            "height": canvas["height"],
            "background": canvas["background"],
            **{k: canvas[k] for k in ("size", "dpi", "bleed", "safe") if k in canvas},
        },
        "active_layer": state["active_layer"],
        "head": state["head"],
    }
    layers = state["layers"]
    index = {item["id"]: item for item in project.state["layers"]}
    removed = None
    if since is not None:
        changed, removed = _changed_since(project, since)
        layers = [layer for layer in layers if layer["id"] in changed]
        result["since"] = since
    if collapse:
        counts = {}
        kept = []
        for layer in layers:
            parent = index.get(layer.get("parent") or "")
            if parent is not None and generator_kind(parent, project.state, objects=True):
                counts[parent["id"]] = counts.get(parent["id"], 0) + 1
            else:
                kept.append(layer)
        layers = kept
    if filter:
        layers = _filtered(project, layers, filter)
    entries = [{"id": layer["id"], **_brief(layer)} for layer in layers]
    if collapse:
        for entry in entries:
            kind = generator_kind(index.get(entry["id"]), project.state, objects=True)
            if kind:
                entry["generated"] = kind
                entry["children"] = counts.get(entry["id"], 0)
    if since is not None:
        for entry in entries:
            entry["change"] = changed[entry["id"]]
    from .objects import path_of

    for entry in entries:
        if "object" in entry or "object_part" in entry:
            path = path_of(project, index[entry["id"]], index)
            if path and path != entry["name"]:
                entry["object_path"] = path
    if fields is not None:
        require(isinstance(fields, list | tuple) and all(isinstance(f, str) for f in fields),
                "fields is a list of layer field names", field="fields")
        keep = {*LAYER_FIELDS, *fields}
        entries = [{key: value for key, value in entry.items() if key in keep} for entry in entries]
    result["layer_count"] = len(entries)
    result["layers"] = _rounded(entries[offset:offset + limit])
    result["next_offset"] = offset + limit if offset + limit < len(entries) else None
    if removed:
        result["removed"] = removed
    for key in ("variables", "swatches", "presets"):
        if state.get(key):
            result[key] = state[key] if key != "presets" else sorted(state[key])
    for key in ("artboards", "comps", "symbols", "guides", "character_styles", "paragraph_styles", "luts", "diagrams", "flows"):
        if state.get(key):
            result[key] = sorted(state[key])
    if state.get("selection"):
        result["selection"] = True
    if state.get("timeline", {}).get("tracks") or state.get("timeline", {}).get("text_animations"):
        timeline = state["timeline"]
        result["timeline"] = {"duration": timeline["duration"], "fps": timeline["fps"], "tracks": len(timeline["tracks"]),
                              **({"text_animations": len(timeline["text_animations"])} if timeline.get("text_animations") else {})}
    if state.get("brushes"):
        result["brushes"] = sorted(state["brushes"])
    if state.get("animation", {}).get("frames"):
        result["animation_frames"] = [frame["name"] for frame in state["animation"]["frames"]]
    if state.get("animation", {}).get("animations"):
        result["animations"] = sorted(state["animation"]["animations"])
    if state.get("fields"):
        result["fields"] = [{k: v for k, v in item.items() if k in ("key", "kind", "required", "tab", "rect_pt", "page", "option")}
                            for item in state["fields"]]
    if state.get("form"):
        result["form"] = state["form"]
    if state.get("links"):
        problems = [{key: item[key] for key in ("layer", "source", "state", "message") if key in item}
                    for item in state["links"] if item["state"] != "ok"]
        counts = {name: sum(1 for item in state["links"] if item["state"] == name) for name in {i["state"] for i in state["links"]}}
        result["links"] = {"count": len(state["links"]), **{name: n for name, n in sorted(counts.items()) if name != "ok"},
                           **({"problems": problems[:20]} if problems else {})}
    from .objects import all_objects, path_of, record

    objects = all_objects(project)
    if objects:
        index = {item["id"]: item for item in project.state["layers"]}
        result["objects"] = [{"path": path_of(project, layer, index), "kind": record(layer)["kind"]}
                             for layer in objects][:100]
    for key in ("accessibility", "page_accessibility"):
        if state.get(key):
            result[key] = state[key]
    if state["transaction"]:
        result["transaction"] = True
    return result


def _changed_since(project, since):
    """The layers changed since revision ``since``: ``({id: "added" | "changed"}, [{id, name} removed])``, from
    the stored states (a history diff; no rendering)."""
    from .errors import require

    require(isinstance(since, str) and since in project.nodes,
            f"Unknown revision {since!r}; pass a head from an earlier result or vixl_document(action='history')",
            "not_found", field="since")
    old = {layer["id"]: layer for layer in project._state_at(since).get("layers", [])}
    new = {layer["id"]: layer for layer in project.state["layers"]}
    changed = {ident: ("added" if ident not in old else "changed") for ident, layer in new.items()
               if ident not in old or old[ident] != layer}
    removed = [{"id": ident, "name": layer["name"]} for ident, layer in old.items() if ident not in new]
    return changed, removed


def _filtered(project, layers, filter):
    """``filter`` = {type, name (glob), parent (a layer, or "none" for top-level layers)}."""
    from fnmatch import fnmatchcase

    from .errors import require

    require(isinstance(filter, dict) and set(filter) <= {"type", "name", "parent"},
            "filter is an object with type, name (a glob) and parent", field="filter")
    kind, name, parent = filter.get("type"), filter.get("name"), filter.get("parent")
    parent_id = None
    if parent not in (None, "none", ""):
        parent_id = project.layer(parent)["id"]
    kept = []
    for layer in layers:
        if kind is not None and layer["type"] != kind:
            continue
        if name is not None and not fnmatchcase(layer["name"], name):
            continue
        if parent is not None and (layer.get("parent") or None) != parent_id:
            continue
        kept.append(layer)
    return kept
