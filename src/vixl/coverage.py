"""Coverage over a document's variants: one design check or suite run over every artboard, page and comp.

Each axis is ``None`` (the one view asked for with artboard/page/comp), ``"all"`` or a list of names. Every
combination is checked; findings name the artboard, page and comp they came from, and the report states
exactly which variants were covered.
"""

from itertools import product

from .errors import require

MAX_VARIANTS = 500
AXES = ("artboard", "page", "comp")


def requested(artboards=None, pages=None, comps=None):
    return any(value is not None for value in (artboards, pages, comps))


def _names(value, available, axis):
    if value is None:
        return None
    if value == "all":
        return list(available)
    values = [value] if isinstance(value, (str, int)) and not isinstance(value, bool) else value
    require(isinstance(values, list) and values and all(isinstance(v, (str, int)) and not isinstance(v, bool)
                                                         for v in values),
            f"{axis}s is 'all' or a list of {axis} names", field=f"{axis}s")
    return list(dict.fromkeys(values))


def variants(project, artboards=None, pages=None, comps=None, *, include_hidden=False, artboard=None, page=None,
             comp=None):
    """Every {artboard, page, comp} combination to check. An axis without a plural falls back to the single
    value (or None for the document as it is)."""
    from .pages import find_page, page_list

    state = project.state
    boards = _names(artboards, state.get("artboards", {}), "artboard")
    for name in boards or []:
        require(name in state.get("artboards", {}), f"Unknown artboard: {name}", field="artboards",
                suggestions=sorted(state.get("artboards", {})))
    page_refs = None
    if pages is not None:
        require(state.get("pages"), "This document has no pages; leave pages out", field="pages")
        if pages == "all":
            page_refs = [record["id"] for record in page_list(project, include_hidden=include_hidden)]
        else:
            page_refs = [find_page(state, ref, "pages")["id"] for ref in _names(pages, (), "page")]
        require(page_refs, "Every page is hidden from export; pass include_hidden to check them", field="pages")
    comp_names = _names(comps, state.get("comps", {}), "comp")
    for name in comp_names or []:
        require(name in state.get("comps", {}), f"Unknown layer comp: {name}", field="comps",
                suggestions=sorted(state.get("comps", {})))
    axes = [boards if boards is not None else [artboard], page_refs if page_refs is not None else [page],
            comp_names if comp_names is not None else [comp]]
    require(all(axes), "Nothing to cover: the document has none of the requested artboards or comps",
            field="artboards")
    combos = [dict(zip(AXES, values)) for values in product(*axes)]
    require(len(combos) <= MAX_VARIANTS, f"Coverage spans {len(combos)} variants; at most {MAX_VARIANTS}",
            "resource_limit")
    return combos


def label(project, combo):
    """A short name for one variant, such as 'artboard story, page 2 (Intro), comp dark'."""
    parts = []
    if combo.get("artboard"):
        parts.append(f"artboard {combo['artboard']}")
    if combo.get("page") is not None:
        pages = project.state.get("pages") or []
        number = next((i for i, record in enumerate(pages, 1) if record["id"] == combo["page"]), None)
        name = next((record["name"] for record in pages if record["id"] == combo["page"]), combo["page"])
        parts.append(f"page {number} ({name})" if number else f"page {name}")
    if combo.get("comp"):
        parts.append(f"comp {combo['comp']}")
    return ", ".join(parts) or "document"


def public(project, combo):
    """The variant as reported: the axes that are set, pages by name."""
    result = {key: value for key, value in combo.items() if value is not None}
    if "page" in result:
        result["page"] = next((record["name"] for record in project.state.get("pages") or []
                               if record["id"] == result["page"]), result["page"])
    return result


def check_all(project, *, artboards=None, pages=None, comps=None, include_hidden=False, **options):
    """``check_design`` over every variant, merged into one report: each finding carries ``variant`` and its message
    names it; ``variants`` gives each one's status and ``coverage`` what was checked."""
    from .checks import check_design, tally

    combos = variants(project, artboards, pages, comps, include_hidden=include_hidden,
                      artboard=options.pop("artboard", None), page=options.pop("page", None),
                      comp=options.pop("comp", None))
    issues, summary, checked = [], [], None
    for combo in combos:
        report = check_design(project, **options, **combo)
        checked = checked or report.get("checked")
        name, where = label(project, combo), public(project, combo)
        for item in report.get("issues", []):
            issues.append({**item, "variant": where, "message": f"[{name}] {item['message']}"})
        summary.append({**where, "passed": report["passed"], "errors": report["errors"],
                        "warnings": report["warnings"], "issues": len(report.get("issues", []))})
    result = {**tally(issues), "issues": issues}
    if checked:
        result["checked"] = checked
    result["variants"] = summary
    result["coverage"] = coverage_record(project, combos)
    return result


def coverage_record(project, combos):
    record = {"variants": len(combos)}
    for axis in AXES:
        values = list(dict.fromkeys(public(project, combo).get(axis) for combo in combos))
        if values != [None]:
            record[axis + "s"] = values
    return record
