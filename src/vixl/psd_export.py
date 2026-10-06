"""Layered Photoshop (PSD) export for designer handoff.

Every Vixl layer becomes one 8-bit RGBA pixel layer, rendered with its effects, styles, masks and
clipping in canvas space and cropped to what it draws. Names, opacity, visibility and blend modes
carry over, groups become PSD layer groups (folder records with section dividers), and the file
carries the flattened composite that ``render`` produces. A group that Vixl transforms or filters
as a whole (rotation, flip, skew, resize, effects, styles, clip, mask, repeat, distortion) is
written as one pixel layer, because PSD groups cannot transform their contents. Text, shapes and
paths are pixels, not editable type or vectors; adjustment layers are baked into the composite
only. Channel data is PackBits (RLE) compressed.

Format reference: Adobe Photoshop File Format Specification, version 1 (PSD) files.
"""

import io
import struct

import numpy as np

from .errors import require

BLEND_KEYS = {
    "normal": b"norm", "multiply": b"mul ", "screen": b"scrn", "overlay": b"over", "darken": b"dark",
    "lighten": b"lite", "difference": b"diff", "add": b"lddg", "subtract": b"fsub",
}
MAX_SIDE = 30000  # The PSD (version 1) limit on each canvas side.
GROUP_END = "</Layer group>"


# ---------------------------------------------------------------------------------------------
# Encoding


def packbits(row):
    """PackBits-encode one row of bytes (``bytes`` or uint8 array)."""
    data = np.frombuffer(bytes(row), dtype=np.uint8)
    n = len(data)
    if n == 0:
        return b""
    starts = np.flatnonzero(np.concatenate(([True], data[1:] != data[:-1])))
    lengths = np.diff(np.concatenate((starts, [n])))
    out = bytearray()
    if len(starts) > n // 2:
        # Mostly literal (photographic) rows: literal packets only, without a per-byte loop.
        raw = data.tobytes()
        for i in range(0, n, 128):
            chunk = raw[i:i + 128]
            out.append(len(chunk) - 1)
            out += chunk
        return bytes(out)
    literal = bytearray()

    def flush():
        for i in range(0, len(literal), 128):
            chunk = literal[i:i + 128]
            out.append(len(chunk) - 1)
            out.extend(chunk)
        literal.clear()

    raw = data.tobytes()
    for start, length in zip(starts.tolist(), lengths.tolist()):
        if length < 3:
            literal += raw[start:start + length]
            continue
        flush()
        value = raw[start]
        while length > 0:
            count = min(length, 128)
            if count < 3:
                literal += bytes([value]) * count
            else:
                out.append(257 - count)  # -(count - 1) as an unsigned byte
                out.append(value)
            length -= count
    flush()
    return bytes(out)


def rle_channel(plane):
    """``(row byte counts, packed rows)`` of one 2-D uint8 plane."""
    rows = [packbits(row) for row in plane]
    return [len(r) for r in rows], b"".join(rows)


def encoded_channel(plane):
    """One layer channel's data: compression 1 (RLE), the per-row u16 byte counts, then the rows."""
    if plane.size == 0:
        return struct.pack(">H", 0)
    counts, data = rle_channel(plane)
    return struct.pack(">H", 1) + struct.pack(f">{len(counts)}H", *counts) + data


def pascal(name, multiple):
    """A Pascal string of at most 255 bytes, padded so its whole length is a multiple of ``multiple``."""
    raw = name.encode("mac_roman", "replace")[:255]
    data = bytes([len(raw)]) + raw
    return data + b"\0" * (-len(data) % multiple)


def block(key, data):
    """An additional layer information block ('8BIM' signature, key, even-padded length)."""
    data += b"\0" * (len(data) % 2)
    return b"8BIM" + key + struct.pack(">I", len(data)) + data


