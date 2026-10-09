import json

from PIL import Image
import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.interfaces import Session
from vixl.workflows import dispatch


def source(tmp_path):
    p = Project(80, 80, 'transparent')
    p.apply([{'type': 'variable', 'name': 'ink', 'value': '#111111'},
             {'type': 'shape', 'name': 'dot', 'shape': 'ellipse', 'fill': '${ink}', 'x': 20, 'y': 20, 'width': 20, 'height': 20},
             {'type': 'timeline-set', 'duration': 400, 'fps': 5},
             {'type': 'animate-preset', 'target': 'dot', 'preset': 'pulse', 'duration': 400}])
    p.save(tmp_path / 'dot.vixl')


def request():
    return {'states': {name: {'source': 'dot.vixl', **({'loop': False, 'on_complete': 'waiting', 'interruptible': False}
                      if name in ('success', 'error') else {})} for name in ('thinking', 'waiting', 'success', 'error')},
            'default_state': 'waiting', 'themes': {'light': {'ink': '#111111'}, 'dark': {'ink': '#eeeeee'}},
            'transitions': [{'from': 'waiting', 'event': 'start', 'to': 'thinking'},
                            {'from': 'thinking', 'event': 'done', 'to': 'success'}], 'output': 'bundle'}


def test_four_state_theme_and_reduced_motion_package(tmp_path):
    source(tmp_path)
    original = (tmp_path / 'dot.vixl').read_bytes()
    result = dispatch(Session(workspace=tmp_path), 'app-animation-package', request())
    assert result['variants'] == 8
    manifest = json.loads((tmp_path / 'bundle/manifest.json').read_text())
    assert manifest['version'] == 1 and manifest['default_state'] == 'waiting'
    for state in manifest['states'].values():
        assert Project.load(tmp_path / 'bundle' / state['master']).state['timeline']['tracks']
        for variant in state['variants'].values():
            for key in ('animation', 'poster', 'reduced_motion'):
                path = tmp_path / 'bundle' / variant[key]
                assert path.resolve().is_relative_to((tmp_path / 'bundle').resolve()) and path.is_file()
                assert Image.open(path).size == (80, 80)
    light = Image.open(tmp_path / 'bundle/assets/waiting/light-reduced.png')
    dark = Image.open(tmp_path / 'bundle/assets/waiting/dark-reduced.png')
    assert light.tobytes() != dark.tobytes()
    assert (tmp_path / 'dot.vixl').read_bytes() == original
    consumer = (tmp_path / 'bundle/index.html').read_text()
    assert 'prefers-reduced-motion' in consumer and 'interruptible' in consumer and 'VixlAnimation' in consumer
    with pytest.raises(VixlError):
        dispatch(Session(workspace=tmp_path), 'app-animation-package', request())


@pytest.mark.parametrize('change', ['missing-default', 'missing-source', 'bad-transition', 'completion-loop'])
def test_invalid_packages_fail_without_partial_output(tmp_path, change):
    source(tmp_path)
    spec = request()
    if change == 'missing-default':
        spec['default_state'] = 'missing'
    elif change == 'missing-source':
        spec['states']['waiting']['source'] = 'missing.vixl'
    elif change == 'bad-transition':
        spec['transitions'][0]['to'] = 'missing'
    else:
        spec['states']['waiting']['on_complete'] = 'thinking'
    with pytest.raises((VixlError, FileNotFoundError)):
        dispatch(Session(workspace=tmp_path), 'app-animation-package', spec)
    assert not (tmp_path / 'bundle').exists()


def test_sample_consumer_obeys_transitions_and_reduced_motion(tmp_path):
    import re
    import shutil
    import subprocess
    from vixl.app_animation import CONSUMER
    if not shutil.which('node'):
        pytest.skip('Node is unavailable for the browser-consumer logic test')
    def state(loop=True):
        return {'loop': loop, 'interruptible': loop, 'on_complete': None if loop else 'waiting',
                               'variants': {theme: {'animation': theme + '.webp', 'reduced_motion': theme + '.png',
                                                    'duration_ms': 400} for theme in ('light', 'dark')}}
    manifest = {'default_state': 'waiting', 'themes': ['light', 'dark'],
                'states': {'waiting': state(), 'thinking': state(), 'success': state(False)},
                'transitions': [{'from': 'waiting', 'event': 'start', 'to': 'thinking'},
                                {'from': 'thinking', 'event': 'done', 'to': 'success'}]}
    script = re.search(r'</script><script>(.*?)</script>', CONSUMER, re.S)[1]
    setup = '''
const assert=require('node:assert/strict');
const nodes={};let finish,reduce=false;
function node(id){return nodes[id]??=( {value:'',textContent:'',add(o){if(!this.value)this.value=o.value;},append(){}} );}
global.document={getElementById:node,createElement:()=>({})};
global.Option=function(name,value){this.value=value;};global.window={};
global.matchMedia=(q)=>q.includes('reduced')?{get matches(){return reduce;},addEventListener(){}}:{matches:false};
global.setTimeout=(f)=>{finish=f;return 1;};global.clearTimeout=()=>{};
'''
    setup += 'node("manifest").textContent=' + json.dumps(json.dumps(manifest)) + ';\n'
    assertions = '''
assert.equal(window.VixlAnimation.state(),'waiting');
assert.equal(window.VixlAnimation.send('start'),true);
assert.equal(window.VixlAnimation.send('done'),true);
assert.equal(window.VixlAnimation.select('waiting'),false);
finish();assert.equal(window.VixlAnimation.state(),'waiting');
reduce=true;node('themes').value='dark';window.VixlAnimation.select('thinking',true);
assert.equal(node('animation').src,'dark.png');
'''
    path = tmp_path / 'consumer.cjs'
    path.write_text(setup + script + assertions)
    subprocess.run(['node', str(path)], check=True, capture_output=True, text=True)
