"""Fillable PDF forms: AcroForm fields and widgets over Vixl's page artwork.

Vixl draws each field's box into the page (exactly as in the PNG); the PDF field on top is
transparent and draws only the value — typed text, the check mark, the radio dot or the selected
option. Every widget gets a generated appearance (``NeedAppearances`` is never set), an
accessible name (``/TU``) and a place in the tab order (the order of the page's ``/Annots``,
which each page declares with ``/Tabs /S``). Text is typed in Helvetica (``/DA``) unless the form's
``entry_font`` is ``embed``: then each field's own font is embedded as a WinAnsi TrueType font
(the whole Western European character set, since viewers type with it) and named in ``/DA`` and
``/DR``. Values in the appearance streams are laid out with the metrics of the font typed in.

The only actions in the file are the JavaScript field actions that enforce a field's validation
rules (``form_rules``): no links, submit, launch or open actions. Every string is hex, and
output is byte-identical for identical input (``pdf_writer``).
"""

from .errors import VixlError, require
from .form_rules import actions
from .pdf_writer import Name, Text

# Helvetica advance widths (1/1000 em) for WinAnsiEncoding codes 32–255, from Adobe's Core 14
# AFM metrics (freely redistributable). Undefined codes use the space width.
_WIDTHS = (
    "278 278 355 556 556 889 667 191 333 333 389 584 278 333 278 278 556 556 556 556 556 556 556 556 556 556 278 278 "
    "584 584 584 556 1015 667 667 722 722 667 611 778 722 278 500 667 556 833 722 778 667 778 722 667 611 722 667 944 "
    "667 667 611 278 278 278 469 556 333 556 556 500 556 556 278 556 556 222 222 500 222 833 556 556 556 556 333 500 "
    "278 556 500 722 500 500 500 334 260 334 584 278 556 278 222 556 333 1000 556 556 333 1000 667 333 1000 278 611 "
    "278 278 222 222 333 333 350 556 1000 333 1000 500 333 944 278 500 667 278 333 556 556 556 556 260 556 333 737 "
    "370 556 584 333 737 333 400 584 333 333 333 556 537 278 333 333 365 556 834 834 834 611 667 667 667 667 667 667 "
    "1000 722 667 667 667 667 278 278 278 278 722 722 778 778 778 778 778 584 778 722 722 722 722 667 667 611 556 556 "
    "556 556 556 556 889 500 556 556 556 556 278 278 278 278 556 556 556 556 556 556 556 584 611 556 556 556 556 500 "
    "556 500"
)
HELVETICA = dict(zip(range(32, 256), map(int, _WIDTHS.split())))
ASCENT, DESCENT = 718, -207  # Helvetica, 1/1000 em
FLAGS = {"read_only": 1, "required": 2, "multiline": 1 << 12, "no_toggle_off": 1 << 14, "radio": 1 << 15,
         "combo": 1 << 17, "edit": 1 << 18, "comb": 1 << 24}
CAPTIONS = {"check": "4", "cross": "8", "dot": "l"}  # ZapfDingbats


class EntryFont:
    """The font a viewer types a field's entries in: its resource name, WinAnsi advance widths and
    vertical metrics (1/1000 em)."""

    def __init__(self, resource, widths, ascent, descent, default_width=278, family="Helvetica"):
        self.resource, self.widths, self.ascent, self.descent = resource, widths, ascent, descent
        self.default_width, self.family = default_width, family


HELV = EntryFont("Helv", HELVETICA, ASCENT, DESCENT)


def encode(text):
    """WinAnsi bytes for typed-entry text; raises when a character is outside it."""
    try:
        return text.encode("cp1252")
    except UnicodeEncodeError as exc:
        raise VixlError("invalid_format", "The entry font (Western European characters) cannot show some characters; "
                        "fill with mode flatten instead", field="values") from exc


def text_width(data, size, font=HELV):
    return sum(font.widths.get(byte, font.default_width) for byte in data) * size / 1000


def wrap(text, size, width, font=HELV):
    """Break ``text`` into lines that fit ``width`` points in ``font`` (words longer than a
    line are broken)."""
    lines = []
    for paragraph in text.split("\n"):
        current = ""
        for word in paragraph.split(" "):
            candidate = word if not current else current + " " + word
            if text_width(encode(candidate), size, font) <= width or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
            while text_width(encode(current), size, font) > width and len(current) > 1:
                cut = len(current)
                while cut > 1 and text_width(encode(current[:cut]), size, font) > width:
                    cut -= 1
                lines.append(current[:cut])
                current = current[cut:]
        lines.append(current)
    return lines


