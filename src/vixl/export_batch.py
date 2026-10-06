"""One call, several files: sizes, formats or artboards of a document, or several documents.

The same options as ``vixl_export_file`` apply per target. Every target is validated before the
first file is written, so a typo in the seventh entry does not leave six files behind.
"""

import difflib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from . import calls
from .assets import read_bounded
from .errors import VixlError, require

MAX_TARGETS = 64


class Target(BaseModel):
    """The options of vixl_export_file, plus the document to export and its own overwrite flag."""

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


def export_batch(session, export_file, targets, defaults=None, overwrite=False, stop_on_error=False, document=None):
    from .mcp_tools import EXPORT_SUFFIXES

    require(isinstance(targets, list) and 0 < len(targets) <= MAX_TARGETS,
            f"Give 1–{MAX_TARGETS} targets", field="targets")
    require(defaults is None or isinstance(defaults, dict), "defaults must be an object", field="defaults")
    defaults = {key: value for key, value in (defaults or {}).items() if key not in ("path",)}
    plan, seen = [], {}
    for index, raw in enumerate(targets):
        target = parse_target(index, raw, defaults)
        destination = session.resolve(target.path)
        require(destination.suffix.lower() in EXPORT_SUFFIXES,
                f"targets[{index}]: choose a PNG, JPEG, WEBP, TIFF, AVIF, SVG, PDF, ICO, HTML or PPTX filename",
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
            item = {"path": target.path, "error": exc.as_dict()}
            if stop_on_error:
                results.append(item)
                calls.progress(index + 1, len(plan), target.path)
                break
        results.append(item)
        calls.progress(index + 1, len(plan), target.path)
    return {"count": len(plan), "written": written, "failed": len(results) - written,
            "documents": documents, "results": results,
            **({"stopped_early": True} if len(results) < len(plan) else {})}
