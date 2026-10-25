"""``localize``: build one checked variant of a master document per locale.

Each locale's candidate gets the locale's values (from the document, its project groups and an optional strings
CSV), its font fallbacks, a mirrored layout when it is right to left, and the text fit policy (``shrink`` runs
``fit-text`` down to ``min_size``; ``flag`` only reports). The candidate is then checked as the locale check does
(``locale_check``). A locale with a missing key or a finding at ``fail_on`` is held: nothing is written for it and
the report lists its findings and the repairs tried. Every other locale writes its outputs into ``output_dir``:
the derived document ``<master>.<code>.vixl`` (a copy, without the locale table), an export per ``formats`` entry
(``<master>.<code>.png`` ...), and with ``spec`` a campaign run (``production.run``) into ``<code>/`` on the
localized document, so a campaign gets a locale axis on top of its rows and matrix.

``localize.json`` in ``output_dir`` records each locale's fingerprint: the localized state, the renderer
environment, the fonts, links and the build settings. A re-run rebuilds only the locales whose fingerprint
changed (an edited master changes every locale; an edited translation changes one) and reuses the others when
their files are untouched. Existing files that this record did not write are refused unless ``overwrite``.
"""

from pathlib import Path

from ...errors import require
from .locale_check import KINDS, compare, evaluate, localized, request_options, request_strings, status, suite_names
from .locales import DEFAULT_SOURCE, locale_table, missing_keys, options, select

RECORD = "localize.json"
FORMATS = ("png", "jpg", "webp", "svg", "pdf")
DERIVED_DROP = ("locales", "locale_options")


def _digest_file(path):
    from ...production import file_digest

    return file_digest(path)


def _fingerprint(candidate, settings):
    from ...assurance import digest
    from ...links import fingerprint as link_fingerprint
    from ...production import stable_state
    from ...render_cache import environment
    from ...text import font_data, font_digest

    fonts = [font_digest(font_data(candidate, layer)) for layer in candidate.state["layers"] if layer["type"] == "text"]
    # Other locales' values are not part of this locale's output.
    state = {key: value for key, value in candidate.state.items() if key not in DERIVED_DROP}
    return digest([stable_state(state), environment(), settings, fonts, link_fingerprint(candidate)])


def _intact(directory, prior):
    return all((directory / item["path"]).is_file() and _digest_file(directory / item["path"]) == item["sha256"]
               for item in prior.get("outputs", []))


def _owned(prior):
    """{relative path: sha256} of the files the previous run wrote, as they were written."""
    return {item["path"]: item["sha256"] for entry in prior.values() for item in entry.get("outputs", [])}


def _writable(path, relative, owned, overwrite):
    if not path.exists() or overwrite:
        return
    require(relative in owned and _digest_file(path) == owned[relative],
            f"{relative} already exists and this localize run did not write it; pass overwrite=true to replace it",
            "output_exists", field="output_dir")


def derive(candidate, code, master):
    """The localized document saved for ``code``: the candidate without the locale table, as one revision."""
    for key in DERIVED_DROP:
        candidate.state.pop(key, None)
    candidate.path, candidate._revision = None, None
    candidate._record([], f"Localized to {code} from {master}")
    return candidate


