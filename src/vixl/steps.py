"""Session steps: batch items that need the workspace (files, URLs, the font cache, the brand) and so are not
document operations, but run in order inside the same all-or-nothing batch as them.

An MCP or REST batch may mix them with operations, e.g. ``[{type: font-pair, pairing: random},
{type: import-image, path: photo.jpg, name: photo}, {type: move, target: photo, x: 40}]``: the steps and
operations apply to one candidate copy of the document, which is saved only when every item succeeded.
Workspace-scoped font steps (``scope: workspace``) write ``brand.json`` after the document batch succeeds.
"""

from functools import lru_cache
import inspect
import re
from typing import Annotated, Any, Literal

from pydantic import ConfigDict, Field, ValidationError, create_model

from .errors import VixlError, require

Variety = Literal["low", "medium", "high", "fixed"]
Scope = Annotated[Literal["document", "workspace"], Field(
    description="document (default); workspace makes it the brand.json default for new documents")]


def _upload(session, path, data_base64):
    from .assets import read_bounded
    from .io_policy import decode_upload

    limit = session.limits.max_asset_bytes
    return read_bounded(session.resolve(path), limit) if path else decode_upload(data_base64, limit)


def import_image(session, project, *, path: str | None = None,
                 data_base64: Annotated[str | None, Field(description="Image bytes as base64 or a data: URL")] = None,
                 url: Annotated[str | None, Field(description="Public https:// image URL (no credentials, at most 5 "
                                                              "redirects; private hosts refused)")] = None,
                 name: str = "image",
                 credit: Annotated[str | None, Field(description="Attribution, e.g. 'Photo: Ana Ruiz / Unsplash'")] = None,
                 license: Annotated[str | None, Field(description="License or usage terms, e.g. 'CC BY 4.0'")] = None):
    """Embed an image as a new layer from a workspace file, base64 bytes or a URL (PNG/JPEG/WebP keep their bytes);
    use web images only with the rights to do so and record credit and license."""
    from .image_import import attribution, fetch_image, import_image as embed

    require(sum(value is not None for value in (path, data_base64, url)) == 1,
            "Provide exactly one of path, data_base64 or url", field="path")
    attribution(credit, license)
    if url is not None:
        data, source = fetch_image(url, session.limits)
    else:
        data, source = _upload(session, path, data_base64), ({"path": path} if path else None)
    return embed(project, data, name, source=source, credit=credit, license=license)


def import_document(session, project, *, path: str | None = None, data_base64: str | None = None,
                    source: Annotated[str | None, Field(description="figma: a Figma file URL or file key (the token "
                                                                    "comes from FIGMA_TOKEN or VIXL_FIGMA_TOKEN)")] = None,
                    format: Annotated[Literal["svg", "pdf", "figma"] | None, Field(
                        description="Default: from the path (.svg, .pdf; a .json path or source is figma)")] = None,
                    name: str = "import",
                    page: Annotated[int | str, Field(description="PDF page number, or the Figma page number or name")] = 1,
                    dpi: int = 144,
                    svg_mode: Annotated[Literal["editable", "appearance", "auto"], Field(
                        description="editable layers (default), auto (draw unsupported elements as images) or "
                                    "appearance (one image; SVG source kept)")] = "editable",
                    node_id: Annotated[str | None, Field(description="figma: the frame or node to import (1:2 or 1-2)")] = None,
                    rasterize_unsupported: Annotated[bool, Field(
                        description="figma: import a PNG render of nodes Vixl cannot keep editable; otherwise they "
                                    "are skipped and listed in the report")] = False,
                    font_map: Annotated[dict[str, str] | None, Field(
                        description="pdf: PDF font family to registered font name, e.g. {Literata: literata-400, "
                                    "'Literata Bold': literata-700}")] = None,
                    install_fonts: Annotated[bool | None, Field(
                        description="Allow downloading from Google Fonts a font the document and the font cache lack "
                                    "(default: true for Vixl's own SVG, false for PDF)")] = None):
    """Import an SVG (Vixl's own round-trips losslessly), one PDF page as editable text, paths and images, or a Figma
    file, frame or node as editable layers (from a URL or key with the server's Figma token, or an exported file
    JSON); svg_mode=appearance imports one image instead. External or active SVG is rejected."""
    from .imports import import_document as read

    require(sum(value is not None for value in (path, data_base64, source)) == 1,
            "Provide exactly one of path, data_base64 or source", field="path")
    if format is None:
        if source is not None or (path and path.lower().endswith(".json")):
            format = "figma"
        else:
            require(path and path.lower().endswith((".svg", ".pdf")), "Give format: svg, pdf or figma", field="format")
            format = path.lower().rsplit(".", 1)[1]
    if format == "figma":
        data = source if source is not None else _upload(session, path, data_base64)
        return read(project, data, format, name, page, dpi, svg_mode, node_id=node_id,
                    rasterize_unsupported=rasterize_unsupported)
    require(source is None and node_id is None and not rasterize_unsupported,
            "source, node_id and rasterize_unsupported are Figma import options", field="source")
    require(isinstance(page, int), "A PDF page is a number", field="page")
    options = {"install_fonts": install_fonts} if install_fonts is not None else {}
    if font_map:
        options["font_map"] = font_map
    return read(project, _upload(session, path, data_base64), format, name, page, dpi, svg_mode, **options)


