"""Rebuild the pinned, offline VIXL Line emoji library from OpenMoji 17 and Unicode 17.

Usage: python scripts/build_emojis.py --sources /path/to/downloaded/sources
See docs/emojis.md for the URLs, licensing and review process.
"""

import argparse
import copy
import hashlib
import io
import json
import math
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter

from fontTools.misc.transform import Identity
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.basePen import BasePen
from fontTools.svgLib.path import parse_path
from fontTools.svgLib.path.shapes import PathBuilder

from vixl.imports import transform
from vixl.model import new_layer
from vixl.project import Project

INK = "#23364D"
PALETTE = {
    "#000000": INK,
    "#FCEA2B": "#F6CD70",
    "#F1B31C": "#DDA64C",
    "#EA5A47": "#DC7366",
    "#D22F27": "#B95050",
    "#92D3F5": "#A3CFDC",
    "#61B2E4": "#69A9BD",
    "#1E50A0": "#426F9D",
    "#B1CC33": "#A9BD79",
    "#5C9E31": "#739B76",
    "#B399C8": "#BAA6CF",
    "#8967AA": "#927CAB",
    "#E67A94": "#D995AA",
    "#FFA7C0": "#EAB9C7",
    "#9B9B9A": "#A0A9B3",
    "#3F3F3F": "#4C5968",
    "#FFFFFF": "#FFFCF5",
}
SVG = "{http://www.w3.org/2000/svg}"
STYLE = "VIXL Line 2"


def rounded_polygon(points, inset=0.12):
    """Straight sides with short curved corners, without snapping artwork to a grid."""
    corners = []
    for i, point in enumerate(points):
        prev, following = points[i - 1], points[(i + 1) % len(points)]
        before = tuple(point[j] + (prev[j] - point[j]) * inset for j in (0, 1))
        after = tuple(point[j] + (following[j] - point[j]) * inset for j in (0, 1))
        corners.append((before, point, after))
    pen = SVGPathPen(None)
    pen.moveTo(corners[0][0])
    for before, point, after in corners:
        pen.lineTo(before)
        pen.qCurveTo(point, after)
    pen.closePath()
    return pen.getCommands()


class GeometricPen(BasePen):
    """Facet large curves mildly; preserve small curves and round internal corners."""

    def __init__(self):
        super().__init__(None)
        self.output = SVGPathPen(None)

    def _moveTo(self, point):
        self.output.moveTo(point)

    def _lineTo(self, point):
        self.output.lineTo(point)

    def _curveToOne(self, a, b, end):
        start = self._getCurrentPoint()
        controls = (start, a, b, end)
        if max(max(p[j] for p in controls) - min(p[j] for p in controls) for j in (0, 1)) < 12:
            self.output.curveTo(a, b, end)
            return
        from shapely.geometry import LineString

        samples = []
        for i in range(17):
            t, s = i / 16, 1 - i / 16
            samples.append(
                tuple(
                    s**3 * start[j] + 3 * s * s * t * a[j] + 3 * s * t * t * b[j] + t**3 * end[j]
                    for j in (0, 1)
                )
            )
        points = list(LineString(samples).simplify(1.1).coords)
        for i in range(1, len(points) - 1):
            point, prev, following = points[i], points[i - 1], points[i + 1]
            amount = min(0.18, 0.85 / max(0.01, min(math.dist(prev, point), math.dist(point, following))))
            before = tuple(point[j] + (prev[j] - point[j]) * amount for j in (0, 1))
            after = tuple(point[j] + (following[j] - point[j]) * amount for j in (0, 1))
            self.output.lineTo(before)
            self.output.qCurveTo(point, after)
        self.output.lineTo(end)

    def _closePath(self):
        self.output.closePath()

    def _endPath(self):
        self.output.endPath()


def geometric(root):
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag not in ("path", "circle", "ellipse"):
            continue
        if tag in ("circle", "ellipse"):
            rx = float(element.get("r", element.get("rx", 0)))
            ry = float(element.get("r", element.get("ry", 0)))
            if min(rx, ry) < 7:
                continue
            cx, cy = float(element.get("cx", 0)), float(element.get("cy", 0))
            cut = math.sqrt(2) - 1
            vertices = [
                (-cut, -1),
                (cut, -1),
                (1, -cut),
                (1, cut),
                (cut, 1),
                (-cut, 1),
                (-1, cut),
                (-1, -cut),
            ]
            path = rounded_polygon([(cx + x * rx, cy + y * ry) for x, y in vertices])
            for attr in ("r", "rx", "ry", "cx", "cy"):
                element.attrib.pop(attr, None)
            element.tag = SVG + "path"
        else:
            pen = GeometricPen()
            parse_path(element.get("d", ""), pen)
            path = pen.output.getCommands()
        element.set("d", path)


