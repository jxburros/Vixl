"""Render profiling: where a render spends its time and what its caches did.

With ``VIXL_PROFILE=1`` in the environment, every CLI command, MCP tool call and REST request records a
profile and returns it next to its result as ``render_profile`` (CLI ``--json`` and dict results, MCP result
envelopes, REST JSON bodies and the ``X-Vixl-Profile`` header). Python callers use ``profile()``:

    with profiling.profile() as run:
        project.render()
    run.report()

Without a profile the renderer only reads one context variable per layer, so it costs nothing measurable.
The profile is per call (a context variable), so concurrent MCP calls do not mix; the rasterised-SVG
cache counters are process-wide and include other calls running at the same time.
"""

from collections import defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
import os
import statistics
import time

ACTIVE = ContextVar("vixl_profile", default=None)
OFF = ("", "0", "off", "false", "no")
TOP_LAYERS = 25


def enabled():
    """Whether ``VIXL_PROFILE`` asks for profiles."""
    return os.environ.get("VIXL_PROFILE", "").strip().lower() not in OFF


def current():
    """The profile recording this call, or None (the common case: one context-variable read)."""
    return ACTIVE.get()


class Profile:
    """Per-layer draw times (exclusive of nested layers), cache counters, phase times and renders."""

    def __init__(self):
        from .vector_raster import CACHE

        self.started = time.perf_counter()
        self.layers = {}
        self.counters = defaultdict(int)
        self.phases = defaultdict(float)
        self.renders = []
        self.stack = []
        self.svg = (CACHE.hits, CACHE.misses)

    def count(self, name, amount=1):
        self.counters[name] += amount

    def phase(self, name, seconds):
        self.phases[name] += seconds

    def enter(self):
        """Start timing a layer drawn from scratch; nested layers (group children) are subtracted."""
        self.stack.append([time.perf_counter(), 0.0, defaultdict(float)])

    def stage(self, name, seconds):
        """Time spent in one stage (draw, transform, effects, styles) of the layer being drawn."""
        if self.stack:
            self.stack[-1][2][name] += seconds

    def leave(self, layer):
        start, nested, stages = self.stack.pop()
        total = time.perf_counter() - start
        if self.stack:
            self.stack[-1][1] += total
        own = max(0.0, total - nested)
        entry = self.layers.setdefault(layer["id"], {"id": layer["id"], "name": layer.get("name"), "type": layer["type"],
                                                     "ms": 0.0, "draws": 0, "stages": defaultdict(float)})
        entry["ms"] += own * 1000
        entry["draws"] += 1
        for name, seconds in stages.items():
            entry["stages"][name] += seconds * 1000
        return own

    def render(self, **details):
        self.renders.append(details)

    def report(self):
        from .vector_raster import CACHE

        layers = sorted(self.layers.values(), key=lambda entry: -entry["ms"])
        by_type = defaultdict(lambda: {"ms": 0.0, "layers": 0})
        for entry in layers:
            by_type[entry["type"]]["ms"] += entry["ms"]
            by_type[entry["type"]]["layers"] += 1
        counters = dict(self.counters)
        counters["svg_hits"] = CACHE.hits - self.svg[0]
        counters["svg_misses"] = CACHE.misses - self.svg[1]
        return {
            "elapsed_ms": round((time.perf_counter() - self.started) * 1000, 2),
            "phases_ms": {name: round(seconds * 1000, 2) for name, seconds in sorted(self.phases.items())},
            "layers_drawn": len(layers),
            "layers": [{**{k: v for k, v in entry.items() if k != "stages"}, "ms": round(entry["ms"], 2),
                        "stages_ms": {k: round(v, 2) for k, v in sorted(entry["stages"].items())}}
                       for entry in layers[:TOP_LAYERS]],
            "by_type": {kind: {"ms": round(value["ms"], 2), "layers": value["layers"]}
                        for kind, value in sorted(by_type.items(), key=lambda item: -item[1]["ms"])},
            "caches": counters,
            "renders": self.renders[-20:],
            "render_count": len(self.renders),
        }

    def costly(self, ratio=10.0, floor_ms=50.0):
        """Layers whose own draw time is more than ``ratio`` times the median and at least ``floor_ms``."""
        times = [entry["ms"] for entry in self.layers.values()]
        if len(times) < 2:
            return [], 0.0
        median = statistics.median(times)
        return [entry for entry in self.layers.values()
                if entry["ms"] >= floor_ms and entry["ms"] > ratio * max(median, 1e-3)], median