def entry_font_problem(data):
    """Why a font file cannot be embedded for typed entries, or None when it can."""
    from .fonts import embedding
    from .pdf_writer import FontSet

    if not FontSet.embeddable(data):
        return "it is not a TrueType (glyf) font"
    permission = embedding(data)
    if permission in ("restricted", "preview-print"):
        return f"its embedding permission is {permission}"
    return None


def embed_entry_font(writer, data, resource):
    """Write ``data`` as a simple TrueType font with WinAnsiEncoding (subset to the WinAnsi
    characters, which is what a viewer can type with it); returns (EntryFont, font ref)."""
    import io
    import logging

    from fontTools import subset
    from fontTools.ttLib import TTFont

    from .pdf_writer import _postscript_name

    logging.getLogger("fontTools.subset").setLevel(logging.WARNING)
    chars = {code: bytes([code]).decode("cp1252", "ignore") for code in range(32, 256)}
    chars = {code: char for code, char in chars.items() if char}
    font = TTFont(io.BytesIO(data), recalcTimestamp=False)
    options = subset.Options()
    options.notdef_outline = True
    options.name_IDs = ["*"]
    options.layout_features = []
    options.drop_tables += ["GSUB", "GPOS", "GDEF", "DSIG", "FFTM"]
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=[ord(c) for c in chars.values()])
    subsetter.subset(font)
    buffer = io.BytesIO()
    font.save(buffer)
    program = buffer.getvalue()
    head, hhea, hmtx = font["head"], font["hhea"], font["hmtx"]
    scale = 1000 / head.unitsPerEm
    cmap = font.getBestCmap() or {}
    missing = round(hmtx[".notdef"][0] * scale) if ".notdef" in hmtx.metrics else 0
    widths = {code: round(hmtx[cmap[ord(char)]][0] * scale) if ord(char) in cmap else missing
              for code, char in chars.items()}
    os2 = font["OS/2"] if "OS/2" in font else None
    base = _postscript_name(font)
    file_ref = writer.add_stream({"Length1": len(program)}, program)
    descriptor = writer.add({
        "Type": Name("FontDescriptor"), "FontName": Name(base), "Flags": 32,
        "FontBBox": [round(head.xMin * scale), round(head.yMin * scale), round(head.xMax * scale), round(head.yMax * scale)],
        "ItalicAngle": float(font["post"].italicAngle) if "post" in font else 0,
        "Ascent": round(hhea.ascent * scale), "Descent": round(hhea.descent * scale),
        "CapHeight": round((getattr(os2, "sCapHeight", 0) or hhea.ascent * 0.7) * scale),
        "StemV": 80, "FontFile2": file_ref, "MissingWidth": missing,
    })
    ref = writer.add({"Type": Name("Font"), "Subtype": Name("TrueType"), "BaseFont": Name(base), "FirstChar": 32,
                      "LastChar": 255, "Widths": [widths.get(code, missing) for code in range(32, 256)],
                      "Encoding": Name("WinAnsiEncoding"), "FontDescriptor": descriptor})
    family = font["name"].getDebugName(16) or font["name"].getDebugName(1) or base
    entry = EntryFont(resource, widths, round(hhea.ascent * scale), round(hhea.descent * scale), missing, family)
    return entry, ref


def _num(value):
    from .pdf_export import _fmt

    return _fmt(value)


def _rgb(rgba):
    return f"{_num(rgba[0] / 255)} {_num(rgba[1] / 255)} {_num(rgba[2] / 255)}"


