"""Portable character packages (``.vixlchar``): one rigged character with named expressions, poses and motions.

A package is one deterministic ZIP of two members. ``character.vixl`` is the portable object document of the
character (``objects.portable_bytes``: the character group top-level, with the fonts, images and swatches it uses).
``manifest.json`` is ``{format, version, name, kind, character_version, description, tags, size, parts, rig,
expressions, poses, motions, checks, fonts, assets, files, created_with}``: ``files`` holds the SHA-256 of
``character.vixl``, ``fonts`` and ``assets`` those of the files inside it.

Package files are untrusted input. Reading is bounded (archive and member sizes, a fixed list of members, no
encryption), the document opens through the ordinary bounded loader, and every digest and manifest field is
checked against the character it describes before anything is placed. Nothing in a package is executed.
"""

import difflib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
import zipfile

from ...errors import VixlError, require
from ...model import finite, is_number
from .characters import (CYCLE_BONES, VIEWS, check_joints, check_motion, cycle, pose, pose_key, recolor)

FORMAT, VERSION = "vixl-character", 1
SUFFIX = ".vixlchar"
DOCUMENT, MANIFEST = "character.vixl", "manifest.json"
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_NAMED = 64
MAX_KEYS = 64
MAX_SCAN = 4000
MAX_DEPTH = 6
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
RELEASE = re.compile(r"\d{1,6}(?:\.\d{1,6}){0,2}(?:[-+][0-9A-Za-z.-]{1,32})?")
DIGEST = re.compile(r"[0-9a-f]{64}")
MANIFEST_KEYS = ("format", "version", "name", "kind", "character_version", "description", "tags", "size", "parts",
                 "rig", "expressions", "poses", "motions", "checks", "fonts", "assets", "files", "created_with")
CYCLE_FIELDS = ("cycle", "start", "duration", "period", "amount", "samples", "view")
KEY_FIELDS = ("time", "angles", "easing")
SKIP_DIRS = ("node_modules", "__pycache__")

# Expression variants by part family, applied to the part as placed: sx/sy scale its box about its centre, dy moves
# it by a fraction of its width (negative is up), rot turns it (left parts as given, right parts mirrored).
FAMILY = {"left-eye": "eye", "right-eye": "eye", "left-brow": "brow", "right-brow": "brow", "mouth": "mouth"}
VARIANTS = {
    "eye": {"open": {}, "wide": {"sx": 1.15, "sy": 1.3}, "closed": {"sy": 0.15}, "squint": {"sy": 0.45},
            "happy": {"sy": 0.3, "dy": -0.1}},
    "brow": {"neutral": {}, "raised": {"dy": -0.35}, "lowered": {"dy": 0.15}, "angry": {"rot": 15, "dy": 0.1},
             "sad": {"rot": -15, "dy": 0.05}, "tilted": {"rot": -12}},
    "mouth": {"neutral": {}, "smile": {"sx": 1.3, "sy": 0.8}, "grin": {"sx": 1.4, "sy": 1.9},
              "frown": {"sx": 0.9, "sy": 0.55, "dy": 0.12}, "open": {"sy": 2.6}, "o": {"sx": 0.65, "sy": 2.4},
              "flat": {"sx": 1.1, "sy": 0.35}, "smirk": {"sx": 1.05, "sy": 0.7, "rot": -8}},
}
# What a package offers when its author names none: each entry whose parts or bones the character has. The standard
# character's brows touch its hairline in the hair colour, so these defaults turn brows rather than raise them.
EXPRESSIONS = {
    "neutral": {},
    "happy": {"mouth": "smile", "left-eye": "happy", "right-eye": "happy"},
    "confused": {"left-brow": "tilted", "right-brow": "lowered", "mouth": "smirk"},
    "surprised": {"left-eye": "wide", "right-eye": "wide", "mouth": "o"},
    "sad": {"left-brow": "sad", "right-brow": "sad", "mouth": "frown"},
    "angry": {"left-brow": "angry", "right-brow": "angry", "mouth": "flat"},
    "celebrate": {"left-eye": "closed", "right-eye": "closed", "mouth": "grin"},
}
POSES = {
    "celebrate": {"left-upper-arm": -100, "left-lower-arm": -50, "right-upper-arm": 100, "right-lower-arm": 50},
    "wave": {"right-upper-arm": 100, "right-lower-arm": 50, "right-hand": 10},
    "point": {"right-upper-arm": 90, "right-lower-arm": 0},
}
MOTIONS = {
    "wave": {"cycle": "wave", "duration": 1200, "period": 600},
    "walk": {"cycle": "walk", "duration": 2000, "period": 1000},
    "idle": {"cycle": "idle", "duration": 2000, "period": 2000},
    "react": {"cycle": "react", "duration": 800},
}


