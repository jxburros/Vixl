"""Render reproducibility (#512): reference-render verification, a render lockfile and drift checks.

Three levels are reported under ``reproduction`` (each implies the ones before it):

- ``renderable``: the document renders in this environment (all a bare ``vixl reproduce`` can say);
- ``environment-matched``: a lockfile was given and nothing it records has drifted (Vixl version and
  engine source, imaging/shaping/encoding packages, Python, fonts, embedded assets, linked sources, the
  document and its canvas settings, every page, artboard and sampled timeline frame, the variables and
  seeds, and the export settings and tools of each recorded export);
- ``reference-verified``: a fresh render matches an approved reference, either a reference image within
  a declared tolerance or the lockfile's exact render hash.

A mismatch is ``reference-mismatch`` (or ``export-mismatch`` when only a recorded export differs) and a lockfile
difference ``drifted``; all fail validation in ``outcome``. Lockfiles (version 2; version 1 still verifies) hold versions
and SHA-256 hashes, plus a coarse block-average signature of each recorded export's pixels: no layer contents, provider
settings or credentials, and a value from a credential environment variable is refused (``assert_no_secrets``). Remote AI
inference is not replayed; generated pixels are embedded assets, so they are frozen inputs like any other image.

Recorded exports (``exports=["png", "jpg:quality=80", "mp4"]``) are compared by ``export_lock``: bytes for formats
written deterministically, decoded pixels within a tolerance for lossy encoders, with ``byte_identical`` and
``visually_equivalent`` reported separately.
"""

import hashlib
import json
import os
import platform
import re
from pathlib import Path

from ...errors import VixlError, require
from ...hashing import content_hash
from ...model import is_int
from . import export_lock

LOCK_VERSION = 2
READABLE = (1, 2)
LEVELS = ("renderable", "environment-matched", "reference-verified")
ENVIRONMENT = ("vixl", "engine", "python", "dependencies", "toolchain")
MAX_TARGETS = 500
MAX_FRAMES = 32
DEFAULT_FRAMES = 3
MAX_SEEDS = 200
CREDENTIAL = re.compile(r"(^|_)(KEY|TOKEN|SECRET|PASSWORD|PASSWD|PASSPHRASE|CREDENTIALS?|APIKEY)(_|$)", re.IGNORECASE)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def render_hash(image):
    image = image.convert("RGBA")
    return _sha(f"{image.width}x{image.height}:".encode() + image.tobytes())


def _dependencies():
    from ...render_cache import PACKAGES, environment

    version, engine, versions = environment()
    return version, engine, {package: value for (package, _), value in zip(PACKAGES, versions)}


def _fonts(project):
    from ...text import font_data, font_digest

    fonts = {}
    for layer in project.state["layers"]:
        if layer["type"] == "text":
            try:
                fonts.setdefault(layer.get("font") or "default", font_digest(font_data(project, layer)))
            except Exception as exc:  # noqa: BLE001 - an unreadable font is itself drift worth reporting
                fonts.setdefault(layer.get("font") or "default", f"unreadable: {type(exc).__name__}")
    return dict(sorted(fonts.items()))


def _linked(project):
    from ...links import fingerprint
    from ...validation import dependencies

    files = {}
    for entry in dependencies(project)["linked"]:
        path = Path(entry["path"])
        files[entry["path"]] = _sha(path.read_bytes()) if path.is_file() else None
    return {"documents": [[source, revision] for source, revision in fingerprint(project)], "files": files}


# Secrets ----------------------------------------------------------------------------------------

def secret_values():
    """``{environment variable: value}`` for the credentials in this environment: variables named like a key, token,
    secret or password, and the key variables of the configured AI providers. Short values are skipped."""
    names = {name for name in os.environ if CREDENTIAL.search(name)}
    try:
        from ..ai import models

        names |= {item["key_env"] for item in {**models.BUILTIN, **models.configured()}.values()
                  if isinstance(item, dict) and item.get("key_env")}
    except (ImportError, VixlError, OSError, ValueError, TypeError):
        pass  # Without the provider plugin or its settings file only the name pattern applies.
    return {name: os.environ[name] for name in sorted(names) if len(os.environ.get(name, "")) >= 8}


