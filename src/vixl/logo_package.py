"""The ``logo-package`` workflow: one logo in, a delivery folder out.

Variants (full colour, mono black, mono white, on light, on dark), optional lockups built from a mark
and a wordmark layer (mark, horizontal, stacked), and the files a brand hand-off needs: strict SVG,
RGB (and optionally CMYK) PDF, PNG at 1x/2x/3x, an icon set with favicon, a social avatar and an Open
Graph image, a usage sheet (the proof page) and optionally a zip. Every variant is also saved as an
editable .vixl in ``source/``, and the files are written through the same export path as
``vixl_export_batch``. Nothing is overwritten unless ``overwrite`` is true, and a failure removes the
files this call wrote.

Recolouring is a heuristic: every visible fill, stroke, text and gradient colour becomes the one ink;
shadows, glows and effects are dropped; images become a silhouette of their alpha (an opaque image
first loses the background colour found in its corners). Detail that only colour separates merges.
The result's ``report`` says what was done. EPS is not produced: use the PDF or SVG.
"""

import json
import zipfile
from pathlib import Path

from .errors import VixlError, require

VARIANTS = ("full-color", "mono-black", "mono-white", "on-light", "on-dark")
LOCKUPS = ("mark", "horizontal", "stacked")
COLOR_KEYS = ("fill", "stroke", "color", "stroke_color", "start", "end", "colors", "stops", "background")
SOURCE_SUFFIXES = (".vixl", ".png", ".jpg", ".jpeg", ".webp", ".svg")
USAGE = {
    "full-color": "Primary logo. Use on white or light, plain backgrounds.",
    "mono-black": "One-colour black: fax, stamps, engraving, single-ink print and light backgrounds.",
    "mono-white": "Reversed (white): dark photos and dark brand colours. Transparent background.",
    "on-light": "Logo on the light brand background, ready to place.",
    "on-dark": "Logo on the dark brand background, ready to place.",
}
FIELDS = {"source", "output", "trace", "variants", "lockups", "mark", "wordmark", "clear_space", "light", "dark",
          "png_sizes", "cmyk", "icons", "social", "proof", "zip", "overwrite"}


def _luminance_contrast(rgb, background):
    """WCAG contrast of two 0-255 RGB colours."""
    from .colors import contrast_ratio

    return contrast_ratio([v / 255 for v in rgb[:3]], [v / 255 for v in background[:3]])


def _rgba(value, state):
    from .design import resolve_color
    from .render import color

    try:
        return color(resolve_color(value, state)) if isinstance(value, str) else None
    except (VixlError, ValueError, TypeError, KeyError):
        return None


def _recolor_value(value, ink, state, counts):
    if isinstance(value, str):
        rgba = _rgba(value, state)
        if rgba is None:
            counts["kept"] += 1
            return value
        if rgba[3] == 0:
            return value
        counts["colors"] += 1
        return ink
    if isinstance(value, list):
        return [_recolor_value(item, ink, state, counts) for item in value]
    if isinstance(value, dict):
        return {key: _recolor_value(item, ink, state, counts) if key in COLOR_KEYS else item
                for key, item in value.items()}
    return value


def _silhouette(image, ink_rgba):
    """``image`` as one ink. Alpha is kept; an opaque image first loses its corner background colour."""
    import numpy as np
    from PIL import Image

    pixels = np.asarray(image.convert("RGBA")).astype(np.int16)
    alpha = pixels[..., 3]
    note = None
    if alpha.min() == 255:
        corners = np.array([pixels[0, 0], pixels[0, -1], pixels[-1, 0], pixels[-1, -1]])[:, :3]
        background = np.median(corners, axis=0)
        distance = np.abs(pixels[..., :3] - background).max(axis=2)
        alpha = np.clip((distance - 24) * 6, 0, 255)
        note = "an opaque image lost its corner background colour to become a silhouette"
    out = np.zeros(pixels.shape, np.uint8)
    out[..., :3] = ink_rgba[:3]
    out[..., 3] = (alpha * (ink_rgba[3] / 255)).astype(np.uint8)
    return Image.fromarray(out, "RGBA"), note


