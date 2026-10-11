"""Native PowerPoint tables for Vixl table groups.

A table group (see ``tables.py``) exports to .pptx as a real table (``a:tbl`` in a graphic frame), so it
can be edited in PowerPoint, Keynote or Google Slides: one cell per table cell with its text, font, size,
color and alignment, the column widths and row heights Vixl laid out, the header band, zebra bands and
rules. Decimal-aligned columns are right-aligned (their figures share a number format, so the points line
up). Rotated or flipped tables, and tables whose layers carry effects, export as their shapes instead.
"""

from xml.sax.saxutils import escape, quoteattr

from .chart_pptx import solid

TABLE_URI = "http://schemas.openxmlformats.org/drawingml/2006/table"
ALIGN = {"left": "l", "center": "ctr", "right": "r", "decimal": "r"}


def _line(tag, state, color, width_emu):
    if color is None or width_emu <= 0:
        return f"<a:{tag} w=\"0\"><a:noFill/></a:{tag}>"
    return f'<a:{tag} w="{width_emu}" cap="flat" cmpd="sng" algn="ctr">{solid(state, color)}<a:prstDash val="solid"/></a:{tag}>'


def borders(recipe, rows, columns, top):
    """For each cell, (left, right, top, bottom) rule weights in pixels as the Vixl layout draws them."""
    style = recipe.get("borders", "horizontal")
    weight = max(1, round(recipe.get("border_width", 1)))
    grid = [[[0, 0, 0, 0] for _ in range(columns)] for _ in range(rows)]
    for i in range(rows):
        for j in range(columns):
            edges = grid[i][j]
            if style in ("horizontal", "all", "header", "outer") and top and i == 0:
                edges[3] = weight * (1 if style in ("all", "outer") else 2)
            if style in ("horizontal", "all") and i >= top:
                edges[3] = weight
            if style == "all":
                edges[0] = edges[1] = edges[2] = weight
                edges[3] = max(edges[3], weight)
            if style == "outer":
                if i == 0:
                    edges[2] = weight
                if i == rows - 1:
                    edges[3] = weight
                if j == 0:
                    edges[0] = weight
                if j == columns - 1:
                    edges[1] = weight
    return grid


