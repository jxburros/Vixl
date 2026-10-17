"""Field validation rules for fillable PDFs.

Vixl checks a field's rules (``format`` email, digits, number range or date display, and
``pattern``) when it fills a form. This module also writes them into the fillable PDF as standard
field actions, so a viewer enforces them while someone types: Acrobat's own AFNumber, AFRange
and AFDate functions where one exists (Acrobat, Chrome and Firefox all run them), and a short
JavaScript validate action otherwise. Scripts come from fixed templates; the only caller text in
them is a JSON-escaped string literal, and the PDF stays byte-identical for identical input.
"""

import json
import re
from re import _parser as sre

from .errors import VixlError
from .pdf_writer import Name, Text

EMAIL = r"[^@\s]+@[^@\s]+"
MAX_PATTERN = 200
MAX_MESSAGE = 200
MAX_REPEAT = 1000
MAX_VALUE = 1024  # longest text matched against a pattern; bounds polynomial backtracking such as \d*\d*x
DATE_TOKENS = {"YYYY": "yyyy", "MM": "mm", "M": "m", "DD": "dd", "D": "d"}
DATE_PICTURE = re.compile(r"(?:YYYY|MM|M|DD|D|[-/. ,])+")
UNSAFE = ("ASSERT", "ASSERT_NOT", "GROUPREF", "GROUPREF_EXISTS", "ATOMIC_GROUP", "POSSESSIVE_REPEAT")


def check_pattern(pattern):
    """Raise unless ``pattern`` means the same to Python and to a viewer's JavaScript and cannot
    take exponential time. A pattern must match the whole value; it can use classes, groups,
    alternation, ``{n,m}`` counts and ``^``/``$``, but no flags, named groups, look-around,
    back-references, possessive or atomic syntax, ``\\A``/``\\Z``, counts above 1000, or an
    unbounded repeat of something ambiguous: a body that can match empty, a variable count such as
    ``(a+)+`` or ``(a?a?)+``, or alternatives that can start with the same character such as
    ``(a|aa)+`` or ``(.|a)+``."""
    def reject(reason):
        raise VixlError("invalid_operation", f"pattern {reason}", field="pattern",
                        suggestions=["Use a plain pattern such as [A-Z]{2}-[0-9]{4}"])

    if not isinstance(pattern, str) or not 0 < len(pattern) <= MAX_PATTERN:
        reject(f"is a regular expression of 1–{MAX_PATTERN} characters")
    try:
        tree = sre.parse(pattern)
        re.compile(pattern, re.ASCII)
    except (re.error, RecursionError, OverflowError) as exc:
        reject(f"is not a valid regular expression ({exc})")
    if tree.state.flags & ~re.UNICODE or tree.state.groupdict:
        reject("cannot use inline flags or named groups")

    def width(items):
        return sre.SubPattern(tree.state, list(items)).getwidth()[0]

    def walk(items, unbounded):
        for op, value in items:
            name = str(op)
            if name in UNSAFE:
                reject("cannot use look-around, back-references, or possessive or atomic syntax")
            if name == "AT" and str(value) in ("AT_BEGINNING_STRING", "AT_END_STRING"):
                reject("cannot use \\A or \\Z (use ^ and $)")
            if name in ("MAX_REPEAT", "MIN_REPEAT"):
                low, high, body = value
                if high != sre.MAXREPEAT and high > MAX_REPEAT:
                    reject(f"cannot repeat more than {MAX_REPEAT} times")
                if unbounded and (high > 1 or low != high):
                    reject("cannot repeat something that is inside an unbounded repeat, like (a+)+ or (a?)+")
                if high == sre.MAXREPEAT and width(body) == 0:
                    reject("cannot have an unbounded repeat of something that can match nothing, like (a?)*")
                walk(body, unbounded or high == sre.MAXREPEAT)
            elif name == "SUBPATTERN":
                if value[1] or value[2]:
                    reject("cannot use inline flags")
                walk(value[3], unbounded)
            elif name == "BRANCH":
                if unbounded:
                    ambiguous(value[1])
                for branch in value[1]:
                    walk(branch, unbounded)

    def ambiguous(branches):
        # Inside an unbounded repeat, alternatives must be told apart by their first character, or the
        # matcher can split the same text between them in exponentially many ways.
        if any(width(branch) == 0 for branch in branches):
            reject("cannot have an alternative that can match nothing inside an unbounded repeat, like (a|aa)+")
        seen = set()
        for branch in branches:
            chars = first(branch)
            if chars is None or chars & seen:
                reject("cannot have alternatives that start alike inside an unbounded repeat, like (a|ab)+ or "
                       "(.|a)+; make each start with a different character")
            seen |= chars

    walk(tree, False)


CATEGORIES = {"CATEGORY_DIGIT": frozenset(range(48, 58)), "CATEGORY_SPACE": frozenset(b" \t\n\r\f\v"),
              "CATEGORY_WORD": frozenset(b"_0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")}


