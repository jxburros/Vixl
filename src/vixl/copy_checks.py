"""Checks that read the words: the ``text`` suite rule, the ``placeholders`` design check and the brand word lists.

Text is measured as drawn, after variable substitution, so an artboard or campaign row is checked with its own copy.
"""

import re

from .errors import require

MAX_PATTERN = 1000
MAX_PHRASES = 100
MAX_ALLOWED = 5000
CASES = ("sensitive", "insensitive")

# Leftover template copy. Upper-case markers only, so ordinary words ("todo list") are not flagged.
BUILTIN_PLACEHOLDERS = (
    ("lorem ipsum", r"(?i)\blorem\s+ipsum\b|\bdolor\s+sit\s+amet\b|\bconsectetur\s+adipiscing\b"),
    ("marker", r"\b(?:TODO|TBD|TBC|FIXME|XXX+)\b"),
    ("slot text", r"(?i)\b(?:your|insert|add|enter|place)\s+(?:[\w-]+\s+){0,3}here\b"),
    ("slot text", r"(?i)\b(?:headline|heading|title|subtitle|subheading|tagline|body\s+copy|copy|caption|text|name|"
                  r"logo|image|photo|button(?:\s+text)?|cta|call\s+to\s+action|price|date)\s+(?:goes\s+)?here\b"),
    ("slot text", r"(?i)\b(?:sample|placeholder|dummy)\s+(?:text|copy|headline|title)\b"),
)
# ``${name}`` left in drawn text (a variable whose value is itself a placeholder, or text pasted from elsewhere).
LEFTOVER_FIELD = re.compile(r"\$\{[^{}\n]{0,200}\}")
# Another tool's merge-field syntax; not Vixl's, so it is only worth a look.
FOREIGN_FIELD = re.compile(r"\{\{[^{}\n]{0,200}\}\}|\[\[[^\[\]\n]{1,80}\]\]|<<[^<>\n]{1,80}>>")


def phrases(value, name, where):
    """A phrase or list of phrases as a list."""
    items = [value] if isinstance(value, str) else value
    require(isinstance(items, list) and 0 < len(items) <= MAX_PHRASES
            and all(isinstance(item, str) and 0 < len(item) <= MAX_PATTERN for item in items),
            f"{where}: {name} is a phrase or a list of at most {MAX_PHRASES} phrases", field=name)
    return items


def compile_patterns(value, name, where, flags=0):
    compiled = []
    for item in phrases(value, name, where):
        try:
            compiled.append(re.compile(item, flags))
        except re.error as exc:
            from .errors import VixlError

            raise VixlError("invalid_suite", f"{where}: {name} {item!r} is not a valid regular expression ({exc})",
                            field=name) from None
    return compiled


def word_pattern(phrase):
    """A literal word or phrase matched as whole words, ignoring case and spacing."""
    words = [re.escape(word) for word in phrase.split()]
    return re.compile(r"(?<![\w-])" + r"\s+".join(words) + r"(?![\w-])", re.IGNORECASE)


def allowed_spans(text, patterns):
    """Character spans of ``text`` covered by allowed words or phrases (brand.json ``words.allow``)."""
    return [match.span() for pattern in patterns for match in pattern.finditer(text)]


def first_match(pattern, text, spans=()):
    """The first match of ``pattern`` in ``text`` that is not inside one of ``spans``, or None."""
    for match in pattern.finditer(text):
        if not any(start <= match.start() and match.end() <= end for start, end in spans):
            return match
    return None


def count_words(text):
    return len(text.split())


def count_characters(text):
    """Characters as read: line breaks do not count."""
    return len(text.replace("\r", "").replace("\n", ""))


def shown_layers(project, target="*", layer_type=None):
    """Layers matching ``target`` (a name, glob, ID or ``group:NAME``) that are drawn: visible with
    nonzero opacity, as are all their parents. An unmatched name selects nothing."""
    from .errors import VixlError
    from .spatial import _select

    index = {layer["id"]: layer for layer in project.state["layers"]}

    def shown(layer):
        while layer:
            if not layer["visible"] or layer["opacity"] <= 0:
                return False
            layer = index.get(layer.get("parent"))
        return True

    try:
        chosen = _select(project, target)
    except VixlError:
        chosen = []
    return [layer for layer in chosen if shown(layer) and (layer_type is None or layer["type"] == layer_type)]


