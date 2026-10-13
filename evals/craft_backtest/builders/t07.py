"""T07 name badges (1200 × 900 each): four of the ten badges and page 2 of the print sheet.

Placed by hand at the ink positions measured in ``runs/T07/claude-V/badges/badge-01.png``, ``badge-03.png``,
``badge-04.png`` and ``badge-06.png``: the event header, a rule, the centred name block (first name, last name,
company) and the role bar along the bottom. The report gives the type (Inter Tight 800 for the names, Inter for the rest). The
print page is ``badges-print.pdf`` page 2 (612 × 792 pt, here at 2× scale): four badges in the first two of
three grid rows, so the last row of the sheet is empty."""

from ..kit import Doc

NAVY, SLATE, GREY, AMBER, FOAM = "#14263b", "#34475e", "#5b6878", "#f2a541", "#a8d5c8"


def badge(first, last, company, role, bar, name_tops, sizes):
    d = Doc(1200, 900, "#ffffff", body=36)
    d.centered("event", "Harbor Makers Summit 2026", 56, 46, NAVY)
    d.centered("dates", "November 20–21, 2026 · Port Ellery", 114, 31, GREY)
    d.rect("header-rule", 60, 178, 1080, 3, "#d5d9de")
    d.centered("first-name", first, name_tops[0], sizes[0], NAVY)
    d.centered("last-name", last, name_tops[1], sizes[1], SLATE)
    if company:
        d.centered("company", company, name_tops[2], sizes[2], GREY)
    d.rect("role-bar", 0, 720, 1200, 180, bar)
    d.centered("role", role, 775, 70, NAVY if bar != NAVY else "#ffffff", tracking=8)
    return d.build()


def print_page():
    d = Doc(1224, 1584, "#ffffff", body=24)
    for row in range(2):
        for col in range(2):
            x, y = 36 + col * 576, 72 + row * 432
            d.outline(f"badge-{row * 2 + col + 7}", x, y, 576, 432, "#c9ced4", 1)
            d.centered(f"badge-{row * 2 + col + 7}-name", ("Priya", "Tomás", "Yuki", "Ada")[row * 2 + col],
                       y + 140, 80, NAVY, left=x, right=x + 576)
            d.rect(f"badge-{row * 2 + col + 7}-bar", x, y + 346, 576, 86, (AMBER, FOAM, NAVY, FOAM)[row * 2 + col])
    return d.build()


def build():
    return {
        "T07-badge-01": badge("Mara", "Quinn", "Tidewick Café", "SPEAKER", AMBER, (241, 465, 594), (180, 104, 50)),
        "T07-badge-03": badge("Zoë", "Ångström-Okonkwo", "Saltmarsh Records", "SPEAKER", AMBER, (241, 465, 594),
                              (180, 104, 50)),
        "T07-badge-04": badge("Bartholomew", "Featherstonehaugh-Villanueva", "Port Ellery Maritime Museum & Historical "
                              "Society", "ATTENDEE", FOAM, (241, 465, 594), (150, 80, 44)),
        "T07-badge-06": badge("Sam", "Okafor", None, "STAFF", NAVY, (281, 505, 0), (180, 104, 50)),
        "T07-print-page-2": print_page(),
    }
