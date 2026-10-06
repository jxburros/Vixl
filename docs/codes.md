# QR codes and barcodes

[Documentation home](README.md) · [Getting started](getting-started.md) · [Visual gallery](gallery.md)

`qr` and `barcode` draw scannable codes as ordinary vector shapes. The code is one `shape` layer of kind
`path` whose path is the dark modules merged into rectilinear outlines, so PNG, SVG, PDF and PPTX all draw
it natively: crisp at any size, no embedded image, and the same geometry in every export.

```json
{"type": "qr", "name": "ticket", "data": "https://example.com/t/${id}", "module": 6, "x": 40, "y": 40}
{"type": "barcode", "name": "sku", "data": "400638133393", "symbology": "ean13", "module": 3, "height": 120}
```

With an opaque `background` (the default is white) the code sits in a group named after the layer, with
`NAME background` (a rectangle covering the code and its quiet zone) and `NAME code` (the modules). With
`background: "none"` the code is a single layer named `NAME`; keep the area around it light and clear.

## Fields

| Field | `qr` | `barcode` |
| --- | --- | --- |
| `data` | Text or URL (QR byte, alphanumeric and numeric modes are chosen automatically). | Code 128: printable ASCII. EAN-13: 12 digits (the check digit is added) or 13 (the check digit is validated; a wrong one is an error that suggests the right one). |
| `error` | Error correction `L` (7%), `M` (15%, default), `Q` (25%) or `H` (30%, survives a small logo on top). | — |
| `symbology` | — | `code128` (default; switches to set C for runs of digits) or `ean13`. |
| `quiet` | Quiet zone in modules on each side; default 4. | Quiet zone in modules left and right; default 10 for Code 128, 11 left / 7 right for EAN-13. |
| `module` | Pixels per module; default 8. | Pixels per narrowest bar; default 3. |
| `size` / `width`, `height` | `size`: the whole side including the quiet zone, in pixels (instead of `module`). | `width`: the whole width including quiet zones; `height`: bar height (default half the width, at least 40). |
| `color`, `background` | Module colour (default black) and background (default white, `none` for no background). | Same. |
| `name`, `x`, `y` | As for any layer (`x`/`y` accept `"center"` and percentages). | Same. |

`qr` or `barcode` with a `target` (the group or its code layer) changes `data`, `error`, `quiet`, `color`,
`background` and the size in place; without a new size it keeps the module size, so a longer text makes a
larger code. Move, rotate and align codes like any layer.

## Variables and merges

`data` may contain `${variables}` (filters too: `${sku|default:000000000000}`). The stored path shows the
current values; every render re-encodes the data with the values in force, so a `merge-impose` run prints one
correct code per CSV row, and an invalid value (an EAN-13 with a wrong check digit) fails that row with a
clear message. The layer's box stays the same size, so a longer value packs more, smaller modules.

## The `codes` check

`check` runs `codes` by default when a document has codes:

- **Module size**: at the canvas `dpi` a QR module needs at least 0.33 mm, a Code 128 bar 0.19 mm and an
  EAN-13 bar 0.264 mm (80% of nominal); without a dpi at least 2 px, and a warning for fractional module
  sizes under 4 px (blurred edges).
- **Contrast** between the modules and the quiet zone as drawn: below 3:1 is an error, below 4.5:1 a warning,
  and light modules on a dark background are a warning (many scanners read only dark on light).
- **Quiet zone**: any other ink drawn inside the quiet zone (a layer above the code, or something showing
  through when there is no background) is an error.

QR codes are encoded with [segno](https://github.com/heuer/segno); Code 128 and EAN-13 are encoded by Vixl.
Very large QR codes (version 29 and up at the default error correction) exceed the path size limit and are
refused; shorten the data (a short URL) or lower the error correction.
