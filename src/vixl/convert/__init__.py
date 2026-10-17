"""The conversion kit: turn documents and saved tool calls made with earlier Vixl releases into ones for this release.

    from vixl.convert import convert_file, convert_project, convert_directory, convert_batch
    convert_file("poster-0.20.vixl", "poster.vixl")            # report: changes, warnings, counts
    convert_file("poster-0.20.vixl", look="current", dry_run=True)
    convert_batch(saved_calls)                                   # old MCP calls → the seven-tool surface

``look="preserve"`` (default) keeps the old look by writing formerly implicit behaviour into explicit fields;
``look="current"`` only removes what the current code no longer reads and reports what will look different.
The engine never imports this package: migration logic lives here, not in the runtime. See docs/reference/converting.md.
"""

from .batches import TOOLS, convert_batch, convert_batch_file
from .documents import convert_directory, convert_file, convert_manifest, convert_project, convert_state
from .rules import RULES

__all__ = ["RULES", "TOOLS", "convert_batch", "convert_batch_file", "convert_directory", "convert_file",
           "convert_manifest", "convert_project", "convert_state"]
