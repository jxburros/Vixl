"""A bounded reader for layered Photoshop (PSD) files.

Reads the subset Vixl can keep: version 1 (not PSB), 8 bits per channel, RGB, with raw or PackBits
(RLE) channel data. For each layer record it returns the name, box, opacity, blend key, visibility,
clipping flag, group section markers, the layer mask and the type-tool block; pixels are decoded on
request. Anything else (16/32-bit, CMYK, greyscale, indexed, Lab, ZIP-compressed channels) is refused
with ``unsupported_psd``.

The file is untrusted. Every length is checked against the bytes that exist before it is used, the
layer count and each layer's size are checked against ``Limits`` before any pixel buffer is made, the
pixels of all layers and masks together stay under ``Limits.max_load_pixels``, and a row never decodes
to more than its declared width.

Format reference: Adobe Photoshop File Format Specification (file header, layer and mask information,
image data sections).
"""

import struct
from dataclasses import dataclass, field

import numpy as np

from .errors import VixlError, require

BLENDS = {
    b"norm": "normal", b"mul ": "multiply", b"scrn": "screen", b"over": "overlay", b"dark": "darken",
    b"lite": "lighten", b"diff": "difference", b"lddg": "add", b"fsub": "subtract", b"pass": "normal",
}
MAX_CHANNELS = 56  # the format's own limit
MAX_COORDINATE = 300000  # the format's canvases are at most 30,000 px (PSB 300,000) per side
MAX_BLOCK = 8 * 1024 * 1024  # a type-tool block kept for reading
# Additional layer information that changes what a layer draws and that the import does not apply.
ADJUSTMENTS = {
    b"brit": "brightness/contrast", b"levl": "levels", b"curv": "curves", b"expA": "exposure", b"vibA": "vibrance",
    b"hue ": "hue/saturation", b"hue2": "hue/saturation", b"blnc": "colour balance", b"blwh": "black and white",
    b"phfl": "photo filter", b"mixr": "channel mixer", b"clrL": "colour lookup", b"nvrt": "invert",
    b"post": "posterize", b"thrs": "threshold", b"grdm": "gradient map", b"selc": "selective colour",
}
FILLS = {b"SoCo": "solid colour fill", b"GdFl": "gradient fill", b"PtFl": "pattern fill"}
EFFECTS = (b"lfx2", b"lrFX", b"lmfx")
VECTOR_MASKS = (b"vmsk", b"vsms")


def bad(message):
    return VixlError("invalid_psd", f"Malformed PSD: {message}")


@dataclass
class Mask:
    box: tuple  # left, top, right, bottom on the canvas
    default: int  # the value outside the box: 0 hides, 255 shows
    disabled: bool = False
    relative: bool = False  # positioned relative to the layer
    parameters: bool = False  # density or feather is set
    data: tuple | None = None  # (offset, length) of its channel


@dataclass
class Layer:
    name: str
    box: tuple  # left, top, right, bottom on the canvas
    opacity: float
    blend: str  # the four-character blend key
    visible: bool
    clipping: bool
    section: int | None  # 1 or 2: a group (open or closed); 3: the marker that ends a group; None: a layer
    channels: dict = field(default_factory=dict)  # channel id: (offset, length)
    mask: Mask | None = None
    blocks: list = field(default_factory=list)  # keys of its additional information blocks
    type_data: bytes | None = None
    fill_opacity: float = 1.0
    lengths: list = field(default_factory=list, repr=False)  # (channel id, byte length) as the record lists them

    @property
    def size(self):
        return self.box[2] - self.box[0], self.box[3] - self.box[1]


@dataclass
class Document:
    width: int
    height: int
    channels: int
    dpi: float | None
    layers: list  # bottom to top
    merged_alpha: bool  # the composite's fourth channel is its transparency
    image_offset: int
    data: bytes = field(repr=False, default=b"")


