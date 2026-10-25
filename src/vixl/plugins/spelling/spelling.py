"""The ``spelling`` check: words in drawn text that the dictionary does not know.

Text is read as drawn (after variables, per artboard). URLs, domains, emails, ``@handles``, ``#hex`` colours and
hashtags, numbers, words with digits and all-capital words of four letters or fewer are skipped. A word is known
when the dictionary for the document language has it (any case; a trailing possessive ``'s`` is ignored; each part
of a hyphenated word may be known on its own) or when the workspace allows it: brand.json ``words.allow``, the
values of brand.json ``facts`` and ``.vixl/dictionary.txt`` (one word or phrase per line, ``#`` comments).

The language is the form settings ``lang``, else the document ``lang`` (``accessibility``), else ``en``. English
is bundled (``data/en.txt.gz``, built from SCOWL; its header holds the source and licence). Another language
comes from the ``spelling-<lang>`` content pack (``vixl.packs``); without it the check reports one review
finding, ``dictionary-unavailable``, and never passes silently.
"""

from difflib import get_close_matches
from functools import lru_cache
import gzip
import io
from pathlib import Path
import re

from ...errors import require

DATA = Path(__file__).parent / "data"
BUNDLED = {"en": DATA / "en.txt.gz"}
MAX_FINDINGS = 50
MAX_SUGGESTIONS = 3
MAX_DICTIONARY_BYTES = 8 * 1024 * 1024
MAX_WORKSPACE_WORDS = 20000

SKIP = re.compile(
    r"(?i)\b(?:https?://|ftp://|www\.)\S+"           # URLs
    r"|[\w.+-]+@[\w-]+(?:\.[\w-]+)+"                  # emails
    r"|(?<![\w@])@\w+"                                # @handles
    r"|(?<![\w#])#\w+"                                # #hex colours and hashtags
    r"|\b(?:[\w-]+\.)+[a-z]{2,}\b(?:/\S*)?"           # bare domains (example.com/path)
)
TOKEN = re.compile(r"[\w'’-]+")
LETTERS = re.compile(r"[A-Za-zÀ-ÖØ-öø-ɏ]+(?:'[A-Za-zÀ-ÖØ-öø-ɏ]+)*")


def language(project):
    """The primary language subtag the document is checked in."""
    state = project.state
    tag = (state.get("form") or {}).get("lang") or (state.get("accessibility") or {}).get("lang") or "en"
    return tag.split("-")[0].lower()


def pack_name(lang):
    return f"spelling-{lang}"


def _read_words(path):
    with open(path, "rb") as f:
        data = f.read(MAX_DICTIONARY_BYTES + 1)
    if data[:2] == b"\x1f\x8b":
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
            data = stream.read(MAX_DICTIONARY_BYTES * 4 + 1)
    require(len(data) <= MAX_DICTIONARY_BYTES * 4, f"Spelling dictionary {Path(path).name} is too large",
            "resource_limit")
    text = data.decode("utf-8", errors="replace")
    return frozenset(line.strip().lower() for line in text.splitlines() if line.strip() and not line.startswith("#"))


@lru_cache(maxsize=4)
def _load(path, size, mtime):
    return _read_words(path)


def dictionary(lang):
    """(words, None) for ``lang``, or (None, message) when its dictionary is unavailable."""
    from ...errors import VixlError
    from ... import packs

    path = BUNDLED.get(lang)
    if path is None:
        name = pack_name(lang)
        if name not in packs.PACKS:
            return None, (f"Spelling dictionary unavailable for {lang!r}: Vixl bundles English only and no "
                          f"{name} content pack is published; check the copy by eye, or set the document lang to en")
        try:
            path = packs.path(name, download=packs.downloads_allowed())
        except VixlError as exc:
            return None, f"Spelling dictionary unavailable for {lang!r}: {exc}"
    stat = Path(path).stat()
    return _load(str(path), stat.st_size, stat.st_mtime_ns), None


@lru_cache(maxsize=4)
def _index(words):
    """{(first letter, length): [words]}: the candidates suggestions are drawn from."""
    buckets = {}
    for word in words:
        if word.isalpha():
            buckets.setdefault((word[0], len(word)), []).append(word)
    return buckets


def suggestions(word, words):
    """Up to three known words close to ``word`` (difflib over words of the same first letter and similar length)."""
    lower = word.lower()
    buckets = _index(words)
    candidates = [w for size in range(len(lower) - 2, len(lower) + 3) for w in buckets.get((lower[0], size), ())]
    found = get_close_matches(lower, candidates, n=MAX_SUGGESTIONS * 2, cutoff=0.75)
    # Swapped letters are the commonest typo: a candidate with the same letters ranks first.
    letters = sorted(lower)
    found = sorted(found, key=lambda w: sorted(w) != letters)[:MAX_SUGGESTIONS]
    if word[:1].isupper():
        found = [w.upper() if word.isupper() else w[:1].upper() + w[1:] for w in found]
    return found


