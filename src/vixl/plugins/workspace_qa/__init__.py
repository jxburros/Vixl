"""Workspace QA: checks over many documents, find and replace across them, protected edits, proofs, reproducibility, delivery."""

PLUGIN = {
    "name": "workspace_qa",
    "title": "Workspace QA",
    "summary": "check-all and replace-across over many documents, protected edits, proof pages, render lockfiles and "
               "deliverable packages.",
    "kind": "workflows",
    "modules": ["workspace_checks", "replace_across", "protected_edit", "proof", "reproduce", "export_lock", "package",
                "dependents", "candidate", "workflow"],
    "workflows": ["workflow"],
    "requires": ["teamwork", "ai"],
}