def recolor(project, ink):
    """Make every visible colour in ``project`` the one ``ink``. Returns what changed."""
    from .assets import add_image
    from .render import color

    state = project.state
    ink_rgba = color(ink)
    counts = {"colors": 0, "kept": 0}
    dropped, images, notes = 0, 0, set()
    for layer in state["layers"]:
        for key in COLOR_KEYS:
            if key in layer and not (key == "background" and layer["type"] == "group"):
                layer[key] = _recolor_value(layer[key], ink, state, counts)
        if layer["type"] == "shape" and "fill" not in layer:
            from .geometry import default_fill

            if default_fill(layer) != "transparent":
                layer["fill"] = ink
                counts["colors"] += 1
        for key in ("styles", "looks"):
            if layer.get(key):
                dropped += len(layer[key])
                layer[key] = {}
        if layer.get("effects"):
            dropped += len(layer["effects"])
            layer["effects"] = []
        if layer.get("asset") and layer["type"] in ("raster", "frame", "image"):
            silhouette, note = _silhouette(project.image(layer["asset"]), ink_rgba)
            layer["asset"] = add_image(project, silhouette)
            images += 1
            if note:
                notes.add(note)
    report = {"colors_replaced": counts["colors"]}
    if dropped:
        report["effects_dropped"] = dropped
    if images:
        report["images_silhouetted"] = images
    if counts["kept"]:
        report["unrecognised_colors_kept"] = counts["kept"]
    if notes:
        report["notes"] = sorted(notes)
    return report


def _load_source(session, source, document, trace, report):
    from .assets import add_encoded, read_bounded
    from .project import Project

    if source is None:
        with session.project(document=document) as project:
            return project.clone()
    path = session.resolve(source)
    suffix = path.suffix.lower()
    require(suffix in SOURCE_SUFFIXES, f"source must be one of {', '.join(SOURCE_SUFFIXES)}", field="source")
    require(path.is_file(), f"No file at {source}", "not_found", field="source")
    if suffix == ".vixl":
        return Project.load(path, limits=session.limits)
    data = read_bounded(path, session.limits.max_asset_bytes)
    from .image_diff import load_visual

    image = load_visual(path, session.limits, data=data)
    project = Project(image.width, image.height, "transparent", limits=session.limits)
    if suffix == ".svg":
        from .imports import import_document

        import_document(project, data, "svg", name="logo", svg_mode="auto")
        report["source"] = "SVG imported as editable paths (or kept as its appearance when too complex)"
        return project
    asset, _ = add_encoded(project, data)
    if trace:
        project.apply([{"type": "drawing", "action": "import", "asset": asset, "name": "logo",
                        "settings": {"deskew": False, "crop": False, "perspective": False, "sheet": False,
                                     "margin": 0, "ink": "#000000"}},
                       {"type": "drawing", "action": "vectorize", "target": "logo",
                        "settings": {"mode": "outline"}}])
        report["source"] = ("raster traced with drawing vectorize (outline): every variant, full colour included, is "
                            "the one-colour silhouette; compare it with the original before shipping")
        return project
    project.apply({"type": "add", "asset": asset, "name": "logo"})
    report["source"] = "raster placed as an image: SVG needs vector content (pass trace=true), PDFs embed the image"
    return project


def _content_box(project, ids=None):
    """Visible bounds [x0, y0, x1, y1] of the given top-level layers (all when None), from a render."""
    import numpy as np

    from .render import render

    trial = project.clone()
    if ids is not None:
        for layer in trial.state["layers"]:
            if layer.get("parent") is None and layer["id"] not in ids:
                layer["visible"] = False
    trial.state["canvas"]["background"] = "transparent"
    box = render(trial).getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    require(box is not None, "The logo has no visible content", field="source")
    return np.array(box, float)


def _top_level(project, name, field):
    layer = project.layer(name)
    require(layer.get("parent") is None, f"{field} {name!r} is inside a group; give the top-level group instead",
            field=field)
    return layer["id"]


