# A check-suite-gated pipeline

![v1 vs v3](output/diff-v1-v3.png)

The card template from workflow 01, guarded by its `card` suite, replaying a realistic change request:

1. **v1** passes the gate (`vixl check` without `fix` findings + `vixl workflow check` on the suite).
2. A teammate asks for a teal "TRY IT", a smaller definition and a bigger graphic. Sent through
   `vixl workflow act` (apply to a candidate, run suites, commit only on a clean pass), it is **refused**:
   4.14:1 contrast, definition smaller than the activity text, graphic overlapping the text
   (`output/act-v2.json`). `v2-rejected.png` shows what was refused.
3. A fix with the same intent (white "TRY IT" on a teal chip, graphic scaled and placed clear) is tried:
   the first placement is itself refused (2.4 px from the panel edge, the suite asks 16), the second commits.
4. `vixl diff v1.vixl v3.vixl --mode side-by-side --max-fraction 0.05` keeps the change small and local.
5. Data gate: a new CSV row with a 290-character definition fails `render --data`'s per-row check; the
   shortened row passes.

`build.py` exits non-zero if the final state fails any gate, so it can run in CI as is. `pipeline-log.json`
is the audit trail.

## Reuse it
Put your requirements in the suite (`SUITE` in workflow 01, attached with `suite-set`), send every change
through `vixl workflow act --request` (`{"operations": [...], "suites": ["card"]}`), and gate on
`committed`, not on re-checking the file afterwards (a refused change leaves the old, passing document).
`--max-fraction` measures how much changed, not whether it is good; keep it next to the suite.
For GitHub, the repository's action does the check + diff + proof part on pull requests (docs/ci.md).
