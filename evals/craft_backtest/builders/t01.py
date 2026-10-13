"""T01 picture (2400 × 1600): a flat-style lighthouse at dusk with a beam, sailboats, stars and waves.

Reconstructed by hand from ``runs/T01/claude-V/picture.png``: the sky, sea, headland, lighthouse, beam, boats,
stars and wave lines at their measured places, drawn as plain shapes. No text."""

from ..kit import Doc


def build():
    d = Doc(2400, 1600, "#2a2f5c", body=42)
    d.op({"type": "gradient", "name": "sky", "x": 0, "y": 0, "width": 2400, "height": 1050, "angle": 90,
          "stops": [{"offset": 0, "color": "#262a57"}, {"offset": 0.6, "color": "#8a5a7a"},
                    {"offset": 1, "color": "#f2a541"}]})
    d.rect("sea", 0, 1030, 2400, 570, "#2c3566")
    d.rect("headland", 0, 980, 1100, 620, "#3a3550")
    d.rect("lighthouse", 370, 330, 120, 650, "#f7f1e5")
    d.rect("lantern", 350, 280, 160, 70, "#14263b")
    d.glow("lamp-glow", 280, 200, 300, 230, "#f2a541")
    d.op({"type": "shape", "name": "beam", "shape": "triangle", "x": 480, "y": 330, "width": 1920, "height": 690,
          "fill": "#f7f1e5", "opacity": 0.35, "rotation": -90})
    for i, (x, y, w) in enumerate([(1480, 1020, 130), (1960, 1100, 170)]):
        d.op({"type": "shape", "name": f"sail-{i + 1}", "shape": "triangle", "x": x, "y": y, "width": w,
              "height": round(w * 1.2), "fill": "#f7f1e5"})
        d.rect(f"hull-{i + 1}", x - 10, y + round(w * 1.2), w + 20, 18, "#14263b")
    for i, (x, y) in enumerate([(180, 120), (860, 230), (1500, 80), (1980, 110), (2240, 260), (1180, 60)]):
        d.ellipse(f"star-{i + 1}", x, y, 10, 10, "#f7f1e5")
    for i, (x, y, w) in enumerate([(1100, 1230, 300), (1620, 1150, 260), (2100, 1420, 220)]):
        d.rect(f"wave-{i + 1}", x, y, w, 5, "#a8d5c8", opacity=0.6)
    return {"T01-picture": d.build()}
