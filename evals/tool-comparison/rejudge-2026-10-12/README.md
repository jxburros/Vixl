# Blind re-judging, 2026-10-12

Every lane of every test, scored again from scratch so that all scores are current. Nothing carries over
from earlier judging. The other lanes were rebuilt from their committed sources; the rebuild notes are
in the sealed archive.

| Path | What it is |
| --- | --- |
| `packages/<test>.zip` | One blind package per test, made by [`../rejudge.py`](../rejudge.py). Each holds the brief, the round-2 request, the judging prompt, a score form, and every lane's deliverables under a random code |
| [`../JUDGING.md`](../JUDGING.md) | The judging prompt and rubric (also inside every zip) |
| [`JUDGE-PROMPT.md`](JUDGE-PROMPT.md) | The prompt for an outside judge that works from this branch |
| `scores/` | Filled score forms, one per judge per test: `<test>.<judge>.json` |
| `sealed.tar.gz.enc` | Encrypted: `key.csv` (code to lane), `excluded.txt`, the rebuild notes and the Claude judge's forms. The owner holds the passphrase; unseal only after every judge and the calibration are done: `openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -in sealed.tar.gz.enc \| tar xz` |

## Protocol

1. **Three judges per test**, each in a fresh session per test, never shown another judge's scores:
   Claude, plus two other models. The median of the three is the score of record.
2. **Disagreement.** Any test where two judges differ by 2 or more on fidelity, craft or revision for
   the same code is flagged for a human look.
3. **Calibration.** A person scores T03, T04, T08 and T16 blind on the
   [calibration page](https://claude.ai/artifact/FEDpj7c1xo9T6Btr61wjbR) (private to its owner), with the same
   rubric. Comparing those scores with the judges' shows how far each judge drifts.
4. **Not blind, done afterwards:** hard checks, report honesty and editability need the reports and
   sources. One judge scores them from `runs/` against the `TESTS.md` answer keys.

## Running another model as a judge

- **A coding agent that can clone the repository** (Codex, Gemini CLI and the like): give it the
  prompt in [`JUDGE-PROMPT.md`](JUDGE-PROMPT.md). It checks out only the packages, judges all 16 tests
  in order and pushes its forms to its own branch.
- **A chat app** (ChatGPT, Gemini): download one zip, start a new chat, attach the zip and paste the
  prompt. If the app can't open zips, unzip it and attach `brief.md`, `round2-request.md`,
  `scores-template.json` and each code's `views/` images (plus `VIEWS.md`), or work through the test
  one code at a time.

Save each returned form as `scores/<test>.<judge>.json`.

T01's web-code lane is not judged: its `picture.svg` was never committed, so it can't be rebuilt.
