"""Add the role-derived columns the badge template needs (bar colour, bar ink, role in capitals).
Name and company cells are copied byte-for-byte from the fixture.
Round 2: Sponsor bar is plum #6b3f69 with white ink (navy on plum is too dark to read),
and one extra speaker row (Iris Van der Berg) is appended after the fixture rows."""
import csv, sys
src, dst = sys.argv[1], sys.argv[2]
BAR = {"Speaker": ("#f2a541", "#14263b"), "Attendee": ("#a8d5c8", "#14263b"),
       "Staff": ("#14263b", "#ffffff"), "Sponsor": ("#6b3f69", "#ffffff")}
EXTRA = [{"first_name": "Iris", "last_name": "Van der Berg", "role": "Speaker", "company": "Lowtide Labs"}]
with open(src, newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f)) + EXTRA
with open(dst, "w", newline="", encoding="utf-8") as f:
    cols = ["first_name", "last_name", "role", "company", "role_label", "bar_color", "bar_ink"]
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    for r in rows:
        bar, ink = BAR.get(r["role"], BAR["Attendee"])
        w.writerow({**r, "role_label": r["role"].upper(), "bar_color": bar, "bar_ink": ink})
