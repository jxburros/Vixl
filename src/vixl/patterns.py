"""Regular expressions that callers supply: selectors (``name_regex``, ``text_regex``), text suites, copy facts,
brand placeholders and the replace-across workflow.

Python's ``re`` backtracks, and a thread inside one ``re`` call cannot be stopped: a pattern such as ``(a+)+$``
against a long run of ``a`` would hold its CPU and its workspace slot long after the hard timeout asked the call
to stop. So for a service caller (``bounded()``: an MCP or limited REST call, a server process, or
``VIXL_SAFE_REGEX=1``) a pattern runs one of two ways:

* On ``re``, when its worst case is provably small. ``analyse`` reads the parsed pattern and bounds the steps a
  backtracking match can take on ``n`` characters as ``coefficient * n ** degree``; the pattern is then matched only
  against text short enough to stay inside ``BUDGET`` steps (its ``cap``). Back-references, a repeat inside a repeat
  such as ``(a+)+``, and alternatives that start alike inside a repeat such as ``(a|ab)*`` have no such bound.
* On RE2 (the optional ``google-re2`` package, ``pip install 'vixl-engine[re2]'``), which matches in time linear
  in the text: a pattern ``re`` cannot bound at all, and any pattern on text longer than its cap. RE2 has no
  look-around or back-references. ``re2_source`` spells ``\\w``, ``\\d`` and ``\\s`` as the Unicode classes
  Python means; ``\\b`` is ASCII there.

So an ordinary pattern on ordinary text runs on ``re`` exactly as before, with or without RE2. Without RE2 a
pattern that cannot be bounded is refused (``Refused``), and text longer than a pattern's cap raises
``resource_limit``. Local callers (the CLI and the Python API outside a service call) keep plain ``re``.
``compile`` returns a ``Pattern`` with ``search``, ``finditer`` and ``subn`` either way; in a service call each
of them is also a cancellation checkpoint.
"""

import os
import re
from re import _parser as sre

from .errors import VixlError

ENV = "VIXL_SAFE_REGEX"
BUDGET = 2 ** 26  # Backtracking steps one match may take: under a second of ``re`` at its slowest.
MIN_CAP = 64  # A pattern that cannot be matched against even this much text is refused outright.
LONG_REPEAT = 64  # A repeat count from which the repeat is treated as open-ended.
EXPAND = 4  # Exact counts up to this are analysed as that many copies.
SERVING = False  # Set by a server process at start (``serving``): every pattern in it is a service caller's.
_BIG = 1e30
_ASCII = frozenset(range(128))
# A set of characters: the ASCII code points in it, and which kinds of other characters it holds: "word", "space",
# "any" when that is not known, "fold-k" for the non-ASCII characters that match a letter when case is ignored
# (the Kelvin sign for k, the long s, the dotless i), which are word characters, or "c8364" for one symbol that is
# neither a word character nor a space. Word and space never coincide.
_WORD, _SPACES, _ANY = frozenset({"word"}), frozenset({"space"}), frozenset({"any"})
_FULL = (_ASCII, _ANY)
_NONE = (frozenset(), frozenset())
_SPACE = frozenset(b" \t\n\r\f\v\x1c\x1d\x1e\x1f")
_CATEGORIES = {"CATEGORY_DIGIT": (frozenset(range(48, 58)), _WORD), "CATEGORY_SPACE": (_SPACE, _SPACES),
               "CATEGORY_WORD": (frozenset(b"_0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"), _WORD)}