def assert_no_secrets(value):
    """Refuse ``value`` (a lockfile or a report) when it contains a credential from the environment. The error names
    the variable, never the value."""
    text = json.dumps(value, default=str)
    leaked = [name for name, secret in secret_values().items() if secret in text]
    require(not leaked, f"Refusing to record a credential from {', '.join(leaked)}: a lockfile holds versions and hashes "
            "only", "forbidden", field="lock")


# Targets, variables and seeds -------------------------------------------------------------------

def frame_times(project, frames=None, times=None):
    """Timeline sample times (ms) to lock: ``times`` as given (milliseconds, ``'1.5s'``, ``'50%'`` or a marker), else
    ``frames`` spread over the duration. Without either, an animated document gets ``DEFAULT_FRAMES`` and any other
    document none."""
    from ...timeline import parse_time

    timeline = project.state.get("timeline") or {}
    animated = bool(timeline.get("tracks") or timeline.get("text_animations"))
    require(frames is None or (is_int(frames) and 0 <= frames <= MAX_FRAMES), f"frames is a whole number from 0 to "
            f"{MAX_FRAMES}", field="frames")
    duration = timeline.get("duration") or 3000
    if times is not None:
        require(isinstance(times, list) and len(times) <= MAX_FRAMES, f"times is a list of at most {MAX_FRAMES} times",
                field="times")
        return sorted({parse_time(value, duration, timeline.get("markers")) for value in times})
    if frames is None:
        frames = DEFAULT_FRAMES if animated else 0
    return sorted({round(duration * i / frames) for i in range(frames)}) if frames else []


def _target(kind, name, image, **extra):
    return {"kind": kind, "name": name, **extra, "sha256": render_hash(image), "size": list(image.size)}


def target_hashes(project, times):
    """The render hash of every page, every artboard and each sampled timeline frame."""
    from ...timeline import project_at

    pages = project.state.get("pages") or []
    boards = list(project.state.get("artboards") or {})
    require(len(pages) + len(boards) + len(times) <= MAX_TARGETS, f"A lockfile covers at most {MAX_TARGETS} pages, "
            "artboards and frames", "resource_limit", field="lock")
    found = []
    for number, page in enumerate(pages, 1):
        found.append(_target("page", f"page {number}", project.render(page=number), title=page.get("name")))
    for name in boards:
        found.append(_target("artboard", name, project.render(artboard=name)))
    for time in times:
        found.append(_target("frame", f"{time} ms", project_at(project, time).render(), time=time))
    return found


def _variables(project, variables):
    value = project.state.get("variables", {}) if variables is None else variables
    record = {"count": len(value), "sha256": content_hash(value, default=str)}
    if isinstance(value, dict):
        record["names"] = {str(name): content_hash(item, default=str)[:16] for name, item in sorted(value.items())}
    return record


def _seeds(state):
    found = {}

    def walk(value, path):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "seed" and is_int(item):
                    found["/".join(path) or "document"] = item
                else:
                    walk(item, [*path, str(key)])
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, [*path, str(item.get("name", index)) if isinstance(item, dict) else str(index)])

    walk({key: value for key, value in state.items() if key != "history"}, [])
    ordered = dict(sorted(found.items()))
    return {"count": len(ordered), "sha256": content_hash(ordered), "values": dict(list(ordered.items())[:MAX_SEEDS])}