def drawn_text(project, layers):
    """{layer id: the text it draws} for text layers, after variables, character styles and symbols resolve."""
    from .render import resolved_layers

    wanted = {layer["id"] for layer in layers if layer["type"] == "text"}
    return {item["id"]: item.get("text", "") for item in resolved_layers(project) if item["id"] in wanted}


# --- the ``text`` suite rule -------------------------------------------------------------------------------------

TEXT_FIELDS = {"target", "pattern", "contains", "forbid", "min_characters", "max_characters", "min_words",
               "max_words", "case", "brand", "spelling"}


def validate_text_rule(rule, where):
    from .model import finite

    case = rule.get("case", "sensitive")
    require(case in CASES, f"{where}: case is sensitive or insensitive", field="case")
    flags = re.IGNORECASE if case == "insensitive" else 0
    for name in ("pattern", "forbid"):
        if name in rule:
            compile_patterns(rule[name], name, where, flags)
    if "contains" in rule:
        phrases(rule["contains"], "contains", where)
    for name in ("min_characters", "max_characters", "min_words", "max_words"):
        if name in rule:
            require(type(rule[name]) is int, f"{where}: {name} is a whole number", field=name)
            finite(rule[name], f"{where}: {name}", 0, 1e7)
    require(isinstance(rule.get("target", "*"), str), f"{where}: target is a layer name, glob or group:NAME",
            field="target")
    for name in ("brand", "spelling"):
        require(type(rule.get(name, False)) is bool, f"{where}: {name} is true or false", field=name)
    require(any(name in rule for name in TEXT_FIELDS - {"target", "case"}),
            f"{where}: set pattern, contains, forbid, brand, spelling or a character/word limit", field="pattern")


def brand_forbidden(project):
    from .brand import for_project

    return list((for_project(project).get("words") or {}).get("forbid", []))


def brand_allowed(kit):
    """brand.json ``words.allow`` as whole-word patterns."""
    return [word_pattern(phrase) for phrase in (kit.get("words") or {}).get("allow", [])]


def spelling_findings(project, texts):
    """Unknown words in ``texts`` ({layer id: drawn text}) through the ``spell`` plugin hook (the spelling
    plugin): ``{"lang", "words": [{"layer", "word", "suggestions"}]}``. A missing dictionary raises
    ``pack_unavailable``, so a suite rule reads it as needs_review, never as a pass."""
    from .errors import VixlError
    from .plugins import first

    result = first("spell", project, texts)
    if result is None:
        raise VixlError("unavailable", "Spelling needs the spelling plugin, which is not registered")
    if not result.get("available", True):
        raise VixlError("pack_unavailable", result["message"])
    return result


