# Install and make your first design

[Documentation home](README.md) · Next: [document concepts](concepts.md)

You need Python 3.11+ or the Windows installer. A graphical display, AI account and GPU
are unnecessary for this tutorial. Commands below use a terminal; Python offers the same
operation engine. For an agent client, use the [MCP configuration guide](interfaces.md#mcp).

## Install

On Windows, install the latest executable from [GitHub Releases](https://github.com/jxburros/Vixl/releases/latest),
then open a terminal and run `vixl --version`. The installer includes Python and automatic
updates. `vixl update --check` checks availability; `vixl update` installs it. See
[release instructions](releases.md) for PATH repair and rollback.

For a source install on macOS, Linux or Windows:

```bash
git clone https://github.com/jxburros/Vixl.git
cd Vixl
python -m venv .venv
# macOS / Linux:
source .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
python -m pip install -e '.[server,pdf]'
vixl --version
```

The core install is `python -m pip install -e .`; MCP is included. `server` adds REST and
live review; `pdf` adds PDF page import. To update this checkout later, save your changes,
run `git pull --ff-only`, and repeat the install. Pip installs use pip-managed updates;
the bundled Windows updater is a separate installation mechanism.

For reproducible work, install a tag rather than tracking `main`:

```bash
python -m pip install 'https://github.com/jxburros/Vixl/archive/refs/tags/v0.25.0.tar.gz'
```

Latest `main` may include changes beyond the tagged release while reporting the same
package version. Record the commit with `git rev-parse HEAD` when working from source.

## Create, edit and export

Use a fresh output filename. Explicit `-p` keeps every command on the intended document.
Quote colors beginning with `#` so shells do not treat them as comments.

```bash
vixl new 800x600 --background '#18283b' -o hello.vixl
vixl -p hello.vixl text add 'Hello, Vixl' --name title --size 64 --color '#ffffff'
vixl -p hello.vixl align title center
vixl -p hello.vixl checkpoint first-design
vixl -p hello.vixl inspect --json
vixl -p hello.vixl check --checks bounds contrast
vixl -p hello.vixl render --out hello-preview.png
vixl -p hello.vixl export hello.png
```

You now have an editable `hello.vixl` and a PNG export. Open the PNG to inspect the actual
appearance. `check` covers the rules requested, not every possible design problem. The
bundled DejaVu Sans font makes proofing work offline; for finished brand work, choose a
font with `vixl font pairings` and install a pairing or import your licensed font. See
[typography](typography.md).

Editing commands autosave. To revise the headline and undo the change:

<!-- docs-test: continue -->
```bash
vixl -p hello.vixl text title --text 'Ready to create'
vixl -p hello.vixl render --out revised.png
vixl -p hello.vixl undo
```

## Use an atomic batch

Save this as `hello-ops.json`. Names allow later operations to address layers created
earlier in the same batch.

<!-- docs-test: save hello-ops.json -->
```json
{"operations": [
  {"type": "text", "name": "title", "text": "Hello, Vixl", "size": 64, "color": "#ffffff"},
  {"type": "align", "target": "title", "alignment": "center"}
]}
```

```bash
vixl new 800x600 --background '#18283b' -o batch.vixl
vixl -p batch.vixl apply hello-ops.json --dry-run
vixl -p batch.vixl apply hello-ops.json
vixl -p batch.vixl export batch.png
```

Dry-run reports proposed changes without saving. A failed batch commits none of its
changes. Get allowed fields with `vixl schema` and individual command help with
`vixl text --help`; [operations](operations.md) explains normalization and validation.

## The same design in Python

```python
from vixl import Project

project = Project(800, 600, background="#18283b")
project.apply([
    {"type": "text", "name": "title", "text": "Hello, Vixl", "size": 64, "color": "#ffffff"},
    {"type": "align", "target": "title", "alignment": "center"},
])
report = project.check(checks=["bounds", "contrast"])
assert report["passed"], report["issues"]
project.save("python-hello.vixl")
project.export("python-hello.png")
```

Python edits remain in memory until you call `save` (which, like exports, refuses to replace another existing file
unless you pass `overwrite=True`); `render()` returns a Pillow RGBA image.
The [interface reference](interfaces.md) documents loading, history, errors and services.

## Continue

Choose a [campaign](tutorials/campaign.md), [chart](tutorials/charts.md),
[form or deck](tutorials/forms-and-decks.md), or [animation](tutorials/motion.md).
For an existing image, start with `vixl -p hello.vixl add photo.jpg --name photo`, then use
[design tools](design-tools.md) for positioning, masks and effects.
