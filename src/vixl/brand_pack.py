"""Brand packages: ``vixl brand init``, ``pack``, ``install`` and ``element``.

A brand package (``.vixlbrand``) is one deterministic ZIP: ``brand.json``, the workspace resource library
(``resources/<kind>.json``: palettes, templates, workflows, suites, guidance, assets and the other kinds, without
those that belong to an installed plugin pack), the asset files (``assets/<sha256>.<ext>``) and ``manifest.json``,
which lists every other member with its SHA-256. It holds data only.

Installing reads the archive within fixed bounds, checks every member against the manifest, validates the brand
and every resource as saving them would (fonts, logos and element files decode; assets pass the pack-asset
checks), and only then writes. The three destinations (the asset folder, the resource library and brand.json) are
written through temporary files renamed into place, and a failure restores what was there before. Nothing in a
package is executed.
"""

from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import zipfile

from .errors import VixlError, require

FORMAT, VERSION = "vixl-brand-pack", 1
SUFFIX = ".vixlbrand"
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_EXPANDED_BYTES = 96 * 1024 * 1024
MAX_MEMBERS = 2000
MAX_JSON_BYTES = 16 * 1024 * 1024
ASSET_MEMBER = re.compile(r"assets/[0-9a-f]{64}\.(png|jpg|svg|webp)")


def _canonical(value):
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _library(workspace):
    from .assets import read_bounded
    from .resources import resource_path

    path = resource_path(workspace)
    data = json.loads(read_bounded(path, 1024 * 1024)) if path.exists() else {}
    require(isinstance(data, dict), "Invalid resource library", "invalid_resource")
    return path, data


def _plugin_owned(library):
    return {(kind, name) for pack in (library.get("_plugins") or {}).values()
            for kind, names in (pack.get("resources") or {}).items() for name in names}


# --- init -------------------------------------------------------------------------------------------------------


def init(workspace, *, name=None, pairing=None, fonts=(), palette=None, mode="light", overwrite=False):
    """Write a valid ``brand.json``: a name, palette roles from a palette resource, a pairing and embedded fonts
    (``fonts`` is ``[(role, file)]``)."""
    import base64
    import random

    from .assets import read_bounded
    from .brand import brand_path, validate, write_raw

    path = brand_path(workspace)
    require(overwrite or not path.exists(), "brand.json already exists; pass --overwrite to replace it",
            "output_exists", field="workspace")
    kit = {"name": name or Path(workspace).resolve().name or "Brand"}
    if palette:
        from .layouts import ROLES, assign_roles
        from .resources import get

        colors = get("palettes", palette, workspace=workspace)
        roles = assign_roles({"palette": colors, "mode": mode, "policy": "strict"}, random.Random(palette))
        kit["palette"] = {role: roles[role] for role in ROLES}
    if pairing:
        from .typefaces import get_pairing

        get_pairing(pairing)
        kit["pairing"] = pairing
    for role, source in fonts:
        from .fonts import validate_font
        from .type_roles import role_name

        role_name(role, "--font ROLE")
        data = read_bounded(source, 16 * 1024 * 1024)
        validate_font(data)
        kit.setdefault("fonts", {})[role] = {"name": f"{_slug(kit['name'])}-{role}",
                                             "data_base64": base64.b64encode(data).decode("ascii")}
    validate(deepcopy(kit))
    write_raw(path, kit)
    return {"path": "brand.json", "name": kit["name"], **({"palette": kit["palette"]} if palette else {}),
            **({"pairing": pairing} if pairing else {}), "fonts": sorted(kit.get("fonts", {})),
            "next": "vixl brand validate; add logos, presets, elements and styles to brand.json"}


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "brand"


# --- pack -------------------------------------------------------------------------------------------------------


