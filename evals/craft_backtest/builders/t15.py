"""T15 seamless pattern tile (1024 × 1024): kelp, shells, waves and dots.

``ops/T15-tile-placements.json`` holds every copy of the run's two ``pattern-scatter`` groups (``motifs``: 16
copies plus wrapped ghosts; ``dots``: 45 plus one ghost) as ``tile.svg`` places them: centre, rotation, size and
fill. Each copy is drawn as a rounded box of that size (kelp is tall and narrow, shells and waves are round)
at that place, and each group carries the ``pattern_scatter`` recipe the report gives, so the tile is the same
scatter as the original, not a new roll of today's ``pattern-scatter``."""

import json

from ..kit import OPS, Doc


def build():
    placements = json.loads((OPS / "T15-tile-placements.json").read_text(encoding="utf-8"))
    d = Doc(1024, 1024, "#f7f1e5", body=27)
    names = {}
    for kind in ("dots", "motifs"):
        names[kind] = []
        for i, item in enumerate(placements[kind]):
            name = f"{kind}/{i + 1}"
            w, h = item["width"], item["height"]
            d.rect(name, round(item["cx"] - w / 2, 1), round(item["cy"] - h / 2, 1), w, h, item["fill"],
                   radius=round(min(w, h) / 2, 1), rotation=item["rotation"])
            names[kind].append(name)
        d.op({"type": "group", "name": kind, "targets": names[kind]})
    project = d.build()
    recipes = {"dots": {"seed": 31, "count": 45}, "motifs": {"seed": 5, "count": 16, "scale": 1.15,
                                                             "scale_jitter": 0.3, "rotation_jitter": 70}}
    for kind, recipe in recipes.items():
        group = project.layer(kind)
        group["pattern_scatter"] = {"width": 1024, "height": 1024, **recipe}
        group["content_width"], group["content_height"] = 1024, 1024
    return {"T15-tile": project}
