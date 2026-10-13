# Judging prompt: blind tool comparison

Paste everything below the line into a fresh session of the judging model. Give it the package for one
test (the `package/<test>/` folder, or a zip of it); with a coding agent that can read the repository,
point it at the folder instead. Use a fresh session per test, and never show a judge another judge's scores.

---

You are judging a blind design comparison. Several tools made the same brief. Each tool's work is in a
folder named with a random four-letter code. You don't know which tool made which, so don't try to
guess: judge only what is on the page.

## What's in the folder

- `brief.md`: what was asked for in round 1.
- `round2-request.md`: the change request each tool got in round 2.
- `<CODE>/r1/` and `<CODE>/r2/` for each code. Each has:
  - `views/`: the images to judge from. `VIEWS.md` says what each one is. Vector files are drawn at a
    common size, so they are sharp. Large images come as an `overview` plus 1:1 `crop` files, which show
    the real pixels. Images 128 px or smaller also come `enlarged … nearest`, with hard pixels on purpose.
    Animations come as `frames` sheets with timestamps.
  - `files/`: the actual deliverables, if you can open them (PDF, SVG, MP4, GIF, PPTX).
  - `facts.json`: measured facts: pixel sizes, pages, frames, durations, fonts, form fields.
- `scores-template.json`: the form to fill in.

Not in the folder, on purpose: each tool's REPORT.md, its editable source files, and input files such as
CSVs, the raw photo or the lyrics. Reports, sources and editability are judged separately, so don't
take fidelity off for their absence; judge the deliverables that are here. Where a check needs an input
you don't have, check what you can (internal consistency, timing you can measure) and say what you
couldn't verify.

## How to judge

1. Read `brief.md` and `round2-request.md`.
2. For each code, look at every round-1 view. Open the crops: blur, soft edges, halos, jaggies,
   clipping, collisions and misalignment only show at real size. The overview alone is not enough.
3. Score each code on its own (see the rubric below), and list concrete defects as you find them.
4. Then compare the codes in pairs (`pairwise_round1`).
5. Then look at round 2 next to round 1 for each code, and score `revision`.
6. Fill in `scores-template.json` and return it. Name the file `<test>.<judge id>.json` and put the same
   id in `"judge"`. Use the judge id your instructions give you; if they give none, use your model name.

## Rubric

Every score is a whole number from 1 to 5. Use the full range. A 5 is not the default for "nothing wrong",
and a 3 is not an insult.

**`fidelity`: everything asked for, exactly.**
- 5: every deliverable, size, format, line of copy and spec, exactly as asked.
- 3: a few misses: one wrong line of copy, a missing file, a spec not met.
- 1: big parts missing or wrong.

Check copy character by character (accents, en dashes, middle dots, capitals). Text set in capitals by
styling still counts as different copy if the brief gave it in mixed case. List every miss in
`fidelity_misses`. Missing files cost fidelity.

**`craft`: would you publish it as is?** This is your overall verdict, not an average of the sub-scores.
- 5: a professional designer would ship it unchanged.
- 4: good; a designer would fix one or two things.
- 3: fine but generic, or several things need fixing.
- 2: visibly amateur, or parts are broken.
- 1: broken.

**`craft_sub`: what drives the craft score.** Score each from 1 to 5, or `null` where it doesn't apply.
- `hierarchy`: the most important thing reads first and the reading order is clear.
- `spacing`: margins, alignment and rhythm are consistent; space is distributed, with no dead bands and no
  crowding.
- `type`: typefaces suit the job and pair well; sizes, weights, tracking and line breaks are considered;
  everything is legible at its intended size.
- `colour`: the palette is used with intent, contrast works, and accents are used with restraint.
- `finish`: the execution is clean at real size: sharp edges, no blur, halos, banding, jaggies, clipping or
  stray marks, and small refinements are present.
- `motif`: imagery and illustration are specific to this subject and well drawn, not a generic stand-in.
  Use `null` when the piece has no imagery by design (a text-only form, for example).

More decoration is not more craft. Judge whether each element earns its place.

**`defects`: concrete problems.** One entry per problem, as
`{"where": "<file and region>", "what": "<the problem>", "severity": "minor" | "major" | "broken"}`.
Use this for anything you'd point at on a printout. Name the view or crop where you saw it.

**`revision`: the round-2 result, judged against `round2-request.md`.**
- 5: every requested change is made, and nothing else changed.
- 3: right, but with collateral changes (things moved or changed that weren't asked for), or one request
  missed.
- 1: wrong, or other things broke. If `r2/` is empty, score 1 and say so.

Compare r1 and r2 views side by side for drift. Put what you saw in `revision_notes`.

**`pairwise_round1`: which would you publish?** For each pair, using round 1 only:
- `publish`: `"a"`, `"b"` or `"tie"`;
- `margin`: `"slight"`, `"clear"` or `"decisive"`;
- `why`: one sentence naming the deciding difference.

## Rules

- Judge only what the files show. Don't guess the tool, and don't reward a guess about how hard it was
  to make.
- Look at the codes in a different order from the one they're listed in, so the first one you see
  doesn't anchor you.
- If a view looks blurry, check the crop or file before blaming the work. `VIEWS.md` says whether an
  image was reduced, and only `nearest` views are enlarged.
- Return only the filled JSON, then at most five lines on anything that made judging hard.
