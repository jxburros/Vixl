"""Prepare craft-check pieces for judging: views at real size, 1:1 crops and a use-size thumbnail.

    python evals/craft-check/prepare.py evals/craft-check/2026-10-13 OUT

For every piece folder (C01 …) with an exported PNG or JPEG, writes OUT/<piece>/ with brief.md, the
deliverable, views/ and VIEWS.md. The thumbnail size comes from THUMBNAILS: the small size each brief
says the piece must work at.
"""

import shutil
import sys
from pathlib import Path

from PIL import Image

KIT = Path(__file__).resolve().parent
sys.path.insert(0, str(KIT.parent / "tool-comparison"))
from rejudge import raster_views  # noqa: E402

THUMBNAILS = {"C01": 400, "C02": 360, "C03": 160, "C04": 480, "C05": 400, "C06": 300, "C07": 390, "C08": 120}


def prepare(runs, out):
    for piece in sorted(p for p in runs.iterdir() if p.is_dir()):
        images = sorted(f for f in piece.iterdir() if f.suffix.lower() in (".png", ".jpg", ".jpeg"))
        if not images:
            print(piece.name, "no deliverable")
            continue
        dest = out / piece.name
        shutil.rmtree(dest, ignore_errors=True)
        (dest / "views").mkdir(parents=True)
        shutil.copy(next(KIT.glob(f"briefs/{piece.name}-*.md")), dest / "brief.md")
        note = []
        for image in images:
            shutil.copy(image, dest / image.name)
            with Image.open(image) as im:
                im.load()
                raster_views(im.copy(), image.name, dest / "views", note)
                side = THUMBNAILS.get(piece.name)
                if side:
                    scale = side / max(im.size)
                    small = im.convert("RGB").resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
                    small.save(dest / "views" / f"{image.name}.thumbnail-{side}px.png")
                    note.append(f"{image.name}.thumbnail-{side}px.png: the piece at {small.width}×{small.height}, "
                                "the small size the brief says it must work at")
        (dest / "VIEWS.md").write_text("\n".join(f"- {line}" for line in note) + "\n", encoding="utf-8")
        print(piece.name, len(note), "views")


if __name__ == "__main__":
    prepare(Path(sys.argv[1]), Path(sys.argv[2]))
