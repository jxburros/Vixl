"""Caller regular expressions cannot outlive the hard timeout (#825): for a service caller a pattern runs on ``re``
only when its backtracking is bounded, on RE2 (google-re2, optional) otherwise, and is refused when neither holds.

Every test passes with and without google-re2 installed: ``no_re2`` hides it, and the RE2 tests skip without it."""

import re
import time

import pytest

from vixl import Project, VixlError, copy_checks, group_consistency, patterns, selectors
from vixl.calls import CALL, CallState
from vixl.errors import Cancelled
from vixl.plugins.workspace_qa import replace_across

CATASTROPHIC = [r"(a+)+$", r"(a|aa)+$", r"(a|ab)*c", r"(\w+\s*)*$", r"(a?)*b", r"(ab?b)+c", r"(x+x+)+y", r"(a+)\1"]
# Patterns agents and suites really send. Each is bounded, so it stays on ``re`` and means what it always did.
ORDINARY = [r"^price-\d+$", r"badge|ribbon", r"\bsale\b", r"[A-Z]{2,}", r"\d+%", r"\w+@\w+\.\w+", r".*total.*",
            r"^Title.*\d+$", r"(?<!\w)sale(?!\w)", r"\$\d+(\.\d{2})?", r"https?://\S+", r"\d{4}-\d{2}-\d{2}",
            r"(foo|bar)+baz", r"lorem ipsum|TODO|FIXME", r"\d+\s*(px|pt|em)", r"\d{1,3}(,\d{3})*", r"é+\s\w+"]
TEXTS = ["price-12", "PRICE-7 ", "Summer sale", "wholesale", "Save 20% today", "mail me@example.com now", "Total: $4.50",
         "Title of 2024", "see https://example.com/x?y=1", "2026-11-14", "foobarfoobaz", "Lorem ipsum dolor", "12 px",
         "1,234,567", "éé déjà vu", "line one\nthe total is here\nline three", ""]


@pytest.fixture
def service(monkeypatch):
    """Compile as a service caller does."""
    monkeypatch.delenv(patterns.ENV, raising=False)
    monkeypatch.setattr(patterns, "SERVING", True)


@pytest.fixture
def no_re2(monkeypatch):
    monkeypatch.setattr(patterns, "re2_module", lambda: None)


@pytest.fixture
def re2(monkeypatch):
    return pytest.importorskip("re2")


def poster(text):
    project = Project(400, 300, "white")
    project.apply([{"type": "text", "name": "body", "text": text, "size": 12, "x": 10, "y": 10, "color": "black"},
                   {"type": "text", "name": "price-1", "text": "$4.50", "size": 12, "x": 10, "y": 60, "color": "black"}])
    return project


def select(project, where):
    return project.apply([{"type": "edit-layers", "where": where, "do": {"type": "hide"}, "dry_run": True}],
                         detail="compact")


# ----------------------------------------------------------------------------------------------- who is bounded

def test_local_callers_keep_python_re(monkeypatch):
    monkeypatch.delenv(patterns.ENV, raising=False)
    assert not patterns.bounded()
    compiled = patterns.compile(r"(a+)+$")
    assert (compiled.engine, compiled.cap, compiled.pattern) == ("re", None, r"(a+)+$")
    assert compiled.search("aaa") and [m[0] for m in patterns.compile(r"\d+").finditer("a1 b22")] == ["1", "22"]
    assert patterns.compile(r"(\w+)@(\w+)").subn(r"\2 at \1", "me@home") == ("home at me", 1)


