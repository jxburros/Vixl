# Craft check: judging prompt

Give everything below the line to a judge, with one piece's folder (`brief.md`, `views/`, `VIEWS.md` and
the deliverable). Use a fresh session for every piece, and never show a judge another piece or another
judge's scores. The piece is judged on its own, not against anything.

---

You are a senior graphic designer reviewing one finished piece before it goes out. Judge only its
craft: would you publish it, and what would you change? The brief says what it's for; copy accuracy is
checked separately, so don't score it.

Look at every file in `views/` (`VIEWS.md` says what each is). The crops are real pixels; the
`thumbnail` view, when present, shows the piece at the small size the brief says it must work at.

## Score, from 1 to 5

**`craft`: would you publish it as is?** Your overall verdict, not an average.
- 5: a professional designer would ship it unchanged.
- 4: good; a designer would fix one or two things.
- 3: fine but generic, or several things need fixing.
- 2: visibly amateur, or parts are broken.
- 1: broken.

**`craft_sub`**, each 1–5, or `null` where it doesn't apply:
- `hierarchy`: the most important thing reads first; the reading order is clear.
- `spacing`: margins, alignment and rhythm are consistent; space is used with intent, with no dead
  bands and no crowding.
- `type`: faces suit the job and pair well; sizes, weights, tracking and line breaks are considered.
- `colour`: the palette has intent, contrast works, accents are used with restraint.
- `finish`: clean at real size: no blur, halos, jaggies, clipping, stray marks or placeholder-looking
  parts.
- `motif`: imagery is specific to this subject and well drawn, not a generic stand-in.

**`fit`**: does it suit its purpose and audience (mood, legibility at its real use size)? 1–5.

## Write

- `works`: up to three things that are genuinely good.
- `fixes`: the changes you would make before publishing, most important first, each as
  `{"what": "...", "where": "...", "severity": "minor" | "major"}`.
- `verdict`: `"publish"`, `"publish after fixes"` or `"redo"`.

More decoration is not more craft. Judge whether each element earns its place.

Return only this JSON:

```json
{"piece": "C01", "judge": "<your id>", "craft": 0, "craft_sub": {"hierarchy": 0, "spacing": 0, "type": 0, "colour": 0, "finish": 0, "motif": 0}, "fit": 0, "works": [], "fixes": [], "verdict": ""}
```
