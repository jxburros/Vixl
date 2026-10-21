"""Layers drawn ahead on the render pool (#590): the pixels are those of a sequential render."""

import io
import os
import random
import threading
import time

import numpy as np
from PIL import Image
import pytest

from vixl import Project
from vixl import render as R


def pixels(image):
    return np.asarray(image.convert("RGBA"))


def busy_document():
    """Styled, blurred, clipped, grouped and raster layers, so every path of the compositor is taken."""
    random.seed(11)
    p = Project(1600, 1200, "white")
    noise = io.BytesIO()
    Image.effect_noise((300, 200), 50).convert("RGB").save(noise, format="PNG")
    p.import_image(data=noise.getvalue(), name="photo")
    ops = [{"type": "move", "target": "photo", "x": 40, "y": 30}]
    for i in range(24):
        ops.append({"type": "shape", "shape": random.choice(["ellipse", "rectangle", "star"]), "name": f"s{i}",
                    "x": random.randint(0, 1400), "y": random.randint(0, 1000), "width": random.randint(60, 300),
                    "height": random.randint(60, 300), "fill": random.choice(["#e63", "#369", "#9c3", "#fc0"])})
    ops.append({"type": "gradient", "name": "wash", "width": 900, "height": 700, "x": 300, "y": 200,
                "start": "#ff000080", "end": "#0000ff40", "direction": "radial"})
    ops.append({"type": "look", "look": "soft-shadow", "targets": [f"s{i}" for i in range(0, 24, 2)]})
    ops += [{"type": "effect", "target": f"s{i}", "name": "blur", "amount": 6} for i in range(1, 24, 4)]
    ops.append({"type": "group", "targets": ["s3", "s7"], "name": "pair"})
    ops.append({"type": "layer-style", "target": "pair", "name": "drop-shadow", "settings": {"blur": 12, "dy": 8}})
    ops.append({"type": "clip", "target": "s9", "base": "s10"})
    ops.append({"type": "blend", "target": "s11", "value": "multiply"})
    p.apply(ops, detail="brief")
    return p


def rendered(project, threads, monkeypatch):
    monkeypatch.setenv("VIXL_RENDER_THREADS", str(threads))
    monkeypatch.setattr(R, "PREFETCH_MIN_PIXELS", 0)
    project._cache = R.LayerCache()
    project._decoded.clear()
    return pixels(R.render(project))


def test_threads_draw_the_same_pixels_as_one(monkeypatch):
    p = busy_document()
    one = rendered(p, 1, monkeypatch)
    calls = []
    original = R.Prefetch.refill

    def refill(self):
        calls.append(len(self.queue) + len(self.pending))
        return original(self)

    monkeypatch.setattr(R.Prefetch, "refill", refill)
    four = rendered(p, 4, monkeypatch)
    assert np.array_equal(one, four)
    assert max(calls) > 0  # the pool did draw layers ahead


def test_layer_cache_is_threadsafe():
    cache = R.LayerCache(entries=16, budget=40 * 40 * 4 * 12)
    errors = []

    def hammer(seed):
        rng = random.Random(seed)
        try:
            for _ in range(2000):
                key = rng.randrange(40)
                if cache.image(key) is None:
                    cache.put(key, Image.new("RGBA", (rng.randint(10, 40), 40)))
        except Exception as error:  # the assertion below names it
            errors.append(error)

    threads = [threading.Thread(target=hammer, args=(seed,)) for seed in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert cache.bytes == sum(image.width * image.height * 4 for image in cache.values())
    assert len(cache) <= cache.entries


def test_pool_is_off_with_zero_threads_and_inside_its_own_workers(monkeypatch):
    monkeypatch.setenv("VIXL_RENDER_THREADS", "0")
    assert R.render_pool() is None and R.render_threads() == 0
    monkeypatch.setenv("VIXL_RENDER_THREADS", "nonsense")
    assert R.render_threads() == 0


@pytest.mark.perf
@pytest.mark.skipif((os.cpu_count() or 1) < 4 or "PYTEST_XDIST_WORKER" in os.environ,
                    reason="a speedup is measured on four idle cores: run pytest -m perf without -n")
def test_soft_shadowed_shapes_render_faster_on_the_pool(monkeypatch):
    p = Project(4000, 4000, "white")
    p.apply([{"type": "shape", "shape": "ellipse", "name": f"c{i}", "x": (i % 10) * 380 + 100,
              "y": (i // 10) * 380 + 100, "width": 300, "height": 300, "fill": "#e63"} for i in range(80)],
            detail="brief")
    p.apply({"type": "look", "look": "soft-shadow", "targets": [f"c{i}" for i in range(80)]}, detail="brief")

    def best(threads):
        monkeypatch.setenv("VIXL_RENDER_THREADS", str(threads))
        times = []
        for _ in range(3):
            p._cache = R.LayerCache()
            started = time.perf_counter()
            R.render(p)
            times.append(time.perf_counter() - started)
        return min(times)

    sequential, pooled = best(1), best(4)
    assert pooled < 0.85 * sequential, (pooled, sequential)
