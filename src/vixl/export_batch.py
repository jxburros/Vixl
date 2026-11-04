"""One call, several files: sizes, formats or artboards of a document, or several documents.

The same options as ``vixl_export`` apply per target. Every target is validated before the
first file is written, so a typo in the seventh entry does not leave six files behind. The
preflight also opens each target's document and refuses the batch when a layer references an
embedded asset that is gone, a text layer names a font no renderer can load, or the export would
not fit the server's page and megapixel limits: those would fail one target after the others
were written, and the error names the target instead.
"""

import difflib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from . import calls
from .assets import read_bounded
from .errors import VixlError, require
from .outcomes import make, summarize

MAX_TARGETS = 64


class Target(BaseModel):
    """The options of vixl_export, plus the document to export and its own overwrite flag."""

    model_config = ConfigDict(extra="forbid")

    path: str
    document: str | None = None
    overwrite: bool | None = None
    quality: int = Field(90, ge=1, le=100)
    scale: float = Field(1, ge=0.01, le=16)
    profile: str | None = None
    variables: dict | None = None
    background: str = "white"
    sampling: Literal["smooth", "nearest"] = "smooth"
    svg_policy: Literal["appearance", "strict"] = "appearance"
    artboard: str | None = None
    comp: str | None = None
    color_space: Literal["rgb", "cmyk"] = "rgb"
    icc_profile: str | None = None
    intent: Literal["perceptual", "relative", "saturation", "absolute"] = "relative"
    black_generation: float = Field(1.0, ge=0, le=1)
    ink_limit: float | None = Field(None, ge=100, le=400)
    proof: bool = False
    simulate: Literal["protanopia", "deuteranopia", "tritanopia", "achromatopsia"] | None = None
    dpi: float | None = Field(None, ge=36, le=2400)
    icon_sizes: list[int] | None = None
    time: float | str | None = None
    page: int | str | None = None
    pages: list[int | str] | str | None = None
    pdf_content: Literal["vector", "raster"] | None = None
    fillable: bool = False
    values: dict | None = None
    fill_mode: Literal["flatten", "editable"] = "flatten"
    alpha: Literal["auto", "keep", "flatten"] = "auto"
    title: str | None = None
    max_bytes: int | None = Field(None, ge=1)
    check: bool = False
    spec: str | dict | None = None


SPECIAL = {"path", "document", "overwrite", "icc_profile"}


def parse_target(index, raw, defaults):
    """Validate one target; errors name it and suggest the nearest option for a typo."""
    where = f"targets[{index}]"
    require(isinstance(raw, dict), f"{where} must be an object like {{path: 'out.png', scale: 2}}", field=where)
    try:
        return Target(**{**defaults, **raw})
    except ValidationError as exc:
        problem = exc.errors()[0]
        key = ".".join(str(part) for part in problem["loc"])
        allowed = sorted(Target.model_fields)
        if problem["type"] == "extra_forbidden":
            close = difflib.get_close_matches(key, allowed, 1, 0.5)
            raise VixlError(
                "invalid_operation",
                f"{where}: unknown option {key!r}" + (f"; did you mean {close[0]!r}?" if close else "")
                + f". Options: {', '.join(allowed)}",
                field=f"{where}.{key}", allowed=allowed, suggestions=close,
            ) from exc
        raise VixlError("invalid_operation", f"{where}.{key}: {problem['msg']}", field=f"{where}.{key}") from exc


def shown_document(session, document):
    return session.relative(session.resolve(document) if document else session.active())


def readiness(project, variables=None):
    """Why a render of ``project`` would fail before it starts: ``(code, message)`` for the first embedded asset
    a layer or mask references that the document no longer holds (``missing_asset``), image variable without an
    asset, or text font (layer or rich-text span) no renderer can load (``missing_font``); None when it is ready."""
    from .render import font_for

    assets = project.assets
    variables = variables or {}
    fonts = {}
    for layer in project.state.get("layers", []):
        name = layer.get("name", layer.get("id"))
        asset = layer.get("asset")
        if isinstance(asset, str) and asset not in assets and not layer.get("asset_variable"):
            return "missing_asset", f"layer {name!r} references embedded asset {asset!r}, which the document no longer holds"
        variable = layer.get("asset_variable")
        if variable:
            value = variables.get(variable, (project.state.get("variables") or {}).get(variable))
            if value is None:
                return "missing_variable", f"layer {name!r} takes its image from variable {variable!r}, which has no value"
            if str(value) not in assets:
                return "missing_asset", f"layer {name!r}: image variable {variable!r} names {value!r}, not an embedded asset"
        mask = layer.get("mask")
        if isinstance(mask, dict) and isinstance(mask.get("asset"), str) and mask["asset"] not in assets:
            return "missing_asset", f"the mask of layer {name!r} references embedded asset {mask['asset']!r}, which is gone"
        if layer.get("type") != "text":
            continue
        used = [layer.get("font")]
        rich = layer.get("rich")
        if isinstance(rich, dict):
            used += [span.get("font") for span in rich.get("spans", []) if isinstance(span, dict)]
        for font in used:
            if font is None or font in fonts:
                continue
            try:
                font_for(project, {"font": font, "size": 12})
            except VixlError as exc:
                return exc.code, f"layer {name!r}: {exc}"
            fonts[font] = True
    return None


