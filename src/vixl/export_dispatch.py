"""Export a document to a file or bytes in any supported format: the dispatcher behind ``Project.export``.

It lives apart from ``render.py`` so the renderer does not import the PDF, PowerPoint, PSD, SVG and HTML writers.
"""

from copy import deepcopy
import io
from pathlib import Path

from PIL import Image, ImageOps

from .errors import VixlError, require
from .model import finite
from .render import EXPORT_PROFILES, color, render, view_page


def export(
    project,
    path=None,
    *,
    quality=None,
    scale=1,
    profile=None,
    variables=None,
    format=None,
    background="white",
    artboard=None,
    comp=None,
    sampling="smooth",
    svg_policy="appearance",
    color_space="rgb",
    icc_profile=None,
    intent="relative",
    black_generation=1.0,
    ink_limit=None,
    proof=False,
    simulate=None,
    dpi=None,
    icon_sizes=None,
    time=None,
    page=None,
    pages=None,
    pdf_content=None,
    report=None,
    fillable=False,
    values=None,
    fill_mode="flatten",
    alpha="auto",
    presenter=None,
    overwrite=False,
    width=480,
    columns=None,
    labels=True,
    title=None,
    max_bytes=None,
    isolate=None,
    padding=None,
    svg_document=True,
):
    """Render and encode. ``color_space='cmyk'`` separates JPEG/TIFF/PDF output (ICC profile
    bytes in ``icc_profile`` for press-accurate separation, else device-naive GCR with
    ``black_generation`` 0–1 and ``ink_limit`` in percent). ``proof`` soft-proofs RGB output
    through that separation; ``simulate`` previews a color-vision deficiency. ``alpha`` sets the
    channels of PNG, WEBP, TIFF and AVIF output: ``keep`` always writes RGBA, ``auto`` writes RGB
    when every pixel is opaque and RGBA otherwise (the file export default), and ``flatten``
    composites onto ``background`` and writes RGB (as JPEG and PDF always do). PDF is vector by
    default, RGB or CMYK: ``pdf_content='raster'`` writes one image per page instead, and ``report``
    receives ``content``, ``content_reason``, ``raster_fallbacks`` and ``page_size``. HTML output of a
    multi-page document is a self-contained slide presentation (see ``presenter.py``): ``presenter``
    is ``False`` for the plain single-image HTML, ``True`` for a presentation of any document, or
    a dict of options (theme, notes, slide_images, start, title). ``title`` is the PDF document title
    (default: the page's title layer, then the file name). ``max_bytes`` is a size budget: when the
    encoded file is larger, ``report['warnings']`` says so (the export still succeeds). ``isolate`` (layer
    names, object paths such as ``dog/head`` or ``object:KIND``) exports only those layers, cropped to their ink
    plus ``padding`` pixels on a transparent canvas, in any format. SVG output embeds the document it shows (its layers,
    and the images and fonts they use) so that importing the SVG gives back the same editable layers;
    ``svg_document=False`` leaves it out."""
    require(isinstance(overwrite, bool), "overwrite must be true or false", field="overwrite")
    require(path is None or overwrite or not Path(path).exists(),
            "Export output already exists; pass overwrite=True to replace it", "output_exists", field="path")
    require(path is None or Path(path).suffix.lower() != ".vixl", "Cannot export over a Vixl project")
    quality_given = quality is not None  # None: not given (PDF images stay lossless, others use 90)
    quality = 90 if quality is None else quality
    require(alpha in ("auto", "keep", "flatten"), "alpha must be auto, keep or flatten", field="alpha")
    require(sampling in ("smooth", "nearest"), "Sampling must be smooth or nearest")
    require(color_space in ("rgb", "cmyk"), "Color space must be rgb or cmyk")
    if time is not None:
        # A single timeline frame: the document with every animated property applied at ``time``.
        from .timeline import default_timeline, parse_time, project_at

        timeline = project.state.get("timeline") or default_timeline()
        project = project_at(project, parse_time(time, timeline["duration"], timeline.get("markers")))
    require(svg_policy in ("appearance", "strict"), "SVG policy must be appearance or strict")
    if isolate is not None:
        require(not pages and page != "all", "isolate exports one page; pass page, not pages", field="isolate")
        require(padding is None or 0 <= finite(padding, "padding", 0, 4096), "padding is 0-4096 px", field="padding")
        from .objects import isolated_export

        project = isolated_export(view_page(project, page) if page is not None else project, isolate, padding=padding)
        page = None
        if report is not None:
            report["isolated"] = {"layers": [project.layer(ident)["name"] for ident in project._isolated],
                                  "size": [project.state["canvas"]["width"], project.state["canvas"]["height"]]}
    else:
        require(padding is None, "padding goes with isolate", field="padding")
    from .pages import parse_pages

    all_pages = pages == "all"
    pages = None if all_pages else parse_pages(pages)
    if isinstance(page, str) and page.isdigit():
        page = int(page)
    suffix = Path(path).suffix.lower() if path else ""
    requested = (format or suffix.lstrip(".") or "PNG").upper()
    sheet = page == "all" or (all_pages or bool(pages)) and requested not in ("PDF", "PPTX", "HTML", "HTM")
    require(page is None or not pages, "Pass page or pages, not both")
    if sheet:
        require(requested in ("PNG", "JPG", "JPEG", "WEBP", "TIFF", "TIF", "AVIF"),
                "Page contact sheets require a raster image format", field="page")
        require(not (artboard or comp or profile or time is not None),
                "Page contact sheets do not take artboard, comp, profile or time", field="page")
    require(fill_mode in ("flatten", "editable"), "fill_mode must be flatten or editable", field="fill_mode")
    if fillable or fill_mode == "editable":
        # A fillable PDF: Vixl's artwork with AcroForm fields on top (prefilled with ``values``).
        require((format or "").upper() == "PDF" or suffix == ".pdf" or (not format and not suffix),
                "Fillable forms export as PDF", field="fillable")
        require(color_space == "rgb", "Fillable PDFs are RGB; export CMYK without fillable", field="color_space")
        require(page is None or not pages, "Pass page or pages, not both")
        from .pdf_forms import export_fillable

        return export_fillable(project, path, pages=pages or ([page] if page is not None else None), values=values,
                               dpi=dpi, content=pdf_content or "vector", background=background, report=report)
    if variables:
        from .forms import all_fields, has_fields

        if has_fields(project):
            keys = {layer["field"]["key"] for _, layer in all_fields(project)} & set(variables)
            require(not keys, f"{', '.join(sorted(keys))} name form fields; pass field values in values, not variables",
                    field="variables")
    if values:
        # Flattened filling: the values are drawn into a throwaway copy that never touches the
        # document or the persistent render cache.
        from .forms import with_values

        project = with_values(project, values)
        if (format or "").upper() == "PDF" or suffix == ".pdf":
            pdf_content = pdf_content or "vector"
    from .presenter import export_presenter, wants_presenter

    html_name = (format or (suffix[1:] if suffix in (".html", ".htm") else "")).upper() in ("HTML", "HTM")
    # Options a presentation cannot honor keep a paged document's HTML export the single artwork page.
    artwork = bool(profile or artboard or comp or proof or simulate or icc_profile) or color_space != "rgb"
    if wants_presenter(False if presenter is None and artwork else presenter, html=html_name,
                       paged=bool(project.state.get("pages")), page=page):
        require(not artwork, "A presentation shows pages in RGB; profile, artboard, comp, proof, simulate and CMYK do not apply")
        require(page is None or not pages, "Pass page or pages, not both")
        data = export_presenter(project, pages=pages or ([page] if page is not None else None), options=presenter,
                                variables=variables, svg_policy=svg_policy, scale=scale, report=report)
        if path:
            Path(path).write_bytes(data)
        return data
    from .plugins import first as plugin_first

    exported = plugin_first("export-format", project, path, (format or suffix.lstrip(".")).lower(), report,
                            pages=pages, page=page, artwork=artwork, isolate=isolate)
    if exported is not None:
        return exported
    if (format or "").upper() == "PSD" or suffix == ".psd":
        require(not (pages or artwork), "PSD export writes one page in RGB; profile, artboard, "
                "comp, proof, simulate, CMYK and pages do not apply", field="format")
        from .psd_export import export_psd

        return export_psd(project, path, page=page, variables=variables, report=report)
    if (format or "").upper() == "PPTX" or suffix == ".pptx":
        require(not artwork, "PPTX keeps editable RGB slides; profile, artboard, comp, proof, simulate and CMYK do not "
                "apply (export a PNG or PDF to preview them)", field="format")
        from .pptx_export import export_pptx

        return export_pptx(project, path, pages=pages, dpi=dpi, report=report)
    wants_pdf = (format or "").upper() == "PDF" or suffix == ".pdf"
    paged = bool(project.state.get("pages"))
    requested_scale = scale
    raster_only = [name for name, used in (("profile", profile), ("artboard", artboard), ("comp", comp), ("proof", proof),
                                           ("simulate", simulate)) if used]
    if wants_pdf:
        require(pdf_content in (None, "vector", "raster"), "pdf_content must be vector or raster", field="pdf_content")
        require(not (raster_only and pdf_content == "vector"),
                f"pdf_content=vector cannot be combined with {', '.join(raster_only)}: those export the page as an image",
                field="pdf_content")
    if wants_pdf and not raster_only and (pdf_content or scale == 1):
        # Every PDF is written by Vixl's own writer: vector unless raster is asked for (exact physical
        # print pages, TrimBox and BleedBox, selectable text, CMYK). A scaled export is a larger
        # raster, so it keeps the image path below unless pdf_content says otherwise.
        require(page is None or not pages, "Pass page or pages, not both")
        from .pdf_export import export_pdf

        separation = None
        if color_space == "cmyk":
            from . import colors

            if icc_profile is None and report is not None:
                report.setdefault("warnings", []).append(
                    "CMYK conversion has no ICC profile; colors may shift or lose saturation. "
                    "Supply icc_profile (CLI --icc) for the intended printer/paper.")
            separation = dict(profile=colors.load_profile(icc_profile) if icc_profile is not None else None,
                              intent=intent, black=finite(black_generation, "black_generation", 0, 1),
                              ink_limit=None if ink_limit is None else ink_limit / 100, background=background)
        content = pdf_content or "vector"
        data = export_pdf(project, path, pages=pages or ([page] if page is not None else None), content=content,
                          dpi=dpi, background=background, color_space=color_space, separation=separation,
                          jpeg_quality=int(quality) if quality_given else None, title=title, report=report)
        if report is not None:
            report["content_reason"] = ("requested with pdf_content" if pdf_content else
                                        "default: vector, with images only for what PDF cannot draw (see raster_fallbacks)")
        return data
    if not sheet and (page is not None or paged):
        project = view_page(project, page)
    resample = Image.Resampling.NEAREST if sampling == "nearest" else Image.Resampling.LANCZOS
    require(path is None or Path(path).suffix.lower() != ".vixl", "Cannot export over a Vixl project")
    finite(scale, "scale", 0.01, 16)
    finite(quality, "quality", 1, 100)
    settings = {}
    if profile:
        require(profile in EXPORT_PROFILES, f"Unknown export profile: {profile}")
        settings = deepcopy(EXPORT_PROFILES[profile])
    requested_format = (
        format or settings.get("format") or (Path(path).suffix[1:] if path and Path(path).suffix.lower() in (".svg", ".html", ".htm") else "")
    ).upper()
    if requested_format in ("SVG", "HTML", "HTM"):
        require(not profile, "SVG export does not use raster export profiles")
        require(
            color_space == "rgb" and not (proof or simulate or icc_profile),
            "SVG export is RGB; use PDF, TIFF or JPEG for CMYK, and a raster or PDF export for proof and simulate",
        )
        from .svg import export_svg

        if requested_format in ("HTML", "HTM"):
            from .html_export import export_html
            export_svg = export_html
        data = export_svg(project, scale=scale, variables=variables, artboard=artboard, comp=comp, svg_policy=svg_policy,
                          **({"document": svg_document} if requested_format == "SVG" else {}))
        if path:
            Path(path).write_bytes(data)
        return data
    require(svg_policy == "appearance", "Strict SVG policy requires SVG output")
    if format:
        format = {"JPG": "JPEG", "TIF": "TIFF"}.get(format.upper(), format.upper())
    image = None
    if sheet:
        from .deck import contact_sheet

        image = contact_sheet(project, pages=pages, width=width, columns=columns, labels=labels, variables=variables)
    if image is None and scale > 1 and sampling != "nearest" and not (artboard or comp or settings.get("size")):
        # Enlarge by re-rendering a scaled copy, so text, shapes and vectors stay crisp.
        from .proxy import scaled_project

        project.limits.size(round(project.state["canvas"]["width"] * scale), round(project.state["canvas"]["height"] * scale))
        proxy = scaled_project(project, scale)
        if proxy is not None:
            image = render(proxy, variables)
            scale = 1
    if image is None:
        image = render(project, variables, artboard, comp)
    size = settings.pop("size", None)
    if size:
        image = ImageOps.contain(image, size, resample)
    target_size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    project.limits.size(*target_size)
    if target_size != image.size:
        image = image.resize(target_size, resample)
    profile_format = settings.pop("format", None)
    fmt = (
        format
        or profile_format
        or (
            {
                ".jpg": "JPEG",
                ".jpeg": "JPEG",
                ".webp": "WEBP",
                ".tif": "TIFF",
                ".tiff": "TIFF",
                ".png": "PNG",
                ".avif": "AVIF",
                ".pdf": "PDF",
                ".ico": "ICO",
            }.get(Path(path).suffix.lower())
            if path
            else "PNG"
        )
    )
    require(fmt in ("PNG", "JPEG", "WEBP", "TIFF", "AVIF", "PDF", "ICO"),
            f"Unsupported export format {(Path(path).suffix if path and not format else format) or '(none)'!r}; use png, "
            "jpg, webp, tiff, avif, pdf, ico, svg, pptx, psd or html (fonts: ttf, otf, woff, woff2; audio: vixl_export "
            "(.wav), or a .wav path on the CLI; animation: export-timeline)",
            field="format")
    from . import colors

    cms = None
    if icc_profile is not None:
        cms = colors.load_profile(icc_profile)
    require(ink_limit is None or 100 <= ink_limit <= 400, "Ink limit must be 100–400%")
    separation = dict(
        profile=cms,
        intent=intent,
        black=finite(black_generation, "black_generation", 0, 1),
        ink_limit=None if ink_limit is None else ink_limit / 100,
        background=background,
    )
    if simulate:
        image = colors.simulate_vision(image, simulate)
    if proof:
        image = colors.proof_image(image, **separation)
    canvas_dpi = project.state["canvas"].get("dpi")
    if dpi is not None:
        finite(dpi, "dpi", 36, 2400)
    # requested_scale: a crisp enlargement re-renders at full size and resets ``scale`` to 1.
    effective_dpi = dpi or (canvas_dpi * requested_scale if canvas_dpi else None)
    if not effective_dpi and fmt == "TIFF":
        # TIFF is a print format and readers assume 1 dpi without resolution tags; use the 72 dpi a PDF export assumes.
        effective_dpi = 72 * requested_scale
    if effective_dpi and "dpi" not in settings:
        settings["dpi"] = (round(effective_dpi, 3), round(effective_dpi, 3))
    if color_space == "cmyk":
        require(fmt in ("JPEG", "TIFF", "PDF"), "CMYK export supports JPEG, TIFF and PDF" + (
            "; for an RGB soft proof of print colours drop --cmyk (color_space) and keep --proof" if proof else ""),
            field="color_space")
        require(not proof, "Choose either a CMYK separation or an RGB soft proof")
        image = colors.cmyk_image(image, **separation)
        if cms is not None:
            settings["icc_profile"] = cms.tobytes()
    elif icc_profile is not None:
        require(proof, "An ICC profile needs color_space='cmyk' or proof=True")
    if image.mode == "RGBA" and (fmt in ("JPEG", "PDF") or alpha == "flatten" and fmt != "ICO"):
        base = Image.new("RGBA", image.size, color(background))
        base.alpha_composite(image)
        image = base.convert("RGB")
    elif image.mode == "RGBA" and alpha == "auto" and fmt != "ICO" and image.getchannel("A").getextrema()[0] == 255:
        image = image.convert("RGB")  # an opaque canvas needs no alpha channel
    if fmt == "PDF":
        settings["resolution"] = settings.pop("dpi", (72, 72))[0]
        settings.pop("quality", None)
    if fmt == "ICO":
        sizes = icon_sizes or [16, 24, 32, 48, 64, 128, 256]
        require(
            isinstance(sizes, list) and 0 < len(sizes) <= 16 and all(isinstance(s, int) and 8 <= s <= 256 for s in sizes),
            "ICO sizes must be 1–16 integers from 8 to 256",
        )
        require(abs(image.width - image.height) <= 1, "ICO export needs a square canvas (try the favicon size)")
        settings = {"sizes": [(s, s) for s in sorted(set(sizes))]}
    else:
        require(icon_sizes is None, "icon_sizes applies to ICO export")
        settings.setdefault("quality", int(quality))
    stream = io.BytesIO()
    try:
        image.save(stream, format=fmt, **settings)
    except (OSError, KeyError) as exc:
        raise VixlError("codec_error", str(exc)) from exc
    data = stream.getvalue()
    if fmt == "PDF" and report is not None:
        report.update(content="raster", color_space=color_space, content_reason=(
            f"{', '.join(raster_only)} export the page as an image" if raster_only else
            f"scale {requested_scale:g} exports a larger image; pass pdf_content for a vector or raster PDF at its natural size"))
    if report is not None and fmt in ("PNG", "JPEG", "WEBP", "TIFF", "AVIF"):
        from .animation import still_size_warnings

        if warnings := still_size_warnings(project, fmt, len(data), max_bytes):
            report.setdefault("warnings", []).extend(warnings)
    if path:
        Path(path).write_bytes(data)
    return data
