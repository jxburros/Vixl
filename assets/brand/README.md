# Vixl brand artwork

The current logo is the [Ripple kit](ripple/START-HERE.md) in `ripple/`: the wordmark (whose x and l
are the reflection of the v and i), the x on its own as the symbol, app and favicon artwork, the
animated wordmark and editable masters. Use the color logo on light backgrounds and the reverse logo
on dark backgrounds. `ripple/build.py` generates every file in the kit.

The README uses the horizontal SVGs. The browser review uses the reverse horizontal
logo and simplified dark favicon, embedded so they display before authentication.
The Claude Desktop bundle uses the square app PNG. Windows executables
and the installer use a multi-size ICO made from that same app artwork.

After changing the logo, run `python assets/brand/ripple/build.py` and then
`python distribution/prepare_branding.py` to refresh the packaged browser SVGs and Windows ICO,
then commit those outputs. The ICO includes 16, 24, 32, 48, 64, 128 and 256 px images; the master
remains square without pre-rounded corners. The full kit stays in the source repository;
only the browser artwork is included in the Python runtime.

The previous identity, the [Digital Shift kit](digital-shift/START-HERE.md), is kept in
`digital-shift/` for reference, marked retired. It is no longer used.
