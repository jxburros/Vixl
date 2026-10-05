"""Generate signup-form.pdf (fillable AcroForm) and signup-sample.pdf (flattened fill).
Uses reportlab for layout/fields and pypdf for post-processing (JS actions, flags, tab order)."""
import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.colors import HexColor, white, black
from reportlab.pdfbase.pdfmetrics import stringWidth
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (NameObject, DictionaryObject, TextStringObject, NumberObject, ArrayObject)

HERE = os.path.dirname(os.path.abspath(__file__))
NAVY, AMBER = HexColor("#14263b"), HexColor("#f2a541")
INK, MUTED, BOX_BG = HexColor("#1d2733"), HexColor("#5b6675"), HexColor("#f7f4ee")
W, H = letter
M = 54                      # side margin
CW = W - 2 * M              # content width
FH = 22                     # text field height
SLOTS = ["7:00–7:45", "7:45–8:30", "8:30–9:15", "9:15–10:00"]
ACTS = [("music", "Music"), ("poetry", "Poetry"), ("comedy", "Comedy"), ("other", "Other")]
NEEDS = [("needs_mic", "Microphone"), ("needs_amp", "Guitar amp"),
         ("needs_keyboard", "Keyboard"), ("needs_projector", "Projector")]

SAMPLE = {
    "performer_name": "Bartholomew Okonkwo-Fitzgerald & The Driftwood Quartet",
    "email": "bart.driftwood@example.com", "phone": "", "act_type": "music",
    "performers": "4", "needs_mic": True, "needs_amp": True, "needs_keyboard": False,
    "needs_projector": False,
    "pieces": "1. Salt on the Window\n2. The Keeper's Waltz\n3. Low Tide Blues",
    "slot": "8:30–9:15", "photo_consent": True,
    "signature": "B. Okonkwo-Fitzgerald", "date": "2026-11-12",
}


def label(c, x, y, text, required=False, size=9.5):
    c.setFont("Helvetica-Bold", size); c.setFillColor(INK)
    c.drawString(x, y, text)
    if required:
        c.setFillColor(HexColor("#b8661a"))
        c.drawString(x + stringWidth(text, "Helvetica-Bold", size) + 2, y, "*")


def box(c, x, y, w, h):
    c.setFillColor(BOX_BG); c.setStrokeColor(NAVY); c.setLineWidth(0.8)
    c.rect(x, y, w, h, fill=1, stroke=1)


def fit_text(c, text, x, y, maxw, font="Helvetica", size=11, minsize=6):
    while size > minsize and stringWidth(text, font, size) > maxw:
        size -= 0.25
    c.setFont(font, size); c.setFillColor(black); c.drawString(x, y, text)
    assert stringWidth(text, font, size) <= maxw, text


