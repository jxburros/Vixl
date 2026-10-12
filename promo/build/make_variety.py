#!/usr/bin/env python3
"""Build editable promo masters, proofs and a reel without replacing the existing films."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw

from vixl.promo_templates import TREATMENTS
from vixl.resources import create_template
from vixl.timeline import contact_sheet, export_timeline, project_at

COPY = {
    'kinetic': ('Ideas become editable.', 'Your agent makes it. You keep the layers.', 'Make it with Vixl'),
    'editorial': ('Keep the real thing.', 'Live text. Editable layers. A master you can change.', 'Ideas become editable.'),
    'neon': ('Make your next move.', 'Build motion with editable shapes and keyframes.', 'Bring it to life'),
    'spotlight': ('One design. Every size.', 'Create a master. Adapt it for your next channel.', 'Start with Vixl'),
    'split': ('Ask. Build. Edit.', 'From a brief to a document you can keep changing.', 'Keep the layers'),
    'stat': ('3 pillars.', 'Programmable. Editable. Checked.', 'Meet Vixl'),
}
COLORS = {
    'kinetic': ('#152c3d', '#ffffff', '#74ded5', '#152c3d'),
    'editorial': ('#fff6e7', '#30281f', '#a34b26', '#ffffff'),
    'neon': ('#100d24', '#faf5ff', '#d5ff42', '#100d24'),
    'spotlight': ('#152c3d', '#ffffff', '#367e8b', '#ffffff'),
    'split': ('#f0f7f6', '#152c3d', '#287681', '#ffffff'),
    'stat': ('#152c3d', '#ffffff', '#74ded5', '#152c3d'),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path(__file__).resolve().parents[1] / 'variety')
    parser.add_argument('--scenes', action='store_true', help='Build masters and proof sheets only')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    # Build in a fresh destination: deliberate protection for edited masters and prior renders.
    planned = ['gallery.jpg', 'manifest.json', 'promo-variety.mp4']
    planned += [f'{s}{suffix}' for s in TREATMENTS for suffix in ('.vixl', '-sheet.jpg')]
    if any((args.out / name).exists() for name in planned):
        parser.error('Output already exists; choose a fresh --out directory to preserve edited masters.')
    gallery = Image.new('RGB', (1200, 860), '#ececec')
    draw = ImageDraw.Draw(gallery)
    manifest = []
    with tempfile.TemporaryDirectory(prefix='vixl-promo-') as scratch:
        clips = []
        for i, style in enumerate(TREATMENTS):
            bg, fg, accent, on_accent = COLORS[style]
            title, subtitle, cta = COPY[style]
            variables = dict(title=title, subtitle=subtitle, cta=cta, background=bg, foreground=fg,
                             accent=accent, on_accent=on_accent)
            name = f'video-promo-{style}'
            p = create_template(name, variables, seed=42)
            report = project_at(p, 2500).check(checks=['bounds', 'contrast'])
            if not report['passed']:
                raise RuntimeError(f'{name}: {report}')
            p.save(args.out / f'{style}.vixl')
            contact_sheet(p, times=[0, 700, 1500, 3000, 5100, 6000], columns=3, max_width=1200).convert('RGB').save(
                args.out / f'{style}-sheet.jpg', quality=90)
            x, y = (i % 3) * 400, (i // 3) * 430
            gallery.paste(project_at(p, 2500).render().convert('RGB').resize((400, 400)), (x, y))
            draw.text((x + 12, y + 408), style, fill='#152c3d')
            manifest.append({'template': name, 'master': f'{style}.vixl', 'seed': 42, 'variables': variables})
            if not args.scenes:
                clip = Path(scratch) / f'{style}.mp4'
                export_timeline(p, clip, fps=24, scale=.5)
                clips.append(clip)
            print(f'Built {style}', flush=True)
        if clips:
            playlist = Path(scratch) / 'clips.txt'
            playlist.write_text(''.join(f"file '{clip.as_posix()}'\n" for clip in clips))
            subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-f', 'concat', '-safe', '0', '-i',
                            str(playlist), '-c', 'copy', str(args.out / 'promo-variety.mp4')], check=True)
    gallery.save(args.out / 'gallery.jpg', quality=92)
    (args.out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
