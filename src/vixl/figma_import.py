"""Import a Figma file (or one node of it) as an editable Vixl document.

Two layers, kept apart so the mapping runs offline:

* ``FigmaClient`` and ``import_source`` talk to the Figma REST API with a personal access token that comes only
  from the environment (``FIGMA_TOKEN`` or ``VIXL_FIGMA_TOKEN``); nothing is saved in a document.
* ``build`` is a pure function from the file JSON plus the fetched image bytes to Vixl operations and a report.
  ``import_figma_document`` applies that to a project without any network access.

Every lossy decision is recorded as ``{node_id, name, type, what_was_lost}`` in the report.
Mapping rules are documented in docs/figma.md.
"""

import json
import math
import os
import re
from urllib.parse import parse_qs, unquote, urlsplit

import httpx

from .colors import hex_of
from .errors import VixlError, require

API = "https://api.figma.com"
TOKEN_ENVS = ("FIGMA_TOKEN", "VIXL_FIGMA_TOKEN")
TIMEOUT = 60
MAX_RESPONSE = 256 * 1024 * 1024
MAX_IMAGES = 200
KEY = re.compile(r"[A-Za-z0-9]{8,64}")
HOSTS = ("figma.com", "www.figma.com")
CONTAINERS = ("FRAME", "GROUP", "COMPONENT", "COMPONENT_SET", "INSTANCE", "SECTION")
FRAME_LIKE = ("FRAME", "COMPONENT", "COMPONENT_SET", "INSTANCE", "SECTION")
PATH_NODES = ("VECTOR", "BOOLEAN_OPERATION", "STAR", "POLYGON", "REGULAR_POLYGON", "LINE")
IGNORED = ("SLICE",)
# Figma blend modes with an exact Vixl counterpart.
BLENDS = {"NORMAL": "normal", "PASS_THROUGH": "normal", "MULTIPLY": "multiply", "SCREEN": "screen",
          "OVERLAY": "overlay", "DARKEN": "darken", "LIGHTEN": "lighten", "DIFFERENCE": "difference",
          "LINEAR_DODGE": "add"}
ALIGNS = {"MIN": "start", "CENTER": "center", "MAX": "end"}
IDENTITY = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))


# ---------------------------------------------------------------------------------------------- source and token

def parse_source(source):
    """``(file_key, node_id or None)`` from a Figma file URL or a bare file key.

    URLs look like ``https://www.figma.com/design/<key>/<name>?node-id=1-2`` (``/file/``, ``/board/`` and
    ``/proto/`` work too; a branch URL addresses its branch). A node id written ``1-2`` in the URL is ``1:2``."""
    require(isinstance(source, str) and source.strip(), "Give a Figma file URL or file key", "invalid_figma_source",
            field="source", suggestions=["https://www.figma.com/design/<file-key>/<name>", "<file-key>"])
    text = source.strip()
    if not re.match(r"(?i)[a-z][a-z0-9+.-]*://", text):
        require(KEY.fullmatch(text), f"{text!r} is not a Figma file key or URL", "invalid_figma_source", field="source",
                suggestions=["Copy the file URL from the Figma address bar (https://www.figma.com/design/<key>/...)"])
        return text, None
    parts = urlsplit(text)
    require(parts.scheme == "https" and (parts.hostname or "").lower() in HOSTS,
            "Figma URLs look like https://www.figma.com/design/<file-key>/<name>", "invalid_figma_source",
            field="source")
    segments = [unquote(s) for s in parts.path.split("/") if s]
    require(len(segments) >= 2 and segments[0] in ("design", "file", "board", "proto", "slides", "make")
            and KEY.fullmatch(segments[1]),
            "That Figma URL has no file key; expected https://www.figma.com/design/<file-key>/<name>",
            "invalid_figma_source", field="source")
    key = segments[1]
    if len(segments) >= 4 and segments[2] == "branch" and KEY.fullmatch(segments[3]):
        key = segments[3]
    node = parse_qs(parts.query).get("node-id", [None])[0]
    return key, normalize_node_id(node)


def normalize_node_id(node):
    """``1-2`` (URL spelling) as ``1:2``; ``None`` stays ``None``."""
    if node is None:
        return None
    node = str(node).strip()
    require(re.fullmatch(r"\d+[:-]\d+(;\d+[:-]\d+)*", node), f"{node!r} is not a Figma node id (such as 1:2)",
            "invalid_figma_source", field="node_id", suggestions=["Right-click a layer, Copy link, and use its node-id"])
    return node.replace("-", ":")


def token_from_env(env=None):
    env = os.environ if env is None else env
    for name in TOKEN_ENVS:
        if env.get(name, "").strip():
            return env[name].strip()
    raise VixlError(
        "figma_token_missing",
        "Set FIGMA_TOKEN (or VIXL_FIGMA_TOKEN) to a Figma personal access token to import from Figma",
        field="token",
        suggestions=["In Figma: Settings > Security > Personal access tokens > Generate new token, "
                     "with the file_content:read scope",
                     "export FIGMA_TOKEN=... in the environment that runs Vixl (it is never saved in a document)",
                     "Or import a file you already exported: send the Figma file JSON as the import data"])


# -------------------------------------------------------------------------------------------------- API client

class FigmaClient:
    """Minimal Figma REST client. ``transport`` (an ``httpx`` transport) lets tests answer without a network;
    ``download`` fetches image bytes from the URLs Figma returns (default: Vixl's bounded HTTPS fetch)."""

    def __init__(self, token, *, transport=None, base=API, download=None, limits=None):
        self.token, self.base, self.transport, self.limits = token, base.rstrip("/"), transport, limits
        self._download = download

    def get(self, route, params=None):
        try:
            with httpx.Client(transport=self.transport, timeout=TIMEOUT, follow_redirects=False) as client:
                response = client.get(self.base + route, params=params, headers={"X-Figma-Token": self.token})
        except httpx.HTTPError as exc:
            raise VixlError("figma_unreachable", f"Cannot reach the Figma API ({type(exc).__name__})",
                            suggestions=["Check network access to api.figma.com and retry"]) from exc
        self._raise_for_status(response)
        require(len(response.content) <= MAX_RESPONSE, "The Figma response is too large; import a single frame with "
                "its node-id", "resource_limit", field="node_id")
        try:
            return response.json()
        except ValueError as exc:
            raise VixlError("figma_error", "The Figma API returned something that is not JSON") from exc

    @staticmethod
    def _raise_for_status(response):
        status = response.status_code
        if status < 400:
            return
        try:
            detail = response.json()
            detail = detail.get("err") or detail.get("message") or detail.get("error") or ""
        except ValueError:
            detail = ""
        if status in (401, 403):
            raise VixlError("figma_forbidden", "Figma refused the token (HTTP %d%s). It is invalid, expired, or lacks "
                            "read access to this file" % (status, f": {detail}" if detail else ""), status=status,
                            suggestions=["Generate a new personal access token with the file_content:read scope "
                                         "(Figma Settings > Security > Personal access tokens)",
                                         "Check that the token's account can open the file in Figma",
                                         "Update FIGMA_TOKEN / VIXL_FIGMA_TOKEN"])
        if status == 404:
            raise VixlError("figma_not_found", "Figma has no file or node with that key (HTTP 404)", status=status,
                            suggestions=["Check the file key in the URL: https://www.figma.com/design/<file-key>/...",
                                         "Check the node-id belongs to this file",
                                         "The token's account must be able to open the file"])
        if status == 429:
            wait = response.headers.get("Retry-After", "")
            seconds = int(wait) if wait.strip().isdigit() else None
            raise VixlError("figma_rate_limited", "Figma rate limit reached"
                            + (f"; retry after {seconds} s" if seconds is not None else "; retry later"),
                            status=status, retry_after_s=seconds,
                            plan_tier=response.headers.get("X-Figma-Plan-Tier"),
                            suggestions=["Wait for the retry-after period, then import again",
                                         "Import one frame (node-id) instead of the whole file to use fewer requests"])
        if status == 400:
            raise VixlError("figma_bad_request", f"Figma rejected the request (HTTP 400){': ' + detail if detail else ''}",
                            status=status)
        raise VixlError("figma_error", f"Figma API error (HTTP {status}){': ' + detail if detail else ''}", status=status,
                        suggestions=["Retry later; status.figma.com shows outages"] if status >= 500 else [])

    def file(self, key, node_id=None):
        params = {"geometry": "paths"}
        if node_id:
            params["ids"] = node_id
        return self.get(f"/v1/files/{key}", params)

    def image_fills(self, key):
        """``{imageRef: url}`` for every image fill in the file."""
        return (self.get(f"/v1/files/{key}/images").get("meta") or {}).get("images") or {}

    def render(self, key, ids, scale=2):
        """``{node_id: url}`` of PNG renders of the nodes."""
        found = {}
        for start in range(0, len(ids), 50):
            data = self.get(f"/v1/images/{key}", {"ids": ",".join(ids[start:start + 50]), "format": "png",
                                                  "scale": scale, "use_absolute_bounds": "true"})
            found.update({k: v for k, v in (data.get("images") or {}).items() if v})
        return found

    def download(self, url):
        if self._download is not None:
            return self._download(url)
        from .fetch import fetch_bounded

        limit = self.limits.max_asset_bytes if self.limits else 64 * 1024 * 1024
        return fetch_bounded(url, limit, accept="image/*", label="Figma image")[0]


