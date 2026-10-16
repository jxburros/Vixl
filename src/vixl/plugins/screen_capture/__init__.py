"""Screen capture: an explicit local desktop, region or window capture to PNG."""

PLUGIN = {
    "name": "screen_capture",
    "title": "Screen capture",
    "summary": "Capture the local desktop, a pixel rectangle or a Windows window to a PNG, only when asked.",
    "kind": "workflows",
    "modules": ["screen_capture", "workflow"],
    "workflows": ["workflow"],
}