def test_service_calls_processes_and_the_environment_switch_bound_patterns(monkeypatch):
    monkeypatch.delenv(patterns.ENV, raising=False)
    token = CALL.set(CallState())
    try:
        assert patterns.bounded()  # An MCP call, or a limited REST or Host call.
    finally:
        CALL.reset(token)
    assert not patterns.bounded()
    monkeypatch.setenv(patterns.ENV, "1")
    assert patterns.bounded()
    monkeypatch.delenv(patterns.ENV)

    from vixl.call_limits import CallLimits, add_arguments, from_arguments
    import argparse

    parser = argparse.ArgumentParser()
    add_arguments(parser)
    from_arguments(parser.parse_args([]))  # What `vixl serve`, `vixl mcp` and `vixl host` call at start.
    assert patterns.SERVING and patterns.bounded()
    described = CallLimits().describe()["caller_regex"]  # GET /limits and vixl_job(action="list") report it.
    assert described["bounded"] and described["configure"] == {"env": "VIXL_SAFE_REGEX"}
    assert described["linear_engine"] == ("re2" if patterns.re2_module() else None)
    monkeypatch.setenv(patterns.ENV, "0")  # The operator's way out, for a server whose callers are trusted.
    assert not patterns.bounded()


# ------------------------------------------------------------------------------------------ without google-re2

@pytest.mark.parametrize("pattern", CATASTROPHIC)
def test_a_catastrophic_pattern_is_refused_at_once(service, no_re2, pattern):
    started = time.perf_counter()
    with pytest.raises(VixlError) as caught:
        selectors.parse_where({"text_regex": pattern})
    assert time.perf_counter() - started < 1
    error = caught.value
    assert error.code == "invalid_operation" and "cannot run on a shared service" in str(error)
    assert error.details["field"] == "where.text_regex"
    assert any("google-re2" in hint for hint in error.details["suggestions"])


def test_a_catastrophic_selector_returns_an_error_within_a_short_budget(service, no_re2):
    # Unbounded, this search takes 2 ** 28 steps: about ten seconds inside one call that nothing can stop.
    project = poster("a" * 28 + "!")
    started = time.perf_counter()
    with pytest.raises(VixlError) as caught:
        select(project, {"text_regex": r"(a+)+$"})
    assert time.perf_counter() - started < 2
    assert caught.value.code == "invalid_operation" and "repeat inside a repeat" in str(caught.value)


@pytest.mark.parametrize("fixture", ["no_re2", "re2"])
def test_ordinary_patterns_behave_as_before(service, fixture, request):
    request.getfixturevalue(fixture)
    for pattern in ORDINARY:
        compiled = selectors.compile_regex(pattern)
        assert compiled.engine == "re", pattern  # Bounded, so RE2 is not needed even where it is installed.
        plain = re.compile(pattern, re.IGNORECASE)
        for text in TEXTS:
            assert bool(compiled.search(text)) == bool(plain.search(text)), (pattern, text)
    for pattern in ORDINARY:
        if pattern.startswith(".*"):
            continue
        compiled, plain = patterns.compile(pattern), re.compile(pattern)
        for text in TEXTS:
            assert [m.span() for m in compiled.finditer(text)] == [m.span() for m in plain.finditer(text)], pattern


def test_ordinary_selectors_select_the_same_layers_in_a_service_call(service, no_re2):
    project = poster("Summer sale: 20% off")
    assert select(project, {"name_regex": r"^price-\d+$"})["edit_layers"][0]["matched"] == 1
    assert select(project, {"text_regex": r".*sale.*"})["edit_layers"][0]["matched"] == 1
    assert select(project, {"text_regex": r"\d+%|\$\d+"})["edit_layers"][0]["matched"] == 2
    assert select(project, {"text_regex": r"(?<!\w)off(?!\w)"})["edit_layers"][0]["matched"] == 1


def test_a_pattern_too_slow_for_its_window_is_refused_and_a_capped_one_refuses_long_text(service, no_re2):
    with pytest.raises(VixlError) as caught:
        selectors.parse_where({"name_regex": r"\d*\d*\d*x"})
    assert "n^4" in str(caught.value) and "2000 characters" in str(caught.value)
    compiled = patterns.compile(r"\d*\d*\d*x")  # A site with no window: allowed, but only on short text.
    assert compiled.engine == "re" and compiled.long is None and patterns.MIN_CAP <= compiled.cap < 200
    assert compiled.search("12x") and not compiled.search("1" * compiled.cap)
    with pytest.raises(VixlError) as caught:
        compiled.search("1" * (compiled.cap + 1))
    assert caught.value.code == "resource_limit" and caught.value.details["maximum"] == compiled.cap
    with pytest.raises(patterns.Refused):
        patterns.compile(r"\d*\d*\d*\d*\d*\d*x")  # No text is short enough.