_LETTERS = frozenset(b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
INSTALL = "pip install 'vixl-engine[re2]'"


class Refused(ValueError):
    """A valid pattern that a service will not run: ``reason`` says why, in words that follow the pattern's name."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason
        self.suggestions = ["Use plain repeats such as [A-Z]+-\\d+ and avoid .* between two other parts",
                            f"Or install google-re2 on the server ({INSTALL}) for linear-time matching"]


def serving(on=True):
    """Mark this process as a service: every caller pattern is then bounded, in or out of a tracked call."""
    global SERVING
    SERVING = bool(on)


def bounded():
    """True when caller patterns must be bounded: a service process or call, or ``VIXL_SAFE_REGEX=1``."""
    from .calls import CALL

    flag = os.environ.get(ENV, "").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return False
    return SERVING or CALL.get() is not None or flag in ("1", "true", "yes", "on")


def status():
    """How this process runs caller patterns, as a service reports it (``GET /limits``, ``vixl_job(action='list')``)."""
    linear = re2_module() is not None
    return {"bounded": bounded(), "linear_engine": "re2" if linear else None, "configure": {"env": ENV},
            "note": "Patterns re cannot bound, and long texts, run on RE2" if linear else
                    f"Patterns with no time bound are refused; {INSTALL} lifts that"}


def re2_module():
    """The ``re2`` module of google-re2, or None when it is not installed."""
    try:
        import re2
    except ImportError:
        return None
    return re2 if hasattr(re2, "Options") else None


# ----------------------------------------------------------------------------------------------- cost analysis

def _add(a, b):
    if a[0] != b[0]:
        return a if a[0] > b[0] else b
    return (a[0], min(a[1] + b[1], _BIG))


def _mul(a, b):
    return (a[0] + b[0], min(a[1] * b[1], _BIG))


def _union(a, b):
    return (a[0] | b[0], a[1] | b[1])


def _disjoint(a, b):
    if a[0] & b[0] or a[1] & b[1]:
        return False
    if not a[1] or not b[1]:
        return True
    if "any" in a[1] or "any" in b[1]:
        return False
    folded = lambda kinds: any(kind.startswith("fold-") for kind in kinds)  # noqa: E731
    return not ("word" in a[1] and folded(b[1])) and not ("word" in b[1] and folded(a[1]))


class _Analysis:
    """Bounds the backtracking of one parsed pattern. ``follow`` values are ``(cost, first)``: the cost of matching
    everything after a point, as ``(degree, coefficient)`` in the text length, and the characters it can start with."""

    def __init__(self, tree, flags):
        self.tree = tree
        self.asserts = 0
        self.fold = bool((flags | tree.state.flags) & re.IGNORECASE) or self.scoped_fold(tree)

    def scoped_fold(self, items):
        for op, value in items:
            name = str(op)
            if name == "SUBPATTERN" and (value[1] & re.IGNORECASE or self.scoped_fold(value[3])):
                return True
            if name == "BRANCH" and any(self.scoped_fold(branch) for branch in value[1]):
                return True
            if name in ("MAX_REPEAT", "MIN_REPEAT", "POSSESSIVE_REPEAT") and self.scoped_fold(value[2]):
                return True
            if name in ("ASSERT", "ASSERT_NOT") and self.scoped_fold(value[1]):
                return True
            if name == "ATOMIC_GROUP" and self.scoped_fold(value):
                return True
        return False

    def chars(self, code):
        """The set one literal character matches. Case folding reaches outside ASCII (``K`` matches the Kelvin sign)."""
        if code >= 128:
            char = chr(code)
            if char.isspace():
                return (frozenset(), _SPACES)
            if char.isalnum():
                return (frozenset(), _WORD)
            cased = char.lower() != char or char.upper() != char
            return (frozenset(), _ANY if cased and self.fold else frozenset({f"c{code}"}))
        if self.fold and code in _LETTERS:
            return (frozenset({code, code ^ 32}), self.folded({code}))
        return (frozenset({code}), frozenset())

    @staticmethod
    def folded(codes):
        return frozenset("fold-" + chr(code | 32) for code in codes if chr(code | 32) in "iks")

    def char_class(self, members):
        found, negate = _NONE, False
        for member, argument in members:
            kind = str(member)
            if kind == "NEGATE":
                negate = True
            elif kind == "LITERAL":
                found = _union(found, self.chars(argument))
            elif kind == "RANGE":
                low, high = argument
                part = frozenset(range(low, min(high, 127) + 1))
                wide = _ANY if high >= 128 else self.folded(part & _LETTERS) if self.fold else frozenset()
                if self.fold:
                    part |= frozenset(code ^ 32 for code in part & _LETTERS)
                found = _union(found, (part, wide))
            elif kind == "CATEGORY" and str(argument) in _CATEGORIES:
                found = _union(found, _CATEGORIES[str(argument)])
            else:  # A negated or unknown category: anything.
                return _FULL
        return (_ASCII - found[0], _ANY) if negate else found

    def one(self, op, value):
        """The character set of a single-character item, or None for any other item."""
        name = str(op)
        if name == "LITERAL":
            return self.chars(value)
        if name == "IN":
            return self.char_class(value)
        if name == "NOT_LITERAL":
            return (_ASCII - self.chars(value)[0], _ANY)
        if name == "ANY":
            return _FULL
        return None

    def first(self, items, follow):
        """The characters a match of ``items`` then ``follow`` (a first set) can start with."""
        for index, (op, value) in enumerate(items):
            name = str(op)
            rest = lambda: self.first(items[index + 1:], follow)  # noqa: E731
            single = self.one(op, value)
            if single is not None:
                return single
            if name == "AT":
                continue
            if name == "SUBPATTERN":
                return self.first(value[3], rest())
            if name == "ATOMIC_GROUP":
                return self.first(value, rest())
            if name == "BRANCH":
                after, found = rest(), _NONE
                for branch in value[1]:
                    found = _union(found, self.first(branch, after))
                return found
            if name in ("MAX_REPEAT", "MIN_REPEAT", "POSSESSIVE_REPEAT"):
                low, _, body = value
                after = rest()
                inner = self.first(body, after)
                return inner if low and body.getwidth()[0] else _union(inner, after)
            return _FULL  # Look-around and anything unknown: no claim.
        return follow

    def sequence(self, items, follow, strict):
        for index in range(len(items) - 1, -1, -1):
            follow = self.item(*items[index], follow, strict)
        return follow

    def item(self, op, value, follow, strict):
        name = str(op)
        cost, first = follow
        single = self.one(op, value)
        if single is not None:
            return (cost, single)
        if name == "AT":
            return follow
        if name == "SUBPATTERN":
            return self.sequence(value[3], follow, strict)
        if name == "ATOMIC_GROUP":
            return self.sequence(value, follow, strict)
        if name == "BRANCH":
            return self.branch(value[1], follow, strict)
        if name in ("ASSERT", "ASSERT_NOT"):
            self.asserts += 1
            inner = self.sequence(value[1], ((0, 1.0), _NONE), False)[0]
            return (_add(inner, cost), first if inner[0] == 0 and name == "ASSERT" and value[0] > 0 else _FULL)
        if name in ("MAX_REPEAT", "MIN_REPEAT", "POSSESSIVE_REPEAT"):
            return self.repeat(*value, follow, strict)
        if name in ("GROUPREF", "GROUPREF_EXISTS"):
            raise Refused("it uses a back-reference, which has no time bound")
        raise Refused(f"it uses syntax that cannot be bounded ({name.lower()})")

    def branch(self, branches, follow, strict):
        results = [self.sequence(branch, follow, strict) for branch in branches]
        if strict:
            # Inside a repeat, alternatives must be told apart by their first character, or the matcher can split
            # the same text between them in exponentially many ways.
            seen = _NONE
            for branch in branches:
                start = self.first(branch, _NONE)
                if not branch.getwidth()[0] or not _disjoint(start, seen):
                    raise Refused("alternatives inside a repeat start alike or can match nothing, like (a|ab)+ or "
                                  "(a|)+; make each start with a different character")
                seen = _union(seen, start)
        cost, first = (0, 0.0), _NONE
        for result in results:
            cost, first = _add(cost, result[0]), _union(first, result[1])
        return (cost, first)

    def repeat(self, low, high, body, follow, strict):
        cost, first = follow
        if high == low:
            if low <= EXPAND:
                for _ in range(low):
                    follow = self.sequence(body, follow, strict)
                return follow
        elif high == 1:  # Optional: with it, or without.
            start = self.first(body, _NONE)
            if strict and not _disjoint(start, first):
                raise Refused("an optional part inside a repeat can be confused with what follows it, like (ab?b)+")
            taken = self.sequence(body, follow, strict)
            return (_add(taken[0], cost), _union(taken[1], first))
        if not body.getwidth()[0]:
            raise Refused("it repeats something that can match nothing, like (a?)* or (a*)+")
        start = self.first(body, _NONE)
        asserts = self.asserts
        # Inside the body, what follows is the next round or the rest; the body must match in one way only.
        each = self.sequence(body, ((0, 1.0), _union(start, first)), True)[0]
        long = high >= LONG_REPEAT
        if high == low:  # An exact count: no choice of how many rounds.
            return (_add(_mul((0, float(low)), each), cost), start)
        if long:
            # A body that matches one way reads each character once; look-around inside it runs every round.
            own = _mul((1, 1.0), each) if self.asserts > asserts else (max(1, each[0]), each[1])
            ways = (1, 1.0)
        else:
            own, ways = _mul((0, float(high)), each), (0, float(high - low + 1))
        if _disjoint(start, first):
            # The rest cannot start where a round starts: giving rounds back fails at once each time.
            total = _add(_add(own, cost), ways)
        elif strict:
            raise Refused("it has a repeat inside a repeat that can split the same text in many ways, like (a+)+ or "
                          "(\\w+\\s*)*")
        else:
            total = _add(own, _mul(ways, cost))
        return (total, start if low else _union(start, first))


def analyse(pattern, flags=0):
    """``(degree, coefficient)``: a match of ``pattern`` by ``re.search`` on ``n`` characters takes at most about
    ``coefficient * n ** degree`` steps. Raises ``re.error`` for an invalid pattern and ``Refused`` for one with no
    such bound."""
    try:
        tree = sre.parse(pattern, flags)
    except (RecursionError, OverflowError) as exc:
        raise re.error(f"pattern is nested too deeply ({type(exc).__name__})") from exc
    try:
        cost = _Analysis(tree, flags).sequence(tree, ((0, 1.0), _NONE), False)[0]
    except RecursionError as exc:
        raise Refused("it is nested too deeply to bound") from exc
    multiline = (flags | tree.state.flags) & re.MULTILINE
    anchored = bool(tree) and str(tree[0][0]) == "AT" and (
        str(tree[0][1]) == "AT_BEGINNING_STRING" or (str(tree[0][1]) == "AT_BEGINNING" and not multiline))
    return cost if anchored else _mul((1, 1.0), cost)  # An unanchored search starts at every character.


def cap_of(cost):
    """The longest text a pattern of this cost may be matched against, or None for no limit."""
    degree, coefficient = cost
    if degree == 0:
        return None
    return int((BUDGET / max(coefficient, 1.0)) ** (1.0 / degree))


# ----------------------------------------------------------------------------------------------------- patterns

class Pattern:
    """A compiled caller pattern: ``search``, ``finditer`` and ``subn`` behave as on ``re.Pattern``.

    ``engine`` (``"re"`` or ``"re2"``) names what matches text of up to ``cap`` characters (None: any length).
    Longer text goes to ``long``, the RE2 form of the same pattern, or is refused when there is none."""

    def __init__(self, pattern, compiled, engine, cap=None, checked=False, long=None):
        self.pattern, self.compiled, self.engine, self.cap = pattern, compiled, engine, cap
        self.checked, self.long = checked, long

    def __repr__(self):
        return f"Pattern({self.pattern!r}, engine={self.engine!r}, cap={self.cap})"

    def matcher(self, text):
        if self.checked:
            from .calls import check_cancelled

            check_cancelled()
        if self.cap is None or len(text) <= self.cap:
            return self.compiled
        if self.long is not None:
            return self.long
        raise VixlError(
            "resource_limit",
            f"Text of {len(text)} characters is too long to match against the pattern {self.pattern!r} within "
            f"the service's time bound (this pattern: {self.cap} characters)",
            pattern=self.pattern, characters=len(text), maximum=self.cap,
            suggestions=["Simplify the pattern: fewer open-ended repeats such as .* or \\w+ next to each other",
                         f"Or install google-re2 on the server ({INSTALL}) for linear-time matching"])

    def search(self, text):
        return self.matcher(text).search(text)

    def finditer(self, text):
        return self.matcher(text).finditer(text)

    def subn(self, replacement, text):
        try:
            return self.matcher(text).subn(replacement, text)
        except (re.error, IndexError) as exc:  # A template that names a group the pattern lacks (``re``, RE2).
            raise VixlError("invalid_request", f"The replacement {replacement!r} does not fit the pattern "
                            f"{self.pattern!r}: {exc}", field="with") from exc


# RE2's \w, \d and \s are ASCII; these are the classes Python's mean for text. (\b stays ASCII: RE2 has no other.)
_RE2_CLASSES = {"w": r"\pL\pN_", "d": r"\p{Nd}", "s": r"\t\n\v\f\r\x1c-\x1f \x{85}\pZ"}


def re2_source(pattern):
    """``pattern`` with ``\\w``, ``\\d``, ``\\s`` and their negations spelled as the Unicode classes Python gives
    them, so RE2 matches accented words and other scripts as ``re`` does."""
    out, index, in_class = [], 0, False
    while index < len(pattern):
        char = pattern[index]
        if char == "\\" and index + 1 < len(pattern):
            escaped = pattern[index + 1]
            if escaped in _RE2_CLASSES:
                out.append(_RE2_CLASSES[escaped] if in_class else f"[{_RE2_CLASSES[escaped]}]")
            elif escaped.lower() in _RE2_CLASSES and not in_class:
                out.append(f"[^{_RE2_CLASSES[escaped.lower()]}]")
            else:
                out.append(char + escaped)
            index += 2
            continue
        out.append(char)
        index += 1
        if in_class:
            in_class = char != "]"
        elif char == "[":
            in_class = True
            if pattern[index:index + 1] == "^":
                out.append("^")
                index += 1
            if pattern[index:index + 1] == "]":  # A leading ] is a literal.
                out.append("\\]")
                index += 1
    return "".join(out)


def _re2_compile(pattern, flags):
    """``pattern`` compiled by RE2, or None when google-re2 is not installed or cannot run it."""
    module = re2_module()
    if module is None:
        return None
    options = module.Options()
    options.log_errors = False
    options.case_sensitive = not flags & re.IGNORECASE
    options.dot_nl = bool(flags & re.DOTALL)
    try:
        return module.compile(("(?m)" if flags & re.MULTILINE else "") + re2_source(pattern), options)
    except module.error:
        return None


def _boolean_core(pattern, flags):
    """``pattern`` without a leading ``.*``: for a yes-or-no search the two are the same, and the lead only makes
    every start position scan the line."""
    while pattern.startswith(".*"):
        tree = sre.parse(pattern, flags)
        op, value = tree[0]
        if str(op) not in ("MAX_REPEAT", "MIN_REPEAT") or value[0] or value[1] != sre.MAXREPEAT \
                or [str(o) for o, _ in value[2]] != ["ANY"]:
            break
        rest = pattern[3:] if str(op) == "MIN_REPEAT" else pattern[2:]
        try:
            sre.parse(rest, flags)
        except re.error:
            break
        pattern = rest
    return pattern


def compile(pattern, flags=0, *, window=None, boolean=False):  # noqa: A001 - mirrors re.compile
    """Compile a caller's ``pattern``. ``window`` is the longest text the site will match it against (None: any
    length); ``boolean`` says only ``search``'s yes or no is used. Raises ``re.error`` for an invalid pattern and,
    for a service caller, ``Refused`` for one that neither engine can run inside the time bound."""
    plain = re.compile(pattern, flags)
    if not bounded():
        return Pattern(pattern, plain, "re")
    source = _boolean_core(pattern, flags) if boolean else pattern
    if source != pattern:
        plain = re.compile(source, flags)
    try:
        cost = analyse(source, flags)
    except Refused:
        linear = _re2_compile(source, flags)
        if linear is None:
            raise
        return Pattern(pattern, linear, "re2", checked=True)
    cap = cap_of(cost)
    if cap is None or (window is not None and cap >= window):
        return Pattern(pattern, plain, "re", cap=cap, checked=True)
    # ``re`` is bounded only on text up to ``cap``: RE2 takes the rest, or all of it when ``cap`` is tiny.
    linear = _re2_compile(source, flags)
    if cap >= MIN_CAP and (linear is not None or window is None):
        return Pattern(pattern, plain, "re", cap=cap, checked=True, long=linear)
    if linear is not None:
        return Pattern(pattern, linear, "re2", checked=True)
    raise Refused(f"its open-ended repeats (.*, +, {{n,}}) can take about n^{cost[0]} steps on n characters, too "
                  f"slow for text of {window or MIN_CAP} characters; put a distinct character between repeats, or "
                  "anchor it with ^" + (" (RE2 is installed but does not support this pattern's syntax)"
                                        if re2_module() is not None else ""))
