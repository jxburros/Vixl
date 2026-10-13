"""T04 logo sheet (1600 × 1200): the Tidewick mark, lockups and small sizes on a cream half and a navy half.

Reconstructed by hand from ``runs/T04/claude-V/logo-sheet.png``: each mark is a disc (its drawing does not
matter to composition), the wordmarks, taglines and labels are text at their measured ink positions, and the
navy lower half is a panel. The app icon appears only on the cream half, as in the original."""

from ..kit import Doc

NAVY, CREAM, AMBER = "#14263b", "#f5efe4", "#f2a541"


def _half(d, top, ink, accent, paper, suffix, app_icon):
    d.ellipse(f"lockup-mark{suffix}", 90, top + 70, 185, 185, accent if suffix else NAVY)
    d.text(f"wordmark{suffix}", "Tidewick", 306, top + 100, 112, ink)
    d.text(f"tagline{suffix}", "COFFEE BY THE HARBOR", 306, top + 207, 26, accent if suffix else ink, tracking=5)
    d.text(f"label-horizontal{suffix}", "Horizontal lockup", 60, top + 294, 20, ink)
    d.ellipse(f"mark{suffix}", 66, top + 332, 168, 168, accent if suffix else NAVY)
    d.ellipse(f"mark-mono{suffix}", 286, top + 332, 169, 169, CREAM if suffix else NAVY)
    for i, (x, size) in enumerate(((542, 60), (625, 31), (676, 16))):
        d.ellipse(f"small-{i + 1}{suffix}", x, top + 444 + (60 - size) // 2, size, size, accent if suffix else NAVY)
    d.text(f"label-mark{suffix}", "Mark", 60, top + 519, 20, ink)
    d.text(f"label-mono{suffix}", "One-colour mark", 280, top + 519, 20, ink)
    d.text(f"label-sizes{suffix}", "Actual size: 64, 32, 16 px", 540, top + 519, 20, ink)
    d.ellipse(f"stacked-mark{suffix}", 1233, top + 65, 154, 154, accent if suffix else NAVY)
    d.text(f"stacked-wordmark{suffix}", "Tidewick", 1110, top + 245, 92, ink)
    d.text(f"stacked-tagline{suffix}", "COFFEE BY THE HARBOR", 1160, top + 334, 22, accent if suffix else ink,
           tracking=5)
    d.text(f"label-stacked{suffix}", "Stacked lockup", 1080, top + 388, 20, ink)
    if app_icon:
        d.rect("app-icon", 1080, top + 410, 96, 96, NAVY)
        d.text("label-app-icon", "App icon", 1080, top + 519, 20, ink)


def build():
    d = Doc(1600, 1200, CREAM, body=20)
    _half(d, 0, NAVY, AMBER, CREAM, "", True)
    d.rect("navy-half", 0, 600, 1600, 600, NAVY)
    _half(d, 600, CREAM, AMBER, NAVY, "-dark", False)
    return {"T04-logo-sheet": d.build()}
