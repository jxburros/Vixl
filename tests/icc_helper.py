"""Build a tiny, valid CMYK output ICC profile (lut8 A2B0/B2A0) for offline tests."""

import struct

from vixl.colors import cmyk_to_srgb, lab_to_srgb, srgb_to_cmyk, srgb_to_lab


def _s15(value):
    return struct.pack(">i", round(value * 65536))


def _pad(data):
    return data + b"\0" * (-len(data) % 4)


def _lut8(inputs, outputs, grid, function):
    body = b"mft1" + b"\0" * 4 + bytes([inputs, outputs, grid, 0])
    body += b"".join(_s15(v) for v in (1, 0, 0, 0, 1, 0, 0, 0, 1))
    body += bytes(range(256)) * inputs
    table = bytearray()
    for index in range(grid**inputs):
        coordinates = []
        for _ in range(inputs):
            coordinates.append(index % grid / (grid - 1))
            index //= grid
        table += bytes(function(list(reversed(coordinates))))
    body += bytes(table) + bytes(range(256)) * outputs
    return body


def _cmyk_to_lab(c):
    L, a, b = srgb_to_lab(cmyk_to_srgb(*c))
    return [round(min(max(L, 0), 100) * 255 / 100), round(min(max(a + 128, 0), 255)), round(min(max(b + 128, 0), 255))]


def _lab_to_cmyk(v):
    lab = (v[0] * 100, v[1] * 255 - 128, v[2] * 255 - 128)
    rgb = [min(max(x, 0.0), 1.0) for x in lab_to_srgb(lab)]
    return [round(x * 255) for x in srgb_to_cmyk(rgb)]


def cmyk_profile():
    desc = b"Vixl test CMYK"
    tags = {
        b"desc": b"desc" + b"\0" * 4 + struct.pack(">I", len(desc) + 1) + desc + b"\0" + b"\0" * 8 + b"\0" * 3 + b"\0" * 67,
        b"wtpt": b"XYZ " + b"\0" * 4 + _s15(0.9642) + _s15(1.0) + _s15(0.8249),
        b"cprt": b"text" + b"\0" * 4 + b"Public domain test data\0",
        b"A2B0": _lut8(4, 3, 3, _cmyk_to_lab),
        b"B2A0": _lut8(3, 4, 9, _lab_to_cmyk),
    }
    table_size = 4 + 12 * len(tags)
    offset = 128 + table_size
    entries, blobs = b"", b""
    for signature, data in tags.items():
        data = _pad(data)
        entries += signature + struct.pack(">II", offset + len(blobs), len(data))
        blobs += data
    size = 128 + table_size + len(blobs)
    header = struct.pack(">I", size) + b"lcms" + struct.pack(">I", 0x02100000) + b"prtr" + b"CMYK" + b"Lab "
    header += struct.pack(">6H", 2025, 1, 1, 0, 0, 0) + b"acsp" + b"\0" * 4 + b"\0" * 4 + b"\0" * 8 + b"\0" * 8
    header += struct.pack(">I", 0) + _s15(0.9642) + _s15(1.0) + _s15(0.8249) + b"lcms" + b"\0" * 16 + b"\0" * 28
    assert len(header) == 128
    return header + struct.pack(">I", len(tags)) + entries + blobs
