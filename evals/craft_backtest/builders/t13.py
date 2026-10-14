"""T13 pixel sprite sheet (192 × 32): six 32 × 32 frames of the lighthouse keeper.

From ``runs/T13/claude-V/keeper-sheet.png`` and ``keeper-sheet.json``: each frame holds the keeper as a few
pixel-aligned blocks (hood and coat, face, boots, lantern), shifted by the frame's bob. No text."""

from ..kit import Doc


def build():
    d = Doc(192, 32, "transparent", body=10)
    for frame in range(6):
        x, bob = frame * 32, frame % 2
        d.rect(f"f{frame + 1}-coat", x + 10, 6 + bob, 12, 20, "#f2c230")
        d.rect(f"f{frame + 1}-face", x + 13, 9 + bob, 6, 4, "#f2d2b0")
        d.rect(f"f{frame + 1}-boots", x + 11, 26, 10, 4, "#5a3a2a")
        d.rect(f"f{frame + 1}-lantern", x + 23, 18 + bob, 3, 4, "#f2a541")
    return {"T13-sprite-sheet": d.build()}
