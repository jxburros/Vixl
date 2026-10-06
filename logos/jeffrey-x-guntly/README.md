# Jeffrey X Guntly logo

Vector recreation of `reference.jpg` (1000 × 1000), traced into editable Bézier paths.
The rendered result matches the reference to within 7 of 69,483 ink pixels.

- `jeffrey-x-guntly.vixl` — editable Vixl document
- `jeffrey-x-guntly.svg` / `.png` — exports

## Layers

```
Jeffrey X Guntly (group)
├── vine      the vine with its leaves and thorns, including the stroke that forms the X's thin arm
├── X         the thick diagonal of the X, with its serifs and leaves
├── Jeffrey   (group) J, e, f, f 2, r, e 2, y
└── Guntly    (group) G, u, n, t, l, y 2
reference     the original image (hidden), for comparison
```

Each letter is its own path layer, so letters, words, the X and the vine can be moved,
recoloured or reshaped on their own.

## Rebuilding the trace

`tools/trace.py` splits the reference into those parts and traces each with potrace
(`pip install potracer scipy`); `tools/build_ops.py` turns the paths into a Vixl batch:

```
python3 tools/trace.py reference.jpg paths.json
python3 tools/build_ops.py paths.json ops.json "Jeffrey X Guntly"
vixl --project jeffrey-x-guntly.vixl apply ops.json
```
