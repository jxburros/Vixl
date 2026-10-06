"""Native PowerPoint charts for Vixl chart groups.

A chart group (see ``charts.py``) exports to .pptx as a real chart object: DrawingML chart XML with its
categories and series, plus an embedded workbook holding the same table, so *Edit Data* works in
PowerPoint, Keynote and Google Slides. The package parts are written directly (no python-pptx or
spreadsheet library is needed). Colors, fonts, scale, number formats, gridlines, legend and value
labels follow the chart's own settings. A rotated or flipped chart, which PowerPoint cannot draw,
stays the shapes it is in Vixl. Total labels and a donut's center text have no native counterpart:
the center text is exported as a text box over the chart, total labels are listed in the report.
"""

import io
from xml.sax.saxutils import escape, quoteattr
import zipfile

from .charts import Kit, Style, rgba

C_NS = ('xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')
XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
CHART_TYPE = "application/vnd.openxmlformats-officedocument.drawingml.chart+xml"
SHEET_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
SHEET_PARTS = "application/vnd.openxmlformats-officedocument.spreadsheetml"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
LEGEND_POSITIONS = {"top": "t", "bottom": "b", "left": "l", "right": "r"}


def text(value):
    return escape("".join(c for c in str(value) if c in "\t\n\r" or ord(c) >= 32))


def number(value):
    return repr(value) if isinstance(value, float) else str(value)


# ---------------------------------------------------------------------------------------------
# The embedded workbook: one sheet, categories down column A, one series per column after it

def column(index):
    return chr(ord("A") + index)


def string_item(value):
    space = ' xml:space="preserve"' if value != value.strip() else ""
    return f"<si><t{space}>{text(value)}</t></si>"


def workbook(categories, series):
    """The bytes of a minimal .xlsx holding the chart's table (written deterministically)."""
    strings, references = [], []

    def shared(value):
        references.append(value)
        if value not in strings:
            strings.append(value)
        return strings.index(value)

    rows = ['<row r="1">' + "".join(f'<c r="{column(j + 1)}1" t="s"><v>{shared(s["name"])}</v></c>'
                                    for j, s in enumerate(series)) + "</row>"]
    for i, category in enumerate(categories):
        cells = f'<c r="A{i + 2}" t="s"><v>{shared(category)}</v></c>' + "".join(
            f'<c r="{column(j + 1)}{i + 2}"><v>{number(s["values"][i])}</v></c>'
            for j, s in enumerate(series) if s["values"][i] is not None)
        rows.append(f'<row r="{i + 2}">{cells}</row>')
    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    sheet = (f'{XML}<worksheet xmlns="{main}"><dimension ref="A1:{column(len(series))}{len(categories) + 1}"/>'
             f'<sheetData>{"".join(rows)}</sheetData></worksheet>')
    table = "".join(string_item(s) for s in strings)
    parts = {
        "[Content_Types].xml": (
            f'{XML}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            f'<Override PartName="/xl/workbook.xml" ContentType="{SHEET_TYPE}.main+xml"/>'
            f'<Override PartName="/xl/worksheets/sheet1.xml" ContentType="{SHEET_PARTS}.worksheet+xml"/>'
            f'<Override PartName="/xl/sharedStrings.xml" ContentType="{SHEET_PARTS}.sharedStrings+xml"/>'
            f'<Override PartName="/xl/styles.xml" ContentType="{SHEET_PARTS}.styles+xml"/></Types>'),
        "_rels/.rels": (f'{XML}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                        f'<Relationship Id="rId1" Type="{REL}/officeDocument" Target="xl/workbook.xml"/></Relationships>'),
        "xl/workbook.xml": (f'{XML}<workbook xmlns="{main}" xmlns:r="{REL}"><sheets>'
                            '<sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>'),
        "xl/_rels/workbook.xml.rels": (
            f'{XML}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{REL}/worksheet" Target="worksheets/sheet1.xml"/>'
            f'<Relationship Id="rId2" Type="{REL}/styles" Target="styles.xml"/>'
            f'<Relationship Id="rId3" Type="{REL}/sharedStrings" Target="sharedStrings.xml"/></Relationships>'),
        "xl/worksheets/sheet1.xml": sheet,
        "xl/sharedStrings.xml": (f'{XML}<sst xmlns="{main}" count="{len(references)}" uniqueCount="{len(strings)}">{table}</sst>'),
        "xl/styles.xml": (f'{XML}<styleSheet xmlns="{main}"><fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
                          '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
                          '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
                          '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
                          '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
                          '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'),
    }
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)), data)
    return stream.getvalue()