def _invalid(message, field):
    raise VixlError("invalid_pack", f"Invalid character package: {message}", field=field)


def canonical(value):
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _name(value, field):
    require(isinstance(value, str) and NAME.fullmatch(value), f"{field}: names are 1-64 letters, digits, hyphens or "
            f"underscores; got {value!r}", field=field)
    return value


# --- validation against a character -----------------------------------------------------------------------------


def check_expression(group, mapping, field):
    """``mapping`` ({part: variant}) names face parts the character has and variants of their family."""
    require(isinstance(mapping, dict) and len(mapping) <= len(FAMILY), f"{field} maps parts to variants, such as "
            "{mouth: smile, left-brow: raised}", field=field)
    parts = group["character"]["parts"]
    for part, variant in mapping.items():
        family = FAMILY.get(part)
        require(family is not None, f"{field}.{part}: expressions change {', '.join(FAMILY)}; {part!r} is not one "
                "of them", field=f"{field}.{part}", allowed=list(FAMILY))
        require(part in parts, f"{field}.{part}: {group['name']!r} has no {part} (its parts: {', '.join(parts)})",
                field=f"{field}.{part}", character=group["name"], missing=[part])
        variants = VARIANTS[family]
        require(variant in variants, f"{field}.{part}: {variant!r} is not a {family} variant; variants: "
                f"{', '.join(variants)}", field=f"{field}.{part}", allowed=list(variants),
                suggestions=difflib.get_close_matches(str(variant), list(variants), 2, 0.5))


def check_pose(group, angles, field):
    require(isinstance(angles, dict) and len(angles) <= 64 and all(is_number(v) for v in angles.values()),
            f"{field} maps joints to angles in degrees, such as {{right-upper-arm: 90}}", field=field)
    check_joints(group, angles, field)
    for joint, value in angles.items():
        finite(value, f"{field}.{joint}", -3600, 3600)


def check_motion_spec(group, spec, field):
    """A motion is a cycle ``{cycle, start?, duration?, period?, amount?, samples?, view?}`` the rig can drive, or
    pose keys ``{keys: [{time, angles, easing?}]}`` on joints it has."""
    require(isinstance(spec, dict) and ("cycle" in spec) != ("keys" in spec), f"{field} is {{cycle: walk|run|idle|"
            "ride|react|wave, duration?, period?, amount?, samples?, view?}} or {keys: [{time, angles, easing?}]}",
            field=field)
    if "cycle" in spec:
        unknown = sorted(set(spec) - set(CYCLE_FIELDS))
        require(not unknown, f"{field}: unknown cycle field(s) {unknown}", field=field, allowed=list(CYCLE_FIELDS))
        require(spec["cycle"] in CYCLE_BONES, f"{field}.cycle is one of {', '.join(CYCLE_BONES)}",
                field=f"{field}.cycle", allowed=list(CYCLE_BONES))
        for key in ("start", "duration"):
            require(key not in spec or isinstance(spec[key], str) or is_number(spec[key]),
                    f"{field}.{key} is a time (milliseconds, '1.5s' or a marker)", field=f"{field}.{key}")
        for key in ("period", "amount"):
            require(key not in spec or is_number(spec[key]), f"{field}.{key} is a number", field=f"{field}.{key}")
        require("samples" not in spec or (isinstance(spec["samples"], int) and not isinstance(spec["samples"], bool)
                                          and 4 <= spec["samples"] <= 120),
                f"{field}.samples is 4-120", field=f"{field}.samples")
        require(spec.get("view", "front") in VIEWS, f"{field}.view is {' or '.join(VIEWS)}", field=f"{field}.view")
        check_motion(group, spec["cycle"], field)
        return
    keys = spec["keys"]
    require(set(spec) == {"keys"} and isinstance(keys, list) and 1 <= len(keys) <= MAX_KEYS,
            f"{field}.keys is a list of 1-{MAX_KEYS} pose keys", field=f"{field}.keys")
    for index, key in enumerate(keys):
        where = f"{field}.keys[{index}]"
        require(isinstance(key, dict) and set(key) <= set(KEY_FIELDS) and "time" in key and "angles" in key,
                f"{where} is {{time, angles, easing?}}", field=where)
        require(isinstance(key["time"], str) or is_number(key["time"]), f"{where}.time is a time", field=where)
        require(isinstance(key.get("easing", ""), str), f"{where}.easing is an easing name", field=where)
        check_pose(group, key["angles"], f"{where}.angles")


