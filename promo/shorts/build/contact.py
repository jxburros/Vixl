"""Write contact-sheet.jpg: one frame from the action section of each short, read from the finished MP4s."""
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

import shorts
from short import HERE

TW, TH = 216, 384
made = [make() for make in shorts.SHORTS]
sheet = Image.new("RGB", (5 * TW, 2 * TH), "#252B39")
with tempfile.TemporaryDirectory() as tmp:
    for i, sc in enumerate(made):
        a0, a1 = sc.sections["action"]
        frame = Path(tmp) / f"{sc.name}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{(a0 + (a1 - a0) * 0.72) / 1000:.2f}", "-i",
                        str(HERE / f"vixl-short-{sc.name}.mp4"), "-frames:v", "1", str(frame)], check=True)
        sheet.paste(Image.open(frame).convert("RGB").resize((TW, TH), Image.Resampling.LANCZOS),
                    ((i % 5) * TW, (i // 5) * TH))
sheet.save(HERE / "contact-sheet.jpg", quality=86)
