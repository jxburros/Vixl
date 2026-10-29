# Import Vixl file

In Figma desktop, choose **Plugins → Development → Import plugin from manifest** and select `manifest.json`.
Run **Import Vixl file**, then choose a file exported by `vixl export design.figma.json`.

The plugin adds pages to the current file, embeds image fills, creates editable nodes and loads each requested
font before writing text. Fonts Figma cannot load substitute Inter Regular. The result lists substitutions and
the export's conversion losses. Failed imports remove their newly created pages. No network access is used.

The checked-in `code.js` is ready to run. To rebuild from `code.ts`, use Node.js and run `npm ci && npm run build`.
`npm run check` typechecks against the pinned official Figma plugin declarations. `tests/test_figma_export.py`
exercises the compiled plugin against a mock API; visual parity still needs review in a real Figma file.

See [the guide](../../docs/guides/images/figma.md#export-to-figma) for supported features and known losses.
