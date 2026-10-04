"""Named animation snapshots and bounded GIF/APNG/sprite-sheet exports (pixel-crisp or smooth)."""

from copy import copy, deepcopy
import io
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

from .errors import require
from .model import finite

ANIMATION_TYPES = ("frame-save", "frame-apply", "frame-delete", "animation-set")
MAX_FRAMES = 256
SAMPLING = ("nearest", "smooth")
GIF_WARN_BYTES = 1024 * 1024


def frame_project(project, frame):
    candidate = copy(project)
    candidate.state = deepcopy(frame["state"])
    candidate._cache = {}
    return candidate


def validate_animation(project, state):
    if "animation" not in state:
        return
    from .validation import check_state
    from .render import resolve_layout

    animation = state["animation"]
    require(
        isinstance(animation, dict) and set(animation) <= {"frames", "loop"}, "Invalid animation settings"
    )
    frames = animation.get("frames", [])
    require(isinstance(frames, list) and len(frames) <= MAX_FRAMES, "Animation supports at most 256 frames")
    loop = animation.get("loop", 0)
    require(
        isinstance(loop, int) and not isinstance(loop, bool) and 0 <= loop <= 65535, "Loop must be 0–65535"
    )
    names, sizes = set(), set()
    total = 0
    for frame in frames:
        require(
            isinstance(frame, dict) and set(frame) == {"name", "duration", "state"}, "Invalid animation frame"
        )
        from .design import named

        named(frame["name"])
        require(frame["name"] not in names, "Duplicate animation frame")
        names.add(frame["name"])
        duration = frame["duration"]
        require(
            isinstance(duration, int) and 10 <= duration <= 60000 and duration % 10 == 0,
            "Frame duration must be 10–60000 ms, in multiples of 10",
        )
        snapshot = frame["state"]
        require(
            isinstance(snapshot, dict) and "animation" not in snapshot,
            "Nested animation frames are forbidden",
        )
        check_state(project, snapshot)
        require(
            not any(layer.get("linked") for layer in snapshot["layers"]),
            "Embed linked images before saving frames",
        )
        w, h = snapshot["canvas"]["width"], snapshot["canvas"]["height"]
        sizes.add((w, h))
        total += w * h
        require(
            total <= project.limits.max_pixels,
            f"Animation frames exceed the pixel budget (frames × canvas pixels ≤ {project.limits.max_pixels:,}); "
            "save fewer frames, use a smaller canvas or animate with the keyframe timeline",
            "resource_limit",
        )
        resolve_layout(frame_project(project, frame))
    require(len(sizes) <= 1, "All animation frames must have the same canvas size")


def execute_animation(project, op):
    animation = project.state.setdefault("animation", {"frames": [], "loop": 0})
    frames = animation["frames"]
    kind = op["type"]
    if kind == "animation-set":
        if "loop" in op:
            animation["loop"] = op["loop"]
        if "order" in op:
            require(
                len(op["order"]) == len(frames) and set(op["order"]) == {f["name"] for f in frames},
                "Order must list every frame exactly once",
            )
            by_name = {f["name"]: f for f in frames}
            animation["frames"] = [by_name[name] for name in op["order"]]
        return
    from .design import named

    name = named(op["name"])
    existing = next((f for f in frames if f["name"] == name), None)
    if kind == "frame-save":
        require(
            existing is not None or len(frames) < MAX_FRAMES,
            "Animation frame limit reached",
            "resource_limit",
        )
        snapshot = deepcopy({k: v for k, v in project.state.items() if k != "animation"})
        frame = {
            "name": name,
            "duration": op.get("duration", existing["duration"] if existing else 100),
            "state": snapshot,
        }
        if existing:
            frames[frames.index(existing)] = frame
        else:
            frames.append(frame)
        validate_animation(project, project.state)
    else:
        require(existing is not None, f"Unknown animation frame: {name}")
        if kind == "frame-delete":
            frames.remove(existing)
        else:
            project.state = deepcopy(existing["state"])
            project.state["animation"] = animation


