# Vixl evaluation run · 2026-10-05

Everything in `evals/` that can run in a cloud Claude Code session was run against Vixl 0.18.0:

1. the **agent eval suite** (`evals/tasks`, 18 tasks): reference replay in all four schema/tool modes,
   then a **live agent run**, with Claude itself as the agent;
2. the **tool comparison kit** (`evals/tool-comparison`, 16 briefs): round 1 and the round-2 revision in
   every agent lane that runs here (V Vixl, W web code, C Python, T CLI tools), then blind judging.

**Not run:** the API-driven `--agent claude` mode, because no `ANTHROPIC_API_KEY` is configured; the G, D
and K lanes, which are app products (ChatGPT image generation, Claude Design, claude.ai skills); and
the Codex/GPT half of every pair. Every run here used the same model (Claude Code subagents on
`claude-opus-5-5`), so the comparison isolates the tool, but only for one agent.

## 1. Agent eval suite

### Reference replay (offline, deterministic)

| Schema / tools | Result | Round trips | Tool errors | Tool result tokens/task |
| --- | --- | ---: | ---: | ---: |
| full / all | 18/18 | 3.44 | 0 | ≈359 |
| full / core | 18/18 | 3.44 | 0 | ≈359 |
| slim / all | 18/18 | 3.44 | 0 | ≈359 |
| slim / core | 18/18 | 3.44 | 0 | ≈359 |

The baseline in `evals/baseline.json` passes in every mode, and `tests/test_eval_harness.py` passes
(23 tests).

### Live agent run (Claude as the agent)

The harness's API agent couldn't run, so two Claude subagents did the 18 briefs through this session's
Vixl MCP server (v0.18.0, `--tools core --schema slim`). Each task got a workspace prepared by
`harness.prepare_workspace` under `evals/live-runs/<task>/`, and the result was graded with the
harness's own `grade()` function. The agents never saw the task JSON (checks and reference solutions).

| Task | Result | Vixl calls | Errors | Task | Result | Vixl calls | Errors |
| --- | --- | ---: | ---: | --- | --- | ---: | ---: |
| copy-between-documents | pass | 3 | 0 | restore-deleted | pass | 5 | 0 |
| equal-spacing | pass | 4 | 0 | roll-applied | pass | 5 | 0 |
| fix-layout | pass | 6 | 0 | story-list | pass | 5 | 0 |
| font-pairing | pass | 5 | 0 | svg-logo-import | pass | 4 | 0 |
| form-batch-fill | pass | 6 | 1 | template-creation | pass | 4 | 0 |
| form-registration | pass | 7 | 0 | timeline-motion | pass | 7 | 0 |
| layout-filled | pass | 3 | 0 | variable-variants | pass | 6 | 0 |
| photo-caption | pass | 7 | 0 | workflow-checked-edit | pass | 8 | 0 |
| print-cmyk | pass | 3 | 0 | youtube-thumbnail | pass | 13 | 0 |

**18/18 pass. 101 Vixl calls (5.6 per task, against 3.4 for the scripted reference), 1 tool error (1.0 %).**

Differences from a harness run:
- Paths carried a workspace prefix.
- Several agents shared one MCP server, so every call passed `document=`.
- The font tasks downloaded the real Google fonts instead of using the offline `.font-cache` fixture.
- Token usage isn't available.

Grades are in `evals/live-runs/grades.json`; per-task agent notes are in `agent-log-{a,b}.json`.

Friction the live agents hit:
- **`vixl_workflow` form-fill with `combine: true`** fails with a raw Python error ("unsupported operand
  type(s) for /: 'PosixPath' and 'bool'"). `combine` takes a path, and `vixl_workflow_schema` lists field
  names without types, so the agent had to guess.
- **The `field` operation's properties have no types or descriptions.** The agent built the form from
  `skills/vixl/references/documents.md`.
- **A `text` operation aimed at an existing layer** silently created a new layer named "text" instead
  of resizing the existing one (youtube-thumbnail).
- **The suite object for `workflow` isn't described** by the operation schema (the agent read
  `docs/production.md`).
