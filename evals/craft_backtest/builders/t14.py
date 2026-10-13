"""T14 lyric video, a chorus frame (1280 × 720) at 10 s.

From the template the report describes (current line in a 1040 × 190 centred box at 64 px, next line at 30 px
below it, a section label) and the frame at 10 s of ``runs/T14/claude-V/lighthouse.mp4``: a dusk gradient,
the dark sea band, the lighthouse on its island at the right and the beam behind the lyric."""

from ..kit import Doc


def build():
    d = Doc(1280, 720, "#2a1838", body=30)
    d.op({"type": "gradient", "name": "sky", "x": 0, "y": 0, "width": 1280, "height": 720, "angle": 90,
          "stops": [{"offset": 0, "color": "#2a1838"}, {"offset": 0.75, "color": "#c0605a"},
                    {"offset": 1, "color": "#1e1e2a"}]})
    d.intent("sky", role="background")
    d.rect("sea", 0, 560, 1280, 160, "#1e2130")
    d.intent("sea", allow_crop=True)
    d.rect("beam", 220, 220, 900, 120, "#f7f1e5", opacity=0.25)
    d.intent("beam", role="decoration")
    d.rect("lighthouse", 1132, 420, 36, 150, "#f7f1e5")
    d.ellipse("island", 1080, 555, 140, 40, "#151522")
    d.text("section", "Chorus", 50, 40, 20, "#f7f1e5")
    d.centered("lyric", "Lighthouse, lighthouse, sweep across the sea", 250, 64, "#f7f1e5", left=120, right=1160)
    d.centered("lyric-next", "Turn your golden eye and bring the ships to me", 446, 30, "#e8dccf", left=120,
               right=1160)
    return {"T14-chorus-frame": d.build()}