# ------------------------------------------------------------------------------------------------ matrix helpers

def matrix(value):
    """A 2x3 ``((a, c, tx), (b, d, ty))`` from Figma's relativeTransform, or None when malformed."""
    try:
        (a, c, tx), (b, d, ty) = value
        return ((float(a), float(c), float(tx)), (float(b), float(d), float(ty)))
    except (TypeError, ValueError):
        return None


def multiply(m, n):
    return tuple(tuple(sum(m[i][k] * (n[k][j] if k < 2 else (1.0 if j == 2 else 0.0)) for k in range(3))
                       for j in range(3)) for i in range(2))


def transform_point(m, x, y):
    return m[0][0] * x + m[0][1] * y + m[0][2], m[1][0] * x + m[1][1] * y + m[1][2]


def invert(m):
    (a, c, tx), (b, d, ty) = m
    det = a * d - b * c
    if abs(det) < 1e-12:
        return IDENTITY
    ia, ib, ic, id_ = d / det, -b / det, -c / det, a / det
    return ((ia, ic, -(ia * tx + ic * ty)), (ib, id_, -(ib * tx + id_ * ty)))


def number(value, digits=3):
    value = round(float(value), digits)
    return int(value) if value == int(value) else value


def color_of(paint_or_color, alpha=1.0):
    c = paint_or_color.get("color", paint_or_color)
    return hex_of((c.get("r", 0), c.get("g", 0), c.get("b", 0), c.get("a", 1) * alpha))


def utf16_to_index(text):
    """Map a UTF-16 code-unit offset (what Figma counts) to a Python string index."""
    table, units = [], 0
    for index, char in enumerate(text):
        table.extend([index] * (2 if ord(char) > 0xFFFF else 1))
        units += 2 if ord(char) > 0xFFFF else 1
    table.append(len(text))
    return table


def rounded_rect_path(w, h, radii):
    """Closed path for a rectangle with per-corner radii (top-left, top-right, bottom-right, bottom-left)."""
    limit = min(w, h) / 2
    tl, tr, br, bl = (max(0.0, min(float(r), limit)) for r in radii)
    f = number
    parts = [f"M{f(tl)} 0", f"L{f(w - tr)} 0"]
    if tr:
        parts.append(f"A{f(tr)} {f(tr)} 0 0 1 {f(w)} {f(tr)}")
    parts.append(f"L{f(w)} {f(h - br)}")
    if br:
        parts.append(f"A{f(br)} {f(br)} 0 0 1 {f(w - br)} {f(h)}")
    parts.append(f"L{f(bl)} {f(h)}")
    if bl:
        parts.append(f"A{f(bl)} {f(bl)} 0 0 1 0 {f(h - bl)}")
    parts.append(f"L0 {f(tl)}")
    if tl:
        parts.append(f"A{f(tl)} {f(tl)} 0 0 1 {f(tl)} 0")
    return " ".join(parts) + " Z"


# --------------------------------------------------------------------------------------------- gradient mapping

def _mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(4))


def _stops(raw, to_offset):
    """Vixl stops from Figma stops: ``to_offset`` maps a Figma position to a Vixl offset; the ramp is clipped to
    0-1 (Figma pads past the ends, so does Vixl) and offsets are made strictly increasing."""
    points = sorted(((to_offset(s["position"]), tuple(s["color"].get(k, 1 if k == "a" else 0) for k in "rgba"))
                     for s in raw), key=lambda p: p[0])
    if not points:
        return []
    clipped = []
    for (o0, c0), (o1, c1) in zip(points, points[1:]):
        if o1 <= 0 or o0 >= 1:
            continue
        if o0 < 0 < o1:
            c0, o0 = _mix(c0, c1, -o0 / (o1 - o0)), 0.0
        if o1 > 1 > o0:
            c1, o1 = _mix(c0, c1, (1 - o0) / (o1 - o0)), 1.0
        for o, c in ((o0, c0), (o1, c1)):
            if not clipped or o > clipped[-1][0] or c != clipped[-1][1]:
                clipped.append((o, c))
    if not clipped:
        edge = points[-1] if points[-1][0] <= 0 else points[0]
        clipped = [(0.0, edge[1]), (1.0, edge[1])]
    if clipped[0][0] > 0:
        clipped.insert(0, (0.0, clipped[0][1]))
    if clipped[-1][0] < 1:
        clipped.append((1.0, clipped[-1][1]))
    result = []
    for o, c in clipped:
        o = min(1.0, max(0.0, o))
        if result and o <= result[-1]["offset"]:
            o = result[-1]["offset"] + 1e-4
        result.append({"offset": round(o, 5), "color": hex_of(c)})
    # A nudge past 1 (several stops stacked at the end) is pulled back so offsets stay in range and increasing.
    for i in range(len(result) - 1, -1, -1):
        limit = 1.0 if i == len(result) - 1 else result[i + 1]["offset"] - 1e-4
        result[i]["offset"] = round(min(result[i]["offset"], limit), 5)
    return result[:64]


def gradient_settings(paint):
    """Vixl gradient-overlay settings for a Figma linear or radial gradient paint, plus the lossy notes.

    Vixl ramps are linear in the layer's normalized box, as Figma's handle positions are, so a linear gradient maps
    exactly; a radial one maps exactly when its handles are axis aligned and equal in normalized length."""
    handles = [(h.get("x", 0.0), h.get("y", 0.0)) for h in paint.get("gradientHandlePositions", [])]
    raw, notes = paint.get("gradientStops") or [], []
    if len(handles) < 3 or len(raw) < 2:
        return None, ["gradient without handles or stops"]
    h0, h1, h2 = handles[:3]
    ax, ay, bx, by = h1[0] - h0[0], h1[1] - h0[1], h2[0] - h0[0], h2[1] - h0[1]
    det = ax * by - bx * ay
    if abs(det) < 1e-9:
        return None, ["degenerate gradient handles"]
    if any(s["color"].get("a", 1) < 0.999 for s in raw):
        notes.append("gradient stop transparency blends with the first stop colour instead of fading out")
    if paint["type"] == "GRADIENT_LINEAR":
        gx, gy = by / det, -bx / det
        length = abs(gx) + abs(gy)
        centre = gx * (0.5 - h0[0]) + gy * (0.5 - h0[1])
        stops = _stops(raw, lambda s: (s - centre) / length + 0.5)
        return {"direction": "angled", "angle": round(math.degrees(math.atan2(gy, gx)), 3), "stops": stops}, notes
    rx, ry = math.hypot(ax, ay), math.hypot(bx, by)
    axis_aligned = (abs(ay) < 1e-3 and abs(bx) < 1e-3) or (abs(ax) < 1e-3 and abs(by) < 1e-3)
    if not axis_aligned or abs(rx - ry) > 0.05 * max(rx, ry):
        notes.append("elliptical or rotated radial gradient approximated as a circular one")
    radius = (rx + ry) / 2
    stops = _stops(raw, lambda s: s * radius / 0.5)
    return {"direction": "radial", "center": [round(min(1, max(0, h0[0])), 5), round(min(1, max(0, h0[1])), 5)],
            "stops": stops}, notes