def lockups(base, mark=None, wordmark=None, wanted=None, clear_space=0.25):
    """``{name: project}``: the whole logo trimmed to its content plus clear space, or, with ``mark`` and
    ``wordmark``, the mark alone and the horizontal and stacked lockups."""
    require(isinstance(clear_space, (int, float)) and 0 <= clear_space <= 2, "clear_space must be 0-2 (a fraction "
            "of the mark's height)", field="clear_space")
    # Logo files sit on whatever surface they are placed on: the source document's canvas colour is not part of
    # the logo, so every lockup (and the full-colour and one-colour variants made from it) is transparent.
    base = base.clone()
    base.state["canvas"]["background"] = "transparent"
    if not (mark or wordmark):
        require(not wanted or wanted == ["logo"], "lockups need mark and wordmark layers", field="lockups")
        project = base.clone()
        box = _content_box(project)
        pad = round(clear_space * min(box[2] - box[0], box[3] - box[1]))
        _fit(project, {layer["id"]: (pad - box[0], pad - box[1]) for layer in project.state["layers"]
                       if layer.get("parent") is None}, (box[2] - box[0] + 2 * pad, box[3] - box[1] + 2 * pad))
        return {"logo": project}
    require(mark and wordmark, "Give both mark and wordmark (layer names or ids) for lockups", field="mark")
    wanted = wanted or list(LOCKUPS)
    unknown = sorted(set(wanted) - set(LOCKUPS))
    require(not unknown, f"Unknown lockup(s) {unknown}; choose from {', '.join(LOCKUPS)}", field="lockups")
    mark_id, word_id = _top_level(base, mark, "mark"), _top_level(base, wordmark, "wordmark")
    m, w = _content_box(base, {mark_id}), _content_box(base, {word_id})
    mw, mh, ww, wh = m[2] - m[0], m[3] - m[1], w[2] - w[0], w[3] - w[1]
    pad = gap = round(clear_space * mh)
    result = {}
    for name in wanted:
        project = base.clone()
        keep = {mark_id} if name == "mark" else {mark_id, word_id}
        doomed = [layer["id"] for layer in project.state["layers"] if layer.get("parent") is None and layer["id"] not in keep]
        if doomed:
            project.apply([{"type": "remove", "target": ident} for ident in doomed])
        if name == "mark":
            placements, size = {mark_id: (pad - m[0], pad - m[1])}, (mw + 2 * pad, mh + 2 * pad)
        elif name == "horizontal":
            height = max(mh, wh)
            placements = {mark_id: (pad - m[0], pad + (height - mh) / 2 - m[1]),
                          word_id: (pad + mw + gap - w[0], pad + (height - wh) / 2 - w[1])}
            size = (mw + gap + ww + 2 * pad, height + 2 * pad)
        else:
            width = max(mw, ww)
            placements = {mark_id: (pad + (width - mw) / 2 - m[0], pad - m[1]),
                          word_id: (pad + (width - ww) / 2 - w[0], pad + mh + gap - w[1])}
            size = (width + 2 * pad, mh + gap + wh + 2 * pad)
        _fit(project, placements, size)
        result[name] = project
    return result


def _fit(project, placements, size):
    """Move each top-level layer by its offset, then size the canvas."""
    operations = [{"type": "move", "target": ident, "x": round(dx), "y": round(dy), "relative": True}
                  for ident, (dx, dy) in placements.items() if round(dx) or round(dy)]
    operations.append({"type": "canvas", "width": max(1, round(size[0])), "height": max(1, round(size[1]))})
    project.apply(operations)


def _mean_ink(project):
    """Average colour of the visible logo pixels."""
    import numpy as np

    from .render import render

    trial = project.clone()
    trial.state["canvas"]["background"] = "transparent"
    pixels = np.asarray(render(trial).convert("RGBA")).reshape(-1, 4)
    pixels = pixels[pixels[:, 3] > 128]
    return tuple(int(v) for v in pixels[:, :3].mean(axis=0)) if len(pixels) else (0, 0, 0)


def variants(lockup, wanted, light, dark):
    """``{variant: (project, report)}`` for one lockup."""
    from .render import color

    result = {}
    for name in wanted:
        project = lockup.clone()
        report = {}
        if name == "mono-black":
            report = recolor(project, "#000000")
        elif name == "mono-white":
            report = recolor(project, "#ffffff")
        elif name in ("on-light", "on-dark"):
            background = light if name == "on-light" else dark
            ratio = _luminance_contrast(_mean_ink(lockup), color(background)[:3])
            if ratio < 3:
                report = recolor(project, "#000000" if name == "on-light" else "#ffffff")
                report["reversed"] = (f"the full-colour logo's average colour has only {ratio:.1f}:1 contrast on "
                                      f"{background}, so this variant uses the one-colour "
                                      f"{'black' if name == 'on-light' else 'white'} logo")
            else:
                report["contrast"] = round(ratio, 2)
            project.apply({"type": "canvas", "background": background})
        result[name] = (project, report)
    return result