def _workspace(project):
    workspace = getattr(project, "_workspace", None)
    if workspace is None and project.path:
        workspace = Path(project.path).parent
    return Path(workspace) if workspace else None


def _phrases_words(phrases):
    out = set()
    for phrase in phrases:
        out.add(phrase.strip().lower())
        out.update(token.lower() for token in LETTERS.findall(phrase.replace("’", "'")))
    return out


def allowed(project):
    """Words the workspace accepts: brand.json ``words.allow``, brand ``facts`` values and ``.vixl/dictionary.txt``."""
    from ...brand import for_project

    kit = for_project(project) or {}
    phrases = list((kit.get("words") or {}).get("allow", []))
    for spec in (kit.get("facts") or {}).values():
        if isinstance(spec, dict):
            phrases += [v for v in spec.get("values", []) if isinstance(v, str)]
            if isinstance(spec.get("value"), str):
                phrases.append(spec["value"])
    workspace = _workspace(project)
    path = workspace / ".vixl" / "dictionary.txt" if workspace else None
    if path is not None and path.is_file() and path.resolve().is_relative_to(workspace.resolve()):
        from ...assets import read_bounded

        text = read_bounded(path, 2 * 1024 * 1024).decode("utf-8", errors="replace")
        lines = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
        phrases += lines[:MAX_WORKSPACE_WORDS]
    return _phrases_words(phrases)


def _known(token, words, extra):
    lower = token.lower()
    if lower in words or lower in extra:
        return True
    for suffix in ("'s", "'"):
        stem = lower[: -len(suffix)]
        if lower.endswith(suffix) and stem and (stem in words or stem in extra):
            return True
    return False


def unknown(text, words, extra):
    """[word] in ``text`` the dictionary and allow list do not know, in order, each once."""
    text = SKIP.sub(" ", text.replace("’", "'"))
    found = []
    for raw in TOKEN.findall(text):
        token = raw.strip("'-")
        if not token or any(ch.isdigit() or ch == "_" for ch in token):
            continue
        if _known(token, words, extra):
            continue
        parts = [part.strip("'") for part in token.split("-") if part.strip("'")]
        for part in parts:
            if len(part) < 2 or not LETTERS.fullmatch(part):
                continue  # Single letters and words in other scripts are not checked.
            if part.isupper() and len(part) <= 4:
                continue  # Acronyms: USA, FAQ, CEO.
            if not _known(part, words, extra) and part not in found:
                found.append(part)
    return found


def spell(project, texts):
    """The ``spell`` hook: unknown words in {layer id: text}, with suggestions."""
    lang = language(project)
    words, message = dictionary(lang)
    if words is None:
        return {"lang": lang, "available": False, "message": message, "words": []}
    extra = allowed(project)
    found = []
    for layer, text in texts.items():
        for word in unknown(text, words, extra):
            found.append({"layer": layer, "word": word, "suggestions": suggestions(word, words)})
    return {"lang": lang, "available": True, "words": found}


def check(checks, candidate, resolved, issue, **context):
    if "spelling" not in checks:
        return
    from ...copy_checks import shown_layers

    layers = [resolved[layer["id"]] for layer in shown_layers(candidate, "*", "text") if layer["id"] in resolved]
    texts = {layer["id"]: layer.get("text", "") for layer in layers if layer.get("text", "").strip()}
    if not texts:
        return
    result = spell(candidate, texts)
    if not result["available"]:
        issue("spelling", "warning", result["message"] + ". The spelling check did not run", code="dictionary-unavailable",
              action="review", lang=result["lang"], pack=pack_name(result["lang"]))
        return
    by_id = {layer["id"]: layer for layer in layers}
    for item in result["words"][:MAX_FINDINGS]:
        hint = f" (did you mean {', '.join(repr(s) for s in item['suggestions'])}?)" if item["suggestions"] else ""
        issue("spelling", "warning", f"{by_id[item['layer']]['name']!r} has {item['word']!r}, which the "
              f"{result['lang']} dictionary does not know{hint}; correct it, or add it to brand.json words.allow or "
              ".vixl/dictionary.txt", [by_id[item["layer"]]], code="unknown-word", action="review",
              word=item["word"], suggestions=item["suggestions"], lang=result["lang"])
    if len(result["words"]) > MAX_FINDINGS:
        issue("spelling", "warning", f"{len(result['words']) - MAX_FINDINGS} more unknown words are not listed",
              code="unknown-word-more", action="review", omitted=len(result["words"]) - MAX_FINDINGS)