def unicode_name(name):
    text = name.encode("utf-16-be")
    return block(b"luni", struct.pack(">I", len(text) // 2) + text)


# ---------------------------------------------------------------------------------------------
# Layer tree


class Record:
    def __init__(self, name, *, pixels=None, box=(0, 0, 0, 0), opacity=1.0, blend="normal", visible=True,
                 section=None):
        self.name, self.pixels, self.box = name, pixels, box
        self.opacity, self.blend, self.visible, self.section = opacity, blend, visible, section


def flat_group(layer):
    """Whether Vixl transforms or filters this group as a whole (so it exports as one pixel layer)."""
    from .affine import precise

    return bool(
        precise(layer) or layer.get("rotation", 0) % 360 or layer.get("flip_x") or layer.get("flip_y")
        or any(e.get("enabled", True) for e in layer.get("effects") or []) or layer.get("styles") or layer.get("clip")
        or (layer.get("mask") and layer["mask"].get("enabled", True)) or layer.get("repeat") or layer.get("distort")
        or layer.get("cut_paper")
        or abs(layer["width"] - layer.get("content_width", layer["width"])) > 1e-6
        or abs(layer["height"] - layer.get("content_height", layer["height"])) > 1e-6
    )


def _pixels(project, layer, index, bounds, ancestors):
    """The layer drawn on its own through its (PSD group) ancestors onto the canvas, at full opacity
    and shown, so the PSD record carries opacity and visibility instead. ``(RGBA array, box)``."""
    from .render import layer_canvas_surface

    view = dict(index)
    view[layer["id"]] = {**layer, "opacity": 1, "visible": True}
    for ident in ancestors:
        view[ident] = {**index[ident], "opacity": 1, "visible": True}
    surface = layer_canvas_surface(project, view[layer["id"]], bounds, view)
    box = surface.getchannel("A").getbbox()
    if not box:
        return np.zeros((0, 0, 4), np.uint8), (0, 0, 0, 0)
    return np.asarray(surface.crop(box)), box


def build(project, report):
    from .render import child_index, color, resolve_layout, resolved_layers
    from .design import resolve_color

    layers = resolved_layers(project)
    index = {layer["id"]: layer for layer in layers}
    bounds = resolve_layout(project, layers=layers)
    children = child_index(layers)
    c = project.state["canvas"]
    records = []  # bottom to top
    texts, flattened, skipped = [], [], []
    background = color(resolve_color(c["background"], project.state))
    if background[3]:
        pixels = np.empty((c["height"], c["width"], 4), np.uint8)
        pixels[:] = background
        records.append(Record("Background", pixels=pixels, box=(0, 0, c["width"], c["height"])))

    def walk(parent, ancestors):
        for layer in children.get(parent, []):
            name = layer.get("name") or layer["id"]
            if layer["type"] == "adjustment":
                skipped.append(name)
                continue
            common = dict(opacity=layer.get("opacity", 1), blend=layer.get("blend", "normal"),
                          visible=layer.get("visible", True))
            if layer["type"] == "group" and children.get(layer["id"]) and not flat_group(layer):
                records.append(Record(GROUP_END, section=3, visible=common["visible"]))
                walk(layer["id"], [*ancestors, layer["id"]])
                records.append(Record(name, section=1, **common))
                continue
            if layer["type"] == "group" and children.get(layer["id"]):
                flattened.append(name)
            if layer["type"] == "text":
                texts.append(name)
            pixels, box = _pixels(project, layer, index, bounds, ancestors)
            records.append(Record(name, pixels=pixels, box=box, **common))

    walk(None, [])
    report.update(layers=sum(1 for r in records if r.section is None),
                  groups=sum(1 for r in records if r.section == 1))
    warnings = report.setdefault("warnings", [])
    if texts:
        report["text_as_pixels"] = texts
        warnings.append(f"{len(texts)} text layer(s) are pixel layers in the PSD, not editable type: "
                        + ", ".join(texts[:8]) + (" ..." if len(texts) > 8 else ""))
    if flattened:
        report["flattened_groups"] = flattened
        warnings.append("group(s) transformed or filtered as a whole are single pixel layers: " + ", ".join(flattened[:8]))
    if skipped:
        report["adjustments_in_composite_only"] = skipped
        warnings.append("adjustment layer(s) are applied in the composite image only: " + ", ".join(skipped[:8]))
    return records


# ---------------------------------------------------------------------------------------------
# Writer


def _record_bytes(record):
    top, left = record.box[1], record.box[0]
    bottom, right = record.box[3], record.box[2]
    channels = []
    if record.pixels is not None and record.pixels.size:
        planes = {-1: record.pixels[:, :, 3], 0: record.pixels[:, :, 0], 1: record.pixels[:, :, 1], 2: record.pixels[:, :, 2]}
    else:
        top = left = bottom = right = 0
        planes = {-1: np.zeros((0, 0), np.uint8), 0: np.zeros((0, 0), np.uint8), 1: np.zeros((0, 0), np.uint8),
                  2: np.zeros((0, 0), np.uint8)}
    for ident, plane in planes.items():
        channels.append((ident, encoded_channel(np.ascontiguousarray(plane))))
    head = struct.pack(">iiiiH", top, left, bottom, right, len(channels))
    for ident, data in channels:
        head += struct.pack(">hI", ident, len(data))
    key = BLEND_KEYS.get(record.blend, b"norm")
    flags = 0 if record.visible else 2
    if record.section is not None:
        flags |= 8 | 16  # pixel data irrelevant to appearance (folder and divider records)
    head += b"8BIM" + key + struct.pack(">BBBB", max(0, min(255, round(record.opacity * 255))), 0, flags, 0)
    extra = struct.pack(">I", 0) + struct.pack(">I", 0) + pascal(record.name, 4) + unicode_name(record.name)
    if record.section is not None:
        extra += block(b"lsct", struct.pack(">I", record.section) + (b"8BIM" + key if record.section == 1 else b""))
    head += struct.pack(">I", len(extra)) + extra
    return head, b"".join(data for _, data in channels)


def write(records, composite, dpi=72):
    """PSD bytes for ``records`` (bottom to top) and the RGBA ``composite`` image."""
    width, height = composite.size
    out = io.BytesIO()
    out.write(b"8BPS" + struct.pack(">H", 1) + b"\0" * 6 + struct.pack(">HIIHH", 4, height, width, 8, 3))
    out.write(struct.pack(">I", 0))  # colour mode data
    fixed = round(dpi * 65536)
    resolution = struct.pack(">IHHIHH", fixed, 1, 1, fixed, 1, 1)
    resources = b"8BIM" + struct.pack(">H", 1005) + b"\0\0" + struct.pack(">I", len(resolution)) + resolution
    out.write(struct.pack(">I", len(resources)) + resources)
    heads, datas = [], []
    for record in records:
        head, data = _record_bytes(record)
        heads.append(head)
        datas.append(data)
    # A negative count says the first alpha channel of the merged image holds its transparency.
    info = struct.pack(">h", -len(records)) + b"".join(heads) + b"".join(datas)
    info += b"\0" * (len(info) % 2)
    layer_section = struct.pack(">I", len(info)) + info + struct.pack(">I", 0)  # no global layer mask
    out.write(struct.pack(">I", len(layer_section)) + layer_section)
    pixels = np.asarray(composite.convert("RGBA"))
    counts, rows = [], []
    for channel in (0, 1, 2, 3):
        row_counts, data = rle_channel(np.ascontiguousarray(pixels[:, :, channel]))
        counts += row_counts
        rows.append(data)
    out.write(struct.pack(">H", 1) + struct.pack(f">{len(counts)}H", *counts) + b"".join(rows))
    return out.getvalue()


def export_psd(project, path=None, *, page=None, variables=None, report=None):
    """Layered PSD bytes of the document (one page of a paged document); written to ``path`` when given.
    ``report`` receives the layer and group counts and warnings about what became pixels."""
    from .render import render, view_page

    report = {} if report is None else report
    view = view_page(project, page)
    if variables:
        from .design_render import artboard_project

        view = artboard_project(view, None, None, variables)
    c = view.state["canvas"]
    require(c["width"] <= MAX_SIDE and c["height"] <= MAX_SIDE, f"PSD canvases are at most {MAX_SIDE} px per side",
            "resource_limit")
    records = build(view, report)
    composite = render(view)
    data = write(records, composite, dpi=view.state["canvas"].get("dpi") or 72)
    if path:
        from pathlib import Path

        Path(path).write_bytes(data)
    return data