def pack(workspace, output, *, overwrite=False):
    """Write the workspace brand and its resource library as one deterministic ``.vixlbrand`` ZIP."""
    from .brand import load_raw
    from .pack_assets import blob_name, read
    from .production import write_bytes
    from .project_folder import deterministic_zip
    from .resources import BUILTINS

    output = Path(output).absolute()
    require(output.suffix == SUFFIX, f"Brand packages end in {SUFFIX}", field="output")
    require(overwrite or not output.exists(), f"Output already exists: {output.name}; pass --overwrite",
            "output_exists", field="output")
    kit = load_raw(workspace)
    require(kit, "No brand.json in the workspace; vixl brand init writes one", "not_found", field="workspace")
    _, library = _library(workspace)
    owned = _plugin_owned(library)
    entries, listed, skipped = {"brand.json": _canonical(kit)}, {}, []
    for kind in sorted(BUILTINS):
        items = {}
        for name, value in sorted((library.get(kind) or {}).items()):
            if (kind, name) in owned:
                skipped.append(f"{kind}/{name}")
            else:
                items[name] = value
        if not items:
            continue
        entries[f"resources/{kind}.json"] = _canonical(items)
        listed[kind] = sorted(items)
        if kind == "assets":
            for record in items.values():
                entries[f"assets/{blob_name(record)}"] = read(record, workspace)
    manifest = {"format": FORMAT, "version": VERSION, "name": kit.get("name"), "resources": listed,
                "files": {member: hashlib.sha256(data).hexdigest() for member, data in sorted(entries.items())}}
    entries["manifest.json"] = _canonical(manifest)
    with tempfile.TemporaryDirectory(prefix=".vixlbrand-") as staging:
        staged = Path(staging) / "pack.zip"
        deterministic_zip(staged, entries)
        data = staged.read_bytes()
    require(len(data) <= MAX_ARCHIVE_BYTES, "The brand package exceeds 64 MiB", "resource_limit")
    write_bytes(output, data, replace=overwrite)
    return {"path": str(output), "name": kit.get("name"), "files": len(entries), "resources": listed,
            "sha256": hashlib.sha256(data).hexdigest(),
            **({"skipped_plugin_resources": skipped} if skipped else {})}


# --- install ----------------------------------------------------------------------------------------------------


def _member_name(name):
    from .resources import BUILTINS

    path = PurePosixPath(name)
    safe = (not path.is_absolute() and "\\" not in name and ".." not in path.parts and name == path.as_posix())
    allowed = (name in ("manifest.json", "brand.json")
               or (len(path.parts) == 2 and path.parts[0] == "resources" and path.suffix == ".json"
                   and path.stem in BUILTINS)
               or ASSET_MEMBER.fullmatch(name) is not None)
    require(safe and allowed, f"Unexpected member in the brand package: {name[:80]!r}", "invalid_pack")


def read_package(source):
    """``{member: bytes}`` of a brand package, every member named in the manifest with a matching SHA-256."""
    from .assets import read_bounded

    data = read_bounded(source, MAX_ARCHIVE_BYTES)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            require(len(infos) <= MAX_MEMBERS, "The brand package has too many members", "resource_limit")
            names = [info.filename for info in infos]
            require(len(set(names)) == len(names), "Duplicate members in the brand package", "invalid_pack")
            require(sum(info.file_size for info in infos) <= MAX_EXPANDED_BYTES,
                    "The brand package expands beyond 96 MiB", "resource_limit")
            members = {}
            for info in infos:
                _member_name(info.filename)
                require(not info.flag_bits & 0x1 and info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                        "Encrypted or unsupported compression in the brand package", "invalid_pack")
                limit = MAX_JSON_BYTES if info.filename.endswith(".json") else 2 * 1024 * 1024
                require(info.file_size <= limit, f"{info.filename} exceeds its size limit", "resource_limit")
                with archive.open(info) as stream:
                    content = stream.read(limit + 1)
                require(len(content) <= limit, f"{info.filename} exceeds its size limit", "resource_limit")
                members[info.filename] = content
    except zipfile.BadZipFile as exc:
        raise VixlError("invalid_pack", "Not a brand package: the file is not a ZIP archive") from exc
    except (RuntimeError, NotImplementedError, EOFError, zipfile.LargeZipFile, ValueError, OSError) as exc:
        raise VixlError("invalid_pack", f"Unreadable brand package: {type(exc).__name__}") from exc
    require("manifest.json" in members and "brand.json" in members,
            "A brand package holds manifest.json and brand.json", "invalid_pack")
    manifest = _json(members["manifest.json"], "manifest.json")
    require(isinstance(manifest, dict) and manifest.get("format") == FORMAT and manifest.get("version") == VERSION
            and isinstance(manifest.get("files"), dict), "Unsupported brand package format", "invalid_pack")
    expected = manifest["files"]
    require(set(expected) == set(members) - {"manifest.json"},
            "The brand package's members do not match its manifest", "invalid_pack")
    for member, digest in expected.items():
        require(hashlib.sha256(members[member]).hexdigest() == digest,
                f"Checksum mismatch for {member} in the brand package", "invalid_pack")
    return members


