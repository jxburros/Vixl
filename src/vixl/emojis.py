"""Offline Unicode emoji art, portable document overrides and destination-ready packs."""

from copy import deepcopy
from functools import lru_cache
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
import zipfile
import xml.etree.ElementTree as ET

from .errors import require, VixlError

DATA = Path(__file__).parent / "data" / "emojis"
CONTEXT = b"VIXL-EMOJI-CONTEXT\0"
GLYPH = b"VIXL-EMOJI-GLYPH\0"
SVG = "{http://www.w3.org/2000/svg}"
SHORTCODE = re.compile(r":[a-zA-Z0-9_+-]{2,64}:")
TYPES = ("emoji-mode", "emoji-set", "emoji-reset")

DESTINATIONS = {
    "images": {
        "size": 128,
        "max_bytes": None,
        "name_pattern": r"[a-z0-9_]{2,64}",
        "description": "Portable PNG + SVG image pack, editable VIXL masters and an offline preview.",
        "instructions": "Open index.html to browse. Use PNG files in any image upload or SVG on the web.",
    },
    "discord": {
        "size": 128,
        "max_bytes": 256 * 1024,
        "name_pattern": r"[a-z0-9_]{2,32}",
        "description": "Static Discord custom emoji: 128×128 PNG, at most 256 KiB, 2–32 character names.",
        "url": "https://support.discord.com/hc/en-us/articles/360036479811-Custom-Emojis",
        "instructions": "Unzip, then open Server Settings → Emoji → Upload Emoji and select files from png/. "
        "You need Create Expressions or Manage Expressions permission. Server emoji slots "
        "and use outside the server depend on the server and your Discord plan.",
    },
    "slack": {
        "size": 128,
        "max_bytes": 128 * 1024,
        "name_pattern": r"[a-z0-9_]{2,64}",
        "description": "Static Slack custom emoji: 128×128 transparent PNG, at most 128 KiB.",
        "url": "https://slack.com/help/articles/206870177-Add-custom-emoji-and-aliases-to-your-workspace",
        "instructions": "Unzip, then open Slack’s emoji picker → Add Emoji → Upload Image. Select a PNG "
        "and use its filename as the name. Your workspace must allow custom emoji.",
    },
}