def text_rule(project, rule):
    """(passed, detail) for a ``text`` rule: limits and ``pattern`` hold for each selected text layer,
    ``forbid`` matches none of them, and every ``contains`` phrase appears somewhere in their combined copy."""
    flags = re.IGNORECASE if rule.get("case", "sensitive") == "insensitive" else 0
    target = rule.get("target", "*")
    layers = shown_layers(project, target, "text")
    if not layers and target != "*" and not any(ch in target for ch in "*?[") and not target.startswith("group:"):
        project.layer(target)  # A named layer that does not exist is unmeasurable (needs_review), not a pass.
    texts = drawn_text(project, layers)
    measured, problems = [], []
    for layer in layers:
        text = texts.get(layer["id"], "")
        characters, words = count_characters(text), count_words(text)
        measured.append({"layer": layer["name"], "text": text if len(text) <= 160 else text[:157] + "...",
                         "characters": characters, "words": words})
        for name, value in (("characters", characters), ("words", words)):
            minimum, maximum = rule.get(f"min_{name}"), rule.get(f"max_{name}")
            if minimum is not None and value < minimum:
                problems.append(f"{layer['name']!r} has {value} {name}; at least {minimum} required")
            if maximum is not None and value > maximum:
                problems.append(f"{layer['name']!r} has {value} {name}; at most {maximum} allowed")
        if "pattern" in rule:
            for pattern in compile_patterns(rule["pattern"], "pattern", "text", flags):
                if not pattern.search(text):
                    problems.append(f"{layer['name']!r} does not match {pattern.pattern!r}")
    forbidden = []
    patterns = [(pattern, False) for pattern in
                (compile_patterns(rule["forbid"], "forbid", "text", flags) if "forbid" in rule else [])]
    allow = []
    if rule.get("brand"):
        from .brand import for_project

        patterns += [(word_pattern(word), True) for word in brand_forbidden(project)]
        allow = brand_allowed(for_project(project))
    for pattern, from_brand in patterns:
        for layer in layers:
            text = texts.get(layer["id"], "")
            match = first_match(pattern, text, allowed_spans(text, allow) if from_brand else ())
            if match:
                forbidden.append({"layer": layer["name"], "match": match[0], "pattern": pattern.pattern})
    for item in forbidden:
        problems.append(f"{item['layer']!r} contains forbidden {item['match']!r}")
    misspelled = []
    if rule.get("spelling"):
        names = {layer["id"]: layer["name"] for layer in layers}
        found = spelling_findings(project, {layer["id"]: texts.get(layer["id"], "") for layer in layers})
        misspelled = [{"layer": names[item["layer"]], "word": item["word"], "suggestions": item["suggestions"]}
                      for item in found["words"]]
        problems += [f"{item['layer']!r} has the unknown word {item['word']!r}"
                     + (f" (did you mean {', '.join(item['suggestions'])}?)" if item["suggestions"] else "")
                     for item in misspelled]
    missing = []
    if "contains" in rule:
        combined = "\n".join(texts.get(layer["id"], "") for layer in layers)
        haystack = combined.casefold() if flags else combined
        for phrase in phrases(rule["contains"], "contains", "text"):
            if (phrase.casefold() if flags else phrase) not in haystack:
                missing.append(phrase)
        problems += [f"Required phrase {phrase!r} does not appear" for phrase in missing]
    detail = {"layers": measured[:20], **({"omitted": len(measured) - 20} if len(measured) > 20 else {})}
    if problems:
        detail["problems"] = problems[:20]
    if forbidden:
        detail["forbidden"] = forbidden[:20]
    if missing:
        detail["missing"] = missing
    if misspelled:
        detail["unknown_words"] = misspelled[:50]
    if not layers:
        detail["note"] = f"No visible text layers match {target!r}"
    return not problems, detail


# --- the ``placeholders`` design check ----------------------------------------------------------------------------

def placeholder_patterns(project):
    """[(label, compiled pattern)]: the built-in leftovers plus brand.json ``placeholders``."""
    from .brand import for_project

    found = [(label, re.compile(pattern)) for label, pattern in BUILTIN_PLACEHOLDERS]
    for pattern in for_project(project).get("placeholders", []):
        found.append(("brand placeholder", re.compile(pattern)))
    return found


def escaped_fields(source):
    """The literal ``${...}`` texts a source string draws on purpose with the ``$${...}`` escape."""
    from .variables import _SUBSTITUTION

    return {match[1] for match in _SUBSTITUTION.finditer(source or "") if match[1] is not None}


def undefined_variables(project):
    """Listing entries (``variables.listing``) for placeholders that do not resolve."""
    from .variables import listing

    return [entry for entry in listing(project) if not entry["defined"]]


def stand_in(project, undefined):
    """Give each undefined variable its own placeholder text as a value, so the rest of a check can draw the
    document; the placeholders check reports the variables themselves."""
    for entry in undefined:
        project.state["variables"].setdefault(entry["name"], "${" + entry["name"] + "}")