def defaults(group):
    """The built-in expressions, poses and motions this character can use, plus ``rest`` (every joint at 0)."""
    parts, bones = group["character"]["parts"], group["character"]["bones"]
    expressions = {name: dict(value) for name, value in EXPRESSIONS.items() if all(part in parts for part in value)}
    poses = {"rest": {bone: 0 for bone in bones}}
    poses.update({name: dict(value) for name, value in POSES.items() if all(bone in bones for bone in value)})
    motions = {name: dict(value) for name, value in MOTIONS.items()
               if all(bone in bones for bone in CYCLE_BONES[value["cycle"]])}
    return expressions, poses, motions


def _named(group, values, check, field):
    require(isinstance(values, dict) and len(values) <= MAX_NAMED, f"{field} maps names to entries (at most "
            f"{MAX_NAMED})", field=field)
    for name, value in values.items():
        _name(name, f"{field}.{name}")
        check(group, value, f"{field}.{name}")
    return values


def _checks(values, field="checks"):
    from ...checks import CHECKS, OPTIONAL_CHECKS

    known = list(CHECKS + OPTIONAL_CHECKS)
    require(isinstance(values, list) and len(values) <= 16 and all(isinstance(v, str) for v in values),
            f"{field} is a list of check names", field=field)
    unknown = [name for name in values if name not in known]
    require(not unknown, f"{field}: unknown check(s) {unknown}", field=field, allowed=known)
    return list(dict.fromkeys(values))


# --- building ---------------------------------------------------------------------------------------------------


def _rig(group):
    by_id = {ident: part for part, ident in group["character"]["parts"].items()}
    rig = {}
    for bone, spec in group["character"]["bones"].items():
        rig[bone] = {"part": by_id.get(spec["layer"], ""), "length": spec["length"],
                     "limits": list(spec.get("limits", [-180, 180])), **({"parent": spec["parent"]}
                                                                          if spec.get("parent") else {})}
    return rig


def _inventory(document):
    fonts = {name: hashlib.sha256(document.assets[asset]).hexdigest()
             for name, asset in document.state.get("fonts", {}).items() if asset in document.assets}
    assets = {member: hashlib.sha256(data).hexdigest() for member, data in sorted(document.assets.items())}
    return fonts, assets


def build(project, target, output, *, name=None, description="", tags=(), version="1.0.0", expressions=None,
          poses=None, motions=None, checks=None, overwrite=False):
    """Write the character ``target`` as a ``.vixlchar`` package; returns a summary with the file's SHA-256."""
    from ...objects import portable_bytes, record
    from ...production import write_bytes
    from ...project_folder import deterministic_zip
    from ... import __version__
    from .characters import rig as character

    output = Path(output)
    require(output.suffix == SUFFIX, f"Character packages end in {SUFFIX}", field="output")
    require(overwrite or not output.exists(), f"Output already exists: {output.name}; pass overwrite: true",
            "output_exists", field="output")
    group = character(project, target)
    require(group["character"]["bones"], f"{group['name']!r} has no rig; add one with character-rig before packaging",
            field="target")
    name = _name(name or group["name"], "name")
    require(isinstance(version, str) and RELEASE.fullmatch(version), "version is a release such as 1.0.0",
            field="version")
    require(isinstance(description, str) and len(description) <= 2000, "description is at most 2000 characters",
            field="description")
    tags = list(tags or [])
    require(len(tags) <= 32 and all(isinstance(t, str) and 0 < len(t) <= 64 for t in tags), "tags are at most 32 "
            "short strings", field="tags")
    builtin_expressions, builtin_poses, builtin_motions = defaults(group)
    expressions = _named(group, builtin_expressions if expressions is None else expressions, check_expression,
                         "expressions")
    poses = _named(group, builtin_poses if poses is None else poses, check_pose, "poses")
    motions = _named(group, builtin_motions if motions is None else motions, check_motion_spec, "motions")
    if checks is None:
        checks = ["character", *(["object"] if group.get("object") else [])]
    checks = _checks(checks)
    data = portable_bytes(project, {"isolate": [group["id"]]})
    document = _open(data, project.limits)
    fonts, assets = _inventory(document)
    canvas = document.state["canvas"]
    manifest = {
        "format": FORMAT, "version": VERSION, "name": name, "kind": record(group)["kind"],
        "character_version": version, "description": description, "tags": tags,
        "size": [canvas["width"], canvas["height"]], "parts": sorted(group["character"]["parts"]),
        "rig": _rig(group), "expressions": expressions, "poses": poses, "motions": motions,
        "checks": checks, "fonts": fonts, "assets": assets, "files": {DOCUMENT: hashlib.sha256(data).hexdigest()},
        "created_with": __version__,
    }
    with tempfile.TemporaryDirectory(prefix=".vixlchar-") as staging:
        staged = Path(staging) / "package.zip"
        deterministic_zip(staged, {MANIFEST: canonical(manifest), DOCUMENT: data})
        packed = staged.read_bytes()
    require(len(packed) <= MAX_ARCHIVE_BYTES, "The character package exceeds 64 MiB", "resource_limit")
    write_bytes(output, packed, replace=overwrite)
    return {"output": str(output), "name": name, "kind": manifest["kind"], "character_version": version,
            "sha256": hashlib.sha256(packed).hexdigest(), "bytes": len(packed), "parts": len(manifest["parts"]),
            "bones": sorted(manifest["rig"]), "expressions": sorted(expressions), "poses": sorted(poses),
            "motions": sorted(motions), "checks": checks}


