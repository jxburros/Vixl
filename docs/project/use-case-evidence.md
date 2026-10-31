# Use-case evidence

[Project documentation](README.md) · [Use-case catalog](../use-cases.md)

The [use-case catalog](../use-cases.md) gives each use case its tier, main route and typical calls and minutes. This
page records where those figures come from, so the catalog stays a plain list for readers. A row that is not listed
below is an estimate (`E`). The last table of the catalog (interface and path authoring additions, 0.26) is
estimated throughout.

## Evidence codes

| Code | Meaning |
| --- | --- |
| **M:T01…T16** | Measured: Vixl lane of the [tool comparison](https://github.com/jxburros/VixlExamples/blob/main/eval-results/2026-10-06-vixl-0.20-tool-comparison.md) on 0.20.0, round 1 (all tool calls, including reads and file checks; median-style single runs). **R2** marks the round-2 revision of the same brief. |
| **M:eval:name** | Measured: live agent run of [`evals/tasks/name.json`](../../evals/tasks) on 0.18.0 ([results](https://github.com/jxburros/VixlExamples/blob/main/eval-results/2026-10-05-full-evaluation.md)). Counts are Vixl calls only, so add 1–3 for file reads. |
| **M:X01…X10** | Measured: [exploration](https://github.com/jxburros/VixlExamples/blob/main/explorations/README.md) build script on 0.21.0. The time is the *script's* run time; writing such a script by hand is T5. |
| **E** | Estimate from the operations involved and the nearest measured case. Replace with a measurement when you have one. |

## Measured rows

| ID | Tier | Evidence |
| --- | --- | --- |
| DAT-03 | T0 · One-shot | M:T08 R2 |
| DOC-24 | T0 · One-shot | M:eval:print-cmyk |
| DOC-30 | T1 · Quick | M:eval:copy-between-documents |
| SHP-20 | T1 · Quick | M:eval:equal-spacing |
| QA-10 | T1 · Quick | M:eval:fix-layout |
| TXT-20 | T1 · Quick | M:eval:font-pairing |
| FRM-01 | T1 · Quick | M:eval:form-batch-fill |
| FRM-02 | T1 · Quick | M:eval:form-registration |
| SOC-01 | T1 · Quick | M:eval:layout-filled |
| PHO-10 | T1 · Quick | M:eval:photo-caption |
| COL-01 | T1 · Quick | M:eval:restore-deleted |
| SOC-02 | T1 · Quick | M:eval:roll-applied |
| SOC-03 | T1 · Quick | M:eval:story-list |
| BRD-01 | T1 · Quick | M:eval:svg-logo-import |
| SOC-04 | T1 · Quick | M:eval:template-creation |
| MOT-01 | T1 · Quick | M:eval:timeline-motion |
| PRD-01 | T1 · Quick | M:eval:variable-variants |
| QA-11 | T1 · Quick | M:eval:workflow-checked-edit |
| ILL-20 | T2 · Standard | M:T01 |
| SOC-30 | T2 · Standard | M:T02 |
| DAT-20 | T2 · Standard | M:T08 |
| FRM-10 | T2 · Standard | M:T06 |
| PIX-10 | T2 · Standard | M:T13 |
| MOT-10 | T2 · Standard | M:T12 |
| PRN-10 | T2 · Standard | M:T03 |
| SOC-31 | T2 · Standard | M:eval:youtube-thumbnail |
| ILL-21 | T2 · Standard | M:T01 R2 |
| SOC-32 | T2 · Standard | M:T02 R2 |
| PRN-11 | T2 · Standard | M:T03 R2 |
| BRD-10 | T2 · Standard | M:T04 R2 |
| DEK-10 | T2 · Standard | M:T05 R2 |
| FRM-11 | T2 · Standard | M:T06 R2 |
| PRD-10 | T2 · Standard | M:T07 R2 |
| DAT-21 | T2 · Standard | M:T08 R2 |
| PHO-20 | T2 · Standard | M:T10 R2 |
| DRW-10 | T2 · Standard | M:T11 R2 |
| MOT-11 | T2 · Standard | M:T12 R2 |
| PIX-11 | T2 · Standard | M:T13 R2 |
| MOT-12 | T2 · Standard | M:T14 R2 |
| ILL-22 | T2 · Standard | M:T15 R2 |
| PRN-12 | T2 · Standard | M:T16 R2 |
| PRN-30 | T3 · Involved | M:T16 |
| DEK-30 | T3 · Involved | M:T05 |
| PRD-30 | T3 · Involved | M:T07 |
| ILL-40 | T3 · Involved | M:T15 |
| SOC-60 | T3 · Involved | M:T09 |
| PHO-40 | T3 · Involved | M:T10 |
| DRW-30 | T3 · Involved | M:T11 |
| MOT-30 | T3 · Involved | M:T14 |
| BRD-40 | T4 · Large | M:T04 |
| BRD-41 | T4 · Large | M:X02 |
| PRN-50 | T4 · Large | M:X01 |
| DAT-50 | T4 · Large | M:X08 |
| PRD-40 | T4 · Large | M:X07 |
| MOT-40 | T4 · Large | M:X03 |
| PIX-40 | T4 · Large | M:X04 |
| ILL-50 | T4 · Large | M:X05 |
| PHO-50 | T4 · Large | M:X06 |
| SOC-70 | T4 · Large | M:X09 |
| MOT-41 | T4 · Large | M:X10 |

## Maintaining the catalog

- **Add a row** whenever you find a use case that isn't here: a user request, an issue, a new
  operation, a template, a size, a guide kind or a workflow action. Pick the domain prefix, take
  the next free number, and put it in the catalog under the tier you expect. Its evidence is `E` until measured.
- **Measure when you can.** An eval run, a tool-comparison brief, an exploration build or a
  timed session all count. List the row under [measured rows](#measured-rows) with the source and the version, and move the row if it
  lands in another tier.
- **Never renumber.** IDs stay attached to the use case so links and issues keep working.
- **Move blocked rows** into a tier when a release fixes them, and say so in the notes ("since 0.22").
- **Name releases, not issues.** Catalog notes say "since 0.25", never "(#512)"; record the issue under
  [issue provenance](#issue-provenance). A test fails on issue references in user pages.
- **Re-check after releases** that change the agent surface, schemas or defaults; the cost notes
  in the catalog came from the 0.20.0 tool comparison and the 0.21.0 exploration rebuild.

## Row template

```markdown
| PRE-NN | What someone wants to make or do | main operations or tools | calls · min | requirements, gaps, links |
```

## Issue provenance

The catalog names releases, not issues. These are the `jxburros/vixl` issues each row's notes cited before the
references were moved here in 0.33.3; look them up for the history of a row. Rows are in catalog order.

| Row | Issues |
| --- | --- |
| DOC-13 | #512 |
| DOC-35 | #284, #300 |
| DOC-36 | #511 |
| DOC-38 | #334 |
| DOC-40 | #712 |
| DOC-37 | #259 |
| TXT-10 | #335 |
| TXT-13 | #603 |
| TXT-14 | #419 |
| TXT-23 | #684, #419 |
| BLK-07 | #213 |
| TXT-17 | #650 |
| TXT-24 | #652 |
| TXT-25 | #652 |
| CLR-13 | #404 |
| CLR-14 | #654 |
| SHP-23 | #382 |
| SHP-17 | #266 |
| SHP-18 | #653 |
| SHP-31 | #653 |
| SHP-32 | #519 |
| SHP-25 | #650 |
| ILL-05 | #258 |
| ILL-60 | #380 |
| ILL-66 | #427 |
| ILL-61 | #379 |
| ILL-62 | #521 |
| DAT-51 | #169 |
| DAT-52 | #169 |
| PRD-53 | #172 |
| PRD-54 | #172 |
| PRD-55 | #444 |
| PRD-56 | #444 |
| DEK-51 | #170 |
| PRN-51 | #444 |
| DRW-31 | #443 |
| DOC-22 | #231 |
| QA-01 | #464, #524, #525 |
| QA-09 | #532 |
| QA-25 | #571 |
| QA-26 | #518 |
| QA-27 | #520 |
| QA-28 | #526 |
| QA-32 | #531, #562 |
| QA-33 | #563 |
| BRD-05 | #527, #528 |
| BRD-56 | #436 |
| BRD-57 | #436 |
| BRD-58 | #436 |
| BRD-59 | #529, #530 |
| AGT-34 | #536 |
| SOC-83 | #368 |
| BRD-54 | #443 |
| DAT-43 | #169 |
| ILL-52 | #380 |
| MOT-09 | #179 |
| MOT-13 | #472 |
| BLK-24 | #381 |
| PRD-60 | #568 |
| PRD-61 | #572 |
| PRD-62 | #578 |
| PRD-64 | #569 |
| AGT-45 | #579 |
| AGT-30 | #537, #543 |
| AGT-46 | #544 |
| AGT-48 | #546 |
| AGT-49 | #547 |
| AGT-47 | #545 |
| QA-47 | #559 |
| QA-48 | #560 |
| PRN-12 | #169 |
| MOT-27 | #510 |
| PRD-22 | #381 |
| QA-37 | #564 |
| QA-45 | #558 |
| QA-46 | #557 |
| PRN-30 | #169 |
| SOC-60 | #210 |
| SOC-62 | #210 |
| BLK-15 | #210, #653, #519 |
| PRD-51 | #565, #576 |
| PRD-63 | #568 |
| BLK-25 | #542 |
| Place native-coordinate path art in a display box | #610 |
| Choose an integration interface | #640 |
| Render final campaign outputs under a severity profile | #563, #701 |

## Ideas not yet placed

Add new ideas here when you are unsure of the tier, then move them into a catalog table.

- Recipe card or cookbook page
- Real-estate listing flyer with a photo grid
- Sports team roster or match-day graphic
- Wedding seating chart
- Restaurant table tent
- Conference schedule (multi-track agenda)
- Floor plan or seating map on a grid
- Periodic-table style grid of tiles
- Calendar page or year planner
- Coupon or gift voucher with a unique code per row
- Book interior pages with running heads
- Map-style illustration with labelled regions
- Infographic for accessibility (color-vision-safe palette)
- Animated emoji or sticker pack
- Tarot or playing-card deck from a CSV
- Album lyric booklet