class Cursor:
    def __init__(self, data, pos=0, end=None):
        self.data, self.pos, self.end = data, pos, len(data) if end is None else end

    def take(self, count):
        if count < 0 or self.pos + count > self.end:
            raise bad("the file ends inside a structure")
        start, self.pos = self.pos, self.pos + count
        return self.data[start:self.pos]

    def unpack(self, fmt):
        return struct.unpack(fmt, self.take(struct.calcsize(fmt)))

    def section(self, length):
        """A cursor over the next ``length`` bytes, which this cursor skips."""
        if length < 0 or self.pos + length > self.end:
            raise bad("a section is longer than the file")
        start, self.pos = self.pos, self.pos + length
        return Cursor(self.data, start, self.pos)

    @property
    def left(self):
        return self.end - self.pos


def _box(cursor, limits, what):
    top, left, bottom, right = cursor.unpack(">4i")
    if bottom < top or right < left or max(map(abs, (top, left, bottom, right))) > MAX_COORDINATE:
        raise bad(f"{what} has an impossible box")
    width, height = right - left, bottom - top
    require(width <= limits.max_dimension and height <= limits.max_dimension and width * height <= limits.max_pixels,
            f"PSD {what} of {width}×{height} px exceeds the size limit", "resource_limit")
    return left, top, right, bottom


def _header(cursor, limits):
    signature, version = cursor.unpack(">4sH")
    if signature != b"8BPS":
        raise VixlError("invalid_psd", "Not a Photoshop file (it does not start with 8BPS)")
    require(version == 1, "Large document format (PSB) files are not supported; save as PSD", "unsupported_psd")
    cursor.take(6)
    channels, height, width, depth, mode = cursor.unpack(">HIIHH")
    if not 1 <= channels <= MAX_CHANNELS or not width or not height:
        raise bad("impossible channel count or size")
    require(depth == 8, f"{depth}-bit PSD files are not supported; convert to 8 bits/channel", "unsupported_psd")
    modes = {0: "bitmap", 1: "greyscale", 2: "indexed", 4: "CMYK", 7: "multichannel", 8: "duotone", 9: "Lab"}
    require(mode == 3, f"{modes.get(mode, 'this colour mode')} PSD files are not supported; convert to RGB",
            "unsupported_psd")
    require(channels >= 3, "An RGB PSD needs three colour channels", "invalid_psd")
    require(width <= limits.max_dimension and height <= limits.max_dimension and width * height <= limits.max_pixels,
            f"PSD canvas of {width}×{height} px exceeds the size limit", "resource_limit")
    return channels, width, height


def _resolution(resources):
    """Horizontal pixels per inch from the resolution resource (1005), or None."""
    try:
        while resources.left >= 12:
            signature, ident = resources.unpack(">4sH")
            if signature not in (b"8BIM", b"MeSa", b"AgHg", b"PHUT", b"DCSR"):
                return None
            (length,) = resources.unpack(">B")
            resources.take(length + (1 - length % 2))  # the Pascal name, padded to an even total
            (size,) = resources.unpack(">I")
            body = resources.section(size)
            if size % 2 and resources.left:
                resources.take(1)
            if ident == 1005 and size >= 4:
                dpi = body.unpack(">I")[0] / 65536
                return dpi if 1 <= dpi <= 9600 else None
    except VixlError:
        pass  # Resources are optional metadata: a damaged list only loses the resolution.
    return None


