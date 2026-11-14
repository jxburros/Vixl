"""The object-detect workflow action."""

from .detect import DEFAULT_CONFIDENCE, DEFAULT_TOLERANCE

ACTIONS = {"object-detect": ({"targets", "apply", "min_confidence", "tolerance", "provider"}, set())}
FIELD_TYPES = {"object-detect": {
    "targets": {"type": "array", "items": {"type": "string"}, "maxItems": 500,
                "description": "Layers or groups to look at (with everything inside them); default the whole page."},
    "apply": {"type": "boolean", "default": False,
              "description": "false (default): return the proposals and change nothing. true: apply the batches of "
              "the proposals at or above min_confidence as one undo step and run the object check on the result."},
    "min_confidence": {"type": "number", "minimum": 0, "maximum": 1, "default": DEFAULT_CONFIDENCE,
                       "description": "With apply: the lowest confidence that is applied; the rest are listed under "
                       "skipped."},
    "tolerance": {"type": "number", "minimum": 0, "maximum": 100, "default": DEFAULT_TOLERANCE,
                  "description": "Pixels of gap across which the ink of two loose layers still counts as touching."},
    "provider": {"type": ["string", "boolean"],
                 "description": "A configured AI provider name (or true for the default one): its detect results on "
                 "raster images are offered as low-confidence candidates. Left out, nothing leaves the machine and "
                 "raster images are only counted in notes."},
}}
SUMMARIES = {"object-detect": "Propose groupings and kinds for undeclared objects (recipes, names, touching ink); "
                              "a dry run unless apply is true."}


def dispatch(session, action, request, document=None):
    from .detect import detect

    apply = request.get("apply", False)
    with session.project(write=bool(apply), document=document) as project:
        return detect(project, targets=request.get("targets"), apply=apply,
                      min_confidence=request.get("min_confidence", DEFAULT_CONFIDENCE),
                      tolerance=request.get("tolerance", DEFAULT_TOLERANCE), provider=request.get("provider"))