# --- reading ----------------------------------------------------------------------------------------------------


def _archive(path, limits):
    """``{member: bytes}`` of a package within fixed bounds, every member named in the manifest with its digest."""
    from ...assets import read_bounded

    data = read_bounded(path, MAX_ARCHIVE_BYTES)
    limit = {MANIFEST: MAX_MANIFEST_BYTES, DOCUMENT: limits.max_project_bytes}
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            require(sorted(names) == sorted(limit), f"A character package holds exactly {MANIFEST} and {DOCUMENT}; "
                    f"found {[n[:80] for n in names[:8]]}", "invalid_pack", field="package")
            require(sum(info.file_size for info in infos) <= MAX_MANIFEST_BYTES + limits.max_project_bytes,
                    "The character package expands beyond its limit", "resource_limit", field="package")
            members = {}
            for info in infos:
                require(not info.flag_bits & 0x1 and info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                        "Encrypted or unsupported compression in the character package", "invalid_pack",
                        field="package")
                bound = limit[info.filename]
                require(info.file_size <= bound, f"{info.filename} exceeds its size limit", "resource_limit",
                        field="package")
                with archive.open(info) as stream:
                    content = stream.read(bound + 1)
                require(len(content) <= bound, f"{info.filename} exceeds its size limit", "resource_limit",
                        field="package")
                members[info.filename] = content
    except zipfile.BadZipFile as exc:
        raise VixlError("invalid_pack", "Not a character package: the file is not a ZIP archive",
                        field="package") from exc
    except (RuntimeError, NotImplementedError, EOFError, zipfile.LargeZipFile, ValueError, OSError) as exc:
        raise VixlError("invalid_pack", f"Unreadable character package: {type(exc).__name__}", field="package") from exc
    return data, members


def _json(data):
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise VixlError("invalid_pack", f"{MANIFEST} in the character package is not valid JSON",
                        field="package") from exc


