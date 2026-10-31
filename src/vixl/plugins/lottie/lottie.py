"""Lottie at the requested frame rate, using the same vector geometry as SVG export.

Every property is sampled at every frame, then keyed natively: a span between source keyframes becomes one Bezier
key when the source easing, cut to that span, reproduces every sample; other spans keep one held key per changed
frame. Groups are full-canvas precompositions: their children already carry the ancestor transforms, and their
opacity is composited once. A linked document is one precomposition of its own vectors, sampled at the source
times it shows and played through a time remap. Unsupported geometry is an embedded image sequence, never a
frozen first frame; strict exports refuse it.
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
import numpy as np

from ...errors import require

FORMATS = ('lottie', 'json', 'tgs')
MAX_RASTER_BYTES = 128 * 1024 * 1024
MAX_SAMPLES = 250_000


class Unsupported(ValueError):
    pass


def prop(value):
    return {'a': 0, 'k': value}


LINEAR = (0.0, 0.0, 1.0, 1.0)
# Largest difference, in the property's own units (pixels, degrees, percent, 0-1 colour), between a fitted curve
# and the sampled frames. Players evaluate the same Bezier; anything further apart keeps per-frame keys.
TOLERANCE = 1e-3


def _cubic(a, b, u):
    return 3 * a * (1 - u) ** 2 * u + 3 * b * (1 - u) * u * u + u ** 3


def curve_at(curve, x):
    """Eased progress of a unit cubic Bezier at time progress ``x`` (scalar or array), as players solve it."""
    x1, y1, x2, y2 = curve
    x = np.asarray(x, dtype=float)
    low, high = np.zeros_like(x), np.ones_like(x)
    for _ in range(40):
        middle = (low + high) / 2
        below = _cubic(x1, x2, middle) < x
        low, high = np.where(below, middle, low), np.where(below, high, middle)
    return _cubic(y1, y2, (low + high) / 2)


def _parameter(curve, x):
    x1, _, x2, _ = curve
    low, high = 0.0, 1.0
    for _ in range(60):
        middle = (low + high) / 2
        low, high = (middle, high) if _cubic(x1, x2, middle) < x else (low, middle)
    return (low + high) / 2


def _split(points, u):
    def lerp(p, q):
        return (p[0] + (q[0] - p[0]) * u, p[1] + (q[1] - p[1]) * u)

    a, b, c = lerp(points[0], points[1]), lerp(points[1], points[2]), lerp(points[2], points[3])
    d, e = lerp(a, b), lerp(b, c)
    f = lerp(d, e)
    return (points[0], a, d, f), (f, e, c, points[3])


def subcurve(curve, start, end):
    """The part of a unit easing curve between time progress ``start`` and ``end``, rescaled to the unit
    square, or None when that part has no value change or would need time handles outside 0-1."""
    if end - start < 1e-9:
        return None
    if start <= 0 and end >= 1:
        return curve
    u0, u1 = _parameter(curve, max(0.0, start)), _parameter(curve, min(1.0, end))
    if u1 <= 0:
        return None
    left, _ = _split(((0.0, 0.0), curve[:2], curve[2:], (1.0, 1.0)), u1)
    _, part = _split(left, u0 / u1)
    dx, dy = part[3][0] - part[0][0], part[3][1] - part[0][1]
    if dx < 1e-12 or abs(dy) < 1e-12:
        return None
    x1, y1 = (part[1][0] - part[0][0]) / dx, (part[1][1] - part[0][1]) / dy
    x2, y2 = (part[2][0] - part[0][0]) / dx, (part[2][1] - part[0][1]) / dy
    if not (-1e-9 <= x1 <= 1 + 1e-9 and -1e-9 <= x2 <= 1 + 1e-9) or max(abs(y1), abs(y2)) > 100:
        return None
    return (min(1.0, max(0.0, x1)), y1, min(1.0, max(0.0, x2)), y2)


def numbers(value):
    if isinstance(value, dict):
        return [n for key in value for n in numbers(value[key])]
    if isinstance(value, (list, tuple)):
        return [n for item in value for n in numbers(item)]
    return [float(value)]


class Motion:
    """Where a composition's source keyframes fall among its samples, and the easing curves that can
    describe the motion between two samples: each source segment's curve, cut to that span."""

    def __init__(self, project, times, positions):
        import bisect

        self.times, self.positions = times, positions
        timeline = project.state.get('timeline') or {}
        self.tracks = [track['keys'] for track in timeline.get('tracks', []) if len(track.get('keys', [])) > 1]
        count = len(times)
        breaks = {0, count - 1}
        for keys in self.tracks:
            for key in keys:
                index = bisect.bisect_left(times, key['time'] - 1e-6)
                if index < count and abs(times[index] - key['time']) <= 1e-6:
                    breaks.add(index)
                else:
                    breaks.update((index - 1, index))
        self.breaks = sorted(n for n in breaks if 0 <= n < count)
        self.cache = {}

    def curves(self, a, b):
        import bisect

        from ...timeline import bezier_curve

        if (a, b) in self.cache:
            return self.cache[a, b]
        start, end = self.times[a], self.times[b]
        found = []
        for keys in self.tracks:
            index = bisect.bisect_right(keys, start + 1e-6, key=lambda key: key['time'])
            if not 0 < index < len(keys):
                continue
            left, right = keys[index - 1], keys[index]
            span = right['time'] - left['time']
            if span <= 0 or end > right['time'] + 1e-6:
                continue
            curve = bezier_curve(left.get('easing', 'linear'))
            part = curve and subcurve(curve, (start - left['time']) / span, (end - left['time']) / span)
            if part:
                found.append(tuple(round(v, 6) for v in part))
        self.cache[a, b] = result = list(dict.fromkeys([*found, LINEAR]))
        return result


