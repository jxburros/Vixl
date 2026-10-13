"""T02 social post (1080 × 1350): open mic night.

Reconstructed by hand from ``runs/T02/claude-V/post.png`` and its report: kicker, two-line headline, a shape
microphone in an amber glow, the date on a full-width amber band, address and call to action, three wave lines
and the URL, each at the ink position measured in the PNG. The report gives the sizes (headline 160, date 48,
details 38, kicker and URL 30)."""

from ..kit import Doc

NAVY, CREAM, AMBER, CORAL, FOAM = "#14263b", "#f7f1e5", "#f2a541", "#e2725b", "#a8d5c8"


def build():
    d = Doc(1080, 1350, NAVY, body=30)
    d.text("kicker", "TIDEWICK CAFÉ PRESENTS", 82, 92, 38, AMBER, tracking=8)
    d.text("headline", "Open Mic Night", 82, 160, 160, CREAM, width=760)
    d.glow("glow", 560, 200, 520, 450, AMBER)
    d.rect("mic-head", 773, 340, 90, 150, CORAL, radius=45)
    d.rect("mic-stand", 815, 490, 5, 98, CREAM)
    d.rect("mic-base", 768, 588, 100, 14, CREAM, radius=7)
    d.rect("date-band", 82, 650, 916, 116, AMBER)
    d.centered("date", "Thursday, November 12 · 7–10 pm", 683, 48, NAVY, left=82, right=998)
    d.text("address", "12 Quay Street, Port Ellery", 82, 812, 38, CREAM)
    d.text("cta", "Free entry · Sign up at the counter", 82, 872, 38, FOAM)
    for i, y in enumerate((1023, 1079, 1135)):
        d.wave(f"wave-{i + 1}", 63, y, 954, 34, FOAM, 4)
        d.intent(f"wave-{i + 1}", role="decoration")
    d.text("url", "tidewick.example", 82, 1212, 30, CREAM)
    return {"T02-post": d.build()}
