"""Build a portable paper character, preview and animated WebP (no external image/audio assets)."""
from pathlib import Path
from vixl.project import Project
from vixl.timeline import export_timeline, render_at


def build():
    project = Project(480, 360, '#e2d4b5')
    project.apply([
        {'type': 'shape', 'name': 'hill', 'shape': 'ellipse', 'width': 650, 'height': 150, 'x': -80, 'y': 285, 'fill': '#728468'},
        {'type': 'layer-depth', 'target': 'hill', 'depth': 3},
        {'type': 'character', 'name': 'Ada', 'x': 180, 'y': 65, 'height': 280, 'colors': {'outfit': '#ba6346'}},
        {'type': 'character-save', 'target': 'Ada', 'name': 'Ada-paper'},
        {'type': 'character-cycle', 'target': 'Ada', 'cycle': 'idle', 'duration': 2400, 'period': 2400, 'samples': 24},
        {'type': 'cut-paper', 'targets': ['Ada', 'hill'], 'grain': .045, 'roughness': .4, 'thickness': 2, 'fps': 12, 'jitter': .2, 'seed': 17},
        {'type': 'speech-bubble', 'name': 'greeting', 'anchor': 'Ada/head', 'text': 'A little paper world.', 'x': 20, 'y': 20, 'max_width': 200, 'size': 21, 'fill': '#fff7e6'},
        {'type': 'particles', 'name': 'dust', 'preset': 'dust', 'count': 12, 'x': 240, 'y': 120, 'spread': [400, 190], 'life': 3000, 'duration': 2400, 'size': 1, 'seed': 17},
        {'type': 'lighting', 'ambient': .9, 'lights': [{'x': 60, 'y': 40, 'radius': 240, 'color': '#ffefce', 'intensity': .12}], 'vignette': .18},
        {'type': 'audio-track', 'name': 'chime', 'synth': 'bell', 'duration': 700, 'start': 0, 'volume': .35, 'fade_out': 300},
        {'type': 'timeline-set', 'duration': 2400, 'fps': 24},
    ])
    return project


def main(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    project = build()
    project.save(output / 'paper-character.vixl')
    render_at(project, 400).save(output / 'paper-character.png')
    export_timeline(project, output / 'paper-character.webp', fps=12)
    from vixl.checks import check_design
    print(check_design(project, checks=['character', 'motion', 'captions']))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('output', nargs='?', default='paper-demo')
    main(parser.parse_args().output)
