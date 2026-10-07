# Vixl 0.22.0 QA, stress and exploration report

QA pass over the published v0.22.0 release (wheel from the GitHub release, Linux x86-64, Python 3.13).

- `vixl-0.22.0-qa-report.pdf`: the 24-page report, typeset with Vixl itself.
- `vixl-0.22.0-qa-report.vixl`: its editable master.
- `all-findings.json` / `all-findings.csv`: all 177 recorded checks (100 issues, 77 passes) with repro steps.
- `build_report.py` + `content.json`: rebuild the report with the Vixl Python API:
  `python build_report.py <qa-dir> <out-dir>` (the qa-dir with every area's `findings.json` and evidence ships in the
  separate assets zip, which is too large for the repository).

Headline: the project's 2,832 tests pass against the wheel and nothing crashed, hung or escaped the sandbox. The issues
cluster in raster rendering of open stroked paths (EXP-01), SVG/PDF/PPTX parity, the logo-package workflow, and
per-edit cost on large documents.
