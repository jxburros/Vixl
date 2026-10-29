"""Lottie at the requested frame rate, using the same vector geometry as SVG export.

Properties are sampled at frame instants, including non-Bezier easings and constraints. Groups are full-canvas
precompositions: their children already carry the ancestor transforms, and their opacity is composited once.
Unsupported geometry is an embedded image sequence, never a frozen first frame; strict exports refuse it.
"""

import base64
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

from fontTools.misc.transform import Identity

from ...errors import require

FORMATS = ('lottie', 'json', 'tgs')
MAX_RASTER_BYTES = 128 * 1024 * 1024
MAX_SAMPLES = 250_000


class Unsupported(ValueError):
    pass


def prop(value):
    return {'a': 0, 'k': value}


def animated(values):
    if all(value == values[0] for value in values[1:]):
        return prop(values[0])
    if isinstance(values[0], dict) and 'v' in values[0]:
        if any(len(value['v']) != len(values[0]['v']) for value in values):
            raise Unsupported('changing path topology')
        wrapped = [[value] for value in values]
    else:
        wrapped = [[value] if isinstance(value, (int, float)) else value for value in values]
    keys = [{'t': n, 's': value, 'h': 1} for n, value in enumerate(wrapped)
            if not n or value != wrapped[n - 1]]
    return {'a': 1, 'k': keys}


def merge(values):
    first = values[0]
    if isinstance(first, dict):
        if any(set(value) != set(first) for value in values):
            raise Unsupported('changing vector structure')
        if set(first) == {'a', 'k'}:
            return animated([value['k'] for value in values])
        return {key: merge([value[key] for value in values]) for key in first}
    if isinstance(first, list):
        if any(len(value) != len(first) for value in values):
            raise Unsupported('changing vector structure')
        return [merge([value[n] for value in values]) for n in range(len(first))]
    if any(value != first for value in values):
        raise Unsupported('changing vector structure')
    return first


def transform(matrix, opacity=100):
    a, b, c, d, x, y = matrix
    sx = math.hypot(a, b)
    if sx < 1e-9:
        raise Unsupported('singular affine transform')
    sy = (a * d - b * c) / sx
    if abs(sy) < 1e-9:
        raise Unsupported('singular affine transform')
    shear = (a * c + b * d) / (sx * sy)
    if abs(shear) > 1e-7:
        raise Unsupported('affine shear')
    return {'a': prop([0, 0, 0]), 'p': prop([x, y, 0]), 's': prop([sx * 100, sy * 100, 100]),
            'r': prop(math.degrees(math.atan2(b, a))), 'o': prop(opacity),
            'sk': prop(-math.degrees(math.atan(shear))), 'sa': prop(0)}


def paths(data, matrix=Identity):
    from ...geometry import parse_path

    result, current = [], None

    def point(value):
        return [round(v, 6) for v in matrix.transformPoint(value)]

    def finish(closed=False):
        if current and current['v']:
            current['c'] = closed
            result.append({'ty': 'sh', 'ks': prop(current)})

    for command, coords in parse_path(data):
        if command == 'M':
            finish()
            current = {'v': [point(coords)], 'i': [[0, 0]], 'o': [[0, 0]], 'c': False}
        elif command in ('L', 'C', 'Q'):
            end = point(coords[-2:])
            before = current['v'][-1]
            incoming = [0, 0]
            if command in ('C', 'Q'):
                first = point(coords[:2])
                last = point(coords[2:4]) if command == 'C' else first
                factor = 1 if command == 'C' else 2 / 3
                current['o'][-1] = [(v - old) * factor for v, old in zip(first, before)]
                incoming = [(v - old) * factor for v, old in zip(last, end)]
            current['v'].append(end)
            current['i'].append(incoming)
            current['o'].append([0, 0])
        elif command == 'Z':
            if len(current['v']) > 1 and current['v'][-1] == current['v'][0]:
                current['i'][0] = current['i'].pop()
                current['v'].pop()
                current['o'].pop()
            finish(True)
            current = None
    finish()
    return result