def fit(block, progress, curves):
    """The first curve that reproduces every sample of ``block`` (samples x dimensions), or None."""
    first, change = block[0], block[-1] - block[0]
    for curve in curves:
        predicted = first + np.outer(curve_at(curve, progress), change)
        if np.max(np.abs(predicted - block)) <= TOLERANCE:
            return curve
    return None


def keyframes(values, motion, wrap):
    """Lottie keys for per-sample values: one Bezier key per span between source keyframes that the samples
    confirm, held keys elsewhere. Returns ``(keys, eased, baked)``, counting the spans of each kind."""
    positions = motion.positions
    table = np.array([numbers(value) for value in values], dtype=float)
    keys, eased, baked = [], 0, 0

    def hold(index):
        value = wrap(values[index])
        if not (keys and keys[-1].get('h') and keys[-1]['s'] == value):
            keys.append({'t': positions[index], 's': value, 'h': 1})

    breaks = motion.breaks
    for a, b in zip(breaks, breaks[1:]):
        block = table[a:b + 1]
        if np.all(block == block[0]):
            hold(a)
            continue
        curve = None
        # Two samples fit any curve, so a span needs a sample inside it before its curve is trusted.
        if b - a > 1:
            span = positions[b] - positions[a]
            progress = (np.array(positions[a:b + 1]) - positions[a]) / span
            curve = fit(block, progress, motion.curves(a, b))
        if curve:
            eased += 1
            keys.append({'t': positions[a], 's': wrap(values[a]),
                         'o': {'x': [curve[0]], 'y': [curve[1]]}, 'i': {'x': [curve[2]], 'y': [curve[3]]}})
        else:
            baked += 1
            for index in range(a, b):
                hold(index)
    last = len(values) - 1
    if keys and keys[-1].get('h') and keys[-1]['s'] == wrap(values[last]):
        pass
    else:
        keys.append({'t': positions[last], 's': wrap(values[last]), 'h': 1})
    return keys, eased, baked


def linear_keys(values, positions):
    """Keys for a piecewise-linear signal (a time remap): one linear key per straight run, held elsewhere."""
    keys = []

    def hold(index):
        if not (keys and keys[-1].get('h') and keys[-1]['s'] == [values[index]]):
            keys.append({'t': positions[index], 's': [values[index]], 'h': 1})

    a, count = 0, len(values)
    while a < count - 1:
        b = a + 1
        slope = (values[b] - values[a]) / (positions[b] - positions[a])
        while b + 1 < count and abs(values[b + 1] - values[b] - slope * (positions[b + 1] - positions[b])) <= 1e-9:
            b += 1
        if b - a > 1 and slope:
            keys.append({'t': positions[a], 's': [values[a]], 'o': {'x': [0.0], 'y': [0.0]},
                         'i': {'x': [1.0], 'y': [1.0]}})
        else:
            for index in range(a, b):
                hold(index)
        a = b
    if not (keys and keys[-1].get('h') and keys[-1]['s'] == [values[-1]]):
        keys.append({'t': positions[-1], 's': [values[-1]], 'h': 1})
    return {'a': 1, 'k': keys} if len(keys) > 1 else prop(values[0])


