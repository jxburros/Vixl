"""Diagrams: flowcharts, org charts, timelines and other node-and-connector layouts that re-route on edit."""

PLUGIN = {
    "name": "diagrams",
    "title": "Diagrams",
    "summary": "Node-and-connector diagrams with automatic layout and routing, kept live as nodes move.",
    "kind": "operations",
    "modules": ["diagrams", "diagram_layout", "hooks"],
    "operations": ["diagrams"],
    "commands": ["diagrams"],
    "hooks": {
        "validate-state": ["hooks:validate_state"],
        "check": ["hooks:check"],
        "after-apply": ["hooks:after_apply"],
        "apply-report": ["hooks:apply_report"],
    },
}