def import_font(session, project, *, name: Annotated[str, Field(description="The font name text operations use")],
                path: str | None = None,
                url: Annotated[str | None, Field(description="Public https:// URL of a TTF/OTF file")] = None):
    """Import a TTF/OTF font from a workspace file or an https URL under a registered name."""
    from .fonts import import_font as embed

    require((path is None) != (url is None), "Provide exactly one of path or url", field="path")
    return embed(project, url if url is not None else session.resolve(path), name)


def font_pair(session, project, *, pairing: Annotated[str, Field(
                  description="A curated pairing name (vixl_reference('fonts')) or 'random'")] = "random",
              seed: int | None = None, mood: str | None = None, best_for: str | None = None, scope: Scope = "document"):
    """Download (or reuse from cache), embed and register a pairing's heading and body fonts and make them the
    document typography that layouts use by default."""
    from .typefaces import pair_fonts, pair_workspace

    if scope == "workspace":
        return pair_workspace(session.workspace, pairing, seed=seed, mood=mood, best_for=best_for)
    return pair_fonts(project, pairing, seed=seed, mood=mood, best_for=best_for)


def font_install(session, project, *, family: Annotated[str, Field(description="Any Google Fonts family")],
                 weight: Annotated[int, Field(ge=100, le=900)] = 400, italic: bool = False,
                 name: Annotated[str | None, Field(description="Registered name (default family-weight)")] = None,
                 role: Annotated[str | None, Field(description="Make it this role's font: heading, body, a text stage "
                                                               "(h1, label …) or any lowercase role")] = None,
                 scope: Scope = "document"):
    """Download one style of a Google Fonts family, embed and register it; role makes it that role's font."""
    from .typefaces import install_font, install_workspace

    if scope == "workspace":
        return install_workspace(session.workspace, family, weight, italic, name, role)
    return install_font(project, family, weight, italic, name, role)


def font_cover(session, project, *, text: Annotated[str | None, Field(
                   description="Cover the characters of this text (default: every text layer's)")] = None,
               scripts: Annotated[list[str] | None, Field(
                   description="Scripts to cover: Devanagari, Han, Hiragana/Katakana, Hangul, Thai, Arabic (or "
                               "japanese, chinese, korean, hindi)")] = None,
               weight: Annotated[int, Field(ge=100, le=900)] = 400):
    """Install the catalog Noto face for each script no available font draws (CJK, Devanagari, Thai ...) and append
    it to font-fallbacks; uses the font cache first and refuses, naming the families, when downloads are off."""
    from .typefaces import cover_fonts

    return cover_fonts(project, text, scripts, weight)


