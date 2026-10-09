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


DITHERS = ("auto", "none", "ordered", "floyd")
# 8x8 Bayer matrix: a fixed pattern in screen space, so ordered dithering never shimmers between frames.
BAYER = (np.array([[0, 32, 8, 40, 2, 34, 10, 42], [48, 16, 56, 24, 50, 18, 58, 26], [12, 44, 4, 36, 14, 46, 6, 38],
                   [60, 28, 52, 20, 62, 30, 54, 22], [3, 35, 11, 43, 1, 33, 9, 41], [51, 19, 59, 27, 49, 17, 57, 25],
                   [15, 47, 7, 39, 13, 45, 5, 37], [63, 31, 55, 23, 61, 29, 53, 21]]) + 0.5) / 64 - 0.5


def has_gradients(images, colors=256):
    """True when the first frames hold many more distinct colors than a GIF palette can: gradients, glows
    or soft shadows, which band when quantized without dithering."""
    sample = images[0].convert("RGB")
    sample = sample.reduce(max(1, math.ceil(math.sqrt(sample.width * sample.height / 40000))))
    return len(sample.getcolors(maxcolors=1 << 24) or ()) > colors * 2


def gif_frame(image, colors=256, palette=None, dither="none"):
    # Reserve index 0 for transparency, with a deterministic alpha threshold.
    if palette is not None and dither == "ordered":
        rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
        height, width = rgb.shape[:2]
        spread = min(64.0, max(10.0, 255 / colors ** (1 / 3) * 0.6))
        rgb = rgb + spread * np.tile(BAYER, (height // 8 + 1, width // 8 + 1))[:height, :width, None]
        indexed = Image.fromarray(np.clip(rgb, 0, 255).astype("uint8")).quantize(palette=palette, dither=Image.Dither.NONE)
    elif palette is not None:
        mode = Image.Dither.FLOYDSTEINBERG if dither == "floyd" else Image.Dither.NONE
        indexed = image.convert("RGB").quantize(palette=palette, dither=mode)
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


def check_dither(dither):
    require(dither in DITHERS, f"dither must be one of {', '.join(DITHERS)}", field="dither")


def gif_bytes(images, duration, loop, colors=256, dither="none"):
    """Encode RGBA frames as an animated GIF. Fully opaque sequences keep each frame and store only
    the changed pixels of the next (lossless); sequences with transparency clear between frames.
    ``dither`` "ordered" (a fixed Bayer pattern) or "floyd" (error diffusion) quantizes every frame to
    one shared palette so gradients band less; "auto" picks ordered when the frames hold gradients."""
    check_colors(colors)
    check_dither(dither)
    if dither == "auto":
        dither = "ordered" if has_gradients(images, colors) else "none"
    opaque = all(image.getchannel("A").getextrema()[0] >= 128 for image in images)
    palette = None
    if colors < 256 or dither != "none":
        # A shared palette keeps unchanged pixels identical between frames, so the frame-difference
        # encoding stays small and dithering is stable from frame to frame.
        sample = images[:: max(1, len(images) // 16)][:16]
        step = max(1, math.ceil(math.sqrt(sample[0].width * sample[0].height / 65536)))
        tiles = [image.convert("RGB").resize((max(1, image.width // step), max(1, image.height // step)),
                                               Image.Resampling.NEAREST) for image in sample]
        # Reserve exact colours for flat artwork before sampling: tiny brand accents must
        # not disappear into averaged neighbours. Bound the histogram for photographic frames.
        exact = set()
        for image in sample:
            histogram = image.convert("RGB").getcolors(colors - 1)
            if histogram is None:
                exact = set()
                break
            exact.update(rgb for _, rgb in histogram)
            if len(exact) >= colors:
                exact = set()
                break
        montage = Image.new("RGB", (tiles[0].width, tiles[0].height * len(tiles)))
        for i, tile in enumerate(tiles):
            montage.paste(tile, (0, i * tiles[0].height))
        palette = montage.quantize(colors=colors - 1, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        if exact:
            entries = sorted(exact)
            entries += [entries[-1]] * (256 - len(entries))
            palette.putpalette([channel for rgb in entries for channel in rgb])
    frames = [gif_frame(image, colors, palette, dither) for image in images]
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


def webp_plays(loop):
    """The WebP ANIM loop count for a Vixl ``loop`` (additional repetitions, 0 = forever): WebP counts
    total plays, as APNG does, while GIF's NETSCAPE count is the repetitions."""
    return loop + 1 if loop else 0


def save_webp(images, durations, loop, **options):
    """Encode an animated WebP. libwebp merges identical neighbours and writes a still image when only
    one frame is left; that file has no duration, so it is rewrapped as a one-frame animation that keeps
    the whole length, as GIF and APNG do."""
    stream = io.BytesIO()
    images[0].save(stream, format="WEBP", save_all=True, append_images=images[1:], duration=durations,
                   loop=webp_plays(loop), **options)
    data = stream.getvalue()
    if data[12:16] == b"VP8X" and data[20] & 0x02:
        return data
    durations = durations if isinstance(durations, (list, tuple)) else [durations] * len(images)
    return _one_frame_webp(data, images[0].size, sum(durations), webp_plays(loop))


def _one_frame_webp(data, size, duration, plays):
    chunks, offset = [], 12
    while offset + 8 <= len(data):
        fourcc, length = data[offset:offset + 4], int.from_bytes(data[offset + 4:offset + 8], "little")
        chunks.append((fourcc, data[offset:offset + 8 + length + (length & 1)]))
        offset += 8 + length + (length & 1)
    image = b"".join(chunk for fourcc, chunk in chunks if fourcc in (b"ALPH", b"VP8 ", b"VP8L"))
    require(image, "WebP encoder wrote no image data", "codec_error")
    alpha = any(fourcc in (b"ALPH", b"VP8L") for fourcc, _ in chunks)

    def u24(value):
        return int(value).to_bytes(3, "little")

    def chunk(fourcc, payload):
        return fourcc + len(payload).to_bytes(4, "little") + payload + b"\0" * (len(payload) & 1)

    w, h = size
    header = chunk(b"VP8X", bytes([0x02 | (0x10 if alpha else 0)]) + b"\0\0\0" + u24(w - 1) + u24(h - 1))
    anim = chunk(b"ANIM", b"\0\0\0\0" + int(plays).to_bytes(2, "little"))
    frame = chunk(b"ANMF", u24(0) + u24(0) + u24(w - 1) + u24(h - 1) + u24(min(duration, 0xFFFFFF)) + b"\x02" + image)
    body = b"WEBP" + header + anim + frame
    return b"RIFF" + len(body).to_bytes(4, "little") + body


def webp_trial(images, durations, loop=0):
    """Bytes of a quick lossy animated WebP of the same frames, or ``None`` when Pillow has no WebP."""
    from PIL import features

    if not images or not features.check("webp"):
        return None
    try:
        return len(save_webp(images, durations, loop, quality=75, method=0))
    except (OSError, ValueError):
        return None


def decoded_frames(data):
    """RGBA frames and durations of an encoded animation."""
    frames, durations = [], []
    with Image.open(io.BytesIO(data)) as image:
        for index in range(getattr(image, "n_frames", 1)):
            image.seek(index)
            frames.append(image.convert("RGBA"))
            durations.append(image.info.get("duration", 100))
    return frames, durations


def alternatives(size, webp=None):
    """What to export instead of a big GIF, as a clause after "or", with the WebP size measured when it can be."""
    measured = webp() if webp is not None else None
    if measured is None:
        return "export MP4 or WebP, which are usually several times smaller"
    if measured < size:
        return (f"export WebP ({measured:,} bytes for these frames, measured: {size / measured:.1f}x smaller) "
                "or MP4")
    return f"export MP4 (a WebP of these frames measured no smaller: {measured:,} bytes)"


def size_warnings(format, data, max_bytes=None, gradients=False, webp=None, label="max_bytes", dither=None, budget=None):
    """Warnings for an encoded animation: a GIF over 1 MB (or ``max_bytes``) and gradient-heavy GIFs steer
    to MP4/WebP. ``webp`` is a callable returning the size of a trial WebP of the same frames, called only
    when a warning needs it. ``budget`` is a size target the export already fitted to (``target_bytes``):
    the generic 1 MB note is left out, since the caller chose the size and a miss is reported where the
    fit happened. ``dither`` is the dither the GIF used, so its advice is not repeated. The export never
    fails over size."""
    warnings = []
    size = len(data)
    if max_bytes is not None and size > max_bytes:
        warnings.append(f"{format.upper()} is {size:,} bytes, over the {label} target of {max_bytes:,}. Lower fps, colors or scale, "
                        "or shorten the range" + (f"; or {alternatives(size, webp)}." if format == "gif" else "."))
    elif format == "gif" and size > GIF_WARN_BYTES and max_bytes is None and budget is None:
        warnings.append(
            f"GIF is {size / 1048576:.1f} MB; ad networks and chat apps often cap GIFs near 150 KB–1 MB. "
            f"Lower fps, colors or scale, shorten the range or pass target_bytes; or {alternatives(size, webp)}."
        )
    if format == "gif" and gradients and size > GIF_WARN_BYTES // 4 and not any("MP4" in w for w in warnings):
        if dither in ("ordered", "floyd"):
            warnings.append(f"This GIF has gradients or soft glows, which band in 256 colors even with dither {dither!r}: "
                            "export MP4 or WebP for clean results.")
        else:
            warnings.append("This GIF has gradients or soft glows, which band in 256 colors: export MP4 or WebP for clean "
                            "results, or pass dither: 'ordered'.")
    return warnings


# Defaults a ``preset`` fills in where the call leaves fps, scale, colors and target_bytes at their defaults.
PRESETS = {
    "chat": {"width": 480, "fps": 15, "target_bytes": 1_000_000},
    "web": {"width": 800, "fps": 20, "target_bytes": 2_000_000},
    "email": {"width": 600, "fps": 10, "colors": 128, "target_bytes": 1_000_000},
}
MAX_FIT_TRIES = 10


def fit_steps(format, fps, colors, quality):
    """(tone, frame step, scale) to try in order: fewer GIF colors (lower WebP quality) first, then a
    lower frame rate, then a smaller size."""
    if format == "gif":
        tones = [colors] + [c for c in (128, 64) if c < colors]
    elif format == "webp":
        tones = [quality] + [q for q in (75, 60, 45) if q < quality]
    else:
        tones = [None]
    steps = [(tone, 1, 1.0) for tone in tones]
    tone = tones[-1]
    steps += [(tone, k, 1.0) for k in (2, 3) if fps / k >= 5]
    step = steps[-1][1]
    steps += [(tone, step, s) for s in (0.75, 0.56, 0.42)]
    return steps[:MAX_FIT_TRIES]


def _subsample(images, durations, step):
    if step == 1:
        return images, durations
    return images[::step], [sum(durations[i:i + step]) for i in range(0, len(durations), step)]


def fit_encode(images, durations, encode, target, steps, fps, tone_name=None, cancelled=None):
    """Encode, measure and step down (``fit_steps``) until the file is at most ``target`` bytes.
    Returns ``(data, frames, durations, chosen)``; when nothing fits, the smallest attempt with
    ``chosen["fits"]`` false."""
    best = None
    for tries, (tone, step, scale) in enumerate(steps, 1):
        require(not (cancelled and cancelled()), "Export cancelled", "cancelled")
        frames, times = _subsample(images, durations, step)
        if scale < 1:
            size = (max(1, round(images[0].width * scale)), max(1, round(images[0].height * scale)))
            frames = [image.resize(size, Image.Resampling.LANCZOS) for image in frames]
        data = encode(frames, times, tone)
        chosen = {"fps": round(fps / step, 3), "scale": scale, "bytes": len(data), "tries": tries, "fits": len(data) <= target}
        if tone_name:
            chosen[tone_name] = tone
        if best is None or len(data) < len(best[0]):
            best = (data, frames, times, chosen)
        if chosen["fits"]:
            return data, frames, times, chosen
    data, frames, times, chosen = best
    return data, frames, times, {**chosen, "tries": len(steps)}


def encoded_frames(data):
    """``(frame_count, durations)`` of an animated GIF/WebP/APNG as written (the encoder merges identical frames)."""
    with Image.open(io.BytesIO(data)) as image:
        count = getattr(image, "n_frames", 1)
        durations = []
        for index in range(count):
            image.seek(index)
            image.load()  # WebP reads a frame's duration only when it decodes the frame.
            durations.append(image.info.get("duration", 0))
    return count, durations


TEXTURE_LOOKS = ("grain", "paper", "film", "risograph", "halftone", "noise")


def textured_layers(project):
    """Names of the layers carrying texture looks or grain/noise effects: per-pixel noise that PNG cannot compress."""
    names = []
    for layer in project.state.get("layers", []):
        effects = [e.get("name") for e in layer.get("effects") or []]
        if any(name in TEXTURE_LOOKS for name in (*layer.get("looks", []), *effects)):
            names.append(layer["name"])
    return names


def still_size_warnings(project, format, size, max_bytes=None):
    """Warnings for an encoded still of ``size`` bytes: over ``max_bytes`` when given, and a PNG above
    1 MB, naming texture looks as the likely cause. The export itself never fails over size."""
    warnings = []
    textured = textured_layers(project)
    hint = (f" Texture looks ({', '.join(textured[:5])}) add noise that PNG cannot compress: lower their amount, "
            "or export JPEG or WebP." if textured and format == "PNG" else "")
    if max_bytes is not None and size > max_bytes:
        warnings.append(f"{format} is {size:,} bytes, over the max_bytes budget of {max_bytes:,}." + hint
                        + ("" if format == "PNG" else " Lower quality or scale."))
    elif format == "PNG" and size > GIF_WARN_BYTES:
        warnings.append(f"PNG is {size / 1048576:.1f} MB; messaging apps often recompress or reject images this large."
                        + (hint or " Export JPEG or WebP, or reduce the canvas size."))
    return warnings


def sheet_cells(entries):
    """The distinct frames of a sequence in order of first use: one sprite-sheet cell each."""
    return list({frame["name"]: frame for frame, _ in entries}.values())


def animation_bytes(
    project, *, format="gif", scale=1, columns=None, sampling="nearest", colors=256, animation=None, quality=90, dither="auto"
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
    check_dither(dither)
    require(dither == "auto" or format == "gif", "dither applies to GIF export", field="dither")
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
            stream.write(gif_bytes(images, durations, loop, colors, dither))
        elif format == "webp":
            # Crisp (nearest) pixel art is stored losslessly; smooth renders use `quality`.
            options = {"lossless": True} if sampling == "nearest" else {"quality": quality, "method": 4}
            stream.write(save_webp(images, durations, loop, **options))
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


def export_video(project, path, *, format, scale, sampling, quality, animation=None, overwrite=False):
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

    result = _video(path, frames(), Fraction(1000, tick), format, quality, overwrite, sum(counts), (w, h))
    return {**result, "fps": float(result["fps"])}


def export_animation(
    project, path, *, format=None, scale=1, columns=None, sampling="nearest", colors=256, animation=None, quality=90,
    overwrite=False, dither="auto", max_bytes=None,
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
    require(overwrite or not any(p.exists() for p in destinations), "Animation output already exists; pass overwrite=True")
    if format in VIDEO:
        require(colors == 256, "colors applies to GIF export", field="colors")
        require(columns is None, "Columns apply only to sprite sheets")
        result = export_video(project, path, format=format, scale=scale, sampling=sampling, quality=quality,
                              animation=animation, overwrite=overwrite)
        return {**result, **({"animation": animation} if animation is not None else {})}
    data, metadata = animation_bytes(
        project, format=format, scale=scale, columns=columns, sampling=sampling, colors=colors,
        animation=animation, quality=quality, dither=dither,
    )
    # Create only after all rendering succeeds. Refuse concurrent clobbers as well.
    with path.open("wb" if overwrite else "xb") as stream:
        stream.write(data)
    if metadata is not None:
        with destinations[1].open("w" if overwrite else "x", encoding="utf-8") as stream:
            json.dump(metadata, stream, indent=2)
    from .animation_sets import resolve_sequence

    entries, _ = resolve_sequence(project.state["animation"], animation)
    # Report what was written: the sheet's own size, and the frames left after the encoder merged repeats.
    size = [metadata["width"], metadata["height"]] if metadata is not None else list(scaled_size(entries[0][0]["state"]["canvas"], scale))
    written = {}
    if format != "sheet":
        count, _ = encoded_frames(data)
        written = {"frames": count, **({"rendered_frames": len(entries)} if count != len(entries) else {})}
    gradients = format == "gif" and has_gradients([render_frame(project, entries[0][0]["name"], scale, sampling)], colors)
    return {
        "output": str(path),
        "format": format,
        "size": size,
        **({"frame_size": list(scaled_size(entries[0][0]["state"]["canvas"], scale))} if metadata is not None else {}),
        **written,
        "bytes": len(data),
        **({"animation": animation} if animation is not None else {}),
        **({"metadata": str(destinations[1])} if metadata is not None else {}),
        **({"warnings": warnings} if (warnings := size_warnings(
            format, data, max_bytes, gradients, webp=lambda: webp_trial(*decoded_frames(data)),
            dither=("ordered" if gradients else "none") if dither == "auto" else dither)) else {}),
    }
