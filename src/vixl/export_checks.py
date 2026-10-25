"""Post-export checks: read a delivered file back and compare it with a delivery spec.

``inspect(path)`` returns the facts of one file (format, bytes, SHA-256, plus per format: PDF pages and boxes,
fonts and whether each is embedded, colour spaces, form fields and ink coverage; raster size, dpi, ICC profile, mode
and alpha; PowerPoint slides, text frames and native charts; HTML and SVG external references, notes and text).
``verify(path, spec)`` checks those facts against a delivery spec and returns findings in the ``checks.py`` issue
shape (``check: "export"``, a ``code``, ``severity`` and ``action``) with an outcome.

Specs are data: the presets in ``data/delivery-specs.json`` (``print-letter-bleed``, ``instagram-feed``,
``web-banner`` ...) or inline fields, optionally on top of a preset (``{"preset": "web-banner", "max_bytes": 200000}``).
Verification only reads the file: it never changes or replaces it.

PDF pages, boxes, embedded fonts and the rendered ink come from pypdfium2 when it is installed. Without it a byte
scan of the file's objects (including compressed object streams) reads the boxes, fonts and form fields; ink
coverage then cannot be measured and a spec that asks for it gets a review finding, never a pass.
"""

from functools import lru_cache
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
import zipfile
import zlib

from .errors import VixlError, require
from .model import Limits

CHECK = "export"
MAX_PAGES = 200  # pages whose boxes and fonts are read
MAX_INK_PAGES = 20  # pages rendered for ink coverage
INK_DPI = 36
MAX_LISTED = 20  # references, fonts and names listed per fact
MAX_INFLATE = 64 * 1024 * 1024  # decompressed PDF stream bytes read by the byte scan
MAX_ZIP_ENTRY = 32 * 1024 * 1024
TOLERANCE_PT = 0.5
SPEC_FIELDS = {
    "description": "What the spec is for",
    "preset": "A preset to start from; the other fields override it",
    "formats": "Allowed file extensions, e.g. [\"pdf\"]",
    "max_bytes": "Largest file size in bytes",
    "pages": "Page or slide count: a number, or [min, max]",
    "trim": "PDF trim size: a size name (letter, a4 ...) or [width, height] (points, or strings such as '8.5in', '210mm')",
    "bleed": "PDF bleed on every side (points or '0.125in', '3mm'); 0 means no bleed",
    "fonts_embedded": "Every PDF font is embedded",
    "color": "rgb, cmyk or gray: the colour model of the file",
    "ink_limit": "Most total ink in percent (CMYK print)",
    "fillable": "true: the PDF has form fields; false: it has none",
    "width": "Exact raster width in px",
    "height": "Exact raster height in px",
    "min_width": "Smallest raster width in px",
    "min_height": "Smallest raster height in px",
    "sizes": "Allowed raster sizes [[width, height], ...]",
    "aspect": "Allowed width/height ratio [min, max]",
    "dpi": "Smallest resolution recorded in the raster file",
    "alpha": "true: the raster keeps an alpha channel; false: it has none",
    "icc": "true: an ICC profile is embedded; false: none is",
    "editable_text": "PowerPoint text stays in text frames (when the document has text)",
    "native_charts": "PowerPoint charts are native chart parts: true (as many as the document has) or a minimum count",
    "self_contained": "HTML and SVG load nothing from the network or other files",
    "notes": "HTML speaker notes: true present, false absent",
    "text_as_text": "SVG text stays <text> elements (when the document has text)",
}
UNITS_PT = {"pt": 1.0, "in": 72.0, "mm": 72 / 25.4, "cm": 72 / 2.54}
RASTER = ("png", "jpg", "webp", "tiff", "avif", "gif", "bmp", "ico")


# ------------------------------------------------------------------------------------------------- specs


@lru_cache(maxsize=1)
def presets():
    """The bundled delivery specs by name."""
    data = json.loads((Path(__file__).parent / "data" / "delivery-specs.json").read_text(encoding="utf-8"))
    return data["specs"]


def resolve_spec(spec):
    """``(name, fields)`` for a preset name, an inline dict (optionally with ``preset``), ``True`` or ``None``
    (the ``default`` preset). Unknown fields and presets are errors that list the choices."""
    import difflib

    if spec is None or spec is True:
        spec = "default"
    if isinstance(spec, str):
        name = spec.strip()
        if name not in presets():
            close = difflib.get_close_matches(name, list(presets()), 3, 0.5)
            raise VixlError("invalid_request", f"Unknown delivery spec {name!r}" + (
                f"; did you mean {' or '.join(map(repr, close))}?" if close else "")
                + f". Presets: {', '.join(presets())}; or give the fields inline", field="spec",
                allowed=list(presets()), suggestions=close)
        return name, {k: v for k, v in presets()[name].items() if k != "description"}
    require(isinstance(spec, dict), "spec is a preset name or an object of delivery fields", field="spec")
    unknown = sorted(set(spec) - set(SPEC_FIELDS))
    if unknown:
        close = difflib.get_close_matches(unknown[0], list(SPEC_FIELDS), 1, 0.5)
        raise VixlError("invalid_request", f"Unknown delivery spec field {unknown[0]!r}"
                        + (f"; did you mean {close[0]!r}?" if close else "") + f". Fields: {', '.join(SPEC_FIELDS)}",
                        field=f"spec.{unknown[0]}", allowed=list(SPEC_FIELDS), suggestions=close)
    base = {}
    name = "inline"
    if spec.get("preset") is not None:
        name, base = resolve_spec(spec["preset"])
        name = f"{name}+inline" if set(spec) - {"preset", "description"} else name
    fields = {**base, **{k: v for k, v in spec.items() if k not in ("preset", "description")}}
    _validate(fields)
    return name, fields


def _validate(fields):
    def number(key, low=0):
        value = fields.get(key)
        require(value is None or (isinstance(value, (int, float)) and not isinstance(value, bool) and value >= low),
                f"spec.{key} must be a number ≥ {low}", field=f"spec.{key}")

    for key in ("max_bytes", "width", "height", "min_width", "min_height", "dpi"):
        number(key, 1)
    number("ink_limit", 100)
    formats = fields.get("formats")
    require(formats is None or (isinstance(formats, list) and formats and all(isinstance(f, str) for f in formats)),
            "spec.formats is a list of extensions such as [\"pdf\"]", field="spec.formats")
    pages = fields.get("pages")
    require(pages is None or (isinstance(pages, int) and not isinstance(pages, bool) and pages >= 1)
            or (isinstance(pages, list) and len(pages) == 2 and all(isinstance(v, int) for v in pages)),
            "spec.pages is a count or [min, max]", field="spec.pages")
    require(fields.get("color") in (None, "rgb", "cmyk", "gray"), "spec.color is rgb, cmyk or gray", field="spec.color")
    for key in ("fonts_embedded", "fillable", "alpha", "icc", "editable_text", "self_contained", "notes",
                "text_as_text"):
        require(fields.get(key) is None or isinstance(fields[key], bool), f"spec.{key} is true or false",
                field=f"spec.{key}")
    charts = fields.get("native_charts")
    require(charts is None or isinstance(charts, bool) or (isinstance(charts, int) and charts >= 0),
            "spec.native_charts is true, false or a minimum count", field="spec.native_charts")
    for key in ("aspect",):
        value = fields.get(key)
        require(value is None or (isinstance(value, list) and len(value) == 2
                                  and all(isinstance(v, (int, float)) and v > 0 for v in value)),
                f"spec.{key} is [min, max]", field=f"spec.{key}")
    sizes = fields.get("sizes")
    require(sizes is None or (isinstance(sizes, list) and sizes and all(
        isinstance(s, list) and len(s) == 2 and all(isinstance(v, int) for v in s) for s in sizes)),
        "spec.sizes is a list of [width, height]", field="spec.sizes")
    if fields.get("trim") is not None:
        trim_points(fields["trim"])
    if fields.get("bleed") is not None:
        length_points(fields["bleed"], "bleed")


