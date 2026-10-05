# T07 · Name badges from a spreadsheet

Conference name badges, one per row of `evals/tool-comparison/fixtures/badges.csv`
(columns `first_name`, `last_name`, `role`, `company`; 10 rows).

**Event.** "Harbor Makers Summit 2026" · "November 20–21, 2026 · Port Ellery".

**Badge design.** 4 × 3 in, landscape, 300 dpi (1200 × 900 px). On every badge:

- the first name, largest;
- the last name, under it, smaller;
- the company, smaller still (leave the line out cleanly when the company is empty);
- the event name and dates, small;
- a full-width color bar with the role in capitals.

Role colors: Speaker = amber `#f2a541`, Attendee = sea-foam `#a8d5c8`, Staff = navy `#14263b`,
Sponsor = coral `#e2725b`. Any other role uses the Attendee color but still prints its own role
name. Text on a bar must contrast with it.

Every name must be printed exactly as written in the file, accents and all, and must fit on the
badge without being cut off or overlapping anything. All ten badges share one design.

## Deliverables

| File | Spec |
| --- | --- |
| `badges/badge-01.png` … `badges/badge-10.png` | One per row, in file order, 1200 × 900 px |
| `badges-print.pdf` | US Letter, portrait; six badges per page (2 columns × 3 rows) at actual size, centered, with crop marks |
| your editable source | if your tool has one (a template, project file or script) |

## When you're done

Put every file in the run folder you were given. Then write `REPORT.md` there, listing each file
and how you made it, anything in this brief you didn't do or did differently and why, and anything
you're unsure about. Be exact: the report is checked against the files.
