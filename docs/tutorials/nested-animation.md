# Reuse an animation

[Documentation home](../README.md) · [Motion tutorial](motion.md) · [Linked documents](../guides/output/linked-documents.md)

Save a moving dot as a reusable document, then give two linked instances different timing. The instances keep
their source editable: changing `dot.vixl` changes both instances on the next render.

```python
from pathlib import Path
from vixl import Project
from vixl.timeline import export_timeline

folder = Path("motion-demo")
folder.mkdir(exist_ok=True)
dot = Project(160, 80, "transparent")
dot.apply([
    {"type": "shape", "name": "dot", "shape": "ellipse", "width": 24, "height": 24,
     "x": 12, "y": 28, "fill": "#ef6648"},
    {"type": "timeline-set", "duration": 1000, "fps": 30, "loop": 1},
    {"type": "animate", "target": "dot", "property": "x", "from": 12, "to": 124,
     "start": 0, "end": 1000, "easing": "ease-in-out"},
])
dot.save(folder / "dot.vixl")

scene = Project(320, 80, "#faf5ed")
scene.save(folder / "scene.vixl")
scene.apply([
    {"type": "timeline-set", "duration": 2000, "fps": 30, "loop": 1},
    {"type": "link", "source": "dot.vixl", "name": "slow",
     "time": {"loop": "pingpong"}},
    {"type": "animation-instance", "source": "dot.vixl", "name": "fast", "x": 160,
     "time": {"offset": 300, "speed": 2, "loop": "pingpong", "before": "hidden"}},
])
scene.save()
export_timeline(scene, folder / "scene.webp")
```

The first dot plays at its source speed. The second waits 300 ms, then plays twice as fast. Each reverses at
the end of the source timeline. Use `trim_start` and `trim_end` to reuse just one part of a longer source, and
`variables` alongside `time` to give each instance different source text or colours.

`scene.inspect()["links"]` reports each source's duration and the instance's first playback window.
Use `link-refresh` after accepting a source edit to clear its stale status; it keeps each instance's timing.