def _plan_social(primary, mark, light):
    """Avatar (mark, else the logo) and Open Graph image (the widest lockup) on the light background."""
    from .assets import add_image
    from .project import Project
    from .timeline import render_scaled

    plans = {}
    for name, size, source, share in (("avatar", "logo-avatar", mark, 0.62), ("og-image", "og-image", primary, 0.6)):
        project = Project.sized(size, light, design=False)
        canvas = project.state["canvas"]
        logo = source.state["canvas"]
        scale = min(canvas["width"] * share / logo["width"], canvas["height"] * share / logo["height"])
        image = render_scaled(source, scale)
        asset = add_image(project, image)
        project.apply({"type": "add", "asset": asset, "name": "logo",
                       "x": round((canvas["width"] - image.width) / 2), "y": round((canvas["height"] - image.height) / 2)})
        plans[name] = project
    return plans


def build(session, request, document=None):
    from .export_batch import export_batch
    from .exports import ICON_SETS, export_icons
    from .mcp_tools import export_file

    unknown = sorted(set(request) - FIELDS)
    require(not unknown, f"Unknown logo-package field(s) {unknown}", field=unknown[0] if unknown else None)
    require(isinstance(request.get("output"), str), "Give output: a folder for the package", field="output")
    overwrite = bool(request.get("overwrite", False))
    wanted = request.get("variants") or list(VARIANTS)
    require(isinstance(wanted, list) and not set(wanted) - set(VARIANTS),
            f"variants must be a list from {', '.join(VARIANTS)}", field="variants")
    light, dark = request.get("light", "#ffffff"), request.get("dark", "#111111")
    for field, value in (("light", light), ("dark", dark)):
        require(isinstance(value, str) and _rgba(value, {"variables": {}}) is not None, f"{field} must be a colour",
                field=field)
    sizes = request.get("png_sizes", [512])
    require(isinstance(sizes, list) and sizes and all(isinstance(s, int) and 16 <= s <= 4096 for s in sizes),
            "png_sizes must be a list of base widths, 16-4096 px", field="png_sizes")
    icons = request.get("icons", "web")
    require(icons is False or icons in (*ICON_SETS, "all"), "icons must be web, apple, android, windows, all or false",
            field="icons")
    root = session.resolve(request["output"])
    require(not root.exists() or root.is_dir(), f"{request['output']} exists and is not a folder", field="output")

    report = {}
    base = _load_source(session, request.get("source"), document, request.get("trace", False), report)
    built = lockups(base, request.get("mark"), request.get("wordmark"), request.get("lockups"),
                    request.get("clear_space", 0.25))
    primary = built.get("horizontal") or built.get("logo") or next(iter(built.values()))
    mark = built.get("mark") or primary

    # Every file is planned (and checked against overwrite) before the first one is written.
    documents, targets, previews = {}, [], []
    for lockup, project in built.items():
        for variant, (candidate, recolored) in variants(project, wanted, light, dark).items():
            stem = f"{lockup}-{variant}"
            documents[f"source/{stem}.vixl"] = candidate
            if recolored:
                report.setdefault("variants", {})[stem] = recolored
            try:
                candidate.export(format="SVG", svg_policy="strict")
                targets.append({"path": f"svg/{stem}.svg", "document": f"source/{stem}.vixl", "svg_policy": "strict"})
                previews.append((f"svg/{stem}.svg", USAGE[variant]))
            except VixlError as exc:
                report.setdefault("skipped", []).append(f"svg/{stem}.svg: {exc}")
                previews.append((f"png/{stem}-{sizes[0]}w@1x.png", USAGE[variant]))
            targets.append({"path": f"pdf/{stem}.pdf", "document": f"source/{stem}.vixl"})
            if request.get("cmyk"):
                targets.append({"path": f"pdf/{stem}-cmyk.pdf", "document": f"source/{stem}.vixl", "color_space": "cmyk"})
            width = candidate.state["canvas"]["width"]
            for base_width in sizes:
                for factor in (1, 2, 3):
                    scale = base_width * factor / width
                    if not 0.01 <= scale <= 16:
                        report.setdefault("skipped", []).append(f"png/{stem}-{base_width}w@{factor}x.png: scale {scale:.2f} "
                                                                "is outside 0.01-16")
                        continue
                    targets.append({"path": f"png/{stem}-{base_width}w@{factor}x.png", "document": f"source/{stem}.vixl",
                                    "scale": round(scale, 6)})
    social = _plan_social(primary, mark, light) if request.get("social", True) else {}
    for name, project in social.items():
        documents[f"source/social-{name}.vixl"] = project
        targets.append({"path": f"social/{name}.png", "document": f"source/social-{name}.vixl"})
        previews.append((f"social/{name}.png", "Social avatar (shown as a circle)." if name == "avatar" else
                         "Open Graph link preview (1200×630)."))
    icon_names = []
    if icons:
        entries = [item for key in (ICON_SETS if icons == "all" else [icons]) for item in ICON_SETS[key]]
        icon_names = [f"icons/{name}" for name, _ in entries]
        icon_names += [f"icons/{name}" for name in (["favicon.ico", "site.webmanifest"] if icons in ("web", "all")
                                                     else ["favicon.ico"] if icons == "windows" else [])]
    extra = (["usage.html"] if request.get("proof", True) else []) + ["package.json"]
    zip_path = None
    if request.get("zip"):
        zip_path = session.resolve(request["zip"] if isinstance(request["zip"], str) else f"{request['output'].rstrip('/')}.zip")
        require(zip_path.suffix.lower() == ".zip", "zip must be true or a .zip path", field="zip")
    planned = [root / rel for rel in (*documents, *(t["path"] for t in targets), *icon_names, *extra)]
    if zip_path:
        planned.append(zip_path)
    existing = [session.relative(path) for path in planned if path.exists()]
    require(overwrite or not existing, f"{len(existing)} package file(s) already exist (e.g. {existing[:3]}); "
            "set overwrite=true or choose a new output folder", field="output", existing=existing[:20])
    require(len(targets) <= 640, "The package would write more than 640 files; choose fewer variants or png_sizes",
            field="png_sizes")

    written = []
    try:
        for rel, project in documents.items():
            path = root / rel
            session.make_parent(path)
            if path.exists() and overwrite:
                path.unlink()
            project.path, project._revision = None, None
            project.save(path)
            written.append(path)
        for target in targets:
            target["document"] = session.relative(root / target["document"])
            target["path"] = session.relative(root / target["path"])
        for start in range(0, len(targets), 64):
            batch = export_batch(session, export_file, targets[start:start + 64], overwrite=overwrite, stop_on_error=True)
            written += [session.resolve(item["path"]) for item in batch["results"] if "error" not in item]
            failed = [item for item in batch["results"] if "error" in item]
            if failed:
                raise VixlError(failed[0]["error"]["error"], f"{failed[0]['path']}: {failed[0]['error']['message']}",
                                field="output")
        if icons:
            directory = root / "icons"
            if overwrite:
                for rel in icon_names:
                    (root / rel).unlink(missing_ok=True)
            icon_result = export_icons(mark.clone(), directory, icon_set=icons)
            written += [root / rel for rel in icon_names]
            if icon_result.get("warnings"):
                report.setdefault("notes", []).extend(icon_result["warnings"])
        files = sorted(session.relative(path) for path in written if path.exists())
        usage = None
        if request.get("proof", True):
            from .proof import proof_page

            items = [{"path": session.relative(root / rel), "note": note} for rel, note in previews
                     if (root / rel).exists()]
            items += [{"path": session.relative(root / rel), "label": f"{Path(rel).stem} (source, checked)"}
                      for rel in documents if rel.endswith("full-color.vixl")]
            if icons:
                items.append({"path": session.relative(root / "icons" / "favicon.ico"), "note": "Favicon (16-256 px)."})
            usage_path = root / "usage.html"
            if overwrite:
                usage_path.unlink(missing_ok=True)
            usage = proof_page(items[:200], usage_path, resolve=session.resolve, title="Logo package: usage",
                               limits=session.limits, overwrite=overwrite)
            written.append(usage_path)
            files.append(session.relative(usage_path))
        report["formats"] = ("SVG (strict), PDF (RGB" + (" and CMYK" if request.get("cmyk") else "") + "), PNG at 1x/2x/3x"
                             + (", icons and favicon" if icons else "") + (", social avatar and Open Graph image" if social else "")
                             + ". No EPS: use the PDF or SVG.")
        manifest = {"package": session.relative(root), "lockups": list(built), "variants": wanted,
                    "light": light, "dark": dark, "png_sizes": sizes, "files": files, "usage": USAGE, "report": report}
        manifest_path = root / "package.json"
        with manifest_path.open("w" if overwrite else "x", encoding="utf-8") as stream:
            json.dump(manifest, stream, indent=2)
        written.append(manifest_path)
        files.append(session.relative(manifest_path))
        result = {"output": session.relative(root), "lockups": list(built), "variants": wanted, "count": len(files),
                  "files": files, "report": report}
        if usage:
            result["usage"] = session.relative(root / "usage.html")
        if zip_path:
            if overwrite:
                zip_path.unlink(missing_ok=True)
            session.make_parent(zip_path)
            with zipfile.ZipFile(zip_path, "x", zipfile.ZIP_DEFLATED) as archive:
                for rel in files:
                    path = session.resolve(rel)
                    archive.write(path, Path(rel).relative_to(Path(session.relative(root))).as_posix())
            written.append(zip_path)
            result["zip"] = session.relative(zip_path)
        return result
    except BaseException:
        for path in written:
            if path.exists() and path.is_file():
                path.unlink()
        raise