def lock(project, image=None, *, frames=None, times=None, exports=None, variables=None, targets=True, resolve=Path,
         limits=None):
    """The lockfile for ``project`` as it renders now.

    ``targets`` adds the render hash of every page and artboard and of ``frames`` (or the ``times``) of an animated
    document; ``exports`` (``["png", "jpg:quality=80"]``) are encoded and recorded with their hashes and tools;
    ``variables`` replaces the document's variables as the row set to hash."""
    from ... import __version__
    from ...assurance import digest
    from ...production import stable_state

    version, engine, packages = _dependencies()
    canvas = project.state["canvas"]
    image = image if image is not None else project.render()
    value = {
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
        "variables": _variables(project, variables),
        "seeds": _seeds(project.state),
    }
    if targets:
        value["targets"] = target_hashes(project, frame_times(project, frames, times))
    if exports is not None:
        value["exports"], chain = export_lock.record_all(project, export_lock.parse_all(exports), resolve=resolve,
                                                         limits=limits)
        if chain:
            value["toolchain"] = chain
    assert_no_secrets(value)
    return value


def validate_lock(locked):
    require(isinstance(locked, dict) and locked.get("version") in READABLE, "Unsupported lockfile", field="lock",
            readable=list(READABLE))
    for item in locked.get("exports") or []:
        require(isinstance(item, dict) and item.get("format") in export_lock.FORMATS
                and isinstance(item.get("options"), dict), "The lockfile's exports are damaged", field="lock")
    return locked


# Drift ------------------------------------------------------------------------------------------

def _target_drift(old, new):
    before = {(item["kind"], item["name"]): item for item in old}
    after = {(item["kind"], item["name"]): item for item in new}
    found = []
    for key in [*before, *(key for key in after if key not in before)]:
        a, b = before.get(key, {}), after.get(key, {})
        if a.get("sha256") != b.get("sha256"):
            found.append({"kind": key[0], "name": key[1], "locked": a.get("sha256"), "current": b.get("sha256")})
    return found


def drift(locked, current):
    """Located differences between two lockfiles: ``[{kind, name, locked, current}]``. A version 1 lockfile is
    compared on what it records; a version 2 one also on its pages, artboards and frames (``page``, ``artboard`` and
    ``frame`` named like ``page 2``), ``variables``, ``seeds``, and, when ``current`` carries them, recorded exports
    (``export-setting`` and ``toolchain`` named ``FORMAT.OPTION``)."""
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
    if locked.get("version", 1) < 2:
        return found
    if "targets" in current:
        found += _target_drift(locked.get("targets") or [], current["targets"])
    old, new = locked.get("variables") or {}, current.get("variables") or {}
    if old.get("sha256") != new.get("sha256"):
        names = [name for name in sorted(set(old.get("names", {})) | set(new.get("names", {})))
                 if old.get("names", {}).get(name) != new.get("names", {}).get(name)]
        found += [{"kind": "variables", "name": name, "locked": old.get("names", {}).get(name),
                   "current": new.get("names", {}).get(name)} for name in names] or [
            {"kind": "variables", "name": "variables", "locked": old.get("sha256"), "current": new.get("sha256")}]
    old, new = locked.get("seeds") or {}, current.get("seeds") or {}
    if old.get("sha256") != new.get("sha256"):
        located = [{"kind": "seeds", "name": name, "locked": old.get("values", {}).get(name),
                    "current": new.get("values", {}).get(name)}
                   for name in sorted(set(old.get("values", {})) | set(new.get("values", {})))
                   if old.get("values", {}).get(name) != new.get("values", {}).get(name)]
        found += located or [{"kind": "seeds", "name": "seeds", "locked": old.get("sha256"),
                              "current": new.get("sha256")}]
    if "exports" in current:
        found += export_lock.drift(locked, current)
    return found


