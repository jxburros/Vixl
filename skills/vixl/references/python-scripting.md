# Scripting Vixl from Python

Batch generation from a script: build each document with `Project`, check it, save the `.vixl` master, export.
The API surface is listed in [mcp-rest-python](mcp-rest-python.md#python-api); this page is what a generator
script needs on top of it.

## A complete script (runs, and reruns)

<!-- docs-test: run -->
```python
import io
from pathlib import Path

from PIL import Image, ImageDraw

from vixl import Project, VixlError

OUT = Path("build")                      # masters and exports go in one folder, not next to the script
MARKETS = [("north", "North Market", "#1d3557"), ("harbour", "Harbour Market", "#2a9d8f"),
           ("hill", "Hill Street Market", "#6d597a")]


def badge_png(color):
    """An image made in memory (a chart, a QR code, a downloaded file): PNG bytes, never written to disk."""
    image = Image.new("RGBA", (240, 240), (0, 0, 0, 0))
    ImageDraw.Draw(image).ellipse([8, 8, 232, 232], fill=color, outline="#ffffff", width=8)
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def build(slug, title, color):
    project = Project(1080, 1080, background=color)
    result = project.apply([
        {"type": "shape", "shape": "rectangle", "name": "band", "x": 0, "y": 760, "width": 1080, "height": 320,
         "fill": "#00000033", "role": "background"},
        {"type": "text", "name": "title", "text": title, "x": 140, "y": 420, "width": 800, "align": "center",
         "size": 96, "color": "#ffffff"},
        {"type": "text", "name": "date", "text": "Every Saturday, 8 to 2", "x": 140, "y": 840, "width": 800,
         "align": "center", "size": 44, "color": "#ffffff"},
    ], detail="compact")
    added = [layer["name"] for layer in result["changes"]["layers"].values() if layer.get("added")]
    assert added == ["band", "title", "date"], result

    imported = project.import_image(data=badge_png("#ffd166"), name="badge")   # a new layer at 0, 0
    project.apply({"type": "move", "target": "badge", "x": 420, "y": 130})
    assert project.bounds("badge") == (420.0, 130.0, imported["width"], imported["height"])

    report = project.check(checks=["bounds", "contrast", "safe_area"])
    if not report["passed"]:
        raise SystemExit(f"{slug}: {report['verdict']}: {[issue['message'] for issue in report['issues']]}")

    project.save(OUT / f"{slug}.vixl", overwrite=True)            # the editable master; overwrite=True for reruns
    data = project.export(OUT / f"{slug}.png", overwrite=True)    # writes the file and returns its bytes
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and (OUT / f"{slug}.png").read_bytes() == data
    return len(data)


OUT.mkdir(exist_ok=True)
for market in MARKETS:
    print(market[0], build(*market), "bytes")

# A later run can open a master and change one thing instead of rebuilding it.
project = Project.load(OUT / "north.vixl")
project.apply({"type": "text-set", "target": "date", "text": "Closed this Saturday"})
project.save()                                                    # its own file: no overwrite needed
try:
    project.export(OUT / "north.png")                             # exists already
except VixlError as error:
    assert error.code == "output_exists"
    project.export(OUT / "north.png", overwrite=True)
```

## Reruns

`save` and every export refuse to replace an existing file (`VixlError.code == "output_exists"`), with one
exception: `save()` or `save(path)` to the file the project was loaded from or last saved to. A generator script
builds each `Project` fresh, so its second run meets the files of the first: pass `overwrite=True` to both
`save(path)` and `export(path)` in a script that owns its output folder. To edit instead of rebuild,
`Project.load(path)`, apply, `save()`.

## Return values

| Call | Returns |
| --- | --- |
| `apply(ops, detail="brief"\|"compact"\|"full")` | dict: `success`, `operations`, `changes.layers` by layer ID (new: `added`, `name`, `type`, `bounds`; compact adds new values; full, the default, adds before/after), plus `normalized`, `warnings`, `defaults` when relevant. Atomic: an error applies nothing |
| `apply(ops, check=True)` | the same plus `result["check"]` |
| `check(checks=[…])` | dict: `passed`, `verdict`, `issues[{rule, severity, action, layers, message}]`, `by_action`, `outcome`; without `checks` the defaults run (including `fonts`, which reports the proofing font) |
| `import_image(path \| data=bytes \| url=…, name=…)` | dict: `id`, `name`, `width`, `height`, `bounds`, `asset`; the layer lands at 0, 0 at its pixel size and is active: position it with `move` (or `resize`, `align`, `place`) |
| `export(path, …)` | the encoded bytes, and the file when a path is given |
| `save(path)` | the saved path |
| `render()` | Pillow RGBA image |
| `bounds(name)` | `(x, y, width, height)` on the canvas |

Errors raise `VixlError` (`code`, `details` with `field`, `operation_index`, `suggestions`; `as_dict()`).

## Output and fonts

- One output folder per script (`build/`), masters beside exports; relative paths resolve against the working
  directory. In a Git repository check `git check-ignore -v FILE`: some repositories ignore `*.vixl`.
- `Project(w, h)` is a plain canvas in the proofing font; `Project(purpose="social", seed=7)` rolls a palette and a
  font pairing; `vixl.typefaces.pair_fonts(project, "random")` installs a pairing on a plain canvas.
