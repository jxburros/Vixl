"""Lyric videos: a song, a user-timed LRC file and a styled template become a synced MP4 or WebM."""

PLUGIN = {
    "name": "lyrics",
    "title": "Lyric videos",
    "summary": "Synced lyric videos from audio, an LRC file and a styled template document.",
    "kind": "workflows",
    "modules": ["lyrics", "workflow", "timing", "cli", "verification", "compositions"],
    "hooks": {"cli-command": ["cli:command"]},
    "workflows": ["workflow"],
    "requires": ["film", "ai"],
}
