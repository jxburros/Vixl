"""Pixel diffs between two documents or images (``vixl diff``, proof pages, the GitHub Action).

Either side can be a ``.vixl`` document (rendered at full size), a raster image, an SVG (rendered with
resvg) or a PDF (first page, needs pypdfium2). The comparison is ``checks.pixel_diff``, the same one
``vixl_render_compare`` uses.
"""

import io
from pathlib import Path

from .errors import VixlError, require
from .model import Limits

RASTER = (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".gif", ".bmp", ".avif", ".ico")
VISUAL = (".vixl", ".svg", ".pdf", *RASTER)


def load_visual(path, limits=None, *, data=None, page=1, dpi=144):
    """An RGBA image of a document or image file. ``data`` gives the bytes instead of reading ``path``
    (``path`` then only names the format), for a base version taken from ``git show``."""
    from .assets import decode, read_bounded

    limits = limits or Limits()
    suffix = Path(path).suffix.lower()
    require(suffix in VISUAL, f"Cannot compare {Path(path).name}: give a .vixl document or an image "
            f"({', '.join(VISUAL[1:])})", "invalid_request", field="path")
    if data is None:
        require(Path(path).is_file(), f"No such file: {path}", "not_found", field="path")
        data = read_bounded(path, limits.max_project_bytes if suffix == ".vixl" else limits.max_asset_bytes)
    if suffix == ".vixl":
        from .project import Project

        with _staged(path, data) as staged:
            return Project.load(staged, limits=limits).render().convert("RGBA")
    if suffix == ".svg":
        import resvg_py

        try:
            rendered = resvg_py.svg_to_bytes(svg_string=data.decode("utf-8"))
        except Exception as exc:  # resvg reports malformed SVG with assorted exception types
            raise VixlError("invalid_image", f"Cannot render {Path(path).name}: {exc}", field="path") from exc
        return decode(bytes(rendered), limits)
    if suffix == ".pdf":
        try:
            import pypdfium2
        except ImportError as exc:
            raise VixlError("missing_dependency", "Comparing PDFs needs pypdfium2 (pip install 'vixl-engine[pdf]')",
                            field="path") from exc
        document = pypdfium2.PdfDocument(data)
        try:
            require(1 <= page <= len(document), f"The PDF has {len(document)} page(s)", field="page")
            limits.size(*(max(1, round(v * dpi / 72)) for v in document[page - 1].get_size()))
            image = document[page - 1].render(scale=dpi / 72).to_pil().convert("RGBA")
        finally:
            document.close()
        return image
    return decode(data, limits)


class _staged:
    """The document path itself when ``data`` came from it, else a temporary copy of ``data``."""

    def __init__(self, path, data):
        self.path, self.data, self.folder = Path(path), data, None

    def __enter__(self):
        if self.path.is_file() and self.path.stat().st_size == len(self.data) and self.path.read_bytes() == self.data:
            return self.path
        import tempfile

        self.folder = tempfile.TemporaryDirectory()
        staged = Path(self.folder.name) / "staged.vixl"
        staged.write_bytes(self.data)
        return staged

    def __exit__(self, *exc):
        if self.folder:
            self.folder.cleanup()


def diff_images(before, after, *, threshold=8, mode="diff"):
    """``(image, stats)`` for two RGBA images. Different sizes compare at ``before``'s size (``after`` is
    resized and ``resized`` is reported). ``mode`` diff paints changed pixels red over a dimmed ``after``;
    side-by-side shows before | after | diff."""
    from PIL import Image

    from .checks import diff_highlight, pixel_diff, side_by_side

    require(mode in ("diff", "side-by-side"), "mode must be diff or side-by-side", field="mode")
    require(isinstance(threshold, (int, float)) and 0 <= threshold < 255, "threshold must be 0-254", field="threshold")
    stats = {"before_size": list(before.size), "after_size": list(after.size)}
    if before.size != after.size:
        after = after.resize(before.size, Image.Resampling.LANCZOS)
        stats["resized"] = True
    mask, measured = pixel_diff(before, after, threshold)
    stats.update(measured, identical=measured["changed_pixels"] == 0, threshold=threshold)
    highlighted = diff_highlight(after, mask)
    image = highlighted if mode == "diff" else side_by_side(side_by_side(before, after), highlighted)
    return image, stats


def diff_files(before, after, output=None, *, threshold=8, mode="diff", overwrite=False, limits=None,
               before_data=None):
    """Compare two files and optionally write the diff PNG to ``output`` (never over an existing file unless
    ``overwrite``). Returns the stats with the paths."""
    limits = limits or Limits()
    if output is not None:
        destination = Path(output)
        require(destination.suffix.lower() == ".png", "The diff image must be a .png", field="output")
        require(overwrite or not destination.exists(), f"{output} already exists; pass overwrite", field="output")
    left = load_visual(before, limits, data=before_data)
    right = load_visual(after, limits)
    image, stats = diff_images(left, right, threshold=threshold, mode=mode)
    result = {"before": str(before), "after": str(after), **stats}
    if output is not None:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb" if overwrite else "xb") as stream:
            stream.write(buffer.getvalue())
        result["output"] = str(output)
    return result


def cli(args, limits):
    from .commands import Parser

    parser = Parser(prog="vixl diff", description="Pixel-diff two documents or images (.vixl, PNG, JPEG, WEBP, "
                    "TIFF, SVG, PDF): changed-pixel stats and an optional diff image")
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("--out", help="Write the diff image here (.png)")
    parser.add_argument("--mode", choices=["diff", "side-by-side"], default="diff")
    parser.add_argument("--threshold", type=float, default=8, help="Per-channel change that counts (0-254, default 8)")
    parser.add_argument("--max-fraction", type=float, help="Exit with an error when more than this fraction changed")
    parser.add_argument("--overwrite", action="store_true")
    a = parser.parse_args(args)
    result = diff_files(a.before, a.after, a.out, threshold=a.threshold, mode=a.mode, overwrite=a.overwrite,
                        limits=limits)
    if a.max_fraction is not None and result["changed_fraction"] > a.max_fraction:
        raise VixlError("diff_exceeded", f"{result['changed_fraction']:.2%} of pixels changed (limit "
                        f"{a.max_fraction:.2%})", report=result)
    return result
