# Tool comparison: blind re-judging · 2026-10-13

Every score in the tool comparison was made again from scratch, so that all of them are current and
were made the same way. Nothing was carried over. This replaces the scores in the
[2026-10-12](2026-10-12-vixl-0.26-evaluation.md), [2026-10-06](2026-10-06-vixl-0.20-tool-comparison.md)
and [2026-10-05](2026-10-05-full-evaluation.md) reports; the runs themselves did not change.

Why it was redone:
- **The non-Vixl scores were stale.** Since 2026-10-05, each re-judging of the Vixl lane told its
  judge to leave the other lanes' scores as recorded. Seven judge notes say a judge disagreed and left
  them anyway. On T04, two later judges scored the web-code lane a point lower than its record.
- **One judge per test.** A craft gap of half a point (median 4 against 4.5) was within what one
  judge's taste can produce.
- **The gallery made some work look worse than it was.** It drew T04's web-code SVGs at their native
  64 px and enlarged them, so they looked blurry next to Vixl's. The gallery is fixed.

The method, packages, prompts, forms and scripts are in
[`evals/tool-comparison/rejudge-2026-10-12/`](../evals/tool-comparison/rejudge-2026-10-12/README.md).

## Summary

- **The craft gap was mostly in the old scores.** Web code's mean craft fell from 4.56 to 3.78 on blind
  re-judging; Vixl's stayed at 3.81. On scores alone, the two are level.
- **Side by side, web code is still preferred more often.** Asked which they would publish, the judges
  picked web code over Vixl in 16 of 27 calls, and web code won 6 of the 9 tests they share. Most
  margins were "slight". The human calibration agreed: web code over Vixl on T03, T08 and T16, and a
  tie on T04.
- **Vixl beats Python** (15 of 27 calls, 5 of 9 tests) and is close to the command-line tools (4 of 9
  calls, 1 of 3 tests).
- **What loses Vixl the comparisons is layout finish**: spacing, rhythm and alignment (T02, T07, T08,
  T15, T16), then flat scenes and generic motifs (T03, T12), then drawing and image finish (T10, T11,
  T13). Spacing and motif are Vixl's lowest craft sub-scores.
- **Fidelity, editability and honesty are strong in every lane.** Vixl passes 92 of 96 hard checks and
  every report is honest.

## Method

1. **Rebuild.** The web-code, Python and command-line lanes commit only their sources, so every run
   was rebuilt from them (notes in `sealed/REBUILD-*.md`). T01's web-code lane can't be rebuilt: its
   `picture.svg` was never committed, so it is not judged.
2. **Blind packages.** [`rejudge.py`](../evals/tool-comparison/rejudge.py) put each test's lanes under
   random codes, stripped producer metadata, and made views that treat every lane the same:
   - vectors drawn at a common size;
   - 1:1 crops of large images;
   - nearest-neighbour enlargements of icons;
   - frame sheets of animations.
3. **Three blind judges per test**, each scoring fidelity, craft (with six sub-scores), revision, a
   defect list and a pairwise "which would you publish?" call, using the
   [rubric](../evals/tool-comparison/JUDGING.md):
   - Judge 1: Claude subagents, one per test.
   - Judges 2 and 3: two outside models, each working through all 16 tests in order from the branch.

   The score of record is the median.
4. **Human calibration.** A person scored T03, T04, T08 and T16 blind on a scoring page. Only the craft
   scores and the publish picks are used: fidelity and revision are checkable facts that the judges and
   hard checks cover.
5. **Not blind.** Hard checks, report honesty and editability need the reports and sources. Four
   agents re-checked every lane from the rebuilt files against the `TESTS.md` answer keys, without
   seeing earlier scores.

## Per lane

Medians, with means in brackets. Craft, fidelity and revision are the blind medians.

| Lane | Runs | Hard checks | All pass | Fidelity | Craft | Revision | Editability | Reports honest |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| **V** Vixl | 16 | 92/96 (96 %) | 12/16 | 5 (4.62) | 4 (3.81) | 4.5 (4.38) | 5 (4.56) | 16 yes |
| **W** web code | 9 | 52/54 (96 %) | 7/9 | 4 (4.33) | 4 (3.78) | 4 (4.11) | 5 (4.67) | 9 yes |
| **C** Python | 9 | 52/53 (98 %) | 8/9 | 5 (4.67) | 4 (3.56) | 5 (4.44) | 5 (4.56) | 7 yes · 2 partly |
| **T** CLI tools | 3 | 14/16 (88 %) | 1/3 | 4 (4.33) | 4 (3.33) | 5 (4.83) | 4 (4.33) | 2 yes · 1 partly |

