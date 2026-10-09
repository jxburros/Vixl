"""Self-contained app animation families using the existing timeline encoders."""
from copy import deepcopy
import json
from pathlib import Path
import re
import tempfile

from .errors import require
from .model import finite

FIELDS = {
    'states': {'type': 'object', 'description': 'Named states. Each has source (.vixl), optional loop (default true), interruptible (true), on_complete state, poster time, variables and per-theme variable overrides.'},
    'default_state': {'type': 'string', 'description': 'Initial state; must exist in states.'},
    'themes': {'type': 'object', 'description': 'Theme names mapped to document variables; default light and dark with no overrides.'},
    'transitions': {'type': 'array', 'description': 'Explicit {from, event, to} rules. State names must exist; event names are identifiers.'},
    'output': {'type': 'string', 'description': 'New workspace-relative package directory; existing directories are refused.'},
    'format': {'type': 'string', 'enum': ['webp', 'gif', 'apng'], 'description': 'Animated asset encoding; default webp. Every variant also has a reduced-motion PNG.'},
}


def identifier(value):
    require(isinstance(value, str) and re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,49}', value),
            'State, theme and event names must be 1–50 letters, digits, underscores or hyphens')
    return value


def variable_map(value):
    require(isinstance(value, dict) and len(value) <= 1000 and all(isinstance(k, str) for k in value),
            'Theme and state variables must be objects with at most 1000 entries')
    return value


