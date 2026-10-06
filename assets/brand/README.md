# Vixl brand artwork

The complete supplied [Digital Shift kit](digital-shift/START-HERE.md) is preserved in
`digital-shift/`, including editable masters, usage guidance and the overview.
Use its color logo on light backgrounds and reverse logo on dark backgrounds.

The README uses the horizontal SVGs. The browser review uses the reverse horizontal
logo and simplified dark favicon, embedded so they display before authentication.
The Claude Desktop bundle uses the supplied square app PNG. Windows executables
and the installer use a multi-size ICO made from that same app artwork.

After replacing artwork in the kit, run `python distribution/prepare_branding.py`
to refresh the packaged browser SVGs and Windows ICO, then commit those outputs.
The ICO includes 16, 24, 32, 48, 64, 128 and 256 px images; the master remains
square without pre-rounded corners. The full kit stays in the source repository;
only the browser artwork is included in the Python runtime.

## GWatch logo kits

[`gwatch/`](gwatch/START-HERE.md) holds Vixl-built logo kits for GWatch and GWatch Agent: vector
rebuilds of the supplied artwork in mark, horizontal and stacked layouts, four colour treatments,
and SVG, PDF, PNG, ICO and platform icon sets. Rebuild with `python assets/brand/gwatch/build.py`.
