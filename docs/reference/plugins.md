# Plugins

Vixl splits its optional features into **built-in plugins**: packages under `src/vixl/plugins/` that join the
core through one registry (`vixl.plugins`). They all ship with Vixl and are always on. The split keeps the
core small and lets a plugin move out of the package later without changing the core.

Four kinds of extension use the word "plugin" or "pack". They are different things:

| Name | What it is | Where it lives |
| --- | --- | --- |
| Built-in plugin | An optional feature package, such as charts, lyric videos or Figma import | `src/vixl/plugins/<name>/` |
| Python extension | Third-party trusted code loaded from entry points with `vixl --plugins` (filters, providers, operations) | Installed Python packages; see [interfaces](interfaces.md#trusted-extensions) |
| Resource pack | A declarative pack of saved shapes, suites, styles and templates (`plugin-install`) | The workspace resource library; see [studio](../guides/automation/studio.md) |
| Content pack | Large data Vixl downloads on first use, such as the emoji artwork | The [VixlPacks](https://github.com/jxburros/VixlPacks) repository |

## Is a new feature a plugin?

Check these parameters **before** adding a feature, and say which way it went in the pull request.

### It stays in the core if any of these is true

1. **The document model, renderer or an exporter must know about it** to draw or save a document correctly: a
   new layer type, render path, blend, effect or fill rule. (A feature that writes ordinary layers does not
   count.)
2. **Other core modules need it.** It is a shared helper: geometry, color, text, assets, checks infrastructure.
3. **It changes what every document gets**: a default, a normalization, a house-style rule, or a check that
   runs for every document.
4. **It is part of the working loop every agent uses**: create, apply, check, render, export, `vixl_reference`.

### Otherwise it is a plugin if most of these are true

1. **Self-contained.** Its code fits in one package, and the core reaches it only through the registry roles
   and hooks below. The plugin may import the core freely. The core does not import the plugin.
2. **Ordinary output.** A document it made still opens, renders and exports without it: it writes standard
   layers, and any data of its own sits in its own keys, which the core keeps unchanged.
3. **A particular audience or domain**: lyric videos, comics, Figma import, print imposition. Not general
   design.
4. **Its own heavy or optional dependency**: an external tool (ffmpeg), an optional package (pypdfium2), network
   access or a model provider.

### Large data is a content pack

Data over about 1 MB that only some features use (artwork, sample libraries, large catalogs) goes to
VixlPacks and is downloaded on first use through `vixl.packs`. The pack is pinned to a commit
and checked by SHA-256. Small indexes that the core needs to answer queries offline, such as the emoji
catalog, stay in `src/vixl/data/`. The built-in packs are `emojis` (the artwork) and `fonts` (third-party fonts the
examples use, named like the font cache); the fallback fonts that make text render offline ship in the package.

`cjk` has a seam but no published pack yet. Text whose CJK, Devanagari or Thai characters no document font covers
draws them from a face already on the machine: `vixl.packs.local("cjk")` (the `VIXL_CJK_PACK` override: a font
file, or a zip of files named like the font cache, `noto-sans-sc-400.ttf`), then the font cache
(`typefaces.local_script_faces`). Rendering never downloads a pack. To publish one, commit a zip of the Noto Sans
SC, TC, JP and KR regular styles under those names (OFL, with its licence) to VixlPacks and add a `PACKS["cjk"]`
entry with the commit, SHA-256 and size, in the shape the `vixl.packs` docstring shows; `vixl.packs.install("cjk")`
then fetches it once and the render path finds it in the pack directory.

### Grey areas

- **It needs a hook point that does not exist yet.** Add the hook point to `vixl.plugins.HOOKS` with its call
  signature, call it from the core, and document it below. Do not import the plugin from the core instead. If
  the hook would need half of the plugin's internals, the feature is probably core.
- **It is mostly ordinary layers but adds one export format or document-level record.** It is still a plugin.
  Use the `export-format` and `validate-state` hooks. The font maker is the example: it writes glyph layers and
  a `font_design` record, and adds TTF/OTF/WOFF export through a hook.
- **It extends an existing plugin.** Put it in that plugin's package.

## Adding a built-in plugin

1. Create `src/vixl/plugins/<name>/` with an `__init__.py` that holds only the `PLUGIN` manifest (data):

   ```python
   PLUGIN = {
       "name": "comics",                 # the package name
       "title": "Comics",
       "summary": "Comic pages: ordered panels, gutters, artwork slots, captions and dialogue.",
       "kind": "operations",             # operations | workflows | importer | provider | checks
       "modules": ["comics"],            # every module in the package
       "operations": ["comics"],         # modules with TYPES, schemas(add) and execute(project, op)
       "commands": [],                   # modules with compile_command(cmd, args)
       "workflows": [],                  # modules with ACTIONS, dispatch(...), optional FIELD_TYPES and SUMMARIES
       "hooks": {},                      # {"hook point": ["module:function", ...]}
       "requires": [],                   # other plugins this one imports
       "capabilities": {},               # {"topic": ("words that select it", ["guidance names"])}
       "checks": [],                     # optional design check names this plugin adds
   }
   ```

   `checks` names optional design checks (`check --checks NAME`); they join `checks.OPTIONAL_CHECKS` and the
   plugin's `check` hook runs them. The `spelling` plugin adds `spelling` this way.

   `capabilities` adds topics to `vixl_reference('capabilities')` (the charts plugin adds `charts`). The guidance
   names must exist in the one guidance registry, `src/vixl/guidance.py`; add the text there, not in the plugin.

2. Add the name to `BUILTIN` in `src/vixl/plugins/__init__.py`. The order there is the registration order.
3. Classify each new operation in `targets.py` (`EACH`, `JOINT` or one), as for any operation.
4. Regenerate the table below from `vixl.plugins.markdown_table()` and the operations table in
   `docs/reference/operations.md`. Tests compare both.
5. Write tests. `tests/test_plugins.py` checks the manifest, the declared `requires` and the boundary: a core
   module that imports a plugin module fails the test unless the import is in its list of known exceptions.

## Hook points

| Hook point | Signature | Called |
| --- | --- | --- |
| `normalize` | `fn(kind, op, note) -> op` | For every operation, before schema validation |
| `validate-layer` | `fn(layer, state, project)` | For every layer when a document is validated |
| `validate-state` | `fn(project, state)` | Once per document validation |
| `check` | `fn(checks, candidate, resolved, local_bounds, projection, issue, document, artboard, page)` | During design checks; act only when your check name is in `checks` (`document` is the checked document before its page view and candidate copy) |
| `after-apply` | `fn(project)` | After a batch applies, before checks |
| `apply-report` | `fn(project, operations, result)` | When the apply result is assembled |
| `export-format` | `fn(project, path, format, report, **options) -> data or None` | On export; return None for formats that are not yours |
| `import-format` | `fn(project, data, format, **options) -> result or None` | On import; return None for formats that are not yours |
| `brand-format` | `fn(data) -> (kit, unmapped) or None` | `vixl.brand.load_brand_or_profile`: read an uploaded brand in another format (the brand kit reads a Design Profile); return None for shapes that are not yours |
| `spell` | `fn(project, texts) -> {lang, available, message?, words} or None` | The `text` suite rule's `spelling: true`: unknown words in `{layer id: drawn text}` with suggestions |
| `check-variants` | `fn(project, request) -> report or None` | `vixl check --locales` and the workflow `check` field `locales`; return None when the request names none of your variant axes |
| `cli-command` | `fn(cmd, args, options, limits) -> result or None` | For every top-level CLI command (`vixl CMD …`) before the core's own; return None for commands that are not yours |
| `production-report` | `fn(project, spec, report)` | When a campaign run (`production.run`) has its results, before `production.json` is final |
| `job-kind` | `fn(kind) -> {validate, run} or None`, kinds in `fn.KINDS` | When a durable job is submitted or run; return None for kinds that are not yours |
| `job-complete` | `fn(event) -> delivery record or None` | Once when a durable job, `check-all` or a pipeline run ends (`vixl.jobs.completion_event` shape) |
| `resource-kind` | `fn(kind) -> {builtins, validate} or None`, categories in `fn.KINDS` | When the resource library lists, reads or saves a category that is not built in |
| `host-route` | `fn(app, host)` | Once when `vixl host` builds its app: add routes; `host.session(ws)`, `host.workspace(ws)` and `host.answer(error)` are the helpers, and every route is already behind the bearer token |

## Helpers other plugins use

A plugin that declares `requires: ["workspace_qa"]` can call these (see their module docstrings):

- `workspace_qa.dependents`: the workspace dependency graph. `graph(workspace, documents=None)` reads every
  document's links, `brand.json`, project groups, merge data and templates and library suites into a reverse index
  (cached by mtime in `.vixl-checks/links-index.json`); `dependents(workspace, target, kinds=…, nested=…)`,
  `walk(…)` (with the cycles found) and `tree(…)` answer who depends on a file or `suite:NAME`;
  `register(reader)` adds an edge kind (`fn(state, path, workspace) -> [(kind, target)]`).
- `workspace_qa.candidate`: evaluate a change on an unsaved copy and commit only if clean.
  `evaluate(session, document, change, request=…, fail_on=…)` applies a function or operations, runs `check` and the
  attached suites (`workspace_checks.check_document`) and diffs the render; `evaluate_all(…, apply="if-passing",
  journal=NAME)` does it for many documents under their file locks; `commit(session, journal, evaluations)`
  publishes through the project-group journal (`group-recover NAME` undoes an interrupted one).
- `workspace_qa.approval`: `find(path, workspace)`, `status(project, approval)` and `report(project)` read a
  document's approved baseline; `approved_changes(session, {path: candidate})` lists approved documents a change moves.

## Built-in plugins

<!-- generated from vixl.plugins.markdown_table(); tests/test_plugins.py compares it -->
| Plugin | Kind | What it adds | Operations and workflow actions |
| --- | --- | --- | --- |
| `charts` (Charts and tables) | operations | Data charts, tables and key-value lists as editable layers, with native PPTX charts and tables. | `chart`, `chart-data`, `key-value-list`, `table`, `table-data` |
| `drawing` (Hand drawing) | operations | Import, clean, vectorize, straighten, fill and restyle hand drawings and photographed sketches. | `drawing`, `drawing-compare`, `drawing-report` |
| `diagrams` (Diagrams) | operations | Node-and-connector diagrams with automatic layout and routing, kept live as nodes move. | `diagram`, `diagram-from-text`, `diagram-set` |
| `comics` (Comics) | operations | Comic pages: ordered panels, gutters, artwork slots, captions and dialogue. | `comic-layout` |
| `atmosphere` (Atmosphere) | operations | Reflection, haze, star-field, string-lights and bokeh, each one operation. | `bokeh`, `haze`, `reflection`, `star-field`, `string-lights` |
| `organic` (Organic shapes) | operations | Composable organic shapes: generators, growth rules and presets for living things. | `organic`, `organic-catalog` |
| `characters` (Characters) | operations | Standard-part characters with planar rigs, poses and retargetable walk, idle and other cycles, shared as .vixlchar packages with named expressions, poses and motions. | `character`, `character-cycle`, `character-ik`, `character-lipsync`, `character-load`, `character-pose`, `character-rig`, `character-save`, `character-discover`, `character-inspect`, `character-package`, `character-place` |
| `fontmaker` (Font maker) | operations | Design a font in a document (metrics, glyph grid, kerning) and export TTF, OTF, WOFF and WOFF2. | `font-build`, `font-design`, `font-glyph`, `font-grid` |
| `film` (Film) | workflows | Assemble scenes and shots into MP4, WebM, GIF or WebP films; sample video and analyze audio. | `audio-analyze`, `film-export`, `film-plan`, `film-preview`, `video-sample` |
| `lyrics` (Lyric videos) | workflows | Synced lyric videos from audio, an LRC file and a styled template document. | `lyric-video-build`, `lyric-video-export`, `lyric-video-plan` |
| `imposition` (Print imposition) | workflows | Merge CSV rows into a template and impose the copies n-up on press sheets with marks and bleed. | `merge-impose` |
| `brand_kit` (Brand kit) | workflows | Logo packages, brand guideline boards, device, print and merch mockups and print-ready art from a brand.json and a logo. | `brand-board`, `brand-export`, `brand-import`, `logo-package`, `mockup`, `mockup-list`, `mockup-save`, `print-art` |
| `deck_markdown` (Markdown to deck) | workflows | Turn a Markdown outline into a checked slide deck with charts, tables and speaker notes. | `deck-from-markdown` |
| `teamwork` (Teamwork) | workflows | Workspace branches and merges, document groups with shared parameters and rollback, suite inference. | `branch-fork`, `branch-list`, `branch-merge`, `branch-status`, `group-apply`, `group-define`, `group-list`, `group-recover`, `group-show`, `suite-infer` |
| `workspace_qa` (Workspace QA) | workflows | check-all and replace-across over many documents, protected edits, proof pages, render lockfiles, deliverable packages, approved baselines and link impact. | `approve`, `check-all`, `link-impact`, `package`, `proof`, `protected-edit`, `replace-across`, `reproduce` |
| `layout_repair` (Layout repair) | workflows | repair-layout: try ranked candidate fixes for failing checks and keep the least disruptive one. | `repair-layout` |
| `pipelines` (Pipelines) | workflows | Saved, resumable pipelines over many documents with a run record, watch mode with triggers and schedules, completion webhooks, data sync from a CSV and bulk structure upgrades. | `bulk-upgrade`, `data-sync`, `pipeline-run`, `watch` |
| `app_animation` (App animation packages) | workflows | Package animation states, theme variants, reduced-motion images and a sample consumer for apps. | `app-animation-package` |
| `screen_capture` (Screen capture) | workflows | Capture the local desktop, a pixel rectangle or a Windows window to a PNG, only when asked. | `screen-capture` |
| `localization` (Localization) | workflows | Locale variable tables and strings CSVs, a locale x finding check matrix, and localize fan-out with fit, RTL mirroring and font fallbacks. | `locales-set`, `group-locales`, `locale-check`, `localize` |
| `figma_import` (Figma import) | importer | Import a Figma page or node as editable layers, with images, fonts and unsupported nodes rasterized. | hooks: import-format |
| `pdf_import` (PDF import) | importer | Import a PDF page as editable layers (needs the optional pypdfium2 package). | hooks: import-format |
| `ai` (AI providers) | provider | Generate, edit, detect and describe images through configured providers; model discovery and routing. | none: the core calls it directly |
| `spelling` (Spelling) | checks | An optional spelling check of drawn text with suggestions; English is bundled, other languages are content packs. | hooks: check, spell |

## Not separable yet

These core modules still import plugin code directly. Each is listed with its reason in
`tests/test_plugins.py` (`KNOWN_COUPLINGS`). Remove an entry when its import moves behind a hook. A plugin can
ship separately only when it has no entries left.

- The CLI, REST and MCP surfaces call the AI provider plugin, workspace checks, reproduce, package and imposition
  directly for their own commands.
- The job queue runs film, lyric video and AI generation jobs by kind.
- Design checks and accessibility read chart data for chart contrast and series colors. PPTX export writes
  native charts and tables.
- Smaller helpers: `parts` uses the drawing plugin's erode and dilate, `timeline` poses characters, `resources`
  validates mockup templates, `group_consistency` reads workspace check members, `audio` probes media, and
  converters reuse the chart style.
- Workflow request descriptions for plugin actions are still in `workflow_schema.py`.
