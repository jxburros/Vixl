# AI Field Guide packet: reusable workflows

Automation an educator or a comms team can reuse with Vixl 0.23.0 (CLI and Python only). Every folder has a
`build.py` you run from the repository root and a README saying how to adapt it. All of them read the packet
brand in [`brand/brand.json`](brand/brand.json) (palette roles, Lexend + Atkinson Hyperlegible Next).
Field notes, with the bugs and rough edges found on the way, are in [NOTES.md](NOTES.md).

| # | Workflow | Run time | What you get |
| --- | --- | --- | --- |
| 01 | [Term of the day](01-term-of-the-day/) | ~30 s | 12 glossary cards from a CSV, a contact sheet, 4-up print PDF |
| 02 | [One message, many sizes](02-one-message-many-sizes/) | ~1.5 min | one announcement at 6 sizes, adapt vs recompose, checked |
| 03 | [Check-gated pipeline](03-check-gated-pipeline/) | ~25 s | a suite that refuses a bad change, a fix that passes, diffs, a data gate |
| 04 | [Proof page](04-proof-page/) | ~10 s | one offline HTML review page for the whole packet, with approve/reject |
| 05 | [Variety study](05-variety-study/) | ~2 min | 24 rolls: house style 1 vs 2 at low/medium/high, with a verdict |
| 06 | [Throughput and REST](06-throughput-and-rest/) | ~6 min | 100 cards four ways with timings; REST render/compose smoke test |

Order: 01 first (02–06 reuse its template or outputs), 04 last (it gathers everything).

```bash
for n in 01-term-of-the-day 02-one-message-many-sizes 03-check-gated-pipeline 05-variety-study \
         06-throughput-and-rest 04-proof-page; do
  python explorations/11-ai-packet/workflows/$n/build.py
done
```

Outputs are trimmed to keep the folder small (about 9 MB): intermediate PNGs are deleted once a sheet or a
report holds them, and the scripts say so where they do it.