def build(path, fill=None):
    """fill=None -> fillable form; fill=dict -> flattened drawing of values."""
    c = canvas.Canvas(path, pagesize=letter)
    c.setTitle("Open Mic Sign-up – Tidewick Café"); c.setAuthor("Tidewick Café")
    c.setSubject("Open mic sign-up form")
    af = c.acroForm if fill is None else None  # no AcroForm at all in the flattened copy
    tf_kw = dict(fontName="Helvetica", fontSize=11, borderColor=NAVY, fillColor=BOX_BG,
                 textColor=black, borderWidth=0.8, forceBorder=True)

    # Header
    c.setFillColor(NAVY); c.rect(0, H - 104, W, 104, fill=1, stroke=0)
    c.setFillColor(AMBER); c.rect(0, H - 108, W, 4, fill=1, stroke=0)
    c.setFillColor(white); c.setFont("Helvetica-Bold", 28)
    c.drawString(M, H - 56, "Open Mic Sign-up")
    c.setFillColor(AMBER); c.setFont("Helvetica", 13)
    c.drawString(M, H - 80, "Tidewick Café · Thursdays 7–10 pm")

    y = H - 136
    c.setFont("Helvetica", 8.5); c.setFillColor(MUTED)
    c.drawString(M, y, "Fields marked")
    c.setFillColor(HexColor("#b8661a")); c.drawString(M + stringWidth("Fields marked ", "Helvetica", 8.5), y, "*")
    c.setFillColor(MUTED); c.drawString(M + stringWidth("Fields marked * ", "Helvetica", 8.5), y, "are required.")

    def text_field(name, lbl, x, y, w, req=False, h=FH, maxlen=None, flags="", tip=None, hint=None):
        label(c, x, y + h + 5, lbl, req)
        if hint:
            c.setFont("Helvetica", 8); c.setFillColor(MUTED)
            c.drawRightString(x + w, y + h + 5, hint)
        if fill is None:
            fl = " ".join(f for f in [flags, "required" if req else ""] if f)
            kw = dict(tf_kw)
            if maxlen: kw["maxlen"] = maxlen
            if "multiline" in flags: kw["fontSize"] = 11
            af.textfield(name=name, tooltip=tip or lbl, x=x, y=y, width=w, height=h,
                         fieldFlags=fl, **kw)
        else:
            box(c, x, y, w, h)
            val = fill.get(name, "")
            if "multiline" in flags:
                lines = val.split("\n")
                lh = (h - 8) / 3
                for i, ln in enumerate(lines):
                    fit_text(c, ln, x + 5, y + h - 4 - lh * (i + 1) + 4, w - 10)
            elif val:
                fit_text(c, val, x + 5, y + (h - 11) / 2 + 2.5, w - 10)

    # 1. Performer name
    y -= 50
    text_field("performer_name", "Performer or act name", M, y, CW, req=True, maxlen=80,
               hint="max 80 characters")
    # 2. Email + phone
    y -= 52
    ew = CW * 0.6
    text_field("email", "Email", M, y, ew - 12, req=True, tip="Email address (name@example.com)")
    text_field("phone", "Phone", M + ew, y, CW - ew, hint="optional")
    # 3. Act type radios
    y -= 30
    label(c, M, y, "Type of act", True)
    y -= 22
    x = M
    for val, txt in ACTS:
        if fill is None:
            af.radio(name="act_type", value=val, selected=False, x=x, y=y, size=14,
                     buttonStyle="circle", borderColor=NAVY, fillColor=BOX_BG,
                     textColor=NAVY, borderWidth=0.8, shape="circle",
                     tooltip="Type of act: " + txt, fieldFlags="required noToggleToOff radio")
        else:
            c.setStrokeColor(NAVY); c.setFillColor(BOX_BG); c.setLineWidth(0.8)
            c.circle(x + 7, y + 7, 7, fill=1, stroke=1)
            if fill.get("act_type") == val:
                c.setFillColor(NAVY); c.circle(x + 7, y + 7, 3.5, fill=1, stroke=0)
        c.setFont("Helvetica", 10.5); c.setFillColor(INK); c.drawString(x + 20, y + 3.5, txt)
        x += 100
    # 4. Number of performers
    y -= 52
    text_field("performers", "Number of performers", M, y, 90, hint=None,
               tip="Number of performers (1 to 6)")
    c.setFont("Helvetica", 8.5); c.setFillColor(MUTED); c.drawString(M + 100, y + 7, "1 to 6")
    # 5. We need
    y -= 30
    label(c, M, y, "We need:")
    y -= 22
    x = M
    for name, txt in NEEDS:
        if fill is None:
            af.checkbox(name=name, x=x, y=y, size=14, checked=False, buttonStyle="check",
                        borderColor=NAVY, fillColor=BOX_BG, textColor=NAVY, borderWidth=0.8,
                        tooltip="We need: " + txt)
        else:
            check(c, x, y, 14, fill.get(name))
        c.setFont("Helvetica", 10.5); c.setFillColor(INK); c.drawString(x + 20, y + 3.5, txt)
        x += 125
    # 6. Pieces
    ph = 62
    y -= 30 + ph
    text_field("pieces", "Song or piece titles", M, y, CW, h=ph, flags="multiline",
               hint="one per line, up to 3")
    # 7. Slot dropdown
    y -= 52
    label(c, M, y + FH + 5, "Preferred slot", True)
    if fill is None:
        ascii_slots = [o.replace("\u2013", "-") for o in SLOTS]  # reportlab AP cannot encode en dash; fixed in postprocess
        af.choice(name="slot", tooltip="Preferred slot", value=" ", options=[" "] + ascii_slots,
                  x=M, y=y, width=180, height=FH, fontName="Helvetica", fontSize=11,
                  borderColor=NAVY, fillColor=BOX_BG, textColor=black, borderWidth=0.8,
                  fieldFlags="combo required", forceBorder=True)
    else:
        box(c, M, y, 180, FH)
        fit_text(c, fill["slot"], M + 5, y + 7.5, 150)
        c.setFillColor(NAVY); p = c.beginPath()
        p.moveTo(M + 163, y + 13); p.lineTo(M + 173, y + 13); p.lineTo(M + 168, y + 7); p.close()
        c.drawPath(p, fill=1, stroke=0)
    # 8. Photo consent
    y -= 34
    if fill is None:
        af.checkbox(name="photo_consent", x=M, y=y, size=14, checked=False, buttonStyle="check",
                    borderColor=NAVY, fillColor=BOX_BG, textColor=NAVY, borderWidth=0.8,
                    tooltip="I agree to be photographed during the show")
    else:
        check(c, M, y, 14, fill.get("photo_consent"))
    c.setFont("Helvetica", 10.5); c.setFillColor(INK)
    c.drawString(M + 20, y + 3.5, "I agree to be photographed during the show")
    c.setFont("Helvetica", 8.5); c.setFillColor(MUTED)
    c.drawString(M + 20 + stringWidth("I agree to be photographed during the show", "Helvetica", 10.5) + 6,
                 y + 3.5, "(optional)")
    # 9. Signature + date
    y -= 62
    sw = CW * 0.62
    text_field("signature", "Signature", M, y, sw - 12, req=True, h=26,
               tip="Signature (type your name)", hint="type your full name")
    text_field("date", "Date", M + sw, y, CW - sw, req=True, h=26, tip="Date (YYYY-MM-DD)",
               hint="YYYY-MM-DD")

    # Footer
    c.setStrokeColor(AMBER); c.setLineWidth(1.5); c.line(M, 62, W - M, 62)
    c.setFont("Helvetica", 9.5); c.setFillColor(NAVY)
    c.drawCentredString(W / 2, 44, "Return this form at the counter or email it to openmic@tidewick.example")
    c.showPage(); c.save()


