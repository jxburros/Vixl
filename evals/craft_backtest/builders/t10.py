"""T10 photo edit, captioned crop (1600 × 900): the coast at golden hour.

The edited photograph is the whole canvas, so it stands here as a full-canvas sky-to-sea gradient (a
background to the checks); the headland, lighthouse, rocks and figure are dark silhouettes and the caption
sits at the bottom left, all at the positions measured in ``runs/T10/claude-V/coast-caption.png``."""

from ..kit import Doc


def build():
    d = Doc(1600, 900, "#2b2140", body=40)
    d.op({"type": "gradient", "name": "photo", "x": 0, "y": 0, "width": 1600, "height": 900, "angle": 90,
          "stops": [{"offset": 0, "color": "#3a2a6a"}, {"offset": 0.5, "color": "#f08a5a"},
                    {"offset": 1, "color": "#3c2f45"}]})
    d.intent("photo", role="background")
    d.rect("headland", 0, 390, 520, 180, "#1a1424", radius=60)
    d.rect("lighthouse", 120, 240, 30, 160, "#1a1424")
    d.rect("rocks", 900, 740, 700, 160, "#141019", radius=40)
    d.rect("figure", 1110, 560, 60, 200, "#141019", radius=20)
    d.text("caption", "Port Ellery at golden hour", 72, 770, 44, "#f7f1e5")
    return {"T10-caption": d.build()}
