"""Named animations (ordered subsets of the saved frames) and edits applied to many frames at once.

Saved frames stay self-contained snapshots in ``state["animation"]["frames"]``. A named animation
only references frames by name, so one document holds an idle, a walk and a wave cycle, each with
its own order, timing and loop, and each exports on its own. ``frames-edit`` runs an operation list
against every saved frame (or one animation's frames) as part of the surrounding atomic batch."""

from copy import deepcopy
import difflib

from .errors import VixlError, require

MAX_ANIMATIONS = 64
MAX_SEQUENCE = 1024
MAX_NESTED = 200
NAMED_KEYS = {"frames", "duration", "durations", "loop"}


def check_duration(value):
    require(
        isinstance(value, int) and not isinstance(value, bool) and 10 <= value <= 60000 and value % 10 == 0,
        "Frame duration must be 10–60000 ms, in multiples of 10",
    )


def check_loop(value):
    require(
        isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 65535, "Loop must be 0–65535"
    )


def unknown_frames(names, available):
    missing = [name for name in names if name not in available]
    if not missing:
        return
    close = difflib.get_close_matches(str(missing[0]), sorted(available), 3, 0.5)
    raise VixlError(
        "frame_not_found",
        f"Unknown animation frame: {missing[0]}"
        + (f"; did you mean {' or '.join(map(repr, close))}?" if close else f". Saved frames: {', '.join(sorted(available)) or 'none'}"),
        field="order",
        suggestions=close,
    )


def validate_named(animation, frame_names):
    """Check every named animation of an animation block against the saved frame names."""
    from .design import named

    sets = animation.get("animations", {})
    require(
        isinstance(sets, dict) and len(sets) <= MAX_ANIMATIONS,
        f"A document holds at most {MAX_ANIMATIONS} named animations",
        "resource_limit",
    )
    for name, spec in sets.items():
        named(name)
        require(
            isinstance(spec, dict) and "frames" in spec and set(spec) <= NAMED_KEYS,
            f"Invalid named animation {name!r}",
        )
        order = spec["frames"]
        require(
            isinstance(order, list) and 1 <= len(order) <= MAX_SEQUENCE and all(isinstance(n, str) for n in order),
            f"Animation {name!r} needs 1–{MAX_SEQUENCE} frame names",
        )
        unknown_frames(order, frame_names)
        require(not ("duration" in spec and "durations" in spec), f"Animation {name!r}: use duration or durations")
        if "duration" in spec:
            check_duration(spec["duration"])
        if "durations" in spec:
            require(
                isinstance(spec["durations"], list) and len(spec["durations"]) == len(order),
                f"Animation {name!r}: durations needs one value per frame in order",
            )
            for value in spec["durations"]:
                check_duration(value)
        if "loop" in spec:
            check_loop(spec["loop"])


def resolve_sequence(animation, name=None):
    """The entries ``(frame, duration_ms)`` and loop count to play. Without a name that is every saved
    frame in saved order; a name selects that animation's frames, repeats and timing."""
    frames = animation.get("frames", [])
    if name is None:
        return [(frame, frame["duration"]) for frame in frames], animation.get("loop", 0)
    sets = animation.get("animations", {})
    if name not in sets:
        close = difflib.get_close_matches(str(name), sorted(sets), 3, 0.5)
        raise VixlError(
            "animation_not_found",
            f"Unknown animation: {name}"
            + (f"; did you mean {' or '.join(map(repr, close))}?" if close else f". Named animations: {', '.join(sorted(sets)) or 'none'}"),
            field="animation",
            suggestions=close,
            available=sorted(sets),
        )
    spec = sets[name]
    by_name = {frame["name"]: frame for frame in frames}
    entries = []
    for index, frame_name in enumerate(spec["frames"]):
        frame = by_name[frame_name]
        duration = spec["durations"][index] if "durations" in spec else spec.get("duration", frame["duration"])
        entries.append((frame, duration))
    return entries, spec.get("loop", animation.get("loop", 0))


def summaries(animation):
    """Named animations as ``{name: {loop, total_duration, frames: [{name, duration}]}}``."""
    result = {}
    for name in animation.get("animations", {}):
        entries, loop = resolve_sequence(animation, name)
        result[name] = {
            "loop": loop,
            "total_duration": sum(duration for _, duration in entries),
            "frames": [{"name": frame["name"], "duration": duration} for frame, duration in entries],
        }
    return result


