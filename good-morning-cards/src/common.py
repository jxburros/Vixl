import sys
sys.path.insert(0, '/tmp/claude-0/-home-user-Vixl/a9628876-9af1-5cc2-98ab-1f0ea7ca6808/scratchpad/w')
from bear import *
from vixl.project import Project
from vixl.typefaces import pair_fonts
from vixl.timeline import contact_sheet, render_at, export_timeline
from PIL import Image

def kf(o, target, prop, keys):
    """keys: list of (time, value[, easing]) -> keyframe ops (easing applies to the segment that starts at that key)."""
    for k in keys:
        op = {"type": "keyframe", "target": target, "property": prop, "time": k[0], "value": k[1]}
        if len(k) > 2:
            op["easing"] = k[2]
        o.add(op)

def make(w, h, bg, ops, fonts=True, fps=20, duration=4000):
    p = Project(w, h, bg)
    if fonts:
        pair_fonts(p, "fredoka-nunito")
    r = p.apply([{"type": "timeline-set", "duration": duration, "fps": fps, "loop": 0}] + ops.ops, detail="brief")
    return p, r

def sheet(p, path, times, max_width=1800, columns=None):
    im = contact_sheet(p, times=times, columns=columns, max_width=max_width)
    im.save(path)