def _layer_record(cursor, limits):
    box = _box(cursor, limits, "layer")
    (count,) = cursor.unpack(">H")
    if count > MAX_CHANNELS:
        raise bad("a layer has too many channels")
    lengths = [cursor.unpack(">hI") for _ in range(count)]
    signature, key, opacity, clipping, flags, _ = cursor.unpack(">4s4sBBBB")
    if signature != b"8BIM":
        raise bad("a layer record has no blend signature")
    if key not in BLENDS and key[::-1] in BLENDS:
        key = key[::-1]  # some writers store the key byte-reversed
    (extra_length,) = cursor.unpack(">I")
    extra = cursor.section(extra_length)
    mask = None
    (mask_length,) = extra.unpack(">I")
    mask_data = extra.section(mask_length)
    if mask_length >= 18:
        mask_box = _box(mask_data, limits, "layer mask")
        default, mask_flags = mask_data.unpack(">BB")
        mask = Mask(mask_box, 255 if default else 0, disabled=bool(mask_flags & 2), relative=bool(mask_flags & 1),
                    parameters=bool(mask_flags & 16))
    (ranges,) = extra.unpack(">I")
    extra.section(ranges)
    (length,) = extra.unpack(">B")
    name = bytes(extra.take(length)).decode("mac_roman", "replace")
    extra.take(-(1 + length) % 4)
    layer = Layer(name, box, opacity / 255, key.decode("latin-1"), not flags & 2, bool(clipping), None, mask=mask,
                  lengths=lengths)
    while extra.left >= 12:
        signature, tag, size = extra.unpack(">4s4sI")
        if signature not in (b"8BIM", b"8B64"):
            raise bad("a layer has an unreadable information block")
        body = extra.section(size)
        if size % 2 and extra.left and extra.data[extra.pos:extra.pos + 1] == b"\0":
            extra.take(1)
        layer.blocks.append(tag)
        if tag == b"luni" and size >= 4:
            (chars,) = body.unpack(">I")
            layer.name = bytes(body.take(2 * chars)).decode("utf-16-be", "replace").rstrip("\0") or layer.name
        elif tag in (b"lsct", b"lsdk") and size >= 4:
            (kind,) = body.unpack(">I")
            layer.section = kind if kind in (1, 2, 3) else None
            if size >= 12:
                _, blend = body.unpack(">4s4s")
                layer.blend = blend.decode("latin-1")
        elif tag == b"TySh" and size <= MAX_BLOCK:
            layer.type_data = bytes(body.take(size))
        elif tag == b"iOpa" and size >= 1:
            layer.fill_opacity = body.unpack(">B")[0] / 255
    return layer


def read(data, limits):
    """The ``Document`` in PSD bytes: its size and its layer records, bottom to top, without pixels (see
    ``layer_pixels``, ``mask_pixels`` and ``composite``). Raises ``invalid_psd``, ``unsupported_psd`` or
    ``resource_limit``."""
    require(len(data) <= limits.max_asset_bytes, "PSD exceeds byte limit", "resource_limit")
    data = bytes(data)
    cursor = Cursor(data)
    try:
        channels, width, height = _header(cursor, limits)
        cursor.section(cursor.unpack(">I")[0])  # colour mode data (empty for RGB)
        dpi = _resolution(cursor.section(cursor.unpack(">I")[0]))
        section = cursor.section(cursor.unpack(">I")[0])
        layers, merged_alpha = [], False
        if section.left >= 4:
            info = section.section(section.unpack(">I")[0])
            if info.left >= 2:
                (count,) = info.unpack(">h")
                merged_alpha, count = count < 0, abs(count)
                require(count <= limits.max_layers, f"PSD has {count} layers; the limit is {limits.max_layers}",
                        "resource_limit")
                # Each record takes at least 34 bytes, so a count the file cannot hold fails before the loop.
                if count * 34 > info.left:
                    raise bad("the layer count is larger than the file")
                layers = [_layer_record(info, limits) for _ in range(count)]
                total = width * height
                for layer in layers:
                    for ident, length in layer.lengths:
                        chunk = info.section(length)
                        layer.channels[ident] = (chunk.pos, length)
                    total += layer.size[0] * layer.size[1]
                    if layer.mask and -2 in layer.channels:
                        layer.mask.data = layer.channels[-2]
                        total += (layer.mask.box[2] - layer.mask.box[0]) * (layer.mask.box[3] - layer.mask.box[1])
                # Everything the importer may decode (the canvas, every layer and mask), counted from the
                # declared boxes before any buffer exists.
                require(total <= limits.max_load_pixels,
                        f"PSD layers together hold {total:,} pixels; the limit is {limits.max_load_pixels:,}",
                        "resource_limit")
    except struct.error as exc:
        raise bad("the file ends inside a structure") from exc
    return Document(width, height, channels, dpi, layers, merged_alpha, cursor.pos, data)


