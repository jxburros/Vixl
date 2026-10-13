"""Build shorts and write contact sheets of sampled frames: python preview.py OUT_DIR [short-prefix ...]"""
import sys
import time

from PIL import Image

import shorts
from vixl.timeline import render_at

OUT = sys.argv[1]
wanted = sys.argv[2:]
for make in shorts.SHORTS:
    sc = make()
    if wanted and not any(sc.name.startswith(w) for w in wanted):
        continue
    t0 = time.time()
    p = sc.build()
    (h0, h1), (a0, a1), (w0, w1), (e0, e1) = (sc.sections[k] for k in ("hook", "action", "why", "end"))
    times = [round(h0 + (h1 - h0) * 0.4), h1 - 200] + [round(a0 + (a1 - a0) * f) for f in (0.1, 0.25, 0.4, 0.55,
                                                                                            0.7, 0.85, 0.98)]
    times += [w1 - 200, round(e0 + (e1 - e0) * 0.3), e1 - 50]
    cols, tw, th = 6, 270, 480
    sheet = Image.new("RGB", (cols * tw, 2 * th))
    for i, t in enumerate(times):
        im = render_at(p, t).convert("RGB").resize((tw, th))
        sheet.paste(im, ((i % cols) * tw, (i // cols) * th))
    sheet.save(f"{OUT}/{sc.name}.jpg", quality=88)
    print(sc.name, f"{time.time() - t0:.1f}s", times, flush=True)
