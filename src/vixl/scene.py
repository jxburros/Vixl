"""Depth compositing, deterministic particles/camera motion and cut-paper rendering."""
from copy import deepcopy
import hashlib
import math
import numpy as np
from PIL import Image, ImageFilter
from .errors import require
from .model import finite

TYPES = ("layer-depth", "camera", "lighting", "particles", "cut-paper")


def schemas(add):
    from .motion_schema import documented
    add = documented(add)
    from .schema import S, N, B
    from .timeline import easing_schema
    point = {"type": "array", "items": N, "minItems": 2, "maxItems": 2}
    pose = {"type": "array", "items": N, "minItems": 3, "maxItems": 3}
    add("layer-depth", {"depth": N}, ["depth"])
    add("camera", {"from": pose, "to": pose, "start": N, "duration": N, "easing": easing_schema(), "follow": S, "shake": N, "focus": N, "focus_to": N, "aperture": N, "seed": {"type": "integer"}, "clear": B})
    add("lighting", {"lights": {"type": "array", "maxItems": 16, "items": {"type": "object"}}, "ambient": N, "vignette": N, "exposure": N, "saturation": N, "tint": S, "shadow": {"type": "object"}, "clear": B})
    add("particles", {"name": S, "preset": {"enum": ["dust", "bubbles", "sparks", "spores"]}, "count": {"type": "integer", "minimum": 1, "maximum": 256}, "x": N, "y": N, "spread": point, "velocity": point, "gravity": N, "turbulence": N, "life": N, "size": N, "color": S, "start": N, "duration": N, "seed": {"type": "integer"}}, ["name"])
    add("cut-paper", {"targets": {"type": "array", "items": S, "maxItems": 512}, "grain": N, "roughness": N, "thickness": N, "fps": N, "jitter": N, "seed": {"type": "integer"}, "children": B, "clear": B})


