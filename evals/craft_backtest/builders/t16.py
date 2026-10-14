"""T16 café menu (US Legal at 150 dpi, 1275 × 2100).

Placed by hand at the ink positions measured in ``runs/T16/claude-V/menu-preview.png``: the double frame, the
title and subtitle, four sections (a heading, an amber rule 4 px tall that starts 7 px left of the text, item
rows at a 42 px pitch with a dotted leader and a price set from x 998), the seasonal items' descriptions, and
the key and hours under a short rule. The report gives the type (DM Serif Display, DM Sans)."""

from ..kit import Doc

NAVY, CREAM, AMBER, GREY = "#14263b", "#f7f1e5", "#f2a541", "#5b6470"

SECTIONS = (
    ("COFFEE", 425, [("Espresso", "$3.00"), ("Macchiato", "$3.50"), ("Cortado", "$4.00"), ("Flat white", "$4.75"),
                     ("Cappuccino", "$4.75"), ("Latte", "$5.00"), ("Crème brûlée latte", "$5.75"),
                     ("Drip coffee", "$2.75"), ("Drip refill", "$1.00")]),
    ("TEA", 903, [("Earl Grey", "$3.25"), ("Sencha", "$3.50"), ("Matcha (ceremonial)", "$5.50"),
                  ("Chai latte", "$5.00")]),
    ("BAKERY", 1171, [("Butter croissant", "$3.75"), ("Pain au chocolat", "$4.25"), ("Cardamom bun", "$4.50"),
                      ("Almond financier (N)", "$3.50"), ("Banana bread (V)", "$4.00"),
                      ("Flourless chocolate cake (GF)", "$5.25")]),
)
SEASONAL = (("Smoked maple latte", "$6.00", "Maple syrup smoked in-house, double ristretto, steamed milk."),
            ("Gingerbread flat white", "$5.75", "Molasses, ginger and cinnamon with our house espresso."),
            ("Spiced pear tart (N)", "$6.50", "Poached pear, frangipane, brown-butter crust."))


def _row(d, key, name, price, top):
    d.text(f"{key}-name", name, 197, top, 30, NAVY)
    d.op({"type": "shape", "name": f"{key}-leader", "shape": "rectangle", "x": 330, "y": top + 22,
          "width": 633, "height": 3, "fill": "transparent", "stroke": GREY, "stroke_width": 2, "dash": [2, 8]})
    d.intent(f"{key}-leader", role="decoration")
    d.text(f"{key}-price", price, 998 if price != "$1.00" else 1007, top, 30, NAVY)


def build():
    d = Doc(1275, 2100, CREAM, body=30)
    d.outline("frame-outer", 91, 91, 1093, 1918, NAVY, 3)
    d.outline("frame-inner", 103, 103, 1069, 1894, AMBER, 2)
    d.intent("frame-outer", role="decoration")
    d.intent("frame-inner", role="decoration")
    d.centered("title", "Tidewick Café", 150, 124, NAVY)
    d.centered("subtitle", "Coffee by the harbor", 309, 40, NAVY, tracking=2)
    for heading, top, items in SECTIONS:
        key = heading.lower()
        d.text(f"{key}-heading", heading, 197, top, 40, NAVY)
        d.rect(f"{key}-rule", 190, top + 35, 895, 4, AMBER)
        for i, (name, price) in enumerate(items):
            _row(d, f"{key}-{i + 1}", name, price, top + 41 + 42 * i)
    d.text("seasonal-heading", "SEASONAL", 197, 1523, 40, NAVY)
    d.rect("seasonal-rule", 190, 1558, 895, 4, AMBER)
    for i, (name, price, note) in enumerate(SEASONAL):
        top = 1564 + 77 * i
        _row(d, f"seasonal-{i + 1}", name, price, top)
        d.text(f"seasonal-{i + 1}-note", note, 197, top + 39, 24, GREY)
    d.rect("footer-rule", 540, 1838, 195, 4, AMBER)
    d.centered("key", "V = vegan · GF = gluten-free · N = contains nuts", 1866, 28, GREY)
    d.centered("hours", "Mon–Fri 7 am–6 pm · Sat–Sun 8 am–5 pm · 12 Quay Street, Port Ellery", 1920, 30, NAVY)
    return {"T16-menu": d.build()}
