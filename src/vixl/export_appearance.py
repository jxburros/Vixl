"""Freeze dynamic balloon geometry and preserve scene compositing in vector exports."""


def prepare(project):
    from .captions import prepare_bubbles

    project = prepare_bubbles(project)
    if not project.state.get('lighting'):
        return project
    from .assets import add_image
    from .model import new_layer
    from .render import render

    image = render(project)
    candidate = project.clone()
    layer = new_layer('Composited scene', 'raster', image.width, image.height,
                      asset=add_image(candidate, image), export_fallback='scene lighting and color grading')
    candidate.state['layers'] = [layer]
    candidate.state['active_layer'] = layer['id']
    candidate.state.pop('lighting', None)
    candidate.state['selection'] = None
    candidate.state['canvas']['background'] = 'transparent'
    return candidate
