# Throughput (100 cards) and REST

Times four ways of making 100 term cards from workflow 01's template (4-core container):

| Path | Per card |
| --- | --- |
| `vixl render --data` with the per-row check (default) | 818 ms |
| `vixl render --data --no-check` | 276 ms |
| `vixl workflow run`, reflow action + suite, 1 / 4 workers | 1267 / 686 ms |
| Python: `Project.load` once, `render(variables=row)` in a loop | 211 ms |

Exact numbers are in `output/timings.json`. Pick by need: the Python loop for speed when the copy is known to
fit, `render --data` for a checked merge, the production run when text must reflow and every card must pass
the suite.

The REST part starts `vixl -p card.vixl serve`, then calls `POST /check`, `POST /render` with variables
(0.25 s, a ready "card of the day" endpoint), `POST /compose` (a dry run: a whole linkedin-post with layout,
check and preview in 0.36 s, nothing saved) and `POST /preview`. Results in `output/rest.json`, images in
`output/rest-render.png` and `output/rest-compose-preview.png`.
