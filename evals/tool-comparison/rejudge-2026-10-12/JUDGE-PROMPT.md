# Prompt for an outside judge

Give everything below the line to a coding agent that can clone GitHub repositories (Codex, Gemini CLI,
Jules and the like). Replace `<JUDGE_ID>` with a short name for this judge, such as `gpt` or `gemini`.

---

You are an independent judge in a blind design comparison. Several tools made the same 16 design briefs.
Your job is to score their work. Everything you need is in one GitHub branch.

Repository: https://github.com/jxburros/Vixl
Branch: `claude/tender-dijkstra-q6va0n`
Your judge id: `<JUDGE_ID>`

## 1. Get only the judging files

Check out just these two paths, so nothing else in the repository is in front of you:

```bash
git clone --filter=blob:none --no-checkout --branch claude/tender-dijkstra-q6va0n \
  https://github.com/jxburros/Vixl.git vixl-judge
cd vixl-judge
git sparse-checkout set --no-cone /evals/tool-comparison/JUDGING.md /evals/tool-comparison/rejudge-2026-10-12/packages/ /evals/tool-comparison/rejudge-2026-10-12/scores/
git checkout
```

You need Python with Pillow (and pypdf, python-pptx if available) and ffmpeg for the video tests.

## 2. Rules

- Read nothing else in the repository: no other folders, no git history, no other branches, and don't
  try to open `sealed.tar.gz.enc`. They hold earlier scores and the answer key, and seeing them spoils
  the test.
- Judge only what's in each package. The entries are under random codes, so don't try to work out
  which tool made which.
- Judge the 16 tests one at a time, T01 to T16. Finish and save one test's form before opening the next
  zip, and don't revise earlier forms after you've seen later tests.

## 3. For each test

1. Unzip `evals/tool-comparison/rejudge-2026-10-12/packages/<test>.zip` into a scratch folder outside the
   repository.
2. Read `JUDGING.md` in the unzipped folder. Everything under its line is your rubric and procedure;
   follow it exactly. In short:
   - score fidelity, craft (with its six sub-scores), defects and revision for every code;
   - make a pairwise "which would you publish?" call for every pair;
   - look at every round-1 view, including all crops, at real size. Blur, halos, clipping and
     misalignment only show there.
3. Fill in that test's `scores-template.json`, with `"judge": "<JUDGE_ID>"`.
4. Save it as `evals/tool-comparison/rejudge-2026-10-12/scores/<test>.<JUDGE_ID>.json` and check it parses
   as JSON.

## 4. When all 16 are done

- If you can push to the repository, commit the 16 files on a new branch named
  `rejudge-scores-<JUDGE_ID>` and push it. Use a plain commit message such as "Add blind judge scores"
  with no model names, signatures or co-author trailers.
- If you can't push, print all 16 JSON forms in your final answer, one after another, each under a line
  with its file name.

Finish with at most ten lines on anything that made judging hard: a view that wouldn't open, a brief
that seemed contradictory, a file you couldn't read.
