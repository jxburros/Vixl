"""``vixl convert OLD.vixl|DIR …`` and ``vixl convert-batch OLD.json …``."""

import argparse
import json
from pathlib import Path

from ..errors import require


def _parser(prog):
    from ..cli import Parser

    return Parser(prog=prog)


def convert(args):
    p = _parser("vixl convert")
    p.add_argument("source", help="An old .vixl document, or a folder converted recursively (with --out)")
    p.add_argument("-o", "--out", "--output", dest="out",
                   help="The converted document (default NAME-converted.vixl), or the folder for a folder")
    p.add_argument("--look", choices=["preserve", "current"], default="preserve",
                   help="preserve (default): keep the old look with explicit fields; current: take today's defaults "
                        "and report what looks different")
    p.add_argument("--dry-run", action="store_true", help="Convert and check, write nothing")
    p.add_argument("--report", help="Also write the report as JSON to this file")
    p.add_argument("--overwrite", action="store_true", help="Replace existing output files")
    p.add_argument("--history", choices=["keep", "drop"], default="keep",
                   help="keep (default): convert every undo revision; drop: start a new history")
    p.add_argument("--saved-by", help="The release that saved the document, when its vixl_version is wrong")
    p.add_argument("--batch", action="store_true", help="The source is saved tool calls (same as convert-batch)")
    a = p.parse_args(args)
    if a.batch:
        return convert_batch(args)
    from .documents import convert_directory, convert_file, summarize

    source = Path(a.source)
    options = dict(look=a.look, dry_run=a.dry_run, overwrite=a.overwrite, history=a.history, saved_by=a.saved_by)
    if source.is_dir():
        require(a.out, "Converting a folder needs --out OUTDIR (a new folder; sources are never overwritten)",
                field="out")
        result = convert_directory(source, a.out, **options)
    else:
        result = summarize([convert_file(source, a.out, **options)])
    _write_report(a.report, result, a.overwrite)
    return result


def convert_batch(args):
    p = _parser("vixl convert-batch")
    p.add_argument("source", help="Saved MCP tool calls, operation batches or an MCP config (.json or .jsonl)")
    p.add_argument("-o", "--out", "--output", dest="out", help="Default NAME-converted.json")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--report")
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--batch", action="store_true", help=argparse.SUPPRESS)
    a = p.parse_args(args)
    from .batches import convert_batch_file

    report = convert_batch_file(a.source, a.out, dry_run=a.dry_run, overwrite=a.overwrite)
    result = {"converted": [report], "failed": [],
              "summary": {"files": 1, "converted": 1, "failed": 0, "changes": report["counts"]["changes"],
                          "warnings": report["counts"]["warnings"]}}
    _write_report(a.report, result, a.overwrite)
    return result


def _write_report(path, result, overwrite):
    if not path:
        return
    path = Path(path)
    require(overwrite or not path.exists(), f"{path} exists; pass --overwrite to replace it", "output_exists",
            field="report")
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
