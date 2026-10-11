"""Standalone, responsive, script-free HTML using the SVG export contract."""

import base64
from html import escape


def export_html(project, **options):
    from .accessibility import document_title, page_alt, page_language
    from .svg import export_svg

    svg = export_svg(project, **options)
    texts = [
        layer.get("text", "")
        for layer in project.state["layers"]
        if layer.get("visible", True) and layer["type"] == "text"
    ]
    described = [layer["alt"] for layer in project.state["layers"] if layer.get("visible", True) and layer.get("alt")]
    heading = document_title(project.state) or (texts[0][:200] if texts else "Vixl artwork")
    summary = page_alt(project.state)
    title = escape(heading)
    alt = escape(summary or heading)
    description = escape(" · ".join(texts + described)[:4000] or "Exported Vixl design")
    lang = escape(page_language(project.state) or "en")
    uri = "data:image/svg+xml;base64," + base64.b64encode(svg).decode("ascii")
    return f'''<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'">
<title>{title}</title><style>body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#eee}}
figure{{margin:0;max-width:100%;width:fit-content}}img{{display:block;max-width:100%;height:auto}}
figcaption{{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}}</style></head>
<body><main><figure><img src="{uri}" alt="{alt}"><figcaption>{description}</figcaption></figure></main></body></html>'''.encode(
        "utf-8"
    )