def check_placeholders(project, resolved, layers, issue, variant=None, undefined=()):
    """Report leftover template copy in drawn text: lorem ipsum, TODO/TBD markers, "Headline here" slot text,
    ``${name}`` merge fields that drew literally (``$${name}`` escapes excepted) and, for review only, another
    tool's ``{{field}}`` syntax. Variables that do not resolve are reported naming the variable (and the
    ``variant`` being checked). Layers marked with ``layer-intent literal_text`` are skipped."""
    label = f" in {variant}" if variant else ""
    extra = {"variant": variant} if variant else {}
    patterns = placeholder_patterns(project)
    stored = {layer["id"]: layer for layer in project.state["layers"]}
    for item in layers:
        layer = resolved[item["id"]]
        if layer["type"] != "text" or layer.get("literal_text"):
            continue
        text = layer.get("text", "")
        source = stored.get(item["id"], {}).get("text", "")
        if source and "${" in source and not text.strip():
            issue("placeholders", "warning", f"{item['name']!r} draws nothing{label}: its variables are empty "
                  f"({source.strip()[:60]!r}); supply the copy or remove the layer", [item], code="empty-variable", **extra)
            continue
        for kind, pattern in patterns:
            match = pattern.search(text)
            if match:
                issue("placeholders", "warning", f"{item['name']!r} still holds placeholder copy {match[0]!r}{label} "
                      f"({kind}); replace it, or mark intended text with layer-intent literal_text", [item],
                      code="leftover", match=match[0], **extra)
                break
        literal = escaped_fields(source) | {"${" + entry["name"] + "}" for entry in undefined}
        for match in LEFTOVER_FIELD.finditer(text):
            if match[0] not in literal:
                issue("placeholders", "warning", f"{item['name']!r} draws the unresolved merge field {match[0]!r}{label}; "
                      "give the variable a value (write $${name} for a literal ${name})", [item],
                      code="unresolved", match=match[0], **extra)
                break
        match = FOREIGN_FIELD.search(text)
        if match:
            issue("placeholders", "warning", f"{item['name']!r} has {match[0]!r}{label}, which looks like a merge field "
                  "from another tool's template (Vixl uses ${name}); replace it if it is leftover copy", [item],
                  code="foreign-field", match=match[0], action="review", **extra)
    shown = {item["id"] for item in layers}
    reported = set()
    for entry in undefined:
        if entry["layer"] not in shown or (entry["layer"], entry["name"]) in reported:
            continue
        reported.add((entry["layer"], entry["name"]))
        issue("placeholders", "error", f"Undefined variable ${{{entry['name']}}}{label} in {entry['layer_name']!r} "
              f"({entry['field']}); define it, add |default:TEXT, or supply it in every row", [resolved[entry["layer"]]],
              code="undefined-variable", variable=entry["name"], **extra)


# --- brand.json word lists ------------------------------------------------------------------------------------------

def validate_brand(kit):
    """The copy fields of brand.json: ``words`` {forbid: [phrases], prefer: {avoid: use}, allow: [words]} and
    ``placeholders`` (extra regular expressions that mark leftover template copy). ``allow`` lists names and terms
    the brand spells its own way: forbid and prefer skip them, and the spelling check accepts them."""
    words = kit.get("words", {})
    require(isinstance(words, dict) and set(words) <= {"forbid", "prefer", "allow"},
            "brand words has forbid, prefer and allow")
    if "forbid" in words:
        phrases(words["forbid"], "forbid", "brand words")
    allow = words.get("allow", [])
    require(isinstance(allow, list) and len(allow) <= MAX_ALLOWED
            and all(isinstance(item, str) and item.strip() and len(item) <= 200 for item in allow),
            f"brand words allow is a list of at most {MAX_ALLOWED} words or phrases")
    prefer = words.get("prefer", {})
    require(isinstance(prefer, dict) and len(prefer) <= 1000
            and all(isinstance(k, str) and k.strip() and isinstance(v, str) and v for k, v in prefer.items()),
            "brand words prefer maps a word to avoid to the word to use")
    if "placeholders" in kit:
        compile_patterns(kit["placeholders"], "placeholders", "brand.json")


def check_brand_words(project, kit, resolved, layers, issue):
    """brand.json ``words``: a forbidden phrase is a fix; a word with a preferred replacement is a review. A match
    inside an allowed word or phrase (``words.allow``, such as a product name) is skipped."""
    words = kit.get("words") or {}
    forbid = [(phrase, word_pattern(phrase)) for phrase in words.get("forbid", [])]
    prefer = [(avoid, use, word_pattern(avoid)) for avoid, use in (words.get("prefer") or {}).items()]
    if not forbid and not prefer:
        return
    allow = brand_allowed(kit)
    for item in layers:
        layer = resolved[item["id"]]
        if layer["type"] != "text":
            continue
        text = layer.get("text", "")
        spans = allowed_spans(text, allow)
        for phrase, pattern in forbid:
            match = first_match(pattern, text, spans)
            if match:
                issue("brand", "error", f"{item['name']!r} uses {match[0]!r}, which brand.json forbids", [item],
                      code="forbidden-word", match=match[0])
        for avoid, use, pattern in prefer:
            match = first_match(pattern, text, spans)
            if match:
                issue("brand", "warning", f"{item['name']!r} uses {match[0]!r}; the brand prefers {use!r}", [item],
                      code="preferred-word", match=match[0], prefer=use, action="review")
