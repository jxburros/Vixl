"""Promo templates must survive creation, resizing, editing and persistence."""
import pytest

from vixl import Project
from vixl.promo_templates import FORMATS, TREATMENTS, builtins
from vixl.resources import catalog, create_template, validate
from vixl.timeline import project_at, seam_findings

COPY = {'title': 'Ideas become editable.', 'subtitle': 'Your agent makes it. You keep the layers.', 'cta': 'Make it with Vixl'}


@pytest.mark.parametrize('name', list(builtins()))
def test_promo_template_public_creation_and_loop(name, tmp_path):
    item = catalog('templates')[name]
    validate('templates', item)
    p = create_template(name, COPY, seed=42)
    assert (p.state["canvas"]["width"], p.state["canvas"]["height"]) == (item['width'], item['height'])
    assert p.state['timeline']['duration'] == 6000
    assert not seam_findings(p)
    frame = project_at(p, 2500)
    assert frame.check(checks=['bounds'])['passed']
    assert frame.render().tobytes() != project_at(p, 0).render().tobytes()
    assert project_at(p, 0).render().tobytes() == project_at(p, 6000).render().tobytes()
    p.apply({'type': 'text-set', 'target': 'promo-title', 'text': 'Still editable'})
    path = tmp_path / 'promo.vixl'
    p.save(path)
    assert Project.load(path).layer('promo-title')['text'] == 'Still editable'


@pytest.mark.parametrize('style', list(TREATMENTS))
def test_promo_scales_down_and_reproduces(style):
    name = f'video-promo-{style}'
    p = Project(540, 540)
    p.apply({'type': 'template-apply', 'name': name, 'variables': COPY, 'seed': 42})
    assert project_at(p, 2500).check(checks=['bounds'])['passed']
    assert p.layer('promo-title')['size'] <= 65
    assert p.layer('promo-cta')['size'] <= 18
    a = create_template(name, COPY, seed=42)
    b = create_template(name, COPY, seed=42)
    assert project_at(a, 2500).render().tobytes() == project_at(b, 2500).render().tobytes()


def test_promo_library_has_distinct_compositions():
    items = builtins()
    assert len(items) == len(FORMATS) * len(TREATMENTS)
    images = [project_at(create_template(f'video-promo-{style}', COPY, seed=42), 2500).render().tobytes()
              for style in TREATMENTS]
    assert len(set(images)) == len(TREATMENTS)