def execute(project, op):
    from .operations import execute as apply
    kind = op["type"]
    require(isinstance(op.get("seed", 0), int) and 0 <= op.get("seed", 0) < 2 ** 63, "Seed must be a nonnegative 63-bit integer")
    if kind == "layer-depth":
        project.layer(op.get("target"))["depth"] = finite(op["depth"], "depth", 0.05, 1000)
    elif kind == "camera":
        if op.get("clear"):
            project.state.pop("camera", None)
            return
        settings = {k: deepcopy(v) for k, v in op.items() if k not in ("type", "target", "clear")}
        for key in ("from", "to"):
            value = settings.get(key, [0, 0, 1])
            require(isinstance(value, list) and len(value) == 3, "Camera pose is [x,y,zoom] in pixels")
            finite(value[0], "camera x", -1e6, 1e6)
            finite(value[1], "camera y", -1e6, 1e6)
            finite(value[2], "camera zoom", 0.05, 16)
        for key, default, low, high in (("start", 0, 0, 600000), ("duration", 1000, 10, 600000), ("shake", 0, 0, 1000), ("focus", 1, 0.05, 1000), ("focus_to", 1, 0.05, 1000), ("aperture", 0, 0, 64)):
            finite(settings.get(key, default), key, low, high)
        from .timeline import easing_function
        easing_function(settings.get("easing", "ease-in-out"))
        if settings.get("follow"):
            settings["follow"] = project.layer(settings["follow"])["id"]
        project.state["camera"] = settings
    elif kind == "lighting":
        if op.get("clear"):
            project.state.pop("lighting", None)
            return
        settings = {k: deepcopy(v) for k, v in op.items() if k not in ("type", "target", "clear", "shadow")}
        for key, default, low, high in (("ambient", 1, 0, 2), ("vignette", 0, 0, 1), ("exposure", 0, -5, 5), ("saturation", 1, 0, 3)):
            finite(settings.get(key, default), key, low, high)
        lights = settings.get("lights", [])
        require(isinstance(lights, list) and len(lights) <= 16, "At most 16 lights")
        from .render import color
        for light in lights:
            require(isinstance(light, dict) and set(light) <= {"x", "y", "radius", "intensity", "color"}, "Unknown light field")
            for key, default, lo, hi in (("x", 0, -1e6, 1e6), ("y", 0, -1e6, 1e6), ("radius", 200, 1, 1e6), ("intensity", 0.3, 0, 4)):
                finite(light.get(key, default), key, lo, hi)
            color(light.get("color", "white"))
        if "tint" in settings:
            color(settings["tint"])
        if "shadow" in op:
            for layer in list(project.state["layers"]):
                if not layer.get("parent") and layer["type"] != "adjustment":
                    apply(project, {"type": "layer-style", "target": layer["id"], "name": "drop-shadow", "settings": op["shadow"]})
        project.state["lighting"] = settings
    elif kind == "particles":
        count = op.get("count", 32)
        require(isinstance(count, int) and 1 <= count <= 256, "Particle count must be 1–256")
        require(count + len(project.state["layers"]) <= project.limits.max_layers, "Particles exceed layer budget", "resource_limit")
        preset = op.get("preset", "dust")
        defaults = {"dust": ([4, -3], "#eadcb8", 2, 5000), "bubbles": ([0, -25], "#bde9f4", 5, 4000), "sparks": ([30, -90], "#ffd069", 2, 900), "spores": ([2, -10], "#b9cfa0", 3, 6000)}
        require(preset in defaults, "Unknown particle preset")
        velocity, color, size, life = defaults[preset]
        settings = {"velocity": op.get("velocity", velocity), "spread": op.get("spread", [100, 30]), "gravity": op.get("gravity", 180 if preset == "sparks" else 0), "turbulence": op.get("turbulence", 4), "life": op.get("life", life), "start": op.get("start", 0), "duration": op.get("duration", 3000)}
        for key in ("velocity", "spread"):
            require(isinstance(settings[key], list) and len(settings[key]) == 2, f"Particle {key} is [x,y]")
            for value in settings[key]:
                finite(value, key, 0 if key == "spread" else -100000, 100000)
        finite(settings["life"], "particle life", 10, 600000)
        finite(settings["duration"], "particle duration", 10, 600000)
        finite(settings["start"], "particle start", 0, 600000)
        finite(settings["gravity"], "particle gravity", -100000, 100000)
        finite(settings["turbulence"], "particle turbulence", 0, 10000)
        size = finite(op.get("size", size), "particle size", 1, 256)
        rng = np.random.default_rng(op.get("seed", 0))
        for index in range(count):
            apply(project, {"type": "shape", "shape": "ellipse", "name": f"{op['name']}/{index}", "width": max(1, round(size * 2)), "height": max(1, round(size * 2)), "fill": op.get("color", color), "stroke_width": 0})
            layer = project.layer()
            ox = op.get("x", 0) + rng.uniform(-0.5, 0.5) * settings["spread"][0]
            oy = op.get("y", 0) + rng.uniform(-0.5, 0.5) * settings["spread"][1]
            layer.update(x=ox, y=oy, particle={**settings, "origin": [ox, oy], "phase": index / count, "seed": float(rng.uniform(0, math.tau))})
        from .timeline import _timeline
        timeline = _timeline(project)
        timeline["duration"] = max(timeline["duration"], settings["start"] + settings["duration"])
        require(timeline["duration"] <= 600000, "Particle end exceeds 10 minutes")
    else:
        targets = [project.layer(ref) for ref in op.get("targets", [op.get("target")])]
        if op.get("children", True):
            from .design import descendants
            ids = {layer["id"] for layer in targets}
            for layer in targets:
                ids |= descendants(project, layer["id"])
            targets = [layer for layer in project.state["layers"] if layer["id"] in ids and layer["type"] != "group"]
        settings = {"grain": op.get("grain", 0.08), "roughness": op.get("roughness", 0.5), "thickness": op.get("thickness", 2), "seed": op.get("seed", 0)}
        for key, hi in (("grain", 0.5), ("roughness", 1), ("thickness", 20)):
            finite(settings[key], key, 0, hi)
        for index, layer in enumerate(targets):
            if op.get("clear"):
                if "cut_paper" not in layer:
                    continue
                previous = layer.pop("cut_paper").get("previous_shadow")
                if previous is None:
                    layer.get("styles", {}).pop("drop-shadow", None)
                else:
                    layer.setdefault("styles", {})["drop-shadow"] = previous
                continue
            previous = deepcopy(layer.get("cut_paper", {}).get("previous_shadow", layer.get("styles", {}).get("drop-shadow")))
            layer["cut_paper"] = {**settings, "seed": settings["seed"] + index, "previous_shadow": previous}
            layer["depth"] = 1 + index * 0.015
            apply(project, {"type": "layer-style", "target": layer["id"], "name": "drop-shadow", "settings": {"color": "#251c16", "opacity": 0.28, "dx": settings["thickness"], "dy": settings["thickness"] * 1.5, "blur": max(1, settings["thickness"])}})
        if op.get("clear"):
            if not any(layer.get("cut_paper") for layer in project.state["layers"]):
                project.state.pop("stop_motion", None)
        else:
            project.state["stop_motion"] = {"fps": finite(op.get("fps", 12), "stop motion fps", 1, 60), "jitter": finite(op.get("jitter", 0.35), "jitter", 0, 10), "seed": op.get("seed", 0)}