def primitive(element):
    tag, a = element.tag.rsplit('}', 1)[-1], element.attrib
    def number(key, default=0):
        return float(a.get(key, default))
    if tag == 'path':
        return a['d']
    if tag == 'line':
        return f'M{number("x1")} {number("y1")} L{number("x2")} {number("y2")}'
    if tag == 'rect':
        x, y, w, h = (number(key) for key in ('x', 'y', 'width', 'height'))
        rx, ry = min(w / 2, number('rx')), min(h / 2, number('ry', number('rx')))
        if not rx or not ry:
            return f'M{x} {y} h{w} v{h} h{-w} Z'
        return (f'M{x + rx} {y} H{x + w - rx} A{rx} {ry} 0 0 1 {x + w} {y + ry} '
                f'V{y + h - ry} A{rx} {ry} 0 0 1 {x + w - rx} {y + h} H{x + rx} '
                f'A{rx} {ry} 0 0 1 {x} {y + h - ry} V{y + ry} A{rx} {ry} 0 0 1 {x + rx} {y} Z')
    if tag in ('ellipse', 'circle'):
        x, y = number('cx'), number('cy')
        rx, ry = number('rx', number('r')), number('ry', number('r'))
        return f'M{x - rx} {y} A{rx} {ry} 0 1 0 {x + rx} {y} A{rx} {ry} 0 1 0 {x - rx} {y} Z'
    raise Unsupported(f'SVG {tag} geometry')


def paint(value, opacity, defs, matrix, stroke=False):
    from ...render import color
    from ...imports import transform as svg_transform

    if value in ('none', 'transparent') or opacity == 0:
        return None
    match = re.fullmatch(r'url\(#([^()]+)\)', value)
    if not match:
        rgba = color(value)
        return {'ty': 'st' if stroke else 'fl', 'c': prop([v / 255 for v in rgba[:3]]),
                'o': prop(opacity * rgba[3] / 255 * 100), **({} if stroke else {'r': 1})}
    gradient = defs[match[1]]
    settings = gradient.attrib
    t = matrix.transform(svg_transform(settings.get('gradientTransform', '')))
    stops = list(gradient)
    values, alphas = [], []
    for stop in stops:
        offset = float(stop.get('offset'))
        rgba = color(stop.get('stop-color'))
        values += [offset, *(v / 255 for v in rgba[:3])]
        alphas += [offset, float(stop.get('stop-opacity', 1)) * rgba[3] / 255]
    if gradient.tag.endswith('linearGradient'):
        first = t.transformPoint((float(settings['x1']), float(settings['y1'])))
        last = t.transformPoint((float(settings['x2']), float(settings['y2'])))
        kind = 1
    else:
        # Lottie radial fills are circular in shape coordinates. Elliptical gradients need their own matrix.
        a, b, c, d, _, _ = t
        if abs(math.hypot(a, b) - math.hypot(c, d)) > 1e-6 or abs(a * c + b * d) > 1e-6:
            raise Unsupported('elliptical radial gradient')
        first = t.transformPoint((float(settings.get('cx', 0)), float(settings.get('cy', 0))))
        last = t.transformPoint((float(settings.get('cx', 0)) + float(settings.get('r', 1)),
                                 float(settings.get('cy', 0))))
        kind = 2
    return {'ty': 'gs' if stroke else 'gf', 't': kind, 'g': {'p': len(stops), 'k': prop(values + alphas)},
            's': prop(list(first)), 'e': prop(list(last)), 'o': prop(opacity * 100),
            **({} if stroke else {'r': 1})}


