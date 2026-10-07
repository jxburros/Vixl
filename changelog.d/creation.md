### Changed defaults

- **One creation path.** `vixl new`, Python `Project()`/`Project.sized()`/`Project.new()`, `vixl_document_create`, compose and REST compose now create documents the same way: they roll and store `design_defaults`, and the same `seed` and `variety` give identical defaults on every surface. `vixl new` gains `--seed`, `--variety`, `--purpose` and `--no-fonts`. `Project(width, height)` alone is still a plain canvas; `Project.sized(size, design=False)` gives a plain named-size canvas as before (#394).
- **Default document size by purpose.** Size, width and height are optional on create and compose. Without them, the new `purpose` option picks the size (social 1080×1350, slides 1920×1080, print Letter or A4 by locale, icon 1024×1024 …), and with neither the document is 1080×1080. CLI and MCP used to require a size, and Python `Project()` was 1920×1080: pass `width=1920, height=1080` (`vixl new 1920x1080`) for the old Python default (#413).
- **Canvas background from the palette.** A new design document without `background` gets the rolled palette's background role; logo, icon and favicon sizes and mark purposes (logo, emblem, monogram, icon, favicon …) stay transparent. Pass `background: "transparent"` (`--background transparent`) for the old result. Plain canvases are now stored as `transparent` rather than `#00000000` (#411).
- **Fonts installed at creation.** New documents embed the workspace default fonts or, without them, install the rolled font pairing from the font cache, then the network, so text no longer starts in the proofing fallback. Offline, creation reports the pairing under `creation.fonts` with a next step and does not retry the network in that process. Pass `workspace_fonts: false` (`--no-fonts`) or set `VIXL_AUTO_FONTS=off` for the old result; `VIXL_AUTO_FONTS=cache` never downloads (#418).
- **`layout-apply` follows the whole stored direction.** Without `seed`, it now uses the document's rolled layout seed, margin, corner, look, style, motif and background treatment as well as palette, mode, type scale, density and accent, matching `vixl_roll(apply=true)`; explicit fields still win. Pass `seed` for an independent choice (#392).
- **Density shapes the spacing.** Airy and dense now widen and tighten a rolled `direction.margin` (×1.25 and ×0.75) and the spacing unit behind gaps, and rolls weight density like the layout builder (balanced twice as often). Pass `density: "balanced"` for the previous margins and gaps (#390).

### Added

- **`creation` in create results** (MCP, CLI, Python `report=`, compose): the size and why (`argument`, `purpose` or `default`), the background and why (`argument`, `palette` or `mark`), and whether the pairing was installed (#394, #411, #413, #418).

### Fixes

- **Rolled accents show in safe compositions.** The accent a roll chooses (rule, bar, dot, block, outline) is drawn next to the composition's own device; before, it was recorded but never drawn. Pass `accent: "none"` for the old result (#389).
