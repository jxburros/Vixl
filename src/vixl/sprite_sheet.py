"""Sprite sheets as a grid: one row per facing or state, one column per frame, a fixed cell size.

``sprite-sheet`` declares the grid on the document (``state["sprite_sheet"]``); ``pixel-art`` and ``move`` then
take ``cell: [row, column]`` instead of canvas coordinates, and ``export-animation`` with ``format: "sheet"``
writes the canvas as the sheet with its clips (name, row, frame rectangles, durations) as JSON a game engine reads.
"""

from copy import deepcopy

from .errors import require

MAX_ROWS, MAX_COLUMNS, MAX_CELL, MAX_CLIPS = 64, 256, 1024, 256
DURATION = 100  # ms per frame when neither the sheet nor the clip says
METADATA = ("neutral", "aseprite")
FIELDS = ("cell", "rows", "columns", "duration", "clips")
CLIP_FIELDS = ("row", "frames", "duration", "durations", "loop")


def _whole(value, low, high):
    return type(value) is int and low <= value <= high


def _duration(value, field):
    require(_whole(value, 10, 60000), f"{field} is a frame time in ms, 10-60000", field=field)


def validate_sheet(sheet):
    """Check a stored sheet declaration: ``{cell: [w, h], rows: [names], columns, duration?, clips?}``."""
    require(isinstance(sheet, dict) and not set(sheet) - set(FIELDS), "sprite_sheet holds cell, rows, columns, "
            "duration and clips", "invalid_project")
    cell, rows, columns = sheet.get("cell"), sheet.get("rows"), sheet.get("columns")
    require(isinstance(cell, list) and len(cell) == 2 and all(_whole(v, 1, MAX_CELL) for v in cell),
            f"cell is [width, height] in whole pixels, 1-{MAX_CELL}", field="cell")
    require(isinstance(rows, list) and 1 <= len(rows) <= MAX_ROWS
            and all(isinstance(name, str) and name and not name.isdigit() for name in rows)
            and len(set(rows)) == len(rows),
            f"rows is a list of 1-{MAX_ROWS} different row names (down, left, right, up ...)", field="rows")
    require(_whole(columns, 1, MAX_COLUMNS), f"columns is the frames per row, 1-{MAX_COLUMNS}", field="columns")
    if "duration" in sheet:
        _duration(sheet["duration"], "duration")
    clips = sheet.get("clips", {})
    require(isinstance(clips, dict) and len(clips) <= MAX_CLIPS, f"clips maps at most {MAX_CLIPS} clip names to "
            "{row, frames, duration, durations, loop}", field="clips")
    for name, clip in clips.items():
        require(isinstance(name, str) and name and isinstance(clip, dict), "clips maps clip names to {row, frames, "
                "duration, durations, loop}", field="clips")
        unknown = sorted(set(clip) - set(CLIP_FIELDS))
        require(not unknown, f"Clip {name!r}: unknown field(s) {unknown}; available: {', '.join(CLIP_FIELDS)}",
                field="clips")
        if "row" in clip:
            row_index(sheet, clip["row"], "clips")
        frames = clip.get("frames", list(range(columns)))
        require(isinstance(frames, list) and 1 <= len(frames) <= 1024 and all(_whole(v, 0, columns - 1) for v in frames),
                f"Clip {name!r}: frames lists column indexes 0-{columns - 1} in play order", field="clips")
        if "duration" in clip:
            _duration(clip["duration"], "clips")
        if "durations" in clip:
            require(isinstance(clip["durations"], list) and len(clip["durations"]) == len(frames),
                    f"Clip {name!r}: durations needs one value per frame ({len(frames)})", field="clips")
            for value in clip["durations"]:
                _duration(value, "clips")
        require(isinstance(clip.get("loop", True), bool), f"Clip {name!r}: loop is true or false", field="clips")
    names = [name for name, _, _ in _expanded(sheet)]
    require(len(set(names)) == len(names), "Two clips end up with the same name; rename one", field="clips")


def sheet_of(project):
    sheet = project.state.get("sprite_sheet")
    require(sheet is not None, "The document has no sprite sheet: declare one with sprite-sheet {cell: [w, h], "
            "rows: [...], columns: n}", "not_found", field="cell")
    return sheet


def row_index(sheet, row, field="cell"):
    rows = sheet["rows"]
    if isinstance(row, str):
        require(row in rows, f"Unknown sheet row {row!r}; rows: {', '.join(rows)}", field=field, suggestions=rows)
        return rows.index(row)
    require(_whole(row, 0, len(rows) - 1), f"A sheet row is a row name ({', '.join(rows)}) or an index "
            f"0-{len(rows) - 1}", field=field)
    return row


def cell_origin(project, cell):
    """The canvas position of the top-left of ``cell`` ``[row, column]`` (row by name or index, column from 0)."""
    sheet = sheet_of(project)
    require(isinstance(cell, list) and len(cell) == 2, "cell is [row, column]: a row name or index and a column "
            "counted from 0", field="cell")
    row = row_index(sheet, cell[0])
    require(_whole(cell[1], 0, sheet["columns"] - 1), f"The sheet has columns 0-{sheet['columns'] - 1}; got "
            f"{cell[1]!r}", field="cell")
    return cell[1] * sheet["cell"][0], row * sheet["cell"][1]


def place_in_cell(project, layer, cell):
    """Move ``layer`` into ``cell``; its x and y are read as an offset inside the cell. The layer has to fit the
    cell, so nothing it draws (a pixel sprite's outline is drawn inside its own grid) reaches the next frame."""
    x, y = cell_origin(project, cell)
    width, height = sheet_of(project)["cell"]
    ox, oy = layer["x"], layer["y"]
    require(ox >= 0 and oy >= 0 and ox + layer["width"] <= width and oy + layer["height"] <= height,
            f"{layer['name']!r} is {layer['width']:g}x{layer['height']:g} at offset ({ox:g}, {oy:g}) and does not "
            f"fit the {width}x{height} cell; x and y are offsets inside the cell", field="cell")
    layer["x"], layer["y"] = x + ox, y + oy


