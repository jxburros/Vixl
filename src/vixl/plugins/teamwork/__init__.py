"""Teamwork: workspace branches with three-way merges, document groups with checked bulk edits, suite inference."""

PLUGIN = {
    "name": "teamwork",
    "title": "Teamwork",
    "summary": "Workspace branches and merges, document groups with shared parameters and rollback, suite inference.",
    "kind": "workflows",
    "modules": ["collaboration", "project_groups", "suite_infer", "workflow"],
    "workflows": ["workflow"],
    "requires": ["workspace_qa"],
}
