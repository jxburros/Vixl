"""Pipelines: saved multi-step runs over many documents, completion webhooks, data sync and bulk upgrades."""

PLUGIN = {
    "name": "pipelines",
    "title": "Pipelines",
    "summary": "Saved, resumable pipelines over many documents with a run record, completion webhooks, data sync "
               "from a CSV and bulk structure upgrades.",
    "kind": "workflows",
    "modules": ["spec", "runner", "notify", "candidate", "data_sync", "bulk_upgrade", "workflow"],
    "workflows": ["workflow"],
    "hooks": {"job-kind": ["runner:job_kind"], "job-complete": ["notify:deliver"],
              "resource-kind": ["spec:resource_kind"]},
    "requires": ["workspace_qa", "teamwork"],
}