def inspect_animation(project):
    animation = project.state.get("animation", {"frames": [], "loop": 0})
    return {
        "loop": animation.get("loop", 0),
        "total_duration": sum(f["duration"] for f in animation["frames"]),
        "frames": [
            {
                "name": f["name"],
                "duration": f["duration"],
                "canvas": f["state"]["canvas"],
                "layer_count": len(f["state"]["layers"]),
            }
            for f in animation["frames"]
        ],
    }


def check_scale(scale, sampling):
    require(sampling in SAMPLING, "Sampling must be nearest or smooth", field="sampling")
    if sampling == "nearest":
        require(
            isinstance(scale, int) and not isinstance(scale, bool) and 1 <= scale <= 32,
            "Nearest-neighbor scale must be an integer 1–32; use sampling='smooth' for fractional scales",
            field="scale",
        )
    else:
        finite(scale, "scale", 0.05, 32)


def scaled_size(canvas, scale):
    return max(1, round(canvas["width"] * scale)), max(1, round(canvas["height"] * scale))


def render_frame(project, name, scale=1, sampling="nearest"):
    """Render a saved frame. Nearest enlarges pixel by pixel; smooth re-renders at the target size."""
    check_scale(scale, sampling)
    frame = next((f for f in project.state.get("animation", {}).get("frames", []) if f["name"] == name), None)
    require(frame is not None, f"Unknown animation frame: {name}")
    project.limits.size(*scaled_size(frame["state"]["canvas"], scale))
    from .timeline import render_scaled

    return render_scaled(frame_project(project, frame), scale, sampling)


def gif_frame(image, colors=256, palette=None):
    # Reserve index 0 for transparency, with a deterministic alpha threshold.
    if palette is not None:
        indexed = image.convert("RGB").quantize(palette=palette, dither=Image.Dither.NONE)
    else:
        indexed = image.convert("RGB").quantize(
            colors=colors - 1, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE
        )
    pixels = np.asarray(indexed, dtype=np.uint16) + 1
    pixels[np.asarray(image.getchannel("A")) < 128] = 0
    result = Image.fromarray(pixels.astype("uint8")).convert("P")
    result.putpalette([0, 0, 0] + indexed.getpalette()[:765])
    result.info["transparency"] = 0
    return result


def check_colors(colors):
    require(isinstance(colors, int) and not isinstance(colors, bool) and 2 <= colors <= 256, "GIF colors must be an integer 2–256", field="colors")


