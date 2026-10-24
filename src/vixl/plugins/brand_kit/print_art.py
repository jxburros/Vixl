"""The ``print-art`` action of the ``mockup`` workflow: print-ready art for each placed area of a product.

Each placed design is drawn at its area's ``print_size_mm`` and ``dpi`` (a ``fit`` of the design into the print box, as
the mockup shows it), saved as an editable ``source/AREA.vixl`` linked to the design and exported as ``AREA.png`` with
the resolution recorded, through the same export path as ``vixl_export`` (so the call limits and the refusal to overwrite
apply). Two options prepare the art for screen printing and direct-to-garment:

- ``spot_colors: N`` posterizes the art to at most N flat inks (median cut over the printed pixels; a pixel prints
  or it does not, at half alpha) and writes ``AREA-spot.png`` with the separations: one film positive per ink
  (``AREA-inkK.png``, black where the ink prints), light inks first, or the same as pages of ``AREA-separations.pdf``
  with ``separations: "pdf"``.
- ``underbase: true`` adds a white choke layer under the colours, ``AREA-underbase.png`` (black where white ink
  prints, pulled in by ``choke_mm`` so white never shows at the edge). Only dark garments get one: on a light
  garment (or a product with no garment colour) it is skipped and the result says why.
"""

import os

from ...errors import VixlError, require
from . import mockups

FIELDS = {"mockup", "design", "place", "output", "dpi", "fit", "source_page", "artboard", "garment_color",
          "spot_colors", "separations", "underbase", "choke_mm", "overwrite"}
REQUIRED = {"mockup", "output"}
DARK_GARMENT = 0.4  # WCAG relative luminance below which a garment counts as dark
MAX_INKS = 12
MAX_PIXELS_SAMPLED = 1_000_000

FIELD_TYPES = {
    "mockup": {"type": "string", "description": "The product template (mockup-list): its areas with a print size "
               "give the print files."},
    "design": mockups.FIELD_TYPES["design"],
    "place": mockups.FIELD_TYPES["place"],
    "output": {"type": "string", "description": "A new folder for the print files: AREA.png and source/AREA.vixl per "
               "area, plus the separation files."},
    "dpi": {"type": "number", "minimum": 72, "maximum": 1200, "default": 300,
            "description": "Print resolution: each area is print_size_mm / 25.4 × dpi pixels, within the pixel limit."},
    "fit": mockups.FIELD_TYPES["fit"],
    "source_page": mockups.FIELD_TYPES["source_page"],
    "artboard": mockups.FIELD_TYPES["artboard"],
    "garment_color": {"type": "string", "description": "The garment's colour, which decides whether an underbase is "
                      "made (default: the template's)."},
    "spot_colors": {"type": "integer", "minimum": 1, "maximum": MAX_INKS,
                    "description": "Posterize each area to at most this many inks and write the separations."},
    "separations": {"type": "string", "enum": ["png", "pdf"], "default": "png",
                    "description": "Separations as one PNG per ink (film positive: black where the ink prints) or as "
                                   "the pages of one PDF per area."},
    "underbase": {"type": "boolean", "default": False,
                  "description": "Write a white choke layer under the art, for dark garments only."},
    "choke_mm": {"type": "number", "minimum": 0, "maximum": 5, "default": 0.2,
                 "description": "How far the underbase is pulled in from the art's edge, in millimetres."},
    "overwrite": {"type": "boolean", "default": False, "description": "Replace existing print files."},
}


def is_dark(colour):
    """Whether a garment colour is dark enough to need a white underbase."""
    from ...colors import relative_luminance
    from ...render import color

    return relative_luminance([c / 255 for c in color(colour)[:3]]) < DARK_GARMENT


def pixel_size(print_size_mm, dpi):
    return tuple(max(1, round(mm / 25.4 * dpi)) for mm in print_size_mm)