def validate_manifest(manifest):
    """The manifest's shape: known keys, types and sizes (what it says about the character is checked against
    the document by ``read``)."""
    def need(condition, key, text):
        if not condition:
            _invalid(f"manifest {key} {text}", f"manifest.{key}")

    need(isinstance(manifest, dict) and manifest.get("format") == FORMAT, "format", f"must be {FORMAT!r}")
    need(manifest.get("version") == VERSION, "version", f"must be {VERSION} (this release reads version {VERSION})")
    unknown = sorted(set(manifest) - set(MANIFEST_KEYS))
    need(not unknown, "keys", f"include unknown field(s) {unknown[:8]}")
    missing = [key for key in MANIFEST_KEYS if key not in manifest]
    need(not missing, "keys", f"lack {missing}")
    need(isinstance(manifest["name"], str) and NAME.fullmatch(manifest["name"]), "name", "is not a valid name")
    need(isinstance(manifest["kind"], str) and 0 < len(manifest["kind"]) <= 80, "kind", "must be an object kind")
    need(isinstance(manifest["character_version"], str) and RELEASE.fullmatch(manifest["character_version"]),
         "character_version", "must be a release such as 1.0.0")
    need(isinstance(manifest["description"], str) and len(manifest["description"]) <= 2000, "description",
         "must be text of at most 2000 characters")
    need(isinstance(manifest["tags"], list) and len(manifest["tags"]) <= 32
         and all(isinstance(t, str) and len(t) <= 64 for t in manifest["tags"]), "tags", "must be short strings")
    size = manifest["size"]
    need(isinstance(size, list) and len(size) == 2 and all(isinstance(v, int) and 0 < v <= 1_000_000 for v in size),
         "size", "must be [width, height]")
    parts = manifest["parts"]
    need(isinstance(parts, list) and 0 < len(parts) <= 64 and all(isinstance(p, str) and p for p in parts), "parts",
         "must list 1-64 part names")
    rig = manifest["rig"]
    need(isinstance(rig, dict) and 0 < len(rig) <= 64 and all(
        isinstance(b, str) and isinstance(s, dict) and set(s) <= {"part", "parent", "length", "limits"}
        and isinstance(s.get("part"), str) and is_number(s.get("length"))
        and isinstance(s.get("limits"), list) and len(s["limits"]) == 2 and all(is_number(v) for v in s["limits"])
        and isinstance(s.get("parent", ""), str) for b, s in rig.items()), "rig",
        "maps 1-64 bones to {part, parent?, length, limits}")
    for key in ("expressions", "poses", "motions"):
        value = manifest[key]
        need(isinstance(value, dict) and len(value) <= MAX_NAMED and all(
            isinstance(n, str) and NAME.fullmatch(n) and isinstance(v, dict) for n, v in value.items()), key,
            f"maps at most {MAX_NAMED} names to objects")
    need(isinstance(manifest["checks"], list) and len(manifest["checks"]) <= 16
         and all(isinstance(c, str) for c in manifest["checks"]), "checks", "must list check names")
    for key, limit in (("fonts", 256), ("assets", 10000)):
        value = manifest[key]
        need(isinstance(value, dict) and len(value) <= limit and all(
            isinstance(n, str) and len(n) <= 200 and isinstance(d, str) and DIGEST.fullmatch(d)
            for n, d in value.items()), key, "maps names to SHA-256 digests")
    files = manifest["files"]
    need(isinstance(files, dict) and set(files) == {DOCUMENT} and isinstance(files[DOCUMENT], str)
         and DIGEST.fullmatch(files[DOCUMENT]), "files", f"must give the SHA-256 of {DOCUMENT}")
    need(isinstance(manifest["created_with"], str) and len(manifest["created_with"]) <= 40, "created_with",
         "must be a release")


def _open(data, limits):
    """The package's document, opened by the ordinary bounded document loader from a private temporary file."""
    from ...project import Project

    with tempfile.TemporaryDirectory(prefix="vixl-character-") as staging:
        path = Path(staging) / DOCUMENT
        path.write_bytes(data)
        document = Project.load(path, limits=limits)
    document.path = None
    return document


def character_root(document):
    tops = [layer for layer in document.state["layers"] if not layer.get("parent")]
    if len(tops) != 1 or tops[0]["type"] != "group" or "character" not in tops[0]:
        _invalid(f"{DOCUMENT} must hold one top-level character group", DOCUMENT)
    return tops[0]


