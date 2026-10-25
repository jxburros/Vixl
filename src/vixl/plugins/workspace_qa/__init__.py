"""Workspace QA: checks over many documents, find and replace across them, protected edits, proofs, reproducibility,
delivery, approved baselines, the workspace dependency graph and link impact."""

PLUGIN = {
    "name": "workspace_qa",
    "title": "Workspace QA",
    "summary": "check-all and replace-across over many documents, protected edits, proof pages, render lockfiles, "
               "deliverable packages, approved baselines and link impact.",
    "kind": "workflows",
    "modules": ["workspace_checks", "replace_across", "protected_edit", "proof", "reproduce", "export_lock", "package",
                "approval", "dependents", "candidate", "link_impact", "commands", "workflow"],
    "workflows": ["workflow"],
    "hooks": {"check": ["approval:check"], "production-report": ["approval:production_report"],
              "cli-command": ["commands:command"]},
    "requires": ["teamwork", "ai"],
}
