"""Messages an operation raises while it runs, reported in the result of ``Project.apply``.

``warn`` says something was dropped or did not take effect (``warnings``); ``note`` records an
interpretation the caller should learn (``normalized``, next to the spelling rewrites). Both are
collected only while ``Project.apply`` runs, so operations called directly stay silent.
"""


def warn(project, message):
    """Report that an operation dropped or ignored something."""
    queue = getattr(project, "_warnings", None)
    if queue is not None and message not in queue:
        queue.append(message)


def note(project, message):
    """Report how an operation was interpreted."""
    queue = getattr(project, "_notes", None)
    if queue is not None and message not in queue:
        queue.append(message)


def start(project):
    project._warnings, project._notes = [], []


def finish(project):
    """The (warnings, notes) collected since ``start``."""
    return project.__dict__.pop("_warnings", []), project.__dict__.pop("_notes", [])