def restyle(raw, flag=False):
    root = ET.fromstring(raw)
    for e in root.iter():
        for key in ("fill", "stroke"):
            value = e.get(key)
            if value:
                if value.startswith("#") and len(value) == 4:
                    value = "#" + "".join(c * 2 for c in value[1:])
                # National flags retain their identifying colors.
                e.set(
                    key,
                    INK
                    if value.upper() in ("#000000", "BLACK")
                    else value
                    if flag
                    else PALETTE.get(value.upper(), value),
                )
        if e.get("stroke-width"):
            e.set("stroke-width", str(float(e.get("stroke-width")) * 0.85))
    root.set("fill", INK)
    root.set("width", "72")
    root.set("height", "72")
    if not flag:
        geometric(root)
    return ET.tostring(root, encoding="utf-8")


def evenodd(path):
    from shapely.geometry import LineString
    from shapely.ops import polygonize, unary_union
    from vixl.vector_boolean import flatten, winding
    from vixl.shape_catalog import poly

    contours = flatten(path, tolerance=0.02)
    contours = [c if c[0] == c[-1] else c + [c[0]] for c in contours if len(c) > 2]
    faces = polygonize(unary_union([LineString(p) for p in contours if len(p) > 2]))
    filled = []
    for face in faces:
        p = face.representative_point()
        if sum(winding(c, p.x, p.y) for c in contours) % 2:
            filled.append(face)
    result = unary_union(filled)
    polygons = list(result.geoms) if result.geom_type == "MultiPolygon" else [result]
    return " ".join(
        poly(list(r.coords)) for p in polygons if p.geom_type == "Polygon" for r in [p.exterior, *p.interiors]
    )


def master(raw, entry):
    project = Project(72, 72, background="transparent")
    layers = []

    def walk(e, matrix=Identity, inherited=None, group="art"):
        tag = e.tag.rsplit("}", 1)[-1]
        props = {**(inherited or {}), **e.attrib}
        matrix = matrix.transform(transform(e.get("transform", "")))
        if props.get("display") == "none" or tag in ("defs", "clipPath"):
            return
        if tag in ("g", "svg"):
            for child in e:
                walk(child, matrix, props, e.get("id", group))
            return
        if tag == "rect" and (not e.get("width") or not e.get("height")):
            return
        builder = PathBuilder()
        geometry = copy.copy(e)
        geometry.attrib = {k: v for k, v in e.attrib.items() if k != "transform"}
        if not builder.add_path_from_element(geometry):
            raise ValueError(f"Unsupported bundled element: {tag}")
        if not builder.paths:
            return
        pen = SVGPathPen(None)
        parse_path(builder.paths[0], TransformPen(pen, matrix))
        path = pen.getCommands()
        if not path:
            return
        name = f"{group}-{len(layers) + 1:02d}"
        fill = props.get("fill", INK)
        stroke = props.get("stroke", "none")
        from vixl.colors import parse, hex_of

        def paint(value, alpha):
            if value == "none":
                return "transparent"
            rgba = parse(value)
            return hex_of((*rgba[:3], rgba[3] * float(alpha)))

        if props.get("fill-rule") == "evenodd" and fill != "none":
            original = path
            path = evenodd(path)
            if not path:
                if stroke == "none":
                    return
                path, fill = original, "none"
        layer = new_layer(
            name,
            "shape",
            72,
            72,
            shape="path",
            path=path,
            fill=paint(fill, props.get("fill-opacity", 1)),
            stroke=paint(stroke, props.get("stroke-opacity", 1)),
            stroke_width=float(props.get("stroke-width", 1)) * (matrix[0] ** 2 + matrix[1] ** 2) ** 0.5,
            line_cap=props.get("stroke-linecap", "butt"),
            opacity=float(props.get("opacity", 1)),
        )
        layer["id"] = "lyr_" + hashlib.sha256((entry["id"] + name).encode()).hexdigest()[:16]
        if props.get("stroke-dasharray"):
            layer["dash"] = [max(0.0001, float(n)) for n in re.findall(r"[\d.]+", props["stroke-dasharray"])]
        layers.append(layer)

    walk(ET.fromstring(raw))
    project.state["layers"] = layers
    project.state["active_layer"] = layers[-1]["id"]
    project.state["emoji_artwork"] = {
        "id": entry["id"],
        "name": entry["name"],
        "license": entry.get("license", "CC-BY-SA-4.0"),
        "source": entry.get("source", "OpenMoji 17.0.0"),
        "author": entry.get("author", "OpenMoji contributors"),
        "group": entry.get("group", "Custom"),
        "category": entry.get("subgroup", "custom"),
        "kind": entry.get("kind", "original"),
        "style": STYLE,
    }
    # A source master has one initial revision, with deterministic IDs for reproducible archives.
    root = "rev_" + hashlib.sha256(entry["id"].encode()).hexdigest()[:16]
    project.nodes = {
        root: {
            "id": root,
            "parent": None,
            "operations": [],
            "label": "VIXL Line source",
            "state": copy.deepcopy(project.state),
        }
    }
    project.head = root
    project.branches = {"main": root}
    project.current_branch = "main"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        write(z, "project.json", json.dumps(project.manifest(), separators=(",", ":")).encode())
    return buf.getvalue()