def first(items):
    """The characters a match of ``items`` can start with, or None for "any" (``.``, negated sets): a
    conservative answer, so a None means the caller treats it as overlapping everything."""
    chars = set()
    for op, value in items:
        name = str(op)
        if name == "LITERAL":
            return chars | {value}
        if name == "IN":
            for member, argument in value:
                kind = str(member)
                if kind == "LITERAL":
                    chars.add(argument)
                elif kind == "RANGE":
                    chars |= set(range(argument[0], argument[1] + 1))
                elif kind == "CATEGORY" and str(argument) in CATEGORIES:
                    chars |= CATEGORIES[str(argument)]
                else:
                    return None
            return chars
        if name == "AT":
            continue
        if name == "SUBPATTERN":
            inner = first(value[3])
        elif name == "BRANCH":
            inner = set()
            for branch in value[1]:
                part = first(branch)
                if part is None:
                    return None
                inner |= part
        elif name in ("MAX_REPEAT", "MIN_REPEAT"):
            inner = first(value[2])
        else:
            return None
        if inner is None:
            return None
        chars |= inner
        if sre.SubPattern(sre.State(), [(op, value)]).getwidth()[0]:
            return chars
    return chars


def pattern_matches(pattern, text):
    """Whether the whole of ``text`` matches ``pattern`` (ASCII classes, as in JavaScript). Text longer
    than ``MAX_VALUE`` is refused rather than matched."""
    if len(text) > MAX_VALUE:
        raise VixlError("invalid_input", f"A field with a pattern holds at most {MAX_VALUE} characters; set its "
                        f"max_length to {MAX_VALUE} or less", field="max_length", max_length=MAX_VALUE)
    return re.fullmatch(pattern, text, re.ASCII) is not None


def date_picture(display):
    """Acrobat's date picture (``dd/mm/yyyy``) for a ``format.display`` (``DD/MM/YYYY``), or None
    when the display has literal text a viewer cannot express."""
    if not DATE_PICTURE.fullmatch(display):
        return None
    return re.sub(r"YYYY|MM|M|DD|D", lambda match: DATE_TOKENS[match[0]], display)


def _js(value):
    # JSON string and number literals are valid JavaScript; ASCII escapes keep any text safe.
    return json.dumps(value)


def _reject(test, message):
    # One validate step: refuse the entry when ``test`` (an expression over event.value) fails.
    return f"if (event.rc && event.value && !({test})) {{ app.alert({_js(message)}); event.rc = false; }}"


def _only(characters):
    return f"if (!event.willCommit && event.change && !/^[{characters}]*$/.test(event.change)) {{ event.rc = false; }}"


def scripts(record):
    """{"K": keystroke, "F": format, "V": validate} JavaScript for a field's rules (only the
    events that have one)."""
    kind, fmt, custom = record["kind"], record.get("format"), record.get("message")
    keystroke, display, validate = [], [], []
    if kind == "text":
        if fmt == "email":
            validate.append(_reject(f"/^{EMAIL}$/.test(event.value)", custom or "Enter an email address such as name@example.com."))
        elif fmt == "digits":
            keystroke.append(_only("0-9"))
            validate.append(_reject("/^[0-9]+$/.test(event.value)", custom or "Use the digits 0-9 only."))
        if record.get("pattern"):
            test = f"new RegExp({_js('^(?:' + record['pattern'] + ')$')}).test(event.value)"
            validate.append(_reject(test, custom or "The entry is not in the expected format."))
    elif kind == "number":
        fmt = fmt or {}
        if fmt.get("decimals") is not None:
            arguments = f"{fmt['decimals']}, 1, 0, 0, \"\", true"
            keystroke.append(f"AFNumber_Keystroke({arguments});")
            display.append(f"AFNumber_Format({arguments});")
        else:
            keystroke.append(_only("0-9.+eE-"))
            validate.append(_reject("isFinite(Number(event.value))", custom or "Enter a number."))
        low, high = fmt.get("min"), fmt.get("max")
        if low is not None or high is not None:
            if custom:
                bounds = [f"Number(event.value) >= {_js(low)}" if low is not None else "true",
                          f"Number(event.value) <= {_js(high)}" if high is not None else "true"]
                validate.append(_reject(" && ".join(bounds), custom))
            else:
                validate.append(f"AFRange_Validate({_js(low is not None)}, {_js(low or 0)}, {_js(high is not None)}, "
                                f"{_js(high or 0)});")
    elif kind == "date":
        picture = date_picture((fmt or {}).get("display", "YYYY-MM-DD"))
        if picture:
            keystroke.append(f"AFDate_KeystrokeEx({_js(picture)});")
            display.append(f"AFDate_FormatEx({_js(picture)});")
    return {key: "\n".join(lines) for key, lines in (("K", keystroke), ("F", display), ("V", validate)) if lines}


def actions(record):
    """The field's PDF additional-actions dictionary (``/AA``) enforcing its rules, or None."""
    return {key: {"Type": Name("Action"), "S": Name("JavaScript"), "JS": Text(code)}
            for key, code in scripts(record).items()} or None
