# Tool comparison: same model, different tools

The [agent eval suite](../README.md) asks whether an agent can finish a brief *with Vixl*. This kit
asks a different question: **given the same model and the same brief, how does Vixl compare with
the other ways an AI can make the same thing?** Other ways means writing HTML, SVG or Python,
driving free desktop tools, generating images, or using Claude Design.

Every tool here is free or comes with Claude and ChatGPT/Codex. Nothing needs a new sign-up.

| Path | What it is |
| --- | --- |
| [`briefs/`](briefs/) | 16 briefs for the agents, one per test, with exact copy, specs and file names |
| [`TESTS.md`](TESTS.md) | **For you, not the agents:** the lanes for each test, hard checks, round-2 change requests and answer keys |
| [`fixtures/`](fixtures/) | Inputs: CSV data, a sketch photo, LRC lyrics; `make_fixtures.py` adds the song and the photo |
| [`inspect_outputs.py`](inspect_outputs.py) | Measurable facts about any tool's outputs, and blind copies for judging |
| [`scoresheet.csv`](scoresheet.csv) | One row per run |

## Results

- [2026-10-06](../../eval-results/2026-10-06-vixl-0.20-tool-comparison.md): the Vixl lane re-run on
  Vixl 0.20.0 (the current scores in `scoresheet.csv` and `runs/`).
