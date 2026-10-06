import json
from xml.etree import ElementTree as ET

import pytest

from vixl import Project, VixlError


def scene():
    p = Project(480, 360, 'white')
    p.apply({'type': 'shape', 'shape': 'rectangle', 'name': 'card', 'width': 300, 'height': 240,
             'fill': '#808080'})
    return p


def test_lighting_vector_exports_report_fallback():
    p = scene()
    p.apply({'type': 'lighting', 'ambient': 0.5, 'lights': [], 'exposure': -1})
    assert p.render().getpixel((100, 100))[0] < 128
    svg = ET.fromstring(p.export(format='SVG'))
    metadata = json.loads(svg.find('{http://www.w3.org/2000/svg}metadata').text)
    assert 'lighting' in metadata['vixl']['raster_fallbacks'][0]['reason']
    with pytest.raises(VixlError, match='raster'):
        p.export(format='SVG', svg_policy='strict')
    report = {}
    assert p.export(format='PDF', report=report).startswith(b'%PDF')
    assert 'lighting' in str(report['raster_fallbacks'])
    assert p.export(format='PPTX', report=report).startswith(b'PK')
    assert 'lighting' in str(report['raster_fallbacks'])
    assert p.layer('card')['type'] == 'shape'


def test_cut_paper_is_rendered_in_vector_fallback():
    p = scene()
    p.apply({'type': 'cut-paper', 'target': 'card', 'grain': 0.2, 'roughness': 0.2})
    svg = p.export(format='SVG')
    assert b'cut-paper grain and edge texture' in svg and b'data:image/png' in svg
    report = {}
    p.export(format='PDF', report=report)
    assert report['raster_fallbacks']
