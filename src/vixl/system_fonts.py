"""The fonts installed on this machine, found the way other programs find them, and matched by name.

Sources, merged and deduplicated by file (every face of a collection is indexed):

- Linux and BSD: fontconfig (``fc-list``), which honours the user's ``fonts.conf`` directories; when it is not
  installed, ``/usr/share/fonts``, ``/usr/local/share/fonts``, ``~/.local/share/fonts``, ``~/.fonts`` and
  ``$XDG_DATA_DIRS/fonts``.
- Windows: the font registrations under ``SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Fonts`` (machine and
  per-user), plus ``%WINDIR%\\Fonts`` and ``%LOCALAPPDATA%\\Microsoft\\Windows\\Fonts``.
- macOS: ``/System/Library/Fonts``, ``/Library/Fonts`` and ``~/Library/Fonts``.
- ``VIXL_FONT_DIRS``: more directories (``os.pathsep``-separated), searched first.

``VIXL_SYSTEM_FONTS=off`` turns installed fonts off, ``extra`` keeps only ``VIXL_FONT_DIRS``. The bundled faces are
always indexed first, so their family names resolve to the same file on every machine.

Sources are probed once per process (again on a miss after ``PROBE_TTL`` seconds) and each file's faces are kept
in an on-disk index (``VIXL_SYSTEM_FONT_INDEX``, default ``~/.cache/vixl/system-fonts.json``) keyed by the file's
size and modification time, and directory walks by the directories' modification times, so a process reads only
the fonts that changed. Only ``.ttf``, ``.otf``, ``.ttc`` and ``.otc`` files from those fixed sources are read,
never a path a caller passes.
"""

import difflib
from functools import lru_cache
import hashlib
from io import BytesIO
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time

from .errors import VixlError

EXTENSIONS = (".ttf", ".otf", ".ttc", ".otc")
MAX_FILES = 6000  # font files indexed in all
MAX_FILE_BYTES = 64 * 1024 * 1024  # larger files are skipped (the largest CJK collections are ~40 MB)
MAX_FACES = 64  # faces per collection and named instances per variable font
MAX_DEPTH = 8
MAX_INDEX_BYTES = 32 * 1024 * 1024
PROBE_TTL = 30.0
INDEX_VERSION = 1
OFF = ("off", "0", "false", "no", "none")
DATA = Path(__file__).parent / "data"

WEIGHTS = {"thin": 100, "hairline": 100, "extralight": 200, "ultralight": 200, "light": 300, "regular": 400,
           "normal": 400, "book": 400, "roman": 400, "plain": 400, "medium": 500, "semibold": 600, "demibold": 600,
           "demi": 600, "bold": 700, "extrabold": 800, "ultrabold": 800, "heavy": 900, "black": 900,
           "extrablack": 950, "ultrablack": 950}
_STYLE = re.compile(r"(?P<weight>\d{3}|" + "|".join(sorted(WEIGHTS, key=len, reverse=True))
                    + r")?(?P<italic>italic|oblique|it)?")

_lock = threading.RLock()
_memo = {}


def mode():
    """``on`` (the default), ``extra`` (only ``VIXL_FONT_DIRS``) or ``off``."""
    value = os.environ.get("VIXL_SYSTEM_FONTS", "").strip().lower()
    if value in OFF:
        return "off"
    return "extra" if value == "extra" else "on"


def norm(text):
    """A name compared case-, space-, hyphen- and underscore-insensitively."""
    return re.sub(r"[\s_\-]+", "", str(text).casefold())


def extra_dirs():
    return [Path(item).expanduser() for item in os.environ.get("VIXL_FONT_DIRS", "").split(os.pathsep) if item.strip()]


def platform_dirs():
    """The standard font directories of this platform (the folder scan)."""
    home = Path.home()
    if sys.platform.startswith("win"):
        dirs = [Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"]
        if os.environ.get("LOCALAPPDATA"):
            dirs.append(Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "Windows" / "Fonts")
        return dirs
    if sys.platform == "darwin":
        return [Path("/System/Library/Fonts"), Path("/Library/Fonts"), home / "Library" / "Fonts"]
    data = os.environ.get("XDG_DATA_DIRS", "").split(os.pathsep)
    return [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), home / ".local" / "share" / "fonts",
            home / ".fonts", *(Path(item) / "fonts" for item in data if item.strip())]