def _consistent(manifest, document):
    """Everything the manifest says about the character is true of the document it ships."""
    from ...objects import record

    root = character_root(document)
    ids = {layer["id"] for layer in document.state["layers"]}
    parts, bones = root["character"]["parts"], root["character"]["bones"]
    if sorted(parts) != sorted(manifest["parts"]) or not set(parts.values()) <= ids:
        _invalid(f"the manifest's parts do not match the character in {DOCUMENT}", "manifest.parts")
    by_id = {ident: part for part, ident in parts.items()}
    rig = {bone: (by_id.get(spec["layer"], ""), spec.get("parent") or "") for bone, spec in bones.items()}
    listed = {bone: (spec["part"], spec.get("parent") or "") for bone, spec in manifest["rig"].items()}
    if rig != listed:
        _invalid(f"the manifest's rig does not match the character's bones in {DOCUMENT}", "manifest.rig")
    if record(root)["kind"] != manifest["kind"]:
        _invalid(f"the manifest's kind does not match the character in {DOCUMENT}", "manifest.kind")
    canvas = document.state["canvas"]
    if [canvas["width"], canvas["height"]] != manifest["size"]:
        _invalid(f"the manifest's size does not match {DOCUMENT}", "manifest.size")
    fonts, assets = _inventory(document)
    if fonts != manifest["fonts"]:
        _invalid(f"the manifest's fonts do not match the fonts in {DOCUMENT}", "manifest.fonts")
    if assets != manifest["assets"]:
        _invalid(f"the manifest's assets do not match the files in {DOCUMENT}", "manifest.assets")
    for key, check in (("expressions", check_expression), ("poses", check_pose), ("motions", check_motion_spec)):
        for name, value in manifest[key].items():
            try:
                check(root, value, f"{key}.{name}")
            except VixlError as exc:
                raise VixlError("invalid_pack", f"Invalid character package: {exc}",
                                field=f"manifest.{key}.{name}") from exc
    try:
        _checks(manifest["checks"], "manifest.checks")
    except VixlError as exc:
        raise VixlError("invalid_pack", f"Invalid character package: {exc}", field="manifest.checks") from exc
    return root