def execute_sheet(project, op):
    if op.get("delete"):
        require(not set(op) - {"type", "delete"}, "delete takes no other field", field="delete")
        sheet_of(project)
        del project.state["sprite_sheet"]
        return
    sheet = {**project.state.get("sprite_sheet", {}), **{key: deepcopy(op[key]) for key in FIELDS if key in op}}
    require(all(key in sheet for key in ("cell", "rows", "columns")), "sprite-sheet needs cell [w, h], rows "
            "[names] and columns", field="cell")
    validate_sheet(sheet)
    project.state["sprite_sheet"] = sheet
    if op.get("fit_canvas", True):
        from .operations import execute

        width, height = sheet["columns"] * sheet["cell"][0], len(sheet["rows"]) * sheet["cell"][1]
        canvas = project.state["canvas"]
        if (canvas["width"], canvas["height"]) != (width, height):
            execute(project, {"type": "canvas", "width": width, "height": height})


def _expanded(sheet):
    """Declared clips as ``(name, row index, clip)``. A clip without a row stands for one per row, named
    ``CLIP-ROW``; a sheet without clips plays each row once through, named after the row."""
    clips = sheet.get("clips") or {}
    if not clips:
        return [(row, index, {}) for index, row in enumerate(sheet["rows"])]
    out = []
    for name, clip in clips.items():
        if "row" in clip:
            out.append((name, row_index(sheet, clip["row"], "clips"), clip))
        else:
            out += [(f"{name}-{row}", index, clip) for index, row in enumerate(sheet["rows"])]
    return out


def clips(sheet, scale=1):
    """The sheet's clips with their frame rectangles in pixels of the exported image and durations in ms."""
    width, height = sheet["cell"][0] * scale, sheet["cell"][1] * scale
    out = []
    for name, row, clip in _expanded(sheet):
        columns = clip.get("frames", list(range(sheet["columns"])))
        each = clip.get("duration", sheet.get("duration", DURATION))
        durations = clip.get("durations", [each] * len(columns))
        out.append({
            "name": name, "row": sheet["rows"][row], "loop": clip.get("loop", True), "duration": sum(durations),
            "frames": [{"column": column, "x": column * width, "y": row * height, "width": width, "height": height,
                        "duration": duration} for column, duration in zip(columns, durations)],
        })
    return out


def metadata(project, *, format="neutral", scale=1, image=None):
    """Frame metadata of the document's sprite sheet. ``neutral``: ``{cell, rows, columns, clips: [{name, row,
    loop, duration, frames: [{column, x, y, width, height, duration}]}]}``. ``aseprite``: the JSON Aseprite writes
    (frames as an array, clips as ``meta.frameTags``), which most engines import."""
    require(format in METADATA, f"Sheet metadata is one of {', '.join(METADATA)}", field="metadata")
    sheet = sheet_of(project)
    width, height = (sheet["columns"] * sheet["cell"][0] * scale, len(sheet["rows"]) * sheet["cell"][1] * scale)
    listed = clips(sheet, scale)
    if format == "neutral":
        return {
            "format": "vixl-sprite-sheet", "version": 1, **({"image": image} if image else {}),
            "width": width, "height": height, "scale": scale,
            "cell": {"width": sheet["cell"][0] * scale, "height": sheet["cell"][1] * scale},
            "rows": list(sheet["rows"]), "columns": sheet["columns"], "clips": listed,
        }
    frames, tags = [], []
    for clip in listed:
        tags.append({"name": clip["name"], "from": len(frames), "to": len(frames) + len(clip["frames"]) - 1,
                     "direction": "forward", **({} if clip["loop"] else {"repeat": "1"})})
        for frame in clip["frames"]:
            size = {"w": frame["width"], "h": frame["height"]}
            frames.append({
                "filename": f"{clip['name']} {frame['column']}",
                "frame": {"x": frame["x"], "y": frame["y"], **size}, "rotated": False, "trimmed": False,
                "spriteSourceSize": {"x": 0, "y": 0, **size}, "sourceSize": size, "duration": frame["duration"],
            })
    return {"frames": frames, "meta": {"app": "Vixl", **({"image": image} if image else {}), "format": "RGBA8888",
                                       "size": {"w": width, "h": height}, "scale": str(scale), "frameTags": tags}}


def sheet_bytes(project, *, scale=1, sampling="nearest", format="neutral", image=None):
    """The sheet as PNG bytes and its metadata. The canvas is the sheet, so it has to be exactly the grid."""
    import io

    from .animation import check_scale
    from .timeline import render_scaled

    check_scale(scale, sampling)
    require(float(scale).is_integer(), "A sprite sheet scales by a whole number so every frame rectangle stays on "
            "whole pixels", field="scale")
    scale = int(scale)
    sheet = sheet_of(project)
    width, height = sheet["columns"] * sheet["cell"][0], len(sheet["rows"]) * sheet["cell"][1]
    canvas = project.state["canvas"]
    require((canvas["width"], canvas["height"]) == (width, height),
            f"The canvas is {canvas['width']}x{canvas['height']} but the sheet's grid is {width}x{height}; run "
            "sprite-sheet again (it fits the canvas) or set the canvas to the grid", field="format")
    stream = io.BytesIO()
    render_scaled(project, scale, sampling).save(stream, format="PNG")
    return stream.getvalue(), metadata(project, format=format, scale=scale, image=image)
