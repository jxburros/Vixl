"""Charts and tables: data charts, tables and key-value lists drawn as ordinary, editable layers."""

PLUGIN = {
    "name": "charts",
    "title": "Charts and tables",
    "summary": "Data charts, tables and key-value lists as editable layers, with native PPTX charts and tables.",
    "kind": "operations",
    "modules": ["charts", "tables", "key_values", "chart_pptx", "table_pptx", "hooks"],
    "operations": ["charts", "tables", "key_values"],
    "commands": ["tables", "key_values", "charts"],
    "hooks": {"normalize": ["hooks:normalize"], "validate-layer": ["hooks:validate_layer"]},
    "capabilities": {"charts": ("chart table data graph plot bar pie line series key value list", ["charts"])},
}
