"""Explicit local desktop capture; never invoked by rendering or document loading."""
import sys
from pathlib import Path

from .errors import require, VixlError

FIELDS = {
    'output': {'type': 'string', 'description': 'Workspace-relative PNG output; no document is required.'},
    'bbox': {'type': 'array', 'items': {'type': 'integer'}, 'minItems': 4, 'maxItems': 4,
             'description': 'Optional desktop pixel rectangle [left, top, right, bottom], including negative monitor coordinates.'},
    'window': {'type': 'integer', 'minimum': 1, 'description': 'Optional Windows HWND (MainWindowHandle); mutually exclusive with bbox.'},
    'all_screens': {'type': 'boolean', 'description': 'Capture all Windows monitors; default false.'},
    'overwrite': {'type': 'boolean', 'description': 'Replace an existing output PNG; default false.'},
}


def capture(session, request):
    from PIL import ImageGrab
    from .assets import png_bytes
    from .production import write_bytes
    path = session.resolve(request['output'])
    require(Path(path).suffix.lower() == '.png', 'Screen capture output must be PNG', field='output')
    for key in ('all_screens', 'overwrite'):
        require(type(request.get(key, False)) is bool, f'{key} must be boolean', field=key)
    require(request.get('overwrite') or not Path(path).exists(), f'Output already exists: {path}', 'output_exists')
    options = {'all_screens': request.get('all_screens', False)}
    require(not ('bbox' in request and 'window' in request), 'Use bbox or window, not both')
    if 'bbox' in request:
        box = request['bbox']
        require(isinstance(box, list) and len(box) == 4 and all(type(x) is int for x in box),
                'bbox must contain four integers', field='bbox')
        session.limits.size(box[2] - box[0], box[3] - box[1])
        options['bbox'] = tuple(box)
    if 'window' in request:
        require(sys.platform == 'win32', 'Window handle capture is available on Windows', 'unsupported_platform')
        require(type(request['window']) is int and request['window'] > 0, 'window must be a positive HWND', field='window')
        options['window'] = request['window']
    try:
        image = ImageGrab.grab(**options)
    except (OSError, RuntimeError, ValueError) as exc:
        raise VixlError('capture_unavailable', 'Desktop capture failed. Run in an interactive desktop session and '
                        'grant screen-recording permission if required by your operating system.', reason=str(exc)) from exc
    session.limits.size(*image.size)
    write_bytes(path, png_bytes(image.convert('RGBA')), replace=request.get('overwrite', False))
    return {'output': str(path), 'width': image.width, 'height': image.height,
            'source': 'window' if 'window' in request else 'screen'}