def _json(data, member):
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise VixlError("invalid_pack", f"{member} in the brand package is not valid JSON") from exc


def _checked(members, workspace):
    """(brand, {kind: {name: value}}, {blob name: bytes}) after validating everything in the package."""
    from .brand import _report_kit, resolve, validate
    from .design import named
    from .pack_assets import blob_name, check_bytes, validate_record
    from .resources import validate as validate_resource

    kit = validate(_json(members["brand.json"], "brand.json"))
    errors = []
    for preset in [None, *(kit.get("presets") or {})]:
        _report_kit(resolve(kit, preset), f"preset {preset}: " if preset else "", errors, [])
    require(not errors, "The brand in the package is not usable: " + "; ".join(dict.fromkeys(errors)), "invalid_brand")
    collected, blobs = {}, {}
    for member, data in members.items():
        if not member.startswith("resources/"):
            continue
        kind = PurePosixPath(member).stem
        items = _json(data, member)
        require(isinstance(items, dict) and len(items) <= 500, f"{member} maps resource names to values",
                "invalid_pack")
        for name, value in items.items():
            named(name)
            if kind == "assets":
                validate_record(value)
                blob = f"assets/{blob_name(value)}"
                require(blob in members, f"Asset {name!r} has no file in the brand package", "invalid_pack")
                require(hashlib.sha256(members[blob]).hexdigest() == value["sha256"],
                        f"Asset {name!r} does not match its file", "invalid_pack")
                require(check_bytes(members[blob], value["media_type"]) == (value["width"], value["height"]),
                        f"Asset {name!r} does not match its recorded size", "invalid_pack")
                blobs[blob_name(value)] = members[blob]
            else:
                validate_resource(kind, value)
                if kind == "objects":
                    from .objects import validate_user_kind

                    validate_user_kind(name, value, workspace)
        collected[kind] = items
    stray = {member for member in members if member.startswith("assets/")} - {f"assets/{name}" for name in blobs}
    require(not stray, "The brand package holds asset files no asset names", "invalid_pack")
    return kit, collected, blobs