def check(c, x, y, s, on):
    c.setStrokeColor(NAVY); c.setFillColor(BOX_BG); c.setLineWidth(0.8)
    c.rect(x, y, s, s, fill=1, stroke=1)
    if on:
        c.setStrokeColor(NAVY); c.setLineWidth(1.8); c.setLineCap(1); c.setLineJoin(1)
        p = c.beginPath(); p.moveTo(x + s * 0.22, y + s * 0.52)
        p.lineTo(x + s * 0.42, y + s * 0.28); p.lineTo(x + s * 0.80, y + s * 0.76)
        c.drawPath(p, fill=0, stroke=1); c.setLineWidth(0.8)


JS = {
    "performers": {
        "/K": 'AFNumber_Keystroke(0, 0, 0, 0, "", true);',
        "/F": 'AFNumber_Format(0, 0, 0, 0, "", true);',
        "/V": 'if (event.value !== "" && (isNaN(event.value) || Number(event.value) < 1 || Number(event.value) > 6 || Math.floor(Number(event.value)) != Number(event.value))) { app.alert("Number of performers must be a whole number from 1 to 6."); event.rc = false; }',
    },
    "email": {
        "/V": 'if (event.value !== "" && !/^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/.test(event.value)) { app.alert("Please enter a valid email address, e.g. name@example.com."); event.rc = false; }',
    },
    "date": {
        "/K": 'AFDate_KeystrokeEx("yyyy-mm-dd");',
        "/F": 'AFDate_FormatEx("yyyy-mm-dd");',
    },
}


def postprocess(path):
    r = PdfReader(path); w = PdfWriter(clone_from=r)
    page = w.pages[0]
    page[NameObject("/Tabs")] = NameObject("/R")  # row order == annotation (creation) order
    REQ = 2
    for a in page["/Annots"]:
        a = a.get_object()
        node = a.get("/Parent", a).get_object() if "/T" not in a else a
        name = node.get("/T")
        if name in ("act_type", "slot", "performer_name", "email", "signature", "date"):
            node[NameObject("/Ff")] = NumberObject(int(node.get("/Ff", 0)) | REQ)
        ff = int(node.get("/Ff", 0))
        if node.get("/FT") == "/Btn" and name != "act_type":
            ff &= ~REQ                                   # checkboxes are optional
        node[NameObject("/Ff")] = NumberObject(ff)
        if name != "performer_name" and "/MaxLen" in node:
            del node["/MaxLen"]                          # reportlab defaults MaxLen=100
        if name == "slot":
            # real option strings with en dashes, no preselected value
            node[NameObject("/Opt")] = ArrayObject([TextStringObject(o) for o in SLOTS])
            node[NameObject("/V")] = TextStringObject("")
            node[NameObject("/DV")] = TextStringObject("")
        if name in JS and "/AA" not in node:
            aa = DictionaryObject()
            for k, code in JS[name].items():
                aa[NameObject(k)] = DictionaryObject({NameObject("/S"): NameObject("/JavaScript"),
                                                      NameObject("/JS"): TextStringObject(code)})
            node[NameObject("/AA")] = aa
    # reportlab already wrote appearance streams; leave NeedAppearances unset so viewers use them
    w._root_object["/AcroForm"].pop("/NeedAppearances", None)
    with open(path, "wb") as f:
        w.write(f)


if __name__ == "__main__":
    form = os.path.join(HERE, "signup-form.pdf")
    build(form); postprocess(form)
    build(os.path.join(HERE, "signup-sample.pdf"), fill=SAMPLE)
    print("ok")
