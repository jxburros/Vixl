"""Workflow actions for lyric videos: plan, build and export."""

from .lyrics import REQUEST_FIELDS
from .timing import ALIGN_FIELDS, EDIT_FIELDS, EXPORT_FIELDS

PATH = {"type": "string", "description": "Workspace-relative path."}
ACTIONS = {
    "lyrics-preview": ({"build", "cue", "output"}, {"build", "cue", "output"}),
    "lyrics-align": (ALIGN_FIELDS, {"audio", "lyrics", "output"}),
    "lyrics-timing-edit": (EDIT_FIELDS, {"timing", "output", "edits"}),
    "lyrics-timing-export": (EXPORT_FIELDS, {"timing", "output"}),
    "lyric-video-plan": (REQUEST_FIELDS, {"audio", "template"}),
    "lyric-video-build": (REQUEST_FIELDS, {"audio", "template", "build"}),
    "lyric-video-export": (REQUEST_FIELDS, {"audio", "template", "build", "output"}),
    "lyric-video-review": ({"build", "approve", "changes_requested", "findings"}, {"build"}),
}
LYRIC_TYPES = {
    "verify": {"type": "string", "enum": ["basic", "full"], "default": "basic",
               "description": "Delivery verification: basic checks encoded streams and every cue's timing/text; "
                              "full also decodes the file and samples up to four visual/brand frames per cue."},
    "compositions": {"type": "array", "items": {"type": "object"}, "description": "Per-cue selection rules: match section/occurrence/cue/contains, deterministic variants and layouts, attachments and part motion."},
    "timing": {**PATH, "description": "Reviewed timing JSON instead of an LRC lyrics file."},
    "build": {**PATH, "description": "The built timeline document (.vixl); an editable keyframed copy of the template. "
              "Export renders an existing build as it is, hand edits included, while it still matches the request."},
    "rebuild": {"type": "boolean", "description": "Export only: build the document again from the template and LRC, "
                "replacing an existing build and discarding hand edits in it."},
    "animation": {"type": "object", "description": "Lyric entry and exit: in, out, duration (ms), distance (px); unit: word uses word-timed typewriter entrances."},
    "cue_animation": {"type": "object", "description": "How cue-* layers enter, leave and move while their words are sung: "
                      "in, out (as animation; default none, a cut), duration, distance, motion (none or sweep: a swing about "
                      "the layer's pivot), amount (degrees, default 12), period (ms for a back-and-forth, default 2800), "
                      "replay (true: the cue layer's own template keys restart at each window), and cues: per-layer "
                      "overrides of any of these keyed by cue layer name, e.g. {\"cue-cell\": {\"in\": \"slide-in-down\"}}."},
}
FIELD_TYPES = {action: LYRIC_TYPES for action in ACTIONS}
FIELD_TYPES["lyric-video-review"] = {
    "build": PATH,
    "approve": {"type": "boolean", "description": "Record explicit human approval of this build's content."},
    "changes_requested": {"type": "boolean", "description": "Record that this build needs changes instead of approval."},
    "findings": {"type": "array", "items": {"type": "string"}, "description": "Review findings; at most 100 short strings."},
}
FIELD_TYPES["lyrics-preview"] = {"build": PATH, "output": PATH, "cue": {"type": "integer", "minimum": 0, "description": "Zero-based built cue index to preview."}}
TIMING_TYPES = {
    "audio": PATH, "lyrics": PATH, "timing": PATH, "output": PATH,
    "provider": {"type": "string", "description": "Configured HTTP or command alignment provider."},
    "replace": {"type": "boolean", "description": "Allow replacing an existing output."},
    "replace_lines": {"type": "boolean", "description": "Replace supplied LRC line starts with aligned starts."},
    "confidence": {"type": "number", "description": "Confidence below this threshold needs review (default 0.7)."},
    "edits": {"type": "array", "items": {"type": "object"}, "description": "Edits with line, optional word, and shift/start/end in milliseconds."},
}
for action in ("lyrics-align", "lyrics-timing-edit", "lyrics-timing-export"):
    FIELD_TYPES[action] = TIMING_TYPES
SUMMARIES = {
    "lyrics-preview": "Preview one built lyric cue through the film preview writer.",
    "lyric-video-review": "Record an explicit review decision for a lyric build; content edits invalidate it.",
    "lyrics-align": "Align plain or LRC lyrics through a configured provider into reviewable timing JSON.",
    "lyrics-timing-edit": "Edit line or word timestamps without invoking an alignment provider.",
    "lyrics-timing-export": "Write reviewed timing as enhanced LRC with word timestamps.",
}


def dispatch(session, action, request, document=None):
    if action == "lyrics-preview":
        from .compositions import preview
        return preview(request, session.workspace, session.limits)
    if action == "lyric-video-review":
        from .verification import review

        return review(request, session.workspace, session.limits)
    from . import lyrics, timing

    if action in ("lyrics-align", "lyrics-timing-edit", "lyrics-timing-export"):
        step = {"lyrics-align": timing.align, "lyrics-timing-edit": timing.edit, "lyrics-timing-export": timing.export}[action]
        return step(request, session.workspace, session.limits)
    step = {"lyric-video-plan": lyrics.plan, "lyric-video-build": lyrics.build, "lyric-video-export": lyrics.export}[action]
    return step(request, session.workspace, session.limits)
