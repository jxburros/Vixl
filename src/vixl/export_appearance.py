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


def fallback_count(project):
    """Static appearance fallback estimate without building images or resolving text outlines."""
    from .svg import supported, vector_overlay

    if project.state.get("lighting"):
        return 1
    return sum(1 for layer in project.state["layers"] if layer.get("visible", True) and layer.get("opacity", 1)
               and (layer["type"] in ("raster", "pixel", "link") or layer.get("cut_paper")
                    or layer.get("export_fallback") or (layer.get("mask") or {}).get("enabled", False)
                    or not supported(layer) or not vector_overlay(layer, project.state)))
