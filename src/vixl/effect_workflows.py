"""Portable multi-tool effects: inspect, customize, save, then apply atomically."""

from .errors import require

WORKFLOWS = {
    "neon-sign": {
        "description": "Color overlay, outer glow and offset shadow for luminous lettering or line art.",
        "defaults": {"target": "artwork", "color": "#00f5d4"},
        "operations": [
            {
                "type": "layer-style",
                "target": "${target}",
                "name": "color-overlay",
                "settings": {"color": "${color}"},
            },
            {
                "type": "layer-style",
                "target": "${target}",
                "name": "outer-glow",
                "settings": {"color": "${color}", "blur": 12, "opacity": 0.8},
            },
            {
                "type": "layer-style",
                "target": "${target}",
                "name": "drop-shadow",
                "settings": {"color": "${color}", "blur": 24, "dy": 2, "opacity": 0.5},
            },
        ],
    },
    "vintage-print": {
        "description": "Sepia toning, deterministic grain and a vignette for an aged print.",
        "defaults": {"target": "artwork"},
        "operations": [
            {"type": "effect", "target": "${target}", "name": "sepia", "amount": 70},
            {"type": "effect", "target": "${target}", "name": "grain", "amount": 0.06, "seed": 7},
            {"type": "effect", "target": "${target}", "name": "vignette", "amount": 0.35},
        ],
    },
    "comic-poster": {
        "description": "High contrast, posterization and halftone screening.",
        "defaults": {"target": "artwork"},
        "operations": [
            {"type": "effect", "target": "${target}", "name": "contrast", "amount": 25},
            {"type": "effect", "target": "${target}", "name": "posterize", "amount": 4},
            {"type": "effect", "target": "${target}", "name": "halftone", "amount": 6},
        ],
    },
    "cut-paper": {
        "description": "Flat color, a crisp outline and a soft offset shadow.",
        "defaults": {"target": "artwork", "color": "#e76f51"},
        "operations": [
            {
                "type": "layer-style",
                "target": "${target}",
                "name": "color-overlay",
                "settings": {"color": "${color}"},
            },
            {
                "type": "layer-style",
                "target": "${target}",
                "name": "stroke",
                "settings": {"color": "white", "width": 2},
            },
            {
                "type": "layer-style",
                "target": "${target}",
                "name": "drop-shadow",
                "settings": {"color": "black", "blur": 4, "dx": 5, "dy": 8, "opacity": 0.4},
            },
        ],
    },
    "ink-illustration": {
        "description": "Grayscale, sketch contours and contrast for an ink drawing.",
        "defaults": {"target": "artwork"},
        "operations": [
            {"type": "effect", "target": "${target}", "name": "grayscale", "amount": 100},
            {"type": "effect", "target": "${target}", "name": "pencil-sketch", "amount": 70},
            {"type": "effect", "target": "${target}", "name": "contrast", "amount": 20},
        ],
    },
}

SUITES = {
    "containers": {
        "description": "Check container bounds, padding, flow/grid layout and item limits after editing.",
        "rules": [{"id": "containers", "kind": "container"}],
    },
    "delivery": {
        "description": "Bounds, placeholder copy and text contrast before delivery.",
        "rules": [
            {"id": "delivery", "kind": "design", "options": {"checks": ["bounds", "blanks", "contrast"]}}
        ],
    },
    "palette": {
        "description": "Check rendered pixels against the active palette (8 RGB levels, 1% allowance).",
        "rules": [{"id": "palette", "kind": "palette", "tolerance": 8, "max_fraction": 0.01}],
    },
    "opaque": {
        "description": "No unintended transparency.",
        "rules": [{"id": "opaque", "kind": "alpha", "maximum": 0}],
    },
    "print-ready": {
        "description": "Print resolution, ink and safe area checks.",
        "rules": [{"id": "print", "kind": "design", "options": {"checks": ["print", "safe_area"]}}],
    },
    "accessible": {
        "description": "Text contrast, legibility and color-vision checks.",
        "rules": [
            {
                "id": "accessible",
                "kind": "design",
                "options": {"checks": ["contrast", "legibility", "color_vision"]},
            }
        ],
    },
    "no-placeholders": {
        "description": "Catch unfinished template copy.",
        "rules": [{"id": "copy", "kind": "design", "options": {"checks": ["blanks"]}}],
    },
}


def validate(value):
    from .automation import bounded_object, validate_action
    from .resources import substitute

    bounded_object(value, {"description", "defaults", "operations"}, "Unknown effect workflow field")
    require(isinstance(value.get("defaults", {}), dict), "Workflow defaults must be an object")
    validate_action({"operations": substitute(value.get("operations"), value.get("defaults", {}))})


def apply(project, value, variables=None, dry_run=False):
    from .resources import substitute
    from .interfaces import service_check

    validate(value)
    return project.apply(
        substitute(value["operations"], {**value.get("defaults", {}), **(variables or {})}),
        check=service_check,
        detail="compact",
        dry_run=dry_run,
    )
