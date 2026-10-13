# Brand voice

[Documentation home](README.md) · [Marketing pack](https://github.com/jxburros/VixlExamples/blob/main/marketing/README.md) · [House style decisions](house-style.md)

How Vixl talks about itself: the README, the marketing pack, release posts, plugin listings and the opening lines
of docs. This guide covers Vixl's own copy only. It does not set the look of what Vixl makes; for output
defaults see [house style](house-style.md).

## The line

**Ideas become editable.**
Vixl is a design engine for AI agents. Programmable, editable, checked.

Use "design engine for AI agents" as the one descriptor. Retired descriptors: "programmable design studio",
"image-document engine" and "headless application designed for autonomous AI agents".

## Three pillars

| Pillar | The question it answers | Proof to point at |
| --- | --- | --- |
| **Programmable** | Can my agent drive it? | One operation format across MCP, CLI, Python and REST; atomic batches of up to 10,000 operations; headless |
| **Editable** | Can I still change it? | Text stays text; layered `.vixl` masters with branching history; real PowerPoint charts; fillable PDFs; Git-reviewable source folders |
| **Checked** | Can I trust it? | Design checks, saved suites, preview before export, CMYK with trim and bleed, golden-image tests |

Lead with the pillar the reader cares about:

- developer docs, the skill and interface pages lead with **Programmable**;
- the README, social posts, carousel and landing copy lead with **Editable**;
- print, production and form docs and release notes lead with **Checked**.

## Voice

Talk like a sharp designer friend, not a press release: contractions, short sentences, the occasional aside.

- **Get the fun from specifics.** "A PPTX that opens in PowerPoint on Monday" beats any adjective.
- **Name the file people get back.** "A PDF people can fill in", not "flexible export options".
- **Let numbers do the bragging.** "10,000 operations, one undo."
- **Tease the problem, not other products.** "A picture of a poster" is fine; naming competitors isn't.
- **One wink per section, at most.** After the first paragraph, reference docs stay plain and exact.
- **Stay honest.** Keep the caveats: illustrative data is labelled, PSD is layered pixels, AI features need
  configured providers, and the licence is source-available, never "open source".

Words we don't use as praise: magic, seamless, revolutionary, AI-powered, unleash, supercharge, game-changer,
delightful. Technical terms are fine where they are exact, such as a seamless loop or tile.

## Examples

| Instead of | Write |
| --- | --- |
| A programmable design studio for AI agents. | A design engine for AI agents. You keep the layers. |
| Edit the data. Keep the chart. | New numbers? Same chart. |
| Make requirements measurable. | Write the brief as tests. |
| Create graphics, documents and motion. Keep working. | Your agent makes the poster. You keep the layers. Nobody redraws it from scratch. |
| Ready to share | Done. Layers kept. |

## Where the copy lives

- `README.md` hero, `pyproject.toml` description and the CLI help header (`src/vixl/cli.py`).
- Plugin listings: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` and the desktop extension
  manifest in `distribution/package_extensions.py`.
- The marketing pack in [VixlExamples](https://github.com/jxburros/VixlExamples): `marketing/copy.json` (captions, descriptions, demo
  script), `marketing/posts.csv` (campaign rows) and the artwork text in `marketing/build.py`. Rebuild with
  `python marketing/build.py` and check with `python marketing/verify.py`.
- The promo video's on-screen text in `promo/build/scenes.py` (also in VixlExamples). Rebuild with
  `python promo/build/make_video.py`.
- The one-line introduction at the top of docs pages, `skills/vixl/SKILL.md` and its references.