def fontconfig_files():
    """The font files fontconfig lists, or None when fontconfig is not installed (then the folders are scanned)."""
    if sys.platform.startswith("win") or sys.platform == "darwin":
        return None
    program = shutil.which("fc-list")
    if program is None:
        return None
    try:
        done = subprocess.run([program, "--format", "%{file}\\n"], capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return [line for line in done.stdout.decode("utf-8", "replace").splitlines() if line.strip()]


def registry_files():
    """Windows: the font files registered for the machine and for the current user, or None elsewhere."""
    if not sys.platform.startswith("win"):
        return None
    import winreg

    key = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
    fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts"
    files = []
    for hive, base in ((winreg.HKEY_LOCAL_MACHINE, fonts), (winreg.HKEY_CURRENT_USER, local)):
        try:
            with winreg.OpenKey(hive, key) as handle:
                for number in range(winreg.QueryInfoKey(handle)[1]):
                    value = winreg.EnumValue(handle, number)[1]
                    if isinstance(value, str) and value:
                        path = Path(value)
                        files.append(str(path if path.is_absolute() else base / path))
        except OSError:
            continue
    return files


def _index_path():
    value = os.environ.get("VIXL_SYSTEM_FONT_INDEX", "").strip()
    if value.lower() in OFF:
        return None
    return Path(value or "~/.cache/vixl/system-fonts.json").expanduser()


def _load_index(path):
    try:
        if path is None or path.stat().st_size > MAX_INDEX_BYTES:
            return {}
        index = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return index if isinstance(index, dict) and index.get("version") == INDEX_VERSION else {}


def _save_index(path, index):
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(index, separators=(",", ":")), encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        pass  # A read-only cache only costs re-reading the fonts next time.


def _mtime(path):
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return None


def _walk(root, cached):
    """``(dirs, files)`` under ``root``: every directory with its modification time and the font files. A walk
    whose directories are all unchanged is reused from ``cached``."""
    if cached and cached.get("dirs") and all(_mtime(d) == m for d, m in cached["dirs"].items()):
        return cached
    dirs, files, seen = {}, [], set()

    def visit(folder, depth):
        if depth > MAX_DEPTH or len(files) >= MAX_FILES:
            return
        try:
            real = os.path.realpath(folder)
            if real in seen:
                return
            seen.add(real)
            dirs[folder] = os.stat(folder).st_mtime_ns
            entries = sorted(os.scandir(folder), key=lambda entry: entry.name)
        except OSError:
            return
        for entry in entries:
            try:
                if entry.is_dir():
                    visit(entry.path, depth + 1)
                elif entry.name.lower().endswith(EXTENSIONS) and entry.is_file():
                    files.append(entry.path)
            except OSError:
                continue

    if os.path.isdir(root):
        visit(str(root), 0)
    return {"dirs": dirs, "files": files[:MAX_FILES]}


def _weight(value):
    value = int(value or 400)
    if 1 <= value <= 9:  # Some old fonts use the 1–9 scale.
        value *= 100
    return max(1, min(1000, value))


def _describe(font, index):
    """The faces one parsed font file (or collection member) offers: one, or its named instances."""
    from .fonts import license_from_names, permission

    if not any(table in font for table in ("glyf", "CFF ", "CFF2")):
        return []  # bitmap-only faces cannot be outlined or embedded
    names = font["name"]
    family = names.getDebugName(16) or names.getDebugName(1)
    if not family:
        return []
    style = names.getDebugName(17) or names.getDebugName(2) or "Regular"
    os2 = font["OS/2"] if "OS/2" in font else None
    weight = _weight(getattr(os2, "usWeightClass", 400))
    slanted = bool(os2 and os2.fsSelection & 1) or bool(font["head"].macStyle & 2)
    base = {"family": family, "style": style, "weight": weight,
            "italic": slanted or bool(re.search(r"italic|oblique", style, re.I)),
            "postscript": names.getDebugName(6) or "", "full": names.getDebugName(4) or f"{family} {style}",
            "legacy": names.getDebugName(1) or family, "index": index,
            "embedding": permission(getattr(os2, "fsType", 0)) if os2 else "unknown"}
    found = license_from_names(names)
    if found:
        base["license"] = found
    if "fvar" not in font or not font["fvar"].instances:
        return [base]
    faces, prefix = [], names.getDebugName(25) or (base["postscript"].split("-")[0] or re.sub(r"\s", "", family))
    for instance in font["fvar"].instances[:MAX_FACES]:
        coords = {axis: float(value) for axis, value in instance.coordinates.items()}
        name = names.getDebugName(instance.subfamilyNameID) or style
        ps = names.getDebugName(instance.postscriptNameID) if instance.postscriptNameID not in (None, 0xFFFF) else None
        faces.append({**base, "style": name, "weight": _weight(round(coords.get("wght", weight))),
                      "italic": base["italic"] or coords.get("ital", 0) >= 0.5 or coords.get("slnt", 0) < 0
                      or bool(re.search(r"italic|oblique", name, re.I)),
                      "postscript": ps or f"{prefix}-{re.sub(r'[^A-Za-z0-9]', '', name)}",
                      "full": f"{family} {name}", "coords": coords})
    return faces


def faces_of(path):
    """Every face of one font file (all members of a collection); [] when it cannot be read."""
    log = logging.getLogger("fontTools")
    level = log.level
    log.setLevel(logging.ERROR)  # odd but harmless metadata (old timestamps …) in host fonts is not news
    try:
        return _faces_of(path)
    finally:
        log.setLevel(level)


def _faces_of(path):
    from fontTools.ttLib import TTCollection, TTFont

    try:
        if os.path.getsize(path) > MAX_FILE_BYTES:
            return []
        if str(path).lower().endswith((".ttc", ".otc")):
            collection = TTCollection(str(path), lazy=True)
            try:
                return [face for number, font in enumerate(collection.fonts[:MAX_FACES])
                        for face in _describe(font, number)]
            finally:
                collection.close()
        font = TTFont(str(path), lazy=True)
        try:
            return _describe(font, 0)
        finally:
            font.close()
    except Exception:  # noqa: BLE001 - an unreadable or malformed file is skipped
        return []


def _candidates(cached_walks):
    """``[(file, source)]`` in priority order, and the walks to store."""
    files, walks = [], {}
    for root in extra_dirs():
        walk = walks[str(root)] = _walk(str(root), cached_walks.get(str(root)))
        files += [(path, "extra") for path in walk["files"]]
    if mode() == "on":
        listed = fontconfig_files()
        if listed is None:
            listed = []
            for root in platform_dirs():
                walk = walks[str(root)] = _walk(str(root), cached_walks.get(str(root)))
                listed += walk["files"]
            source = "folder"
        else:
            source = "fontconfig"
        files += [(path, source) for path in listed]
        registered = registry_files()
        if registered:
            files += [(path, "registry") for path in registered]
            for root in platform_dirs():
                walk = walks[str(root)] = _walk(str(root), cached_walks.get(str(root)))
                files += [(path, "folder") for path in walk["files"]]
    return files, walks


def _bundled():
    from .text import BUNDLED_FONTS

    return [{**face, "file": str(DATA / name), "source": "bundled", "bundled": name}
            for name in BUNDLED_FONTS for face in faces_of(DATA / name)]


@lru_cache(maxsize=1)
def bundled_faces():
    return tuple(_bundled())


def _scan():
    path = _index_path()
    stored = _load_index(path)
    known = stored.get("files", {})
    candidates, walks = _candidates(stored.get("walks", {}))
    faces, files, seen, changed = list(bundled_faces()), {}, set(), False
    for file, source in candidates:
        if len(seen) >= MAX_FILES:
            break
        if not file.lower().endswith(EXTENSIONS):
            continue
        try:
            real = os.path.normcase(os.path.realpath(file))
            if real in seen:
                continue
            stat = os.stat(real)
        except OSError:
            continue
        seen.add(real)
        if stat.st_size > MAX_FILE_BYTES:
            continue
        entry = known.get(real)
        if not (entry and entry.get("m") == stat.st_mtime_ns and entry.get("s") == stat.st_size):
            entry = {"m": stat.st_mtime_ns, "s": stat.st_size, "faces": faces_of(real)}
            changed = True
        files[real] = entry
        faces += [{**face, "file": real, "source": source} for face in entry["faces"]]
    if changed or set(files) != set(known) or walks != stored.get("walks", {}):
        _save_index(path, {"version": INDEX_VERSION, "files": files, "walks": walks})
    return faces


def _settings():
    return mode(), os.environ.get("VIXL_FONT_DIRS", ""), str(_index_path())


def faces(refresh=False):
    """Every installed face (the bundled ones first), from the per-process memo."""
    if mode() == "off":
        return bundled_faces()
    with _lock:
        key = _settings()
        if refresh or _memo.get("key") != key:
            _memo.update(key=key, faces=_scan(), at=time.monotonic())
        return _memo["faces"]


def refresh():
    """Probe the sources again (a font was installed or removed while this process runs)."""
    _clear()
    return faces(refresh=True)


def _clear():
    with _lock:
        _memo.clear()
    lookup.cache_clear()


def _tables():
    """``(by PostScript name, by full name, by typographic family, by legacy family)`` for the current faces."""
    with _lock:
        current = faces()
        memo = _memo.get("tables")
        if memo is not None and memo[0] is current:
            return memo[1]
        postscript, full, family, legacy = {}, {}, {}, {}
        for face in current:
            if face["postscript"]:
                postscript.setdefault(norm(face["postscript"]), face)
            full.setdefault(norm(face["full"]), face)
            family.setdefault(norm(face["family"]), []).append(face)
            if norm(face["legacy"]) != norm(face["family"]):
                legacy.setdefault(norm(face["legacy"]), []).append(face)
        built = postscript, full, family, legacy
        _memo["tables"] = (current, built)
        return built


def _weight_key(weight, wanted):
    """CSS font matching's order of weights for ``wanted``."""
    if 400 <= wanted <= 500:
        if wanted <= weight <= 500:
            return 0, weight - wanted
        return (1, wanted - weight) if weight < wanted else (2, weight - wanted)
    if wanted < 400:
        return (0, wanted - weight) if weight <= wanted else (1, weight - wanted)
    return (0, weight - wanted) if weight >= wanted else (1, wanted - weight)


def choose(options, weight=400, italic=False):
    """The face of one family that CSS font matching picks for ``weight`` and slope."""
    sloped = [face for face in options if face["italic"] == bool(italic)] or list(options)
    return min(sloped, key=lambda face: _weight_key(face["weight"], weight)) if sloped else None


def parse_style(text):
    """``(weight, italic)`` for a style such as ``Bold Italic``, ``SemiBold``, ``700`` or ``Italic``; None when
    it is not one."""
    found = _STYLE.fullmatch(norm(text))
    if not found or not (found["weight"] or found["italic"]):
        return None
    weight = found["weight"]
    return (int(weight) if weight and weight.isdigit() else WEIGHTS.get(weight, 400)), bool(found["italic"])


@lru_cache(maxsize=256)
def _lookup(key, weight, italic, generation):
    postscript, full, family, legacy = _tables()
    if weight is None and italic is None:
        if key in postscript:
            return postscript[key]
        if key in full:
            return full[key]
    for table in (family, legacy):
        if key in table:
            return choose(table[key], 400 if weight is None else weight, bool(italic))
        for name in sorted((name for name in table if key.startswith(name) and name != key), key=len, reverse=True):
            rest = key[len(name):]
            exact = [face for face in table[name] if norm(face["style"]) == rest]
            if exact and weight is None and italic is None:
                return exact[0]
            style = parse_style(rest)
            if style:
                return choose(table[name], style[0] if weight is None else weight,
                              style[1] if italic is None else italic)
    if key.endswith(tuple(norm(ext) for ext in EXTENSIONS)):
        for face in faces():
            if face["source"] != "bundled" and norm(os.path.basename(face["file"])) == key and face["index"] == 0:
                return face
    return None


def lookup(name, weight=None, italic=None):
    """The installed face a font name means, or None: a PostScript name (``Georgia-BoldItalic``), a full name
    (``Georgia Bold Italic``), a family (``Georgia``, at ``weight``/``italic`` when given, else regular), a
    family plus a style (``Inter SemiBold``, ``Inter 600 Italic``) or a font file name (``georgia.ttf``), all
    compared ignoring case, spaces, hyphens and underscores. Within a family the nearest weight wins, as in CSS."""
    if not isinstance(name, str) or not name.strip() or len(name) > 300 or "/" in name or "\\" in name:
        return None
    found = _lookup(norm(name), weight, italic, _generation())
    if found is None and mode() != "off":
        with _lock:
            stale = time.monotonic() - _memo.get("at", 0) > PROBE_TTL
        if stale:  # Installed since the last probe?
            _clear()
            faces(refresh=True)
            found = _lookup(norm(name), weight, italic, _generation())
    return found


lookup.cache_clear = _lookup.cache_clear


def _generation():
    with _lock:
        current = faces()
        return id(current), _settings()


def family_faces(family):
    """Every face of an installed family (by its typographic or legacy family name)."""
    tables = _tables()
    return list(tables[2].get(norm(family)) or tables[3].get(norm(family)) or [])


def suggest(name, count=3):
    """Installed family names close to ``name`` (for an unknown-font error)."""
    if not isinstance(name, str) or mode() == "off":
        return []
    names = {}
    for face in faces():
        if face["source"] != "bundled":
            names.setdefault(face["family"].casefold(), face["family"])
    words = re.split(r"[\s_\-]+", name)
    keys = {name.casefold(), *(" ".join(words[:n]).casefold() for n in range(1, len(words)))}
    close = []
    for key in sorted(keys, key=len, reverse=True):
        for match in difflib.get_close_matches(key, list(names), count, 0.6):
            if names[match] not in close:
                close.append(names[match])
    return close[:count]


def _style_row(face, paths=True):
    row = {key: face[key] for key in ("style", "weight", "italic", "postscript", "file", "index", "embedding", "source")
           if paths or key != "file"}
    if face.get("license"):
        row["license"] = face["license"]
    if face.get("coords"):
        row["variable"] = True
    return row


def families(query=None, *, limit=None, compact=False, include_bundled=False, paths=True):
    """Installed families, each with its styles (style, weight, italic, PostScript name, file, collection index,
    embedding permission, source and licence when the font names one), sorted by family name. ``query`` keeps the
    families whose family, style or PostScript names contain it; ``limit`` caps the families (``truncated`` says so);
    ``compact`` lists only the style names; ``paths=False`` leaves out the files (for remote clients)."""
    grouped = {}
    for face in faces():
        if face["source"] == "bundled" and not include_bundled:
            continue
        styles = grouped.setdefault(face["family"], {})
        styles.setdefault((face["italic"], face["weight"], face["style"]), face)
    wanted = norm(query) if query else ""
    rows = []
    for family in sorted(grouped, key=str.casefold):
        styles = [grouped[family][key] for key in sorted(grouped[family])]
        if wanted and not any(wanted in norm(text) for face in styles
                              for text in (family, f"{family} {face['style']}", face["postscript"])):
            continue
        rows.append({"family": family, "styles": [face["style"] for face in styles] if compact
                     else [_style_row(face, paths) for face in styles]})
    total = len(rows)
    if limit is not None and total > limit:
        rows = rows[:limit]
    result = {"families": rows, "count": total, "mode": mode()}
    if len(rows) < total:
        result["truncated"] = f"showing {len(rows)} of {total} families; pass a query to narrow them"
    return result


def installed_family(family):
    """True when ``family`` is installed on this machine (not only bundled)."""
    return mode() != "off" and any(face["source"] != "bundled" for face in family_faces(family))


@lru_cache(maxsize=8)
def _face_bytes(file, index, coords, mtime, size):
    from fontTools.ttLib import TTFont

    raw = Path(file).read_bytes()
    if len(raw) > MAX_FILE_BYTES:
        raise VixlError("resource_limit", f"Font file {file} exceeds {MAX_FILE_BYTES} bytes")
    if not coords and not file.lower().endswith((".ttc", ".otc")):
        return raw
    font = TTFont(BytesIO(raw), fontNumber=index)
    if coords:
        from fontTools.varLib.instancer import instantiateVariableFont

        try:
            font = instantiateVariableFont(font, dict(coords), updateFontNames=True)
        except Exception:  # noqa: BLE001 - fonts without a usable STAT table keep their names
            font = instantiateVariableFont(TTFont(BytesIO(raw), fontNumber=index), dict(coords))
    out = BytesIO()
    font.save(out)
    return out.getvalue()


def face_bytes(face):
    """One face as a standalone font file: a collection member extracted, a variable font's named instance
    made static."""
    stat = os.stat(face["file"])
    coords = tuple(sorted((face.get("coords") or {}).items()))
    return _face_bytes(face["file"], face["index"], coords, stat.st_mtime_ns, stat.st_size)


RESTRICTED = ("restricted", "preview-print")


def describe(face):
    """The report row for one installed face."""
    row = {key: face[key] for key in ("family", "style", "weight", "italic", "postscript", "embedding")}
    if face.get("license"):
        row["license"] = face["license"]
    return row


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


def _family_slug(face):
    return _slug(face["family"]) or f"font-{hashlib.sha256(face['family'].encode()).hexdigest()[:8]}"


def _register_name(face, weight, italic, base):
    weight = max(100, min(900, int(round((face["weight"] if weight is None else weight) / 100) * 100)))
    slanted = face["italic"] if italic is None else italic
    return f"{base}-{weight}{'-italic' if slanted else ''}"


def _register(project, face, asset, weight=None, italic=None, prefix=None):
    """Register ``asset`` under ``<family>-<weight>[-italic]`` (the name font-install gives, which rich-text
    bold and italic look siblings up by) unless that name is taken by another font; returns the name or None."""
    fonts = project.state.setdefault("fonts", {})
    family = _family_slug(face)
    for base in ([prefix] if prefix else [family, f"{family}-local"]):
        name = _register_name(face, weight, italic, base)
        if len(name) <= 100 and fonts.get(name, asset) == asset:
            fonts[name] = asset
            return name
    return None


def embed(project, name, weight=None, italic=None):
    """Resolve ``name`` to an installed face and embed it in ``project``: returns the font value a text layer stores
    (a bundled file name, or the ``fonts/<sha256>.ttf`` asset, registered as ``<family>-<weight>``), or None when
    no installed face has that name. A face whose licence restricts embedding is still embedded, with a warning."""
    face = lookup(name, weight, italic)
    if face is None:
        return None
    if face["source"] == "bundled":
        return face["bundled"]
    from .fonts import validate_font
    from .notices import note, warn
    from .selectors import record

    data = face_bytes(face)
    if len(data) > project.limits.max_asset_bytes:
        raise VixlError("resource_limit", f"The installed font {face['full']!r} is larger than the asset limit")
    validate_font(data)
    asset = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
    project.assets[asset] = data
    registered = _register(project, face, asset)
    record(project, "installed_fonts", {"requested": name, **describe(face), "asset": asset,
                                        **({"registered": registered} if registered else {})})
    note(project, f"font {name!r} is the installed face {face['family']} {face['style']} ({face['postscript']}); "
                  "its file is embedded in the document, so it renders where the font is not installed")
    if face["embedding"] in RESTRICTED:
        warn(project, f"the installed font {face['family']} {face['style']} has the embedding permission "
                      f"{face['embedding']!r}: its licence may not allow embedding it in a document you share; "
                      "check the licence, or choose an open-licensed family (vixl_reference('fonts'))")
    return asset


def render_data(name):
    """Font bytes for a stored font name no other source resolves (an older document's bare family name),
    without changing the document; None when no installed face has it."""
    face = lookup(name)
    if face is None:
        return None
    if face["source"] == "bundled":
        from .text import file_bytes

        return file_bytes(face["file"])
    return face_bytes(face)


def _origin(project, font):
    """The installed face whose bytes are ``font``'s asset, or None."""
    from .text import font_sha256, font_style

    data = project.assets.get(font)
    if not data:
        return None
    family, weight, italic = font_style(data)
    digest = font_sha256(data)
    for face in family_faces(family):
        if face["source"] != "bundled" and face["weight"] == weight and face["italic"] == italic:
            try:
                if hashlib.sha256(face_bytes(face)).hexdigest() == digest:
                    return face
            except (OSError, VixlError):
                continue
    return None


def add_variants(project, layer):
    """Embed the installed bold and italic faces a rich-text layer's styled spans need when their font is an
    installed face, registered so rich text draws them instead of synthesizing bold or slanting the glyphs."""
    rich = layer.get("rich")
    if mode() == "off" or not rich:
        return
    from .richtext import _registered_name, variant_font

    wanted = {(span.get("font", layer.get("font")), bool(span.get("bold")), bool(span.get("italic")))
              for span in rich.get("spans", []) if span.get("bold") or span.get("italic")}
    for font, bold, italic in sorted(wanted, key=str):
        if not isinstance(font, str) or font not in project.assets or variant_font(project, font, bold, italic, rich)[1:] == (False, False):
            continue
        name = _registered_name(project.state, font)
        face = _origin(project, font) if name else None
        # Only a face that was chosen from this machine by name (registered as embed registers it); a font
        # imported or installed some other way keeps its own variants, whatever this machine has.
        match = re.fullmatch(r"(.+)-(\d{3})(-italic)?", name or "")
        if face is None or not match or name != _register_name(face, None, None, match[1]) or match[1] not in (
                _family_slug(face), f"{_family_slug(face)}-local"):
            continue
        prefix, base = match[1], int(match[2])
        options = family_faces(face["family"])
        if bold:
            heavier = [item for item in options if item["weight"] > face["weight"]]
            chosen = choose(heavier, max(700, face["weight"] + 100), italic or face["italic"]) if heavier else None
            target = chosen and round(chosen["weight"] / 100) * 100
            if not chosen or target not in (600, 700, 800, 900):
                continue
        else:
            chosen = choose(options, face["weight"], True)
            target = base
            if not chosen or not chosen["italic"]:
                continue
        slanted = chosen["italic"] and (italic or face["italic"])
        if (bold and italic and not chosen["italic"]) or chosen is face:
            continue
        data = face_bytes(chosen)
        asset = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
        project.assets[asset] = data
        if _register(project, chosen, asset, weight=target, italic=slanted, prefix=prefix):
            from .selectors import record

            record(project, "installed_fonts", {"requested": f"{prefix} {'bold ' if bold else ''}"
                                                f"{'italic' if italic else ''}".strip(),
                                                **describe(chosen), "asset": asset})


# Installed families with the same design as a catalog script face, under the names operating systems ship them.
SCRIPT_ALIASES = {f"Noto Sans {region}": (f"Noto Sans CJK {region}", f"Source Han Sans {region}")
                  for region in ("SC", "TC", "JP", "KR")}


def script_faces(families):
    """Font bytes of the regular face of each of ``families`` (catalog faces for scripts the bundled fonts lack,
    such as Noto Sans SC) installed on this machine, or of the same design under its system name (Noto Sans CJK SC);
    ``typefaces.local_script_faces`` draws from them as it does from the font cache. Unreadable faces are skipped."""
    if mode() == "off":
        return []
    found = []
    for family in families:
        for name in (family, *SCRIPT_ALIASES.get(family, ())):
            options = [face for face in family_faces(name) if face["source"] != "bundled"]
            face = choose(options, 400, False) if options else None
            if face is None:
                continue
            try:
                found.append(face_bytes(face))
            except Exception:  # noqa: BLE001 - a damaged installed face is skipped
                continue
            break
    return found