def verify_reference(image, reference, *, tolerance=0, max_fraction=0.0):
    """Compare a render with a reference image: a pixel counts as changed when a channel moves by more than
    ``tolerance``; it matches when at most ``max_fraction`` of the pixels changed."""
    from ...checks import pixel_diff

    report = {"tolerance": tolerance, "max_fraction": max_fraction, "size": list(image.size),
              "reference_size": list(reference.size)}
    if image.size != reference.size:
        return False, {**report, "reason": "the render and the reference differ in size"}
    _, stats = pixel_diff(reference, image, threshold=tolerance)
    fraction = stats["changed_pixels"] / max(1, image.width * image.height)  # unrounded, so 0 means none
    return fraction <= max_fraction, {**report, **stats}


def _all(values):
    values = list(values)
    return None if not values or any(v is None for v in values) else all(values)


def reproduce(project, *, reference=None, tolerance=0, max_fraction=0.0, locked=None, limits=None, exports=None,
              verify_exports=False, export_tolerance=None, export_visual=False, variables=None, resolve=Path,
              report=False):
    """Render once and report the reproduction level reached; see the module docstring.

    With a version 2 ``locked`` file, every locked page, artboard and frame is rendered again, and ``verify_exports``
    (or ``exports``, requests that replace the locked settings of the same format and are reported as
    ``export-setting`` drift where they differ) encodes each locked export again and compares it: ``exports`` in the
    result lists ``byte_identical`` and ``visually_equivalent`` per export. ``export_tolerance`` (0-254, default 8) is
    how far a block average of a lossy export may move; ``export_visual`` judges every format by its pixels.
    ``report=True`` returns the compact, manifest-ready summary instead of the full result."""
    from ...image_diff import load_visual
    from ...outcomes import make

    require(type(tolerance) is int and 0 <= tolerance <= 254, "tolerance is 0-254 (largest channel change)",
            field="tolerance")
    require(isinstance(max_fraction, (int, float)) and 0 <= max_fraction <= 1, "max_fraction is 0-1",
            field="max_fraction")
    export_tolerance = export_lock.DEFAULT_TOLERANCE if export_tolerance is None else export_tolerance
    require(is_int(export_tolerance) and 0 <= export_tolerance <= 254, "export_tolerance is 0-254", field="export_tolerance")
    wants_exports = bool(exports) or verify_exports
    require(not wants_exports or locked is not None, "Verifying exports needs a lockfile (lock); record them with "
            "write_lock and exports", field="exports")
    image = project.render()
    planned = None
    if locked is not None:
        validate_lock(locked)
        v2 = locked["version"] >= 2
        require(v2 or not wants_exports, "This lockfile is version 1 and records no exports; write a new one with "
                "write_lock and exports", field="lock")
        if wants_exports:
            planned = export_lock.plan(locked.get("exports") or [], export_lock.parse_all(exports) if exports else None)
            require(planned, "The lockfile records no exports; record them with write_lock and exports", field="exports")
        locked_times = [item["time"] for item in locked.get("targets", []) if item["kind"] == "frame"]
        current = lock(project, image, times=locked_times, variables=variables, targets=v2)
    else:
        current = lock(project, image, targets=False)
    result = {"reproduction": "renderable", "render": current["render"]}
    failures, verified_by, export_failures = [], [], []
    if locked is not None:
        if planned is not None:
            records, chain = export_lock.record_all(project, [entry for _, entry in planned], resolve=resolve,
                                                    limits=limits)
            current["exports"] = [{**record, "locked_index": index} for (index, _), record in zip(planned, records)]
            current["toolchain"] = chain
            verdicts = []
            for (index, _), record in zip(planned, records):
                if index is None:
                    verdicts.append({"format": record["format"], "options": record["options"], "passed": False,
                                     "byte_identical": None, "visually_equivalent": None, "compared": "none",
                                     "reason": "this export is not in the lockfile"})
                else:
                    verdicts.append(export_lock.compare(locked["exports"][index], record, tolerance=export_tolerance,
                                                        visual_only=export_visual))
            result["exports"] = verdicts
            result["byte_identical"] = _all(item["byte_identical"] for item in verdicts)
            result["visually_equivalent"] = _all(item["visually_equivalent"] for item in verdicts)
            for item, record in zip(verdicts, records):
                if item["passed"] or "reason" in item:  # An export that is not locked is reported as drift.
                    continue
                export_failures.append(f"export {export_lock.label(record)} " + (
                    "could not run" if "error" in record else f"differs in its {item['compared']}"))
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
        if planned is not None and not export_failures:
            verified_by.append("locked exports")
    if reference is not None:
        matched, comparison = verify_reference(image, load_visual(reference, limits), tolerance=tolerance,
                                               max_fraction=max_fraction)
        result["reference"] = {"path": str(reference), "matched": matched, **comparison}
        if matched:
            verified_by.append("reference image")
        else:
            failures.append("the render does not match the reference image")
    failures += export_failures
    if failures:
        result["reproduction"] = ("drifted" if locked is not None and result.get("drift") else
                                  "export-mismatch" if export_failures and len(failures) == len(export_failures)
                                  else "reference-mismatch")
    elif verified_by:
        result["reproduction"] = "reference-verified"
    note = ("Current rendering verified only; give a reference image or a lockfile to verify reproduction."
            if locked is None and reference is None else None)
    result["outcome"] = make("completed", "failed" if failures else "passed" if verified_by else "not_run",
                             failures or ([note] if note else []), validated_by=verified_by)
    result["reproducible"] = not failures
    if note:
        result["note"] = note
    return summary(result, locked, current) if report else result


