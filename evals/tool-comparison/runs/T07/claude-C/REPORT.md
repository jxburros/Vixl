# T07 Batch badges, Lane C (Claude, Python scripting)

**Timing:** start Mon Oct 5 22:19:10 UTC 2026, end Mon Oct 5 22:20:11 UTC 2026 (the `date` calls taken at start and end; the report was written straight afterwards). Tool calls: 11 in total, counting this report and the final hand-off.

## Files

| File | How it was made |
| --- | --- |
| `make_badges.py` | The editable source. A Python script (Pillow, fontTools, reportlab) that reads `../../../fixtures/badges.csv`, or a CSV path passed as the first argument, and regenerates everything below. |
| `badges/badge-01.png` … `badges/badge-10.png` | Made by Pillow. One per CSV row, in file order. Each is 1200 × 900 px RGB with 300 dpi metadata. |
| `badges-print.pdf` | Made by reportlab. 2 pages, US Letter portrait (612 × 792 pt). Each page holds a 2 × 3 grid of the PNGs at actual size (4 × 3 in = 288 × 216 pt). Page 1 has badges 1–6 and page 2 has badges 7–10, with the two empty slots on page 2 at the bottom right. The grid is centred, with margins of 18 pt left/right and 72 pt top/bottom. There are crop marks at every cut line: 0.5 pt black lines, 12 pt long, set 3 pt outside the grid. |
| `REPORT.md` | This file. |

## Design (identical on all ten badges)
- **Top:** the event name "Harbor Makers Summit 2026" (DejaVu Sans Bold 40 px), then the dates line "November 20–21, 2026 · Port Ellery" (DejaVu Sans 30 px, grey-blue), then a thin grey rule. Both lines are centred.
- **Middle:** the name block is centred vertically between the rule and the bar.
  - First name: DejaVu Sans Bold, up to 190 px.
  - Last name: Bold, up to 104 px.
  - Company: Regular, up to 54 px, grey.
  - Each line shrinks in 2 px steps only if it would be wider than 1056 px (a 72 px side margin).
  - The script asserts that the name block fits between the rule and the bar, so text cannot overlap the header or the bar.
  - When the company is empty (Sam Okafor), its line and its gap are left out completely and the block re-centres.
- **Bottom:** a full-width bar, 200 px tall, in the role colour, with the role in capitals (Bold, up to 104 px).
  - Text colour: navy `#14263b` or white, whichever contrasts more with the bar.
  - Resulting contrast: Speaker 7.47:1, Attendee and Volunteer 9.50:1, Sponsor 4.96:1, Staff (white text on navy) 15.33:1.
  - Volunteer, which is not in the colour list, uses the Attendee sea-foam bar but prints "VOLUNTEER".

## Choices and deviations
- **Names:** printed exactly as the CSV has them. The file is read as UTF-8 and only leading and trailing whitespace is trimmed. Capitals are applied to the role only.
- **Font fallback:** the script picks a font for each string. If DejaVu Sans covers every character it uses DejaVu Sans; otherwise it uses IPAGothic. Only 花子 / 山田 (row 5) falls back to IPAGothic. IPAGothic has no bold weight, so that badge's name is drawn in regular weight while the others are bold. The script stops with an error if no font covers a string, so missing glyphs (tofu) cannot appear silently.
- **Shrinking long lines:** some lines are reduced below their nominal size to fit the width: "Bartholomew", "Featherstonehaugh-Villanueva", "Port Ellery Maritime Museum & Historical Society" and "Ana Lucía". The hierarchy still holds (first name > last name > company) because each line's maximum size is smaller than the line above it.
- **Vertical position:** because the name block is centred vertically, its exact position varies slightly from badge to badge. The fixed elements (header, rule, bar) are in the same place on every badge.
- **PDF assembly:** the PDF embeds the 300 dpi PNGs as images; it is not separate vector artwork. The badges sit edge to edge with no gutter, so one cut serves two badges, and the crop marks sit in the outer margins only, with none inside the grid. The PDF is RGB, not CMYK.
- **Checks done:** I looked over a contact sheet of all ten PNGs and a render of PDF page 1 by eye. A script confirmed that all PNGs are 1200 × 900 and that the PDF has 2 Letter pages.

## Unsure about
- Whether regular-weight CJK next to bold Latin is acceptable as "one design".
- Whether crop marks are also expected between badges inside the grid. I put them only on the outside.
