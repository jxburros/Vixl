"""Build the Yorkie emoji set with Vixl: editable masters, a pack document, a review sheet and upload-ready packs.

Run from the repository root: python art/yorkie-emojis/build.py
"""

import base64
import re
import shutil
from pathlib import Path

from vixl import Project
from vixl.emojis import export_pack
from vixl.imports import svg_operations

from yorkie_art import EMOJIS, svg

HERE = Path(__file__).resolve().parent
NAVY, INK, PAPER, CARD = "#23364D", "#4C5968", "#F7F5EF", "#FFFCF5"


def masters():
    (HERE / "svg").mkdir(exist_ok=True)
    (HERE / "masters").mkdir(exist_ok=True)
    for name, (title, parts) in EMOJIS.items():
        raw = svg(parts)
        (HERE / "svg" / f"{name}.svg").write_text(raw)
        master = Project(72, 72)
        # The editable importer takes no stroke-linecap; round caps (and joins) are a layer field instead.
        ops = svg_operations(re.sub(r' stroke-line(cap|join)="round"', "", raw).encode(), master, name)
        master.apply([{**op, "line_cap": "round"} for op in ops])
        master.state["emoji_artwork"] = {"author": "Yorkie emoji set", "license": "unspecified", "source": f"art/yorkie-emojis/svg/{name}.svg"}
        master.save(HERE / "masters" / f"{name}.vixl", overwrite=True)


def pack_document():
    cols = 6
    rows = -(-len(EMOJIS) // cols)
    width, cell = 1080, 150
    p = Project(width, 190 + rows * (cell + 16) + 190, background=PAPER)
    ops = [{"type": "emoji-mode", "mode": "vixl"}]
    for name, (title, _) in EMOJIS.items():
        data = base64.b64encode((HERE / "masters" / f"{name}.vixl").read_bytes()).decode()
        ops.append({"type": "emoji-set", "emoji": f":{name}:", "format": "vixl", "data": data, "name": name})
    ops += [
        {"type": "text", "name": "title", "text": "Yorkie emojis", "size": 56, "color": NAVY, "x": 60, "y": 48},
        {"type": "text", "name": "title-emoji", "text": ":yorkie_blep:", "size": 64, "x": 440, "y": 46},
        {"type": "text", "name": "subtitle", "text": f"{len(EMOJIS)} custom shortcodes, editable VIXL masters, Discord and Slack ready",
         "size": 20, "color": INK, "x": 62, "y": 128},
    ]
    gap = (width - 120 - cols * cell) / (cols - 1)
    for i, (name, (title, _)) in enumerate(EMOJIS.items()):
        x, y = 60 + (i % cols) * (cell + gap), 190 + (i // cols) * (cell + 16)
        ops += [
            {"type": "shape", "shape": "rounded-rectangle", "radius": 16, "name": f"card-{name}", "width": cell, "height": cell,
             "fill": CARD, "x": x, "y": y},
            {"type": "text", "name": f"emoji-{name}", "text": f":{name}:", "size": 100, "x": x + 25, "y": y + 4},
            {"type": "text", "name": f"label-{name}", "text": name.replace("_", " "), "size": 14, "color": INK, "x": x + 14, "y": y + 120},
        ]
    y = 190 + rows * (cell + 16) + 20
    small = " ".join(f":{n}:" for n in list(EMOJIS)[:8])
    ops += [
        {"type": "text", "name": "small-label", "text": "At chat size:", "size": 16, "color": NAVY, "x": 62, "y": y + 6},
        {"type": "text", "name": "small-light-label", "text": "good boy", "size": 24, "color": NAVY, "x": 200, "y": y},
        {"type": "text", "name": "small-light", "text": small, "size": 24, "x": 330, "y": y},
        {"type": "shape", "shape": "rounded-rectangle", "radius": 10, "name": "dark-strip", "width": 450, "height": 48,
         "fill": "#313338", "x": 190, "y": y + 44},
        {"type": "text", "name": "small-dark-label", "text": "on dark", "size": 24, "color": "#DBDEE1", "x": 200, "y": y + 52},
        {"type": "text", "name": "small-dark", "text": small, "size": 24, "x": 330, "y": y + 52},
    ]
    # Emoji-only text is artwork, not reading text: glyph contrast does not apply to it.
    art = ["title-emoji", "small-light", "small-dark", *(f"emoji-{n}" for n in EMOJIS)]
    ops += [{"type": "layer-intent", "target": t, "waive": [{"check": "contrast", "reason": "emoji artwork"}]} for t in art]
    p.apply(ops)
    p.save(HERE / "yorkie-emojis.vixl", overwrite=True)
    return p


if __name__ == "__main__":
    masters()
    project = pack_document()
    project.render().save(HERE / "yorkie-emojis.png")
    keys = [f":{n}:" for n in EMOJIS]
    out = HERE / "packs"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir()
    export_pack(out / "yorkie-discord.zip", keys, "discord", project)
    export_pack(out / "yorkie-slack.zip", keys, "slack", project)
    export_pack(out / "yorkie-images-512.zip", keys, "images", project, size=512)
    print(f"{len(keys)} emojis -> {out}")