- **roll-applied** left an empty eyebrow slot that `vixl_check` flagged, so the layout had to be
  re-applied with `unfilled=omit`.

## 2. Tool comparison

38 round-1 runs and 38 round-2 revisions across all 16 briefs, run as fresh Claude Code subagents per
the kit's README:
- **Round 1:** the lane rule and the standard kickoff prompt, with no coaching and no nudges.
- **Round 2:** the TESTS.md change request in a fresh session that only had the files.

Each test was then judged by a separate Claude subagent:
- fidelity and craft scored blind on `inspect_outputs.py --blind` copies, before opening the key;
- hard checks ticked from the inspector facts plus their own measurements;
- report honesty, editability and revision scored against the TESTS.md answer keys.

Judge notes are in `evals/tool-comparison/runs/<T>/JUDGE.md`, and every row is appended to
`evals/tool-comparison/scoresheet.csv`.

### Per-lane summary (medians; minutes are subagent wall time)

| Lane | Runs | Hard checks | Runs passing all | Fidelity | Craft | Honest | Editability | Revision | R1 min | R1 tool calls | R2 min | R2 tool calls |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **V** Vixl | 16 | 89/96 (93 %) | 11/16 | 5 | 4 | 15 yes · 1 partly | 4 | 5 | 8.1 | 54 | 4.5 | 26 |
| **W** web + Chromium | 10 | 59/60 (98 %) | 9/10 | 5 | 4.5 | 10 yes | 5 | 4.5 | 2.3 | 15 | 1.1 | 8 |
| **C** Python libraries | 9 | 52/53 (98 %) | 8/9 | 5 | 4 | 8 yes · 1 partly | 5 | 5 | 2.4 | 14 | 1.0 | 8 |
| **T** CLI tools | 3 | 13/16 (81 %) | 1/3 | 4 | 4 | 2 yes · 1 partly | 5 | 5 | 4.7 | 22 | 1.2 | 9 |

Vixl's wall times are inflated by contention: up to about 15 subagents shared one stdio MCP server, and
several calls hit the client's 60 s timeout even though the edit was saved. Tool-call counts are the
fairer cost measure, and they are also about 3–4× higher for Vixl.

### Per test