def localize(session, project, request, document):
    from ...fileio import file_lock
    from ...production import read_json, run as production_run, write_json

    fail_on = request.get("fail_on", "error")
    formats = request.get("formats", [])
    require(isinstance(formats, list) and all(f in FORMATS for f in formats),
            f"formats is a list of {', '.join(FORMATS)}", field="formats", allowed=list(FORMATS))
    documents = request.get("documents", True)
    for field in ("documents", "overwrite"):
        require(type(request.get(field, False)) is bool, f"{field} must be true or false", field=field)
    spec = request.get("spec")
    if spec is not None:
        from ...production import plan

        require(isinstance(spec, dict), "spec is a campaign spec (the run action's spec)", field="spec")
        plan(spec)
    require(documents or formats or spec is not None,
            "Nothing to write: keep documents, or give formats or a campaign spec", field="documents")
    opts = options(project, request_options(request))
    strings = request_strings(project, request)
    table, sources = locale_table(project, strings, opts)
    source = opts.get("source", DEFAULT_SOURCE)
    codes = select(request.get("locales"), table, source)
    suites = suite_names(project, request)
    directory = session.resolve(request.get("output_dir", "localized"))
    directory.mkdir(parents=True, exist_ok=True)
    master = Path(document).stem if document else "document"
    settings = {"formats": formats, "documents": documents, "checks": request.get("checks"), "suites": suites,
                "suite": request.get("suite"), "fail_on": fail_on, "spec": spec, "min_size": opts.get("min_size"),
                "fit": opts.get("fit", "flag")}
    with file_lock(str(directory / RECORD)):
        record_path = directory / RECORD
        previous = read_json(record_path) if record_path.exists() else {"version": 1, "locales": {}}
        require(previous.get("version") == 1, "Unsupported localize record version", field="output_dir")
        prior = previous.get("locales", {})
        owned = _owned(prior)
        baseline = None
        results = {}
        for code in codes:
            candidate, notes = localized(project, code, table, opts, fit=True)
            missing = missing_keys(table, code, strings)
            fingerprint = _fingerprint(candidate, {**settings, "missing": missing, "master": master, "code": code})
            before = prior.get(code)
            if before and before.get("fingerprint") == fingerprint and _intact(directory, before):
                results[code] = {**before, "status": "reused" if before["status"] in ("completed", "reused")
                                 else before["status"], "reused": True}
                continue
            if baseline is None:
                base, _ = localized(project, source, table, {**opts, "mirror": False}, fit=True)
                baseline = evaluate(base, request, suites)
            current = evaluate(candidate, request, suites)
            found, lines = compare(code, candidate, current, baseline, table, source, opts, strings)
            verdict = status(found, fail_on)
            entry = {"locale": code, "fingerprint": fingerprint, **verdict, "findings": found,
                     **({"missing": missing} if missing else {}),
                     **({"lines": {name: list(pair) for name, pair in lines.items()}} if lines else {}),
                     **{key: value for key, value in notes.items() if value}}
            if verdict["failing"] or missing:
                entry["status"] = "held"
                entry["reason"] = (f"{len(missing)} missing key(s)" if missing else
                                   f"{verdict['failing']} finding(s) at fail_on {fail_on}")
                results[code] = entry
                continue
            outputs = []
            derived = derive(candidate, code, master)
            if documents:
                relative = f"{master}.{code}.vixl"
                path = directory / relative
                _writable(path, relative, owned, request.get("overwrite", False))
                derived.save(path, overwrite=True)
                outputs.append({"path": relative, "sha256": _digest_file(path)})
            for fmt in formats:
                relative = f"{master}.{code}.{fmt}"
                path = directory / relative
                _writable(path, relative, owned, request.get("overwrite", False))
                derived.export(path, overwrite=True)
                outputs.append({"path": relative, "sha256": _digest_file(path)})
            if spec is not None:
                campaign = production_run(derived, spec, directory / code)
                entry["campaign"] = {"directory": code, "status": campaign["status"], "count": campaign["count"],
                                     "withheld": (campaign.get("withheld") or {}).get("count", 0)}
            entry.update(status="completed", outputs=outputs)
            results[code] = entry
        kept = {code: value for code, value in prior.items() if code not in results}
        write_json(record_path, {"version": 1, "master": document, "source": source,
                                 "locales": {**kept, **{code: {k: v for k, v in r.items() if k != "reused"}
                                                        for code, r in results.items()}}})
    held = [{"locale": code, "reason": r.get("reason"),
             "findings": [f["message"] for f in r.get("findings", []) if f["severity"] == "error"][:20]}
            for code, r in results.items() if r["status"] == "held"]
    counts = {state: sum(1 for r in results.values() if r["status"] == state)
              for state in ("completed", "reused", "held")}
    report = {
        "master": document,
        "source": source,
        "output_dir": session.relative(directory),
        "locales": codes,
        "results": results,
        "counts": counts,
        "held": held,
        "passed": not held,
        "status": "needs_review" if held else "completed",
        "matrix": {code: {kind: sum(1 for f in r.get("findings", []) if f["kind"] == kind)
                          for kind in KINDS} for code, r in results.items()},
        "sources": sources,
        "record": session.relative(record_path),
    }
    if held:
        report["message"] = (f"{len(held)} locale(s) held: {', '.join(item['locale'] for item in held)}; nothing was "
                             "written for them. Fix the findings (or set fit: shrink), then run localize again")
    if strings is not None:
        report["strings"] = {"path": strings.get("path"), "keys": len(strings["keys"]),
                             "missing": strings["missing"][:200]}
    return report