def geometry(exporter, layer, budget=32 * 1024 * 1024):
    from ...imports import transform as svg_transform

    root = ET.Element('g')
    if not exporter.geometry(root, layer):
        raise Unsupported(f'{layer["type"]} layer')
    defs = {element.get('id'): element for element in exporter.defs}
    shapes = []
    used = 0

    def walk(element, matrix=Identity, inherited=None, clips=()):
        nonlocal used
        tag = element.tag.rsplit('}', 1)[-1]
        attrs = {**(inherited or {}), **element.attrib}
        t = matrix.transform(svg_transform(element.get('transform', '')))
        alpha = float((inherited or {}).get('opacity', 1)) * float(element.get('opacity', 1))
        attrs['opacity'] = alpha
        if tag == 'svg':
            view = [float(v) for v in element.get('viewBox').split()]
            t = t.translate(float(element.get('x', 0)), float(element.get('y', 0))).scale(
                float(element.get('width')) / view[2], float(element.get('height')) / view[3]).translate(-view[0], -view[1])
            if element.get('overflow', 'hidden') != 'visible':
                first = t.transformPoint(view[:2])
                last = t.transformPoint((view[0] + view[2], view[1] + view[3]))
                clips = (*clips, (*first, *last))
        if tag in ('svg', 'g'):
            for child in element:
                walk(child, t, attrs, clips)
            return
        if tag in ('title', 'desc'):
            return
        data = primitive(element)
        if clips:
            from fontTools.pens.boundsPen import BoundsPen
            from fontTools.pens.transformPen import TransformPen
            from fontTools.svgLib.path import parse_path

            pen = BoundsPen(None)
            parse_path(data, TransformPen(pen, t))
            if pen.bounds and any(pen.bounds[0] < clip[0] - 1e-5 or pen.bounds[1] < clip[1] - 1e-5 or
                                  pen.bounds[2] > clip[2] + 1e-5 or pen.bounds[3] > clip[3] + 1e-5 for clip in clips):
                raise Unsupported('clipped vector geometry')
        items = paths(data, t)
        fill = paint(attrs.get('fill', 'black'), alpha * float(attrs.get('fill-opacity', 1)), defs, t)
        if fill:
            fill['r'] = 2 if attrs.get('fill-rule') == 'evenodd' else 1
        stroke = paint(attrs.get('stroke', 'none'), alpha * float(attrs.get('stroke-opacity', 1)), defs, t, True)
        if stroke:
            a, b, c, d, _, _ = t
            if abs(math.hypot(a, b) - math.hypot(c, d)) > 1e-6 or abs(a * c + b * d) > 1e-6:
                raise Unsupported('nonuniform transformed stroke')
            scale = math.hypot(a, b)
            stroke.update(w=prop(float(attrs.get('stroke-width', 1)) * scale),
                          lc={'butt': 1, 'round': 2, 'square': 3}.get(attrs.get('stroke-linecap'), 1),
                          lj={'miter': 1, 'round': 2, 'bevel': 3}.get(attrs.get('stroke-linejoin'), 1),
                          ml=float(attrs.get('stroke-miterlimit', 4)))
            dash = attrs.get('stroke-dasharray')
            if dash and dash != 'none':
                numbers = [float(v) for v in re.split('[ ,]+', dash.strip())]
                stroke['d'] = [{'n': 'd' if n % 2 == 0 else 'g', 'v': prop(v * scale)} for n, v in enumerate(numbers)]
                stroke['d'].append({'n': 'o', 'v': prop(float(attrs.get('stroke-dashoffset', 0)) * scale)})
        paints = [stroke, fill] if attrs.get('paint-order') == 'stroke fill' else [fill, stroke]
        items += [item for item in reversed(paints) if item]
        group = {'ty': 'gr', 'it': items + [{'ty': 'tr', **transform(Identity)}]}
        used += len(json.dumps(group, separators=(',', ':')).encode('utf-8'))
        require(used <= budget, 'Lottie geometry exceeds the byte budget; reduce text, paths or frame count',
                'resource_limit')
        shapes.append(group)

    walk(root)
    return list(reversed(shapes))


def unsupported(layer):
    for key in ('mask', 'repeat', 'cut_paper', 'export_fallback', '_kinetic'):
        if layer.get(key):
            return f'{key} appearance'
    if any(effect.get('enabled', True) for effect in layer.get('effects', [])):
        return 'layer effects'
    if any(style.get('enabled', True) for style in layer.get('styles', {}).values()):
        return 'layer styles'
    if layer['type'] not in ('shape', 'solid', 'gradient', 'text', 'group', 'pathfinder'):
        return f'{layer["type"]} layer'
    return None


