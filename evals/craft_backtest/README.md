# Craft backtest

Does the `composition` check family find what the judges saw? This set answers it for the round-1 Vixl documents
of the [tool comparison](../tool-comparison/README.md), with the defects named in the blind re-judging
(`rejudge-2026-10-12/scores/T??.{1,2,3,human}.json` in the VixlExamples repository; the Vixl lane's blind code per
test comes from `sealed/key.csv`).

```bash
python -m evals.craft_backtest          # table: per kind, expected defects caught, missed, and false findings
python -m evals.craft_backtest --json   # the same, with every finding and defect
```

`tests/test_craft_backtest.py` runs it and pins the numbers: a change that catches fewer defects or adds a false
finding fails there. Craft plan rule: a new check lands with these numbers in the changelog.

## These are reconstructions, not the originals

The round-1 `.vixl` sources were never committed (craft plan item 1a keeps them from now on). Each document here is
rebuilt from the best evidence published for its run in `evals/tool-comparison/runs/T??/claude-V/` of the
VixlExamples repository: the run's own operation batches where they were kept, otherwise layers placed by hand at
the ink positions measured in the exported PNG or PDF (`runs.py`-style row and column scans), with the sizes and
choices the run's `REPORT.md` states. What they keep is the layout: where the blocks sit, their sizes, alignment
and gaps. What they drop is drawing detail (a microphone is a capsule, a stand and a base; a logo mark is a disc;
a photograph is a gradient). Text is set in the bundled proofing font, so line lengths differ a little from the
originals; positions of the left edges and tops follow the originals.

| Test | Document(s) | How it was made |
| --- | --- | --- |
| T01 picture | `T01-picture` | By hand from `picture.png`: sky, sea, headland, lighthouse, beam, boats, stars, waves |
| T02 social post | `T02-post` | By hand from `post.png` and the report's sizes |
| T03 print poster | `T03-poster` | The run's `scene-ops.json` and `reflection-ops.json` (in `ops/`), plus the text placed from `poster-preview.png` |
| T04 logo sheet | `T04-logo-sheet` | By hand from `logo-sheet.png`; marks drawn as discs |
| T05 slide deck | `T05-slide-4` | By hand from `deck.pdf` page 4 and the report (the run's batches need the masters `deck-from-markdown` made) |
| T06 fillable form | `T06-form` | The run's `build-ops.json` (in `ops/`); its two follow-up batches were not kept, and the render matches `signup-form.pdf` |
| T07 name badges | `T07-badge-01`, `-03`, `-04`, `-06`, `T07-print-page-2` | By hand from the badge PNGs and `badges-print.pdf` page 2 |
| T08 infographic | `T08-infographic` | The run's `build-ops.json` (in `ops/`) with the later edits its report lists; today's chart engine sets the chart titles at x 76 instead of 88 |
| T09 campaign | `T09-story` | By hand from `instagram-story.png` (the size the composition note names) |
| T10 photo edit | `T10-caption` | By hand from `coast-caption.png`; the photo is a full-canvas background |
| T11 sketch to vector | `T11-sketch` | By hand from `sketch-color.png` |
| T12 logo intro | `T12-last-frame` | By hand from `intro-last-frame.png` |
| T13 sprite sheet | `T13-sprite-sheet` | By hand from `keeper-sheet.png` |
| T14 lyric video | `T14-chorus-frame` | By hand from the frame at 10 s of `lighthouse.mp4` and the report's template |
| T15 pattern tile | `T15-tile` | Every copy of the two `pattern-scatter` groups at the place, size and rotation `tile.svg` gives (`ops/T15-tile-placements.json`), drawn as rounded boxes, with the recipe the report gives |
| T16 menu | `T16-menu` | By hand from `menu-preview.png` |

## The manifest

`manifest.json` lists, per test, every defect a judge named for the Vixl lane:

- **expected**: the composition matters (dead band, margin drift, uneven rhythm, crowding, clumped scatter), each
  with the codes that count as catching it, the document and the region in its pixels, the judges who named it
  and their words;
- **out_of_scope**: everything else (drawing, motif, type, colour, data presentation, print, export), with a
  region where it has one.

A finding catches a defect when its code is one of the defect's and its region meets the defect's. A finding that
meets no expected defect but lands on an out-of-scope one is counted apart ("on other judged defects": real, but
not a composition catch); any other finding is false. Judgement calls are written into the defect's text: for
example the T03 list the judge saw "slightly left of the centred axis" is centred within 1 px in the PNG, and is
kept as an expected (and missed) defect because a judge named it.

## Numbers

At the thresholds in `src/vixl/composition.py`:

| Kind | expected | caught | missed | findings | false | on other judged defects |
|---|---:|---:|---:|---:|---:|---:|
| dead_band | 10 | 5 | 5 | 5 | 0 | 0 |
| margin_drift | 5 | 4 | 1 | 10 | 0 | 1 |
| uneven_rhythm | 4 | 2 | 2 | 2 | 0 | 0 |
| crowding | 1 | 1 | 0 | 5 | 0 | 1 |
| clumped_scatter | 1 | 0 | 1 | 0 | 0 | 0 |
| all | 21 | 12 | 9 | 22 | 0 | 2 |

Findings exceed catches because one defect is often found more than once (the four section rules of the T16 menu,
every caption of the T04 sheet). The two findings on other judged defects are a ripple line touching the T03 credit
(the judges' "ripples run through the list") and the indented `$1.00` of the T16 price column (their "ragged price
column").

What it misses, and why:

- **Bands that thin lines or a lone line fill**: the T12 bottom third holds three thin wave strokes, the T02 band
  above the waves is closed by marked decoration, the T08 band has the footnote on its rows, and faint water ripples
  cross the T03 bottom band. The bands are measured on boxes, so sparse ink still counts as filled.
- **Asymmetric space around a block**: T07 badge 06 has 100 px above the name and 141 px below; no band is out of
  scale with the badge's gaps.
- **One badge of the set** (T07 badge 04): the gap between the long first and last names is within the scale.
- **Clumped scatter** (T15): the tile's motif coverage is as even as a fresh `pattern-scatter` (coefficient of
  variation 0.47 against 0.19-0.49 for 60 seeded tiles of the same motifs); what the judges saw is three like motifs
  lined up in one column, which density does not measure.

The thresholds were also run on the 144 rolled designs of `python -m evals.house_style` (48 sparse briefs at three
variety levels): none gets a composition finding.

## Repair

`python -m evals.craft_backtest --repair` runs workflow `repair-layout` (craft plan 2b) on every document with
composition findings, with the default checks and up to 20 iterations, and counts the findings its plan resolves
while adding no fix or review finding of any check. The reconstructions keep text in the safe-area margin where the
originals set it, a failure repair cannot fix, so the plan is never committed on its own; the run applies the
composition repairs it selected and checks again.

| Kind | findings | resolved |
|---|---:|---:|
| dead_band | 5 | 3 |
| margin_drift | 10 | 9 |
| uneven_rhythm | 2 | 2 |
| crowding | 5 | 5 |
| clumped_scatter | 0 | 0 |
| all | 22 | 19 |

17 of the 20 findings that catch a judged defect are resolved, with no new finding. Left over: the T02 band beside
the microphone (the drawing spans the band, and moving the blocks below it would run them into its base), the band in
the T04 logo sheet's dark half, and the T08 chart titles, which would leave the safe area to meet the margin.
`tests/test_craft_backtest.py` pins these numbers too.