# ---------------------------------------------------------------------------------------------
# The chart part

def solid(state, value, alpha=1.0):
    r, g, b, a = rgba(state, value)
    opacity = a / 255 * alpha
    inner = f'<a:alpha val="{round(opacity * 100000)}"/>' if opacity < 1 else ""
    return f'<a:solidFill><a:srgbClr val="{r:02X}{g:02X}{b:02X}">{inner}</a:srgbClr></a:solidFill>'


def run_properties(tag, state, size, color, face, bold=False):
    language = ' lang="en-US"' if tag == "rPr" else ""
    return (f'<a:{tag}{language} sz="{max(100, min(400000, round(size * 100)))}" b="{int(bold)}">{solid(state, color)}'
            f'<a:latin typeface={quoteattr(face)}/><a:ea typeface={quoteattr(face)}/><a:cs typeface={quoteattr(face)}/></a:{tag}>')


def text_properties(state, size, color, face, rotation=None):
    body = f'<a:bodyPr rot="{rotation}" vert="horz"/>' if rotation is not None else "<a:bodyPr/>"
    return (f'<c:txPr>{body}<a:lstStyle/><a:p><a:pPr>{run_properties("defRPr", state, size, color, face)}</a:pPr>'
            '<a:endParaRPr lang="en-US"/></a:p></c:txPr>')


def rich(state, lines, rotation=None, align=None):
    """``c:rich`` text from (text, size, color, face) lines."""
    body = f'<a:bodyPr rot="{rotation}" vert="horz"/>' if rotation is not None else "<a:bodyPr/>"
    paragraphs = "".join(
        f'<a:p><a:pPr{f" algn={quoteattr(align)}" if align else ""}>{run_properties("defRPr", state, size, color, face)}</a:pPr>'
        f'<a:r>{run_properties("rPr", state, size, color, face)}'
        f'<a:t>{text(value)}</a:t></a:r></a:p>' for value, size, color, face in lines)
    return f"<c:rich>{body}<a:lstStyle/>{paragraphs}</c:rich>"


def title_xml(state, lines, x, y):
    """A left-aligned chart title at the fractional position (x, y) of the chart area."""
    return (f'<c:title><c:tx>{rich(state, lines, align="l")}</c:tx><c:layout><c:manualLayout><c:xMode val="edge"/>'
            f'<c:yMode val="edge"/><c:x val="{x:.4f}"/><c:y val="{y:.4f}"/></c:manualLayout></c:layout><c:overlay val="0"/></c:title>')


def axis_title(state, value, size, color, face, rotation=None):
    return (f'<c:title><c:tx>{rich(state, [(value, size, color, face)], rotation)}</c:tx><c:overlay val="0"/></c:title>')


def line_properties(state, color, width_pt=0.75):
    return f'<a:ln w="{round(width_pt * 12700)}">{solid(state, color)}</a:ln>'


def string_cache(formula, values):
    points = "".join(f'<c:pt idx="{i}"><c:v>{text(v)}</c:v></c:pt>' for i, v in enumerate(values))
    return f'<c:strRef><c:f>{formula}</c:f><c:strCache><c:ptCount val="{len(values)}"/>{points}</c:strCache></c:strRef>'