| Test | Lane | Hard | Fid | Craft | Honest | Edit | Rev | R1 min / calls | R2 min / calls |
| --- | --- | ---: | ---: | ---: | --- | ---: | ---: | --- | --- |
| T01 picture | V | 6/6 | 4 | 4 | yes | 4 | 3 | 3.6 / 32 | 3.1 / 16 |
| | C | 6/6 | 5 | 4 | yes | 4 | 3 | 1.8 / 8 | 1.6 / 8 |
| | W | 6/6 | 5 | 4 | yes | 5 | 4 | 1.3 / 7 | 1.3 / 8 |
| T02 social post | V | 5/5 | 4 | 4 | yes | 5 | 5 | 2.5 / 29 | 2.5 / 25 |
| | W | 5/5 | 5 | 5 | yes | 5 | 4 | 1.9 / 14 | 1.4 / 13 |
| T03 print poster | V | 6/8 | 5 | 4 | yes | 4 | 5 | 9.8 / 55 | 5.1 / 26 |
| | W | 7/8 | 4 | 5 | yes | 5 | 4 | 6.3 / 18 | 1.5 / 9 |
| T04 logo kit | V | 6/8 | 4 | 4 | yes | 5 | 5 | 18.1 / 169 | 2.4 / 42 |
| | W | 8/8 | 5 | 4 | yes | 5 | 5 | 2.4 / 16 | 1.1 / 8 |
| T05 slide deck | V | 8/8 | 5 | 5 | yes | 4 | 5 | 8.1 / 57 | 7.0 / 37 |
| | C | 8/8 | 5 | 4 | yes | 5 | 5 | 2.9 / 14 | 1.2 / 9 |
| T06 fillable form | V | 7/7 | 4 | 4 | yes | 5 | 5 | 8.2 / 48 | 6.2 / 25 |
| | C | 7/7 | 5 | 4 | yes | 5 | 5 | 2.4 / 14 | 0.8 / 7 |
| T07 badges | V | 6/7 | 5 | 4 | yes | 3 | 5 | 7.3 / 64 | 7.4 / 50 |
| | W | 7/7 | 5 | 5 | yes | 5 | 5 | 2.2 / 12 | 0.9 / 9 |
| | C | 7/7 | 5 | 3 | yes | 5 | 5 | 1.6 / 11 | 0.8 / 8 |
| T08 infographic | V | 5/5 | 5 | 4 | yes | 3 | 5 | 6.8 / 35 | 3.1 / 26 |
| | C | 5/5 | 5 | 4 | yes | 5 | 5 | 2.2 / 18 | 1.0 / 8 |
| | W | 5/5 | 5 | 5 | yes | 5 | 5 | 2.6 / 16 | 1.0 / 7 |
| T09 six sizes | V | 6/6 | 5 | 4 | yes | 5 | 5 | 14.5 / 98 | 2.2 / 56 |
| | W | 6/6 | 5 | 4 | yes | 5 | 4 | 2.3 / 13 | 1.1 / 11 |
| T10 photo edit | V | 6/6 | 4 | 4 | yes | 5 | 5 | 5.4 / 53 | 2.8 / 26 |
| | C | 5/6 | 4 | 3 | partly | 5 | 5 | 2.9 / 21 | 0.8 / 6 |
| | T | 6/6 | 5 | 4 | yes | 5 | 5 | 4.0 / 21 | 0.9 / 8 |
| T11 hand drawing | V | 4/5 | 3 | 3 | partly | 4 | 5 | 10.3 / 64 | 5.4 / 44 |
| | T | 4/5 | 4 | 4 | partly | 5 | 5 | 4.7 / 22 | 1.2 / 11 |
| | C | 5/5 | 4 | 5 | yes | 5 | 5 | 6.4 / 21 | 1.4 / 10 |
| T12 motion intro | V | 5/5 | 5 | 4 | yes | 4 | 5 | 7.6 / 44 | 6.4 / 21 |
| | W | 5/5 | 5 | 4 | yes | 5 | 5 | 3.7 / 17 | 1.9 / 7 |
| T13 pixel sprite | V | 5/5 | 5 | 3 | yes | 4 | 5 | 5.5 / 24 | 5.1 / 22 |
| | C | 5/5 | 5 | 4 | yes | 5 | 5 | 2.5 / 12 | 1.4 / 10 |
| T14 lyric video | V | 5/5 | 5 | 4 | yes | 4 | 4 | 8.8 / 54 | 5.7 / 23 |
| | T | 3/5 | 4 | 3 | yes | 5 | 4 | 19.7 / 22 | 2.5 / 9 |
| T15 pattern | V | 3/4 | 4 | 3 | yes | 4 | 4 | 13.3 / 71 | 3.8 / 45 |
| | W | 4/4 | 4 | 4 | yes | 4 | 3 | 2.2 / 15 | 0.8 / 8 |
| | C | 4/4 | 5 | 4 | yes | 4 | 3 | 1.8 / 9 | 0.9 / 9 |
| T16 menu | V | 6/6 | 5 | 4 | yes | 4 | 5 | 8.1 / 40 | 3.9 / 20 |
| | W | 6/6 | 5 | 5 | yes | 5 | 5 | 1.5 / 8 | 0.7 / 6 |

### What it says

- **Vixl delivers the briefs.** Median fidelity is 5, every round-2 answer key was hit, and it beat
  the CLI lane on T14's hard checks (5/5 against 3/5): it got the lyric-video empty-timestamp clear right, where
  ffmpeg + ASS left the next line up.
- **Vixl is best at stable in-place revision.**
  - T02 changed only the edited rows and produced a real story re-layout.
  - T03 and T09 changed only the text areas.
  - T15 kept 84 % of the pattern's ink, against 40 % for W and 11 % for C, which re-rolled their random
    placement.
  - T04 kept the mark files byte-identical.
