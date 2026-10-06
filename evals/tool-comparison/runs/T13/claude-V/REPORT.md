# T13 Pixel-art sprite: Vixl lane (claude-V)

Character: a lighthouse keeper in a yellow hooded raincoat with navy trousers and dark brown boots,
holding a lit lantern in the front hand. Side view, facing right.

## Files

| File | How it was made |
| --- | --- |
| `keeper.vixl` | The editable source. Made with the Vixl MCP tools: `vixl_document_create` (32x32, transparent), then one `vixl_operations_apply` batch of `pixel-art` layers written as character rows plus a palette. There are 9 pixel layers: `body` (hood, face, coat, arm and hand), `legs-stand`, `legs-w1` to `legs-w4`, and `lantern-a`/`-b`/`-c` (hanging straight, swung forward, swung back). A second batch builds each frame with `show`/`hide` and integer `move` (body bob, lantern position), saves it with `frame-save` (idle1, idle2, walk1 to walk4), and defines the named animations `idle` and `walk` with `animation-set` (loop 0, which means forever). |
| `keeper-sheet.png` | `vixl_export_animation` with format=sheet, columns=6, scale 1, nearest. The file is 192x32 RGBA, unscaled, with frames in the order idle1, idle2, walk1, walk2, walk3, walk4 from left to right. |
| `keeper-sheet.json` | Written by Vixl next to the sheet in the same export. Each frame has `name`, `x`, `y`, `width`, `height` and `duration` (ms). It also has top-level `width`, `height` and `loop`, and an `animations` object that lists the frames and total duration of `idle` and `walk`. |
| `keeper-idle.gif` | `vixl_export_animation` with animation=idle, scale 8, sampling=nearest. 256x256, 2 frames of 400 ms, loops forever. |
| `keeper-walk.gif` | `vixl_export_animation` with animation=walk, scale 8, sampling=nearest. 256x256, 4 frames of 120 ms, loops forever. |
| `REPORT.md` | This file. |

## Animation design

- **idle:** In frame 2 the body layer (head, coat, arm) moves down 1 px for the breath. The lantern
  moves down with the hand and swings 1 px forward. The legs do not move.
- **walk:** contact, passing, contact, passing. Each leg is drawn in a near colour (#34467a) or a
  far colour (#222c52), and the two contact frames swap which leg is in front. In the passing frames
  the body rises 1 px and the back boot is lifted. The lantern swings forward in walk1, hangs
  straight in walk2 and walk4, and swings back in walk3.
- **Baseline:** the boot soles are on row 30 in all six frames (row 31 is empty).

## Checks I ran (small Pillow scripts that only read the files)

- The sheet is 192x32 RGBA, and every alpha value is 0 or 255.
- The sheet uses 13 opaque colours. The palette is outline #1b1525, raincoat #f4c430/#c98e16/#fff09a,
  skin #f2b48c/#c8805e, trousers #34467a/#222c52, boots #4a2f2a/#6b4a3a, and lantern
  #6b7280/#f08a24/#fff3b0.
- In every frame the lowest opaque row is row 30.
- I checked both GIFs. They are 256x256 with loop=0, and the frame durations are [400, 400] and
  [120x4]. Every 8x8 block in every frame is a single colour, so there is no smoothing. When I
  downsample each GIF frame it matches the matching sheet frame exactly (both colour and
  transparency).
- I looked at an 8x nearest-neighbour preview of the sheet.

## Deviations and choices

- I used the frame names `idle1`, `idle2` and `walk1` to `walk4`. The brief did not set a naming
  scheme.
- `keeper-sheet.json` has more fields than the brief asks for (`loop`, `animations`, and the sheet
  size). These come from Vixl's sheet exporter. I left them in.
- I typed the pixel rows by hand into the `pixel-art` operations. To check row lengths before
  sending them, I ran a small Python script that reads the text and checks it. A second small Python
  script printed the JSON for the repetitive show/hide/move/frame-save batch. It did not make any
  pixel data.
- The export result for the sheet reported `"size":[32,32]` (the frame size), but the file itself
  is 192x32.

## Unsure about

- At 32 px the walk is readable but simple. Because only the leg colours change, the two contact
  frames have the same outline.
- The GIF transparency comes from Vixl's GIF encoder (disposal 2). I checked that the transparent
  pixels stay transparent when Pillow decodes the frames, but I did not test the GIFs in other
  viewers.