@pytest.mark.parametrize("pattern,text", [
    (r"\d+x", "1"), (r"\w+@\w+\.\w+", "a"), (r"[^,]+,[^,]+,[^,]+!", "a"), (r"(foo|bar)+baz", "foo"),
    (r"\s*a\s*b\s*c", " "), (r"https?://\S+!", "http://a"), (r"(?=.*a)(?=.*b).*c", "ab"),
])
def test_an_accepted_pattern_stays_inside_its_time_bound_on_adversarial_text(service, no_re2, pattern, text):
    compiled = patterns.compile(pattern)
    assert compiled.engine == "re" and compiled.cap
    subject = (text * compiled.cap)[:min(compiled.cap, 20_000)]
    started = time.perf_counter()
    compiled.search(subject)
    assert time.perf_counter() - started < 5  # About a second at worst; the margin is for a loaded machine.


def test_a_leading_dot_star_is_dropped_for_a_yes_or_no_search(service, no_re2):
    assert patterns._boolean_core(r".*total.*", 0) == r"total.*"
    assert patterns._boolean_core(r".*?.*total", 0) == r"total"
    assert patterns._boolean_core(r".*|total", 0) == r".*|total"  # An alternative, not a lead.
    assert patterns._boolean_core(r".*+total", 0) == r".*+total"
    assert selectors.compile_regex(r".*total.*").pattern == r".*total.*"  # Reported as the caller wrote it.
    with pytest.raises(patterns.Refused):
        patterns.compile(r".*total.*bar", window=2000)  # Spans matter: the lead stays, and it is too slow.


def test_each_regex_call_is_a_cancellation_checkpoint(service, no_re2):
    compiled = patterns.compile(r"\d+")
    state = CallState()
    token = CALL.set(state)
    try:
        assert compiled.search("a1")
        state.cancel.set()
        with pytest.raises(Cancelled):
            compiled.search("a1")
    finally:
        CALL.reset(token)


def test_suites_facts_placeholders_and_replace_refuse_what_cannot_be_bounded(service, no_re2):
    with pytest.raises(VixlError) as caught:
        copy_checks.validate_text_rule({"target": "*", "forbid": [r"(a+)+$"]}, "suite 'copy'")
    assert caught.value.code == "invalid_suite" and "cannot run on a shared service" in str(caught.value)
    with pytest.raises(VixlError) as caught:
        group_consistency.validate_facts({"price": {"pattern": r"(\$\d+)+\1"}})
    assert caught.value.code == "invalid_request" and "back-reference" in str(caught.value)
    with pytest.raises(VixlError) as caught:
        replace_across._rules([{"text": r"(\w+\s*)*!", "with": "x", "match": "regex"}])
    assert caught.value.code == "invalid_request" and caught.value.details["field"] == "replace[0]"
    # The same sites take ordinary patterns, and replace still fills its template.
    assert copy_checks.validate_text_rule({"target": "*", "pattern": r"^\$\d+\.\d{2}$"}, "suite 'copy'") is None
    assert group_consistency.validate_facts({"price": {"pattern": r"\$\d+"}})["price"]["regex"].search("now $12")
    rule = replace_across._rules([{"text": r"(\d+) USD", "with": r"$\1", "match": "regex"}])[0]
    assert rule["pattern"].subn(rule["replacement"], "12 USD or 40 USD") == ("$12 or $40", 2)
    with pytest.raises(VixlError) as caught:
        rule["pattern"].subn(r"\3", "12 USD")
    assert caught.value.code == "invalid_request"


