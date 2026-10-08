# Proof page for the packet

`build.py` collects what exists *when it runs*: the key outputs of workflows 01–05 and the image, GIF, SVG,
PDF and `.vixl` files in the sibling folders (`illustrations`, `creative`, `documents`, `animations`, up to 5
each), and writes `output/ai-packet-proof.html` with `vixl workflow proof`:
thumbnails, file facts, `check` findings for `.vixl` items, a before/after diff for the gated card, and
approve/reject buttons that download `ai-packet-proof-decisions.json` for the reviewer to send back.

Open the HTML in any browser; it works offline. Rerun the script after more work lands.

## Reuse it
Edit `items()` (fixed items with labels and notes, then folders to scan) and `MAX_PER_FOLDER`. `max_size`
is 256 px to keep the page under 3 MB: every image is embedded twice as PNG, and the default 1200 px made a
39 MB page here. If an item cannot be read (here a `.vixl` with a missing linked source) the whole call fails;
the script drops that item, retries, and lists it under `dropped` in `output/proof-run.json`.