def quantize_time(project, time):
    settings = project.state.get("stop_motion")
    return math.floor(time * settings["fps"] / 1000) * 1000 / settings["fps"] if settings else time


def apply_at(project, time):
    """Mutate only the timeline's render copy, after authored tracks are sampled."""
    from .timeline import easing_function
    camera = project.state.get("camera")
    canvas = project.state["canvas"]
    for layer in project.state["layers"]:
        if "particle" in layer:
            particle = layer["particle"]
            elapsed = time - particle["start"]
            if elapsed < 0 or elapsed >= particle["duration"]:
                layer["visible"] = False
                continue
            age = (elapsed + particle["phase"] * particle["life"]) % particle["life"] / 1000
            phase = age * 1000 / particle["life"]
            layer["x"] = particle["origin"][0] + particle["velocity"][0] * age + math.sin(age * 3 + particle["seed"]) * particle["turbulence"]
            layer["y"] = particle["origin"][1] + particle["velocity"][1] * age + 0.5 * particle["gravity"] * age * age
            layer["opacity"] *= min(1, phase * 10, (1 - phase) * 5)
        caption = layer.get("caption")
        if caption and caption.get("animation") == "typewriter" and "start" in caption:
            fraction = max(0, min(1, (time - caption["start"]) / (caption["end"] - caption["start"]) / 0.8))
            text_layer = project.layer(caption["text_layer"])
            text = caption["text"][:math.ceil(len(caption["text"]) * fraction)]
            text_layer["text"] = text
            if "rich" in text_layer:
                remaining = len(text)
                spans = []
                for span in text_layer["rich"]["spans"]:
                    item = {**span, "text": span["text"][:remaining]}
                    remaining -= len(item["text"])
                    spans.append(item)
                text_layer["rich"]["spans"] = spans
        if "cut_paper" in layer and project.state.get("stop_motion", {}).get("jitter"):
            stop = project.state["stop_motion"]
            tick = math.floor(time * stop["fps"] / 1000)
            seed = int.from_bytes(hashlib.sha256(f"{layer['id']}:{tick}:{stop['seed']}".encode()).digest()[:8], "big")
            jitter = np.random.default_rng(seed).uniform(-stop["jitter"], stop["jitter"], 2)
            layer["x"] += float(jitter[0])
            layer["y"] += float(jitter[1])
    if camera:
        progress = min(1, max(0, (time - camera.get("start", 0)) / camera.get("duration", 1000)))
        eased = easing_function(camera.get("easing", "ease-in-out"))(progress)
        begin, end = camera.get("from", [0, 0, 1]), camera.get("to", [0, 0, 1])
        cx, cy, zoom = [a + (b - a) * eased for a, b in zip(begin, end)]
        if camera.get("follow"):
            target = project.layer(camera["follow"])
            cx += target["x"] + target["width"] / 2 - canvas["width"] / 2
            cy += target["y"] + target["height"] / 2 - canvas["height"] / 2
        shake = camera.get("shake", 0)
        cx += shake * math.sin(time * 0.081 + camera.get("seed", 0))
        cy += shake * math.sin(time * 0.067 + camera.get("seed", 0) + 1)
        focus = camera.get("focus", 1) + (camera.get("focus_to", camera.get("focus", 1)) - camera.get("focus", 1)) * eased
        for layer in project.state["layers"]:
            if layer.get("parent"):
                continue
            depth = layer.get("depth", 1)
            z = max(0.05, 1 + (zoom - 1) / depth)
            layer["x"] = (layer["x"] - canvas["width"] / 2 - cx / depth) * z + canvas["width"] / 2
            layer["y"] = (layer["y"] - canvas["height"] / 2 - cy / depth) * z + canvas["height"] / 2
            layer["width"] = max(1, round(layer["width"] * z))
            layer["height"] = max(1, round(layer["height"] * z))
            layer["auto_size"] = False
            layer["constraints"] = {}
            blur = min(64, abs(depth - focus) * camera.get("aperture", 0))
            if blur:
                layer["effects"].append({"id": "fx_camera_depth_" + layer["id"], "name": "blur", "amount": blur, "enabled": True})
    return project