def gif_bytes(images, duration, loop, colors=256):
    """Encode RGBA frames as an animated GIF. Fully opaque sequences keep each frame and store only
    the changed pixels of the next (lossless); sequences with transparency clear between frames."""
    check_colors(colors)
    opaque = all(image.getchannel("A").getextrema()[0] >= 128 for image in images)
    palette = None
    if colors < 256:
        # A reduced palette is shared by every frame, so unchanged pixels stay identical between
        # frames and the frame-difference encoding stays small.
        sample = images[:: max(1, len(images) // 16)][:16]
        step = max(1, math.ceil(math.sqrt(sample[0].width * sample[0].height / 65536)))
        tiles = [image.convert("RGB").reduce(step) for image in sample]
        montage = Image.new("RGB", (tiles[0].width, tiles[0].height * len(tiles)))
        for i, tile in enumerate(tiles):
            montage.paste(tile, (0, i * tiles[0].height))
        palette = montage.quantize(colors=colors - 1, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    frames = [gif_frame(image, colors, palette) for image in images]
    stream = io.BytesIO()
    frames[0].save(
        stream,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=duration,
        loop=loop,
        disposal=1 if opaque else 2,
        transparency=0,
        optimize=opaque,
    )
    return stream.getvalue()


def size_warnings(format, data):
    if format == "gif" and len(data) > GIF_WARN_BYTES:
        return [
            f"GIF is {len(data) / 1048576:.1f} MB; ad networks and chat apps often cap GIFs near 150 KB–1 MB. "
            "Lower fps, colors or scale, shorten the range, or export WebP/MP4."
        ]
    return []


def animation_bytes(project, *, format="gif", scale=1, columns=None, sampling="nearest", colors=256):
    require(format in ("gif", "apng", "sheet"), "Animation format must be gif, apng or sheet")
    validate_animation(project, project.state)
    animation = project.state.get("animation", {})
    frames = animation.get("frames", [])
    require(frames, "Save at least one animation frame")
    check_scale(scale, sampling)
    require(colors == 256 or format == "gif", "colors applies to GIF export", field="colors")
    check_colors(colors)
    w, h = scaled_size(frames[0]["state"]["canvas"], scale)
    project.limits.size(w, h)
    require(
        w * h * len(frames) <= project.limits.max_pixels,
        "Animation export exceeds pixel budget",
        "resource_limit",
    )
    require(columns is None or format == "sheet", "Columns apply only to sprite sheets")
    stream = io.BytesIO()
    metadata = None
    durations = [f["duration"] for f in frames]
    if format == "sheet":
        columns = columns if columns is not None else math.ceil(math.sqrt(len(frames)))
        require(isinstance(columns, int) and 1 <= columns <= len(frames), "Invalid sprite-sheet column count")
        rows = math.ceil(len(frames) / columns)
        project.limits.size(w * columns, h * rows)
        image = Image.new("RGBA", (w * columns, h * rows))
        metadata = {
            "width": image.width,
            "height": image.height,
            "loop": animation.get("loop", 0),
            "frames": [],
        }
        for i, frame in enumerate(frames):
            x, y = i % columns * w, i // columns * h
            image.paste(render_frame(project, frame["name"], scale, sampling), (x, y))
            metadata["frames"].append(
                {
                    "name": frame["name"],
                    "duration": frame["duration"],
                    "x": x,
                    "y": y,
                    "width": w,
                    "height": h,
                }
            )
        image.save(stream, format="PNG")
    else:
        images = [render_frame(project, f["name"], scale, sampling) for f in frames]
        loop = animation.get("loop", 0)
        if format == "gif":
            stream.write(gif_bytes(images, durations, loop, colors))
        else:
            images[0].save(
                stream,
                format="PNG",
                save_all=True,
                append_images=images[1:],
                duration=durations,
                loop=loop + 1 if loop else 0,
                disposal=0,
                blend=0,
            )
    return stream.getvalue(), metadata


def export_animation(project, path, *, format=None, scale=1, columns=None, sampling="nearest", colors=256):
    path = Path(path)
    format = format or (".gif" == path.suffix.lower() and "gif") or "apng"
    require(
        path.suffix.lower() in ((".gif",) if format == "gif" else (".png", ".apng")),
        "Use a GIF or PNG/APNG output filename",
    )
    destinations = [path] + ([path.with_suffix(".json")] if format == "sheet" else [])
    require(not any(p.exists() for p in destinations), "Animation output already exists")
    data, metadata = animation_bytes(project, format=format, scale=scale, columns=columns, sampling=sampling, colors=colors)
    # Create only after all rendering succeeds. Refuse concurrent clobbers as well.
    with path.open("xb") as stream:
        stream.write(data)
    if metadata is not None:
        with destinations[1].open("x", encoding="utf-8") as stream:
            json.dump(metadata, stream, indent=2)
    return {
        "output": str(path),
        "format": format,
        "size": list(scaled_size(project.state["animation"]["frames"][0]["state"]["canvas"], scale)),
        "bytes": len(data),
        **({"metadata": str(destinations[1])} if metadata is not None else {}),
        **({"warnings": warnings} if (warnings := size_warnings(format, data)) else {}),
    }
