"""Print imposition: data merge from a template document and a CSV into n-up sheets."""

PLUGIN = {
    "name": "imposition",
    "title": "Print imposition",
    "summary": "Merge CSV rows into a template and impose the copies n-up on press sheets with marks and bleed.",
    "kind": "workflows",
    "modules": ["imposition", "workflow"],
    "workflows": ["workflow"],
}