def paper_image(image, layer):
    settings = layer.get("cut_paper")
    if not settings:
        return image
    rng = np.random.default_rng(settings["seed"])
    pixels = np.asarray(image.convert("RGBA"), dtype=np.float32).copy()
    h, w = pixels.shape[:2]
    grain = rng.normal(0, 255 * settings["grain"], (h, w))
    fibers = rng.normal(0, 255 * settings["grain"] * 0.4, (h, 1))
    pixels[:, :, :3] = np.clip(pixels[:, :, :3] + grain[:, :, None] + fibers[:, :, None], 0, 255)
    # Only erode the silhouette edge. Opaque interiors remain paper, not perforated noise.
    alpha = image.getchannel("A")
    padded = Image.new("L", (w + 2, h + 2))
    padded.paste(alpha, (1, 1))
    eroded = np.asarray(padded.filter(ImageFilter.MinFilter(3)).crop((1, 1, w + 1, h + 1)), dtype=np.float32)
    edge = pixels[:, :, 3] - eroded
    pixels[:, :, 3] -= edge * rng.uniform(0, settings["roughness"], (h, w))
    return Image.fromarray(pixels.astype(np.uint8), "RGBA")


def composite(image, project):
    settings = project.state.get("lighting")
    if not settings:
        return image
    from .render import color
    pixels = np.asarray(image.convert("RGBA"), dtype=np.float32) / 255
    h, w = pixels.shape[:2]
    yy, xx = np.ogrid[:h, :w]
    rgb = pixels[:, :, :3] * settings.get("ambient", 1)
    for light in settings.get("lights", []):
        radius = light.get("radius", 200)
        falloff = np.exp(-((xx - light.get("x", 0)) ** 2 + (yy - light.get("y", 0)) ** 2) / (2 * radius ** 2))
        rgb += np.array(color(light.get("color", "white"))[:3]) / 255 * falloff[:, :, None] * light.get("intensity", 0.3)
    luma = rgb @ np.array([0.2126, 0.7152, 0.0722])
    rgb = luma[:, :, None] + (rgb - luma[:, :, None]) * settings.get("saturation", 1)
    rgb *= 2 ** settings.get("exposure", 0)
    if "tint" in settings:
        rgb *= np.array(color(settings["tint"])[:3]) / 255
    radius = ((xx - w / 2) / max(1, w / 2)) ** 2 + ((yy - h / 2) / max(1, h / 2)) ** 2
    rgb *= np.maximum(0, 1 - settings.get("vignette", 0) * radius / 2)[:, :, None]
    pixels[:, :, :3] = np.clip(rgb, 0, 1)
    return Image.fromarray(np.rint(pixels * 255).astype(np.uint8), "RGBA")