def preflight(session, plan):
    """Refuse the batch, naming the target, when a target's document is not ready to render (``readiness``) or the
    export would exceed the call limits. A document that does not exist is left to the per-target loop, which
    reports it as that target's own error."""
    from .call_limits import check_export, of

    checked = {}
    for index, (target, doc, _) in enumerate(plan):
        where = f"targets[{index}]"
        suffix = session.resolve(target.path).suffix.lower()
        fmt = {".jpg": "JPEG", ".jpeg": "JPEG", ".tif": "TIFF", ".tiff": "TIFF"}.get(suffix, suffix[1:].upper())
        try:
            with session.project(document=doc) as project:
                key = (doc, json_key(target.variables))
                if key not in checked:
                    checked[key] = readiness(project, target.variables)
                problem = checked[key]
                if problem is not None:
                    raise VixlError(problem[0], f"{where} ({target.path}): {problem[1]}", field=where, target=index,
                                    document=shown_document(session, doc))
                if suffix != ".vixl":
                    options = {key: getattr(target, key) for key in target.model_fields_set - SPECIAL}
                    check_export(of(session), project, fmt, options)
        except VixlError as exc:
            if exc.code == "not_found" and "target" not in exc.details:
                continue
            if "target" in exc.details:
                raise
            raise VixlError(exc.code, f"{where} ({target.path}): {exc}", field=where, target=index,
                            **{k: v for k, v in exc.details.items() if k != "field"}) from exc


def json_key(value):
    import json

    return json.dumps(value, sort_keys=True, default=str) if value else ""


def export_batch(session, export_file, targets, defaults=None, overwrite=False, stop_on_error=False, document=None):
    from .io_policy import EXPORT_SUFFIXES

    require(isinstance(targets, list) and 0 < len(targets) <= MAX_TARGETS,
            f"Give 1–{MAX_TARGETS} targets", field="targets")
    require(defaults is None or isinstance(defaults, dict), "defaults must be an object", field="defaults")
    defaults = {key: value for key, value in (defaults or {}).items() if key not in ("path",)}
    plan, seen = [], {}
    for index, raw in enumerate(targets):
        target = parse_target(index, raw, defaults)
        destination = session.resolve(target.path)
        require(destination.suffix.lower() in EXPORT_SUFFIXES,
                f"targets[{index}]: choose a PNG, JPEG, WEBP, TIFF, AVIF, SVG, PDF, ICO, HTML, PPTX or PSD filename",
                field=f"targets[{index}].path")
        require(destination not in seen,
                f"targets[{index}] and targets[{seen.get(destination)}] both write {target.path}",
                field=f"targets[{index}].path")
        seen[destination] = index
        replace = overwrite if target.overwrite is None else target.overwrite
        require(replace or not destination.exists(),
                f"targets[{index}]: {target.path} already exists; set overwrite=true",
                field=f"targets[{index}].path")
        plan.append((target, target.document or document, replace))
    if any(doc is None for _, doc, _ in plan):
        session.active()  # No document named anywhere: fail now unless there is an active one.
    preflight(session, plan)
    results, written, documents = [], 0, []
    for index, (target, doc, replace) in enumerate(plan):
        calls.check_cancelled()
        options = {key: getattr(target, key) for key in target.model_fields_set - SPECIAL}
        options.setdefault("alpha", "auto")
        try:
            if target.icc_profile:
                options["icc_profile"] = read_bounded(session.resolve(target.icc_profile), 16 * 1024 * 1024)
            item = export_file(session, target.path, replace, doc, **options)
            item["document"] = shown_document(session, doc)
            written += 1
            if item["document"] not in documents:
                documents.append(item["document"])
        except VixlError as exc:
            item = {"path": target.path, "error": exc.as_dict(), "outcome": make("failed")}
            if stop_on_error:
                results.append(item)
                calls.progress(index + 1, len(plan), target.path)
                break
        results.append(item)
        calls.progress(index + 1, len(plan), target.path)
    return {"count": len(plan), "written": written, "failed": len(results) - written,
            "documents": documents, "results": results,
            "outcome": summarize([item["outcome"] for item in results] + [make("pending")] * (len(plan) - len(results))),
            **({"stopped_early": True} if len(results) < len(plan) else {})}
