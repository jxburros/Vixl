"""Recipe production, resumable variant matrices and portable component libraries."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import hashlib
import io
import itertools
import json
import os
from pathlib import Path

from PIL import Image, ImageDraw

from .assets import read_bounded
from .assurance import digest
from .automation import validate_inputs
from .errors import VixlError, require
from .fileio import file_lock, temporary


def write_bytes(path, data, *, replace=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = temporary(path.parent, like=path if path.exists() else None)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temp, path)
        else:
            os.link(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def write_json(path, value):
    write_bytes(path, json.dumps(value, indent=2, allow_nan=False).encode(), replace=True)


def file_digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def publish_file(path, source, *, replace=False):
    """Publish a large staged movie/archive without loading it into memory."""
    import shutil

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = temporary(path.parent, like=path if path.exists() else None)
    try:
        with os.fdopen(fd, "wb") as target, Path(source).open("rb") as original:
            shutil.copyfileobj(original, target, 1024 * 1024)
            target.flush()
            os.fsync(target.fileno())
        if replace:
            os.replace(temp, path)
        else:
            os.link(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def read_json(path):
    try:
        return json.loads(read_bounded(path, 8 * 1024 * 1024))
    except (ValueError, OSError) as exc:
        raise VixlError("invalid_manifest", "Cannot read production JSON") from exc


def plan(spec):
    from .automation import bounded_object

    bounded_object(
        spec,
        {
            "version",
            "rows",
            "matrix",
            "artboards",
            "format",
            "kind",
            "quality",
            "suites",
            "repair_actions",
            "workers",
            "actions",
            "motion",
            "fps",
            "profile",
        },
        "Unknown production field",
    )
    require(isinstance(spec.get("profile", ""), str), "profile is a check profile name", field="profile")
    require(spec.get("version", 1) == 1, "Unsupported production version")
    rows, matrix = spec.get("rows", [{}]), spec.get("matrix", {})
    require(
        isinstance(rows, list) and 0 < len(rows) <= 10000 and all(isinstance(r, dict) for r in rows),
        "Production needs 1–10000 input rows",
    )
    require(isinstance(matrix, dict) and len(matrix) <= 10, "Invalid variation matrix")
    require(
        all(isinstance(v, list) and 0 < len(v) <= 100 for v in matrix.values()), "Invalid variation choices"
    )
    boards = spec.get("artboards", [None])
    require(isinstance(boards, list) and 0 < len(boards) <= 100, "Invalid artboards")
    count = len(rows) * len(boards)
    for values in matrix.values():
        count *= len(values)
    require(count <= 10000, "Production exceeds 10000 outputs", "resource_limit")
    require(spec.get("quality", "final") in ("draft", "final"), "Quality must be draft or final")
    kind = spec.get("kind", "image")
    fmt = spec.get("format", "png" if kind == "image" else "webp").lower()
    require(kind in ("image", "timeline"), "Invalid output kind")
    require(
        fmt in ({"png", "jpg", "webp", "svg"} if kind == "image" else {"gif", "webp", "mp4", "webm", "zip"}),
        "Invalid production format",
    )
    require(spec.get("quality", "final") != "draft" or fmt != "svg", "Draft previews are raster images")
    workers = spec.get("workers", 1)
    require(type(workers) is int and 1 <= workers <= 4, "Workers must be 1–4")
    for field in ("actions", "repair_actions", "suites"):
        values = spec.get(field, [])
        require(
            isinstance(values, list)
            and len(values) <= (3 if field == "repair_actions" else 100)
            and all(isinstance(v, str) for v in values),
            f"Invalid {field}",
        )
    variants = []
    for number, row in enumerate(rows, 1):
        require(not set(row) & set(matrix), "A field cannot occur in both a row and the matrix")
        for combination in itertools.product(*matrix.values()):
            for board in boards:
                variants.append(
                    {
                        "id": f"{len(variants) + 1:04d}",
                        "row": number,
                        "values": {**row, **dict(zip(matrix, combination))},
                        "artboard": board,
                    }
                )
    return {
        "version": 1,
        "count": count,
        "kind": kind,
        "format": fmt,
        "quality": spec.get("quality", "final"),
        "variants": variants,
    }


def instantiate(project, values):
    candidate = project.clone()
    from .render import LayerCache

    candidate._cache, candidate._decoded = LayerCache(), {}
    recipe = candidate.state.get("recipe")
    if recipe:
        explicit = set(values)
        values = validate_inputs(recipe.get("inputs", {}), values)
        for name, value in values.items():
            if recipe["inputs"][name].get("type") == "asset":
                require(value in candidate.assets, f"Input {name} must reference an embedded asset")
        # Row values win; an input's default only fills a variable that the document or the
        # artboard (already applied to ``project``) has not set, so board variables are kept.
        values = {
            name: value
            for name, value in values.items()
            if name in explicit or name not in candidate.state["variables"]
        }
    candidate.state["variables"].update(deepcopy(values))
    for action in recipe.get("actions", []) if recipe else []:
        candidate.apply({"type": "action-apply", "name": action}, detail="compact")
    return candidate


def capture_recipe(project, recipe, bindings):
    """Return a portable document template; explicit bindings preserve all embedded assets."""
    from .automation import validate_recipe
    from .validation import check_state

    validate_recipe(recipe)
    defaults = validate_inputs(recipe.get("inputs", {}), {})
    candidate = project.clone()
    for name, binding in bindings.items():
        require(name in recipe["inputs"], f"Unknown input: {name}")
        require(isinstance(binding, dict) and set(binding) == {"target", "field"}, "Invalid binding")
        layer = candidate.layer(binding["target"])
        field = binding["field"]
        require(
            field in {"text", "color", "fill", "start", "end"} and field in layer,
            "Bindings support existing text and color fields; image slots use replace-contents --variable",
        )
        layer[field] = "${" + name + "}"
    candidate.state["variables"].update(defaults)
    candidate.state["recipe"] = deepcopy(recipe)
    check_state(candidate, candidate.state)
    candidate._record([], "Capture recipe")
    for example in recipe.get("examples", []):
        sample = instantiate(candidate, example)
        for suite in sample.state.get("suites", {}):
            report = sample.check_suite(suite)
            require(report["passed"], f"Recipe example failed suite {suite}", "check_failed", report=report)
    return candidate


def render_variant(project, spec, variant, directory, prior=None, cancelled=lambda: False):
    from .assurance import effective
    from .render_cache import enable, environment, user_cache_dir
    from .design_render import artboard_project
    from .timeline import export_timeline

    base = artboard_project(project.clone(), variant["artboard"], None, None)
    candidate = instantiate(base, variant["values"])
    enable(candidate, user_cache_dir())
    for action in spec.get("actions", []):
        candidate.apply({"type": "action-apply", "name": action}, detail="compact")
    if spec.get("motion"):
        candidate.apply({"type": "motion-apply", "name": spec["motion"]}, detail="compact")
    if "fps" in spec:
        candidate.apply({"type": "timeline-set", "fps": spec["fps"]}, detail="compact")
    from .links import fingerprint as link_fingerprint
    from .text import font_data, font_digest

    request_fingerprint = digest([
        stable_state(candidate.state), environment(), spec,
        [font_digest(font_data(candidate, layer)) for layer in candidate.state["layers"] if layer["type"] == "text"],
        link_fingerprint(candidate),
    ])
    # Reuse only a previously approved, byte-verified output with identical inputs,
    # contracts, repair policy, fonts, links and renderer environment.
    if prior and prior.get("request_fingerprint") == request_fingerprint and prior.get("status") in ("completed", "reused"):
        name = prior.get("output", "")
        if name and Path(name).name == name:
            output = directory / name
            if output.is_file() and file_digest(output) == prior.get("sha256"):
                return {**prior, "status": "reused", "outcome": prior.get("outcome") or variant_outcome(
                    prior.get("checks", {}), spec.get("suites", [] if spec.get("profile") else list(
                        effective(candidate))), "completed", spec.get("profile"))}
    leftovers = placeholder_report(candidate, variant)
    if not leftovers["passed"]:
        # An undefined variable or leftover template copy in this row: report it naming the variant, before rendering.
        return {**variant, "status": "needs_review", "checks": {"placeholders": leftovers}, "repairs": [],
                "outcome": leftovers["outcome"]}
    profile = spec.get("profile")
    # A profile chooses the design checks and its own suites unless the spec names suites; without one every
    # attached and inherited suite runs.
    suites = spec.get("suites", [] if profile else list(effective(candidate)))

    def evaluate():
        checks = {name: candidate.check_suite(name) for name in suites}
        if profile:
            checks["design"] = candidate.check(profile=profile)
        elif not suites:
            checks["design"] = candidate.check(checks=["bounds", "flow"])
        return checks

    from .repair import campaign

    # Named document actions and ``auto`` (the built-in repair map) share one repair loop.
    repairs, checks, repair_details = campaign(candidate, spec.get("repair_actions", []), evaluate)
    extra = {"repair_operations": [op for report in repair_details for op in report["operations"]]} if repair_details else {}
    if not all(r["passed"] for r in checks.values()):
        return {**variant, "status": "needs_review", "checks": checks, "repairs": repairs, **extra,
                "outcome": variant_outcome(checks, suites, "completed", profile)}
    settings = plan({k: v for k, v in spec.items() if k not in ("rows", "matrix", "artboards")})
    from .links import fingerprint as link_fingerprint
    from .text import font_data, font_digest

    fonts = [
        font_digest(font_data(candidate, layer))
        for layer in candidate.state["layers"]
        if layer["type"] == "text"
    ]
    fingerprint = digest(
        [
            stable_state(candidate.state),
            environment(),
            settings["kind"],
            settings["format"],
            settings["quality"],
            spec.get("fps"),
            fonts,
            link_fingerprint(candidate),
        ]
    )
    filename = variant["id"] + "-" + fingerprint[:16] + "." + settings["format"]
    output = directory / filename
    if prior and prior.get("fingerprint") == fingerprint and output.is_file():
        if file_digest(output) == prior.get("sha256"):
            return {**prior, "status": "reused", "checks": checks, "outcome": variant_outcome(checks, suites, "completed", profile)}
    # Crash recovery can encounter an already published output before its report was saved.
    # Render again to staging and only accept an existing result with identical bytes.
    import tempfile

    with tempfile.TemporaryDirectory(dir=directory, prefix=".stage-") as temp:
        staged = Path(temp) / filename
        if settings["kind"] == "timeline":
            export_timeline(
                candidate,
                staged,
                fps=spec.get("fps", 12 if settings["quality"] == "draft" else None),
                scale=0.5 if settings["quality"] == "draft" else 1,
                preview=settings["quality"] == "draft",
                cancelled=cancelled,
            )
        elif settings["quality"] == "draft":
            from .proxy import render_preview

            image = render_preview(candidate, 640, 640)
            if settings["format"] == "jpg":
                image = image.convert("RGB")
            image.save(staged)
        else:
            candidate.export(staged)
        checksum = file_digest(staged)
        require(not cancelled(), "Production cancelled", "cancelled")
        if output.exists():
            require(
                file_digest(output) == checksum,
                "Existing output differs; choose a new output directory",
                "output_collision",
            )
        else:
            publish_file(output, staged)
    return {
        **variant,
        "status": "completed",
        "output": filename,
        "fingerprint": fingerprint,
        "request_fingerprint": request_fingerprint,
        "sha256": checksum,
        "checks": checks,
        "repairs": repairs,
        **extra,
        "outcome": variant_outcome(checks, suites, "completed", profile),
        "cache": ({"hits": candidate._disk_cache.hits, "misses": candidate._disk_cache.misses}
                  if candidate._disk_cache is not None else {"hits": 0, "misses": 0, "disabled": True}),
    }


def variant_outcome(checks, suites, execution, profile=None):
    """One output's outcome. Its suites are the required validation, and with a check ``profile`` so is the
    profile's design check (its outcome follows the profile's fail_on); with neither only the default
    bounds and flow checks ran, so a clean output is completed but unvalidated (a failure still fails it)."""
    from .outcomes import from_findings, from_suite, make, merge

    parts = [from_suite(checks[name], name) for name in suites if name in checks]
    if profile and checks.get("design", {}).get("outcome"):
        parts.append(checks["design"]["outcome"])
    if parts:
        return merge(*parts, execution=execution)
    design = checks.get("design")
    if design and not design.get("passed", True):
        return from_findings(design.get("issues", []), execution)
    return make(execution, "not_run", ["no suites: only the default bounds and flow checks ran"])


def placeholder_report(candidate, variant):
    """The placeholders check for one production variant, each finding naming the variant and its input row."""
    label = f"variant {variant['id']} (row {variant.get('row', '?')}" + (
        f", artboard {variant['artboard']})" if variant.get("artboard") else ")")
    report = candidate.check(checks=["placeholders"])
    for item in report["issues"]:
        item.update(variant=variant["id"], row=variant.get("row"))
        item["message"] = f"{label}: {item['message']}"
    return report


def stable_state(state):
    """Normalize fresh object IDs for recipe fingerprints, preserving their references."""
    identifiers = {}

    def collect(value):
        if isinstance(value, dict):
            if isinstance(value.get("id"), str):
                identifiers.setdefault(value["id"], f"object-{len(identifiers)}")
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    def replace(value):
        if isinstance(value, dict):
            return {identifiers.get(k, k): replace(v) for k, v in value.items()}
        if isinstance(value, list):
            return [replace(v) for v in value]
        if isinstance(value, str):
            if value.startswith("effect:") and value[7:] in identifiers:
                return "effect:" + identifiers[value[7:]]
            return identifiers.get(value, value)
        return value

    collect(state)
    return replace(state)


def run(project, spec, directory, *, cancelled=lambda: False, progress=lambda value: None):
    planned = plan(spec)
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    with file_lock(str(directory / "production"), timeout=1):
        manifest = directory / "production.json"
        previous = read_json(manifest) if manifest.exists() else {"version": 1, "results": []}
        require(previous.get("version") == 1, "Unsupported manifest version")
        prior = {r["id"]: r for r in previous["results"]}
        report = {
            "version": 1,
            "quality": planned["quality"],
            **({"profile": spec["profile"]} if spec.get("profile") else {}),
            "count": planned["count"],
            "status": "running",
            "results": [],
        }
        write_json(manifest, report)

        def one(variant):
            from .outcomes import make

            if cancelled():
                return {**variant, "status": "cancelled", "outcome": make("cancelled")}
            try:
                return render_variant(project, spec, variant, directory, prior.get(variant["id"]), cancelled)
            except Exception as exc:
                error = (
                    exc.as_dict()
                    if isinstance(exc, VixlError)
                    else {"error": type(exc).__name__, "message": str(exc)[:500]}
                )
                return {**variant, "status": "failed", "error": error, "outcome": make("failed")}

        with ThreadPoolExecutor(max_workers=spec.get("workers", 1)) as executor:
            pending = {executor.submit(one, v) for v in planned["variants"]}
            for future in as_completed(pending):
                report["results"].append(future.result())
                report["results"].sort(key=lambda r: r["id"])
                write_json(manifest, report)
                progress({"done": len(report["results"]), "total": planned["count"]})
        report["status"] = (
            "cancelled"
            if cancelled()
            else "completed"
            if all(r["status"] in ("completed", "reused") for r in report["results"])
            else "needs_review"
        )
        from .outcomes import summarize

        report["outcome"] = summarize(r.get("outcome") or {"state": "pending"} for r in report["results"])
        contact_sheet(directory, report)
        write_json(manifest, report)
        return report


def contact_sheet(directory, report):
    results = [
        r for r in report["results"] if r.get("output", "").endswith((".png", ".jpg", ".webp", ".gif"))
    ][:100]
    if not results:
        return
    sheet = Image.new("RGB", (800, ((len(results) + 3) // 4) * 180), "#eeeeee")
    draw = ImageDraw.Draw(sheet)
    for i, result in enumerate(results):
        with Image.open(directory / result["output"]) as image:
            image.thumbnail((190, 145))
            x, y = (i % 4) * 200, (i // 4) * 180
            sheet.paste(image.convert("RGB"), (x + 5, y + 5))
            draw.text((x + 5, y + 153), result["id"] + " " + result["status"], fill="black")
    buffer = io.BytesIO()
    sheet.save(buffer, format="PNG")
    write_bytes(directory / "contact-sheet.png", buffer.getvalue(), replace=True)
    report["contact_sheet"] = "contact-sheet.png"


class Library:
    """Immutable versioned .vixl components; metadata never contains provider credentials."""

    def __init__(self, directory):
        self.directory = Path(directory).resolve()

    def save(self, project, name, description="", tags=None):
        from .design import named

        named(name)
        require(len(name) <= 80, "Library names are limited to 80 characters")
        tags = tags or []
        require(isinstance(description, str) and len(description) <= 10000, "Description too long")
        require(
            isinstance(tags, list)
            and len(tags) <= 50
            and all(isinstance(t, str) and len(t) <= 100 for t in tags),
            "Invalid library tags",
        )
        self.directory.mkdir(parents=True, exist_ok=True)
        with file_lock(str(self.directory / "library")):
            ident = name + "-" + digest(project.state)[:16]
            path = self.directory / (ident + ".vixl")
            if not path.exists():
                copy = project.clone()
                copy.path, copy._revision = None, None
                copy.save(path)
            item = {
                "version": 1,
                "id": ident,
                "name": name,
                "description": description,
                "tags": tags,
                "project": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            write_json(self.directory / (ident + ".json"), item)
            return item

    def search(self, query=""):
        terms = query.casefold().split()
        items = [read_json(p) for p in sorted(self.directory.glob("*.json"))]
        return [
            i
            for i in items
            if all(
                t in json.dumps([i.get("name"), i.get("description"), i.get("tags")]).casefold()
                for t in terms
            )
        ]

    def load(self, ident, *, limits=None):
        from .design import named
        from .project import Project

        named(ident)
        path = self.directory / (ident + ".vixl")
        metadata = read_json(self.directory / (ident + ".json"))
        data = read_bounded(path, (limits.max_project_bytes if limits else 256 * 1024 * 1024))
        require(hashlib.sha256(data).hexdigest() == metadata["sha256"], "Library component checksum mismatch")
        return Project.load(path, limits=limits)

    def place(self, project, ident, name, as_="group"):
        """Place a component as an editable group of its layers (new IDs, with its fonts and assets), or with
        ``as_='image'`` as one raster snapshot."""
        from .assets import add_image

        require(as_ in ("group", "image"), "as is group (editable layers, the default) or image", field="as")
        component = self.load(ident, limits=project.limits)
        candidate = project.clone()
        if as_ == "image":
            asset = add_image(candidate, component.render())
            result = candidate.apply({"type": "add", "name": name, "asset": asset}, detail="compact")
            project.__dict__.update(candidate.__dict__)
            return {**result, "source_component": ident, "asset": asset, "as": "image"}
        from .objects import from_document, place, subtree
        from .validation import check_state

        root = place(candidate, {"name": name, "name_as": name}, from_document(component, ident))
        check_state(candidate, candidate.state)
        if candidate.transaction is None:
            candidate._record([], f"Place component {ident}")
        result = {"success": True, "layer": {"id": root["id"], "name": root["name"], "type": "group"},
                  "layers": len(subtree(candidate, root["id"]))}
        project.__dict__.update(candidate.__dict__)
        return {**result, "source_component": ident, "as": "group"}