def field_types():
    path = {"type": "string", "description": "Workspace-relative path."}
    return {
        "source": {**path, "description": "The logo: a .vixl document, or a PNG/JPEG/WEBP/SVG image (default: the "
                   "open document)."},
        "output": {**path, "description": "Package folder (created; existing files are kept unless overwrite)."},
        "trace": {"type": "boolean", "default": False, "description": "Raster source: trace it to vector paths with "
                  "drawing vectorize (one colour), so SVG and the mono variants are vector."},
        "variants": {"type": "array", "items": {"enum": list(VARIANTS)}, "description": "Variants to build (default all)."},
        "mark": {"type": "string", "description": "Top-level layer (name or id) holding the symbol; with wordmark, "
                 "builds lockups."},
        "wordmark": {"type": "string", "description": "Top-level layer (name or id) holding the logotype."},
        "lockups": {"type": "array", "items": {"enum": list(LOCKUPS)}, "description": "With mark and wordmark: "
                    "the lockups to build (default mark, horizontal, stacked)."},
        "clear_space": {"type": "number", "minimum": 0, "maximum": 2, "default": 0.25,
                        "description": "Clear space around and between parts, as a fraction of the mark's height."},
        "light": {"type": "string", "default": "#ffffff", "description": "Background colour of on-light and social images."},
        "dark": {"type": "string", "default": "#111111", "description": "Background colour of on-dark."},
        "png_sizes": {"type": "array", "items": {"type": "integer", "minimum": 16, "maximum": 4096}, "default": [512],
                      "description": "Base widths in px; each is written at 1x, 2x and 3x."},
        "cmyk": {"type": "boolean", "default": False, "description": "Also write CMYK PDFs (-cmyk.pdf)."},
        "icons": {"type": ["string", "boolean"], "enum": ["web", "apple", "android", "windows", "all", False],
                  "default": "web", "description": "Icon set from the mark (web includes favicon.ico); false skips it."},
        "social": {"type": "boolean", "default": True, "description": "Write a social avatar (800×800) and an Open "
                   "Graph image (1200×630)."},
        "proof": {"type": "boolean", "default": True, "description": "Write usage.html, the usage sheet (a proof page)."},
        "zip": {"type": ["boolean", "string"], "description": "Also zip the package: true writes <output>.zip, or "
                "give a .zip path."},
        "overwrite": {"type": "boolean", "default": False, "description": "Replace existing package files."},
    }