Old against new mean craft, on the same runs:

| Lane | Old | New |
| --- | ---: | ---: |
| V | 3.81 | 3.81 |
| W | 4.56 | 3.78 |
| C | 3.89 | 3.56 |
| T | 3.67 | 3.33 |

### Which would you publish?

Votes from the three judges, round 1:

| Pair | Votes | Tests won (majority) |
| --- | --- | --- |
| Vixl and web code | web code 16, Vixl 11 | web code 6 (T02, T03, T07, T08, T15, T16), Vixl 3 (T04, T09, T12) |
| Vixl and Python | Vixl 15, Python 12 | Vixl 5, Python 4 |
| Vixl and CLI tools | CLI tools 5, Vixl 4 | CLI tools 2 (T10, T11), Vixl 1 (T14) |
| Python and web code | web code 6, Python 3 | |
| Python and CLI tools | CLI tools 4, Python 2 | |

## Per test

Hard checks, then the blind medians for fidelity, craft and revision, then editability. The craft
column also shows judges 1/2/3.

| Test | Lane | Hard | Fid | Craft (1/2/3) | Rev | Edit |
| --- | --- | ---: | ---: | --- | ---: | ---: |
| T01 picture | V | 6/6 | 5 | 4 (4/4/4) | 3 | 3 |
| | C | 6/6 | 5 | 3 (3/3/4) | 3 | 3 |
| T02 social post | V | 5/5 | 5 | 4 (4/3/4) | 5 | 5 |
| | W | 5/5 | 5 | 4 (4/4/4) | 4 | 4 |
| T03 poster | V | 7/8 | 4 | 4 (3/4/4) | 4 | 5 |
| | W | 7/8 | 4 | 4 (4/4/4) | 3 | 4 |
| T04 logo kit | V | 7/8 | 3 | 4 (3/4/4) | 4 | 4 |
| | W | 7/8 | 3 | 3 (3/3/4) | 4 | 5 |
| T05 deck | V | 7/8 | 4 | 4 (4/3/4) | 5 | 5 |
| | C | 8/8 | 5 | 3 (3/4/3) | 5 | 5 |
| T06 form | V | 7/7 | 5 | 4 (4/4/5) | 4 | 4 |
| | C | 7/7 | 5 | 4 (3/4/4) | 5 | 5 |
| T07 badges | V | 7/7 | 5 | 4 (4/4/5) | 5 | 5 |
| | W | 7/7 | 5 | 4 (4/4/4) | 5 | 5 |
| | C | 7/7 | 5 | 3 (3/3/4) | 5 | 5 |
| T08 infographic | V | 5/5 | 5 | 4 (3/4/4) | 4 | 5 |
| | W | 5/5 | 5 | 5 (4/5/5) | 4 | 5 |
| | C | 5/5 | 5 | 4 (4/4/4) | 4 | 5 |
| T09 six sizes | V | 6/6 | 5 | 4 (4/4/4) | 4 | 4 |
| | W | 6/6 | 5 | 3 (3/3/3) | 4 | 5 |
| T10 photo | V | 6/6 | 4 | 3 (4/3/3) | 5 | 5 |
| | C | 6/6 | 4 | 3 (3/3/3) | 5 | 5 |
| | T | 6/6 | 5 | 4 (4/4/4) | 4.5 | 5 |
| T11 sketch | V | 4/5 | 4 | 3 (3/3/4) | 5 | 5 |
| | C | 4/5 | 4 | 4 (4/5/4) | 5 | 5 |
| | T | 4/5 | 4 | 4 (4/4/4) | 5 | 4 |
| T12 motion | V | 5/5 | 5 | 4 (3/4/4) | 5 | 5 |
| | W | 5/5 | 4 | 4 (4/3/4) | 5 | 5 |
| T13 sprite | V | 5/5 | 5 | 4 (4/4/4) | 5 | 5 |
| | C | 5/5 | 5 | 4 (4/4/5) | 5 | 5 |
| T14 lyric video | V | 5/5 | 5 | 4 (4/4/4) | 4 | 5 |
| | T | 4/5 | 4 | 2 (2/2/2) | 5 | 4 |
| T15 pattern | V | 4/4 | 5 | 3 (3/3/3) | 3 | 3 |
| | W | 4/4 | 4 | 3 (3/3/4) | 3 | 4 |
| | C | 4/4 | 4 | 4 (4/4/5) | 3 | 3 |
| T16 menu | V | 6/6 | 5 | 4 (3/4/4) | 5 | 5 |
| | W | 6/6 | 4 | 4 (4/4/5) | 5 | 5 |

