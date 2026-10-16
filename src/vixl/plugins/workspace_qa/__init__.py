"""Workspace QA: checks over many documents, find and replace across them, protected edits, proofs, reproducibility."""

PLUGIN = {
    "name": "workspace_qa",
    "title": "Workspace QA",
    "summary": "check-all and replace-across over many documents, protected edits, proof pages and render lockfiles.",
    "kind": "workflows",
    "modules": ["workspace_checks", "replace_across", "protected_edit", "proof", "reproduce", "workflow"],
    "workflows": ["workflow"],
    "requires": ["teamwork"],
}