def read(path, *, limits=None, label=None, document=True):
    """A verified package ``{path, label, manifest, sha256, bytes, document}``: the archive read within bounds, every
    digest matched and, with ``document``, the character document opened and checked against the manifest."""
    from ...model import Limits

    limits = limits or Limits()
    path = Path(path)
    require(path.suffix == SUFFIX, f"Character packages end in {SUFFIX}", field="package")
    require(path.is_file(), f"No character package at {label or path.name!r}", "not_found", field="package")
    data, members = _archive(path, limits)
    manifest = _json(members[MANIFEST])
    validate_manifest(manifest)
    if hashlib.sha256(members[DOCUMENT]).hexdigest() != manifest["files"][DOCUMENT]:
        _invalid(f"checksum mismatch for {DOCUMENT}", DOCUMENT)
    package = {"path": path, "label": label or path.name, "manifest": manifest,
               "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "document": None}
    if document:
        package["document"] = _open(members[DOCUMENT], limits)
        _consistent(manifest, package["document"])
    return package


def summary(package, full=False):
    """What discover and inspect report for a package."""
    m = package["manifest"]
    result = {"name": m["name"], "kind": m["kind"], "character_version": m["character_version"],
              "package": package["label"], **({"description": m["description"]} if m["description"] else {}),
              **({"tags": m["tags"]} if m["tags"] else {}), "parts": len(m["parts"]), "bones": len(m["rig"]),
              "expressions": sorted(m["expressions"]), "poses": sorted(m["poses"]), "motions": sorted(m["motions"])}
    if full:
        result.update(
            format=m["format"], version=m["version"], size=m["size"], parts=m["parts"], rig=m["rig"],
            expressions=m["expressions"], poses=m["poses"], motions=m["motions"], checks=m["checks"],
            fonts=sorted(m["fonts"]), assets=len(m["assets"]), sha256=package["sha256"], bytes=package["bytes"],
            created_with=m["created_with"],
            place={"package": package["label"], **({"pose": sorted(m["poses"])[0]} if m["poses"] else {}),
                   **({"expression": sorted(m["expressions"])[0]} if m["expressions"] else {})})
    return result


# --- discovery --------------------------------------------------------------------------------------------------


def user_library():
    """The user's character folder: ``VIXL_CHARACTERS``, else ``characters/`` beside the user resource library."""
    from ...resources import resource_path

    value = os.environ.get("VIXL_CHARACTERS")
    return Path(value).expanduser() if value else resource_path().parent / "characters"


def _scan(root):
    """``(paths, truncated)``: the ``.vixlchar`` files under ``root``, skipping hidden folders and links, at most
    ``MAX_DEPTH`` folders deep and ``MAX_SCAN`` entries in all."""
    found, seen = [], 0
    for directory, folders, files in os.walk(root, followlinks=False):
        depth = len(Path(directory).relative_to(root).parts)
        folders[:] = sorted(f for f in folders if not f.startswith(".") and f not in SKIP_DIRS) if depth < MAX_DEPTH else []
        for name in sorted(files):
            seen += 1
            if seen > MAX_SCAN:
                return found, True
            path = Path(directory) / name
            if name.endswith(SUFFIX) and not name.startswith(".") and not path.is_symlink():
                found.append(path)
        seen += len(folders)
    return found, False


def _sources(workspace):
    sources = []
    if workspace is not None and Path(workspace).is_dir():
        sources.append(("workspace", Path(workspace).resolve()))
    user = user_library()
    if user.is_dir():
        sources.append(("user", user.resolve()))
    return sources


def _label(source, root, path):
    relative = path.relative_to(root).as_posix()
    return relative if source == "workspace" else f"user:{relative}"


def discover(workspace=None, query=None, *, limits=None):
    """Packages in the workspace and the user library, each read and verified (its document is not opened), with
    those that fail to read listed under ``invalid``."""
    words = re.findall(r"[a-z0-9]+", (query or "").casefold())
    found, invalid, truncated = [], [], False
    for source, root in _sources(workspace):
        paths, cut = _scan(root)
        truncated = truncated or cut
        for path in paths:
            label = _label(source, root, path)
            try:
                package = read(path, limits=limits, label=label, document=False)
            except VixlError as exc:
                invalid.append({"package": label, "source": source, "error": str(exc)})
                continue
            m = package["manifest"]
            text = " ".join([m["name"], m["kind"], m["description"], *m["tags"]]).casefold()
            if all(word in text for word in words):
                found.append({**summary(package), "source": source})
    return {"characters": found, "count": len(found), **({"invalid": invalid} if invalid else {}),
            **({"truncated": True} if truncated else {})}


def locate(ref, workspace=None, resolve=None, limits=None):
    """``(path, label)`` of a package: a workspace path ending in .vixlchar, ``user:PATH`` in the user library, or
    the name of a package found by ``discover`` (the workspace first)."""
    require(isinstance(ref, str) and ref.strip(), "package names a .vixlchar file or a character package name",
            field="package")
    if ref.startswith("user:"):
        root = user_library().resolve()
        path = (root / ref[5:]).resolve()
        require(path.is_relative_to(root), "package escapes the user character library", "forbidden",
                field="package")
        return path, ref
    if ref.endswith(SUFFIX):
        path = resolve(ref) if resolve is not None else Path(workspace or ".") / ref
        return Path(path), ref
    _name(ref, "package")
    listing = discover(workspace, limits=limits)["characters"]
    matches = [item for item in listing if item["name"] == ref]
    if not matches:
        names = sorted({item["name"] for item in listing})
        raise VixlError("not_found", f"No character package named {ref!r}" + (
            f"; found: {', '.join(names[:20])}" if names else f" in the workspace or {user_library()}")
            + "; character-discover lists them", field="package",
            suggestions=difflib.get_close_matches(ref, names, 3, 0.5))
    first = matches[0]
    root = dict(_sources(workspace))[first["source"]]
    label = first["package"]
    return root / (label[5:] if label.startswith("user:") else label), label


# --- placing ----------------------------------------------------------------------------------------------------


def _choice(manifest, root, value, key, check):
    """The named entry ``value`` from the manifest's ``key``, or an inline entry checked against the character."""
    if value is None:
        return None
    if isinstance(value, str):
        named = manifest[key]
        if value not in named:
            raise VixlError("invalid_operation", f"{key[:-1]}: package {manifest['name']!r} has no {key[:-1]} {value!r}; "
                            f"it has {', '.join(sorted(named)) or 'none'}", field=key[:-1], allowed=sorted(named),
                            suggestions=difflib.get_close_matches(value, list(named), 3, 0.5))
        return value, named[value]
    check(root, value, key[:-1])
    return "inline", value


def scale_parts(project, group, factors):
    """Scale parts about their pivots by ``{part: factor}``; a bone on a scaled part lengthens with it."""
    require(isinstance(factors, dict) and len(factors) <= 64, "scale_parts maps parts to factors, such as {head: 1.2}",
            field="scale_parts")
    parts, bones = group["character"]["parts"], group["character"]["bones"]
    for part, factor in factors.items():
        require(part in parts, f"scale_parts.{part}: {group['name']!r} has no part {part!r}; parts: "
                f"{', '.join(parts)}", field=f"scale_parts.{part}", allowed=list(parts))
        finite(factor, f"scale_parts.{part}", 0.25, 4)
        layer = project.layer(parts[part])
        px, py = layer.get("pivot", [0.5, 0.5])
        width, height = layer["width"], layer["height"]
        layer.update(x=layer["x"] + px * width * (1 - factor), y=layer["y"] + py * height * (1 - factor),
                     width=max(1, width * factor), height=max(1, height * factor))
        for bone in bones.values():
            if bone["layer"] == layer["id"]:
                bone["length"] = bone["length"] * factor
    pose(project, group, {})


def express(project, group, mapping):
    """Apply an expression ({part: variant}) to the parts as they are now."""
    parts = group["character"]["parts"]
    for part, variant in mapping.items():
        change = VARIANTS[FAMILY[part]][variant]
        layer = project.layer(parts[part])
        require(all(is_number(layer.get(k)) for k in ("x", "y", "width", "height")),
                f"expression: {layer['name']!r} has no numeric box to change", field=f"expression.{part}")
        width, height = layer["width"], layer["height"]
        new_width, new_height = max(1, width * change.get("sx", 1)), max(1, height * change.get("sy", 1))
        cx = layer["x"] + width / 2
        cy = layer["y"] + height / 2 + change.get("dy", 0) * width
        layer.update(x=cx - new_width / 2, y=cy - new_height / 2, width=new_width, height=new_height, constraints={})
        turn = change.get("rot", 0) * (-1 if part.startswith("right") else 1)
        if turn:
            layer["rotation"] = layer.get("rotation", 0) + turn


def place(project, package, request):
    """Place a verified package as an editable character with new IDs and its rig bindings, then apply overrides,
    a pose, an expression and a motion. Everything is checked before the document changes; it is one undo step."""
    from ...objects import from_document, place as place_object, refresh_outlines, subtree
    from ...validation import check_state

    manifest, document = package["manifest"], package["document"]
    source = character_root(document)
    sizing = [key for key in ("scale", "width", "height") if key in request]
    require(len(sizing) <= 1, f"{' and '.join(sizing)} together would change the character's proportions; give one "
            "(the aspect ratio is kept), and scale single parts with scale_parts", field=sizing[-1] if sizing else "scale")
    chosen_pose = _choice(manifest, source, request.get("pose"), "poses", check_pose)
    chosen_expression = _choice(manifest, source, request.get("expression"), "expressions", check_expression)
    chosen_motion = _choice(manifest, source, request.get("motion"), "motions", check_motion_spec)
    candidate = project.clone()
    op = {"name": manifest["name"], "motion": False, **({"name_as": request["name"]} if request.get("name") else {}),
          **{key: request[key] for key in ("x", "y", "scale", "width", "height") if key in request}}
    root = place_object(candidate, op, from_document(document, package["label"]))
    if request.get("scale_parts"):
        scale_parts(candidate, root, request["scale_parts"])
    recolor(candidate, root, request.get("colors"), request.get("outfit"), strict=True)
    if chosen_pose:
        pose(candidate, root, chosen_pose[1])
    if chosen_expression:
        express(candidate, root, chosen_expression[1])
    if chosen_motion:
        spec = chosen_motion[1]
        if "cycle" in spec:
            cycle(candidate, root, spec)
        else:
            for key in spec["keys"]:
                pose_key(candidate, root, key["angles"], key["time"], key.get("easing", "ease-in-out"))
    refresh_outlines(candidate)
    check_state(candidate, candidate.state)
    if candidate.transaction is None:
        candidate._record([], f"Place character {manifest['name']}")
    project.__dict__.update(candidate.__dict__)
    layers = subtree(project, root["id"])
    result = {"success": True, "layer": {"id": root["id"], "name": root["name"], "type": "group"},
              "character": manifest["name"], "package": package["label"],
              "character_version": manifest["character_version"], "kind": manifest["kind"], "layers": len(layers)}
    for key, chosen in (("pose", chosen_pose), ("expression", chosen_expression), ("motion", chosen_motion)):
        if chosen:
            result[key] = chosen[0]
    if manifest["checks"]:
        result["checks"] = _placed_checks(project, manifest["checks"], layers)
    return result


def _placed_checks(project, checks, layers):
    """The package's checks on the document, keeping the findings about the placed character."""
    ids, names = {layer["id"] for layer in layers}, {layer["name"] for layer in layers}
    report = project.check(checks=list(checks))
    issues = [issue for issue in report.get("issues", [])
              if set(issue.get("layer_ids") or []) & ids or set(issue.get("layers") or []) & names]
    passed = not any(issue.get("severity") == "error" or issue.get("action") == "fix" for issue in issues)
    return {"checks": list(checks), "passed": passed, "issues": issues}
