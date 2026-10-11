"""Render reproducibility (#512): reference-render verification, a render lockfile and drift checks.

Three levels are reported under ``reproduction`` (each implies the ones before it):

- ``renderable``: the document renders in this environment (all a bare ``vixl reproduce`` can say);
- ``environment-matched``: a lockfile was given and nothing it records has drifted (Vixl version and
  engine source, imaging/shaping/encoding packages, Python, fonts, embedded assets, linked sources, the
  document and its canvas settings);
- ``reference-verified``: a fresh render matches an approved reference, either a reference image within
  a declared tolerance or the lockfile's exact render hash.

A mismatch is ``reference-mismatch`` and a lockfile difference ``drifted``; both fail validation in
``outcome``. Lockfiles hold versions and SHA-256 hashes only: no layer contents, provider settings or
credentials. Remote AI inference is not replayed; generated pixels are embedded assets, so they are
frozen inputs like any other image.
"""

import hashlib
import json
import platform
from pathlib import Path

from .errors import require

LOCK_VERSION = 1
LEVELS = ("renderable", "environment-matched", "reference-verified")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def render_hash(image):
    image = image.convert("RGBA")
    return _sha(f"{image.width}x{image.height}:".encode() + image.tobytes())


def _dependencies():
    from .render_cache import PACKAGES, environment

    version, engine, versions = environment()
    return version, engine, {package: value for (package, _), value in zip(PACKAGES, versions)}


def _fonts(project):
    from .text import font_data, font_digest

    fonts = {}
    for layer in project.state["layers"]:
        if layer["type"] == "text":
            try:
                fonts.setdefault(layer.get("font") or "default", font_digest(font_data(project, layer)))
            except Exception as exc:  # noqa: BLE001 - an unreadable font is itself drift worth reporting
                fonts.setdefault(layer.get("font") or "default", f"unreadable: {type(exc).__name__}")
    return dict(sorted(fonts.items()))


def _linked(project):
    from .links import fingerprint
    from .validation import dependencies

    files = {}
    for entry in dependencies(project)["linked"]:
        path = Path(entry["path"])
        files[entry["path"]] = _sha(path.read_bytes()) if path.is_file() else None
    return {"documents": [[source, revision] for source, revision in fingerprint(project)], "files": files}


def lock(project, image=None):
    """The lockfile for ``project`` as it renders now."""
    from . import __version__
    from .assurance import digest
    from .production import stable_state

    version, engine, packages = _dependencies()
    canvas = project.state["canvas"]
    image = image if image is not None else project.render()
    return {
        "version": LOCK_VERSION,
        "vixl": __version__,
        "engine": engine,
        "python": platform.python_version(),
        "dependencies": packages,
        "fonts": _fonts(project),
        "assets": {name: _sha(data) for name, data in sorted(project.assets.items())},
        "linked": _linked(project),
        "document": digest(stable_state(project.state)),
        "settings": {key: canvas.get(key) for key in ("width", "height", "dpi", "background", "bleed", "size",
                                                       "color_profile") if canvas.get(key) is not None},
        "render": {"sha256": render_hash(image), "size": list(image.size)},
    }


ENVIRONMENT = ("vixl", "engine", "python", "dependencies")


def drift(locked, current):
    """Located differences between two lockfiles: ``[{kind, name, locked, current}]``."""
    found = []
    for kind in ("vixl", "engine", "python", "document"):
        if locked.get(kind) != current.get(kind):
            found.append({"kind": kind, "name": kind, "locked": locked.get(kind), "current": current.get(kind)})
    for kind in ("dependencies", "fonts", "assets", "settings"):
        old, new = locked.get(kind, {}), current.get(kind, {})
        for name in sorted(set(old) | set(new)):
            if old.get(name) != new.get(name):
                found.append({"kind": kind, "name": name, "locked": old.get(name), "current": new.get(name)})
    old, new = locked.get("linked", {}), current.get("linked", {})
    for name in sorted(set(old.get("files", {})) | set(new.get("files", {}))):
        if old.get("files", {}).get(name) != new.get("files", {}).get(name):
            found.append({"kind": "linked", "name": name, "locked": old.get("files", {}).get(name),
                          "current": new.get("files", {}).get(name)})
    if old.get("documents") != new.get("documents"):
        found.append({"kind": "linked", "name": "linked documents", "locked": old.get("documents"),
                      "current": new.get("documents")})
    return found