class FormWriter:
    """Collects fields and widgets while ``export_pdf`` writes pages, then the AcroForm."""

    def __init__(self, project, values=None):
        self.project = project
        self.values = values or {}
        self.fields = []        # top-level field refs, in document order
        self.radios = {}        # key → {"ref", "kids", "record", "label", "value"}
        self.fonts = {}
        self.writer = None
        self.k = 1.0
        self.entry_fonts = {}   # font digest -> EntryFont (embedded) or the reason it cannot be
        self.embedded = []      # families embedded for typed entries
        self.fallbacks = []     # {"field", "reason"} for fields typed in Helvetica instead
        from .forms import form_settings

        self.embed = form_settings(project.state).get("entry_font") == "embed"

    def entry_font(self, view, item):
        """The EntryFont a field's entries are typed in (Helvetica unless ``entry_font`` is embed)."""
        if not self.embed:
            return HELV
        from .forms import _text_layer
        from .pdf_writer import font_digest
        from .text import primary_font_data

        data = primary_font_data(view, _text_layer(item, "", float(item.get("size", 16))))
        data = data[0] if isinstance(data, tuple) else data
        key = font_digest(data)
        if key not in self.entry_fonts:
            problem = entry_font_problem(data)
            if problem:
                self.entry_fonts[key] = problem
            else:
                resource = f"VxE{sum(isinstance(v, EntryFont) for v in self.entry_fonts.values()) + 1}"
                font, ref = embed_entry_font(self.writer, data, resource)
                self.fonts[resource] = ref
                self.entry_fonts[key] = font
                self.embedded.append(font.family)
        found = self.entry_fonts[key]
        if isinstance(found, EntryFont):
            return found
        self.fallbacks.append({"field": item["name"], "reason": found})
        return HELV

    def font(self, name):
        if name not in self.fonts:
            base = {"Helv": "Helvetica", "ZaDb": "ZapfDingbats"}[name]
            entry = {"Type": Name("Font"), "Subtype": Name("Type1"), "BaseFont": Name(base)}
            if name == "Helv":
                entry["Encoding"] = Name("WinAnsiEncoding")
            self.fonts[name] = self.writer.add(entry)
        return self.fonts[name]

    def xobject(self, w, h, ops, fonts=()):
        resources = {"Font": {name: self.font(name) for name in fonts}} if fonts else {}
        return self.writer.add_stream({"Type": Name("XObject"), "Subtype": Name("Form"), "BBox": [0, 0, round(w, 4), round(h, 4)],
                                       "Resources": resources}, "\n".join(ops).encode("latin-1"))

    def text_appearance(self, item, w, h, display, size, rgba, font=HELV):
        record = item["field"]
        pad = float(item.get("padding", 0)) * self.k
        ascent, descent = font.ascent, font.descent
        ops = ["/Tx BMC"]
        if display:
            ops += ["q", f"{_num(pad)} {_num(pad)} {_num(max(0.0, w - 2 * pad))} {_num(max(0.0, h - 2 * pad))} re W n",
                    "BT", f"/{font.resource} {_num(size)} Tf", f"{_rgb(rgba)} rg"]
            align = item.get("align", "left")
            if record.get("comb"):
                cells = record["max_length"]
                for i, char in enumerate(display[:cells]):
                    data = encode(char)
                    x = w * (i + 0.5) / cells - text_width(data, size, font) / 2
                    y = (h - (ascent - descent) * size / 1000) / 2 - descent * size / 1000
                    ops += [f"1 0 0 1 {_num(x)} {_num(y)} Tm", f"<{data.hex().upper()}> Tj"]
            else:
                inner = max(1.0, w - 2 * pad)
                multiline = record["kind"] == "multiline"
                lines = wrap(display, size, inner, font) if multiline else [display]
                natural = (ascent - descent) * size / 1000
                leading = natural * 1.2  # the line pitch of Vixl's own layout
                if multiline:
                    top = h - pad - ascent * size / 1000 - natural * 0.1
                else:
                    top = (h - (ascent - descent) * size / 1000) / 2 - descent * size / 1000
                for number, line in enumerate(lines):
                    data = encode(line)
                    width = text_width(data, size, font)
                    x = pad + ((inner - width) / 2 if align == "center" else inner - width if align == "right" else 0)
                    ops += [f"1 0 0 1 {_num(x)} {_num(top - number * leading)} Tm", f"<{data.hex().upper()}> Tj"]
            ops += ["ET", "Q"]
        ops.append("EMC")
        return self.xobject(w, h, ops, [font.resource] if display else [])

    def mark_appearance(self, item, w, h, rgba):
        from .forms import MARK_PATHS, default_appearance

        appearance = {**default_appearance(self.project.state, item["field"]["kind"]), **(item.get("appearance") or {})}
        mark = appearance.get("mark", "dot" if item["field"]["kind"] == "radio" else "check")
        if mark == "dot":
            r = min(w, h) * 0.25
            cx, cy, c = w / 2, h / 2, 0.5523 * min(w, h) * 0.25
            ops = [f"{_rgb(rgba)} rg", f"{_num(cx + r)} {_num(cy)} m",
                   f"{_num(cx + r)} {_num(cy + c)} {_num(cx + c)} {_num(cy + r)} {_num(cx)} {_num(cy + r)} c",
                   f"{_num(cx - c)} {_num(cy + r)} {_num(cx - r)} {_num(cy + c)} {_num(cx - r)} {_num(cy)} c",
                   f"{_num(cx - r)} {_num(cy - c)} {_num(cx - c)} {_num(cy - r)} {_num(cx)} {_num(cy - r)} c",
                   f"{_num(cx + c)} {_num(cy - r)} {_num(cx + r)} {_num(cy - c)} {_num(cx + r)} {_num(cy)} c", "f"]
            return self.xobject(w, h, ops), mark
        side = min(w, h) * 0.8
        scale = side / 100
        ox, oy = (w - side) / 2, (h - side) / 2
        ops = [f"{_rgb(rgba)} RG", f"{_num(12 * scale)} w", "1 J", "1 j"]
        tokens = MARK_PATHS[mark].split()
        i = 0
        while i < len(tokens):
            op, x, y = tokens[i], float(tokens[i + 1]), float(tokens[i + 2])
            # Path coordinates are y-down in a 100 × 100 box; PDF is y-up.
            ops.append(f"{_num(ox + x * scale)} {_num(oy + (100 - y) * scale)} {'m' if op == 'M' else 'l'}")
            i += 3
        ops.append("S")
        return self.xobject(w, h, ops), mark

    def annotations(self, view, number, builder):
        """Widgets for one page, in tab order; called by ``export_pdf`` for each page."""
        from .design import resolve_color
        from .forms import current_values, field_geometry, label_text, option_label, option_values, tab_order, transformed
        from .render import color

        self.writer = builder.writer
        state = view.state
        canvas = state["canvas"]
        self.k = k = builder.k
        ky = getattr(builder, "ky", k)
        page_height = canvas["height"] * ky
        entries, resolved, _, _ = field_geometry(view)
        values = current_values(view)
        refs = []
        for item, (x, y, w, h), matrix in tab_order(self.project.state, entries):
            record = item["field"]
            if transformed(matrix):
                raise VixlError("invalid_operation", f"Field {item['name']!r} is rotated or flipped; PDF fields are upright "
                                "rectangles", field="target")
            rect = [round(x * k, 4), round(page_height - (y + h) * ky, 4), round((x + w) * k, 4), round(page_height - y * ky, 4)]
            width, height = w * k, h * ky
            scale = h / max(1e-9, item["height"])
            size = float(item.get("size", 16)) * scale * k
            rgba = color(resolve_color(item.get("color", "#1f2328"), state))
            value, display = values.get(record["key"], (None, ""))
            label = label_text(view, item, resolved)
            flags = (FLAGS["read_only"] if record.get("read_only") else 0) | (FLAGS["required"] if record.get("required") else 0)
            widget = {"Type": Name("Annot"), "Subtype": Name("Widget"), "Rect": rect, "F": 4}
            kind = record["kind"]
            if kind == "radio":
                group = self.radios.get(record["key"])
                if group is None:
                    group = self.radios[record["key"]] = {"ref": self.writer.reserve(), "kids": [], "record": record,
                                                          "label": "", "value": value}
                    self.fields.append(group["ref"])
                if record.get("group_label"):
                    group["label"] = record["group_label"]
                mark_rgba = color(resolve_color((item.get("appearance") or {}).get("mark_color", item.get("color", "#1f2328")), state))
                on, mark = self.mark_appearance(item, width, height, mark_rgba)
                off = self.xobject(width, height, [])
                option = record["option"]
                widget.update(Parent=group["ref"], AS=Name(option if value == option else "Off"),
                              AP={"N": {option: on, "Off": off}}, MK={"CA": Text(CAPTIONS[mark])},
                              TU=Text(label) if label else None)
                ref = self.writer.add(widget)
                group["kids"].append(ref)
                refs.append(ref)
                continue
            field = {**widget, "T": Text(record["key"]), "TU": Text(label) if label else None,
                     "Ff": flags or None, "Q": {"center": 1, "right": 2}.get(item.get("align", "left"), 0)}
            if kind == "checkbox":
                on_value = record.get("on_value", "Yes")
                mark_rgba = color(resolve_color((item.get("appearance") or {}).get("mark_color", item.get("color", "#1f2328")), state))
                on, mark = self.mark_appearance(item, width, height, mark_rgba)
                off = self.xobject(width, height, [])
                state_name = Name(on_value if value else "Off")
                field.update(FT=Name("Btn"), V=state_name, DV=state_name, AS=state_name,
                             AP={"N": {on_value: on, "Off": off}}, MK={"CA": Text(CAPTIONS[mark])},
                             DA=Text(f"/ZaDb 0 Tf {_rgb(mark_rgba)} rg"))
                field.pop("Q")
            elif kind == "signature":
                field.update(FT=Name("Sig"), AP={"N": self.xobject(width, height, [])})
                field.pop("Q")
            elif kind == "dropdown":
                field["FT"] = Name("Ch")
                field["Ff"] = flags | FLAGS["combo"] | (FLAGS["edit"] if record.get("editable") else 0)
                field["Opt"] = [[Text(v), Text(str(option_label(record, v)))] for v in option_values(record)]
                font = self.entry_font(view, item)
                field["DA"] = Text(f"/{font.resource} {_num(size)} Tf {_rgb(rgba)} rg")
                if value not in (None, ""):
                    field["V"] = field["DV"] = Text(str(value))
                field["AP"] = {"N": self.text_appearance(item, width, height, display, size, rgba, font)}
            else:
                field["FT"] = Name("Tx")
                if kind == "multiline":
                    field["Ff"] = flags | FLAGS["multiline"]
                if record.get("comb"):
                    field["Ff"] = flags | FLAGS["comb"]
                if "max_length" in record:
                    field["MaxLen"] = record["max_length"]
                font = self.entry_font(view, item)
                field["DA"] = Text(f"/{font.resource} {_num(size)} Tf {_rgb(rgba)} rg")
                field["AA"] = actions(record)
                if display:
                    field["V"] = field["DV"] = Text(display)
                field["AP"] = {"N": self.text_appearance(item, width, height, display, size, rgba, font)}
            ref = self.writer.add(field)
            self.fields.append(ref)
            refs.append(ref)
        if refs:
            builder.page_extra = {"Tabs": Name("S")}  # visit widgets in /Annots order
        return refs

    def acroform(self, writer):
        """The AcroForm dictionary (written after every page)."""
        self.writer = writer
        for key, group in self.radios.items():
            record = group["record"]
            flags = FLAGS["radio"] | FLAGS["no_toggle_off"] | (FLAGS["required"] if record.get("required") else 0) | (
                FLAGS["read_only"] if record.get("read_only") else 0)
            value = group["value"]
            writer.add({"FT": Name("Btn"), "T": Text(key), "TU": Text(group["label"]) if group["label"] else None,
                        "Ff": flags, "V": Name(value) if value else Name("Off"), "Kids": group["kids"]}, group["ref"])
        self.font("Helv"), self.font("ZaDb")
        resources = {"Font": dict(self.fonts)}
        return {"Fields": self.fields, "DR": resources, "DA": Text("/Helv 0 Tf 0 g")}


def export_fillable(project, path=None, *, pages=None, values=None, dpi=None, content="vector", background="white",
                    report=None, title=None, lang=None, views=None):
    """A fillable PDF of the document (``values`` prefill it: editable filling)."""
    from .forms import form_settings, has_fields, reject_signature_samples, with_values
    from .pdf_export import export_pdf

    require(has_fields(project), "This document has no fields; add some with the field operation", field="fillable")
    reject_signature_samples(project, values)
    source = with_values(project, values) if values else project
    settings = form_settings(project.state)
    form = FormWriter(source)
    data = export_pdf(source, path, pages=pages, content=content, dpi=dpi, background=background,
                      title=title if title is not None else settings.get("title"), lang=lang or settings.get("lang"),
                      annotations=form.annotations, acroform=form.acroform, fillable=True, report=report, views=views)
    if report is not None and form.embed:
        report["entry_font"] = {"mode": "embed", "embedded": sorted(set(form.embedded)),
                                **({"helvetica_fallback": form.fallbacks} if form.fallbacks else {})}
        if form.fallbacks:
            report.setdefault("warnings", []).extend(
                f"Field {item['field']!r} is typed in Helvetica: its font cannot be embedded ({item['reason']})"
                for item in form.fallbacks)
    return data