# ----------------------------------------------------------------------------------------------------- builder

class Plan:
    """The result of ``build``: operations, the loss report and what the importer learned."""

    def __init__(self):
        self.operations, self.report, self.raster_ids, self.image_refs = [], [], [], []
        self.canvas, self.summary = None, {}

    def as_dict(self):
        return {"operations": self.operations, "report": self.report, "canvas": self.canvas, "summary": self.summary}


def visible(item):
    return item.get("visible", True) is not False


class Builder:
    def __init__(self, project, images, rasters, fonts, options):
        self.project, self.images, self.rasters, self.fonts = project, images or {}, rasters or {}, fonts
        self.options = options
        self.plan = Plan()
        self.ops = self.plan.operations
        self.used = {layer["name"] for layer in project.state["layers"]}
        self.counts = {}
        self.base = IDENTITY
        self.font_cache = {}
        self.layers_made = 0
        self.boards = set()
        self.root_taken = None
        self.frame_abs = IDENTITY      # transform of the nearest ancestor that is not a group

    # report ------------------------------------------------------------------------------------------------
    def lost(self, node, what):
        entry = {"node_id": node.get("id", ""), "name": node.get("name", ""), "type": node.get("type", ""),
                 "what_was_lost": what}
        if entry not in self.plan.report:
            self.plan.report.append(entry)

    def count(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1

    def unique(self, text, fallback="Layer"):
        base = re.sub(r"\s+", " ", str(text or "")).strip()[:190] or fallback
        name, index = base, 2
        while name in self.used:
            name, index = f"{base} {index}", index + 1
        self.used.add(name)
        return name

    # placement ---------------------------------------------------------------------------------------------
    def place(self, absolute, box):
        """Position of a layer whose unrotated local box is ``(x0, y0, w, h)`` inside a node with the given
        absolute transform: x, y of the layer's unrotated box, plus rotation (degrees) and mirroring."""
        x0, y0, w, h = box
        m = multiply(self.base, absolute)
        cx, cy = transform_point(m, x0 + w / 2, y0 + h / 2)
        (a, c, _), (b, d, _) = m
        det = a * d - b * c
        # Mirroring is a flip of the local x axis; the y column then carries the rotation.
        angle = math.degrees(math.atan2(-c, d)) if det < 0 else math.degrees(math.atan2(b, a))
        angle = (angle + 180) % 360 - 180
        skew = abs(a * c + b * d) > 0.02 * max(1e-9, math.hypot(a, b) * math.hypot(c, d))
        return {"x": number(cx - w / 2), "y": number(cy - h / 2), "width": number(w), "height": number(h),
                "rotation": number(angle, 2), "flip": det < 0, "skew": skew}

    def finish_transform(self, place, node):
        """Mirror then rotate the layer just created (rotation keeps its centre)."""
        if place["flip"]:
            self.ops.append({"type": "flip", "direction": "horizontal"})
        if abs(place["rotation"]) > 0.005:
            self.ops.append({"type": "rotate", "value": place["rotation"]})
        if place["skew"]:
            self.lost(node, "skewed transform: the skew was dropped")

    def geometry_box(self, node):
        size = node.get("size") or {}
        box = node.get("absoluteBoundingBox") or {}
        return (float(size.get("x", box.get("width", 0)) or 0), float(size.get("y", box.get("height", 0)) or 0))

    def relative(self, node, parent_box):
        m = matrix(node.get("relativeTransform"))
        if m is not None:
            return m
        box = node.get("absoluteBoundingBox") or {}
        px, py = (parent_box or {}).get("x", 0), (parent_box or {}).get("y", 0)
        return ((1.0, 0.0, box.get("x", 0) - px), (0.0, 1.0, box.get("y", 0) - py))

    # fills and strokes -------------------------------------------------------------------------------------
    def visible_paints(self, node, key):
        return [p for p in node.get(key) or [] if visible(p) and p.get("opacity", 1) > 0
                and (p.get("type") != "SOLID" or p.get("color", {}).get("a", 1) > 0)]

    def stroke_of(self, node):
        paints = self.visible_paints(node, "strokes")
        weight = float(node.get("strokeWeight", 0) or 0)
        if not paints or weight <= 0:
            return None
        paint = paints[-1]
        if len(paints) > 1:
            self.lost(node, f"{len(paints) - 1} extra stroke paint(s) dropped; the top stroke is kept")
        if paint["type"] == "SOLID":
            colour = color_of(paint, paint.get("opacity", 1))
        elif paint["type"].startswith("GRADIENT") and paint.get("gradientStops"):
            colour = color_of(paint["gradientStops"][0], paint.get("opacity", 1))
            self.lost(node, "gradient stroke replaced by its first stop colour")
        else:
            self.lost(node, f"{paint['type'].lower()} stroke is not supported and was dropped")
            return None
        weights = node.get("individualStrokeWeights")
        if weights and len({weights.get(k, 0) for k in ("top", "right", "bottom", "left")}) > 1:
            weight = max(weights.values())
            self.lost(node, "per-side stroke weights replaced by the largest weight on every side")
        stroke = {"stroke": colour, "stroke_width": number(weight, 2),
                  "stroke_align": {"INSIDE": "inside", "OUTSIDE": "outside"}.get(node.get("strokeAlign"), "center")}
        cap = {"ROUND": "round", "SQUARE": "square"}.get(node.get("strokeCap"))
        if cap:
            stroke["line_cap"] = cap
        join = {"ROUND": "round", "BEVEL": "bevel"}.get(node.get("strokeJoin"))
        if join:
            stroke["line_join"] = join
        dashes = [d for d in node.get("strokeDashes") or [] if d > 0]
        if dashes:
            stroke["dash"] = [number(d, 2) for d in dashes]
            stroke["dash_fit"] = False  # Figma draws its dashes at their exact lengths
        return stroke

    def corner_radii(self, node):
        radii = node.get("rectangleCornerRadii")
        if radii and len(radii) == 4:
            return [float(r) for r in radii]
        return [float(node.get("cornerRadius", 0) or 0)] * 4

    def geometry(self, node):
        """How to draw the node's own silhouette: rect (with radii), ellipse or an SVG path in node pixels."""
        w, h = self.geometry_box(node)
        kind = node.get("type")
        if kind in ("RECTANGLE", "FRAME", "COMPONENT", "COMPONENT_SET", "INSTANCE", "SECTION"):
            return {"kind": "rect", "w": w, "h": h, "radii": self.corner_radii(node)}
        if kind == "ELLIPSE":
            arc = node.get("arcData") or {}
            partial = abs((arc.get("endingAngle", 2 * math.pi) - arc.get("startingAngle", 0)) - 2 * math.pi) > 1e-3 \
                or arc.get("innerRadius", 0) > 0
            paths = [g["path"] for g in node.get("fillGeometry") or [] if g.get("path")]
            if partial and paths:
                return {"kind": "path", "w": w, "h": h, "path": " ".join(paths), "winding": node["fillGeometry"][0]}
            if partial:
                self.lost(node, "ellipse arc or ring drawn as a full ellipse (no geometry in the export)")
            return {"kind": "ellipse", "w": w, "h": h}
        if kind == "LINE":
            return {"kind": "line", "w": w, "h": 0}
        paths = [g for g in node.get("fillGeometry") or [] if g.get("path")]
        if paths:
            if any(g.get("windingRule") == "EVENODD" for g in paths):
                self.lost(node, "even-odd fill rule drawn with the non-zero rule; overlapping contours may fill instead "
                          "of cut holes")
            return {"kind": "path", "w": w, "h": h, "path": " ".join(g["path"] for g in paths)}
        if kind == "STAR" and node.get("pointCount"):
            return {"kind": "native", "w": w, "h": h, "fields": {
                "shape": "star", "sides": int(node["pointCount"]), "inner_radius": number(node.get("starInnerRadius", 0.5), 3)}}
        if kind in ("POLYGON", "REGULAR_POLYGON") and node.get("pointCount"):
            return {"kind": "native", "w": w, "h": h, "fields": {"shape": "polygon", "sides": int(node["pointCount"])}}
        strokes = [g for g in node.get("strokeGeometry") or [] if g.get("path")]
        if strokes:
            return {"kind": "path", "w": w, "h": h, "path": " ".join(g["path"] for g in strokes), "outline": True}
        return None

    def shape_op(self, name, geom, place, fill, stroke=None):
        w, h = place["width"], place["height"]
        op = {"type": "shape", "name": name, "x": place["x"], "y": place["y"], "width": w, "height": h, "fill": fill}
        kind = geom["kind"]
        if kind == "rect":
            radii = geom["radii"]
            if len(set(radii)) > 1:
                op.update(shape="path", path=rounded_rect_path(w, h, radii), path_view=[w, h])
            elif radii[0] > 0:
                op.update(shape="rounded-rectangle", radius=number(min(radii[0], min(w, h) / 2)))
            else:
                op["shape"] = "rectangle"
        elif kind == "ellipse":
            op["shape"] = "ellipse"
        elif kind == "native":
            op.update(geom["fields"])
        elif kind == "line":
            op.update(shape="path", path=f"M0 {number(h / 2)} L{number(w)} {number(h / 2)}", path_view=[w, h])
        else:
            op.update(shape="path", path=geom["path"], path_view=[w, h])
        if stroke:
            op.update(stroke)
        return op

    def outline_for(self, geom, place):
        """Frame-op fields that clip an image to the node's silhouette."""
        if geom["kind"] == "rect" and any(geom["radii"]):
            return {"outline": rounded_rect_path(place["width"], place["height"], geom["radii"])}
        if geom["kind"] == "ellipse":
            return {"frame_shape": "ellipse"}
        if geom["kind"] == "path":
            return {"outline": geom["path"]}
        if geom["kind"] == "native" and geom["fields"]["shape"] == "star":
            return {"frame_shape": "star"}
        return {}

    def image_op(self, node, name, paint, geom, place):
        ref = paint.get("imageRef")
        self.plan.image_refs.append(ref)
        data = self.images.get(ref)
        if data is None:
            self.lost(node, "image fill skipped: its image bytes were not available")
            return None
        from .assets import add_encoded

        mode = paint.get("scaleMode", "FILL")
        if mode in ("TILE", "STRETCH", "CROP"):
            self.lost(node, f"image scale mode {mode} approximated as fill (cover)")
        if paint.get("rotation") or paint.get("filters"):
            self.lost(node, "image rotation and filters (exposure, contrast ...) were not applied")
        fit = "fit" if mode == "FIT" else "fill"
        try:
            asset, _ = add_encoded(self.project, data, placed_size=(place["width"] * 2, place["height"] * 2), fit=fit)
        except VixlError as exc:
            self.lost(node, f"image fill skipped: {exc}")
            return None
        return {"type": "frame", "name": name, "asset": asset, "x": place["x"], "y": place["y"],
                "width": place["width"], "height": place["height"], "fit": fit, **self.outline_for(geom, place)}

    def fill_layers(self, node, name, geom, place):
        """Emit one layer per visible fill (bottom first), plus a stroke layer when the top fill cannot carry the
        stroke (a gradient or image would recolour it). Returns the layer names in z order."""
        paints = self.visible_paints(node, "fills")
        stroke = self.stroke_of(node)
        if geom["kind"] == "path" and geom.get("outline"):
            # Only the outlined stroke geometry exists: it is drawn as a filled shape.
            self.lost(node, "stroke exported as outlined geometry: drawn as a filled shape, weight not editable")
            ink = stroke["stroke"] if stroke else (color_of(paints[-1], paints[-1].get("opacity", 1)) if paints
                                                   else "#000000")
            paints, stroke = [{"type": "SOLID", "_hex": ink}], None
        carries = bool(paints) and paints[-1]["type"] == "SOLID"
        separate = bool(stroke) and bool(paints) and not carries
        multi = len(paints) > 1 or separate
        base = node.get("name") or "Shape"
        names = []
        for index, paint in enumerate(paints):
            layer = self.unique(f"{base} fill" + (f" {index + 1}" if index else "")) if multi else name
            kind, opacity = paint["type"], paint.get("opacity", 1)
            if paint.get("blendMode", "NORMAL") not in ("NORMAL", "PASS_THROUGH"):
                self.lost(node, f"fill blend mode {paint['blendMode']} dropped")
            layer_opacity = 1
            if kind == "SOLID":
                ink = paint.get("_hex") or color_of(paint, opacity)
                top = stroke if index == len(paints) - 1 and carries else None
                self.ops.append(self.shape_op(layer, geom, place, ink, top))
            elif kind in ("GRADIENT_LINEAR", "GRADIENT_RADIAL"):
                settings, notes = gradient_settings(paint)
                for note in notes:
                    self.lost(node, note)
                if settings is None:
                    first = (paint.get("gradientStops") or [{"color": {}}])[0]
                    self.ops.append(self.shape_op(layer, geom, place, color_of(first, opacity)))
                else:
                    self.ops.append(self.shape_op(layer, geom, place, settings["stops"][0]["color"][:7]))
                    self.ops.append({"type": "layer-style", "name": "gradient-overlay", "settings": settings})
                    layer_opacity = opacity
            elif kind in ("GRADIENT_ANGULAR", "GRADIENT_DIAMOND") and paint.get("gradientStops"):
                stops = paint["gradientStops"]
                self.lost(node, f"{kind.lower().replace('_', ' ')} fill replaced by a flat colour (its middle stop)")
                self.ops.append(self.shape_op(layer, geom, place, color_of(stops[len(stops) // 2], opacity)))
            elif kind == "IMAGE":
                op = self.image_op(node, layer, paint, geom, place)
                if op is None:
                    if multi:
                        self.used.discard(layer)
                    continue
                self.ops.append(op)
                layer_opacity = opacity
            else:
                self.lost(node, f"{kind.lower()} fill is not supported and was dropped")
                if multi:
                    self.used.discard(layer)
                continue
            self.finish_transform(place, node)
            if layer_opacity < 0.9995:
                self.ops.append({"type": "opacity", "value": number(layer_opacity, 4)})
            names.append(layer)
        if stroke and not (paints and carries):
            layer = self.unique(f"{base} stroke") if names else name
            self.ops.append(self.shape_op(layer, geom, place, "transparent", stroke))
            self.finish_transform(place, node)
            names.append(layer)
        self.layers_made += len(names)
        return names

    # effects and finishing ---------------------------------------------------------------------------------
    def finish(self, node):
        """Operations that apply to the node's layer (the active one): opacity, blend mode, effects, visibility."""
        opacity = node.get("opacity", 1)
        if opacity < 0.9995:
            self.ops.append({"type": "opacity", "value": number(opacity, 4)})
        blend = node.get("blendMode", "PASS_THROUGH")
        if blend in BLENDS:
            if BLENDS[blend] != "normal":
                self.ops.append({"type": "blend", "value": BLENDS[blend]})
        else:
            self.lost(node, f"blend mode {blend} has no Vixl equivalent; drawn as normal")
        shadows = []
        for effect in node.get("effects") or []:
            if not visible(effect):
                continue
            kind = effect.get("type")
            if kind == "DROP_SHADOW":
                shadows.append(effect)
            elif kind == "LAYER_BLUR":
                radius = effect.get("radius", 0)
                if radius > 0:
                    self.ops.append({"type": "effect", "name": "blur", "amount": number(min(radius / 2, 250), 2)})
            elif kind == "INNER_SHADOW":
                self.lost(node, "inner shadow dropped (no inner-shadow effect in Vixl)")
            elif kind == "BACKGROUND_BLUR":
                self.lost(node, "background blur dropped (no backdrop blur in Vixl)")
            else:
                self.lost(node, f"effect {kind} dropped")
        if shadows:
            effect = shadows[0]
            offset = effect.get("offset") or {}
            colour = effect.get("color") or {}
            self.ops.append({"type": "layer-style", "name": "drop-shadow", "settings": {
                "color": hex_of((colour.get("r", 0), colour.get("g", 0), colour.get("b", 0), 1)),
                "dx": number(min(4096, max(-4096, offset.get("x", 0))), 2),
                "dy": number(min(4096, max(-4096, offset.get("y", 0))), 2),
                "blur": number(min(100, effect.get("radius", 0) / 2), 2),
                "opacity": number(colour.get("a", 1), 4)}})
            if effect.get("spread"):
                self.lost(node, "shadow spread dropped")
            if len(shadows) > 1:
                self.lost(node, f"{len(shadows) - 1} extra drop shadow(s) dropped; Vixl layers carry one")
        if not visible(node):
            self.ops.append({"type": "hide"})

    # node dispatch -----------------------------------------------------------------------------------------
    def emit(self, node, parent_abs, parent_box):
        """Create the layer(s) for a child of a parent at ``parent_abs``; returns the Vixl layer name or None.

        A group's children are normally relative to the group, but some exports place them relative to the group's
        frame; the node's absoluteBoundingBox says which reading puts it where Figma drew it."""
        relative = self.relative(node, parent_box)
        absolute = multiply(parent_abs, relative)
        if parent_abs is not self.frame_abs and not self.fits(node, absolute):
            alternative = multiply(self.frame_abs, relative)
            if self.fits(node, alternative):
                absolute = alternative
        return self.emit_at(node, absolute)

    def fits(self, node, absolute):
        """Whether ``absolute`` puts the node's box where its absoluteBoundingBox says (within a pixel)."""
        box = node.get("absoluteBoundingBox")
        if not box or not node.get("size"):
            return True
        w, h = self.geometry_box(node)
        corners = [transform_point(absolute, x, y) for x, y in ((0, 0), (w, 0), (w, h), (0, h))]
        return (abs(min(c[0] for c in corners) - box["x"]) < 1.0 and abs(min(c[1] for c in corners) - box["y"]) < 1.0)

    def emit_at(self, node, absolute):
        """Create the layer(s) for ``node`` whose absolute transform is known; returns its Vixl layer name or None."""
        kind = node.get("type")
        if kind in IGNORED:
            return None
        if node.get("isMask"):
            self.lost(node, "mask layer skipped: the layers it clipped are drawn unmasked")
            return None
        if kind in CONTAINERS:
            return self.container(node, absolute)
        if kind == "TEXT":
            return self.text(node, absolute)
        if kind == "RECTANGLE" or kind == "ELLIPSE" or kind in PATH_NODES:
            return self.shape(node, absolute)
        return self.unsupported(node, absolute)

    def shape(self, node, absolute):
        geom = self.geometry(node)
        if geom is None:
            self.lost(node, "no geometry in the export: node skipped")
            return None
        w, h = geom["w"], geom["h"]
        if geom["kind"] == "line":
            # A line has no height; its box is as thick as its stroke so it has an area to place.
            weight = max(1.0, float(node.get("strokeWeight", 1) or 1))
            box = (0.0, -weight / 2, max(w, 1.0), weight)
        elif w <= 0 and h <= 0:
            self.lost(node, "zero-size node skipped")
            return None
        else:
            box = (0.0, 0.0, max(w, 1.0), max(h, 1.0))
        name = self.unique(node.get("name"), node.get("type", "Layer").title())
        names = self.fill_layers(node, name, geom, self.place(absolute, box))
        if not names:
            self.used.discard(name)
            return None
        return self.wrap(node, name, names)

    def wrap(self, node, name, names):
        """One name for the node: a single layer finishes itself, several are grouped under the node's name."""
        if len(names) > 1:
            self.ops.append({"type": "group", "name": name, "targets": names})
            self.count("group")
        elif names[0] != name:
            self.ops.append({"type": "rename", "name": name})
        self.finish(node)
        return name

    def text(self, node, absolute):
        characters = (node.get("characters") or "").replace(" ", "\n").replace("\r", "")
        if not characters.strip():
            return None
        style = node.get("style") or {}
        name = self.unique(node.get("name") or characters[:30], "Text")
        w, h = self.geometry_box(node)
        place = self.place(absolute, (0.0, 0.0, max(w, 1), max(h, 1)))
        family, weight = style.get("fontFamily", ""), int(style.get("fontWeight", 400) or 400)
        italic = bool(style.get("italic"))
        font, substituted = self.font(node, family, weight, italic)
        size = float(style.get("fontSize", 16) or 16)
        if abs(size - round(size)) > 0.01:
            self.lost(node, f"font size {number(size, 2)} rounded to {round(size)}")
        op = {"type": "text", "name": name, "text": characters, "x": place["x"], "y": place["y"],
              "size": max(1, round(size))}
        if font:
            op["font"] = font
        paints = self.visible_paints(node, "fills")
        colour = "#000000"
        if paints:
            paint = paints[-1]
            if paint["type"] == "SOLID":
                colour = color_of(paint, paint.get("opacity", 1))
            elif paint.get("gradientStops"):
                colour = color_of(paint["gradientStops"][0], paint.get("opacity", 1))
                self.lost(node, "gradient text fill replaced by its first stop colour")
            else:
                self.lost(node, f"{paint['type'].lower()} text fill replaced by black")
        op["color"] = colour
        align = {"CENTER": "center", "RIGHT": "right", "JUSTIFIED": "left"}.get(style.get("textAlignHorizontal"), "left")
        if style.get("textAlignHorizontal") == "JUSTIFIED":
            self.lost(node, "justified text drawn left-aligned")
        op["align"] = align
        if style.get("lineHeightPx") and size:
            op["line_height"] = number(min(5, max(0.5, style["lineHeightPx"] / size)), 3)
        if style.get("letterSpacing"):
            op["tracking"] = number(max(-1000, min(1000, style["letterSpacing"])), 2)
        case = {"UPPER": "uppercase", "LOWER": "lowercase", "TITLE": "capitalize"}.get(style.get("textCase"))
        if case:
            op["text_transform"] = case
        elif style.get("textCase") in ("SMALL_CAPS", "SMALL_CAPS_FORCED"):
            self.lost(node, "small caps drawn as normal text")
        self.ops.append(op)
        # The REST API leaves textAutoResize out for a fixed box (NONE).
        auto = style.get("textAutoResize", "NONE")
        box_x = place["x"]
        if auto != "WIDTH_AND_HEIGHT" or (align != "left" and w > 0):
            width = max(w, 1.0)
            if auto == "WIDTH_AND_HEIGHT" and substituted is not None:
                # A substitute font is wider or narrower; give centred or right-aligned text room and keep its anchor.
                extra = width * 0.25
                width += extra
                box_x = place["x"] - (extra / 2 if align == "center" else extra)
                self.ops[-1]["x"] = number(box_x)
            layout = {"type": "text-layout", "width": number(width), "fit": False}
            if auto == "NONE" and substituted is None:
                # With a substitute font the text may need more room than the Figma box gave it.
                layout["height"] = number(max(h, 1))
            self.ops.append(layout)
        self.text_overrides(node, characters, style, font, family, weight, italic)
        if style.get("textAlignVertical", "TOP") != "TOP" and auto == "NONE":
            self.lost(node, "vertical text alignment (centre/bottom in a fixed-height box) not applied")
        if style.get("paragraphSpacing") or style.get("paragraphIndent"):
            self.lost(node, "paragraph spacing and indent not applied")
        if any(t not in (None, "NONE") for t in style.get("lineTypes") or []) or style.get("listOptions"):
            self.lost(node, "list formatting not applied")
        if node.get("strokes") and self.visible_paints(node, "strokes") and node.get("strokeWeight"):
            stroke = self.stroke_of(node)
            if stroke:
                self.ops.append({"type": "text-set", "stroke_color": stroke["stroke"][:7],
                                 "stroke_width": max(1, round(float(stroke["stroke_width"])))})
        self.finish_transform(place, node)
        self.layers_made += 1
        self.finish(node)
        return name

    def font(self, node, family, weight, italic):
        """``(registered font name or None, substitution marker)``; reports a substitution once per node."""
        key = (family, weight, italic)
        if key not in self.font_cache:
            found = self.fonts(family, weight, italic) if self.fonts and family else (None, None)
            self.font_cache[key] = found if isinstance(found, tuple) else (found, None)
        name, note = self.font_cache[key]
        if name is None:
            self.lost(node, f"font {family or 'unspecified'} {weight}{' italic' if italic else ''} is not available; "
                      "text uses the bundled fallback font")
            return None, "missing"
        if note:
            self.lost(node, note)
            return name, None
        return name, None

    def text_overrides(self, node, characters, style, font, family, weight, italic):
        """``text-style`` operations for characterStyleOverrides runs, plus whole-text italic or bold fallbacks."""
        table = node.get("styleOverrideTable") or {}
        cache = utf16_to_index(characters)
        overrides = node.get("characterStyleOverrides") or []
        if not font:
            if italic:
                self.ops.append({"type": "text-style", "italic": True})
            if weight >= 600:
                self.ops.append({"type": "text-style", "bold": True})
        elif italic and not re.search(r"italic", font):
            self.ops.append({"type": "text-style", "italic": True})
        start = 0
        runs = []
        for index in range(1, len(overrides) + 1):
            if index == len(overrides) or overrides[index] != overrides[start]:
                if overrides[start]:
                    runs.append((start, index, overrides[start]))
                start = index
        for begin, end, ident in runs:
            span = table.get(str(ident)) or {}
            begin_i, end_i = (cache[min(begin, len(cache) - 1)], cache[min(end, len(cache) - 1)])
            if begin_i >= end_i:
                continue
            style_op = {"type": "text-style", "start": begin_i, "end": end_i}
            changed = False
            fam, wt, it = span.get("fontFamily", family), int(span.get("fontWeight", weight) or weight), span.get("italic", italic)
            if (fam, wt, it) != (family, weight, italic):
                name, _ = self.font(node, fam, wt, bool(it))
                if name:
                    if name != font:
                        style_op["font"] = name
                        changed = True
                    if it and "italic" not in name:
                        style_op["italic"] = True
                        changed = True
                else:
                    if bool(it) != italic:
                        style_op["italic"] = bool(it)
                        changed = True
                    if wt >= 600 > weight:
                        style_op["bold"] = True
                        changed = True
            if "fontSize" in span and abs(span["fontSize"] - style.get("fontSize", span["fontSize"])) > 0.01:
                style_op["size"] = number(span["fontSize"], 2)
                changed = True
            if "letterSpacing" in span and span["letterSpacing"] != style.get("letterSpacing", 0):
                style_op["tracking"] = number(span["letterSpacing"], 2)
                changed = True
            fills = [p for p in span.get("fills") or [] if visible(p)]
            if fills and fills[-1].get("type") == "SOLID":
                style_op["color"] = color_of(fills[-1], fills[-1].get("opacity", 1))
                changed = True
            decoration = span.get("textDecoration")
            if decoration == "UNDERLINE":
                style_op["underline"], changed = True, True
            elif decoration == "STRIKETHROUGH":
                style_op["strike"], changed = True, True
            if span.get("textCase") or span.get("hyperlink"):
                self.lost(node, "per-range text case and hyperlinks not applied")
            if changed:
                self.ops.append(style_op)
        if style.get("textDecoration") in ("UNDERLINE", "STRIKETHROUGH"):
            self.ops.append({"type": "text-style", "underline" if style["textDecoration"] == "UNDERLINE" else "strike": True})

    def unsupported(self, node, absolute):
        kind = node.get("type", "?")
        box = node.get("absoluteRenderBounds") or node.get("absoluteBoundingBox")
        if self.options.get("rasterize_unsupported"):
            if node.get("id") in self.rasters and box:
                from .assets import add_encoded

                try:
                    w, h = box["width"], box["height"]
                    asset, _ = add_encoded(self.project, self.rasters[node["id"]], placed_size=(w * 2, h * 2))
                except VixlError as exc:
                    self.lost(node, f"{kind} could not be rasterized: {exc}")
                    return None
                x, y = transform_point(self.base, box["x"], box["y"])
                name = self.unique(node.get("name"), kind.title())
                self.ops.append({"type": "add", "asset": asset, "name": name, "x": number(x), "y": number(y),
                                 "width": number(w), "height": number(h)})
                self.lost(node, f"{kind} has no editable Vixl equivalent: imported as a PNG render")
                self.layers_made += 1
                self.finish(node)
                return name
            self.plan.raster_ids.append(node.get("id"))
        self.lost(node, f"{kind} has no Vixl equivalent: skipped" + ("" if self.options.get("rasterize_unsupported")
                  else " (rasterize_unsupported imports a PNG render instead)"))
        return None

    # containers --------------------------------------------------------------------------------------------
    def container(self, node, absolute, is_root=False):
        kind = node.get("type")
        geom = self.geometry(node) if kind in FRAME_LIKE else None
        w, h = self.geometry_box(node)
        base_name = node.get("name") or kind.title()
        children = node.get("children") or []
        name = self.unique(base_name, kind.title())
        start = len(self.ops)
        members = []
        # The frame's own fill and stroke come first: they sit under the children.
        own = geom and (self.visible_paints(node, "fills") or self.visible_paints(node, "strokes")) and w > 0 and h > 0
        if own and not (is_root and self.root_background(node)):
            place = self.place(absolute, (0.0, 0.0, w, h))
            members.extend(self.fill_layers(node, self.unique(f"{base_name} background"), geom, place))
        child_names, child_nodes = [], []
        outer_frame = self.frame_abs
        self.frame_abs = outer_frame if kind == "GROUP" else absolute
        for child in children:
            made = self.emit(child, absolute, node.get("absoluteBoundingBox"))
            if made:
                child_names.append(made)
                child_nodes.append(child)
        self.frame_abs = outer_frame
        if kind in FRAME_LIKE and node.get("clipsContent") and not is_root:
            self.check_clipping(node, children)
        if not members and not child_names:
            del self.ops[start:]
            self.used.discard(name)
            return None
        clean, why = self.stack_ok(node, absolute, child_nodes)
        if node.get("layoutMode") in ("HORIZONTAL", "VERTICAL", "GRID") and child_names and not clean:
            self.lost(node, f"auto layout kept as a plain group with absolute positions ({why})")
        if is_root:
            if clean and child_names:
                return self.make_stack(node, absolute, name, members, child_names, root=True)
            return members + child_names
        if clean and child_names:
            return self.make_stack(node, absolute, name, members, child_names)
        names = members + child_names
        self.ops.append({"type": "group", "name": name, "targets": names})
        self.layers_made += 1
        self.count("group")
        self.finish(node)
        return name

    def root_background(self, node):
        """True when the root frame's single opaque solid fill became the canvas background."""
        return self.root_taken is not None and self.root_taken == node.get("id")

    def make_stack(self, node, absolute, name, members, child_names, root=False):
        gap = max(0.0, float(node.get("itemSpacing", 0) or 0))
        pad = {side: number(max(0.0, float(node.get(key, 0) or 0)), 2) for side, key in
               (("top", "paddingTop"), ("right", "paddingRight"), ("bottom", "paddingBottom"), ("left", "paddingLeft"))}
        w, h = self.geometry_box(node)
        inner = name if not members else self.unique(f"{node.get('name') or 'Frame'} layout")
        if members:
            self.used.discard(name)
        horizontal = node.get("layoutMode") == "HORIZONTAL"
        op = {"type": "stack", "name": inner, "targets": child_names, "direction": "horizontal" if horizontal else "vertical",
              "gap": number(gap, 2), "padding": pad,
              "align": ALIGNS.get(node.get("counterAxisAlignItems", "MIN"), "start"),
              "justify": ALIGNS.get(node.get("primaryAxisAlignItems", "MIN"), "start")}
        if node.get("primaryAxisSizingMode") == "AUTO" and node.get("counterAxisSizingMode") == "AUTO":
            op["size"] = "hug"
        else:
            op.update(width=number(max(w, 1)), height=number(max(h, 1)))
        self.ops.append(op)
        x, y = transform_point(multiply(self.base, absolute), 0, 0)
        self.ops.append({"type": "move", "target": inner, "x": number(x), "y": number(y)})
        self.layers_made += 1
        self.count("stack")
        if not members:
            if not root:
                self.finish(node)
            return [inner] if root else inner
        outer = name
        self.used.add(outer)
        self.ops.append({"type": "group", "name": outer, "targets": [*members, inner]})
        self.layers_made += 1
        self.count("group")
        if not root:
            self.finish(node)
        return [outer] if root else outer

    def stack_ok(self, node, absolute, children):
        """Whether the auto-layout frame maps to a Vixl stack that reproduces its positions."""
        mode = node.get("layoutMode")
        if mode not in ("HORIZONTAL", "VERTICAL"):
            return False, "not an auto-layout frame"
        if not children:
            return False, "no children"
        if node.get("layoutWrap") == "WRAP":
            return False, "wrapping layout"
        if node.get("primaryAxisAlignItems", "MIN") not in ALIGNS:
            return False, "space-between spacing"
        if node.get("counterAxisAlignItems", "MIN") not in ALIGNS:
            return False, "baseline alignment"
        if float(node.get("itemSpacing", 0) or 0) < 0:
            return False, "negative spacing"
        m = multiply(self.base, absolute)
        if abs(m[0][1]) > 1e-6 or abs(m[1][0]) > 1e-6 or m[0][0] < 0 or m[1][1] < 0:
            return False, "rotated or mirrored frame"
        for child in children:
            if child.get("layoutPositioning") == "ABSOLUTE":
                return False, "an absolutely positioned child"
            r = matrix(child.get("relativeTransform"))
            if r and (abs(r[0][1]) > 1e-6 or abs(r[1][0]) > 1e-6 or r[0][0] < 0 or r[1][1] < 0):
                return False, "a rotated or mirrored child"
        return True, ""

    def check_clipping(self, node, children):
        box = node.get("absoluteBoundingBox")
        if not box:
            return
        for child in children:
            inner = child.get("absoluteBoundingBox")
            if inner and visible(child) and (inner["x"] < box["x"] - 1 or inner["y"] < box["y"] - 1
                                             or inner["x"] + inner["width"] > box["x"] + box["width"] + 1
                                             or inner["y"] + inner["height"] > box["y"] + box["height"] + 1):
                self.lost(node, "frame clips its content but Vixl groups do not: parts outside the frame are drawn")
                return


# --------------------------------------------------------------------------------------------- tree selection

def find_node(node, wanted, matrix_so_far=IDENTITY, parent_box=None):
    """``(node, absolute matrix, parent box)`` of the node with id ``wanted`` (depth first), or None."""
    for child in node.get("children") or []:
        m = multiply(matrix_so_far, _relative(child, parent_box))
        if child.get("id") == wanted:
            return child, m, parent_box
        hit = find_node(child, wanted, m, child.get("absoluteBoundingBox") or parent_box)
        if hit:
            return hit
    return None


def _relative(node, parent_box):
    m = matrix(node.get("relativeTransform"))
    if m is not None:
        return m
    box = node.get("absoluteBoundingBox") or {}
    px, py = (parent_box or {}).get("x", 0), (parent_box or {}).get("y", 0)
    return ((1.0, 0.0, box.get("x", 0) - px), (0.0, 1.0, box.get("y", 0) - py))


def document_root(data):
    """The ``document`` node of a files response (or of one entry of a nodes response)."""
    if "document" in data and isinstance(data["document"], dict):
        return data["document"]
    nodes = data.get("nodes")
    if isinstance(nodes, dict) and nodes:
        first = next(iter(nodes.values()))
        return {"type": "DOCUMENT", "children": [{"type": "CANVAS", "name": "Page", "id": "0:0",
                                                  "children": [first.get("document")]}]}
    raise VixlError("invalid_figma_document", "That JSON is not a Figma file (no 'document' node)",
                    suggestions=["Send the response of GET /v1/files/:key"])


def collect_image_refs(node, found=None):
    """Every image fill reference used under ``node`` (visible fills only), in order."""
    found = [] if found is None else found
    for paint in node.get("fills") or []:
        if paint.get("type") == "IMAGE" and paint.get("imageRef") and visible(paint) and paint["imageRef"] not in found:
            found.append(paint["imageRef"])
    for child in node.get("children") or []:
        collect_image_refs(child, found)
    return found


def select(data, node_id=None, page=None):
    """``(nodes, canvas, pages)``: ``nodes`` are ``(node, absolute transform, parent box)`` for the node asked for,
    or for the visible top-level nodes of one page (the first, or ``page`` by name, id or 1-based number)."""
    document = document_root(data)
    pages = [c for c in document.get("children") or [] if c.get("type") == "CANVAS"]
    require(pages, "The Figma file has no pages", "invalid_figma_document")
    if node_id:
        for canvas in pages:
            hit = find_node(canvas, node_id, IDENTITY, None)
            if hit:
                return [hit], canvas, pages
        raise VixlError("figma_not_found", f"Node {node_id} is not in the file response", field="node_id",
                        suggestions=["Check the node-id in the URL (1-2 means 1:2)"])
    canvas = pages[0]
    if page is not None:
        match = [c for i, c in enumerate(pages, 1) if str(page) in (c.get("name"), c.get("id"), str(i))]
        require(match, f"No page {page!r}; pages: {', '.join(p.get('name', '') for p in pages)}", field="page",
                allowed=[p.get("name", "") for p in pages])
        canvas = match[0]
    return [(child, _relative(child, None), None) for child in canvas.get("children") or []], canvas, pages


def board_name(builder, text):
    base = re.sub(r"[^\w-]+", "-", str(text or "Frame")).strip("-")[:90] or "Frame"
    name, index = base, 2
    while name in builder.boards:
        name, index = f"{base}-{index}", index + 1
    builder.boards.add(name)
    return name


def build(project, data, *, images=None, rasters=None, fonts=None, node_id=None, page=None,
          rasterize_unsupported=False):
    """Pure mapping from Figma file JSON to a :class:`Plan` (operations + report).

    ``images`` maps imageRef to bytes, ``rasters`` maps node id to PNG bytes (for ``rasterize_unsupported``),
    ``fonts(family, weight, italic)`` returns a registered Vixl font name, ``(name, note)`` or None.
    ``project`` supplies limits and receives embedded assets; it is not otherwise changed.

    One selected frame (or a page holding one frame) becomes the whole document, sized to the frame. A page of
    several frames becomes one canvas holding every frame as a group, each with an artboard that frames it."""
    selected, canvas, pages = select(data, node_id, page)
    builder = Builder(project, images, rasters, fonts, {"rasterize_unsupported": rasterize_unsupported})
    plan = builder.plan
    nodes = []
    for node, absolute, box in selected:
        if node.get("type") in IGNORED:
            continue
        if not visible(node) and not node_id:
            builder.lost(node, "hidden top-level node not imported")
            continue
        nodes.append((node, absolute, box))
    require(nodes, "Nothing to import: the selected page or node is empty", "invalid_figma_document")
    blank = not project.state["layers"]

    def extent(node, absolute):
        w, h = builder.geometry_box(node)
        corners = [transform_point(absolute, x, y) for x, y in ((0, 0), (w, 0), (w, h), (0, h))]
        return (min(c[0] for c in corners), min(c[1] for c in corners), max(c[0] for c in corners),
                max(c[1] for c in corners))

    if len(nodes) == 1 and nodes[0][0].get("type") in CONTAINERS:
        root, absolute, _ = nodes[0]
        w, h = builder.geometry_box(root)
        builder.base = invert(absolute)
        size = {"width": max(1, round(w)), "height": max(1, round(h)), "background": "transparent"}
        paints = builder.visible_paints(root, "fills")
        if (blank and len(paints) == 1 and paints[0]["type"] == "SOLID" and paints[0].get("opacity", 1) == 1
                and paints[0]["color"].get("a", 1) == 1 and not any(builder.corner_radii(root))
                and not builder.visible_paints(root, "strokes")):
            size["background"] = color_of(paints[0])
            builder.root_taken = root.get("id")
        if blank:
            plan.operations.append({"type": "canvas", **size})
        plan.canvas = size
        if (root.get("opacity", 1) < 1 or any(visible(e) for e in root.get("effects") or [])
                or root.get("blendMode", "PASS_THROUGH") not in ("PASS_THROUGH", "NORMAL")):
            builder.lost(root, "opacity, effects and blend mode of the root frame are not applied to the document")
        if not builder.container(root, absolute, is_root=True):
            raise VixlError("figma_empty", "Nothing in the selected frame could be imported",
                            suggestions=["Check the report for skipped nodes", "Select a frame with visible content"])
        plan.summary["root"] = {"id": root.get("id"), "name": root.get("name"), "type": root.get("type")}
    else:
        boxes = [extent(n, a) for n, a, _ in nodes]
        left, top = min(b[0] for b in boxes), min(b[1] for b in boxes)
        size = {"width": max(1, math.ceil(max(b[2] for b in boxes) - left)),
                "height": max(1, math.ceil(max(b[3] for b in boxes) - top)), "background": "transparent"}
        builder.base = ((1.0, 0.0, -left), (0.0, 1.0, -top))
        if blank:
            plan.operations.append({"type": "canvas", **size})
        plan.canvas = size
        made = []
        for node, absolute, _ in nodes:
            made_name = builder.emit_at(node, absolute)
            if made_name and node.get("type") in FRAME_LIKE:
                x0, y0, x1, y1 = extent(node, absolute)
                made.append((made_name, node, (x0 - left, y0 - top, x1 - x0, y1 - y0)))
        if not any(op["type"] != "canvas" for op in plan.operations):
            raise VixlError("figma_empty", "Nothing on the selected page could be imported",
                            suggestions=["Check the report for skipped nodes", "Pass a node-id to import one frame"])
        for made_name, node, (x, y, w, h) in made:
            plan.operations.append({"type": "artboard", "name": board_name(builder, node.get("name")),
                                    "x": number(x), "y": number(y), "width": max(1, round(w)), "height": max(1, round(h)),
                                    "targets": [made_name]})
        plan.summary["artboards"] = [{k: op[k] for k in ("name", "x", "y", "width", "height")}
                                     for op in plan.operations if op["type"] == "artboard"]
    plan.summary.update(page=canvas.get("name"), pages=[p.get("name") for p in pages], layers=builder.layers_made,
                        **builder.counts)
    plan.image_refs = list(dict.fromkeys(plan.image_refs))
    plan.raster_ids = list(dict.fromkeys(plan.raster_ids))
    return plan


# ------------------------------------------------------------------------------------------------- font lookup

def font_resolver(project, install=True):
    """A ``fonts`` callable for :func:`build`: a registered ``family-weight`` font, else (with ``install``) the
    nearest Google Fonts weight installed through the font cache, else None (the bundled fallback is used)."""
    from . import typefaces

    def resolve(family, weight, italic):
        registered = project.state.get("fonts", {})
        slug = typefaces.slug(family)
        suffix = "-italic" if italic else ""
        for candidate in (f"{slug}-{weight}{suffix}", family):
            if candidate in registered and (candidate != family or not italic):
                return candidate
        entry = typefaces.find_font(family)
        if entry is None or not install:
            return None
        weights = entry.get("weights") or [400]
        wanted = min(weights, key=lambda w: (abs(w - weight), w))
        for use_italic in ((italic, False) if italic else (False,)):
            name = f"{slug}-{wanted}{'-italic' if use_italic else ''}"
            if name in registered:
                return (name, None) if (wanted, use_italic) == (weight, italic) else (name, _note(family, weight, italic, wanted, use_italic))
            try:
                typefaces.install_font(project, entry["family"], wanted, use_italic)
            except VixlError:
                continue
            exact = (wanted, use_italic) == (weight, italic)
            return name, None if exact else _note(family, weight, italic, wanted, use_italic)
        return None

    return resolve


def _note(family, weight, italic, wanted, got_italic):
    return (f"font {family} {weight}{' italic' if italic else ''} not available; used {wanted}"
            f"{' italic' if got_italic else ''}")


# --------------------------------------------------------------------------------------------- public entry

def _run(project, document, *, images, node_id, page, rasterize_unsupported, install_fonts, fonts=None,
         rasters=None, fetch_rasters=None, extra=None):
    """Build the plan on a copy of ``project``, apply it atomically and describe the result."""
    require(isinstance(document, dict), "Figma data must be a JSON object", "invalid_figma_document")

    def attempt(rasters):
        candidate = project.clone()
        plan = build(candidate, document, images=images, rasters=rasters,
                     fonts=fonts or font_resolver(candidate, install_fonts), node_id=node_id, page=page,
                     rasterize_unsupported=rasterize_unsupported)
        return candidate, plan

    candidate, plan = attempt(rasters or {})
    if rasterize_unsupported and fetch_rasters and plan.raster_ids:
        candidate, plan = attempt(fetch_rasters(plan.raster_ids))
    require(len(plan.operations) <= candidate.limits.max_operations,
            f"The import needs {len(plan.operations)} operations (limit {candidate.limits.max_operations}); import one "
            "frame with its node-id", "resource_limit", field="node_id")
    result = candidate.apply(plan.operations, detail="compact")
    project.__dict__.update(candidate.__dict__)
    return {**result,
            "figma": {**(extra or {}), "name": document.get("name"), "last_modified": document.get("lastModified"),
                      "version": document.get("version"), **plan.summary, "operations": len(plan.operations),
                      "images": len(images or {}), "images_missing": len([r for r in plan.image_refs
                                                                         if r not in (images or {})])},
            "report": plan.report,
            "warnings": [f"{len(plan.report)} lossy decision(s) in the Figma import; see report"] if plan.report else []}


def import_figma_document(project, data, *, images=None, rasters=None, fonts=None, install_fonts=False,
                          node_id=None, page=None, rasterize_unsupported=False):
    """Apply Figma file JSON (a dict, already fetched) to ``project``; no network access except font installs when
    ``install_fonts`` is true. ``images`` maps imageRef to bytes, ``rasters`` node id to PNG bytes."""
    return _run(project, data, images=images, node_id=normalize_node_id(node_id), page=page,
                rasterize_unsupported=rasterize_unsupported, install_fonts=install_fonts, fonts=fonts, rasters=rasters)


def import_source(project, data, *, node_id=None, page=None, rasterize_unsupported=False, install_fonts=True,
                  token=None, env=None, client=None, transport=None, download=None):
    """Import from Figma. ``data`` is a file URL or key (text or bytes), or the JSON of a Figma file to import
    offline. The token comes from the environment unless passed. ``install_fonts`` downloads missing Google Fonts
    families through the font cache; other fonts are substituted and reported."""
    text = data.decode("utf-8-sig") if isinstance(data, (bytes, bytearray)) else str(data)
    node_id = normalize_node_id(node_id)
    if text.lstrip().startswith("{"):
        try:
            document = json.loads(text)
        except ValueError as exc:
            raise VixlError("invalid_figma_document", f"Malformed Figma JSON: {exc}") from exc
        return import_figma_document(project, document, node_id=node_id, page=page, install_fonts=install_fonts)
    key, url_node = parse_source(text.strip())
    node_id = node_id or url_node
    api = client or FigmaClient(token or token_from_env(env), transport=transport, download=download,
                                limits=project.limits)
    document = api.file(key, node_id)
    refs = []
    for node, _matrix, _box in select(document, node_id, page)[0]:
        collect_image_refs(node, refs)
    images = {}
    if refs:
        require(len(refs) <= MAX_IMAGES, f"The selection has {len(refs)} image fills (limit {MAX_IMAGES}); import a "
                "smaller node", "resource_limit", field="node_id")
        urls = api.image_fills(key)
        for ref in refs:
            if urls.get(ref):
                try:
                    images[ref] = api.download(urls[ref])
                except VixlError:
                    continue

    def fetch_rasters(ids):
        rasters = {}
        for ident, url in api.render(key, ids).items():
            try:
                rasters[ident] = api.download(url)
            except VixlError:
                continue
        return rasters

    return _run(project, document, images=images, node_id=node_id, page=page,
                rasterize_unsupported=rasterize_unsupported, install_fonts=install_fonts,
                fetch_rasters=fetch_rasters, extra={"key": key, "node_id": node_id})