def set_named(animation, op):
    """``animation-set`` with a name: define, update or delete one named animation."""
    from .design import named

    name = named(op["name"])
    sets = animation.get("animations", {})
    if op.get("delete"):
        require(
            not any(key in op for key in ("order", "duration", "durations", "loop")),
            "delete cannot be combined with order, duration, durations or loop",
        )
        require(name in sets, f"Unknown animation: {name}", "animation_not_found", field="name")
        del sets[name]
        if not sets:
            animation.pop("animations", None)
        return
    require(
        not ("duration" in op and "durations" in op),
        "Use duration (one value for every frame) or durations (one per frame), not both",
    )
    frame_names = {frame["name"] for frame in animation["frames"]}
    if "order" in op:
        # A full definition: the previous timing and loop of a replaced animation do not carry over.
        spec = {"frames": list(op["order"])}
    else:
        require(
            name in sets,
            f"Unknown animation: {name}; pass order to define it",
            "animation_not_found",
            field="name",
        )
        spec = deepcopy(sets[name])
    unknown_frames(spec["frames"], frame_names)
    for key in ("duration", "durations", "loop"):
        if key in op:
            spec[key] = deepcopy(op[key])
    if "duration" in op:
        spec.pop("durations", None)
    if "durations" in op:
        spec.pop("duration", None)
    require(
        "durations" not in spec or len(spec["durations"]) == len(spec["frames"]),
        "durations needs one value per frame in order",
        field="durations",
    )
    animation.setdefault("animations", {})[name] = spec
    validate_named(animation, frame_names)


def used_by(animation, frame_name):
    return [name for name, spec in animation.get("animations", {}).items() if frame_name in spec["frames"]]


def target_frames(animation, op):
    """The saved frames a ``frames-edit`` reaches: named ones, one animation's, or all of them."""
    frames = animation.get("frames", [])
    require(not ("frames" in op and "animation" in op), "Use frames or animation, not both", field="frames")
    if "animation" in op:
        entries, _ = resolve_sequence(animation, op["animation"])
        names = list(dict.fromkeys(frame["name"] for frame, _ in entries))
    elif "frames" in op:
        names = list(op["frames"])
        unknown_frames(names, {frame["name"] for frame in frames})
    else:
        names = [frame["name"] for frame in frames]
    by_name = {frame["name"]: frame for frame in frames}
    return [by_name[name] for name in names]


def nested_operations(operations):
    """Validate and normalize the operation list once, before any frame is touched."""
    from .animation import ANIMATION_TYPES
    from .interfaces import service_check
    from .schema import validate_operation

    require(
        isinstance(operations, list) and 1 <= len(operations) <= MAX_NESTED,
        f"frames-edit needs 1–{MAX_NESTED} operations",
        field="operations",
    )
    result = []
    for index, operation in enumerate(operations):
        try:
            checked = validate_operation(operation)
            require(checked["type"] not in ANIMATION_TYPES, "Animation operations cannot be nested in frames-edit")
            require(
                checked["type"] not in ("layout-apply", "template-apply", "page") and "page" not in checked,
                "Layouts, templates and pages cannot be applied through frames-edit",
            )
            service_check(checked)
        except VixlError as exc:
            raise VixlError(exc.code, f"frames-edit operations[{index}]: {exc}", **{"field": "operations", **exc.details}) from exc
        result.append(checked)
    return result


def edit_state(project, operations, label):
    """Run validated operations on ``project`` (a frame copy or the scene), as a batch would."""
    from .normalize import apply_centering, resolve_geometry
    from .operations import execute
    from .validation import check_state

    for index, operation in enumerate(operations):
        try:
            resolved, centered = resolve_geometry(project, operation)
            execute(project, deepcopy(resolved))
            apply_centering(project, centered, operation)
        except VixlError as exc:
            details = {k: v for k, v in exc.details.items() if k != "operation_index"}
            raise VixlError(
                exc.code,
                f"frames-edit on {label}, operations[{index}] ({operation['type']}): {exc}",
                **details,
            ) from exc
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise VixlError(
                "invalid_operation",
                f"frames-edit on {label}, operations[{index}] ({operation['type']}): Malformed operation: {exc}",
            ) from exc
    try:
        check_state(project, project.state)
    except VixlError as exc:
        raise VixlError(exc.code, f"frames-edit on {label}: {exc}", **exc.details) from exc


def frames_edit(project, op):
    """Apply ``operations`` to each saved frame (or an animation's / the listed frames) and, with
    ``scene``, to the working scene. The surrounding batch makes the whole edit atomic."""
    from .animation import frame_project

    animation = project.state["animation"]
    operations = nested_operations(op["operations"])
    targets = target_frames(animation, op)
    scene = op.get("scene", False)
    require(targets or scene, "Save at least one animation frame before using frames-edit", field="operations")
    # Operations may be repeated per frame, so bound the total work like any other expansion.
    require(
        len(operations) * (len(targets) + scene) <= 20 * project.limits.max_operations,
        "frames-edit expands to too many operations; edit fewer frames or split the work",
        "resource_limit",
    )
    for frame in targets:
        edited = frame_project(project, frame)
        edit_state(edited, operations, f"frame {frame['name']!r}")
        frame["state"] = edited.state
    if scene:
        edit_state(project, operations, "the working scene")
