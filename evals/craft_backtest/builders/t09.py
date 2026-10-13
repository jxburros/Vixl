"""T09 campaign, Instagram story (1080 × 1920): the winter menu.

Placed by hand at the ink positions measured in ``runs/T09/claude-V/instagram-story.png``: the sun with its
glow, kicker, two-line headline, a short coral rule, the menu line, the date line, the call to action and the
layered hills along the bottom (bleeding off three edges, marked as intentional crops). The story is the size
the judges' composition note names; the other five sizes share its parts."""

from ..kit import Doc

NAVY, CREAM, AMBER, CORAL, FOAM = "#14263b", "#f7f1e5", "#f2a541", "#e2725b", "#a8d5c8"


def build():
    d = Doc(1080, 1920, NAVY, body=46)
    d.glow("sun-glow", 600, 0, 480, 470, AMBER)
    d.ellipse("sun", 720, 110, 240, 240, AMBER)
    d.text("kicker", "TIDEWICK CAFÉ", 90, 550, 38, AMBER, tracking=8)
    d.text("headline", "The Winter Menu is here", 90, 630, 130, CREAM, width=900)
    d.rect("rule", 90, 980, 150, 10, CORAL)
    d.text("menu", "Gingerbread flat white · Smoked maple latte · Cardamom bun", 90, 1040, 46, FOAM, width=900)
    d.text("date", "From Tuesday, December 1 at Tidewick Café", 90, 1200, 46, CREAM, width=700)
    d.text("cta", "See the menu at tidewick.example", 90, 1360, 44, AMBER)
    d.rect("hill-back", -60, 1550, 1200, 430, "#4a6068", radius=200)
    d.rect("hill-front", -80, 1630, 1240, 350, FOAM, radius=180)
    d.rect("shore", -60, 1745, 1200, 235, CREAM, radius=150)
    for name in ("hill-back", "hill-front", "shore"):
        d.intent(name, allow_crop=True)
    return {"T09-story": d.build()}