def wrapper(sample):
    if isinstance(sample, dict) and 'v' in sample:
        return lambda value: [value]
    return lambda value: [value] if isinstance(value, (int, float)) else value


def transform(matrix, opacity=100, anchor=(0, 0)):
    """Lottie transform for an affine matrix. The anchor, a point in the layer's own coordinates, is the
    centre of rotation and scale, so turning or scaling about it leaves the position still."""
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
    ax, ay = anchor
    px, py = a * ax + c * ay + x, b * ax + d * ay + y

    def exact(*values):
        # Matrix products leave noise such as 100.00000000000003, which would read as motion.
        values = [round(value, 9) + 0.0 for value in values]
        return prop(values if len(values) > 1 else values[0])

    return {'a': exact(ax, ay, 0), 'p': exact(px, py, 0), 's': exact(sx * 100, sy * 100, 100),
            'r': exact(math.degrees(math.atan2(b, a))), 'o': exact(opacity),
            'sk': exact(-math.degrees(math.atan(shear))), 'sa': prop(0)}


def unwrap(transforms):
    """Rotation without the jump at +-180 degrees, so a continuous turn stays one curve."""
    previous = None
    for item in transforms:
        angle = item['r']['k']
        if previous is not None:
            angle += 360 * round((previous - angle) / 360)
            item['r'] = prop(angle)
        previous = angle
    return transforms


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
    if layer['type'] not in ('shape', 'solid', 'gradient', 'text', 'group', 'pathfinder', 'link'):
        return f'{layer["type"]} layer'
    return None


# Settings that place a link's content in its box. A link exports as one composition only while they hold still.
LINK_FIXED = ('source', 'source_page', 'artboard', 'variables', 'crop', 'fit', 'position', 'width', 'height', 'time',
              'corner_pin')