Failed hard checks:
- **Copy in capitals:** T03 (kicker) and T04 (tagline), both lanes each. The briefs give that copy in
  mixed case, and the rubric counts capitals set by styling as different copy.
- **T05 Vixl:** the ★ is a drawn shape, so the deck's text reads "4.8".
- **T11, all three lanes:**
  - Vixl drew new ground-line extensions;
  - Python and the CLI tools left about 1° of the 2° tilt.
- **T14 CLI tools:** the next line stays on screen during the instrumental break.

## What costs Vixl the comparisons

Mean craft sub-scores (medians per run):

| Lane | Hierarchy | Spacing | Type | Colour | Finish | Motif |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| V | 4.38 | 3.78 | 4.08 | 4.25 | 4.06 | 3.67 |
| W | 4.44 | 3.78 | 4.00 | 4.44 | 4.11 | 3.29 |
| C | 4.22 | 3.61 | 3.67 | 4.22 | 4.11 | 3.67 |

The judges' reasons when they picked another lane over Vixl fall into four groups:

1. **Spacing, rhythm and alignment** (T02, T07, T08, T15, T16):
   - a loose lower half on the post;
   - uneven gaps in the badge name block;
   - two left margins, a crowded donut label and a dead band on the infographic;
   - lumpy spread on the pattern;
   - heading rules pressed onto the first menu row, and a ragged price column.
2. **Flat scenes and generic motifs** (T03, T12):
   - dash reflections and a placeholder skyline on the poster;
   - thin line waves and a banded beam in the intro.
3. **Drawing and image finish** (T10, T11, T13):
   - grain left in the Instagram crop;
   - fill halos and blobs where fills meet lines;
   - a flat sprite silhouette.
4. **Data presentation** (T08, T16): names, numbers and percentages not paired in one list, and prices
   not right-aligned.

## How far to trust the judges

- **Agreement.** Only 5 scores had judges 2 or more points apart, all on revision. They were settled
  from the evidence and recorded in `resolutions.json`:
  - four are the judges agreeing on the facts but differing on the penalty for capitals;
  - one was a factual error by judge 3: a crop it said moved measured a 0 px shift.
- **Calibration against the person**, on craft for the 9 runs in T03, T04, T08 and T16:

  | | Craft difference | Sub-score difference | Publish picks agreeing |
  | --- | --- | --- | --- |
  | Judge 1 | 0.78 lower | 0.82 lower | 4 of 6 |
  | Judge 2 | 0.22 lower, 0.44 off | 0.42 lower | 4 of 6 |
  | Judge 3 | no bias, 0.67 off | no bias | 5 of 6 |
  | Median of three | 0.22 lower, 0.44 off | 0.38 lower | |

  The median tracks the person closely. The person scored quickly, so treat this as a coarse check.
- **Judge 3** pushed its forms after the branch already held judge 2's. Its scores show no sign of
  copying:
  - it agreed exactly with judge 2 on 60 % of scores, against 57 % for judges 1 and 2;
  - the longest shared phrase is 65 characters of boilerplate.

## Caveats

- **Fonts.** The rebuilds use current Google Fonts files, which may differ slightly from the 2026-10-05
  downloads; some web-code text margins moved by up to 3 px.
- **T14 CLI tools.** Its star field is generated by unseeded noise, so the rebuild's stars differ.
- **Vixl sources.** Vixl's `.vixl` documents are git-ignored, so its editability was judged from
  reports, operation JSON and round-1/round-2 output diffs, not from the documents.
- **T05 decks** were checked in LibreOffice, not uploaded to Google Slides.
- **T12's round-2 request** asks for a 4.5 s build and a 3 s hold in 8 s. Both lanes stretched the
  build, and neither was penalised.
- **T15 editability** was corrected by measurement. Round-1 ink still in place after round 2:
  - Vixl 7 %, so editability 3;
  - Python 16 %, so 3;
  - web code 34 %, so 4.

## Files

- **`evals/tool-comparison/scoresheet.csv` and `runs/<test>/scores.csv`:** the new record, written by
  `rejudge-2026-10-12/record.py`.
- **`rejudge-2026-10-12/`**, the inputs behind the scores:
  - `analysis.json`, with each code's per-judge scores, every pairwise call and the calibration;
  - the forms in `scores/`;
  - the non-blind checks in `nonblind/`, corrected by `nonblind-resolutions.json`;
  - the key in `sealed/`.
- **[`2026-10-12-gallery.md`](2026-10-12-gallery.md):** now shows these scores and the re-drawn T04
  previews.
