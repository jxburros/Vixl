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

- **expected**: the composition matters (dead band, margin drift, uneven rhythm, crowding, clumped scatter; no judged
  defect of a reconstructed document is a hierarchy one, so the four hierarchy codes have none), each
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
| dead_band | 10 | 5 | 5 | 6 | 0 | 1 |
| margin_drift | 5 | 4 | 1 | 10 | 0 | 1 |
| uneven_rhythm | 4 | 2 | 2 | 3 | 0 | 1 |
| crowding | 1 | 1 | 0 | 4 | 0 | 0 |
| clumped_scatter | 1 | 0 | 1 | 0 | 0 | 0 |
| flat_hierarchy | 0 | 0 | 0 | 0 | 0 | 0 |
| single_weight | 0 | 0 | 0 | 0 | 0 | 0 |
| no_focal | 0 | 0 | 0 | 0 | 0 | 0 |
| accent_unused | 0 | 0 | 0 | 0 | 0 | 0 |
| all | 21 | 12 | 9 | 23 | 0 | 3 |

Findings exceed catches because one defect is often found more than once (the four section rules of the T16 menu,
every caption of the T04 sheet). The three findings on other judged defects are the empty top band of the T14 lyric
frame, the T03 subtitle floating midway between the title and the date (the judges' "the list floats"), and the
indented `$1.00` of the T16 price column (their "ragged price column"). Layers under 30% opacity are not blocks, so
the faint ripple that touched the T03 credit no longer counts as a crowded rule.

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

The four hierarchy codes (`flat_hierarchy`, `single_weight`, `no_focal`, `accent_unused`) were gated on this set the
same way: a code lands only with no false finding. None fires on the 20 documents, so none is false, but the backtest
cannot say what they catch, for two reasons. No judged defect of a reconstructed document is a flat scale, a single
weight, a missing focal point or an unused accent (the nearest, the T05 chart whose labels are as large as its data, is
on slide 3, which is not among the reconstructions), so there is no expected defect to catch. And the reconstructions are set in the bundled proofing font and carry no rolled direction,
so `single_weight` (which does not judge the proofing font) and `accent_unused` (which needs a direction with an
accent) cannot fire here at all. What the set does show is headroom: the closest `flat_hierarchy` call is the T14 lyric
frame at 2.13 times the body size against a limit of 1.6; no page has its two heaviest blocks within 15% of each
other with a lighter third (the nearest, the T12 name and tagline, weigh 72% of each other, and two blocks alone are
not judged); the T04 logo sheet, the T07 print sheet and the T05 bullets are series of equals, which the code leaves
alone. Their positive and negative cases are in `tests/test_composition_hierarchy.py`, and the pairs in the skill's
`finishing-pairs.md` are applied and checked by `tests/test_finishing_pairs.py`.

The thresholds were also run on the 144 rolled designs of `python -m evals.house_style` (48 sparse briefs at three
variety levels): none gets a composition finding. That includes the four hierarchy codes: the eval's stand-in fonts are one file under
every name, which `single_weight` cannot tell apart, so the designs were rolled a second time with different stand-in
faces for the heading and the body (Noto Sans and DejaVu Sans): still none.

## Repair

`python -m evals.craft_backtest --repair` runs workflow `repair-layout` (craft plan 2b) on every document with
composition findings, with the default checks and up to 20 iterations, and counts the findings its plan resolves
while adding no fix or review finding of any check. The reconstructions keep text in the safe-area margin where the
originals set it, a failure repair cannot fix, so the plan is never committed on its own; the run applies the
composition repairs it selected and checks again.

| Kind | findings | resolved |
|---|---:|---:|
| dead_band | 6 | 3 |
| margin_drift | 10 | 10 |
| uneven_rhythm | 3 | 1 |
| crowding | 4 | 4 |
| clumped_scatter | 0 | 0 |
| flat_hierarchy, single_weight, no_focal, accent_unused | 0 | 0 |
| all | 23 | 18 |

16 of the 20 findings that catch a judged defect are resolved, with no new finding. Left over: the T02 band beside
the microphone (the drawing spans the band, and moving the blocks below it would run them into its base), the band in
the T04 logo sheet's dark half, and the name blocks of T07 badges 01 and 03: pulling the last name up to the first
leaves the company line floating midway
between the name and the role bar (a floating block is an `uneven_rhythm` finding since the craft-check backtest),
and closing up the whole stack opens a dead band above the bar.
`tests/test_craft_backtest.py` pins these numbers too.