def install(workspace, source, *, preset_only=False, as_name=None, overwrite=False):
    """Validate a brand package in full, then write brand.json, the resource library and the asset files
    atomically. ``preset_only`` adds the package's brand to the existing brand.json as a preset and leaves the
    resources alone. Existing different values are replaced only with ``overwrite``."""
    from .brand import PRESET_FIELDS, brand_path, encoded, load_raw, validate
    from .fileio import file_lock
    from .pack_assets import MAX_LIBRARY_BYTES, blob_dir, library_bytes

    workspace = Path(workspace)
    require(workspace.is_dir(), f"Workspace {str(workspace)!r} is not a directory", field="workspace")
    members = read_package(source)
    kit, collected, blobs = _checked(members, workspace)
    path = brand_path(workspace)
    if preset_only:
        base = load_raw(workspace)
        require(base, "--preset-only adds a preset to an existing brand.json; this workspace has none",
                "not_found", field="workspace")
        preset = as_name or _slug(kit.get("name") or Path(source).stem)
        require(overwrite or preset not in (base.get("presets") or {}),
                f"brand.json already has a preset {preset!r}; pass --overwrite or --as NAME", "output_exists",
                field="as")
        merged = deepcopy(base)
        merged.setdefault("presets", {})[preset] = {key: deepcopy(value) for key, value in kit.items()
                                                    if key in PRESET_FIELDS and key not in ("name", "extends")}
        validate(deepcopy(merged))
        _commit(workspace, {path: encoded(merged)}, {})
        return {"installed": kit.get("name"), "preset": preset, "path": "brand.json",
                "note": f"Select it per document with {{type: brand-preset, name: {preset}}}"}
    with file_lock(str(_library_path(workspace))):
        library_path, library = _library(workspace)
        require(overwrite or not path.exists() or load_raw(workspace) == kit,
                "brand.json already exists and differs; pass --overwrite to replace it", "output_exists",
                field="workspace")
        owned = _plugin_owned(library)
        updated = deepcopy(library)
        conflicts = []
        for kind, items in collected.items():
            for name, value in items.items():
                require((kind, name) not in owned, f"{kind} {name!r} belongs to an installed plugin pack",
                        "resource_conflict")
                current = (library.get(kind) or {}).get(name)
                if current is not None and current != value:
                    conflicts.append(f"{kind}/{name}")
                updated.setdefault(kind, {})[name] = value
        require(overwrite or not conflicts, f"The workspace library already holds different {', '.join(conflicts)}; "
                "pass --overwrite to replace them", "output_exists", conflicts=conflicts)
        library_data = json.dumps(updated, ensure_ascii=False).encode()
        require(len(library_data) <= 1024 * 1024, "The resource library would exceed 1 MiB", "resource_limit")
        require(library_bytes(updated) <= MAX_LIBRARY_BYTES, "The resource library would keep too many asset bytes",
                "resource_limit")
        folder = blob_dir(library_path)
        _commit(workspace, {library_path: library_data, path: encoded(kit)},
                {folder / name: data for name, data in blobs.items()})
    return {"installed": kit.get("name"), "path": "brand.json",
            "resources": {kind: sorted(items) for kind, items in collected.items()},
            **({"replaced": conflicts} if conflicts else {})}


def _library_path(workspace):
    from .resources import resource_path

    return resource_path(workspace)


def _commit(workspace, files, blobs):
    """Write ``blobs`` (new content-addressed files) then ``files`` (replacements), restoring the previous state
    when any step fails."""
    created, replaced = [], []
    try:
        for target, data in blobs.items():
            if target.is_file():
                continue
            require(not target.parent.is_symlink(), "The resource asset folder must not be a symbolic link",
                    "forbidden")
            target.parent.mkdir(parents=True, exist_ok=True)
            _atomic(target, data)
            created.append(target)
        for target, data in files.items():
            previous = target.read_bytes() if target.exists() else None
            _atomic(target, data)
            replaced.append((target, previous))
    except BaseException:
        for target, previous in reversed(replaced):
            if previous is None:
                target.unlink(missing_ok=True)
            else:
                _atomic(target, previous)
        for target in created:
            target.unlink(missing_ok=True)
        raise


def _atomic(target, data):
    fd, temp = tempfile.mkstemp(dir=target.parent, prefix=".vixl-install-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


# --- element ----------------------------------------------------------------------------------------------------


def add_element(workspace, name, source, *, ref=None, overwrite=False, limits=None):
    """Save an object of a document (or the whole document as one group) as a brand.json element."""
    from .assets import local_path
    from .brand import ELEMENT_NAME, brand_path, element_from_document, load_raw, validate, write_raw
    from .project import Project

    require(isinstance(name, str) and ELEMENT_NAME.fullmatch(name),
            "Element names are 1-64 letters, numbers, underscores or hyphens", field="name")
    path = brand_path(workspace)
    raw = load_raw(workspace) if path.exists() else {}
    require(overwrite or name not in (raw.get("elements") or {}),
            f"brand.json already has an element {name!r}; pass --overwrite to replace it", "output_exists",
            field="name")
    other = Project.load(local_path(workspace, source), limits=limits)
    raw = deepcopy(raw)
    raw.setdefault("elements", {})[name] = element_from_document(other, ref)
    validate(deepcopy(raw))
    write_raw(path, raw)
    item = raw["elements"][name]
    return {"element": name, "path": "brand.json", "layers": len(item["layers"]), "assets": len(item["assets"]),
            "use": f"{{type: object-place, name: 'brand:{name}'}}"}
