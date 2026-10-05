"""Named animation snapshots and bounded GIF/APNG/WebP/MP4/sprite-sheet exports (pixel-crisp or smooth)."""

from copy import copy, deepcopy
from fractions import Fraction
import io
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

from .errors import require
from .model import finite

ANIMATION_TYPES = ("frame-save", "frame-apply", "frame-delete", "animation-set", "frames-edit")
MAX_FRAMES = 256
SAMPLING = ("nearest", "smooth")
VIDEO = ("mp4", "webm")
GIF_WARN_BYTES = 1024 * 1024


def frame_project(project, frame):
    candidate = copy(project)
    candidate.state = deepcopy(frame["state"])
    from .render import LayerCache

    candidate._cache = LayerCache()
    return candidate


def validate_animation(project, state):
    if "animation" not in state:
        return
    from .validation import check_state
    from .render import resolve_layout

    animation = state["animation"]
    require(
        isinstance(animation, dict) and set(animation) <= {"frames", "loop", "animations"},
        "Invalid animation settings",
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
    from .animation_sets import validate_named

    validate_named(animation, names)


def execute_animation(project, op):
    animation = project.state.setdefault("animation", {"frames": [], "loop": 0})
    frames = animation["frames"]
    kind = op["type"]
    if kind == "frames-edit":
        from .animation_sets import frames_edit

        return frames_edit(project, op)
    if kind == "animation-set":
        if "name" in op:
            from .animation_sets import set_named

            return set_named(animation, op)
        require(
            not any(key in op for key in ("duration", "durations", "delete")),
            "duration, durations and delete apply to a named animation; pass name",
        )
        if "loop" in op:
            animation["loop"] = op["loop"]
        if "order" in op:
            require(
                len(op["order"]) == len(frames) and set(op["order"]) == {f["name"] for f in frames},
                "Order must list every saved frame exactly once; to play or export a subset, define a named "
                "animation with animation-set name=... order=[...]",
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
            from .animation_sets import used_by

            users = used_by(animation, name)
            require(
                not users,
                f"Frame {name} is used by animation(s) {', '.join(users)}; redefine them with animation-set "
                "(or delete them) first",
            )
            frames.remove(existing)
        else:
            project.state = deepcopy(existing["state"])
            project.state["animation"] = animation


def inspect_animation(project):
    animation = project.state.get("animation", {"frames": [], "loop": 0})
    from .animation_sets import summaries

    named = summaries(animation)
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
        **({"animations": [{"name": name, **info} for name, info in named.items()]} if named else {}),
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


def sheet_cells(entries):
    """The distinct frames of a sequence in order of first use: one sprite-sheet cell each."""
    return list({frame["name"]: frame for frame, _ in entries}.values())


def animation_bytes(
    project, *, format="gif", scale=1, columns=None, sampling="nearest", colors=256, animation=None, quality=90
):
    """Encode saved frames. ``animation`` selects a named animation (its frames, order, timing and
    loop); omitted, every saved frame plays in saved order. MP4/WebM stream to a file (export_animation)."""
    require(
        format in ("gif", "apng", "webp", "sheet"),
        "Animation format must be gif, apng, webp or sheet (mp4 and webm are written to files)",
    )
    validate_animation(project, project.state)
    state = project.state.get("animation", {})
    require(state.get("frames"), "Save at least one animation frame")
    from .animation_sets import resolve_sequence, summaries

    entries, loop = resolve_sequence(state, animation)
    check_scale(scale, sampling)
    require(colors == 256 or format == "gif", "colors applies to GIF export", field="colors")
    check_colors(colors)
    require(
        isinstance(quality, int) and not isinstance(quality, bool) and 1 <= quality <= 100,
        "quality must be an integer 1–100",
        field="quality",
    )
    w, h = scaled_size(entries[0][0]["state"]["canvas"], scale)
    project.limits.size(w, h)
    cells = sheet_cells(entries) if format == "sheet" else entries
    require(
        w * h * len(cells) <= project.limits.max_pixels,
        "Animation export exceeds pixel budget",
        "resource_limit",
    )
    require(columns is None or format == "sheet", "Columns apply only to sprite sheets")
    stream = io.BytesIO()
    metadata = None
    durations = [duration for _, duration in entries]
    rendered = {}

    def image_of(frame):
        # A frame that repeats in the sequence (a ping-pong walk cycle) is rendered once.
        if frame["name"] not in rendered:
            rendered[frame["name"]] = render_frame(project, frame["name"], scale, sampling)
        return rendered[frame["name"]]

    if format == "sheet":
        columns = columns if columns is not None else math.ceil(math.sqrt(len(cells)))
        require(isinstance(columns, int) and 1 <= columns <= len(cells), "Invalid sprite-sheet column count")
        rows = math.ceil(len(cells) / columns)
        project.limits.size(w * columns, h * rows)
        image = Image.new("RGBA", (w * columns, h * rows))
        metadata = {
            "width": image.width,
            "height": image.height,
            "loop": loop,
            "frames": [],
        }
        for i, frame in enumerate(cells):
            x, y = i % columns * w, i // columns * h
            image.paste(image_of(frame), (x, y))
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
        # Frames carry their own saved durations; `animations` says how to play them as named cycles.
        named = summaries(state)
        if animation is not None:
            metadata["animation"] = animation
            named = {animation: named[animation]}
        if named:
            metadata["animations"] = named
        image.save(stream, format="PNG")
    else:
        images = [image_of(frame) for frame, _ in entries]
        if format == "gif":
            stream.write(gif_bytes(images, durations, loop, colors))
        elif format == "webp":
            # Crisp (nearest) pixel art is stored losslessly; smooth renders use `quality`.
            options = {"lossless": True} if sampling == "nearest" else {"quality": quality, "method": 4}
            images[0].save(
                stream,
                format="WEBP",
                save_all=True,
                append_images=images[1:],
                duration=durations,
                loop=loop + 1 if loop else 0,
                **options,
            )
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


def export_video(project, path, *, format, scale, sampling, quality, animation=None):
    """Stream an animation to MP4/WebM (needs ffmpeg). Video has a constant frame rate, so frames are
    repeated on a tick of the greatest common divisor of their durations."""
    from functools import reduce

    from .animation_sets import resolve_sequence
    from .timeline import MAX_STREAMED_FRAMES, _video

    validate_animation(project, project.state)
    state = project.state.get("animation", {})
    require(state.get("frames"), "Save at least one animation frame")
    entries, _ = resolve_sequence(state, animation)
    check_scale(scale, sampling)
    require(
        isinstance(quality, int) and not isinstance(quality, bool) and 1 <= quality <= 100,
        "quality must be an integer 1–100",
        field="quality",
    )
    w, h = scaled_size(entries[0][0]["state"]["canvas"], scale)
    project.limits.size(w, h)
    require(
        w * h * len(entries) <= project.limits.max_pixels,
        "Animation export exceeds pixel budget",
        "resource_limit",
    )
    tick = reduce(math.gcd, (duration for _, duration in entries))
    counts = [duration // tick for _, duration in entries]
    require(
        sum(counts) <= MAX_STREAMED_FRAMES,
        f"Video would need {sum(counts):,} frames; shorten the animation or use gif, apng or webp",
        "resource_limit",
    )
    repeats = {}
    for frame, _ in entries:
        repeats[frame["name"]] = repeats.get(frame["name"], 0) + 1
    cache = {}

    def frames():
        for (frame, _), count in zip(entries, counts):
            name = frame["name"]
            image = cache.get(name) or render_frame(project, name, scale, sampling)
            if repeats[name] > 1:
                cache[name] = image
            for _ in range(count):
                yield image

    result = _video(path, frames(), Fraction(1000, tick), format, quality, False, sum(counts), (w, h))
    return {**result, "fps": float(result["fps"])}


def export_animation(
    project, path, *, format=None, scale=1, columns=None, sampling="nearest", colors=256, animation=None, quality=90
):
    path = Path(path)
    suffix = path.suffix.lower()
    format = format or {".gif": "gif", ".webp": "webp", ".mp4": "mp4", ".webm": "webm"}.get(suffix, "apng")
    require(
        format in ("gif", "apng", "webp", "sheet", *VIDEO),
        "Animation format must be gif, apng, webp, mp4, webm or sheet",
        field="format",
    )
    expected = {"gif": (".gif",), "webp": (".webp",), "mp4": (".mp4",), "webm": (".webm",)}.get(
        format, (".png", ".apng")
    )
    require(
        suffix in expected,
        f"Use a {' or '.join(e.upper().lstrip('.') for e in expected)} output filename for {format}",
        field="path",
    )
    destinations = [path] + ([path.with_suffix(".json")] if format == "sheet" else [])
    require(not any(p.exists() for p in destinations), "Animation output already exists")
    if format in VIDEO:
        require(colors == 256, "colors applies to GIF export", field="colors")
        require(columns is None, "Columns apply only to sprite sheets")
        result = export_video(project, path, format=format, scale=scale, sampling=sampling, quality=quality, animation=animation)
        return {**result, **({"animation": animation} if animation is not None else {})}
    data, metadata = animation_bytes(
        project, format=format, scale=scale, columns=columns, sampling=sampling, colors=colors,
        animation=animation, quality=quality,
    )
    # Create only after all rendering succeeds. Refuse concurrent clobbers as well.
    with path.open("xb") as stream:
        stream.write(data)
    if metadata is not None:
        with destinations[1].open("x", encoding="utf-8") as stream:
            json.dump(metadata, stream, indent=2)
    from .animation_sets import resolve_sequence

    entries, _ = resolve_sequence(project.state["animation"], animation)
    return {
        "output": str(path),
        "format": format,
        "size": list(scaled_size(entries[0][0]["state"]["canvas"], scale)),
        "bytes": len(data),
        **({"animation": animation} if animation is not None else {}),
        **({"metadata": str(destinations[1])} if metadata is not None else {}),
        **({"warnings": warnings} if (warnings := size_warnings(format, data)) else {}),
    }
