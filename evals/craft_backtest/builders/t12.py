"""T12 animated logo intro, last frame (1080 × 1080): the lighthouse, its beam, the name and three waves.

Placed by hand at the ink positions measured in ``runs/T12/claude-V/intro-last-frame.png`` (the frame the
judges reviewed): the beam wedge (a translucent band), the lighthouse tower and lantern on a short sea-foam
bar, the name and tagline, and three thin wave lines across the lower third."""

from ..kit import Doc

NAVY, CREAM, AMBER, FOAM = "#14263b", "#f7f1e5", "#f2a541", "#a8d5c8"


def build():
    d = Doc(1080, 1080, NAVY, body=40)
    d.rect("beam", 176, 260, 330, 110, AMBER, opacity=0.45)
    d.intent("beam", role="decoration")
    d.rect("lantern", 505, 270, 70, 70, AMBER)
    d.rect("tower", 485, 340, 110, 245, CREAM)
    d.rect("bar", 405, 580, 245, 12, FOAM)
    d.centered("name", "Tidewick Café", 548, 104, CREAM)
    d.centered("tagline", "Coffee by the harbor", 669, 46, FOAM)
    for i, y in enumerate((803, 871, 949)):
        d.wave(f"wave-{i + 1}", -20, y, 1120, 46 if i < 2 else 54, FOAM, 6)
        d.intent(f"wave-{i + 1}", role="decoration", allow_crop=True)
    return {"T12-last-frame": d.build()}
