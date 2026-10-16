"""Workflow actions for lyric videos: plan, build and export."""

from .lyrics import REQUEST_FIELDS

PATH = {"type": "string", "description": "Workspace-relative path."}
ACTIONS = {
    "lyric-video-plan": (REQUEST_FIELDS, {"audio", "lyrics", "template"}),
    "lyric-video-build": (REQUEST_FIELDS, {"audio", "lyrics", "template", "build"}),
    "lyric-video-export": (REQUEST_FIELDS, {"audio", "lyrics", "template", "build", "output"}),
}
LYRIC_TYPES = {
    "build": {**PATH, "description": "The built timeline document (.vixl); an editable keyframed copy of the template. "
              "Export renders an existing build as it is, hand edits included, while it still matches the request."},
    "rebuild": {"type": "boolean", "description": "Export only: build the document again from the template and LRC, "
                "replacing an existing build and discarding hand edits in it."},
    "animation": {"type": "object", "description": "Lyric entry and exit: in, out, duration (ms), distance (px)."},
    "cue_animation": {"type": "object", "description": "How cue-* layers enter, leave and move while their words are sung: "
                      "in, out (as animation; default none, a cut), duration, distance, motion (none or sweep: a swing about "
                      "the layer's pivot), amount (degrees, default 12), period (ms for a back-and-forth, default 2800), "
                      "replay (true: the cue layer's own template keys restart at each window), and cues: per-layer "
                      "overrides of any of these keyed by cue layer name, e.g. {\"cue-cell\": {\"in\": \"slide-in-down\"}}."},
}
FIELD_TYPES = {action: LYRIC_TYPES for action in ACTIONS}


def dispatch(session, action, request, document=None):
    from . import lyrics

    step = {"lyric-video-plan": lyrics.plan, "lyric-video-build": lyrics.build, "lyric-video-export": lyrics.export}[action]
    return step(request, session.workspace, session.limits)
