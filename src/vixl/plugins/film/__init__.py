"""Film: scene and shot assembly with camera motion, captions, transitions and audio, plus media analysis."""

PLUGIN = {
    "name": "film",
    "title": "Film",
    "summary": "Assemble scenes and shots into MP4, WebM, GIF or WebP films; sample video and analyze audio.",
    "kind": "workflows",
    "modules": ["film", "media_analysis", "workflow"],
    "workflows": ["workflow"],
}
