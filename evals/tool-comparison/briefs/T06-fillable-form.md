# T06 · Fillable PDF form

A sign-up form for the café's open mic, which people fill in on screen or print.

**Page.** US Letter, portrait. Header: "Open Mic Sign-up" and, under it, "Tidewick Café · Thursdays
7–10 pm". Footer: "Return this form at the counter or email it to openmic@tidewick.example".
Brand colors if you want them: navy `#14263b`, amber `#f2a541`.

**Fields.** Each field gets a visible label. Use exactly these field names (keys) in the PDF:

| Key | Label | Kind | Rules |
| --- | --- | --- | --- |
| `performer_name` | Performer or act name | text | required, max 80 characters |
| `email` | Email | text | required, email format |
| `phone` | Phone | text | optional |
| `act_type` | Type of act | radio group: `music`, `poetry`, `comedy`, `other` | required |
| `performers` | Number of performers | number | 1 to 6 |
| `needs_mic` | Microphone | checkbox | under a group label "We need:" |
| `needs_amp` | Guitar amp | checkbox | |
| `needs_keyboard` | Keyboard | checkbox | |
| `needs_projector` | Projector | checkbox | |
| `pieces` | Song or piece titles | multiline text, 3 lines | |
| `slot` | Preferred slot | dropdown: `7:00–7:45`, `7:45–8:30`, `8:30–9:15`, `9:15–10:00` | required |
| `photo_consent` | I agree to be photographed during the show | checkbox | optional |
| `signature` | Signature | signature or text field | required |
| `date` | Date | date | required |

Tab order follows the reading order, top to bottom.

**Sample fill.** Also produce a filled, flattened copy (no editable fields left) with these values:

```
performer_name: Bartholomew Okonkwo-Fitzgerald & The Driftwood Quartet
email: bart.driftwood@example.com
phone: (leave empty)
act_type: music
performers: 4
needs_mic: yes   needs_amp: yes   needs_keyboard: no   needs_projector: no
pieces: 1. Salt on the Window / 2. The Keeper's Waltz / 3. Low Tide Blues   (one per line)
slot: 8:30–9:15
photo_consent: yes
signature: B. Okonkwo-Fitzgerald
date: 2026-11-12
```

## Deliverables

| File | Spec |
| --- | --- |
| `signup-form.pdf` | The blank form with real, fillable PDF form fields, as specified |
| `signup-sample.pdf` | The sample fill, flattened; every value fully visible (nothing cut off) |
| your editable source | if your tool has one |

## When you're done

Put every file in the run folder you were given. Then write `REPORT.md` there, listing each file
and how you made it, anything in this brief you didn't do or did differently and why, and anything
you're unsure about. Be exact: the report is checked against the files.