def verify_reference(image, reference, *, tolerance=0, max_fraction=0.0):
    """Compare a render with a reference image: a pixel counts as changed when a channel moves by more than
    ``tolerance``; it matches when at most ``max_fraction`` of the pixels changed."""
    from .checks import pixel_diff

    report = {"tolerance": tolerance, "max_fraction": max_fraction, "size": list(image.size),
              "reference_size": list(reference.size)}
    if image.size != reference.size:
        return False, {**report, "reason": "the render and the reference differ in size"}
    _, stats = pixel_diff(reference, image, threshold=tolerance)
    fraction = stats["changed_pixels"] / max(1, image.width * image.height)  # unrounded, so 0 means none
    return fraction <= max_fraction, {**report, **stats}


def reproduce(project, *, reference=None, tolerance=0, max_fraction=0.0, locked=None, limits=None):
    """Render once and report the reproduction level reached; see the module docstring."""
    from .image_diff import load_visual
    from .outcomes import make

    require(type(tolerance) is int and 0 <= tolerance <= 254, "tolerance is 0-254 (largest channel change)",
            field="tolerance")
    require(isinstance(max_fraction, (int, float)) and 0 <= max_fraction <= 1, "max_fraction is 0-1",
            field="max_fraction")
    image = project.render()
    current = lock(project, image)
    result = {"reproduction": "renderable", "render": current["render"]}
    failures, verified_by = [], []
    if locked is not None:
        require(isinstance(locked, dict) and locked.get("version") == LOCK_VERSION, "Unsupported lockfile",
                field="lock")
        found = drift(locked, current)
        result["drift"] = found
        result["environment_drift"] = [item for item in found if item["kind"] in ENVIRONMENT]
        result["input_drift"] = [item for item in found if item["kind"] not in ENVIRONMENT]
        if found:
            failures.append(f"{len(found)} locked item(s) drifted")
        else:
            result["reproduction"] = "environment-matched"
        exact = locked.get("render", {}).get("sha256") == current["render"]["sha256"]
        result["render_matches_lock"] = exact
        if exact:
            verified_by.append("lockfile render hash")
        else:
            failures.append("the render differs from the locked render")
    if reference is not None:
        matched, comparison = verify_reference(image, load_visual(reference, limits), tolerance=tolerance,
                                               max_fraction=max_fraction)
        result["reference"] = {"path": str(reference), "matched": matched, **comparison}
        if matched:
            verified_by.append("reference image")
        else:
            failures.append("the render does not match the reference image")
    if failures:
        result["reproduction"] = "drifted" if locked is not None and result.get("drift") else "reference-mismatch"
    elif verified_by:
        result["reproduction"] = "reference-verified"
    note = ("Current rendering verified only; give a reference image or a lockfile to verify reproduction."
            if locked is None and reference is None else None)
    result["outcome"] = make("completed", "failed" if failures else "passed" if verified_by else "not_run",
                             failures or ([note] if note else []), validated_by=verified_by)
    result["reproducible"] = not failures
    if note:
        result["note"] = note
    return result


def write_lock(project, path, *, overwrite=False):
    path = Path(path)
    require(path.suffix.lower() == ".json", "The lockfile must be a .json file", field="write_lock")
    require(overwrite or not path.exists(), f"{path} already exists; pass overwrite", field="write_lock")
    value = lock(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w" if overwrite else "x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
    return value


def read_lock(path):
    from .production import read_json

    return read_json(path)