- **Vixl costs more and edits less directly when the content is data.** It took 3–4× the tool calls,
  and editability scored 3 in T07 and T08 and 4 in most others, against 5 for the code lanes.
  - **No data binding:** T08 recomputed totals, shares and bar heights outside Vixl.
  - **No merge back to the template:** the T07 print sheet is placed PNGs, so adding a badge meant
    re-importing every image (about 50 calls, against 8–9).
- **Every Vixl hard-check failure traces to a product gap, not to agent error:**
  - **RGBA-only PNG export** failed T03 (preview) and T04 (app icon). In T01 the agent flattened the
    PNG with a script, bending the lane rule.
  - **No TrimBox or BleedBox in PDFs:** T03.
  - **Fixed text boxes don't collapse an empty variable:** T07, Sam Okafor's empty company left a gap.
  - **The organic shell preset ignores stroke colour:** T15, brown outlines outside the palette.
  - **Drawing import treats the desk as ink:** T11, it needed a manual crop. The run also left the
    house corner gap open.
- **Reports were honest across the board** (35 yes, 3 partly). The "partly" cases were misjudgements,
  not false claims:
  - T10 C misread the colour cast as magenta when it was green.
  - T11 V called its line weights uniform; they ranged from 3 to 6 px.
  - T11 T called a residual 0.8° lean the drawing's own slant.

### Vixl issues found (for follow-up)

Export and print:
- **PNG export always writes RGBA**, with no RGB or flatten option. This failed hard checks in T03 and
  T04.
- **CMYK PDF export rasterises everything, including text** ("Vixl won't write vector text into a CMYK
  PDF").
- **PDFs have no TrimBox or BleedBox.**
- **A 0.125 in bleed at 300 dpi is rounded to 38 px**, giving an 810.24 × 1242.24 pt page that the
  agent had to crop.
- **The PPTX export doesn't embed fonts, and the PDF of the same deck is twice the slide size**
  (26.67 × 15 in).
- **A PDF re-export defaulted to raster** (T08 round 2).

MCP surface:
- **`font` is refused inside `vixl_operations_apply` batches.** Agents set fonts per rich-text span or
  through `vixl_text_add`, and `vixl_check` then reports false "bundled fallback font" warnings (T05,
  T16).
- **Operations aimed at an existing layer add a new layer instead of editing it:**
  - `shape` (T08 deleted and re-added 14 layers to recolour them; also seen in T15);
  - `gradient` (T01);
  - `text` (live youtube-thumbnail).
- **`text-set` on a rich-text layer wipes its bullets and letter spacing** (T03 round 2).
- **Resizing with only a height also scaled the width** (T08).
- **A keyframe placed past the end silently lengthens the timeline** (T12).
- **form-fill `combine: true` raises a raw TypeError, and the workflow and `field` schemas have no
  types** (live eval).
- **`vixl_render_preview(values=…)` draws filled single-line values oversized and clipped** (T06).

Missing capabilities agents worked around:
- no chart object or data binding, and no arc or wedge shape (T08 used a 100 % bar);
- no denoise (T10 used blur plus sharpen, and grain remained);
- no negative `scale-x` (T12 built a mirrored pair of beam wedges);
- no path draw-on animation (T12);
- animation order must list every saved frame, so a separate GIF per animation needed a copy of the
  document (T13);
- signature fields can't be required, multiline fields can't take a max length, and fillable PDFs have
  no validation actions (T06);
- the lyric-video build keeps the next line on screen during an empty-timestamp break (T14, fixed by
  hand).

Under about 15 concurrent clients, single calls timed out on the client side after 60 s while the
server still finished the edit (T03, T07, T09, T12, T13, T15).

## Files

- `evals/live-runs/`: live-agent workspaces, `grades.json` (harness grading) and the agent logs.
- `evals/tool-comparison/runs/<T>/`: each run's `REPORT.md` and editable sources, plus `round2/`,
  and per test a `JUDGE.md` and `scores.csv`. Binary deliverables (about 180 MB) are not committed;
  regenerate them from the sources.
- `evals/tool-comparison/scoresheet.csv`: one row per lane per test.