def write(z, name, data):
    info = zipfile.ZipInfo(name, (2025, 9, 9, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    z.writestr(info, data)


def build(sources, output):
    output.mkdir(parents=True, exist_ok=True)
    tests = (sources / "emoji-test.txt").read_text(encoding="utf-8")
    assert "# Version: 17.0" in tests, "Pin Unicode 17.0, not a moving latest URL"
    meta = {e["hexcode"]: e for e in json.loads((sources / "openmoji.json").read_text(encoding="utf-8"))}
    entries, aliases, canonical = [], {}, {}
    group = subgroup = ""
    for line in tests.splitlines():
        if line.startswith("# group: "):
            group = line[9:]
        if line.startswith("# subgroup: "):
            subgroup = line[12:]
        match = re.match(r"([0-9A-F ]+)\s*;\s*([\w-]+)\s*#\s*(\S+)\s+E([\d.]+)\s+(.+)", line)
        if not match:
            continue
        points, status, emoji, version, name = match.groups()
        key = "-".join(points.split())
        # Qualification variants have identical sequences once presentation selectors are removed.
        normalized = emoji.replace("\ufe0f", "")
        if status in ("fully-qualified", "component"):
            canonical[normalized] = key
            entries.append(
                {
                    "id": key,
                    "kind": "unicode",
                    "emoji": emoji,
                    "name": name,
                    "version": version,
                    "group": group,
                    "subgroup": subgroup,
                    "tags": meta.get(key, {}).get("tags", ""),
                    "author": meta.get(key, {}).get("openmoji_author", "OpenMoji contributors"),
                    "source": "OpenMoji 17.0.0",
                    "license": "CC-BY-SA-4.0",
                }
            )
        aliases[emoji] = normalized
    aliases = {emoji: canonical[n] for emoji, n in aliases.items() if n in canonical}
    reaction_sources = Path(__file__).resolve().parents[1] / "assets/emojis/reactions"
    reactions = json.loads((reaction_sources / "catalog.json").read_text(encoding="utf-8"))
    assert len({e["id"] for e in reactions}) == len(reactions)
    entries += [{k: v for k, v in e.items() if k != "file"} for e in reactions]
    aliases.update({e["emoji"]: e["id"] for e in reactions})
    original = zipfile.ZipFile(sources / "openmoji.zip")
    missing = []
    with zipfile.ZipFile(output / ".artwork-building.zip", "w") as bundle:
        for i, entry in enumerate(entries):
            key = entry["id"]
            if key.startswith(":"):
                svg = (reaction_sources / (key.strip(":") + ".svg")).read_bytes()
                write(bundle, f"svg/{key}.svg", svg)
                write(bundle, f"vixl/{key}.vixl", master(svg, entry))
                continue
            name = key + ".svg"
            if name not in original.namelist():
                stripped = key.replace("-FE0F", "")
                name = stripped + ".svg"
            if name not in original.namelist():
                missing.append(key)
                continue
            svg = restyle(original.read(name), entry["group"] == "Flags")
            write(bundle, f"svg/{key}.svg", svg)
            write(bundle, f"vixl/{key}.vixl", master(svg, entry))
            if i % 500 == 0:
                print(i, key, flush=True)
        for name in ("LICENSE.txt", "UNICODE-LICENSE.txt"):
            write(bundle, name, (sources / name).read_bytes())
    assert not missing, f"Missing art: {missing}"
    (output / ".artwork-building.zip").replace(output / "artwork.zip")
    (output / "catalog.json").write_text(
        json.dumps(
            {
                "version": 1,
                "unicode_version": "17.0",
                "unicode_count": len(entries) - len(reactions),
                "reaction_count": sum(e["group"] == "VIXL Reactions" for e in reactions),
                "original_count": len(reactions),
                "original_groups": dict(Counter(e["group"] for e in reactions)),
                "style": STYLE,
                "source": "OpenMoji 17.0.0",
                "license": "CC-BY-SA-4.0",
                "entries": entries,
                "aliases": aliases,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    for name in ("LICENSE.txt", "UNICODE-LICENSE.txt"):
        (output / name).write_bytes((sources / name).read_bytes())
    (output / "emoji-test.txt").write_bytes((sources / "emoji-test.txt").read_bytes())
    print(f"{len(entries)} editable emojis ({len(reactions)} originals), {len(aliases)} recognized sequences")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("src/vixl/data/emojis"))
    args = parser.parse_args()
    build(args.sources, args.output)
