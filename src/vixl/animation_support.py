"""Validate persisted animation-authoring metadata before evaluating render-time generators."""
from .errors import require
from .model import finite


def validate_state(project, state):
    from .audio import validate_track
    tracks = state.get("audio_tracks", [])
    require(isinstance(tracks, list) and len(tracks) <= 32, "Invalid audio tracks")
    for track in tracks:
        validate_track(track)
        require("source" not in track, "Timeline audio must embed imported sources")
        if "asset" in track:
            require(track["asset"] in project.assets, "Missing embedded audio")
    stop = state.get("stop_motion")
    if stop is not None:
        require(isinstance(stop, dict) and set(stop) == {"fps", "jitter", "seed"}, "Invalid stop-motion settings")
        finite(stop["fps"], "stop-motion fps", 1, 60)
        finite(stop["jitter"], "stop-motion jitter", 0, 10)
        require(isinstance(stop["seed"], int), "Stop-motion seed must be an integer")
    # Reuse command validation on a detached empty scene; these operations contain no file IO.
    from copy import copy, deepcopy
    from .scene import execute
    candidate = copy(project)
    candidate.state = deepcopy(state) if "camera" in state or "lighting" in state else state
    for key in ("camera", "lighting"):
        if key in state:
            allowed = {"from", "to", "start", "duration", "easing", "follow", "shake", "focus", "focus_to", "aperture", "seed"} if key == "camera" else {"lights", "ambient", "vignette", "exposure", "saturation", "tint"}
            require(isinstance(state[key], dict) and not set(state[key]) - allowed, f"Invalid {key} settings")
            execute(candidate, {"type": key, **state[key]})
    ids = {layer["id"] for layer in state["layers"]}
    for layer in state["layers"]:
        if "depth" in layer:
            finite(layer["depth"], "layer depth", 0.05, 1000)
        if "cut_paper" in layer:
            paper = layer["cut_paper"]
            require(isinstance(paper, dict) and set(paper) == {"grain", "roughness", "thickness", "seed", "previous_shadow"}, "Invalid cut-paper settings")
            for key, hi in (("grain", .5), ("roughness", 1), ("thickness", 20)):
                finite(paper[key], key, 0, hi)
            if paper["previous_shadow"] is not None:
                from .design import validate_style
                validate_style("drop-shadow", paper["previous_shadow"], state)
            require(isinstance(paper["seed"], int) and paper["seed"] >= 0, "Paper seed must be a nonnegative integer")
        if "particle" in layer:
            particle = layer["particle"]
            require(isinstance(particle, dict) and set(particle) == {"velocity", "spread", "gravity", "turbulence", "life", "start", "duration", "origin", "phase", "seed"}, "Invalid particle settings")
            for key in ("velocity", "spread", "origin"):
                require(isinstance(particle[key], list) and len(particle[key]) == 2, "Invalid particle coordinate pair")
                for value in particle[key]:
                    finite(value, key, -1e6, 1e6)
            for key, lo, hi in (("gravity", -100000, 100000), ("turbulence", 0, 10000), ("life", 10, 600000), ("start", 0, 600000), ("duration", 10, 600000), ("phase", 0, 1), ("seed", 0, 10)):
                finite(particle[key], key, lo, hi)
        if "character" in layer:
            character = layer["character"]
            require(layer["type"] == "group" and isinstance(character, dict) and set(character) == {"version", "parts", "bones"} and character["version"] == 1, "Invalid character metadata")
            parts, bones = character["parts"], character["bones"]
            require(isinstance(parts, dict) and len(parts) <= 64 and all(isinstance(v, str) for v in parts.values()), "Invalid character parts")
            require(isinstance(bones, dict) and len(bones) <= 64, "Invalid character rig")
            for name, bone in bones.items():
                require(isinstance(bone, dict) and bone.get("layer") in parts.values(), "Rig bone needs a character part")
                finite(bone.get("length"), "bone length", .01, 1e6)
                finite(bone.get("angle", 0), "bone angle", -3600, 3600)
                limits = bone.get("limits", [-180, 180])
                require(isinstance(limits, list) and len(limits) == 2, "Invalid joint limits")
                finite(limits[0], "joint limit", -3600, 3600)
                finite(limits[1], "joint limit", limits[0], 3600)
                seen = {name}
                parent = bone.get("parent")
                while parent:
                    require(parent in bones and parent not in seen, "Invalid rig hierarchy or cycle")
                    seen.add(parent)
                    parent = bones[parent].get("parent")
                if "origin" in bone:
                    require(isinstance(bone["origin"], list) and len(bone["origin"]) == 2, "Invalid bone origin")
                    for value in bone["origin"]:
                        finite(value, "bone origin", -1e6, 1e6)
        if "bubble" in layer:
            bubble = layer["bubble"]
            require(isinstance(bubble, dict) and set(bubble) == {"anchor", "text", "body", "tail", "style", "padding", "tail_width"}, "Invalid speech bubble")
            require(bubble["style"] in ("speech", "thought", "shout", "whisper"), "Invalid bubble style")
            require(all(isinstance(bubble[key], str) for key in ("anchor", "text", "body", "tail")), "Invalid bubble layer IDs")
            require(all(bubble[key] in ids for key in ("text", "body", "tail")), "Missing speech bubble component")
            finite(bubble["padding"], "bubble padding", 0, 1000)
            finite(bubble["tail_width"], "bubble tail width", .01, 1000)
        if "caption" in layer:
            from .captions import validate_caption
            require(isinstance(layer["caption"], dict), "Invalid caption metadata")
            caption = {key: value for key, value in layer["caption"].items() if key != "text_layer"}
            validate_caption(caption)
            require(layer["caption"].get("text_layer") in ids, "Missing caption text layer")
    library = state.get("character_library", {})
    require(isinstance(library, dict) and len(library) <= 128, "Invalid character library")
    for layers in library.values():
        require(isinstance(layers, list) and 1 <= len(layers) <= project.limits.max_layers, "Invalid saved character")
        require(all(isinstance(layer, dict) and isinstance(layer.get("id"), str) for layer in layers), "Invalid saved character layer")