def number_cache(formula, values):
    points = "".join(f'<c:pt idx="{i}"><c:v>{number(v)}</c:v></c:pt>' for i, v in enumerate(values) if v is not None)
    return (f'<c:numRef><c:f>{formula}</c:f><c:numCache><c:formatCode>General</c:formatCode>'
            f'<c:ptCount val="{len(values)}"/>{points}</c:numCache></c:numRef>')


class Native:
    """Builds the chart XML for one chart group from its recipe and the numbers its layout recorded."""

    def __init__(self, slide, layer, pt):
        view = slide.view
        self.state, self.recipe, self.summary = view.state, layer["chart"], layer["chart"]["summary"]
        self.W, self.H = layer["content_width"], layer["content_height"]
        self.pt = pt
        self.style = Style(view, self.recipe, self.W, self.H)
        kit = Kit(view, self.recipe, self.style)
        from .text import primary_font_data

        self.face = {head: slide.exporter.font(primary_font_data(view, {"font": kit.fonts[head][0]})) for head in (True, False)}
        self.kind = self.recipe["kind"]
        self.categories, self.series = self.recipe["categories"], self.recipe["series"]
        self.colors = self.summary["colors"]
        self.size = self.style.fs * pt

    # -- pieces -------------------------------------------------------------------------------

    def refs(self, j):
        n = len(self.categories)
        col = column(j + 1)
        return f"Sheet1!$A$2:$A${n + 1}", f"Sheet1!${col}$1", f"Sheet1!${col}$2:${col}${n + 1}"

    def labels(self, color, position, fmt, percent=False, both=False):
        recipe = self.recipe
        if recipe.get("value_labels", "auto") in (False, "none"):
            return ""
        shown = self.summary.get("labels", 0)
        points = self.summary["categories"] * (1 if self.kind in ("pie", "donut") else self.summary["series"])
        if not shown or (recipe.get("value_labels", "auto") == "auto" and shown * 2 < points):
            return ""
        face = self.face[False]
        value, share = (0 if percent else 1), (1 if percent or both else 0)
        separator = "<c:separator>, </c:separator>" if value and share else ""
        return (f'<c:dLbls><c:numFmt formatCode={quoteattr(fmt)} sourceLinked="0"/><c:spPr><a:noFill/><a:ln><a:noFill/></a:ln></c:spPr>'
                f'{text_properties(self.state, self.size * 0.85, color, face)}'
                + (f'<c:dLblPos val="{position}"/>' if position else "")
                + f'<c:showLegendKey val="0"/><c:showVal val="{value}"/><c:showCatName val="0"/><c:showSerName val="0"/>'
                f'<c:showPercent val="{share}"/><c:showBubbleSize val="0"/>{separator}</c:dLbls>')

    def series_core(self, j, s):
        cats, name, values = self.refs(j)
        return (f'<c:idx val="{j}"/><c:order val="{j}"/><c:tx>{string_cache(name, [s["name"]])}</c:tx>',
                f'<c:cat>{string_cache(cats, self.categories)}</c:cat><c:val>{number_cache(values, s["values"])}</c:val>')

    def axes(self, ids, horizontal):
        state, style, recipe, scale = self.state, self.style, self.recipe, self.summary["scale"]
        percent = self.kind.startswith("percent")
        face = self.face[False]
        category = recipe.get("category_title")
        value = recipe.get("value_title")
        low, high, step = (0, 1, scale["step"] / 100) if percent else (scale["min"], scale["max"], scale["step"])
        fmt = "0%" if percent else scale["format"]
        ticks = text_properties(state, self.size, style.muted, face)
        axis_line = f'<c:spPr><a:noFill/>{line_properties(state, style.axis, 1.0)}</c:spPr>'
        cat_title = axis_title(state, category, self.size, style.muted, face, -5400000 if horizontal else None) if category else ""
        val_title = axis_title(state, value, self.size, style.muted, face, None if horizontal else -5400000) if value else ""
        grid = (f'<c:majorGridlines><c:spPr>{line_properties(state, style.grid, 0.75)}</c:spPr></c:majorGridlines>'
                if recipe.get("gridlines", True) else "")
        area = "area" in self.kind
        cat = (f'<c:catAx><c:axId val="{ids[0]}"/><c:scaling><c:orientation val="{"maxMin" if horizontal else "minMax"}"/></c:scaling>'
               f'<c:delete val="0"/><c:axPos val="{"l" if horizontal else "b"}"/>{cat_title}<c:numFmt formatCode="General" sourceLinked="0"/>'
               f'<c:majorTickMark val="none"/><c:minorTickMark val="none"/><c:tickLblPos val="low"/>{axis_line}{ticks}'
               f'<c:crossAx val="{ids[1]}"/><c:crosses val="autoZero"/><c:auto val="1"/><c:lblAlgn val="ctr"/>'
               '<c:lblOffset val="100"/><c:noMultiLvlLbl val="0"/></c:catAx>')
        val = (f'<c:valAx><c:axId val="{ids[1]}"/><c:scaling><c:orientation val="minMax"/><c:max val="{number(high)}"/>'
               f'<c:min val="{number(low)}"/></c:scaling><c:delete val="0"/><c:axPos val="{"b" if horizontal else "l"}"/>{grid}{val_title}'
               f'<c:numFmt formatCode={quoteattr(fmt)} sourceLinked="0"/><c:majorTickMark val="none"/><c:minorTickMark val="none"/>'
               f'<c:tickLblPos val="nextTo"/><c:spPr><a:noFill/><a:ln><a:noFill/></a:ln></c:spPr>{ticks}<c:crossAx val="{ids[0]}"/>'
               f'<c:crosses val="{"max" if horizontal else "autoZero"}"/><c:crossBetween val="{"midCat" if area else "between"}"/>'
               f'<c:majorUnit val="{number(step if not percent else scale["step"] / 100)}"/></c:valAx>')
        return cat + val

    def plot(self):
        state, style, recipe, kind = self.state, self.style, self.recipe, self.kind
        ids = (111111111, 222222222)
        sers = []
        if kind in ("pie", "donut"):
            s = self.series[0]
            head, tail = self.series_core(0, s)
            points = "".join(f'<c:dPt><c:idx val="{i}"/><c:bubble3D val="0"/><c:spPr>{solid(state, color)}'
                             f'<a:ln w="19050">{solid(state, style.separator)}</a:ln></c:spPr></c:dPt>'
                             for i, color in enumerate(self.colors))
            content = recipe.get("value_labels", "auto")
            both, only_value = content == "both", content == "value"
            fmt = self.summary["percent_format"] if not only_value else self.summary["label_format"]
            labels = self.labels(style.ink, "outEnd" if kind == "pie" else None, fmt, percent=not only_value and not both, both=both)
            angle = round(recipe.get("start_angle", 0)) % 360
            chart = (f'<c:varyColors val="1"/><c:ser>{head}{points}{labels}{tail}</c:ser>'
                     f'<c:firstSliceAng val="{angle}"/>')
            if kind == "pie":
                return f"<c:pieChart>{chart}</c:pieChart>"
            hole = max(10, min(90, round(recipe.get("hole", 0.55) * 100)))
            return f"<c:doughnutChart>{chart}<c:holeSize val=\"{hole}\"/></c:doughnutChart>"
        horizontal = "horizontal" in kind
        stacked = kind.startswith(("stacked", "percent"))
        grouping = "percentStacked" if kind.startswith("percent") else "stacked" if stacked else "clustered"
        fmt = self.summary["label_format"]
        if "bar" in kind:
            for j, s in enumerate(self.series):
                head, tail = self.series_core(j, s)
                labels = self.labels(style.on(self.colors[j]) if stacked else style.ink, "ctr" if stacked else "outEnd", fmt)
                sers.append(f'<c:ser>{head}<c:spPr>{solid(state, self.colors[j])}</c:spPr><c:invertIfNegative val="0"/>{labels}{tail}</c:ser>')
            gap = recipe.get("bar_gap", 0.3)
            gap_width = max(0, min(500, round(gap * (1 if stacked else len(self.series)) / (1 - gap) * 100)))
            overlap = '<c:overlap val="100"/>' if stacked else ""
            return (f'<c:barChart><c:barDir val="{"bar" if horizontal else "col"}"/><c:grouping val="{grouping}"/><c:varyColors val="0"/>'
                    f'{"".join(sers)}<c:gapWidth val="{gap_width}"/>{overlap}<c:axId val="{ids[0]}"/><c:axId val="{ids[1]}"/></c:barChart>')
        if "area" in kind:
            for j, s in enumerate(self.series):
                head, tail = self.series_core(j, s)
                fill = solid(state, self.colors[j], 1 if stacked else 0.75)
                sers.append(f'<c:ser>{head}<c:spPr>{fill}</c:spPr>{self.labels(style.ink, None, fmt)}{tail}</c:ser>')
            return (f'<c:areaChart><c:grouping val="{"stacked" if stacked else "standard"}"/><c:varyColors val="0"/>{"".join(sers)}'
                    f'<c:axId val="{ids[0]}"/><c:axId val="{ids[1]}"/></c:areaChart>')
        width = recipe.get("line_width") or max(2, round(self.style.fs * 0.18))
        dots = recipe.get("markers", len(self.categories) * len(self.series) <= 60)
        for j, s in enumerate(self.series):
            head, tail = self.series_core(j, s)
            marker = (f'<c:marker><c:symbol val="circle"/><c:size val="{max(2, min(72, round(width * 2.4 * self.pt)))}"/>'
                      f'<c:spPr>{solid(state, self.colors[j])}<a:ln><a:noFill/></a:ln></c:spPr></c:marker>'
                      if dots else '<c:marker><c:symbol val="none"/></c:marker>')
            stroke = (f'<c:spPr><a:ln w="{round(width * self.pt * 12700)}" cap="rnd">{solid(state, self.colors[j])}<a:round/></a:ln></c:spPr>')
            sers.append(f'<c:ser>{head}{stroke}{marker}{self.labels(style.ink, "t", fmt)}{tail}<c:smooth val="0"/></c:ser>')
        return (f'<c:lineChart><c:grouping val="standard"/><c:varyColors val="0"/>{"".join(sers)}<c:marker val="1"/>'
                f'<c:axId val="{ids[0]}"/><c:axId val="{ids[1]}"/></c:lineChart>')

    def xml(self):
        state, style, recipe, kind = self.state, self.style, self.recipe, self.kind
        radial = kind in ("pie", "donut")
        lines = []
        if recipe.get("title"):
            lines.append((recipe["title"], self.size * 1.5, style.ink, self.face[True]))
        if recipe.get("subtitle"):
            lines.append((recipe["subtitle"], self.size * 1.1, style.muted, self.face[False]))
        title = (title_xml(state, lines, style.pad / self.W, style.pad / self.H) if lines else "")
        legend = self.summary.get("legend")
        legend_xml = (f'<c:legend><c:legendPos val="{LEGEND_POSITIONS[legend]}"/><c:overlay val="0"/>'
                      f'{text_properties(state, self.size, style.ink, self.face[False])}</c:legend>' if legend else "")
        axes = "" if radial else self.axes((111111111, 222222222), "horizontal" in kind)
        background = (f'<c:spPr>{solid(state, recipe["background"])}<a:ln><a:noFill/></a:ln></c:spPr>' if recipe.get("background")
                      else '<c:spPr><a:noFill/><a:ln><a:noFill/></a:ln></c:spPr>')
        return (f'{XML}<c:chartSpace {C_NS}><c:date1904 val="0"/><c:roundedCorners val="0"/><c:chart>{title}'
                f'<c:autoTitleDeleted val="{0 if title else 1}"/><c:plotArea><c:layout/>{self.plot()}{axes}'
                f'<c:spPr><a:noFill/><a:ln><a:noFill/></a:ln></c:spPr></c:plotArea>{legend_xml}<c:plotVisOnly val="1"/>'
                f'<c:dispBlanksAs val="gap"/></c:chart>{background}'
                f'{text_properties(state, self.size, style.ink, self.face[False])}'
                '<c:externalData r:id="rId1"><c:autoUpdate val="0"/></c:externalData></c:chartSpace>')


