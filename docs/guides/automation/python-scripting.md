# Script Vixl from Python

[Documentation home](../../README.md) · [Interfaces](../../reference/interfaces.md#python) · [Production workflows](production.md)

A Python script is the shortest way to make many pieces from one recipe: a set of cards from a table, a sheet per
character, a report per dataset. The script builds each document with `Project`, checks it, saves the editable
`.vixl` master and exports the files. This page covers what a batch script needs that a single call does not:
running it again, reading what calls return, placing images made in memory and keeping the output in one folder.

```python
from vixl import Project, VixlError
```

`Project` is the whole API for one document. It is a trusted local API: file paths and fonts on disk work, nothing
is saved until you call `save`, and a failed `apply` leaves the document as it was. Operations are the same JSON
objects every interface takes (`vixl schema OPERATION` prints one operation's fields).

## A complete script

Save this as `build_cards.py` and run it with `python build_cards.py` from the folder that should hold `build/`.
It makes three square cards, each saved as a master and exported as a PNG, then reopens one master and changes a
line. Run it a second time and it replaces what it made.

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

## Run it again

Vixl never replaces a file it was not told to replace, and the rule is the same for masters and exports:

| Call | An existing file at the path |
| --- | --- |
| `project.save()` or `project.save(path)` to the file the project was loaded from or last saved to | replaced: it is this document |
| `project.save(other_path)` | refused with `output_exists` unless `overwrite=True` |
| `project.export(path)`, `export_animation`, `export_screens` and the other exports | refused with `output_exists` unless `overwrite=True` |

A generator script creates each `Project` fresh, so on its second run every `save(path)` and `export(path)` meets
the file from the first run. Pass `overwrite=True` to both in a script that owns its output folder, as above. To
keep earlier output instead, write each run to its own folder, or catch the error: `VixlError.code` is
`"output_exists"` and the message names the file.

Rebuilding from the recipe each run keeps the script the source of truth. When people or agents edit the masters
afterwards, load them (`Project.load(path)`), change what the run is about and call `save()`; their edits and the
undo history stay in the file.

## What calls return

| Call | Returns |
| --- | --- |
| `project.apply(operations, detail=…)` | A dict: `success`, `operations` (how many ran) and `changes`. `changes["layers"]` is keyed by layer ID; a new layer has `added`, `name`, `type` and `bounds`. `detail="brief"` stops there, `"compact"` adds the new field values, `"full"` (the default) adds before and after snapshots. `normalized` lists input that was rewritten to its canonical form, `warnings` what probably is not what you meant (text cut off by the canvas, a field that does nothing here), `defaults` the values Vixl chose for fields you left out |
| `project.apply(operations, check=True)` | The same, plus `result["check"]`: the design check of the result |
| `project.check(checks=[…])` | A dict: `passed`, `verdict`, `issues` (each with `rule`, `severity`, `action` `fix`/`review`/`informational`, `layers`, `message`), `by_action` and `outcome`. Without `checks` every default check runs, including the one that reports text still set in the proofing font |
| `project.import_image(path)`, `import_image(data=bytes)`, `import_image(url=…)` | A dict: the new layer's `id`, `name`, `width`, `height`, `bounds` and `asset` |
| `project.export(path, …)` | The encoded bytes. With a path it also writes the file; without one it only returns the bytes (a PNG) |
| `project.render()` | A Pillow RGBA image of the canvas |
| `project.save(path)` | The saved file's path (also `project.path` from then on) |
| `project.bounds(name)` | `(x, y, width, height)` on the canvas |
| `project.inspect()` | A dict: the canvas and every layer with its bounds; `inspect(name)` is one layer |

A failed call raises `VixlError`: `error.code` is a stable name (`invalid_operation`, `layer_not_found`,
`output_exists` …), `error.details` carries the field, the operation index in the batch and suggestions, and
`error.as_dict()` is the JSON the other interfaces return. A batch is atomic: when one operation fails, none of it
is applied.

## Images made in memory

`import_image(data=…)` takes the bytes of an encoded image (PNG, JPEG, WebP …), so a picture the script made or
downloaded never needs a temporary file. The new layer is placed at the top-left corner at its pixel size and
becomes the active layer; position it with a `move` operation (or `resize`, `align`, `place`) in the next `apply`,
naming it by the `name` you gave:

```python
layer = project.import_image(data=png_bytes, name="badge", credit="Chart: finance team")
project.apply([{"type": "move", "target": "badge", "x": 420, "y": 130},
               {"type": "resize", "target": "badge", "width": 200, "height": 200}])
```

A Pillow image becomes bytes with `image.save(stream, format="PNG")` on an `io.BytesIO()`. An image file on disk can
skip the import step: the `add` operation takes `path`, `x` and `y` in one go.

## Where the files go

- Give the script one output folder (`build/` above) and write masters and exports into it; create it with
  `mkdir(exist_ok=True)`. Relative paths resolve against the directory the script runs in.
- Keep the `.vixl` master next to each export. The export is what you ship; the master is what you change next
  week.
- In a Git repository, decide whether the output is a build product or a source. A build product belongs in an
  ignored folder; masters you want reviewed belong in a tracked one. Check with `git check-ignore -v FILE`: some
  repositories ignore `*.vixl` because their tests write scratch documents.
- Fonts: a `Project(width, height)` is a plain canvas that draws text in the bundled proofing font, which the
  `fonts` check reports. `Project(purpose="social", seed=7)` creates a design document with a rolled palette and
  font pairing instead; `vixl.typefaces.pair_fonts(project, "random")` installs a pairing on a plain one (from the
  font cache or the network), and a text operation's `font` can be a font file path.

## Related

- [Getting started](../../getting-started.md#the-same-design-in-python) has the smallest script.
- [Interfaces: Python](../../reference/interfaces.md#python) lists the rest of the API: history, transactions,
  measuring, animation and data-driven rendering.
- [Production workflows](production.md) cover campaigns, pipelines and data sync when the batch outgrows a script.
- [Check designs in CI](ci.md) runs the same checks on every pull request.