def length_points(value, name="length"):
    """A length in PDF points: a number (points) or a string with a unit (pt, in, mm, cm)."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        require(value >= 0, f"spec.{name} must be ≥ 0", field=f"spec.{name}")
        return float(value)
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(pt|in|mm|cm)\s*", str(value))
    require(match is not None, f"spec.{name} is points or a length such as '0.125in' or '3mm'", field=f"spec.{name}")
    return float(match[1]) * UNITS_PT[match[2]]


def trim_points(value):
    """Trim size ``(width, height)`` in points from a print size name or a pair of lengths."""
    if isinstance(value, str):
        from .sizes import PX, SIZES, UNIT_INCHES, canonical

        entry = SIZES[canonical(value)]
        require(entry["unit"] != PX, f"spec.trim {value!r} is a pixel size; give a print size", field="spec.trim")
        factor = UNIT_INCHES[entry["unit"]] * 72
        return entry["width"] * factor, entry["height"] * factor
    require(isinstance(value, list) and len(value) == 2, "spec.trim is a size name or [width, height]",
            field="spec.trim")
    return tuple(length_points(v, "trim") for v in value)


# ------------------------------------------------------------------------------------------------- inspect


def sniff(data):
    """The file format from its first bytes (``None`` when unknown)."""
    head = data[:64]
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"\x89PNG"):
        return "png"
    if head.startswith(b"\xff\xd8"):
        return "jpg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff"
    if head[4:12] in (b"ftypavif", b"ftypavis"):
        return "avif"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if head[:4] == b"\x00\x00\x01\x00":
        return "ico"
    if head[:4] == b"8BPS":
        return "psd"
    if head[:2] == b"BM":
        return "bmp"
    if head[:4] == b"PK\x03\x04":
        return "zip"
    if head[:4] in (b"wOFF", b"wOF2", b"OTTO", b"\x00\x01\x00\x00", b"true"):
        return "font"
    text = data[:2048].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if text.startswith((b"<!doctype html", b"<html")):
        return "html"
    if text.startswith(b"<svg") or (text.startswith(b"<?xml") and b"<svg" in text):
        return "svg"
    return None


VIDEO = ("mp4", "webm", "mov")
SAME = {"jpeg": "jpg", "tif": "tiff", "htm": "html"}


def _space(name):
    return {"cmyk": "CMYK", "gray": "Gray", "rgb": "RGB"}.get(name, name)


def inspect(path, *, data=None, limits=None, ink=False):
    """The facts of one exported file: ``format`` (its extension), ``bytes``, ``sha256``, ``width``/``height``
    (pixels; points with ``unit: "pt"`` for a PDF), ``pages``, ``dpi``, ``color`` ({space, mode, alpha,
    icc_profile, color_spaces ...}), ``stream`` (frames of animated images, codecs of video via ffprobe) and per
    format the PDF boxes, fonts, forms and ink, the PowerPoint text frames and charts, and the HTML/SVG references.
    ``data`` gives the bytes instead of reading ``path`` (``path`` then only names the file). ``ink`` renders PDF
    pages (or reads a CMYK raster) for the total ink coverage, which costs a render. A file that cannot be read keeps
    its size and an ``unreadable`` note."""
    limits = limits or Limits()
    path = Path(path)
    suffix = path.suffix.lower()
    extension = suffix.lstrip(".")
    bound = max(limits.max_project_bytes, limits.max_asset_bytes)
    if data is None:
        require(path.is_file(), f"No such file: {path}", "not_found", field="path")
        size = path.stat().st_size
        if extension in VIDEO or size > bound:
            # Streams and very large files: hash them in chunks and read only their header.
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                head = stream.read(65536)
                digest.update(head)
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            facts = {"format": extension or "file", "bytes": size, "sha256": digest.hexdigest()}
            if extension in VIDEO:
                facts.update(video_facts(path))
            elif size > bound:
                facts["unreadable"] = f"the file is larger than the {bound:,}-byte inspection limit"
            return facts
        data = path.read_bytes()
    facts = {"format": extension or "file", "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    kind = sniff(data)
    if kind == "zip":
        kind = "pptx" if extension == "pptx" or b"ppt/" in data[:4096] else "zip"
    if kind == "font":
        kind = extension if extension in ("ttf", "otf", "woff", "woff2") else "font"
    named = SAME.get(extension, extension)
    if kind and named and kind != named:
        facts["content_format"] = kind
    kind = kind or named
    try:
        if kind == "pdf":
            facts.update(_pdf_facts(data, limits, ink))
        elif kind in RASTER:
            facts.update(raster_facts(data, ink=ink))
        elif kind == "pptx":
            facts.update(_pptx_facts(data))
        elif kind == "html":
            facts.update(_html_facts(data))
        elif kind == "svg":
            facts.update(_svg_facts(data))
        elif kind == "psd":
            require(data[:4] == b"8BPS", "not a Photoshop file")
            modes = {1: "Gray", 3: "RGB", 4: "CMYK"}
            facts.update(height=int.from_bytes(data[14:18], "big"), width=int.from_bytes(data[18:22], "big"),
                         color={"space": modes.get(int.from_bytes(data[24:26], "big"), "unknown")})
    except Exception as exc:  # noqa: BLE001 - decoders raise many kinds of error for damaged files; a finding, not a crash
        facts["unreadable"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    return facts


def _ffprobe(path):
    import shutil
    import subprocess

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    command = [ffprobe, "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height,r_frame_rate,"
               "nb_frames,duration,pix_fmt,channels,sample_rate:format=format_name,duration", "-of", "json", str(path)]
    try:
        done = subprocess.run(command, capture_output=True, timeout=120)
        return json.loads(done.stdout or b"{}") if done.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _seconds(*values):
    for value in values:
        try:
            seconds = float(value)
        except (TypeError, ValueError):
            continue
        if seconds >= 0:
            return seconds
    return None


def _rate(value):
    try:
        top, _, bottom = str(value).partition("/")
        return round(float(top) / float(bottom or 1), 3)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _whole(value):
    return int(value) if str(value).isdigit() else None


def video_facts(path):
    """Size, colour and streams of an encoded video, read back with ffprobe (nothing without it)."""
    info = _ffprobe(path)
    if info is None:
        return {}
    streams = info.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    container = info.get("format") or {}
    facts = {"stream": {"container": container.get("format_name")}}
    if video:
        seconds = _seconds(video.get("duration"), container.get("duration"))
        facts["width"], facts["height"] = video.get("width"), video.get("height")
        facts["color"] = {"space": "RGB" if "rgb" in str(video.get("pix_fmt")) else "YUV", "pix_fmt": video.get("pix_fmt")}
        facts["stream"]["video"] = {"codec": video.get("codec_name"), "fps": _rate(video.get("r_frame_rate")),
                                    "frames": _whole(video.get("nb_frames")),
                                    "duration_ms": None if seconds is None else round(seconds * 1000)}
    if audio:
        facts["stream"]["audio"] = {"codec": audio.get("codec_name"), "channels": audio.get("channels"),
                                    "sample_rate": _whole(audio.get("sample_rate"))}
    return facts


def raster_facts(data, *, ink=False):
    """Size, dpi, colour (space, mode, alpha, ICC profile) and the frames of an animated raster file, and its ink
    coverage when it is CMYK and ``ink`` is set."""
    from .assets import open_image

    with open_image(data) as source:
        mode = source.mode
        facts = {"width": source.width, "height": source.height}
        facts["color"] = {"space": "CMYK" if mode == "CMYK" else "Gray" if mode in ("1", "L", "LA", "I", "I;16")
                          else "RGB", "mode": mode,
                          "alpha": "A" in source.getbands() or mode in ("PA", "LA", "RGBa") or "transparency" in source.info,
                          "icc_profile": bool(source.info.get("icc_profile"))}
        icc = source.info.get("icc_profile")
        if icc:
            try:
                from PIL import ImageCms

                facts["color"]["icc_description"] = ImageCms.getProfileDescription(
                    ImageCms.ImageCmsProfile(io.BytesIO(icc))).strip()[:120]
            except Exception:  # noqa: BLE001 - the description is a courtesy
                pass
        if source.info.get("dpi"):
            facts["dpi"] = round(float(source.info["dpi"][0]))
        frames = getattr(source, "n_frames", 1)
        if frames > 1:
            milliseconds = 0
            for index in range(frames):
                source.seek(index)
                milliseconds += int(source.info.get("duration") or 0)
            source.seek(0)
            facts["stream"] = {"container": str(source.format).lower(), "frames": frames,
                               "loop": source.info.get("loop"), "duration_ms": milliseconds}
        if ink and mode == "CMYK":
            from .colors import ink_coverage

            source.thumbnail((1024, 1024))
            coverage = ink_coverage(source)
            facts["ink"] = {"max": coverage["max"], "mean": coverage["mean"], "method": "file CMYK values"}
    return facts


def raster_metadata(data):
    """The short metadata a proof page shows for a raster file: size, mode, dpi, ICC profile and frames."""
    facts = raster_facts(data)
    meta = {"size": f"{facts['width']} × {facts['height']} px", "color": facts["color"]["mode"]}
    if facts.get("dpi"):
        meta["dpi"] = facts["dpi"]
    if facts["color"]["icc_profile"]:
        meta["icc_profile"] = True
    if facts.get("stream"):
        meta["frames"] = facts["stream"]["frames"]
    return meta


def pdf_metadata(data):
    """The short metadata a proof page shows for a PDF: colour spaces, pages and the first page's size. Best effort:
    a PDF neither reader understands gives what could be read."""
    try:
        facts = _pdf_facts(data, Limits(), False)
    except Exception:  # noqa: BLE001 - metadata stays best-effort for odd PDFs
        facts = {}
    spaces = [name for name in ("DeviceCMYK", "DeviceRGB", "DeviceGray", "ICCBased") if name in (facts.get("color") or {}).get("color_spaces", [])]
    meta = {"color": ", ".join(spaces) or "unknown"}
    boxes = facts.get("page_boxes") or []
    if boxes:
        width, height = _size(boxes[0]["media_box"])
        meta.update(pages=facts["pages"], page_size=f"{width:g} × {height:g} pt")
    return meta


# PDF -------------------------------------------------------------------------------------------------------

OBJECT = re.compile(rb"(\d+)\s+(\d+)\s+obj\b")
REF = rb"(\d+)\s+\d+\s+R"


def _dict_end(data, start):
    """The index just past the ``>>`` that closes the dictionary opening at ``start`` (``<<``)."""
    depth, i, n = 0, start, len(data)
    while i < n:
        two = data[i:i + 2]
        if two == b"<<":
            depth, i = depth + 1, i + 2
            continue
        if two == b">>":
            depth, i = depth - 1, i + 2
            if depth == 0:
                return i
            continue
        if data[i:i + 1] == b"(":  # a literal string may hold unbalanced brackets
            level, i = 1, i + 1
            while i < n and level:
                c = data[i:i + 1]
                if c == b"\\":
                    i += 2
                    continue
                level += c == b"(" and 1 or c == b")" and -1 or 0
                i += 1
            continue
        i += 1
    return n


class _Scan:
    """The objects of a PDF by number, read from the bytes: direct objects and those in object streams."""

    def __init__(self, data):
        self.objects, self.streams, self.inflated = {}, {}, 0
        position = 0
        while True:
            match = OBJECT.search(data, position)
            if match is None:
                break
            number, start = int(match[1]), match.end()
            body_start = len(data) - len(data[start:].lstrip())
            if data[body_start:body_start + 2] == b"<<":
                end = _dict_end(data, body_start)
                body = data[body_start:end]
                after = data[end:end + 20].lstrip()
                if after.startswith(b"stream"):
                    stream_start = end + data[end:].index(b"stream") + 6
                    stream_start += 2 if data[stream_start:stream_start + 2] == b"\r\n" else 1
                    length = re.search(rb"/Length\s+(\d+)(?!\s+\d+\s+R)", body)
                    if length:
                        stream_end = stream_start + int(length[1])
                    else:
                        found = data.find(b"endstream", stream_start)
                        stream_end = found if found >= 0 else len(data)
                    self.streams[number] = (body, data[stream_start:stream_end])
                    position = stream_end
                else:
                    position = end
            else:
                stop = data.find(b"endobj", start)
                end = stop if stop >= 0 else len(data)
                body = data[body_start:end].strip()
                position = end
            self.objects[number] = body
        for number, (body, raw) in list(self.streams.items()):
            if re.search(rb"/Type\s*/ObjStm\b", body):
                self._object_stream(body, raw)

    def inflate(self, body, raw):
        """A stream's decoded bytes (FlateDecode or none), within the byte scan's budget; ``None`` otherwise."""
        filters = re.search(rb"/Filter\s*(\[[^\]]*\]|/\w+)", body)
        names = re.findall(rb"/(\w+)", filters[1]) if filters else []
        if names and names != [b"FlateDecode"]:
            return None
        if not names:
            return raw
        budget = MAX_INFLATE - self.inflated
        if budget <= 0:
            return None
        try:
            out = zlib.decompressobj().decompress(raw, budget)
        except zlib.error:
            return None
        self.inflated += len(out)
        return out

    def _object_stream(self, body, raw):
        content = self.inflate(body, raw)
        count, first = re.search(rb"/N\s+(\d+)", body), re.search(rb"/First\s+(\d+)", body)
        if content is None or not count or not first:
            return
        numbers = re.findall(rb"\d+", content[:int(first[1])])
        pairs = list(zip(numbers[0::2], numbers[1::2]))[:int(count[1])]
        for index, (number, offset) in enumerate(pairs):
            start = int(first[1]) + int(offset)
            end = int(first[1]) + int(pairs[index + 1][1]) if index + 1 < len(pairs) else len(content)
            self.objects.setdefault(int(number), content[start:end].strip())

    def get(self, number):
        return self.objects.get(number, b"")

    def resolve(self, body, key):
        """The value of ``/key`` in ``body``, following one indirect reference."""
        match = re.search(rb"/" + key + rb"\s*(" + REF + rb"|\[[^\]]*\]|/\w+|<<)", body)
        if not match:
            return None
        value = match[1]
        if match[2]:
            return self.get(int(match[2]))
        if value == b"<<":
            start = match.start(1)
            return body[start:_dict_end(body, start)]
        return value

    def pages(self):
        """Page dictionaries in document order (the page tree from its root, else object order)."""
        roots = [n for n, body in self.objects.items()
                 if re.search(rb"/Type\s*/Pages\b", body) and not re.search(rb"/Parent\b", body)]
        ordered, seen = [], set()

        def walk(number, inherited, depth=0):
            if number in seen or depth > 32 or len(ordered) >= MAX_PAGES * 4:
                return
            seen.add(number)
            body = self.get(number)
            box = _box(body, "MediaBox") or inherited
            if re.search(rb"/Type\s*/Pages\b", body):
                kids = self.resolve(body, b"Kids") or b""
                for kid in re.findall(REF, kids):
                    walk(int(kid), box, depth + 1)
            elif re.search(rb"/Type\s*/Page\b", body):
                ordered.append((number, body, box))

        for root in roots[:1]:
            walk(root, None)
        if not ordered:
            ordered = [(n, b, _box(b, "MediaBox")) for n, b in sorted(self.objects.items())
                       if re.search(rb"/Type\s*/Page\b", b)]
        return ordered


def _box(body, name):
    match = re.search(rb"/" + name.encode() + rb"\s*\[\s*([-\d.\s]+)\]", body)
    if not match:
        return None
    values = [float(v) for v in match[1].split()]
    return [round(v, 3) for v in values] if len(values) == 4 else None


def _size(box):
    return [round(abs(box[2] - box[0]), 3), round(abs(box[3] - box[1]), 3)] if box else None


def _scan_fonts(scan):
    """``{name: {embedded, subtype}}`` for every font dictionary the byte scan found."""
    fonts = {}
    for body in scan.objects.values():
        if not re.search(rb"/Type\s*/Font\b", body):
            continue
        subtype = re.search(rb"/Subtype\s*/(\w+)", body)
        subtype = subtype[1].decode("latin-1") if subtype else "unknown"
        if subtype in ("CIDFontType0", "CIDFontType2"):
            continue  # a Type0 font's descendant: judged with its parent
        name = re.search(rb"/BaseFont\s*/([^\s/\[\]<>()]+)", body)
        name = name[1].decode("latin-1") if name else f"{subtype} font"
        if subtype == "Type3":
            embedded = True  # the glyphs are drawn by the font's own procedures
        else:
            descriptor = None
            if subtype == "Type0":
                descendants = scan.resolve(body, b"DescendantFonts") or b""
                child = re.search(REF, descendants)
                child = scan.get(int(child[1])) if child else b""
                descriptor = scan.resolve(child, b"FontDescriptor")
            else:
                descriptor = scan.resolve(body, b"FontDescriptor")
            embedded = bool(descriptor and re.search(rb"/FontFile[23]?\b", descriptor))
        entry = fonts.setdefault(name, {"embedded": embedded, "subtype": subtype})
        entry["embedded"] = entry["embedded"] and embedded
    return fonts


def _scan_colors(scan, data):
    """Colour spaces the PDF uses: declared names, image colour spaces and content-stream colour operators.
    ``ink_declared`` is the most CMYK ink any ``k``/``K`` operator sets, in percent."""
    spaces = {name for name in ("DeviceCMYK", "DeviceRGB", "DeviceGray", "ICCBased", "Separation", "DeviceN", "Lab")
              if re.search(rb"/" + name.encode() + rb"\b", data)}
    declared = 0.0
    number = rb"(-?\d*\.?\d+)"
    for body, raw in scan.streams.values():
        if re.search(rb"/Subtype\s*/Image\b|/Type\s*/(ObjStm|XRef|Metadata)\b|/Length1\b", body):
            continue
        content = scan.inflate(body, raw)
        if content is None:
            continue
        for found in set(spaces) | {"DeviceCMYK", "DeviceRGB", "DeviceGray"}:
            if f"/{found}".encode() in content:
                spaces.add(found)
        if re.search(rb"(?:^|\s)" + rb"\s+".join([number] * 3) + rb"\s+(?:rg|RG)\b", content):
            spaces.add("DeviceRGB")
        if re.search(rb"(?:^|\s)" + number + rb"\s+(?:g|G)\b", content):
            spaces.add("DeviceGray")
        for match in re.finditer(rb"(?:^|\s)" + rb"\s+".join([number] * 4) + rb"\s+(?:k|K)\b", content):
            spaces.add("DeviceCMYK")
            declared = max(declared, sum(float(v) for v in match.groups()) * 100)
    return sorted(spaces), round(declared, 1)


def _scan_images_ink(scan):
    """The most total ink of the 8-bit DeviceCMYK images in the PDF (Flate or JPEG), in percent, or ``None``."""
    import numpy as np

    from .colors import ink_coverage

    peak = None
    for body, raw in scan.streams.values():
        if not (re.search(rb"/Subtype\s*/Image\b", body) and re.search(rb"/ColorSpace\s*/DeviceCMYK\b", body)):
            continue
        width, height = re.search(rb"/Width\s+(\d+)", body), re.search(rb"/Height\s+(\d+)", body)
        if not width or not height:
            continue
        w, h = int(width[1]), int(height[1])
        try:
            if re.search(rb"/DCTDecode\b", body):
                from .assets import open_image

                with open_image(raw, ("JPEG",)) as image:
                    image.thumbnail((1024, 1024))
                    values = ink_coverage(image.convert("CMYK"))["max"]
            else:
                pixels = scan.inflate(body, raw)
                if pixels is None or len(pixels) < w * h * 4 or re.search(rb"/DecodeParms\b", body):
                    continue
                values = ink_coverage(np.frombuffer(pixels[:w * h * 4], np.uint8).reshape(h, w, 4))["max"]
        except Exception:  # noqa: BLE001 - an image the scan cannot decode is left to the rendered estimate
            continue
        peak = values if peak is None else max(peak, values)
    return peak


def _scan_forms(scan):
    catalog = next((body for body in scan.objects.values() if re.search(rb"/Type\s*/Catalog\b", body)), b"")
    if not re.search(rb"/AcroForm\b", catalog):
        return {"fields": 0}
    names = []
    for body in scan.objects.values():
        if re.search(rb"/FT\s*/\w+", body):
            title = re.search(rb"/T\s*\(((?:\\.|[^\\)])*)\)", body)
            names.append(title[1].decode("latin-1") if title else "")
    return {"fields": len(names), "names": [n for n in names if n][:MAX_LISTED]}


def _pdfium_pages(data, ink):
    """Pages, boxes, fonts and (with ``ink``) the rendered ink coverage via pypdfium2, or ``None`` without it."""
    try:
        import pypdfium2
        import pypdfium2.raw as raw
    except ImportError:
        return None
    import ctypes

    document = pypdfium2.PdfDocument(data)
    try:
        pages, fonts, coverage = [], {}, []
        for index in range(min(len(document), MAX_PAGES)):
            page = document[index]
            try:
                entry = {"number": index + 1, "media_box": [round(v, 3) for v in page.get_mediabox()]}
                for key, getter in (("trim_box", page.get_trimbox), ("bleed_box", page.get_bleedbox)):
                    box = getter(fallback_ok=False)
                    if box is not None:
                        entry[key] = [round(v, 3) for v in box]
                pages.append(entry)
                for obj in page.get_objects(filter=[raw.FPDF_PAGEOBJ_TEXT]):
                    font = raw.FPDFTextObj_GetFont(obj.raw)
                    if not font:
                        continue
                    size = raw.FPDFFont_GetBaseFontName(font, None, 0)
                    buffer = ctypes.create_string_buffer(max(1, size))
                    raw.FPDFFont_GetBaseFontName(font, buffer, size)
                    name = buffer.value.decode("latin-1", "replace") or "unnamed font"
                    embedded = bool(raw.FPDFFont_GetIsEmbedded(font))
                    fonts.setdefault(name, {"embedded": embedded})["embedded"] &= embedded
                if ink and index < MAX_INK_PAGES:
                    from .colors import cmyk_image, ink_coverage

                    image = page.render(scale=INK_DPI / 72).to_pil().convert("RGB")
                    coverage.append(ink_coverage(cmyk_image(image)))
            finally:
                page.close()
        return {"page_count": len(document), "pages": pages, "fonts": fonts, "coverage": coverage}
    finally:
        document.close()


def _pdf_facts(data, limits, ink):
    scan = _Scan(data)
    facts = {"reader": "byte-scan"}
    spaces, declared = _scan_colors(scan, data)
    model = ("CMYK" if "DeviceCMYK" in spaces and "DeviceRGB" not in spaces else
             "Mixed" if {"DeviceRGB", "DeviceCMYK"} <= set(spaces) else
             "RGB" if set(spaces) & {"DeviceRGB", "ICCBased"} else "Gray" if "DeviceGray" in spaces else "unknown")
    facts["color"] = {"space": model, "color_spaces": spaces}
    facts["forms"] = _scan_forms(scan)
    scanned = scan.pages()
    pages = [{"number": i + 1, "media_box": box, **({"trim_box": _box(body, "TrimBox")} if _box(body, "TrimBox") else {}),
              **({"bleed_box": _box(body, "BleedBox")} if _box(body, "BleedBox") else {})}
             for i, (_, body, box) in enumerate(scanned[:MAX_PAGES])]
    fonts = _scan_fonts(scan)
    page_count = len(scanned)
    rendered = None
    try:
        rendered = _pdfium_pages(data, ink)
    except Exception as exc:  # noqa: BLE001 - pdfium refusing a file leaves the byte scan's facts
        facts["reader_error"] = str(exc)[:200]
    if rendered is not None:
        facts["reader"] = "pypdfium2"
        page_count, pages = rendered["page_count"], rendered["pages"]
        # The fonts the pages draw with, as pdfium resolves them; the scan adds each one's subtype.
        scanned_fonts = fonts
        fonts = {name: {**scanned_fonts.get(name, {}), "embedded": entry["embedded"]}
                 for name, entry in rendered["fonts"].items()}
    facts["pages"] = page_count
    facts["page_boxes"] = pages
    if pages and pages[0].get("media_box"):
        first = pages[0]
        width, height = _size(first["media_box"])
        facts.update(width=width, height=height, unit="pt")
        facts["page_size"] = _size(first.get("trim_box") or first["media_box"])
    facts["fonts"] = [{"name": name, **entry} for name, entry in sorted(fonts.items())][:MAX_LISTED * 5]
    facts["fonts_unembedded"] = sorted(name for name, entry in fonts.items() if not entry["embedded"])
    if ink:
        images = _scan_images_ink(scan)
        if rendered is not None and rendered["coverage"]:
            rendered_max = max(item["max"] for item in rendered["coverage"])
            mean = round(sum(item["mean"] for item in rendered["coverage"]) / len(rendered["coverage"]), 1)
            # A CMYK file states its ink; re-separating its rendered RGB would only estimate it again.
            stated = model == "CMYK" and (declared or images is not None)
            peak = max(declared, images or 0) if stated else max(rendered_max, declared, images or 0)
            facts["ink"] = {"max": round(peak, 1), "mean": mean, "rendered_max": rendered_max,
                            "declared_max": declared, **({"images_max": images} if images is not None else {}),
                            "pages": len(rendered["coverage"]),
                            "method": f"pages rendered at {INK_DPI} dpi and separated (device CMYK estimate); "
                                      "CMYK colour operators and images read from the file"}
        elif declared or images is not None:
            # Without a renderer only CMYK operators and images are read: complete for a pure CMYK file.
            partial = model != "CMYK"
            facts["ink"] = {"max": round(max(declared, images or 0), 1), "declared_max": declared,
                            **({"images_max": images} if images is not None else {}),
                            **({"partial": True} if partial else {}),
                            "method": "CMYK colour operators and images read from the file" + (
                                "; other content was not rendered (install pypdfium2)" if partial else "")}
    return facts


# PowerPoint ------------------------------------------------------------------------------------------------


def _pptx_facts(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        require(len(names) <= 20000, "The PowerPoint file has too many parts", "resource_limit")

        def read(name):
            info = archive.getinfo(name)
            require(info.file_size <= MAX_ZIP_ENTRY, f"{name} is too large to inspect", "resource_limit")
            return archive.read(name).decode("utf-8", "replace")

        slide_names = sorted((n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                             key=lambda n: int(re.search(r"(\d+)\.xml$", n)[1]))
        text_frames, slides_with_text, pictures, chart_refs = 0, 0, 0, 0
        for name in slide_names:
            xml = read(name)
            runs = [t for t in re.findall(r"<a:t>([^<]*)</a:t>", xml) if t.strip()]
            frames = len(re.findall(r"<p:txBody\b", xml))
            text_frames += frames if runs else 0
            slides_with_text += bool(runs)
            pictures += len(re.findall(r"<p:pic\b", xml))
            chart_refs += len(re.findall(r"<c:chart\b", xml))
        notes = sum(1 for n in names if re.fullmatch(r"ppt/notesSlides/notesSlide\d+\.xml", n)
                    and any(t.strip() for t in re.findall(r"<a:t>([^<]*)</a:t>", read(n))))
        charts = sum(1 for n in names if re.fullmatch(r"ppt/charts/chart\d+\.xml", n))
        fonts = sum(1 for n in names if n.startswith("ppt/fonts/"))
    return {"slides": len(slide_names), "pages": len(slide_names), "text_frames": text_frames,
            "slides_with_text": slides_with_text, "pictures": pictures, "charts": charts, "chart_frames": chart_refs,
            "notes": notes, "embedded_fonts": fonts}


# HTML and SVG ----------------------------------------------------------------------------------------------

URL_IN_CSS = re.compile(r"""url\(\s*['"]?([^'")\s]+)|@import\s+['"]([^'"]+)""", re.I)
RESOURCE_ATTRS = {"src", "srcset", "data", "poster", "background"}


def _classify(url):
    url = url.strip()
    lowered = url.lower()
    if not url or lowered.startswith(("data:", "#", "blob:", "about:", "javascript:", "mailto:", "tel:")):
        return None
    return "remote" if lowered.startswith(("http:", "https:", "//", "ftp:")) else "file"


class _References(HTMLParser):
    """Resources a page loads (src, srcset, link/image/use href, CSS url and @import) and the links it shows."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.resources, self.links, self.notes, self.texts, self.slides, self.title = [], [], 0, 0, 0, None
        self._style = False
        self._title = False
        self._notes_depth = 0
        self.note_text = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        tag = tag.lower()
        classes = (attrs.get("class") or "").split()
        if tag == "aside" and "notes" in classes:
            self.notes += 1
        if tag == "section" and "slide" in classes:
            self.slides += 1
        if tag == "text":
            self.texts += 1
        if tag == "style":
            self._style = True
        if tag == "title":
            self._title = True
        for key, value in attrs.items():
            if value is None:
                continue
            key = key.lower()
            if key in RESOURCE_ATTRS:
                for part in (value.split(",") if key == "srcset" else [value]):
                    url = part.strip().split(" ")[0]
                    if _classify(url):
                        self.resources.append((tag, url))
            elif key in ("href", "xlink:href"):
                if tag == "a":
                    if _classify(value):
                        self.links.append(value)
                elif tag != "base" and (tag != "link" or "stylesheet" in (attrs.get("rel") or "").lower()
                                        or "icon" in (attrs.get("rel") or "").lower()
                                        or "preload" in (attrs.get("rel") or "").lower()
                                        or tag in ("image", "use", "feimage", "script")):
                    if _classify(value):
                        self.resources.append((tag, value))
            elif key == "style":
                self._css(tag, value)

    def handle_endtag(self, tag):
        if tag.lower() == "style":
            self._style = False
        if tag.lower() == "title":
            self._title = False

    def handle_data(self, data):
        if self._style:
            self._css("style", data)
        if self._title and data.strip():
            self.title = (self.title or "") + data.strip()

    def _css(self, tag, text):
        for match in URL_IN_CSS.finditer(text):
            url = match[1] or match[2]
            if _classify(url):
                self.resources.append((tag, url))


def _reference_facts(parser):
    resources = list(dict.fromkeys(url for _, url in parser.resources))
    return {"external": [{"url": url[:300], "kind": _classify(url)} for url in resources[:MAX_LISTED]],
            "external_count": len(resources),
            "remote": sum(1 for url in resources if _classify(url) == "remote"),
            "links": len(set(parser.links))}


def _html_facts(data):
    parser = _References()
    parser.feed(data.decode("utf-8", "replace"))
    parser.close()
    return {**_reference_facts(parser), "notes": parser.notes, "slides": parser.slides, "pages": parser.slides or 1,
            "svg_text": parser.texts, **({"title": parser.title[:200]} if parser.title else {})}


def _svg_facts(data):
    upper = data.upper()
    require(b"<!DOCTYPE" not in upper and b"<!ENTITY" not in upper,
            "The SVG declares a DOCTYPE or entities; Vixl does not read those", "invalid_image", field="path")
    from xml.etree import ElementTree

    root = ElementTree.fromstring(data)
    facts = {"color": {"space": "RGB", "vector": True}}
    if root.get("viewBox"):
        facts["view_box"] = root.get("viewBox")
    sizes = [re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?:px)?\s*", root.get(side) or "") for side in ("width", "height")]
    box = (root.get("viewBox") or "").replace(",", " ").split()
    if all(sizes):
        facts.update(width=float(sizes[0][1]), height=float(sizes[1][1]))
    elif len(box) == 4:
        try:
            facts.update(width=float(box[2]), height=float(box[3]))
        except ValueError:
            pass
    parser = _References()
    parser.feed(data.decode("utf-8", "replace"))
    parser.close()
    images = sum(1 for element in root.iter() if element.tag.rsplit("}", 1)[-1] == "image")
    return {**facts, **_reference_facts(parser), "text_elements": parser.texts, "images": images}


# ------------------------------------------------------------------------------------------------- verify


def expectations(project, report=None):
    """What a file exported from ``project`` should contain, for the spec fields that depend on the document:
    visible text and chart layers, and the page or slide count the exporter reported."""
    layers = [layer for layer in project.state["layers"] if layer.get("visible", True)]
    for page in project.state.get("pages") or []:
        # Inactive pages keep their layers in ``content``; the active page's are the document's own.
        layers += [layer for layer in (page.get("content") or {}).get("layers", []) if layer.get("visible", True)]
    expect = {"text": sum(1 for layer in layers if layer.get("type") == "text"),
              "charts": sum(1 for layer in layers if "chart" in layer)}
    report = report or {}
    for key in ("pages", "slides"):
        if isinstance(report.get(key), int):
            expect["pages"] = report[key]
    return expect


def verify(path, spec=None, *, data=None, limits=None, expect=None, facts=None):
    """Check one exported file against a delivery ``spec`` (a preset name, inline fields or ``None`` for the
    ``default`` checks). ``expect`` (``expectations(project)``) lets the document-dependent fields know how much
    text, how many charts and pages the file should hold. Returns ``{passed, spec, requirements, issues, facts,
    outcome}``; issues use the checks.py shape with ``check: "export"``."""
    name, fields = resolve_spec(spec)
    facts = facts or inspect(path, data=data, limits=limits, ink=fields.get("ink_limit") is not None)
    expect = expect or {}
    issues = []
    unmeasured = []

    def issue(code, message, severity="error", **extra):
        action = "fix" if severity == "error" else "review"
        issues.append({"check": CHECK, "code": code, "rule": f"{CHECK}.{code}", "severity": severity,
                       "action": action, "layers": [], "message": message, **extra})

    def cannot(field, why):
        unmeasured.append(field)
        issue("unmeasured", f"{field} could not be measured: {why}", "warning", field=field)

    fmt = SAME.get(facts["format"], facts["format"])
    content = facts.get("content_format")
    if facts.get("unreadable"):
        issue("unreadable", f"The file could not be read as {facts['format']}: {facts['unreadable']}")
    if content:
        issue("format-mismatch", f"The file is named .{fmt} but holds {content.upper()} data", expected=fmt,
              actual=content)
    if fields.get("formats"):
        allowed = list(dict.fromkeys(SAME.get(f.lower().lstrip("."), f.lower().lstrip(".")) for f in fields["formats"]))
        if fmt not in allowed:
            issue("format", f"The file is {fmt.upper()}; the spec wants {', '.join(f.upper() for f in allowed)}",
                  expected=allowed, actual=fmt)
    if fields.get("max_bytes") and facts["bytes"] > fields["max_bytes"]:
        issue("max-bytes", f"The file is {facts['bytes']:,} bytes, over the {fields['max_bytes']:,}-byte budget",
              expected=fields["max_bytes"], actual=facts["bytes"])
    if not facts.get("unreadable"):
        if fmt == "pdf":
            _verify_pdf(facts, fields, expect, issue, cannot)
        elif fmt in RASTER:
            _verify_raster(facts, fields, issue, cannot)
        elif fmt == "pptx":
            _verify_pptx(facts, fields, expect, issue)
        elif fmt in ("html", "svg"):
            _verify_web(fmt, facts, fields, expect, issue)
    if fields.get("pages") is not None and isinstance(facts.get("pages"), int):
        low, high = (fields["pages"], fields["pages"]) if isinstance(fields["pages"], int) else fields["pages"]
        if not low <= facts["pages"] <= high:
            issue("pages", f"The file has {facts['pages']} page(s); the spec wants "
                  + (f"{low}" if low == high else f"{low}-{high}"), expected=fields["pages"], actual=facts["pages"])
    if isinstance(expect.get("pages"), int) and isinstance(facts.get("pages"), int) and fmt in ("pdf", "pptx") \
            and expect["pages"] != facts["pages"]:
        issue("page-count", f"The exporter wrote {expect['pages']} page(s) but the file has {facts['pages']}",
              expected=expect["pages"], actual=facts["pages"])
    return report(path, name, fields, facts, issues, unmeasured)


def report(path, name, fields, facts, issues, unmeasured=()):
    from .outcomes import make

    fixes = [item for item in issues if item["action"] == "fix"]
    reasons = [item["message"] for item in issues if item["action"] == "review"]
    validation = "failed" if fixes else "incomplete" if unmeasured else "passed"
    return {"path": str(path), "format": facts["format"], "spec": name, "requirements": fields,
            "passed": not fixes, "errors": len(fixes), "warnings": len(issues) - len(fixes), "issues": issues,
            "facts": facts,
            "outcome": make("completed", validation, reasons, validated_by=[f"export check ({name})"])}


def _verify_pdf(facts, fields, expect, issue, cannot):
    if fields.get("fonts_embedded") and facts.get("fonts_unembedded"):
        names = facts["fonts_unembedded"]
        issue("font-not-embedded", f"{len(names)} font(s) are not embedded: {', '.join(names[:5])}; printers and "
              "other computers substitute them", fonts=names[:MAX_LISTED])
    trim = trim_points(fields["trim"]) if fields.get("trim") is not None else None
    bleed = length_points(fields["bleed"], "bleed") if fields.get("bleed") is not None else None
    for page in facts.get("page_boxes", []):
        number = page["number"]
        trim_box = page.get("trim_box")
        bleed_box = page.get("bleed_box")
        media = page.get("media_box")
        if bleed:
            if not trim_box or not bleed_box:
                missing = [n for n, box in (("TrimBox", trim_box), ("BleedBox", bleed_box)) if not box]
                issue("bleed-box", f"Page {number} has no {' or '.join(missing)}; a press needs both to cut the "
                      f"{bleed:g} pt bleed", page=number, expected=round(bleed, 3))
            else:
                sides = [trim_box[0] - bleed_box[0], trim_box[1] - bleed_box[1], bleed_box[2] - trim_box[2],
                         bleed_box[3] - trim_box[3]]
                if any(abs(side - bleed) > TOLERANCE_PT for side in sides):
                    issue("bleed-box", f"Page {number} bleeds {', '.join(f'{s:g}' for s in sides)} pt "
                          f"(left, bottom, right, top); the spec wants {bleed:g} pt on every side", page=number,
                          expected=round(bleed, 3), actual=[round(s, 3) for s in sides])
                if media and (media[0] > bleed_box[0] + TOLERANCE_PT or media[1] > bleed_box[1] + TOLERANCE_PT
                              or media[2] < bleed_box[2] - TOLERANCE_PT or media[3] < bleed_box[3] - TOLERANCE_PT):
                    issue("bleed-box", f"Page {number}'s MediaBox is smaller than its BleedBox", page=number)
        elif bleed == 0 and bleed_box and trim_box and bleed_box != trim_box:
            issue("bleed-box", f"Page {number} has a bleed; the spec wants none", page=number)
        if trim:
            size = _size(trim_box or (None if bleed else media))
            if size is None:
                continue
            if not any(abs(size[0] - w) <= TOLERANCE_PT and abs(size[1] - h) <= TOLERANCE_PT
                       for w, h in (trim, trim[::-1])):
                issue("trim-size", f"Page {number} trims to {size[0]:g} × {size[1]:g} pt; the spec wants "
                      f"{trim[0]:g} × {trim[1]:g} pt", page=number, expected=[round(v, 3) for v in trim], actual=size)
    color = fields.get("color")
    spaces = set((facts.get("color") or {}).get("color_spaces", []))
    if color == "cmyk" and "DeviceRGB" in spaces:
        issue("color", "The PDF uses RGB colour; the spec wants CMYK (export with color_space='cmyk')",
              expected="cmyk", actual=sorted(spaces))
    elif color == "rgb" and "DeviceCMYK" in spaces:
        issue("color", "The PDF uses CMYK colour; the spec wants RGB", expected="rgb", actual=sorted(spaces))
    elif color == "gray" and spaces & {"DeviceRGB", "DeviceCMYK"}:
        issue("color", "The PDF uses colour; the spec wants grayscale", expected="gray", actual=sorted(spaces))
    if fields.get("ink_limit") is not None:
        ink = facts.get("ink")
        if not ink:
            cannot("ink_limit", "rendering PDF pages needs pypdfium2 (pip install 'vixl-engine[pdf]')")
        else:
            if ink["max"] > fields["ink_limit"] + 0.5:
                issue("ink-limit", f"Total ink reaches {ink['max']:g}% (limit {fields['ink_limit']:g}%); use a "
                      "lighter rich black or export with ink_limit", expected=fields["ink_limit"], actual=ink["max"])
            if ink.get("partial"):
                cannot("ink_limit", "RGB content was not rendered without pypdfium2")
    if fields.get("fillable") is not None:
        count = (facts.get("forms") or {}).get("fields", 0)
        if fields["fillable"] and not count:
            issue("fillable", "The PDF has no form fields; the spec wants a fillable form (export with fillable)",
                  expected=True, actual=0)
        elif not fields["fillable"] and count:
            issue("fillable", f"The PDF has {count} form field(s); the spec wants a flat PDF", expected=False,
                  actual=count)


def _verify_raster(facts, fields, issue, cannot):
    width, height = facts["width"], facts["height"]
    for key, actual in (("width", width), ("height", height)):
        if fields.get(key) and actual != fields[key]:
            issue("size", f"The image is {width} × {height} px; the spec wants {key} {fields[key]} px",
                  expected={key: fields[key]}, actual=[width, height])
        if fields.get("min_" + key) and actual < fields["min_" + key]:
            issue("size", f"The image is {width} × {height} px; the spec wants {key} at least "
                  f"{fields['min_' + key]} px", expected={"min_" + key: fields["min_" + key]}, actual=[width, height])
    if fields.get("sizes") and [width, height] not in [list(s) for s in fields["sizes"]]:
        issue("size", f"{width} × {height} px is not one of the spec's sizes "
              f"({', '.join(f'{w}×{h}' for w, h in fields['sizes'])})", expected=fields["sizes"], actual=[width, height])
    if fields.get("aspect"):
        low, high = fields["aspect"]
        ratio = width / height
        if not low - 0.005 <= ratio <= high + 0.005:
            issue("aspect", f"The image's width/height is {ratio:.3f}; the spec allows {low:g}-{high:g}",
                  expected=fields["aspect"], actual=round(ratio, 4))
    if fields.get("dpi"):
        if not facts.get("dpi"):
            issue("dpi", f"The file records no resolution; the spec wants at least {fields['dpi']:g} dpi (export with "
                  "dpi)", expected=fields["dpi"])
        elif facts["dpi"] + 0.01 < fields["dpi"]:
            issue("dpi", f"The file records {facts['dpi']:g} dpi; the spec wants at least {fields['dpi']:g}",
                  expected=fields["dpi"], actual=facts["dpi"])
    color_facts = facts.get("color") or {}
    if fields.get("alpha") is True and not color_facts.get("alpha"):
        issue("alpha", "The image has no alpha channel; the spec wants transparency (export with alpha='keep')",
              expected=True, actual=False)
    elif fields.get("alpha") is False and color_facts.get("alpha"):
        issue("alpha", "The image has an alpha channel; the spec wants an opaque image (export with alpha='flatten')",
              expected=False, actual=True)
    if fields.get("icc") is True and not color_facts.get("icc_profile"):
        issue("icc", "No ICC profile is embedded; the spec wants one", expected=True, actual=False)
    elif fields.get("icc") is False and color_facts.get("icc_profile"):
        issue("icc", "An ICC profile is embedded; the spec wants none", expected=False, actual=True)
    color, space = fields.get("color"), color_facts.get("space")
    if color and space != _space(color) and not (color == "rgb" and space == "Gray"):
        issue("color", f"The image is {color_facts.get('mode')}; the spec wants {_space(color)}", expected=color,
              actual=space)
    if fields.get("ink_limit") is not None:
        if space != "CMYK":
            cannot("ink_limit", "ink coverage is measured on CMYK files; this one is " + str(color_facts.get("mode")))
        elif facts.get("ink") and facts["ink"]["max"] > fields["ink_limit"] + 0.5:
            issue("ink-limit", f"Total ink reaches {facts['ink']['max']:g}% (limit {fields['ink_limit']:g}%)",
                  expected=fields["ink_limit"], actual=facts["ink"]["max"])


def _verify_pptx(facts, fields, expect, issue):
    if fields.get("editable_text") and expect.get("text") and not facts.get("text_frames"):
        issue("editable-text", f"The document has {expect['text']} text layer(s) but no slide keeps editable text; "
              "they were drawn as pictures", expected=expect["text"], actual=0)
    wanted = fields.get("native_charts")
    if wanted is True:
        wanted = expect.get("charts") or 0
    if wanted and facts.get("charts", 0) < wanted:
        issue("native-charts", f"The deck has {facts.get('charts', 0)} native chart(s); the spec wants {wanted}",
              expected=wanted, actual=facts.get("charts", 0))


def _verify_web(fmt, facts, fields, expect, issue):
    if fields.get("self_contained") and facts.get("external_count"):
        remote = [item["url"] for item in facts["external"] if item["kind"] == "remote"]
        files = [item["url"] for item in facts["external"] if item["kind"] == "file"]
        if remote:
            issue("remote-resource", f"The {fmt.upper()} loads {facts['remote']} resource(s) from the network: "
                  f"{', '.join(remote[:3])}", urls=remote)
        if files:
            issue("linked-file", f"The {fmt.upper()} loads {len(files)} file(s) that are not inside it: "
                  f"{', '.join(files[:3])}", urls=files)
    if fmt == "html" and fields.get("notes") is not None:
        if fields["notes"] and not facts.get("notes"):
            issue("notes", "The HTML has no speaker notes; the spec wants them", expected=True, actual=0)
        elif not fields["notes"] and facts.get("notes"):
            issue("notes", f"The HTML carries {facts['notes']} speaker note(s); the spec wants none", expected=False,
                  actual=facts["notes"])
    if fmt == "svg" and fields.get("text_as_text"):
        wanted = expect.get("text", 1)
        if wanted and not facts.get("text_elements"):
            issue("text-as-text", "The SVG has no <text> elements: its text was drawn as shapes or pictures",
                  expected=wanted, actual=0)


# ------------------------------------------------------------------------------------------------- wiring


def after_export(project, data, path, format, report, check, spec, options):
    """The export check for an export that wrote ``data``: the spec (``check=True`` alone: the default preset),
    with the export's own ``max_bytes`` and ``fillable`` as requirements when the spec leaves them out."""
    if not check and spec is None:
        return None
    name, fields = resolve_spec(spec)
    inline = dict(fields)
    if options.get("max_bytes") and "max_bytes" not in inline:
        inline["max_bytes"] = options["max_bytes"]
    if options.get("fillable") and "fillable" not in inline:
        inline["fillable"] = True
    suffix = Path(path).suffix if path else "." + {"jpeg": "jpg", "htm": "html"}.get(
        (format or "png").lower(), (format or "png").lower())
    result = verify(Path(path) if path else Path("export" + suffix), inline, data=data, limits=project.limits,
                    expect=expectations(project, report))
    result["spec"] = name
    result["outcome"]["validated_by"] = [f"export check ({name})"]
    if path is None:
        result.pop("path")
    return result


def cli(args, limits):
    from .commands import Parser

    parser = Parser(prog="vixl check-file", description="Read an exported file back and check it against a delivery "
                    "spec: PDF pages, boxes, fonts, colour, ink and forms; raster size, dpi, ICC and alpha; PowerPoint "
                    "text and charts; HTML and SVG references. Read-only.")
    parser.add_argument("file", nargs="?")
    parser.add_argument("--spec", help=f"A preset ({', '.join(presets())}) or inline JSON fields "
                                       "(default: the default preset)")
    parser.add_argument("--document", help="The .vixl it was exported from, so text and chart counts are known")
    parser.add_argument("--list", action="store_true", help="List the delivery spec presets")
    a = parser.parse_args(args)
    if a.list:
        return {"specs": {name: entry.get("description", "") for name, entry in presets().items()},
                "fields": SPEC_FIELDS}
    require(a.file, "Give the exported file to check: vixl check-file FILE [--spec NAME]", "usage_error", field="file")
    spec = a.spec
    if spec and spec.lstrip().startswith("{"):
        try:
            spec = json.loads(spec)
        except ValueError as exc:
            raise VixlError("usage_error", f"--spec is not valid JSON: {exc}", field="spec") from exc
    expect = None
    if a.document:
        from .project import Project

        expect = expectations(Project.load(a.document, limits=limits))
    return verify(a.file, spec, limits=limits, expect=expect)
