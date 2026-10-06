"""Add the role-derived columns the badge template needs (bar colour, bar ink, role in capitals).
Name and company cells are copied byte-for-byte from the fixture."""
import csv, sys
src, dst = sys.argv[1], sys.argv[2]
BAR = {"Speaker": ("#f2a541", "#14263b"), "Attendee": ("#a8d5c8", "#14263b"),
       "Staff": ("#14263b", "#ffffff"), "Sponsor": ("#e2725b", "#14263b")}
with open(src, newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
with open(dst, "w", newline="", encoding="utf-8") as f:
    cols = ["first_name", "last_name", "role", "company", "role_label", "bar_color", "bar_ink"]
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    for r in rows:
        bar, ink = BAR.get(r["role"], BAR["Attendee"])
        w.writerow({**r, "role_label": r["role"].upper(), "bar_color": bar, "bar_ink": ink})
