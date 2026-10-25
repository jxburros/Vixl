"""Workflow actions for pipelines, watch, data sync and bulk upgrades."""

from ...errors import VixlError
from .notify import SCHEMA as NOTIFY
from .runner import REQUEST as RUN_FIELDS
from .data_sync import REQUEST as SYNC_FIELDS
from .bulk_upgrade import REQUEST as UPGRADE_FIELDS
from .watch import REQUEST as WATCH_FIELDS

ACTIONS = {
    "pipeline-run": (RUN_FIELDS, {"pipeline"}),
    "data-sync": (SYNC_FIELDS, {"bind"}),
    "bulk-upgrade": (UPGRADE_FIELDS, set()),
    "watch": (WATCH_FIELDS, set()),
}
PATH = {"type": "string", "description": "Workspace-relative path."}
DOCUMENTS = {"type": "array", "items": {"type": "string", "description": "A glob or path."},
             "description": "Documents: workspace globs or paths (.vixl-* folders are skipped)."}
LEVEL = {"type": "string", "enum": ["error", "warning", "fix", "review", "never"], "default": "error",
         "description": "The check level a finding must reach to fail (as check-all's fail_on)."}
EXPORTS = {"type": "array", "maxItems": 16, "items": {"type": "object", "description": "An export target: path "
           "(with {doc}, {dir} and {key}) plus vixl_export options."},
           "description": "Group bindings: export targets written again for the members a sync changed."}
FIELD_TYPES = {
    "pipeline-run": {
        "pipeline": {"type": ["string", "object"], "description": "A saved pipeline name (resource-save kind "
                     "pipelines) or an inline pipeline {version: 1, targets, steps, on_fail, inputs}."},
        "run": {"type": "string", "description": "Run id: the record is .vixl-runs/<run>/run.json, and running the "
                "same id again resumes it (default: the pipeline name)."},
        "documents": {**DOCUMENTS, "description": "Run over these documents instead of the pipeline's targets."},
        "group": {"type": "string", "description": "Run over this project group's members instead of the targets."},
        "dry_run": {"type": "boolean", "description": "List every planned step and output, and which a run would "
                    "reuse, without writing (default true while the run has no record)."},
        "notify": NOTIFY,
    },
    "data-sync": {
        "bind": {"type": "object", "description": "{data: CSV, key: column, to: {group: NAME} | {spec: campaign.json} "
                 "| {merge: sheets.vixl}}.",
                 "properties": {"data": {**PATH, "description": "The CSV, one row per key."},
                                "key": {"type": "string", "description": "The column whose value identifies a row."},
                                "to": {"type": "object", "description": "What the rows drive: a group (members "
                                       "bound by their variable of the key's name), a campaign file {source, "
                                       "output, spec} or a merge sheet document."}}},
        "name": {"type": "string", "description": "Binding name: the snapshot is .vixl-runs/data/<name>.json "
                 "(default: the CSV's name)."},
        "dry_run": {"type": "boolean", "default": False, "description": "Report the row diff and planned outputs; "
                    "write nothing."},
        "exports": EXPORTS,
        "fail_on": LEVEL,
        "suites": {"type": "boolean", "default": True, "description": "Run each changed member's attached suites."},
        "overwrite": {"type": "boolean", "default": False, "description": "Let re-exports replace files the sync "
                      "did not write itself."},
    },
    "bulk-upgrade": {
        "documents": DOCUMENTS,
        "group": {"type": "string", "description": "Upgrade this project group's members."},
        "convert": {"type": "boolean", "default": True, "description": "Convert documents saved by earlier releases "
                    "(vixl convert)."},
        "look": {"type": "string", "enum": ["preserve", "current"], "default": "preserve",
                 "description": "Conversion: keep the old look, or take the current renderer's."},
        "map": {"type": "object", "description": "{layer name pattern: {rename, role}}: rename matching layers and add "
                "them to a role.", "additionalProperties": {"type": "object", "description": "{rename?, role?}"}},
        "template": {"type": "string", "description": "Re-apply this layout (layout-apply replace), its slots filled "
                     "from the text of the roles with the slot names."},
        "dry_run": {"type": "boolean", "default": True, "description": "Report per document what would change, with "
                    "checks and the render diff; write nothing."},
        "journal": {"type": "string", "default": "bulk-upgrade", "description": "Journal name for the commit; "
                    "group-recover with it rolls an interrupted commit back."},
        "fail_on": LEVEL,
        "suites": {"type": "boolean", "default": True, "description": "Run each document's attached suites."},
    },
}
FIELD_TYPES["watch"] = {
    "config": {**PATH, "description": "The watch config file (default .vixl/watch.json)."},
    "watch": {"type": "object", "description": "An inline watch config instead of the file: {version: 1, name?, "
              "poll?, debounce?, triggers: [{on: save|source-change|brand-change|data-change|schedule, run: "
              "check|check-all|link-impact|pipeline|data-sync, documents?, group?, pipeline?, binding?, request?, "
              "every?, at?}]}."},
    "ticks": {"type": "integer", "minimum": 1, "maximum": 600, "default": 1, "description": "Polls before the "
              "watch returns (one poll a second by default); pending events then run at once."},
    "name": {"type": "string", "description": "State name: .vixl-runs/watch/<name>.json keeps the file digests and "
             "schedule times between watches (default the config's name, else watch)."},
}
SUMMARIES = {
    "pipeline-run": "Run a saved or inline pipeline (act, check, repair, export, export_check, approve per document; "
                    "proof and package once) over its documents: failing documents are held, the run record "
                    ".vixl-runs/<run>/run.json resumes unchanged steps; dry run first.",
    "data-sync": "Sync a CSV bound to a group, campaign spec or merge sheet: row diff against the last snapshot, then "
                 "check, commit and re-export only what the changed rows affect.",
    "watch": "A bounded watch: compare the workspace with the last watch's state and run the triggers that fire "
             "(save, source-change, brand-change, data-change, schedule) as check, check-all, link-impact, pipeline "
             "or data-sync; debounced, one run per document at a time. vixl watch keeps polling.",
    "bulk-upgrade": "Convert, rename/re-role and optionally re-apply the layout of many documents with checks and a "
                    "render diff before and after; dry run by default, journalled commit.",
}


def dispatch(session, action, request, document=None):
    try:
        if action == "pipeline-run":
            from .runner import run

            return run(session, request)
        if action == "data-sync":
            from .data_sync import run

            return run(session, request)
        if action == "watch":
            from .watch import run

            return run(session, request)
        from .bulk_upgrade import run

        return run(session, request)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise VixlError("invalid_request", f"Invalid {action} request: {exc}") from exc
