"""The little of a PSD that a printer's template needs: its ruler guides, its flattened image and which pixels each
named layer draws.

This is not a PSD importer. It reads 8-bit RGB or greyscale PSD files (version 1) with raw or RLE channels, checks
every length against the file and the pixel limit before allocating, and decodes only the flattened image and the
transparency channel of the layers it is asked for. Anything else (PSB, 16-bit, CMYK, ZIP channels) is refused with
the way out: export the template as a flattened PNG.
"""

import struct

import numpy as np

from ...errors import VixlError, require

GUIDES_RESOURCE = 1032
MAX_LAYERS = 2000
PNG_HINT = "export the template as a flattened PNG and import that"


def _fail(message):
    return VixlError("invalid_image", f"{message}; {PNG_HINT}", field="source")


class _Reader:
    def __init__(self, data):
        self.data, self.at = data, 0

    def take(self, count):
        if count < 0 or self.at + count > len(self.data):
            raise _fail("The PSD is truncated")
        self.at += count
        return self.data[self.at - count:self.at]

    def unpack(self, layout):
        return struct.unpack(layout, self.take(struct.calcsize(layout)))


def _packbits(data, start, length, size):
    """One RLE row of ``length`` bytes at ``start``, as exactly ``size`` bytes."""
    out = bytearray()
    at, end = start, min(start + length, len(data))
    while at < end and len(out) < size:
        count = data[at]
        at += 1
        if count < 128:
            out += data[at:at + count + 1]
            at += count + 1
        elif count > 128:
            out += data[at:at + 1] * (257 - count)
            at += 1
    return bytes(out[:size]).ljust(size, b"\0")


def _plane(reader, compression, width, height, counts=None):
    """One channel as a (height, width) uint8 array, read at the reader's position."""
    if compression == 0:
        return np.frombuffer(reader.take(width * height), dtype=np.uint8).reshape(height, width)
    if counts is None:
        counts = reader.unpack(f">{height}H")
    rows = []
    for count in counts:
        rows.append(_packbits(reader.data, reader.at, count, width))
        reader.take(count)
    return np.frombuffer(b"".join(rows), dtype=np.uint8).reshape(height, width)


def read(data, limits, layer_names=()):
    """``{size, guides, image, layers, layer_names}`` of a PSD: ``guides`` [(axis, position)] from the ruler guides
    (``x`` is a vertical line), ``image`` the flattened picture (H × W × 4 uint8), ``layer_names`` every layer's
    name, and ``layers`` {name: mask (H × W bool) of the pixels it draws} for the names in ``layer_names`` (matched
    without case)."""
    reader = _Reader(data)
    signature, version = reader.unpack(">4sH")
    require(signature == b"8BPS", "The file is not a PSD", "invalid_image", field="source")
    if version != 1:
        raise _fail("Large-document PSDs (PSB) are not read")
    reader.take(6)
    channels, height, width, depth, mode = reader.unpack(">HIIHH")
    if depth != 8 or mode not in (1, 3):
        raise _fail("Only 8-bit RGB or greyscale PSDs are read")
    limits.size(int(width), int(height))
    reader.take(reader.unpack(">I")[0])  # colour mode data

    guides = []
    resources = _Reader(reader.take(reader.unpack(">I")[0]))
    while resources.at + 12 <= len(resources.data):
        marker, ident, name_length = resources.unpack(">4sHB")
        if marker != b"8BIM":
            break
        resources.take(name_length + (1 - name_length % 2))
        size = resources.unpack(">I")[0]
        block = resources.take(size)
        resources.take(min(size % 2, len(resources.data) - resources.at))
        if ident == GUIDES_RESOURCE and len(block) >= 16:
            count = struct.unpack(">I", block[12:16])[0]
            for i in range(min(count, (len(block) - 16) // 5)):
                location, direction = struct.unpack(">iB", block[16 + 5 * i:21 + 5 * i])
                guides.append(("x" if direction == 0 else "y", location / 32))

    wanted = {name.casefold() for name in layer_names}
    names, masks = [], {}
    section = _Reader(reader.take(reader.unpack(">I")[0]))
    if len(section.data) >= 6:
        section.take(4)  # the layer info length
        count = abs(section.unpack(">h")[0])
        require(count <= MAX_LAYERS, f"The PSD has more than {MAX_LAYERS} layers", "resource_limit", field="source")
        records = []
        for _ in range(count):
            top, left, bottom, right, channel_count = section.unpack(">iiiiH")
            sizes = [section.unpack(">hI") for _ in range(channel_count)]
            section.take(12)  # blend signature and key, opacity, clipping, flags, filler
            extra = _Reader(section.take(section.unpack(">I")[0]))
            extra.take(extra.unpack(">I")[0])  # layer mask
            extra.take(extra.unpack(">I")[0])  # blending ranges
            length = extra.unpack(">B")[0]
            name = extra.take(length).decode("mac_roman", "replace")
            extra.take(-(length + 1) % 4)
            while extra.at + 12 <= len(extra.data):  # the Unicode name, when the file has one
                marker, key, size = extra.unpack(">4s4sI")
                block = extra.take(min(size + size % 2, len(extra.data) - extra.at))
                if marker == b"8BIM" and key == b"luni" and len(block) >= 4:
                    chars = struct.unpack(">I", block[:4])[0]
                    name = block[4:4 + 2 * chars].decode("utf-16-be", "replace").rstrip("\0")
            names.append(name)
            records.append((name, (top, left, bottom, right), sizes))
        for name, (top, left, bottom, right), sizes in records:
            for ident, size in sizes:
                start = section.at
                section.take(size)
                if ident != -1 or name.casefold() not in wanted or name in masks:
                    continue
                w, h = right - left, bottom - top
                mask = np.zeros((height, width), dtype=bool)
                if w > 0 and h > 0:
                    require(w * h <= limits.max_pixels, "A PSD layer exceeds the pixel limit", "resource_limit",
                            field="source")
                    channel = _Reader(section.data)
                    channel.at = start
                    compression = channel.unpack(">H")[0]
                    if compression not in (0, 1):
                        raise _fail(f"Layer {name!r} uses ZIP compression, which is not read")
                    alpha = _plane(channel, compression, w, h) >= 128
                    y0, y1, x0, x1 = max(top, 0), min(bottom, height), max(left, 0), min(right, width)
                    if y1 > y0 and x1 > x0:
                        mask[y0:y1, x0:x1] = alpha[y0 - top:y1 - top, x0 - left:x1 - left]
                masks[name] = mask

    image = np.full((height, width, 4), 255, dtype=np.uint8)
    if reader.at + 2 <= len(data):
        compression = reader.unpack(">H")[0]
        if compression not in (0, 1):
            raise _fail("The PSD's flattened image uses ZIP compression, which is not read")
        counts = reader.unpack(f">{height * channels}H") if compression == 1 else None
        planes = []
        for index in range(min(channels, 3 if mode == 3 else 1)):
            rows = counts[index * height:(index + 1) * height] if counts else None
            planes.append(_plane(reader, compression, width, height, rows))
        if mode == 3 and len(planes) == 3:
            image[..., :3] = np.dstack(planes)
        elif planes:
            image[..., :3] = planes[0][..., None]
    return {"size": (int(width), int(height)), "guides": guides, "image": image, "layers": masks,
            "layer_names": names}