def _unpack_rows(data, pos, end, counts, width, out):
    """PackBits rows from ``data[pos:end]`` into ``out`` (rows of exactly ``width`` bytes)."""
    row_start = 0
    for count in counts:
        stop = pos + count
        if stop > end:
            raise bad("channel data is shorter than its row table")
        filled, limit = row_start, row_start + width
        while pos < stop:
            n = data[pos]
            pos += 1
            if n < 128:
                n += 1
                if pos + n > stop or filled + n > limit:
                    raise bad("a compressed row overruns its width")
                out[filled:filled + n] = data[pos:pos + n]
                pos += n
                filled += n
            elif n > 128:
                n = 257 - n
                if pos >= stop or filled + n > limit:
                    raise bad("a compressed row overruns its width")
                out[filled:filled + n] = bytes((data[pos],)) * n
                pos += 1
                filled += n
        if filled != limit:
            raise bad("a compressed row is shorter than its width")
        row_start = limit
    return pos


def _plane(data, offset, length, width, height):
    """One channel (compression marker included) as a (height, width) uint8 array."""
    if not width or not height:
        return np.zeros((height, width), np.uint8)
    end = offset + length
    if length < 2:
        raise bad("a channel has no data")
    (compression,) = struct.unpack_from(">H", data, offset)
    pos = offset + 2
    if compression == 0:
        if end - pos < width * height:
            raise bad("raw channel data is shorter than the layer")
        return np.frombuffer(data, np.uint8, width * height, pos).reshape(height, width)
    require(compression == 1, "ZIP-compressed PSD channels are not supported; save with RLE compression "
            "(maximise compatibility)", "unsupported_psd")
    if end - pos < 2 * height:
        raise bad("a channel's row table is cut short")
    counts = struct.unpack_from(f">{height}H", data, pos)
    out = bytearray(width * height)
    _unpack_rows(data, pos + 2 * height, end, counts, width, out)
    return np.frombuffer(out, np.uint8).reshape(height, width)


def layer_pixels(document, layer):
    """The layer's RGBA pixels (height, width, 4); a layer without an alpha channel is opaque."""
    width, height = layer.size
    pixels = np.zeros((height, width, 4), np.uint8)
    pixels[:, :, 3] = 255
    for ident, index in ((0, 0), (1, 1), (2, 2), (-1, 3)):
        if ident in layer.channels:
            pixels[:, :, index] = _plane(document.data, *layer.channels[ident], width, height)
        elif ident >= 0 and width and height:
            raise bad("a layer lacks a colour channel")
    return pixels


def mask_pixels(document, layer):
    """The layer mask as a (height, width) array over ``layer.mask.box``, or None."""
    mask = layer.mask
    if mask is None or mask.data is None:
        return None
    return _plane(document.data, *mask.data, mask.box[2] - mask.box[0], mask.box[3] - mask.box[1])


def composite(document):
    """The merged image the file carries, as RGBA (opaque unless the file marks its fourth channel as
    transparency)."""
    data, width, height = document.data, document.width, document.height
    pos, end = document.image_offset, len(document.data)
    if end - pos < 2:
        raise bad("the file has no image data")
    (compression,) = struct.unpack_from(">H", data, pos)
    pos += 2
    used = 4 if document.merged_alpha and document.channels >= 4 else 3
    pixels = np.zeros((height, width, 4), np.uint8)
    pixels[:, :, 3] = 255
    if compression == 0:
        if end - pos < used * width * height:
            raise bad("the image data is shorter than the canvas")
        for index in range(used):
            pixels[:, :, index] = np.frombuffer(data, np.uint8, width * height, pos + index * width * height
                                                ).reshape(height, width)
        return pixels
    require(compression == 1, "ZIP-compressed PSD image data is not supported", "unsupported_psd")
    rows = document.channels * height
    if end - pos < 2 * rows:
        raise bad("the image data's row table is cut short")
    counts = struct.unpack_from(f">{rows}H", data, pos)
    pos += 2 * rows
    for index in range(used):
        out = bytearray(width * height)
        pos = _unpack_rows(data, pos, end, counts[index * height:(index + 1) * height], width, out)
        pixels[:, :, index] = np.frombuffer(out, np.uint8).reshape(height, width)
    return pixels