def _merge_palette(counts, table, inks):
    """Merge a fine palette down to ``inks`` clusters by the least perceptual loss (Ward's criterion in OKLab, weighted
    by pixel count): ``({palette index: cluster}, [cluster colour])``."""
    from ...colors import srgb_to_oklab

    clusters = [{"w": count, "lab": srgb_to_oklab([c / 255 for c in table[index]]), "rgb": [c * count for c in table[index]],
                 "members": [index]} for count, index in counts]

    def cost(a, b):
        return a["w"] * b["w"] / (a["w"] + b["w"]) * sum((x - y) ** 2 for x, y in zip(a["lab"], b["lab"]))

    while len(clusters) > inks:
        i, j = min(((i, j) for i in range(len(clusters)) for j in range(i + 1, len(clusters))),
                   key=lambda pair: cost(clusters[pair[0]], clusters[pair[1]]))
        a, b = clusters[i], clusters[j]
        w = a["w"] + b["w"]
        clusters[i] = {"w": w, "lab": [(x * a["w"] + y * b["w"]) / w for x, y in zip(a["lab"], b["lab"])],
                       "rgb": [x + y for x, y in zip(a["rgb"], b["rgb"])], "members": a["members"] + b["members"]}
        del clusters[j]
    mapping = {member: n for n, cluster in enumerate(clusters) for member in cluster["members"]}
    return mapping, [tuple(round(c / cluster["w"]) for c in cluster["rgb"]) for cluster in clusters]