@lru_cache(maxsize=1)
def _catalog():
    return json.loads((DATA / "catalog.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _entries():
    return {e["id"]: e for e in _catalog()["entries"]}


@lru_cache(maxsize=1)
def _trie():
    root = {}
    for emoji, key in _catalog()["aliases"].items():
        branch = root
        for char in emoji:
            branch = branch.setdefault(char, {})
        branch[""] = key
    return root


def identifier(value):
    require(isinstance(value, str) and value, "Provide an emoji, Unicode hex sequence or :custom_name:")
    if SHORTCODE.fullmatch(value):
        return value
    if value in _catalog()["aliases"]:
        return _catalog()["aliases"][value]
    key = value.upper().replace("U+", "").replace(" ", "-")
    if key in _entries():
        return key
    raise VixlError("unknown_emoji", f"Unknown emoji: {value!r}; search with emoji-list")


def scan(text, overrides=None):
    """Longest qualified/variant sequence first; VS15 explicitly requests text presentation."""
    root, overrides = _trie(), overrides or {}
    result, i = [], 0
    while i < len(text):
        if text[i] == ":":
            match = SHORTCODE.match(text, i)
            if match and match[0] in overrides:
                result.append((i, match.end(), match[0]))
                i = match.end()
                continue
        branch, j, best = root, i, None
        while j < len(text) and text[j] in branch:
            branch = branch[text[j]]
            j += 1
            if "" in branch:
                key = branch[""]
                # Text-default symbols (arrows, ©, ♥) need VS16 unless explicitly overridden.
                if j - i > 1 or len(_entries()[key]["emoji"]) == 1 or key in overrides:
                    best = (i, j, key)
        if best and best[1] < len(text) and text[best[1]] == "\ufe0e":
            i = best[1] + 1
            continue
        # Ordinary digits, # and * are text; only their keycap sequences are emojis.
        if best and not (best[1] == i + 1 and text[i] in "#*0123456789"):
            result.append(best)
            i = best[1]
        else:
            i += 1
    return result


@lru_cache(maxsize=1)
def _archive(mtime, size):
    # ZipFile serializes seeks on its shared stream. Reuse its index across the thousands
    # of small assets; reopening the archive for every glyph made full-pack exports quadratic.
    return zipfile.ZipFile(DATA / "artwork.zip")


@lru_cache(maxsize=512)
def _bundled(key, kind, mtime, size):
    return _archive(mtime, size).read(f"{kind}/{key}.{kind}")


def bundled(key, kind="svg"):
    require(key in _entries() and kind in ("svg", "vixl"), "Unknown bundled emoji or format")
    stat = (DATA / "artwork.zip").stat()
    return _bundled(key, kind, stat.st_mtime_ns, stat.st_size)


def artwork(project, key, kind="svg"):
    override = project.state.get("emojis", {}).get("overrides", {}).get(key) if project else None
    if override:
        name = override.get("source") if kind == "vixl" else override["asset"]
        if name and (kind != "vixl" or override.get("format") == "vixl"):
            return project.assets[name]
        if kind == "vixl":
            return None
    return bundled(key, kind) if key in _entries() else None


def catalog(query="", group=None, offset=0, limit=100, project=None):
    require(isinstance(query, str), "query must be a string")
    require(
        type(offset) is int and offset >= 0 and type(limit) is int and 1 <= limit <= 500,
        "offset must be nonnegative and limit must be 1–500",
    )
    entries = list(_entries().values())
    overrides = project.state.get("emojis", {}).get("overrides", {}) if project else {}
    entries += [
        {"id": k, "emoji": k, "name": v.get("name", k.strip(":")), "group": "Custom", "tags": ""}
        for k, v in overrides.items()
        if k.startswith(":") and k not in _entries()
    ]
    rows = [
        dict(e, custom=e["id"] in overrides)
        for e in entries
        if (not group or e["group"] == group)
        and (
            not query
            or query.casefold() in " ".join((e["id"], e["emoji"], e["name"], e.get("tags", ""))).casefold()
        )
    ]
    return {
        "unicode_version": _catalog()["unicode_version"],
        "style": _catalog()["style"],
        "unicode_count": _catalog()["unicode_count"],
        "original_count": _catalog().get("original_count", _catalog()["reaction_count"]),
        "total": len(rows),
        "offset": offset,
        "entries": rows[offset : offset + limit],
        "next_offset": offset + limit if offset + limit < len(rows) else None,
        "groups": sorted({e["group"] for e in entries}),
    }


def schemas(add):
    from .schema import S, field

    add(
        "emoji-mode",
        {
            "mode": {
                "type": "string",
                "enum": ["vixl", "font"],
                "description": "vixl (default): bundled art. font: prefer the font; missing sequences still use bundled art.",
            }
        },
        ["mode"],
        description="Choose document emoji rendering; custom overrides always win.",
    )
    add(
        "emoji-set",
        {
            "emoji": field(S, "Unicode emoji, hex sequence, or a new :custom_name: shortcode."),
            "data": field(
                S, "Base64-encoded VIXL master, SVG geometry or PNG image; embedded in the document."
            ),
            "format": {
                "type": "string",
                "enum": ["vixl", "svg", "png"],
                "description": "Source file format.",
            },
            "appearance": field(
                S, "Optional base64 SVG appearance from an exported pack; source stays editable."
            ),
            "name": field(S, "Optional destination name, normalized during export."),
            "license": field(S, "License for this artwork; default unspecified for original user artwork."),
        },
        ["emoji", "data", "format"],
        description="Replace one emoji or register a custom shortcode with portable art.",
    )
    add(
        "emoji-reset",
        {"emoji": field(S, "Emoji or shortcode to reset; omitted removes all overrides.")},
        description="Remove custom artwork and restore bundled emoji rendering.",
    )


def _asset(project, data, ext):
    require(len(data) <= project.limits.max_asset_bytes, "Emoji asset exceeds byte limit", "resource_limit")
    name = ("sources/" if ext == "svg" else "emoji-sources/") + hashlib.sha256(data).hexdigest() + "." + ext
    project.assets[name] = data
    return name


def load_master(raw, limits):
    require(len(raw) <= limits.max_asset_bytes, "Emoji master exceeds byte limit", "resource_limit")
    from .project import Project

    with tempfile.TemporaryDirectory(prefix="vixl-emoji-") as tmp:
        path = Path(tmp) / "source.vixl"
        path.write_bytes(raw)
        project = Project.load(path, limits=limits)
    # Pack imports are portable and must not open fonts or sources from the host filesystem.
    from .richtext import fonts_used

    for layer in project.state["layers"]:
        require(
            layer["type"] != "link" and not layer.get("linked"), "Embed linked sources before using an emoji"
        )
        if layer["type"] == "text":
            require(
                all(
                    f == "DejaVuSans.ttf" or f in project.state.get("fonts", {}) or f in project.assets
                    for f in fonts_used(layer)
                ),
                "Embed emoji master fonts before importing",
            )
    project.path = None
    return project


def source_svg(raw, format, limits):
    from .project import Project
    from .svg import export_svg

    if format == "vixl":
        project = load_master(raw, limits)
        w, h = project.state["canvas"]["width"], project.state["canvas"]["height"]
        svg = export_svg(project)
        svg = svg.encode() if isinstance(svg, str) else svg
    elif format == "svg":
        project = Project(72, 72, background="transparent", limits=limits)
        from .imports import svg_operations

        project.apply(svg_operations(raw, project, "emoji"))
        svg = export_svg(project)
        svg = svg.encode() if isinstance(svg, str) else svg
        w = h = 72
    else:
        from .assets import decode

        image = decode(raw, limits)
        w, h = image.size
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}"><image width="{w}" height="{h}" href="{uri}"/></svg>'.encode()
    require(w > 0 and h > 0, "Emoji source must have a positive canvas")
    # Isolated viewport makes every source fit one em, preserving its own aspect ratio.
    root = ET.Element(SVG + "svg", {"width": "72", "height": "72", "viewBox": "0 0 72 72"})
    nested = ET.fromstring(svg)
    nested.set("x", "0")
    nested.set("y", "0")
    nested.set("width", "72")
    nested.set("height", "72")
    nested.set("viewBox", f"0 0 {w} {h}")
    nested.set("preserveAspectRatio", "xMidYMid meet")
    root.append(nested)
    return ET.tostring(root, encoding="utf-8")


def execute(project, op):
    require("target" not in op, "Emoji operations are document-wide")
    settings = project.state.setdefault("emojis", {"mode": "vixl", "overrides": {}})
    if op["type"] == "emoji-mode":
        settings["mode"] = op["mode"]
    elif op["type"] == "emoji-reset":
        if op.get("emoji"):
            settings["overrides"].pop(identifier(op["emoji"]), None)
        else:
            settings["overrides"] = {}
    else:
        key = identifier(op["emoji"])
        try:
            require(
                len(op["data"]) <= (project.limits.max_asset_bytes * 4 // 3 + 8),
                "Emoji source exceeds byte limit",
                "resource_limit",
            )
            raw = base64.b64decode(op["data"], validate=True)
        except ValueError as exc:
            raise VixlError("invalid_operation", "Emoji data must be valid base64") from exc
        svg = source_svg(raw, op["format"], project.limits)
        if op.get("appearance"):
            try:
                svg = base64.b64decode(op["appearance"], validate=True)
            except ValueError as exc:
                raise VixlError("invalid_operation", "Emoji appearance must be base64 SVG") from exc
            safe_svg(svg, project.limits)
        license = op.get("license", "unspecified")
        provenance = {}
        if op["format"] == "vixl":
            provenance = load_master(raw, project.limits).state.get("emoji_artwork", {})
            license = provenance.get("license", license)
        settings["overrides"][key] = {
            "asset": _asset(project, svg, "svg"),
            "source": _asset(project, raw, op["format"]),
            "format": op["format"],
            "name": op.get("name", key.strip(":")),
            "license": license,
            "author": provenance.get("author", "User supplied"),
            "source_origin": provenance.get("source", "User supplied"),
        }
    # Plain auto-size boxes depend on emoji advances, including newly registered shortcodes.
    from .render import text_metrics

    for layer in project.state["layers"]:
        if layer["type"] == "text" and not layer.get("text_layout"):
            layer["width"], layer["height"], _ = text_metrics(project, layer)
    return {"mode": settings["mode"], "overrides": len(settings["overrides"])}


def safe_svg(raw, limits):
    require(
        len(raw) <= min(limits.max_asset_bytes, 4 * 1024 * 1024),
        "Emoji SVG exceeds byte limit",
        "resource_limit",
    )
    require(
        b"<!DOCTYPE" not in raw.upper() and b"<!ENTITY" not in raw.upper(),
        "SVG entities are unavailable in emoji artwork",
        "invalid_project",
    )
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise VixlError("invalid_project", "Invalid emoji SVG") from exc
    require(root.tag == SVG + "svg", "Expected an emoji SVG root", "invalid_project")
    count = 0
    for node in root.iter():
        count += 1
        require(count <= 20000, "Emoji SVG is too complex", "resource_limit")
        tag = node.tag.rsplit("}", 1)[-1]
        require(
            tag not in ("script", "foreignObject", "a", "style", "text"),
            "Emoji SVG must contain inert image or vector geometry",
            "invalid_project",
        )
        for key, value in node.attrib.items():
            attr = key.rsplit("}", 1)[-1]
            require(
                not attr.lower().startswith("on"), "SVG event handlers are unavailable", "invalid_project"
            )
            if attr in ("href", "src"):
                require(
                    value.startswith("#") or value.startswith("data:image/png;base64,"),
                    "Emoji SVG cannot reference external resources",
                    "invalid_project",
                )
            if attr in ("href", "src") and value.startswith("data:image/png;base64,"):
                try:
                    image_data = base64.b64decode(value.split(",", 1)[1], validate=True)
                except ValueError as exc:
                    raise VixlError("invalid_project", "Invalid emoji image data") from exc
                from .assets import image_size

                limits.size(*image_size(image_data, limits))
            for url in re.findall(r"url\(([^)]+)\)", value, flags=re.IGNORECASE):
                require(
                    url.strip().startswith("#"),
                    "Emoji SVG cannot reference external paints",
                    "invalid_project",
                )
    return root


def validate(project):
    settings = project.state.get("emojis")
    if settings is None:
        return
    require(
        isinstance(settings, dict)
        and settings.get("mode") in ("vixl", "font")
        and isinstance(settings.get("overrides"), dict)
        and len(settings["overrides"]) <= 5000,
        "Invalid emoji settings",
        "invalid_project",
    )
    for key, entry in settings["overrides"].items():
        require(
            identifier(key) == key and isinstance(entry, dict), "Invalid emoji override", "invalid_project"
        )
        safe_svg(project.assets.get(entry.get("asset"), b""), project.limits)
        require(
            entry.get("format") in ("vixl", "svg", "png")
            and entry.get("asset") in project.assets
            and entry.get("source") in project.assets,
            "Missing emoji source asset",
            "invalid_project",
        )


def with_emojis(project, data, text):
    """A content-addressed shaping context; includes artwork so caches track replacement/undo."""
    fonts = data if isinstance(data, tuple) else (data,)
    settings = project.state.get("emojis", {})
    spans = scan(text, settings.get("overrides"))
    if not spans:
        return data
    selected = {}
    for a, b, key in spans:
        if (
            settings.get("mode", "vixl") == "font"
            and key not in settings.get("overrides", {})
            and not key.startswith(":")
        ):
            if font_supports(fonts, text[a:b]):
                continue
        selected[text[a:b]] = base64.b64encode(artwork(project, key)).decode()
    if not selected:
        return data
    from .text import face, primary_font_data, UnsupportedText

    safe_fonts = []
    for font in fonts:
        try:
            face(font)
            safe_fonts.append(font)
        except UnsupportedText:
            pass
    if not safe_fonts:
        safe_fonts = [primary_font_data(project, {"font": "DejaVuSans.ttf", "size": 12})]
    return (*safe_fonts, CONTEXT + json.dumps(selected, sort_keys=True).encode())


def font_supports(fonts, text):
    """Require the whole sequence to shape; cmap coverage alone cannot prove ZWJ support."""
    import uharfbuzz as hb
    from .text import coverage, visible_char, face, UnsupportedText

    for data in fonts:
        try:
            face(data)
        except UnsupportedText:
            continue
        if not all(not visible_char(c) or ord(c) in coverage(data) for c in text):
            continue
        font = hb.Font(hb.Face(data))
        hb.ot_font_set_funcs(font)
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(font, buf)
        if any(g.codepoint == 0 for g in buf.glyph_infos):
            continue
        if (
            "\u200d" in text
            or any(0x1F1E6 <= ord(c) <= 0x1F1FF for c in text)
            or "\u20e3" in text
            or any(0xE0020 <= ord(c) <= 0xE007F for c in text)
            or any(0x1F3FB <= ord(c) <= 0x1F3FF for c in text)
        ) and len(buf.glyph_infos) != 1:
            continue
        return True
    return False


@lru_cache(maxsize=128)
def context(data):
    return {k: GLYPH + base64.b64decode(v) for k, v in json.loads(data[len(CONTEXT) :]).items()}


def is_glyph(data):
    return isinstance(data, bytes) and data.startswith(GLYPH)


def is_context(data):
    return isinstance(data, bytes) and data.startswith(CONTEXT)


class EmojiArt(str):
    """An SVG glyph in font coordinates (72 units, baseline at y=58)."""


class EmojiFace(dict):
    def getBestCmap(self):
        return {}


EMOJI_FACE = EmojiFace(head=SimpleNamespace(unitsPerEm=72), hhea=SimpleNamespace(ascent=58, descent=-14))


def append_art(parent, art, matrix, opacity=1):
    group = ET.SubElement(
        parent,
        SVG + "g",
        {"transform": "matrix(" + " ".join(map(str, matrix)) + ")", "opacity": str(opacity)},
    )
    # Font-space inversion is cancelled inside the SVG, so the rest of text layout is shared.
    inner = ET.SubElement(group, SVG + "g", {"transform": "translate(0 58) scale(1 -1)"})
    root = ET.fromstring(art)
    prefix = "emoji-" + hashlib.sha256((str(art) + repr(matrix)).encode()).hexdigest()[:12] + "-"
    ids = {node.get("id"): prefix + node.get("id") for node in root.iter() if node.get("id")}
    for node in root.iter():
        if node.get("id"):
            node.set("id", ids[node.get("id")])
        for key, value in list(node.attrib.items()):
            for old, new in ids.items():
                value = value.replace("url(#" + old + ")", "url(#" + new + ")")
                if key.rsplit("}", 1)[-1] == "href" and value == "#" + old:
                    value = "#" + new
            node.set(key, value)
    inner.append(root)


def split_context(data, text):
    """Protect entire emoji sequences before bidi's X9 drops joiners and flag tag characters."""
    fonts = data if isinstance(data, tuple) else (data,)
    if not is_context(fonts[-1]):
        return fonts, text, {}
    choices = context(fonts[-1])
    names = sorted(choices, key=len, reverse=True)
    placeholders = {}
    point = 0xF0000
    for name in names:
        while chr(point) in text:
            point += 1
        placeholders[chr(point)] = (name, choices[name])
        point += 1
    reverse = {name: char for char, (name, _) in placeholders.items()}
    pattern = re.compile("|".join(re.escape(n) for n in names))
    return fonts[:-1], pattern.sub(lambda m: reverse[m[0]], text), placeholders


def names_for(keys, project=None):
    overrides = project.state.get("emojis", {}).get("overrides", {}) if project else {}
    result, used = {}, set()
    for key in keys:
        name = overrides.get(key, {}).get("name") or _entries().get(key, {}).get("name", key.strip(":"))
        name = re.sub("[^a-z0-9_]+", "_", name.lower()).strip("_")[:24] or "emoji"
        if len(name) < 2:
            name = "emoji_" + name
        base = name
        suffix = 1
        while name in used:
            suffix += 1
            name = f"{base}_{suffix}"
        used.add(name)
        result[key] = name
    return result


def select(emojis=None, project=None):
    keys = [identifier(e) for e in emojis] if emojis is not None else list(_entries())
    if emojis is None and project:
        keys += [
            k
            for k in project.state.get("emojis", {}).get("overrides", {})
            if k.startswith(":") and k not in _entries()
        ]
    require(keys and len(keys) <= 5000 and len(keys) == len(set(keys)), "Select 1–5000 unique emojis")
    require(
        all(
            k in _entries() or k in (project.state.get("emojis", {}).get("overrides", {}) if project else {})
            for k in keys
        ),
        "Custom shortcode has no artwork",
    )
    return keys


def png(svg, size):
    import resvg_py

    root = ET.fromstring(svg)
    root.set("width", str(size))
    root.set("height", str(size))
    root.set("viewBox", "0 0 72 72")
    return resvg_py.svg_to_bytes(svg_string=ET.tostring(root, encoding="unicode"))


def requirements(destination="images", emojis=None, project=None):
    require(destination in DESTINATIONS, "Unknown emoji destination", allowed=list(DESTINATIONS))
    profile = DESTINATIONS[destination]
    keys = select(emojis, project)
    names = names_for(keys, project)
    entries = []
    for key in keys:
        raw = png(artwork(project, key), profile["size"])
        entries.append(
            {
                "id": key,
                "name": names[key],
                "size": [profile["size"]] * 2,
                "bytes": len(raw),
                "passed": (profile["max_bytes"] is None or len(raw) < profile["max_bytes"])
                and re.fullmatch(profile["name_pattern"], names[key]) is not None,
            }
        )
    return {
        "destination": destination,
        "profile": deepcopy(profile),
        "checked": "2026-10-08",
        "count": len(entries),
        "passed": all(e["passed"] for e in entries),
        "entries": entries,
        "note": "Checks image dimensions, encoded bytes and names. Account permissions and emoji slots are checked by the destination.",
    }


def export_pack(
    output, emojis=None, destination="images", project=None, sources=True, size=None, overwrite=False
):
    require(destination in DESTINATIONS, "Unknown emoji destination")
    require(type(sources) is bool and type(overwrite) is bool, "sources and overwrite must be boolean")
    profile = DESTINATIONS[destination]
    keys = select(emojis, project)
    size = profile["size"] if size is None else size
    require(type(size) is int and 16 <= size <= 1024, "Emoji export size must be 16–1024")
    require(destination == "images" or size == profile["size"], "Use the destination’s required export size")
    output = Path(output)
    require(output.suffix.lower() == ".zip", "Emoji pack output must end in .zip")
    require(overwrite or not output.exists(), "Emoji pack output already exists", "output_exists")
    names = names_for(keys, project)
    overrides = project.state.get("emojis", {}).get("overrides", {}) if project else {}
    # Spool large packs to disk; only one artwork and its PNG need to be decoded at a time.
    with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as buffer:
        entries = []
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
            for key in keys:
                svg = artwork(project, key)
                image = png(svg, size)
                name = names[key]
                require(
                    profile["max_bytes"] is None or len(image) < profile["max_bytes"],
                    f"{name} exceeds {destination} upload byte limit",
                )
                item = {
                    "id": key,
                    "name": name,
                    "image": f"png/{name}.png",
                    "svg": f"svg/{name}.svg",
                    "license": overrides.get(key, {}).get("license", "CC-BY-SA-4.0"),
                    "original_name": _entries().get(key, {}).get("name", name),
                    "kind": _entries().get(key, {}).get("kind", "custom"),
                    "unicode_sequence": _entries()[key]["emoji"] if not key.startswith(":") else None,
                    "codepoints": key.split("-") if not key.startswith(":") else [],
                    "shortcodes": [key] if key.startswith(":") else [],
                    "group": _entries().get(key, {}).get("group", "Custom"),
                    "category": _entries().get(key, {}).get("subgroup", "custom"),
                    "source_origin": overrides[key].get("source_origin", "User supplied")
                    if key in overrides
                    else _entries().get(key, {}).get("source", "User supplied"),
                    "author": overrides[key].get("author", "User supplied")
                    if key in overrides
                    else _entries().get(key, {}).get("author", "User supplied"),
                }
                z.writestr(item["image"], image)
                z.writestr(item["svg"], svg)
                if sources:
                    master = artwork(project, key, "vixl")
                    if master:
                        item["source"] = f"vixl/{name}.vixl"
                        z.writestr(item["source"], master)
                entries.append(item)
            manifest = {
                "version": 1,
                "unicode_version": _catalog()["unicode_version"],
                "style": _catalog()["style"],
                "destination": destination,
                "size": size,
                "entries": entries,
            }
            z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            z.writestr(
                "README.txt",
                profile["instructions"] + "\n\nSee manifest.json for Unicode mappings and licenses.\n"
                "VIXL Line is adapted from OpenMoji 17.0.0 (https://openmoji.org), CC BY-SA 4.0.\n"
                "Changes: softened geometric contours, navy outlines, reduced stroke width and a restrained palette; national flag colors preserved.\n"
                "VIXL Originals (faces, reactions and everyday symbols) are original VIXL artwork under CC BY-SA 4.0; see per-entry source_origin.\n"
                "Custom artwork retains the license stated in manifest.json.\nMade with Vixl.\n",
            )
            for name in ("LICENSE.txt", "UNICODE-LICENSE.txt"):
                z.writestr(name, (DATA / name).read_bytes())
            from html import escape

            cards = "".join(
                f'<figure><img src="{e["image"]}" alt="{escape(e["original_name"], quote=True)}">'
                f"<figcaption>:{escape(e['name'])}:</figcaption></figure>"
                for e in entries
            )
            z.writestr(
                "index.html",
                '<!doctype html><meta charset="utf-8"><title>VIXL Line emojis</title>'
                "<style>body{font:16px system-ui;background:#f7f5f0;color:#23364d;margin:32px}"
                "main{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:16px}"
                "figure{margin:0;padding:16px;background:white;border-radius:12px;text-align:center}"
                "img{width:72px;height:72px}figcaption{overflow-wrap:anywhere;font-size:12px}</style>"
                "<h1>VIXL Line</h1><p>" + escape(profile["instructions"]) + "</p><main>" + cards + "</main>",
            )
        buffer.seek(0)
        # Atomic publication, preserving the engine’s overwrite semantics.
        from .fileio import temporary
        import os

        output.parent.mkdir(parents=True, exist_ok=True)
        fd, staged = temporary(output.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                import shutil

                shutil.copyfileobj(buffer, stream)
                stream.flush()
                os.fsync(stream.fileno())
            if overwrite:
                os.replace(staged, output)
            else:
                os.link(staged, output)
        finally:
            if os.path.exists(staged):
                os.unlink(staged)
    return {
        "output": str(output),
        "count": len(keys),
        "destination": destination,
        "size": size,
        "sources": sources,
        "instructions": profile["instructions"],
    }


def install_pack(project, raw):
    require(len(raw) <= project.limits.max_project_bytes, "Emoji pack exceeds byte limit", "resource_limit")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            infos = z.infolist()
            require(
                len(infos) <= 20010 and len({i.filename for i in infos}) == len(infos),
                "Invalid emoji pack members",
            )
            require(
                sum(i.file_size for i in infos) <= project.limits.max_project_bytes,
                "Expanded emoji pack exceeds byte limit",
                "resource_limit",
            )
            manifest = json.loads(z.read("manifest.json"))
            require(
                isinstance(manifest, dict)
                and manifest.get("version") == 1
                and isinstance(manifest.get("entries"), list),
                "Unsupported emoji pack manifest",
            )
            entries = manifest["entries"]
            require(0 < len(entries) <= 5000, "Emoji pack must have 1–5000 entries")
            ops = []
            keys = set()
            for e in entries:
                require(isinstance(e, dict), "Invalid emoji pack entry")
                key = identifier(e.get("id"))
                require(key not in keys, "Duplicate emoji in pack")
                keys.add(key)
                name = e.get("source") or e.get("image")
                require(isinstance(name, str) and name in z.namelist(), "Missing emoji pack source")
                suffix = Path(name).suffix.lower().lstrip(".")
                require(suffix in ("vixl", "png", "svg"), "Unsupported emoji pack source format")
                info = z.getinfo(name)
                require(
                    info.file_size <= project.limits.max_asset_bytes,
                    "Emoji source exceeds byte limit",
                    "resource_limit",
                )
                ops.append(
                    {
                        "type": "emoji-set",
                        "emoji": key,
                        "format": suffix,
                        "data": base64.b64encode(z.read(name)).decode(),
                        **(
                            {"appearance": base64.b64encode(z.read(e["svg"])).decode()}
                            if e.get("svg") in z.namelist()
                            else {}
                        ),
                        "name": e.get("name", key),
                        "license": e.get("license", "unspecified"),
                    }
                )
            project.apply(ops, detail="compact")
            return {"installed": len(ops), "mode": project.state["emojis"]["mode"]}
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise VixlError("invalid_request", f"Invalid emoji pack: {exc}") from exc


def template(kind="blank", destination="images", limits=None):
    require(kind in ("blank", "face", "symbol", "sheet"), "Unknown emoji template")
    require(destination in DESTINATIONS, "Unknown emoji destination")
    from .project import Project

    project = Project(
        72 if kind != "sheet" else 288,
        72 if kind != "sheet" else 288,
        background="transparent",
        limits=limits,
    )
    project.state["emoji_template"] = {
        "kind": kind,
        "destination": destination,
        "safe_margin": 8,
        "stroke_width": 1.7,
        "ink": "#23364D",
        "help": "Keep distinctive features inside the 8 px safe area. Use 1.7 px navy strokes, straight sides "
        "and softly curved corners. Preserve small round details; do not snap everything to a grid. "
        "Preview at 24 and 32 px. Hide guides before exporting. Use emoji-replace to register your file.",
    }
    ops = []
    if kind == "face":
        ops = [
            {
                "type": "shape",
                "shape": "path",
                "path": "M27 13H45Q46 13 47 14L58 25Q59 26 59 27V45Q59 46 58 47L47 58Q46 59 45 59H27Q26 59 25 58L14 47Q13 46 13 45V27Q13 26 14 25L25 14Q26 13 27 13Z",
                "name": "face",
                "width": 72,
                "height": 72,
                "fill": "#F6CD70",
                "stroke": "#23364D",
                "stroke_width": 1.7,
            }
        ]
        for x in (27, 45):
            ops.append(
                {
                    "type": "shape",
                    "shape": "ellipse",
                    "name": f"eye-{x}",
                    "width": 4,
                    "height": 4,
                    "x": x - 2,
                    "y": 29,
                    "fill": "#23364D",
                }
            )
        ops.append(
            {
                "type": "shape",
                "shape": "path",
                "name": "expression",
                "width": 72,
                "height": 72,
                "path": "M25 42 Q36 54 47 42",
                "fill": "transparent",
                "stroke": "#23364D",
                "stroke_width": 1.7,
                "line_cap": "round",
                "line_join": "round",
            }
        )
    if kind == "symbol":
        ops = [
            {
                "type": "shape",
                "shape": "heart",
                "name": "symbol",
                "width": 42,
                "height": 40,
                "x": 15,
                "y": 17,
                "fill": "#DC7366",
                "stroke": "#23364D",
                "stroke_width": 1.7,
            }
        ]
    if kind == "sheet":
        for row in range(4):
            for col in range(4):
                ops.append(
                    {
                        "type": "shape",
                        "shape": "rectangle",
                        "name": f"guide-{row + 1}-{col + 1}",
                        "width": 56,
                        "height": 56,
                        "x": col * 72 + 8,
                        "y": row * 72 + 8,
                        "fill": "transparent",
                        "stroke": "#A0A9B3",
                        "stroke_width": 0.5,
                    }
                )
                ops.append(
                    {
                        "type": "layer-intent",
                        "target": f"guide-{row + 1}-{col + 1}",
                        "allow_overlap": [],
                        "role": "decoration",
                    }
                )
    if ops:
        project.apply(ops, detail="compact")
    return project
