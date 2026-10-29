"""Render a timeline's frames in worker processes.

Text and vector shapes rasterise through resvg, which holds Python's interpreter lock, so threads cannot draw
frames side by side; processes can. Each worker loads the document once (from a saved copy), then renders
consecutive chunks of frames, so its incremental canvas stays warm within a chunk. The parent hands out at most
two chunks per worker at a time and yields the frames in order, so memory stays bounded and the encoders see
the same frames as a one-process export, byte for byte.

``VIXL_FRAME_WORKERS`` sets the number of processes (``0`` or ``1`` renders in this process). Without an override,
the first chunk renders here; its warm frame time decides whether the remaining work can repay process startup
and pixel transfer, leaving a core for the encoder. Short exports, previews and linked documents render here.
"""

from collections import deque
from dataclasses import asdict
import os
from pathlib import Path
import tempfile

from PIL import Image

MIN_FRAMES_PER_WORKER = 16
# Frames per task: a task starts on a cold canvas, so larger chunks render more frames incrementally; at most
# CHUNK, and fewer when the frames held in flight (two tasks a worker) would pass IN_FLIGHT_BYTES.
CHUNK = 16
IN_FLIGHT_BYTES = 256 * 1024 * 1024
# Conservative estimates from the animation-export measurements. A small predicted gain does not justify
# throwing away a warm canvas and starting processes. Explicit VIXL_FRAME_WORKERS bypasses this estimate.
STARTUP_SECONDS = 1.0
TRANSFER_BYTES_PER_SECOND = 512 * 1024 * 1024

_PROJECT = None  # The document a worker process renders.


def workers_for(project, count, preview=False, *, frame_seconds=None, frame_bytes=0):
    """Workers for the remaining frames (1: in-process), after measuring a warm ``frame_seconds``.

    An explicit environment override is honoured without a sample. Automatic selection stays sequential
    until measured, and requires at least a second and 25% predicted saving after startup and transfers.
    """
    value = os.environ.get("VIXL_FRAME_WORKERS", "").strip()
    try:
        workers = int(value) if value else min(4, (os.cpu_count() or 1) - 1)
    except ValueError:
        workers = 1
    if workers < 2 or preview or count < MIN_FRAMES_PER_WORKER * 2:
        return 1
    from .links import link_layers

    state = project.state
    if link_layers(state) or any(layer.get("linked") for layer in state.get("layers", [])):
        return 1  # Linked files are read relative to the workspace: render them where the workspace is.
    workers = max(1, min(workers, count // MIN_FRAMES_PER_WORKER))
    if value:
        return workers
    if frame_seconds is None or frame_seconds <= 0:
        return 1
    serial = count * frame_seconds
    costs = {n: serial / n + n * STARTUP_SECONDS + count * frame_bytes / TRANSFER_BYTES_PER_SECOND
             for n in range(2, workers + 1)}
    if not costs:
        return 1
    chosen = min(costs, key=costs.get)
    return chosen if serial - costs[chosen] >= max(1.0, serial * 0.25) else 1


def _start(archive, limits, workspace, disk):
    global _PROJECT
    os.environ["VIXL_RENDER_THREADS"] = "1"  # The processes already use the cores.
    from .model import Limits
    from .project import Project

    project = Project.load(archive, limits=Limits(**limits))
    project._workspace = workspace
    if disk:  # Only when the export itself uses the persistent cache (a saved document).
        from .timeline import cached

        project = cached(project)
    _PROJECT = project


def _render(times, scale):
    from .timeline import project_at, render_scaled

    frames = []
    for time in times:
        image = render_scaled(project_at(_PROJECT, time, prune=True), scale)
        frames.append((image.mode, image.size, image.tobytes()))
    return frames


def frames(project, times, scale, workers, cancelled=None):
    """The frames at ``times``, rendered by ``workers`` processes, in order."""
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor

    from .calls import check_cancelled
    from .errors import require

    disk = getattr(project, "_disk_cache", None) is not None
    with tempfile.TemporaryDirectory(prefix="vixl-frames-") as folder:
        archive = Path(folder) / "frames.vixl"
        copy = project.clone()
        copy.path = copy._revision = None
        copy.save(archive)
        canvas = project.state["canvas"]
        frame_bytes = 4 * max(1, round(canvas["width"] * scale)) * max(1, round(canvas["height"] * scale))
        size = max(1, min(CHUNK, IN_FLIGHT_BYTES // (2 * workers * frame_bytes)))
        chunks = [times[i:i + size] for i in range(0, len(times), size)]
        pool = ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"),
                                   initializer=_start, initargs=(str(archive), asdict(project.limits),
                                                                 str(project._workspace), disk))
        pending = deque()

        def stop():
            require(not cancelled or not cancelled(), "Timeline cancelled", "cancelled")
            check_cancelled()

        def finished(future):
            for mode, size, data in future.result():
                stop()
                yield Image.frombytes(mode, size, data)

        try:
            for chunk in chunks:
                while len(pending) >= 2 * workers:
                    yield from finished(pending.popleft())
                stop()
                pending.append(pool.submit(_render, chunk, scale))
            while pending:
                yield from finished(pending.popleft())
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