def style_use(session, project, *, name: Annotated[str, Field(description="A style (vixl_reference('styles'))")],
              palette: Annotated[bool, Field(description="Also define and apply the style's first palette")] = False):
    """Tag the document with a catalog style, store its brief as design guidance and optionally apply its palette."""
    from .styles import apply_operations

    return {"style": name, "operations": [op["type"] for op in apply_operations(name, palette=palette)]}


def roll(session, project, *, purpose: str | None = None, mood: str | None = None, seed: int | None = None,
         variety: Variety | None = None,
         locks: Annotated[dict | None, Field(description="Fix choices such as palette or layout")] = None,
         slots: Annotated[dict | None, Field(description="Layout content, e.g. {title: Launch}")] = None,
         unfilled: Annotated[Literal["omit", "blank"] | None, Field(
             description="Unfilled slots: omit (default with slots) or [Label] blanks")] = None,
         replace: Annotated[bool, Field(description="Remove the layers of the document's previous layout first, "
                                                    "to re-roll a document that already has one")] = False):
    """Roll a coherent direction honouring brand.json and apply it: install the fonts and apply the layout."""
    from .typefaces import roll_document

    return roll_document(project, seed=seed, purpose=purpose, mood=mood, locks=locks, apply=True, slots=slots,
                         unfilled=unfilled, variety=variety, replace=replace)


STEPS = {"import-image": import_image, "import-document": import_document, "import-font": import_font,
         "font-pair": font_pair, "font-install": font_install, "font-cover": font_cover, "style-use": style_use, "roll": roll}


def step_type(kind):
    """The canonical step name for ``kind`` (import_image and importImage included), or None."""
    if not isinstance(kind, str):
        return None
    key = re.sub(r"(?<=[a-z])(?=[A-Z])", "-", kind).replace("_", "-").lower()
    return key if key in STEPS else None


def is_step(op):
    return isinstance(op, dict) and step_type(op.get("type")) is not None


def workspace_scoped(op):
    return step_type(op.get("type")) in ("font-pair", "font-install") and op.get("scope") == "workspace"


@lru_cache(maxsize=None)
def _model(kind):
    fields = {}
    for parameter in list(inspect.signature(STEPS[kind]).parameters.values())[2:]:
        annotation = Any if parameter.annotation is inspect.Parameter.empty else parameter.annotation
        fields[parameter.name] = (annotation, ... if parameter.default is inspect.Parameter.empty else parameter.default)
    return create_model(kind.replace("-", "_"), __config__=ConfigDict(extra="forbid"), **fields)


def step_schema(kind):
    from .mcp_tools import slim_schema

    schema = slim_schema(_model(kind).model_json_schema())
    schema["properties"] = {"type": {"const": kind}, **schema.get("properties", {})}
    schema["required"] = ["type", *schema.get("required", [])]
    schema["description"] = (inspect.getdoc(STEPS[kind]) or "").replace("\n", " ")
    schema["additionalProperties"] = False
    return schema


def parse(op, index):
    """The validated fields of one step, or an invalid_operation error with its schema."""
    kind = step_type(op["type"])
    values = {key: value for key, value in op.items() if key != "type"}
    try:
        parsed = _model(kind).model_validate(values)
    except ValidationError as exc:
        problems = []
        for item in exc.errors():
            where = ".".join(str(part) for part in item.get("loc", ()))
            problems.append(f"unknown field {where!r}" if item.get("type") == "extra_forbidden"
                            else f"{where}: {item.get('msg', 'invalid')}")
        raise VixlError("invalid_operation", f"operations[{index}] ({kind}): " + "; ".join(problems),
                        operation_index=index, field=str(exc.errors()[0].get("loc", ("",))[0]),
                        schema={kind: step_schema(kind)}) from exc
    return kind, {key: getattr(parsed, key) for key in _model(kind).model_fields}


def run(session, project, op, index):
    """Run one step on ``project``; style-use returns operations for the caller to apply in its place."""
    kind, fields = parse(op, index)
    try:
        if kind == "style-use":
            from .styles import apply_operations

            return kind, None, apply_operations(fields["name"], palette=fields["palette"])
        return kind, STEPS[kind](session, project, **fields), None
    except VixlError as exc:
        exc.details.setdefault("operation_index", index)
        raise