def shapes(slide, layer, bounds, emu, layers, index):
    """The shapes that stand for a chart group on a slide: a native chart (frame), plus any text boxes that
    belong over it. Returns None when the chart cannot be native (the group then exports as shapes)."""
    recipe = layer["chart"]
    notes = []
    if layer.get("rotation", 0) % 360 or layer.get("flip_x") or layer.get("flip_y"):
        slide.chart_info.append({"layer": layer["name"], "native": False,
                                 "reason": "rotated or flipped charts are exported as shapes"})
        return None
    if recipe.get("total_labels") and recipe["kind"].startswith("stacked"):
        notes.append("total labels are not part of a native chart")
    summary = recipe.get("summary") or {}
    if "colors" not in summary:
        slide.chart_info.append({"layer": layer["name"], "native": False, "reason": "redraw the chart (chart --target) first"})
        return None
    chart = Native(slide, layer, emu / 12700)
    rid = slide.exporter.chart(slide, chart.xml(), workbook(recipe["categories"], recipe["series"]))
    x, y, w, h = bounds[layer["id"]]
    ident = slide.ident()
    frame = (f'<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="{ident}" name={quoteattr(layer["name"])}/>'
             '<p:cNvGraphicFramePr><a:graphicFrameLocks noGrp="1"/></p:cNvGraphicFramePr><p:nvPr/></p:nvGraphicFramePr>'
             f'<p:xfrm><a:off x="{round(x * emu)}" y="{round(y * emu)}"/><a:ext cx="{max(1, round(w * emu))}" cy="{max(1, round(h * emu))}"/></p:xfrm>'
             '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/chart">'
             f'<c:chart xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" r:id="{rid}"/></a:graphicData></a:graphic></p:graphicFrame>')
    out = [frame]
    # Text that sits over the chart (a donut's center text, anything the person added to the group).
    sx, sy = w / layer["content_width"], h / layer["content_height"]
    for child in layers:
        if child.get("parent") != layer["id"] or not child["visible"] or child["opacity"] <= 0:
            continue
        if child.get("chart_part") not in (None, "center-text"):
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
    slide.chart_info.append({"layer": layer["name"], "native": True, **({"notes": notes} if notes else {})})
    return out


def content_types(exporter):
    """(Default, Override) content-type entries for the chart parts and their embedded workbooks."""
    overrides = "".join(f'<Override PartName="/ppt/charts/chart{i}.xml" ContentType="{CHART_TYPE}"/>'
                        for i in range(1, len(exporter.charts) + 1))
    return (f'<Default Extension="xlsx" ContentType="{SHEET_TYPE}"/>' if exporter.charts else ""), overrides


def files(exporter):
    """Every chart part and embedded workbook, in a fixed order."""
    result = []
    for i, (xml, book) in enumerate(exporter.charts, 1):
        result.append((f"ppt/charts/chart{i}.xml", xml))
        result.append((f"ppt/charts/_rels/chart{i}.xml.rels",
                       f'{XML}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                       f'<Relationship Id="rId1" Type="{REL}/package" Target="../embeddings/Microsoft_Excel_Sheet{i}.xlsx"/></Relationships>'))
        result.append((f"ppt/embeddings/Microsoft_Excel_Sheet{i}.xlsx", book))
    return result
