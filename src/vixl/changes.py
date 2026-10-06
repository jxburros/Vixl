"""Small, stable-ID edit summaries; full snapshots remain an explicit option."""


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
            layers[ident] = {"added": True, **_brief(new[ident])}
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
    with vixl_document_inspect, or use detail=compact for the new values."""
    changes, other = {}, []
    for key, value in compact_changes(before, after).items():
        if key == "layers":
            layers = {}
            for ident, delta in value.items():
                if delta.get("added"):
                    layers[ident] = {k: delta[k] for k in ("added", "name", "type", "bounds") if k in delta}
                elif delta.get("removed"):
                    layers[ident] = delta
                else:
                    layers[ident] = {"changed": sorted(k for k in delta if k != "bounds"),
                                     **({"bounds": delta["bounds"]} if "bounds" in delta else {})}
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


def _stroke(stroke):
    return {
        "brush": stroke["brush"],
        "points": len(stroke["points"]),
        "size": stroke["size"],
        "color": stroke.get("color", "black"),
        **({"mode": stroke["mode"]} if stroke.get("mode", "paint") != "paint" else {}),
    }


def _brief(layer):
    """One-line description of a layer: identity, kind, geometry and the main content field."""
    result = {"name": layer["name"], "type": layer["type"]}
    if "resolved_bounds" in layer:
        result["bounds"] = list(layer["resolved_bounds"])
    if layer["type"] == "text":
        text = layer.get("text", "")
        result["text"] = text if len(text) <= 80 else text[:77] + "..."
        result["size"] = layer.get("size")
    if layer["type"] == "shape":
        result["shape"] = layer.get("shape")
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
    return result


def summarize(project, target=None):
    """Token-light document description for agents (see inspect() for every stored field)."""
    state = project.inspect()
    if target:
        ident = project.layer(target)["id"]
        layer = next(item for item in state["layers"] if item["id"] == ident)
        return {"id": ident, **_brief(layer)}
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
        "layers": [{"id": layer["id"], **_brief(layer)} for layer in state["layers"]],
    }
    for key in ("variables", "swatches", "presets"):
        if state.get(key):
            result[key] = state[key] if key != "presets" else sorted(state[key])
    for key in ("artboards", "comps", "symbols", "guides", "character_styles", "paragraph_styles", "luts"):
        if state.get(key):
            result[key] = sorted(state[key])
    if state.get("selection"):
        result["selection"] = True
    if state.get("timeline", {}).get("tracks"):
        timeline = state["timeline"]
        result["timeline"] = {"duration": timeline["duration"], "fps": timeline["fps"], "tracks": len(timeline["tracks"])}
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
    if state["transaction"]:
        result["transaction"] = True
    return result
