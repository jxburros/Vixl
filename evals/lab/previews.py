"""Turn the files a session left behind into images: for the model (``view_image``, ``render_page``), for the page
and for the judge.

HTML and SVG are rendered with Playwright's Chromium when it is installed (``pip install playwright`` and
``playwright install chromium``; ``--chromium PATH`` or ``VIXL_LAB_CHROMIUM`` points at another Chromium). PDFs use
pypdfium2, PowerPoint files go through LibreOffice when it is on the PATH, and a ``.vixl`` document is rendered by
Vixl only when the session exported nothing else.
"""

import base64
from functools import lru_cache
import io
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading

from PIL import Image

RASTER = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
PAGES = {".html", ".htm"}
KINDS = {**{ext: "image" for ext in RASTER}, ".svg": "svg", ".html": "html", ".htm": "html", ".pdf": "pdf",
         ".pptx": "pptx", ".docx": "docx", ".xlsx": "xlsx", ".vixl": "vixl", ".mp4": "video", ".webm": "video",
         ".md": "text", ".txt": "text", ".csv": "text", ".json": "text", ".css": "text", ".py": "text"}
MODEL_SIDE = 1024  # longest side of an image sent to the model
PREVIEW_SIDE = 1568  # longest side of the stored preview (and of what the judge sees)
MAX_VIEWPORT = 4000
_BROWSER_SLOTS = threading.Semaphore(2)


def chromium_path():
    return os.environ.get("VIXL_LAB_CHROMIUM") or None


@lru_cache(maxsize=1)
def playwright_available():
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False
    return True


def kind(path):
    return KINDS.get(Path(path).suffix.lower(), "other")


def hidden(relative):
    return any(part.startswith(".") or part == "__pycache__" for part in Path(relative).parts)


def deliverables(workspace):
    """Every file the session left in its workspace (hidden files and caches left out), newest first."""
    workspace = Path(workspace)
    found = []
    for path in workspace.rglob("*"):
        relative = path.relative_to(workspace)
        if path.is_file() and not path.is_symlink() and not hidden(relative):
            stat = path.stat()
            found.append({"path": relative.as_posix(), "size": stat.st_size, "kind": kind(path),
                          "mtime": stat.st_mtime})
    return sorted(found, key=lambda item: -item["mtime"])


def fit(image, side):
    image = image.convert("RGBA") if image.mode in ("P", "LA", "PA") else image
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")
    if max(image.size) > side:
        image = image.copy()
        image.thumbnail((side, side), Image.Resampling.LANCZOS)
    return image


def png_bytes(image, side):
    buffer = io.BytesIO()
    fit(image, side).save(buffer, format="PNG")
    return buffer.getvalue()


def image_block(png):
    return {"type": "image", "media_type": "image/png", "data": base64.b64encode(png).decode("ascii")}


def screenshot(source, width=None, height=None, full_page=True):
    """PNG bytes of an HTML or SVG file (``source`` is a Path) rendered in Chromium."""
    from playwright.sync_api import sync_playwright

    source = Path(source).resolve()
    with _BROWSER_SLOTS, sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=chromium_path())
        try:
            page = browser.new_page(viewport={"width": int(width or 1280), "height": int(height or 800)})
            page.goto(source.as_uri(), wait_until="load", timeout=30000)
            if source.suffix.lower() == ".svg" and not width:
                box = page.evaluate("() => { const r = document.documentElement.getBoundingClientRect();"
                                    " return [Math.ceil(r.width), Math.ceil(r.height)]; }")
                w, h = (max(1, min(int(v), MAX_VIEWPORT)) for v in box)
                page.set_viewport_size({"width": w, "height": h})
                full_page = False
            page.wait_for_timeout(300)
            return page.screenshot(full_page=full_page and not height, type="png")
        finally:
            browser.close()


def pdf_page(path, page=0):
    import pypdfium2

    document = pypdfium2.PdfDocument(str(path))
    try:
        index = max(0, min(int(page), len(document) - 1))
        return document[index].render(scale=2).to_pil()
    finally:
        document.close()


def office_to_pdf(path, folder):
    office = shutil.which("soffice") or shutil.which("libreoffice")
    if office is None:
        return None
    subprocess.run([office, "--headless", "--convert-to", "pdf", "--outdir", str(folder), str(path)],
                   capture_output=True, timeout=120)
    result = Path(folder) / (Path(path).stem + ".pdf")
    return result if result.is_file() else None


class PreviewError(RuntimeError):
    pass


def load_image(path, page=0):
    """A PIL image of any previewable file."""
    path = Path(path)
    file_kind = kind(path)
    if file_kind == "image":
        with Image.open(path) as image:
            image.seek(0)
            return image.copy()
    if file_kind in ("svg", "html"):
        if not playwright_available():
            raise PreviewError("rendering HTML and SVG needs Playwright (pip install playwright; "
                               "playwright install chromium)")
        return Image.open(io.BytesIO(screenshot(path)))
    if file_kind == "pdf":
        return pdf_page(path, page)
    if file_kind in ("pptx", "docx", "xlsx"):
        with tempfile.TemporaryDirectory(prefix="vixl-lab-office-") as folder:
            pdf = office_to_pdf(path, folder)
            if pdf is None:
                raise PreviewError(f"previewing {path.suffix} files needs LibreOffice on the PATH")
            return pdf_page(pdf, page)
    if file_kind == "vixl":
        from vixl import Project

        return Project.load(path).render()
    raise PreviewError(f"cannot show a {path.suffix or 'file without an extension'} as an image")


ORDER = ["image", "svg", "pdf", "html", "pptx", "docx", "xlsx", "vixl"]


def make_preview(workspace, out, prefer=()):
    """Write the main deliverable in ``workspace`` as ``out`` (PNG); return (source path, note) or (None, reason).
    Files in ``prefer`` (the ones a round changed) come first, then by kind, then the newest."""
    files = [item for item in deliverables(workspace) if item["kind"] in ORDER]
    files.sort(key=lambda item: (item["path"] not in prefer, ORDER.index(item["kind"])))
    reasons = []
    for item in files:
        try:
            image = load_image(Path(workspace) / item["path"])
        except Exception as exc:  # noqa: BLE001 - try the next file; report why none worked
            reasons.append(f"{item['path']}: {exc}")
            continue
        Path(out).write_bytes(png_bytes(image, PREVIEW_SIDE))
        note = "only the editable .vixl document was left; nothing was exported" if item["kind"] == "vixl" else ""
        return item["path"], note
    return None, "; ".join(reasons) or "no previewable file was left in the workspace"