def records(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from records(child)
    elif isinstance(value, list):
        for child in value:
            yield from records(child)


def package(session, request):
    from .project import Project
    from .timeline import export_timeline, project_at, visible_content, parse_time
    from .assets import png_bytes
    from .production import write_bytes
    states = request['states']
    require(isinstance(states, dict) and 1 <= len(states) <= 32, 'Package needs 1–32 named states')
    for name in states:
        identifier(name)
    require(len({name.casefold() for name in states}) == len(states), 'State names must be unique ignoring case')
    default = request['default_state']
    require(isinstance(default, str) and default in states, 'default_state must name a provided state')
    themes = request.get('themes', {'light': {}, 'dark': {}})
    require(isinstance(themes, dict) and 1 <= len(themes) <= 8, 'Package needs 1–8 themes')
    for name, values in themes.items():
        identifier(name)
        variable_map(values)
    require(len({name.casefold() for name in themes}) == len(themes), 'Theme names must be unique ignoring case')
    transitions = request.get('transitions', [])
    require(isinstance(transitions, list) and len(transitions) <= 256, 'Transitions must be a list of at most 256 rules')
    seen = set()
    for rule in transitions:
        require(isinstance(rule, dict) and set(rule) == {'from', 'event', 'to'}, 'Transition needs from, event and to')
        identifier(rule['from'])
        identifier(rule['to'])
        require(rule['from'] in states and rule['to'] in states, 'Transition references a missing state')
        identifier(rule['event'])
        key = (rule['from'], rule['event'])
        require(key not in seen, f'Ambiguous transition for {key}')
        seen.add(key)
    fmt = request.get('format', 'webp')
    require(fmt in ('webp', 'gif', 'apng'), 'Package format must be webp, gif or apng')
    require(isinstance(request['output'], str), 'output must be a package directory path')
    output = session.resolve(request['output'])
    require(not output.exists(), f'Output directory already exists: {output}', 'output_exists')
    plans = []
    for name, state in states.items():
        require(isinstance(state, dict) and 'source' in state and set(state) <= {
            'source', 'loop', 'interruptible', 'on_complete', 'poster', 'variables', 'themes'}, f'Invalid state: {name}')
        require(isinstance(state['source'], str), f'{name}.source must be a project path')
        for key in ('loop', 'interruptible'):
            require(type(state.get(key, True)) is bool, f'{name}.{key} must be boolean')
        require(state.get('on_complete') is None or isinstance(state['on_complete'], str) and state['on_complete'] in states,
                f'{name}.on_complete references a missing state')
        require(not state.get('on_complete') or not state.get('loop', True), f'{name}: a looping state cannot complete')
        variable_map(state.get('variables', {}))
        overrides = state.get('themes', {})
        require(isinstance(overrides, dict) and set(overrides) <= set(themes), f'{name} references an unknown theme')
        for values in overrides.values():
            variable_map(values)
        source = Project.load(session.resolve(state['source']), limits=session.limits)
        require(not any(row.get('type') == 'link' or row.get('linked') for row in records(source.state)),
                f'{name}: freeze external linked artwork before packaging so the master is self-contained')
        for row in records(source.state):
            font = row.get('font')
            require(not isinstance(font, str) or font in source.assets or not (Path(font).is_absolute() or '/' in font or '\\' in font or Path(font).suffix.lower() in {'.ttf', '.otf', '.woff', '.woff2'}),
                    f'{name}: register and embed external font {font!r} before packaging')
        plans.append((name, state, source))
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {'format': 'vixl-app-animation', 'version': 1, 'default_state': default,
                'themes': list(themes), 'transitions': deepcopy(transitions), 'states': {}}
    with tempfile.TemporaryDirectory(dir=output.parent, prefix='.vixl-app-') as temporary:
        root = Path(temporary) / 'package'
        (root / 'assets').mkdir(parents=True)
        (root / 'masters').mkdir()
        for name, settings, source in plans:
            (root / 'assets' / name).mkdir()
            master = f'masters/{name}.vixl'
            source.save(root / master)
            state = {'master': master, 'loop': settings.get('loop', True),
                     'interruptible': settings.get('interruptible', True),
                     'on_complete': settings.get('on_complete'), 'variants': {}}
            for theme, variables in themes.items():
                p = source.clone()
                p.state['variables'].update({**variables, **settings.get('variables', {}), **settings.get('themes', {}).get(theme, {})})
                p.apply({'type': 'timeline-set', 'loop': 0 if state['loop'] else 1})
                duration = p.state['timeline']['duration']
                if 'poster' in settings:
                    poster = parse_time(settings['poster'], duration, p.state['timeline'].get('markers'))
                    finite(poster, 'poster', 0, duration)
                else:
                    poster = max((round(duration * i / 8) for i in range(9)),
                                 key=lambda time: len(visible_content(project_at(p, time))))
                asset = f'assets/{name}/{theme}.{fmt}'
                still = f'assets/{name}/{theme}-reduced.png'
                report = export_timeline(p, root / asset, format=fmt)
                write_bytes(root / still, png_bytes(project_at(p, poster).render()))
                state['variants'][theme] = {'animation': asset, 'poster': still, 'reduced_motion': still,
                                             'poster_time_ms': poster, 'duration_ms': duration,
                                             'width': p.state['canvas']['width'], 'height': p.state['canvas']['height'],
                                             'variables': deepcopy(p.state['variables']), 'warnings': report.get('warnings', [])}
            manifest['states'][name] = state
        write_bytes(root / 'manifest.json', (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode())
        embedded = json.dumps(manifest, ensure_ascii=False).replace('<', '\\u003c')
        write_bytes(root / 'index.html', CONSUMER.replace('__MANIFEST__', embedded).encode())
        root.rename(output)
    return {'output': str(output), 'manifest': str(output / 'manifest.json'), 'states': len(states),
            'themes': len(themes), 'variants': len(states) * len(themes), 'consumer': str(output / 'index.html')}


CONSUMER = '''<!doctype html><html lang="en"><meta charset="utf-8"><title>Animation family</title>
<style>body{font:16px system-ui;margin:3rem;max-width:50rem}img{display:block;max-width:100%;height:320px;object-fit:contain}button,select{font:inherit;margin:.4rem;padding:.5rem}</style>
<h1>Animation family</h1><label>State <select id="states"></select></label><label>Theme <select id="themes"></select></label>
<img id="animation" alt=""><div id="events"></div><p id="status" aria-live="polite"></p>
<script type="application/json" id="manifest">__MANIFEST__</script><script>
const manifest=JSON.parse(document.getElementById('manifest').textContent);
const states=document.getElementById('states'),themes=document.getElementById('themes'),picture=document.getElementById('animation');
const reduced=matchMedia('(prefers-reduced-motion: reduce)');
let current=manifest.default_state,busy=false,timer;
for(const name of Object.keys(manifest.states))states.add(new Option(name,name));
for(const name of manifest.themes)themes.add(new Option(name,name));
const preferred=matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';
if(manifest.themes.includes(preferred))themes.value=preferred;
function select(name,force=false){
 if(!manifest.states[name])throw new Error('Unknown state: '+name);
 if(!force&&busy&&!manifest.states[current].interruptible){states.value=current;return false;}
 clearTimeout(timer);current=name;states.value=name;
 const state=manifest.states[name],variant=state.variants[themes.value];
 picture.src=reduced.matches?variant.reduced_motion:variant.animation;picture.alt=name;
 busy=!state.loop&&!reduced.matches;
 document.getElementById('status').textContent=name+(reduced.matches?' · reduced motion':'');
 if(busy)timer=setTimeout(()=>{busy=false;if(state.on_complete)select(state.on_complete,true);},variant.duration_ms);
 return true;
}
function send(event){const rule=manifest.transitions.find(r=>r.from===current&&r.event===event);return rule?select(rule.to):false;}
for(const event of new Set(manifest.transitions.map(r=>r.event))){const button=document.createElement('button');button.textContent=event;button.onclick=()=>send(event);document.getElementById('events').append(button);}
states.onchange=()=>select(states.value);themes.onchange=()=>select(current,true);reduced.addEventListener('change',()=>select(current,true));
window.VixlAnimation={send,select,state:()=>current};select(current,true);
</script></html>'''