# --------------------------------------------------------------------------------------------- with google-re2

@pytest.mark.parametrize("pattern", [p for p in CATASTROPHIC if "\\1" not in p])
def test_re2_runs_what_python_re_cannot_bound(service, re2, pattern):
    compiled = selectors.compile_regex(pattern)
    assert compiled.engine == "re2" and compiled.cap is None
    plain = re.compile(pattern, re.IGNORECASE)
    for text in ("aaa", "AAb", "abab c", "x y z", "", "abbc", "xxxxy"):
        assert bool(compiled.search(text)) == bool(plain.search(text)), (pattern, text)
    started = time.perf_counter()
    compiled.search(("a" * 2000) + "!")
    compiled.search(("ab" * 1000) + "!")
    assert time.perf_counter() - started < 1


def test_re2_serves_a_catastrophic_selector_and_long_text(service, re2):
    project = poster("a" * 28 + "!")
    started = time.perf_counter()
    assert select(project, {"text_regex": r"(a+)+$"})["edit_layers"][0]["matched"] == 0
    assert select(project, {"text_regex": r"(a+)+!$"})["edit_layers"][0]["matched"] == 1
    assert time.perf_counter() - started < 2
    assert selectors.compile_regex(r"\d*\d*\d*x").engine == "re"  # Bounded on short text; RE2 takes the rest.
    slow = patterns.compile(r"(\d*)\d*\d*(x)", re.IGNORECASE)
    assert slow.engine == "re" and slow.cap < 200 and slow.long is not None
    assert slow.search("12X").span() == (0, 3)
    assert slow.search("1" * 50_000 + "X").span() == (0, 50_001)  # Past the cap: RE2, not an error.
    assert slow.subn(r"\2", "12x 3X") == ("x X", 2)
    assert slow.subn(r"<\1>", "1" * 300 + "x") == ("<" + "1" * 300 + ">", 1)
    nested = patterns.compile(r"(ab|a)+", 0)
    assert nested.engine == "re2" and [m[0] for m in nested.finditer("abab aab")] == ["abab", "aab"]
    with pytest.raises(VixlError) as caught:
        nested.subn(r"\5", "ab")
    assert caught.value.code == "invalid_request"


def test_re2_reads_word_digit_and_space_classes_as_python_does(service, re2):
    assert patterns.re2_source(r"\w+[\d-]\S[^\s]\\w\W[]\w]") == (
        r"[\pL\pN_]+[\p{Nd}-][^\t\n\v\f\r\x1c-\x1f \x{85}\pZ][^\t\n\v\f\r\x1c-\x1f \x{85}\pZ]\\w"
        r"[^\pL\pN_][\]\pL\pN_]")
    text = "déjà vu\u00a0naïve ٣٤ straße_1 — fin"
    for pattern in (r"(\w+\s*)*", r"(\w|\d\d)+", r"(\S+\s?)+", r"(\W|\s\s)+", r"([\w-]+ ?)+", r"(\d+\d*)+"):
        compiled = patterns.compile(pattern)
        assert compiled.engine == "re2", pattern
        assert [m.span() for m in compiled.finditer(text)] == [m.span() for m in re.finditer(pattern, text)], pattern


def test_what_neither_engine_can_run_is_refused(service, re2):
    with pytest.raises(patterns.Refused) as caught:
        patterns.compile(r"(a+)\1")  # RE2 has no back-references.
    assert "back-reference" in caught.value.reason
    with pytest.raises(patterns.Refused) as caught:
        patterns.compile(r"(?<!x)\d*\d*\d*y", window=2000)  # Nor look-behind; and re is too slow on 2,000.
    assert "RE2 is installed" in caught.value.reason
    capped = patterns.compile(r"(?<!x)\d*\d*\d*y")  # Without a window it runs on re, on short text only.
    assert capped.engine == "re" and capped.long is None
    with pytest.raises(VixlError) as caught:
        capped.search("1" * 500)
    assert caught.value.code == "resource_limit"