class Compiler:
    def __init__(self, project, times, fps, scale, background, strict, cancelled, progress):
        from ...calls import check_cancelled
        from ...captions import prepare_bubbles
        from ...design_render import artboard_project
        from ...render import view_page
        from ...svg import Exporter
        from ...timeline import project_at

        require(len(times) * max(1, len(project.state['layers'])) <= MAX_SAMPLES,
                'Lottie sample budget exceeded; reduce frame rate, duration or layer count', 'resource_limit')
        self.limits = project.limits
        self.native_budget = min(32 * 1024 * 1024, project.limits.max_project_bytes // 4)
        estimate = len(json.dumps(project.state, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
        require(estimate * len(times) <= self.native_budget,
                'Lottie sampled document exceeds the geometry budget; reduce frame rate, duration or complexity',
                'resource_limit')
        self.native_bytes = 0
        self.width, self.height = [max(1, round(project.state['canvas'][key] * scale)) for key in ('width', 'height')]
        project.limits.size(self.width, self.height)
        self.scale, self.times, self.fps = scale, times, fps
        self.strict, self.assets, self.fallbacks = strict, [], []
        self.frames, self.exporters = [], []
        self.images, self.image_bytes, self.next_id = {}, 0, 0
        for index, time in enumerate(times):
            require(not cancelled or not cancelled(), 'Timeline cancelled', 'cancelled')
            check_cancelled()
            frame = prepare_bubbles(artboard_project(view_page(project_at(project, time))))
            if background is not None:
                frame.state['canvas']['background'] = background
            self.frames.append(frame)
            self.exporters.append(Exporter(frame, ET.Element('svg')))
            if progress:
                progress({'done': index + 1, 'total': len(times), 'phase': 'sample'})
        self.count = len(times)
        self.cancelled = cancelled

    def stop(self):
        from ...calls import check_cancelled

        require(not self.cancelled or not self.cancelled(), 'Timeline cancelled', 'cancelled')
        check_cancelled()

    def base(self, name, kind, opacity=None):
        self.next_id += 1
        ks = transform(Identity)
        if opacity is not None:
            ks['o'] = animated(opacity)
        return {'ddd': 0, 'ind': self.next_id, 'ty': kind, 'nm': name, 'sr': 1, 'ks': ks,
                'ao': 0, 'ip': 0, 'op': self.count, 'st': 0, 'bm': 0}

    def raster(self, ident, reason):
        from ...assets import png_bytes
        from ...calls import check_cancelled
        from ...proxy import isolated
        from ...timeline import render_scaled

        name = self.exporters[0].index[ident]['name'] if ident is not None else 'Document'
        self.fallbacks.append({'layer': name, 'reason': reason, 'animated': self.count > 1})
        require(not self.strict, f'Lottie strict export cannot represent {name}: {reason}', 'unsupported_export',
                fallbacks=self.fallbacks)
        output = []
        for n, frame in enumerate(self.frames):
            require(not self.cancelled or not self.cancelled(), 'Timeline cancelled', 'cancelled')
            check_cancelled()
            if ident is not None:
                frame = isolated(frame, [ident])
                target = frame.layer(ident)
                while target is not None:
                    target['opacity'], target['visible'] = 1, True
                    target = frame.layer(target['parent']) if target.get('parent') else None
                frame.state['canvas']['background'] = 'transparent'
            data = png_bytes(render_scaled(frame, self.scale))
            require(len(data) <= self.limits.max_asset_bytes, 'Lottie frame exceeds the asset byte limit', 'resource_limit')
            digest = hashlib.sha256(data).hexdigest()
            asset_id = self.images.get(digest)
            if asset_id is None:
                asset_id = f'image-{len(self.images)}'
                self.images[digest] = asset_id
                self.image_bytes += (len(data) + 2) // 3 * 4 + 128
                require(self.image_bytes <= min(MAX_RASTER_BYTES, self.limits.max_project_bytes // 2),
                        'Lottie raster assets exceed the byte budget; reduce scale or duration',
                        'resource_limit')
                self.assets.append({'id': asset_id, 'w': self.width, 'h': self.height, 'u': '', 'e': 1,
                                    'p': 'data:image/png;base64,' + base64.b64encode(data).decode('ascii')})
            layer = self.base(name, 2)
            layer.update(refId=asset_id, ip=n, op=n + 1)
            opacity = 100
            if ident is not None:
                source = self.exporters[n].index[ident]
                opacity = source['opacity'] * 100 if source['visible'] else 0
            # Some players include a layer's out-point. An explicit zero at the next frame prevents
            # adjacent images from overlapping at that boundary in either interpretation.
            layer['ks']['o'] = {'a': 1, 'k': [{'t': n, 's': [opacity], 'h': 1},
                                             {'t': n + 1, 's': [0], 'h': 1}]}
            output.append(layer)
        return output

    def layer(self, ident):
        self.stop()
        layers = [exporter.index[ident] for exporter in self.exporters]
        first = layers[0]
        for layer in layers:
            reason = unsupported(layer)
            if reason:
                return self.raster(ident, reason)
        opacity = [layer['opacity'] * 100 if layer['visible'] else 0 for layer in layers]
        if first['type'] == 'group':
            children = self.exporters[0].children.get(ident, [])
            output = []
            for child in reversed(children):
                output.extend(self.layer(child['id']))
            asset_id = f'comp-{ident}'
            self.assets.append({'id': asset_id, 'w': self.width, 'h': self.height, 'layers': output})
            layer = self.base(first['name'], 0, opacity)
            layer.update(refId=asset_id, w=self.width, h=self.height)
            return [layer]
        from ...affine import layer_matrix, matrix
        from ...checks import group_matrix
        from ...render import svg_matrix

        shapes, transforms = [], []
        try:
            for exporter, layer in zip(self.exporters, layers):
                self.stop()
                if layer['type'] == 'text':
                    text = layer.get('text', '')
                    if layer.get('rich'):
                        text = ''.join(span.get('text', '') for span in layer['rich'].get('spans', []))
                    require(len(text) <= 4096 and len(text) * self.count * 1024 <= self.native_budget,
                            'Lottie outlined text exceeds the geometry budget; reduce text or frame count',
                            'resource_limit')
                sample = geometry(exporter, layer, self.native_budget - self.native_bytes)
                self.native_bytes += len(json.dumps(sample, separators=(',', ':')).encode('utf-8'))
                require(self.native_bytes <= self.native_budget,
                        'Lottie geometry exceeds the byte budget; reduce frame rate, duration or complexity',
                        'resource_limit')
                shapes.append(sample)
                world = matrix(self.scale, 0, 0, self.scale) @ group_matrix(layer, exporter.index, exporter.bounds)
                world = world @ layer_matrix(layer, exporter.bounds[ident])
                transforms.append(transform(svg_matrix(world), layer['opacity'] * 100 if layer['visible'] else 0))
            output = self.base(first['name'], 4)
            output['shapes'], output['ks'] = merge(shapes), merge(transforms)
        except Unsupported as error:
            return self.raster(ident, str(error))
        return [output]

    def document(self):
        from ...render import color
        from ...design import resolve_color

        whole = []
        for exporter in self.exporters:
            if exporter.project.state.get('lighting'):
                whole.append('scene lighting')
            for layer in exporter.layers:
                if layer['type'] == 'adjustment' or layer.get('clip') or layer.get('blend', 'normal') != 'normal':
                    whole.append(f'{layer["name"]}: backdrop-dependent blend, adjustment or clipping')
        if whole:
            layers = self.raster(None, '; '.join(dict.fromkeys(whole)))
        else:
            layers = []
            for layer in reversed(self.exporters[0].children.get(None, [])):
                layers.extend(self.layer(layer['id']))
            backgrounds = [color(resolve_color(frame.state['canvas']['background'], frame.state)) for frame in self.frames]
            if any(c[3] for c in backgrounds):
                layer = self.base('Canvas background', 4)
                layer['shapes'] = [{'ty': 'rc', 'p': prop([self.width / 2, self.height / 2]),
                                    's': prop([self.width, self.height]), 'r': prop(0)},
                                   {'ty': 'fl', 'c': animated([[v / 255 for v in c[:3]] for c in backgrounds]),
                                    'o': animated([c[3] / 255 * 100 for c in backgrounds]), 'r': 1}]
                layers.append(layer)
        return {'v': '5.7.4', 'fr': self.fps, 'ip': 0, 'op': self.count, 'w': self.width, 'h': self.height,
                'nm': 'Vixl animation', 'ddd': 0, 'assets': self.assets, 'layers': layers,
                'meta': {'sampling': 'one held key per changed frame; source easing and instance timing are baked',
                         'fallbacks': self.fallbacks}}


def export(project, path, format, *, fps=None, scale=1.0, start=None, end=None, background=None, strict=False,
           overwrite=False, cancelled=None, progress=None, **options):
    suffix = Path(path).suffix.lower()
    inferred = {'.json': 'json', '.lottie': 'lottie', '.tgs': 'tgs'}.get(suffix)
    format = format or inferred
    if format not in FORMATS:
        return None
    from ...model import finite
    from ...timeline import default_timeline, frame_times, parse_time

    require(suffix == {'json': '.json', 'lottie': '.lottie', 'tgs': '.tgs'}[format],
            f'Use a .{format} filename for {format}', field='format')
    require(isinstance(strict, bool), 'strict must be a boolean', field='strict')
    require(overwrite or not Path(path).exists(), 'Animation output already exists')
    # These change raster encoding or frame ordering and have no equivalent in interchange.
    defaults = {'columns': None, 'quality': 90, 'colors': 256, 'preview': False, 'dither': 'auto',
                'max_bytes': None, 'poster': None, 'sample_rate': None, 'target_bytes': None, 'preset': None}
    for key, default in defaults.items():
        require(options.get(key, default) == default, f'{key} does not apply to Lottie exports', field=key)
    require(not project.state.get('audio_tracks'), 'Lottie export cannot embed audio tracks', 'unsupported_export')
    finite(scale, 'scale', 0.05, 16)
    settings = project.state.get('timeline') or default_timeline()
    first = parse_time(start, settings['duration'], settings.get('markers')) if start is not None else 0
    last = parse_time(end, settings['duration'], settings.get('markers')) if end is not None else settings['duration']
    times, fps = frame_times(project, fps, first, last)
    if format == 'tgs':
        require(round(project.state['canvas']['width'] * scale) == 512 and round(project.state['canvas']['height'] * scale) == 512,
                'TGS requires a 512 x 512 canvas', 'unsupported_export')
        require(len(times) * 1000 / fps <= 3000 and fps <= 60,
                'TGS requires at most 3 seconds and 60 fps after frame quantization', 'unsupported_export')
        strict = True
    compiler = Compiler(project, times, fps, scale, background, strict, cancelled, progress)
    compiler.stop()
    document = compiler.document()
    if format == 'tgs':
        document['tgs'] = 1
    data = json.dumps(document, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
    require(len(data) <= project.limits.max_project_bytes, 'Lottie output exceeds the project byte limit', 'resource_limit')
    if format == 'lottie':
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, value in [('manifest.json', json.dumps({'version': '1.0', 'animations': [{'id': 'animation'}]}).encode()),
                                ('animations/animation.json', data)]:
                entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, value)
        data = buffer.getvalue()
    elif format == 'tgs':
        data = gzip.compress(data, mtime=0)
        require(len(data) <= 65536, 'TGS exceeds the 64 KiB limit; simplify the animation', 'resource_limit')
    compiler.stop()
    with Path(path).open('wb' if overwrite else 'xb') as stream:
        stream.write(data)
    return {'output': str(path), 'format': format, 'frames': len(times), 'fps': fps,
            'duration': len(times) * 1000 / fps, 'size': [compiler.width, compiler.height], 'bytes': len(data),
            'fallbacks': compiler.fallbacks, 'sampling': 'frame',
            'warnings': ['Motion is sampled at export fps; original easing curves and nested time maps are baked.']}
