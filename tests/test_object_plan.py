"""object-plan: a scaffold of placeholder parts from an object kind (and figure-plan, its person alias)."""

import json
from pathlib import Path

from vixl.interfaces import Session
from vixl.workflows import dispatch

FIXTURES = Path(__file__).parent / "fixtures" / "objects"


def test_figure_plan_output_is_unchanged(tmp_path):
    """The snapshot was written from figure-plan before object-plan existed; the plan itself stays byte-identical."""
    session = Session(workspace=tmp_path)
    for case in json.loads((FIXTURES / "figure-plan-snapshot.json").read_text(encoding="utf-8")):
        result = dispatch(session, "figure-plan", {"spec": case["spec"]})
        result = {key: value for key, value in result.items() if key != "normalized"}
        assert json.dumps(result) == case["json"], case["spec"]