def summary(result, locked=None, current=None):
    """The manifest-ready record of a reproduction check (``reproduce(..., report=True)``): the level, the lock it was
    checked against (version, SHA-256 and what it covers), counts and located items of drift, and each export's
    ``byte_identical`` and ``visually_equivalent``. It holds versions, hashes and outcomes only."""
    found = result.get("drift") or []
    record = {
        "format": "vixl-reproduction", "version": 1,
        "reproduction": result["reproduction"], "reproducible": result["reproducible"],
        "outcome": result["outcome"], "render": {"sha256": result["render"]["sha256"],
                                                 "matches_lock": result.get("render_matches_lock")},
        "lock": None if locked is None else {
            "version": locked.get("version"), "sha256": content_hash(locked), "vixl": locked.get("vixl"),
            "document": locked.get("document"), "targets": len(locked.get("targets") or []),
            "exports": len(locked.get("exports") or [])},
        "drift": {"environment": len(result.get("environment_drift") or []),
                  "input": len(result.get("input_drift") or []), "items": found[:20],
                  **({"omitted": len(found) - 20} if len(found) > 20 else {})},
    }
    if "exports" in result:
        record["byte_identical"] = result["byte_identical"]
        record["visually_equivalent"] = result["visually_equivalent"]
        record["exports"] = [{key: item.get(key) for key in ("format", "options", "passed", "byte_identical",
                                                              "visually_equivalent", "compared") if key in item}
                             for item in result["exports"]]
    if "reference" in result:
        record["reference"] = {key: result["reference"].get(key) for key in ("matched", "tolerance", "max_fraction")}
    assert_no_secrets(record)
    return record


def write_lock(project, path, *, overwrite=False, exports=None, frames=None, times=None, variables=None, resolve=Path,
               limits=None):
    """Write the lockfile for ``project``; ``exports`` (``["png", "jpg:quality=80"]``) are encoded and recorded."""
    from ...production import write_bytes

    path = Path(path)
    require(path.suffix.lower() == ".json", "The lockfile must be a .json file", field="write_lock")
    require(overwrite or not path.exists(), f"{path} already exists; pass overwrite", field="write_lock")
    value = lock(project, frames=frames, times=times, variables=variables, resolve=resolve, limits=limits,
                 exports=exports or None)
    write_bytes(path, json.dumps(value, indent=2, sort_keys=True).encode(), replace=overwrite)
    return value


def read_lock(path):
    from ...production import read_json

    return read_json(path)