class Context:
    """What the document's composition shares with the linked compositions inside it: assets, budgets,
    fallbacks and key counts."""

    def __init__(self, project, strict, cancelled):
        self.strict, self.cancelled, self.limits = strict, cancelled, project.limits
        self.native_budget = min(32 * 1024 * 1024, project.limits.max_project_bytes // 4)
        self.native_bytes = self.samples = self.image_bytes = self.next_id = 0
        self.assets, self.fallbacks, self.images, self.links = [], [], {}, {}
        self.eased = self.baked = self.instances = 0
        self.ids = 0

    def stop(self):
        from ...calls import check_cancelled

        require(not self.cancelled or not self.cancelled(), 'Timeline cancelled', 'cancelled')
        check_cancelled()

    def asset_id(self, kind):
        self.ids += 1
        return f'{kind}-{self.ids}'


class Compiler:
    """One composition: a document sampled at ``times`` (document milliseconds) and keyed at ``positions``
    (whole frames of the composition: the exported animation's frames, or a linked source's distinct times)."""

    def __init__(self, project, times, positions, fps, scale, context, *, frame_at=None, size=None, end=None,
                 background=None, progress=None, label='', drawn=None):
        from ...captions import prepare_bubbles
        from ...design_render import artboard_project
        from ...render import view_page
        from ...svg import Exporter
        from ...timeline import project_at

        self.project, self.context, self.label = project, context, label
        context.samples += len(times) * max(1, len(project.state['layers']))
        require(context.samples <= MAX_SAMPLES,
                'Lottie sample budget exceeded; reduce frame rate, duration or layer count', 'resource_limit')
        estimate = len(json.dumps(project.state, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
        require(estimate * len(times) <= context.native_budget,
                'Lottie sampled document exceeds the geometry budget; reduce frame rate, duration or complexity',
                'resource_limit')
        width, height = size or (project.state['canvas']['width'], project.state['canvas']['height'])
        self.width, self.height = [max(1, round(value * scale)) for value in (width, height)]
        project.limits.size(self.width, self.height)
        self.scale, self.times, self.positions, self.fps = scale, times, positions, fps
        self.count = len(times)
        # Samples that are frames of the output; the others sit at keyframe times between frames, so a curve can
        # start exactly where its source segment starts. Raster fallbacks draw only frames.
        self.drawn = list(range(self.count)) if drawn is None else drawn
        self.end = end if end is not None else positions[-1] + 1
        self.motion = Motion(project, times, positions)
        self.tally = [0, 0]
        if frame_at is None:
            def frame_at(time):
                return artboard_project(view_page(project_at(project, time)))
        self.frames, self.exporters = [], []
        for index, time in enumerate(times):
            context.stop()
            frame = prepare_bubbles(frame_at(time))
            if background is not None:
                frame.state['canvas']['background'] = background
            self.frames.append(frame)
            self.exporters.append(Exporter(frame, ET.Element('svg')))
            if progress:
                progress({'done': index + 1, 'total': len(times), 'phase': 'sample'})

    def next_position(self, index):
        later = [n for n in self.drawn if n > index]
        return self.positions[later[0]] if later else self.end

    def keyed(self, values):
        """``(property, eased, baked)`` for per-sample values."""
        if all(value == values[0] for value in values[1:]):
            return prop(values[0]), 0, 0
        if isinstance(values[0], dict) and 'v' in values[0]:
            if any(len(value['v']) != len(values[0]['v']) for value in values):
                raise Unsupported('changing path topology')
        keys, eased, baked = keyframes(values, self.motion, wrapper(values[0]))
        return {'a': 1, 'k': keys}, eased, baked

    def animated(self, values):
        result, eased, baked = self.keyed(values)
        self.tally[0] += eased
        self.tally[1] += baked
        return result

    def commit(self):
        self.context.eased += self.tally[0]
        self.context.baked += self.tally[1]
        self.tally = [0, 0]

    def merge(self, values):
        first = values[0]
        if isinstance(first, dict):
            if any(set(value) != set(first) for value in values):
                raise Unsupported('changing vector structure')
            if set(first) == {'a', 'k'}:
                return self.animated([value['k'] for value in values])
            return {key: self.merge([value[key] for value in values]) for key in first}
        if isinstance(first, list):
            if any(len(value) != len(first) for value in values):
                raise Unsupported('changing vector structure')
            return [self.merge([value[n] for value in values]) for n in range(len(first))]
        if any(value != first for value in values):
            raise Unsupported('changing vector structure')
        return first

    def placed(self, transforms):
        """A layer's ``ks`` from its per-sample transforms. Position splits into x and y when the two axes
        follow different curves, because players apply only one curve to a whole vector."""
        unwrap(transforms)
        points = [item.pop('p')['k'] for item in transforms]
        ks = self.merge(transforms)
        shared, eased, baked = self.keyed(points)
        if baked:
            x, x_eased, x_baked = self.keyed([[point[0]] for point in points])
            y, y_eased, y_baked = self.keyed([[point[1]] for point in points])
            if x_baked + y_baked < baked:
                shared, eased, baked = {'s': True, 'x': x, 'y': y}, x_eased + y_eased, x_baked + y_baked
        self.tally[0] += eased
        self.tally[1] += baked
        ks['p'] = shared
        return ks

    def base(self, name, kind, opacity=None):
        self.context.next_id += 1
        ks = transform(Identity)
        if opacity is not None:
            ks['o'] = self.animated(opacity)
        return {'ddd': 0, 'ind': self.context.next_id, 'ty': kind, 'nm': name, 'sr': 1, 'ks': ks,
                'ao': 0, 'ip': 0, 'op': self.end, 'st': 0, 'bm': 0}

    def raster(self, ident, reason):
        from ...assets import png_bytes
        from ...proxy import isolated
        from ...timeline import render_scaled

        context = self.context
        self.tally = [0, 0]
        name = self.label + (self.exporters[0].index[ident]['name'] if ident is not None else 'Document')
        context.fallbacks.append({'layer': name, 'reason': reason, 'animated': len(self.drawn) > 1})
        require(not context.strict, f'Lottie strict export cannot represent {name}: {reason}', 'unsupported_export',
                fallbacks=context.fallbacks)
        output = []
        for n in self.drawn:
            frame = self.frames[n]
            context.stop()
            if ident is not None:
                frame = isolated(frame, [ident])
                target = frame.layer(ident)
                while target is not None:
                    target['opacity'], target['visible'] = 1, True
                    target = frame.layer(target['parent']) if target.get('parent') else None
                frame.state['canvas']['background'] = 'transparent'
            data = png_bytes(render_scaled(frame, self.scale))
            require(len(data) <= context.limits.max_asset_bytes, 'Lottie frame exceeds the asset byte limit',
                    'resource_limit')
            digest = hashlib.sha256(data).hexdigest()
            asset_id = context.images.get(digest)
            if asset_id is None:
                asset_id = f'image-{len(context.images)}'
                context.images[digest] = asset_id
                context.image_bytes += (len(data) + 2) // 3 * 4 + 128
                require(context.image_bytes <= min(MAX_RASTER_BYTES, context.limits.max_project_bytes // 2),
                        'Lottie raster assets exceed the byte budget; reduce scale or duration',
                        'resource_limit')
                context.assets.append({'id': asset_id, 'w': self.width, 'h': self.height, 'u': '', 'e': 1,
                                       'p': 'data:image/png;base64,' + base64.b64encode(data).decode('ascii')})
            start, stop = self.positions[n], self.next_position(n)
            layer = self.base(name, 2)
            layer.update(refId=asset_id, ip=start, op=stop)
            opacity = 100
            if ident is not None:
                source = self.exporters[n].index[ident]
                opacity = source['opacity'] * 100 if source['visible'] else 0
            # Some players include a layer's out-point. An explicit zero at the next frame prevents
            # adjacent images from overlapping at that boundary in either interpretation.
            layer['ks']['o'] = {'a': 1, 'k': [{'t': start, 's': [opacity], 'h': 1},
                                             {'t': stop, 's': [0], 'h': 1}]}
            output.append(layer)
        return output

    def matrices(self, ident, layers, inner=None):
        from ...affine import layer_matrix, matrix
        from ...checks import group_matrix
        from ...render import svg_matrix

        result = []
        for exporter, layer in zip(self.exporters, layers):
            world = matrix(self.scale, 0, 0, self.scale) @ group_matrix(layer, exporter.index, exporter.bounds)
            world = world @ layer_matrix(layer, exporter.bounds[ident])
            if inner is not None:
                world = world @ inner
            result.append((svg_matrix(world), layer['opacity'] * 100 if layer['visible'] else 0))
        return result

    def layer(self, ident):
        from ...render import rest_size

        self.context.stop()
        layers = [exporter.index[ident] for exporter in self.exporters]
        first = layers[0]
        for layer in layers:
            reason = unsupported(layer)
            if reason:
                return self.raster(ident, reason)
        if first['type'] == 'link':
            return self.link(ident, layers)
        opacity = [layer['opacity'] * 100 if layer['visible'] else 0 for layer in layers]
        if first['type'] == 'group':
            children = self.exporters[0].children.get(ident, [])
            output = []
            for child in reversed(children):
                output.extend(self.layer(child['id']))
            asset_id = self.context.asset_id('comp')
            self.context.assets.append({'id': asset_id, 'w': self.width, 'h': self.height, 'layers': output})
            layer = self.base(first['name'], 0, opacity)
            layer.update(refId=asset_id, w=self.width, h=self.height)
            self.commit()
            return [layer]
        context, shapes = self.context, []
        try:
            for exporter, layer in zip(self.exporters, layers):
                context.stop()
                if layer['type'] == 'text':
                    text = layer.get('text', '')
                    if layer.get('rich'):
                        text = ''.join(span.get('text', '') for span in layer['rich'].get('spans', []))
                    require(len(text) <= 4096 and len(text) * self.count * 1024 <= context.native_budget,
                            'Lottie outlined text exceeds the geometry budget; reduce text or frame count',
                            'resource_limit')
                sample = geometry(exporter, layer, context.native_budget - context.native_bytes)
                context.native_bytes += len(json.dumps(sample, separators=(',', ':')).encode('utf-8'))
                require(context.native_bytes <= context.native_budget,
                        'Lottie geometry exceeds the byte budget; reduce frame rate, duration or complexity',
                        'resource_limit')
                shapes.append(sample)
            # The box centre is the anchor: rotation and scale about it keep the position still.
            transforms = [transform(world, alpha, [v / 2 for v in rest_size(layer)])
                          for (world, alpha), layer in zip(self.matrices(ident, layers), layers)]
            output = self.base(first['name'], 4)
            output['shapes'], output['ks'] = self.merge(shapes), self.placed(transforms)
        except Unsupported as error:
            return self.raster(ident, str(error))
        self.commit()
        return [output]

    def link(self, ident, layers):
        """A linked document as one precomposition of its own vectors, played by a time remap: offset, speed,
        trim, loop and ping-pong become straight runs of the remap instead of re-sampled copies."""
        from ...affine import matrix
        from ...links import Source, entering, link_layers, placement

        first = layers[0]
        fixed = [{key: layer.get(key) for key in LINK_FIXED} for layer in layers]
        if any(item != fixed[0] for item in fixed[1:]):
            return self.raster(ident, 'animated link placement')
        if first.get('corner_pin'):
            return self.raster(ident, 'link corner pin')
        source = Source(self.project, first)
        parent = [layer.get('_time', time) for layer, time in zip(layers, self.times)]
        mapped = [source.child_time(time) for time in parent]
        visible = [n for n, time in enumerate(mapped) if time is not None]
        if not visible:
            return []
        (dx, dy, dw, dh), (x0, y0, x1, y1), _ = placement(first, source.size)
        sx, sy = dw / (x1 - x0), dh / (y1 - y0)
        inner = matrix(sx, 0, 0, sy, dx - x0 * sx, dy - y0 * sy)
        anchor = ((x0 + x1) / 2, (y0 + y1) / 2)
        try:
            ks = self.placed([transform(world, alpha, anchor) for world, alpha in self.matrices(ident, layers, inner)])
        except Unsupported as error:
            return self.raster(ident, str(error))
        if source.timeline:
            # One whole frame per source time shown: players round a remapped frame to a whole frame, so the
            # time remap points at these indices instead of at fractional source frames.
            times = sorted({mapped[n] for n in visible})
            positions = list(range(len(times)))
            end = len(times)
        elif link_layers(source.selected.state):
            # An untimed source passes the parent's time on to its own animated links.
            times, positions, end = parent, self.positions, self.end
        else:
            times, positions, end = parent[:1], self.positions[:1], self.end
        key = (str(source.path), source.revision, first.get('source_page'), first.get('artboard'),
               json.dumps(source.values, sort_keys=True, default=str), tuple(source.stamps), tuple(times),
               tuple(positions), end)
        if key not in self.context.links:
            with entering(self.project, source.path, first['source']):
                composition = Compiler(source.selected, times, positions, self.fps, 1.0, self.context,
                                       frame_at=lambda time: source.frame(self.project, time), size=source.size,
                                       end=end, label=f'{self.label}{first["name"]} / ')
                content = composition.compose()
            asset_id = self.context.asset_id('link')
            self.context.assets.append({'id': asset_id, 'w': composition.width, 'h': composition.height,
                                        'layers': content})
            self.context.links[key] = (asset_id, composition.width, composition.height)
        asset_id, width, height = self.context.links[key]
        self.context.instances += 1
        output = self.base(first['name'], 0)
        output.update(refId=asset_id, w=width, h=height, ks=ks)
        if min(x0, y0) > 1e-6 or x1 < width - 1e-6 or y1 < height - 1e-6:
            box = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
            output['hasMask'] = True
            output['masksProperties'] = [{'nm': 'Link crop', 'mode': 'a', 'inv': False, 'o': prop(100),
                                          'x': prop(0), 'pt': prop({'v': box, 'i': [[0, 0]] * 4,
                                                                    'o': [[0, 0]] * 4, 'c': True})}]
        if source.timeline:
            index = {time: n for n, time in enumerate(times)}
            held = [index[mapped[min(max(n, visible[0]), visible[-1])]] for n in range(self.count)]
            output['tm'] = linear_keys([n / self.fps for n in held], self.positions)
        if len(visible) < self.count:
            output['ip'], output['op'] = self.positions[visible[0]], self.next_position(visible[-1])
        self.commit()
        return [output]

    def compose(self):
        from ...design import resolve_color
        from ...render import color

        whole = []
        for exporter in self.exporters:
            if exporter.project.state.get('lighting'):
                whole.append('scene lighting')
            for layer in exporter.layers:
                if layer['type'] == 'adjustment' or layer.get('clip') or layer.get('blend', 'normal') != 'normal':
                    whole.append(f'{layer["name"]}: backdrop-dependent blend, adjustment or clipping')
        if whole:
            return self.raster(None, '; '.join(dict.fromkeys(whole)))
        layers = []
        for layer in reversed(self.exporters[0].children.get(None, [])):
            layers.extend(self.layer(layer['id']))
        backgrounds = [color(resolve_color(frame.state['canvas']['background'], frame.state)) for frame in self.frames]
        if any(c[3] for c in backgrounds):
            layer = self.base('Canvas background', 4)
            layer['shapes'] = [{'ty': 'rc', 'p': prop([self.width / 2, self.height / 2]),
                                's': prop([self.width, self.height]), 'r': prop(0)},
                               {'ty': 'fl', 'c': self.animated([[v / 255 for v in c[:3]] for c in backgrounds]),
                                'o': self.animated([c[3] / 255 * 100 for c in backgrounds]), 'r': 1}]
            self.commit()
            layers.append(layer)
        return layers


def key_samples(project, times, fps):
    """Frame times plus the source keyframe times between frames, with their positions in frames and the
    indices of the real frames. Documents with more keys than frames keep only frames."""
    timeline = project.state.get('timeline') or {}
    step = 1000 / fps
    extra = sorted({key['time'] for track in timeline.get('tracks', []) for key in track.get('keys', [])
                    if times[0] < key['time'] < times[-1]
                    and abs((key['time'] - times[0]) / step - round((key['time'] - times[0]) / step)) > 1e-6})
    if len(extra) > len(times):
        extra = []
    samples = sorted([(time, n, True) for n, time in enumerate(times)] +
                     [(time, round((time - times[0]) / step, 6), False) for time in extra])
    return ([time for time, _, _ in samples], [position for _, position, _ in samples],
            [n for n, (_, _, frame) in enumerate(samples) if frame])


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
    samples, positions, drawn = key_samples(project, times, fps)
    if format == 'tgs':
        require(round(project.state['canvas']['width'] * scale) == 512 and round(project.state['canvas']['height'] * scale) == 512,
                'TGS requires a 512 x 512 canvas', 'unsupported_export')
        require(len(times) * 1000 / fps <= 3000 and fps <= 60,
                'TGS requires at most 3 seconds and 60 fps after frame quantization', 'unsupported_export')
        strict = True
    context = Context(project, strict, cancelled)
    compiler = Compiler(project, samples, positions, fps, scale, context, background=background,
                        progress=progress, drawn=drawn, end=len(times))
    context.stop()
    meta = 'eased keys where every frame confirms a source curve; per-frame held keys elsewhere'
    document = {'v': '5.7.4', 'fr': fps, 'ip': 0, 'op': len(times), 'w': compiler.width, 'h': compiler.height,
                'nm': 'Vixl animation', 'ddd': 0, 'assets': context.assets, 'layers': compiler.compose(),
                'meta': {'sampling': meta, 'fallbacks': context.fallbacks}}
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
    context.stop()
    with Path(path).open('wb' if overwrite else 'xb') as stream:
        stream.write(data)
    warnings = []
    if context.baked:
        warnings.append(f'{context.baked} motion span(s) are per-frame keys: their easing is not one Bezier curve '
                        '(bounce, elastic, spring, steps, colour mixing) or several tracks combine in one property.')
    return {'output': str(path), 'format': format, 'frames': len(times), 'fps': fps,
            'duration': len(times) * 1000 / fps, 'size': [compiler.width, compiler.height], 'bytes': len(data),
            'fallbacks': context.fallbacks, 'sampling': 'frame',
            'motion': {'eased': context.eased, 'baked': context.baked, 'instances': context.instances},
            'warnings': warnings}