@contextmanager
def profile(force=True, isolated=False):
    """Record a profile for the calls inside. ``force=False`` records only when ``VIXL_PROFILE`` is set;
    a profile already recording is reused unless ``isolated``. Yields the Profile, or None."""
    if not force and not enabled():
        yield None
        return
    running = ACTIVE.get()
    if running is not None and not isolated:
        yield running
        return
    run = Profile()
    token = ACTIVE.set(run)
    try:
        yield run
    finally:
        ACTIVE.reset(token)


def attach(result, run):
    """Add ``run``'s report to a dict result (or the dict that leads a list result); returns whether it did."""
    if run is None:
        return False
    target = result[0] if isinstance(result, list) and result and isinstance(result[0], dict) else result
    if isinstance(target, dict):
        target["render_profile"] = run.report()
        return True
    return False


def describe_cost(layer):
    """Why a layer is expensive to draw, from its fields: the biggest blur, the stroke point count, the canvas
    area of a raster, a long text, a deep effect stack or soft styles."""
    reasons = []
    effects = [effect for effect in layer.get("effects") or [] if effect.get("enabled", True)]
    blurs = [abs(effect.get("amount") or 0) for effect in effects if effect["name"] in ("blur", "gaussian-blur")]
    if blurs:
        reasons.append(f"blur radius {max(blurs):g} px")
    heavy = [effect["name"] for effect in effects if effect["name"] not in ("blur", "gaussian-blur")]
    if heavy:
        reasons.append("effects " + ", ".join(dict.fromkeys(heavy)))
    if layer.get("strokes"):
        points = sum(len(stroke.get("points") or []) for stroke in layer["strokes"])
        reasons.append(f"{len(layer['strokes']):,} paint strokes with {points:,} points")
    for name, settings in (layer.get("styles") or {}).items():
        if settings.get("enabled", True) and settings.get("blur"):
            reasons.append(f"{name} blur {settings['blur']:g} px")
    if layer["type"] == "text" and len(str(layer.get("text", ""))) > 500:
        reasons.append(f"{len(str(layer['text'])):,} characters of text")
    if layer.get("repeat"):
        reasons.append(f"{layer['repeat'].get('count', 0)} repeated copies")
    width, height = layer.get("width") or 0, layer.get("height") or 0
    if width * height >= 4_000_000:
        reasons.append(f"{round(width):,}×{round(height):,} px")
    return reasons


def cost_findings(project, ratio=10.0, floor_ms=50.0):
    """The ``cost`` check: draw the document once with empty caches and report each layer whose own draw time
    is more than ``ratio`` times the median layer's (and at least ``floor_ms``), naming what makes it costly."""
    from collections import OrderedDict

    from .render import LayerCache, render

    probe = project.clone()
    probe._cache, probe._paint_cache, probe._disk_cache = LayerCache(), OrderedDict(), None
    with profile(isolated=True) as run:
        render(probe)
    costly, median = run.costly(ratio, floor_ms)
    stored = {layer["id"]: layer for layer in probe.state["layers"]}
    findings = []
    for entry in sorted(costly, key=lambda item: -item["ms"]):
        layer = stored.get(entry["id"], entry)
        causes = describe_cost(layer) if entry["id"] in stored else []
        stage = max(entry["stages"].items(), key=lambda item: item[1])[0] if entry["stages"] else None
        message = (f"{entry['name']!r} takes {entry['ms']:,.0f} ms to draw, {entry['ms'] / max(median, 1e-3):,.0f}× the "
                   f"median layer ({median:.2f} ms)" + (f": {', '.join(causes)}" if causes else "")
                   + ". Every render, preview and timeline frame pays it when the layer changes; lower it, or "
                   "rasterize the layer if it is final.")
        findings.append({"layer": entry["id"], "message": message, "ms": round(entry["ms"], 1),
                         "median_ms": round(median, 2), "causes": causes, **({"stage": stage} if stage else {})})
    return findings
