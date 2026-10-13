"""T06 fillable form (US Letter at 300 dpi, 2550 × 3300): open mic sign-up.

The run's own first batch, ``ops/T06-build-ops.json`` (copied from ``runs/T06/claude-V``), applied to a white
letter page. The report's two small follow-up batches were not kept; rendered, this batch matches
``signup-form.pdf`` in every position (only the title weight differs, because the rolled fonts are not
installed here). The body size is set to the form's 10 pt labels (42 px at 300 dpi)."""

from ..kit import Doc, ops_file


def build():
    d = Doc(2550, 3300, "#ffffff", body=42)
    d.op(*ops_file("T06-build-ops.json"))
    return {"T06-form": d.build()}