- [2026-10-05](../../eval-results/2026-10-05-full-evaluation.md#2-tool-comparison): the first full
  run, every agent lane, with the Vixl lane on 0.18.0.

## The tests

| # | Makes | What it probes | Compared with |
| --- | --- | --- | --- |
| [T01](briefs/T01-picture.md) | An illustration | Picture-making with shapes and brushes vs an image model; precise edits | SVG, Python, image generation |
| [T02](briefs/T02-social-post.md) | Instagram post | Exact copy, hierarchy, phone legibility | HTML, image generation, Claude Design |
| [T03](briefs/T03-print-poster.md) | 11 × 17 in print poster | Bleed, safe area, CMYK PDF, 300 dpi | Claude Design, HTML print, image generation |
| [T04](briefs/T04-logo-kit.md) | Logo and icon kit | Real vectors, legibility at 16 px, ICO and app icon | Hand-written SVG, Claude Design, image generation |
| [T05](briefs/T05-slide-deck.md) | 6-slide deck | Editable PPTX, speaker notes, a chart | Claude's PowerPoint skill, Google Slides, python-pptx, Claude Design |
| [T06](briefs/T06-fillable-form.md) | Fillable PDF form | Real form fields, flags, options, tab order | reportlab/pypdf, Claude's PDF skill |
| [T07](briefs/T07-batch-badges.md) | 10 name badges from CSV | Variable data, awkward names (accents, CJK), print imposition | Pillow, HTML + Playwright, image generation |
| [T08](briefs/T08-infographic.md) | Data infographic | Correct numbers, bars to scale, data corrections | matplotlib, D3/SVG, Claude Design, image generation |
| [T09](briefs/T09-multi-size-campaign.md) | One campaign in 6 sizes | Adapting a design from 16:9 to 8:1 | HTML, Claude Design, image generation |
| [T10](briefs/T10-photo-edit.md) | Photo correction | Correcting without repainting; crops; caption | ImageMagick/darktable, OpenCV, ChatGPT image editing |
| [T11](briefs/T11-hand-drawing.md) | Sketch to clean art | Tracing, straightening and filling while keeping the drawing | potrace/Inkscape, OpenCV, image editing |
| [T12](briefs/T12-motion-intro.md) | 6 s animated intro | Keyframes, easing, timing, MP4 and GIF | CSS/GSAP + Playwright, Manim, video models |
| [T13](briefs/T13-pixel-sprite.md) | Pixel-art sprite | A real pixel grid, palette limit, sprite sheet | Pillow, image generation |
| [T14](briefs/T14-lyric-video.md) | Lyric video | LRC timing edge cases, audio | ffmpeg subtitles, HTML/canvas, moviepy |
| [T15](briefs/T15-seamless-pattern.md) | Seamless pattern and mug wrap | Repeat geometry, even scatter | SVG/p5.js, NumPy, image generation |
| [T16](briefs/T16-menu.md) | Text-heavy menu | Long exact copy, aligned prices, print | HTML print, Google Docs, Claude Design, image generation |

**Where to start.** If you only have time for a few, run **T01** (picture vs image generation),
**T03** (poster vs Claude Design), **T05**, **T08**, **T10** and **T12**. With three or four
lanes each, and both agents on the code lanes, that is about 40 runs.

## Lanes

A *lane* is a way of making the thing. Each test in `TESTS.md` lists the lanes worth running.

| Code | Lane | Where it runs | Cost |
| --- | --- | --- | --- |
| **V** | Vixl through MCP (or its CLI) | Claude Code, Codex | free |
| **W** | Web code: HTML, CSS, SVG and JS rendered by headless Chromium (Playwright), plus ffmpeg, ImageMagick or Ghostscript | Claude Code, Codex | free |
| **C** | Python code: Pillow, NumPy, matplotlib, cairo, reportlab, pypdf, python-pptx, OpenCV, moviepy, Manim | Claude Code, Codex | free |
| **T** | Free specialist tools from the command line: ImageMagick, Inkscape, GIMP batch, darktable-cli, potrace, ffmpeg | Claude Code, Codex | free |
| **G** | Built-in image (or video) generation | ChatGPT app (same account as Codex); optionally Gemini, free with your Google account | included |
| **X** | Hybrid: generated artwork, with all text, layout and export in Vixl | Codex or Claude Code, plus ChatGPT for the art if the agent can't generate images | included |
| **D** | Claude Design | claude.ai | included with Claude |
| **K** | Claude's built-in file skills (PowerPoint, PDF, Word), or Google Slides and Docs through the Drive connector | claude.ai | included / free |

**What "same model" covers.** Lanes V, W, C and T run in an agent where you choose the model, so
run each one with Claude (Claude Code) and with GPT (Codex) at the same settings. Those runs isolate
the tool. G, D and K are products with their own models: the image model does the drawing in G, and
the Claude app picks the model in D and K. Treat them as baselines for "what you'd get from the
obvious alternative", and record what model they report.

### Lane rules

Paste the rule for the lane into the kickoff prompt (below).

- **V:** Use Vixl for all of the visual work, through its MCP tools (or the `vixl` command line if
  the tools aren't connected). Read `skills/vixl/SKILL.md` first. Don't draw pixels, write SVG or
  HTML, or use an image generator yourself; small scripts are fine only for reading inputs and
  checking outputs.
- **W:** Build it with web code (HTML, CSS, SVG and JavaScript; libraries such as D3, GSAP,
  Chart.js or p5.js are fine) and make the files by rendering in headless Chromium with Playwright or
  Puppeteer. Free command-line tools such as ffmpeg, ImageMagick and Ghostscript are allowed for
  conversion. Don't use Vixl or an image generator.
- **C:** Write code that generates the files with free libraries, such as Pillow, NumPy, matplotlib,
  cairo, reportlab, pypdf, python-pptx, OpenCV, moviepy or Manim; ffmpeg is allowed for encoding.
  Don't use Vixl, a browser or an image generator.
- **T:** Use free desktop tools driven from the command line, such as ImageMagick, Inkscape, GIMP
  in batch mode, darktable-cli, potrace and ffmpeg, with small scripts to glue them. Don't use Vixl
  or an image generator.
- **G:** Use only the built-in image generation and its editing: no code, no other tools, and at most
  four generations per deliverable. Save what it gives you as-is; don't fix sizes or text in
  another app.
- **X:** Generate the artwork, with no text, with an image generator. Then do all text, layout and
  export in Vixl, importing the generated images.
- **D** and **K:** Paste the brief into a new Claude Design project (D) or a new claude.ai chat (K),
  attach any fixture it names, and export the closest formats the product offers. Whatever it can't
  produce counts as missing.

## Setup (once)

1. **Vixl.** The project's `.mcp.json` runs the current released server (v0.22.0) with the repository root
   as the workspace (the briefs use paths from there), the latest recorded results used v0.20.0. To
   test unreleased changes instead, point both agents at the checkout:

   ```bash
   # Claude Code
   claude mcp add vixl-dev -- uvx --from /path/to/Vixl vixl mcp --workspace /path/to/Vixl --tools core --schema slim
   ```

   ```toml
   # Codex: ~/.codex/config.toml
   [mcp_servers.vixl]
   command = "uvx"
   args = ["--from", "/path/to/Vixl", "vixl", "mcp", "--workspace", "/path/to/Vixl", "--tools", "core", "--schema", "slim"]
   ```

   Keep only one Vixl server enabled in Claude Code during runs (`/mcp` lists and disables them).
   MP4 export needs `ffmpeg` on `PATH`.

2. **Tools for the other lanes.** Install them before you start, so install time and failures don't
   count against a lane: `pip install pillow numpy matplotlib reportlab pypdf python-pptx
   opencv-python moviepy`; Node.js with `npx playwright install chromium`; ImageMagick, Inkscape,
   Ghostscript, potrace and ffmpeg (winget, Homebrew or apt).

3. **Fixtures:** `python evals/tool-comparison/fixtures/make_fixtures.py` writes the 32-second song
   and copies the test photo next to the other inputs.

4. **Judging tools:** `pip install pillow pypdf python-pptx`, plus `ffprobe` (part of ffmpeg).

## Running a test

Each run gets its own folder: `runs/<test>/<agent>-<lane>/`, for example `runs/T03/claude-V`,
`runs/T03/codex-W`, `runs/T03/chatgpt-G` and `runs/T03/claude-D`. `runs/` and `blind/` are
git-ignored; delete those lines from `.gitignore` if you want to commit results.

**Round 1 (agent lanes).** Start a fresh session in the repository and send:

```text
This is one run of a tool comparison. Lane: <CODE> — <LANE RULE>

Do the brief in evals/tool-comparison/briefs/<BRIEF FILE>. Save everything in
evals/tool-comparison/runs/<TEST>/<AGENT>-<CODE>/ and finish with REPORT.md there.
Work on your own: don't ask me questions; make reasonable choices and note them in REPORT.md.
Don't open evals/tool-comparison/TESTS.md or other folders under evals/tool-comparison/runs/.
```

**Round 1 (app lanes G, D, K).** Paste the brief's text with the lane rule, attach the fixtures it
names, and download the results into the run folder yourself. Write a short `REPORT.md`: the
number of generations or messages, and anything the app couldn't do.

**Round 2: the revision.** This is the editability test, so run it in a **fresh session** that only
has the files. Take the change request from `TESTS.md`:

```text
This is one run of a tool comparison. Lane: <CODE> — <LANE RULE>

evals/tool-comparison/runs/<TEST>/<AGENT>-<CODE>/ holds finished work and its REPORT.md.
Make these changes: <ROUND 2 TEXT>
Write the updated deliverables to round2/ inside that folder with the same file names, change
nothing outside round2/, and write round2/REPORT.md saying what you changed and how.
```

For G, continue the same chat, because there is no file to reopen. For D, reopen the same project.
Note in the scoresheet that these lanes kept their context; that difference is part of the result.

### Keeping it fair

1. **Same model and settings** for every lane in a pair (`/model` in Claude Code; the model and
   reasoning effort in Codex). Write the exact model in the scoresheet.
2. **A fresh session per run.** No earlier runs in context.
3. **No coaching.** If an agent stops before finishing, send one standard nudge and count it:
   "Check the brief again and finish anything that is missing." Send nothing else.
4. **Time box:** 30 minutes of agent time per round (60 for T12 and T14). Stop it there and judge
   what exists.
5. **Run all lanes of a test close together**, so updates to the apps don't skew one lane.

## Judging

1. **Facts.** `python evals/tool-comparison/inspect_outputs.py evals/tool-comparison/runs/T03` prints
   sizes, color modes, dpi, PDF boxes and color spaces, form fields, PPTX text and notes, video
   length and audio, color counts and tile seams for every run. Tick the hard checks in `TESTS.md`
   from it, then look at the files for the rest.
2. **Blind look.** `... inspect_outputs.py evals/tool-comparison/runs/T03 --blind blind/T03` copies
   each run's deliverables under a random code. Score fidelity and craft from `blind/T03` before you
   open `blind/T03/key.csv`. For a second opinion, give the blind folder, the brief and the rubric
   to the other model, and don't say which tool made what. Some SVGs name their generator in a comment.
3. **Score** each run in `scoresheet.csv`:

| Column | Measures | 1 | 3 | 5 |
| --- | --- | --- | --- | --- |
| `hard_passed` / `hard_total` | The checklist in `TESTS.md` | | | |
| `fidelity` | Everything asked for, exactly | Big parts missing or wrong | A few misses | Everything, exactly |
| `craft` | Composition, type, color: would you publish it? | Broken or amateur | Fine but generic | You'd use it as is |
| `report_honest` | Does REPORT.md match the facts? | `no` | `partly` | `yes` |
| `editability` | How hard round 2 was for a fresh session | Started over or couldn't | Done with rework or drift | Changed in place, nothing else moved |
| `revision` | The round-2 result | Wrong, or broke other things | Right, with collateral changes | All right, nothing else changed |
| `r1_minutes`, `r1_nudges`, `r2_minutes`, `r2_nudges` | Effort | | | |

To compare lanes, take each lane's median scores, its hard-check pass rate and its total minutes,
first per agent and then across both. A lane that scores well with only one agent is telling you
about the agent, not the tool.
