"""Persistent, bounded document review notes shared by the viewer and agents."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .assets import read_bounded
from .errors import require
from .fileio import file_lock, temporary


def notes(path, action="list", *, text=None, note_id=None):
    require(action in ("list", "add", "resolve"), "Use list, add or resolve", field="action")
    path = Path(str(path) + ".notes.json")
    require(not path.is_symlink(), "Review notes may not be a symbolic link", "forbidden")
    with file_lock(path):
        entries = json.loads(read_bounded(path, 1_048_576)) if path.exists() else []
        if action == "add":
            require(
                isinstance(text, str) and 0 < len(text.strip()) <= 4000,
                "Note must contain 1–4000 characters",
                field="text",
            )
            require(len(entries) < 200, "Review note limit reached", "resource_limit")
            entries.append(
                {
                    "id": uuid4().hex,
                    "text": text.strip(),
                    "resolved": False,
                    "created": datetime.now(timezone.utc).isoformat(),
                }
            )
        elif action == "resolve":
            match = next((entry for entry in entries if entry["id"] == note_id), None)
            require(match is not None, "Review note not found", "not_found")
            match["resolved"] = True
        if action != "list":
            payload = json.dumps(entries, ensure_ascii=False)
            require(
                len(payload.encode("utf-8")) <= 1_048_576, "Review note byte limit reached", "resource_limit"
            )
            fd, tmp = temporary(path.parent, like=path)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    stream.write(payload)
                os.replace(tmp, path)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
    return {"notes": entries}