def shapes(slide, layer, bounds, emu, layers, index):
    """The graphic frame that stands for a table group on a slide, plus anything the person added to the group.
    Returns None when the table cannot be native (the group then exports as its shapes)."""
    from .tables import column_specs, header_count, shown
    from .text import primary_font_data

    recipe = layer["table"]
    summary = recipe.get("summary") or {}
    if layer.get("rotation", 0) % 360 or layer.get("flip_x") or layer.get("flip_y"):
        slide.table_info.append({"layer": layer["name"], "native": False,
                                 "reason": "rotated or flipped tables are exported as shapes"})
        return None
    children = [c for c in layers if c.get("parent") == layer["id"]]
    parts = {c["table_part"]: c for c in children if "table_part" in c}
    if any(c["effects"] or c.get("styles") or c["opacity"] != 1 for c in parts.values()) or "column_widths" not in summary:
        slide.table_info.append({"layer": layer["name"], "native": False,
                                 "reason": "table layers carry effects or opacity; exported as shapes"})
        return None
    state = slide.view.state
    rows = recipe["rows"]
    top = header_count(recipe)
    count = len(rows[0])
    specs = column_specs(recipe, count, rows[top:])
    x, y, w, h = bounds[layer["id"]]
    sx, sy = w / layer["content_width"], h / layer["content_height"]
    widths = [round(v * sx * emu) for v in summary["column_widths"]]
    heights = [round(v * sy * emu) for v in summary["row_heights"]]
    pt = emu / 12700 * min(sx, sy)
    rule = next((c["fill"] for key, c in sorted(parts.items()) if key.startswith("rule-") and c["visible"]), None)
    edges = borders(recipe, len(rows), count, top)
    bands = {}
    for key, part in parts.items():
        if not part["visible"]:
            continue
        if key == "header-band":
            bands[0] = part["fill"]
        elif key.startswith("band-"):
            bands[int(key.split("-")[1])] = part["fill"]
    background = parts.get("fill", {}).get("fill") if parts.get("fill", {}).get("visible", True) else None
    faces = {}
    xml_rows = []
    for i, row in enumerate(rows):
        sample = next((parts[f"cell-{i}-{j}"] for j in range(count) if f"cell-{i}-{j}" in parts), None)
        sample = sample or next((c for key, c in parts.items() if key.startswith("cell-")), None)
        cells = []
        for j, value in enumerate(row):
            part = parts.get(f"cell-{i}-{j}") or sample
            font = part["font"] if part else "DejaVuSans.ttf"
            if font not in faces:
                faces[font] = slide.exporter.font(primary_font_data(slide.view, {"font": font}))
            size = (part["size"] if part else 16) * pt
            color = part["color"] if part else "#000000"
            text = shown(value, specs[j]["format"] if i >= top else None)
            align = ALIGN["right" if specs[j]["align"] == "decimal" and i < top else specs[j]["align"]]
            run = (f'<a:rPr lang="en-US" sz="{max(100, min(400000, round(size * 100)))}" b="0" dirty="0">'
                   f'{solid(state, color)}<a:latin typeface={quoteattr(faces[font])}/><a:ea typeface={quoteattr(faces[font])}/>'
                   f'<a:cs typeface={quoteattr(faces[font])}/></a:rPr>')
            paragraphs = "".join(
                f'<a:p><a:pPr algn="{align}"/>' + (f"<a:r>{run}<a:t>{escape(line)}</a:t></a:r>" if line else "")
                + f'<a:endParaRPr lang="en-US" sz="{max(100, min(400000, round(size * 100)))}" dirty="0"/></a:p>'
                for line in (text.split("\n") if text else [""]))
            pad = recipe.get("padding")
            fs = summary.get("font_size", 16)
            padx = round((pad if pad is not None else fs * 0.6) * sx * emu)
            pady = round((pad if pad is not None else fs * 0.45) * sy * emu)
            left, right, upper, lower = (round(v * min(sx, sy) * emu) for v in edges[i][j])
            fill = bands.get(i, background)
            cells.append(
                f'<a:tc><a:txBody><a:bodyPr/><a:lstStyle/>{paragraphs}</a:txBody>'
                f'<a:tcPr marL="{padx}" marR="{padx}" marT="{pady}" marB="{pady}" anchor="t">'
                f'{_line("lnL", state, rule, left)}{_line("lnR", state, rule, right)}'
                f'{_line("lnT", state, rule, upper)}{_line("lnB", state, rule, lower)}'
                f'{solid(state, fill) if fill else "<a:noFill/>"}</a:tcPr></a:tc>')
        xml_rows.append(f'<a:tr h="{max(1, heights[i])}">{"".join(cells)}</a:tr>')
    grid = "".join(f'<a:gridCol w="{max(1, v)}"/>' for v in widths)
    ident = slide.ident()
    frame = (f'<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="{ident}" name={quoteattr(layer["name"])}/>'
             '<p:cNvGraphicFramePr><a:graphicFrameLocks noGrp="1"/></p:cNvGraphicFramePr><p:nvPr/></p:nvGraphicFramePr>'
             f'<p:xfrm><a:off x="{round(x * emu)}" y="{round(y * emu)}"/><a:ext cx="{max(1, sum(widths))}" '
             f'cy="{max(1, sum(heights))}"/></p:xfrm><a:graphic><a:graphicData uri="{TABLE_URI}">'
             f'<a:tbl><a:tblPr firstRow="{1 if top else 0}" bandRow="0"/><a:tblGrid>{grid}</a:tblGrid>{"".join(xml_rows)}'
             '</a:tbl></a:graphicData></a:graphic></p:graphicFrame>')
    out = [frame]
    for child in children:
        if "table_part" in child or not child["visible"] or child["opacity"] <= 0:
            continue
        cx, cy, cw, ch = bounds[child["id"]]
        shifted = {**bounds, child["id"]: (x + cx * sx, y + cy * sy, cw * sx, ch * sy)}
        from .pdf_export import PageBuilder

        reason = PageBuilder.raster_reason(child)
        xml = None
        if reason is None and child["type"] != "group":
            try:
                xml = slide.leaf(child, shifted[child["id"]], emu)
            except Exception:  # noqa: BLE001 - anything PowerPoint cannot draw falls back to a picture
                reason = "unsupported"
        if xml is None:
            xml = slide.picture(child, shifted, emu, index, layer["id"], reason or "unsupported")
        if xml:
            out.append(xml)
    info = {"layer": layer["name"], "native": True, "rows": len(rows), "columns": count}
    if any(s["align"] == "decimal" for s in specs):
        info["notes"] = ["decimal-aligned columns are right-aligned"]
    slide.table_info.append(info)
    return out