def separate(image, inks):
    """``(posterized RGBA, [(hex colour, mask)])``: ``image`` reduced to at most ``inks`` flat colours. A pixel prints
    where its alpha is at least half; the inks are ordered light to dark, the order they print in."""
    import numpy as np
    from PIL import Image

    pixels = np.asarray(image.convert("RGBA"))
    printed = pixels[..., 3] >= 128
    require(printed.any(), "The design prints nothing in this area (it is fully transparent)", field="design")
    rgb = np.ascontiguousarray(pixels[..., :3])
    chosen = rgb[printed]
    if len(chosen) > MAX_PIXELS_SAMPLED:
        chosen = chosen[:: len(chosen) // MAX_PIXELS_SAMPLED + 1]
    fine = Image.fromarray(chosen.reshape(1, -1, 3), "RGB").quantize(
        colors=min(64, max(16, inks * 8)), method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    table = np.asarray(fine.getpalette()[:768], dtype=np.uint8).reshape(-1, 3)
    mapping, colours = _merge_palette(fine.getcolors(), table.tolist(), inks)
    lookup = np.zeros(256, np.int64)
    for index, cluster in mapping.items():
        lookup[index] = cluster
    labels = lookup[np.asarray(Image.fromarray(rgb, "RGB").quantize(palette=fine, dither=Image.Dither.NONE))]
    found = [(colour, printed & (labels == n)) for n, colour in enumerate(colours)]
    found = [(colour, mask) for colour, mask in found if mask.any()]
    found.sort(key=lambda item: -(0.2126 * item[0][0] + 0.7152 * item[0][1] + 0.0722 * item[0][2]))
    out = np.zeros(pixels.shape, np.uint8)
    for colour, mask in found:
        out[mask, :3] = colour
    out[printed, 3] = 255
    return Image.fromarray(out, "RGBA"), [("#%02x%02x%02x" % colour, mask) for colour, mask in found]


def film(mask):
    """A film positive of ``mask``: 8-bit grey, black where the ink prints."""
    import numpy as np
    from PIL import Image

    return Image.fromarray(np.where(mask, 0, 255).astype(np.uint8), "L")


def choked(mask, pixels):
    """``mask`` pulled in by ``pixels`` (a square structuring element), so a white underbase stays inside the colours."""
    if pixels <= 0:
        return mask
    import numpy as np
    from PIL import Image, ImageFilter

    grey = Image.fromarray(mask.astype(np.uint8) * 255, "L")
    return np.asarray(grey.filter(ImageFilter.MinFilter(2 * pixels + 1))) >= 128


def _write(session, path, save, overwrite, written):
    """Write one file atomically: ``save(file object)``; an existing file is kept unless ``overwrite``."""
    from ...fileio import temporary

    session.make_parent(path)
    fd, temporary_path = temporary(path.parent, like=path if path.exists() else None)
    try:
        with os.fdopen(fd, "wb") as stream:
            save(stream)
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temporary_path, path)
        else:
            os.link(temporary_path, path)
        written.append(path)
    except FileExistsError as exc:
        raise VixlError("invalid_request", f"{session.relative(path)} already exists; set overwrite=true",
                        field="output") from exc
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def print_document(session, design, size, dpi, settings, destination):
    """The editable print document: the design fitted into a transparent canvas of ``size`` pixels."""
    from ...project import Project

    width, height = size
    session.limits.size(width, height)
    project = Project(width, height, "transparent", limits=session.limits)
    project._workspace = session.workspace
    project.path, project._revision = destination, None
    project.apply([{"type": "canvas", "dpi": dpi},
                   {"type": "link", "name": "art", "source": str(design), "x": 0, "y": 0, "width": width,
                    "height": height, "fit": settings["fit"],
                    **{k: settings[k] for k in ("source_page", "artboard") if settings.get(k) is not None}}])
    return project


def build(session, request, document=None):
    from ...export_batch import export_batch
    from ...io_policy import export_file
    from PIL import Image

    names = request["mockup"]
    require(isinstance(names, str), "print-art takes one template name in mockup", field="mockup")
    available = mockups.catalog(session.workspace)
    mockups.resolve_templates(session, {"mockup": names}, available)
    spec = available[names]
    if names not in mockups.BUILTINS:
        mockups.validate(spec)
    settings = mockups.request_settings({k: request[k] for k in ("fit", "source_page", "artboard", "garment_color")
                                         if k in request})
    mockups.check_garment_color(names, spec, settings)
    designs = mockups.plan_designs(session, spec, names, request)
    every = mockups.placements(spec)
    missing = [key for key in designs if not every[key].get("print_size_mm")]
    require(not missing, f"{names!r} has no print size for {', '.join(missing)}: print-art needs print_size_mm on the "
            f"placement (mockup-list shows the areas that have one)", field="place")
    dpi = request.get("dpi", 300)
    require(isinstance(dpi, (int, float)) and not isinstance(dpi, bool) and 72 <= dpi <= 1200,
            "dpi is 72-1200", field="dpi")
    spots = request.get("spot_colors")
    require(spots is None or (isinstance(spots, int) and not isinstance(spots, bool) and 1 <= spots <= MAX_INKS),
            f"spot_colors is a number of inks, 1-{MAX_INKS}", field="spot_colors")
    separations = request.get("separations", "png")
    require(separations in ("png", "pdf"), "separations is png or pdf", field="separations")
    for key in ("underbase", "overwrite"):
        require(type(request.get(key, False)) is bool, f"{key} must be true or false", field=key)
    choke_mm = request.get("choke_mm", 0.2)
    require(isinstance(choke_mm, (int, float)) and not isinstance(choke_mm, bool) and 0 <= choke_mm <= 5,
            "choke_mm is 0-5 millimetres", field="choke_mm")
    overwrite = request.get("overwrite", False)
    underbase = request.get("underbase", False)
    colour = settings["garment_color"] or spec.get("garment_color")
    notes = []
    make_underbase = False
    if underbase:
        if not colour:
            notes.append(f"underbase skipped: {names!r} is not a garment (it has no garment colour)")
        elif not is_dark(colour):
            notes.append(f"underbase skipped: {colour} is a light garment; only dark garments get a white underbase")
        else:
            make_underbase = True
    root = session.resolve(request["output"])
    require(not root.exists() or root.is_dir(), f"{request['output']} exists and is not a folder", field="output")
    sizes = {key: pixel_size(every[key]["print_size_mm"], dpi) for key in designs}
    for key, size in sizes.items():
        session.limits.size(*size)

    plan = {}
    for key in designs:
        extra = []
        if spots:
            extra += [f"{key}-spot.png"]
            extra += ([f"{key}-separations.pdf"] if separations == "pdf"
                      else [f"{key}-ink{n}.png" for n in range(1, spots + 1)])
        if make_underbase:
            extra += [f"{key}-underbase.png"] if separations == "png" or not spots else []
        plan[key] = [f"{key}.png", f"source/{key}.vixl", *extra]
    existing = [session.relative(root / rel) for rels in plan.values() for rel in rels if (root / rel).exists()]
    require(overwrite or not existing, f"{len(existing)} print file(s) already exist (e.g. {existing[:3]}); set "
            "overwrite=true or choose a new output folder", field="output", existing=existing[:20])

    written = []
    rows = []
    try:
        targets = []
        for key, entry in designs.items():
            path = root / f"source/{key}.vixl"
            project = print_document(session, entry["design"], sizes[key], dpi,
                                     {**settings, **{k: v for k, v in entry.items() if k != "design"}}, path)
            session.make_parent(path)
            project.save(path, overwrite=overwrite)
            written.append(path)
            targets.append({"path": session.relative(root / f"{key}.png"), "document": session.relative(path),
                            "alpha": "keep", "dpi": dpi})
        batch = export_batch(session, export_file, targets, overwrite=overwrite, stop_on_error=True)
        for item in batch["results"]:
            if "error" in item:
                raise VixlError(item["error"]["error"], f"{item['path']}: {item['error']['message']}", field="output")
            written.append(session.resolve(item["path"]))
        for key, entry in designs.items():
            row = {"area": key, "design": session.relative(entry["design"]),
                   "print_size_mm": every[key]["print_size_mm"], "dpi": dpi, "pixels": list(sizes[key]),
                   "file": session.relative(root / f"{key}.png"), "source": session.relative(root / f"source/{key}.vixl")}
            if spots or make_underbase:
                with Image.open(root / f"{key}.png") as opened:
                    art = opened.convert("RGBA")
                row.update(_separations(session, root, key, art, spots, separations, make_underbase, choke_mm, dpi,
                                        overwrite, written))
            rows.append(row)
    except BaseException:
        for path in written:
            if path.exists() and path.is_file():
                path.unlink()
        raise
    result = {"mockup": names, "output": session.relative(root), "dpi": dpi, "areas": rows,
              "files": sorted({file for row in rows for file in _files(row)})}
    if colour and spec.get("garment_color"):
        result["garment_color"] = colour
        result["dark_garment"] = is_dark(colour)
    if notes:
        result["notes"] = notes
    return result


def _files(row):
    found = [row["file"], row["source"]]
    spot = row.get("spot")
    if spot:
        found += [spot["file"]] + [ink["file"] for ink in spot["inks"] if ink.get("file")] + (
            [spot["pdf"]] if spot.get("pdf") else [])
    if row.get("underbase", {}).get("file"):
        found.append(row["underbase"]["file"])
    return found


def _separations(session, root, key, art, spots, separations, make_underbase, choke_mm, dpi, overwrite, written):
    """Write the posterized art, its separations and the underbase of one area; returns the result rows."""
    import numpy as np

    out = {}
    pages = []
    printed = np.asarray(art)[..., 3] >= 128
    if make_underbase:
        mask = choked(printed, round(choke_mm / 25.4 * dpi))
        sheet = film(mask)
        out["underbase"] = {"color": "#ffffff", "choke_mm": choke_mm,
                            "coverage": round(float(mask.mean()), 4)}
        if separations == "png" or not spots:
            path = root / f"{key}-underbase.png"
            _write(session, path, lambda stream, sheet=sheet: sheet.save(stream, "PNG", dpi=(dpi, dpi)), overwrite, written)
            out["underbase"]["file"] = session.relative(path)
        pages.append(sheet)
    if spots:
        posterized, inks = separate(art, spots)
        path = root / f"{key}-spot.png"
        _write(session, path, lambda stream: posterized.save(stream, "PNG", dpi=(dpi, dpi)), overwrite, written)
        rows = []
        for number, (colour, mask) in enumerate(inks, 1):
            sheet = film(mask)
            row = {"ink": number, "color": colour, "coverage": round(float(mask.mean()), 4)}
            if separations == "png":
                ink_path = root / f"{key}-ink{number}.png"
                _write(session, ink_path, lambda stream, sheet=sheet: sheet.save(stream, "PNG", dpi=(dpi, dpi)),
                       overwrite, written)
                row["file"] = session.relative(ink_path)
            pages.append(sheet)
            rows.append(row)
        out["spot"] = {"requested": spots, "colors": len(rows), "file": session.relative(path), "inks": rows}
        if separations == "pdf":
            pdf = root / f"{key}-separations.pdf"
            _write(session, pdf, lambda stream: pages[0].save(stream, "PDF", resolution=dpi, save_all=True,
                                                              append_images=pages[1:]), overwrite, written)
            out["spot"]["pdf"] = session.relative(pdf)
            out["spot"]["pages"] = (["underbase"] if make_underbase else []) + [f"ink {r['ink']}" for r in rows]
            if make_underbase:
                out["underbase"]["page"] = 1
    return out
