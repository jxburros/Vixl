import asyncio
import json

import pytest

from vixl import Project, VixlError
from vixl.capabilities import lookup
from vixl.diagnostics import timeline_report, validation_report
from vixl.interfaces import Session
from vixl.mcp_tools import build_server, service_operation_schema
from vixl.schema import operation_schema, validate_operation
from vixl.validation import validate
from vixl.workflows import dispatch


def test_atomic_batch_above_old_limit_and_rollback():
    p = Project(10, 10)
    original = p.head
    ops = [{"type": "variable", "name": f"v{i}", "value": str(i)} for i in range(1001)]
    p.apply(ops)
    assert len(p.state["variables"]) == 1001
    p.undo()
    assert p.head == original and not p.state["variables"]
    with pytest.raises(VixlError):
        p.apply([*ops, {"type": "move", "target": "missing", "x": 1}])
    assert p.head == original and not p.state["variables"]
    assert operation_schema()["properties"]["operations"]["maxItems"] == p.limits.max_operations == 10000


def test_workflow_names_bad_field_and_allowed_fields(tmp_path):
    with pytest.raises(VixlError) as exc:
        dispatch(Session(workspace=tmp_path), "film-plan", {"spec": {}, "specc": {}})
    error = exc.value
    assert "specc" in str(error) and "spec" in str(error)
    assert error.details["field"] == "specc"
    assert error.details["suggestions"]["specc"] == "spec"
    assert error.details["allowed"] == ["spec"]


def test_validation_summaries_preserve_verdict_and_bleed_intent():
    p = Project(200, 100)
    p.apply(
        [
            {
                "type": "shape",
                "shape": "rectangle",
                "name": "background",
                "x": -10,
                "width": 220,
                "height": 100,
            },
            {"type": "layer-intent", "target": "background", "role": "background"},
            {"type": "shape", "shape": "rectangle", "name": "mistake", "x": 300, "width": 10, "height": 10},
        ]
    )
    report = validate(p)
    bleed = next(c for c in report["checks"] if c.get("layer") == "background")
    assert bleed["severity"] == "info"
    compact = validation_report(report, targets=["background"])
    assert not compact["valid"] and compact["summary"]["errors"] == 1
    assert compact["checks"] == [bleed]
    assert validate(p, suppress=["layer.mistake.*"])["valid"]
    p.apply({"type": "layer-intent", "target": "mistake", "allow_crop": True})
    assert validate(p)["valid"]


def test_timeline_detail_and_key_pagination():
    p = Project(20, 20)
    p.apply(
        [
            {"type": "solid", "name": "actor"},
            {"type": "timeline-set", "duration": 10000},
            *[
                {
                    "type": "keyframe",
                    "target": "actor",
                    "property": "opacity",
                    "time": i * 20,
                    "value": (i % 2),
                }
                for i in range(400)
            ],
        ]
    )
    brief = timeline_report(p)
    assert brief["summary"] == {"tracks": 1, "keys": 400}
    assert "keys" not in brief["tracks"][0]
    full = timeline_report(p, detail="full", targets=["act*"], start=1000, end=2000, key_limit=10)
    assert len(full["tracks"][0]["keys"]) == 10
    assert full["tracks"][0]["key_pagination"]["next_offset"] == 10
    rest = timeline_report(p, detail="full", targets=["act*"], start=1000, end=2000, key_offset=10)
    assert rest["tracks"][0]["keys"][0]["time"] == 1200


def test_discovery_parity_and_aliases(tmp_path):
    result = lookup("text", fields=True)
    assert "font" in result["operations"]["text"]["fields"]
    assert "literal local pixels" in " ".join(result["gotchas"])
    assert validate_operation({"type": "move_layer", "x": 2})["type"] == "move"
    assert validate_operation({"type": "set_opacity", "opacity": 50})["value"] == 0.5

    async def run():
        server = build_server(Session(workspace=tmp_path))
        tools = {t.name: t for t in await server.list_tools()}
        assert "vixl_capabilities" in tools
        args = tools["vixl_operations_apply"].inputSchema["properties"]["operations"]
        assert args["maxItems"] == 10000
        result = await server.call_tool("vixl_operation_schema", {"types": ["move_layer"]})
        content = result[0] if isinstance(result, tuple) else result
        assert "move" in json.loads(content[0].text)

    asyncio.run(run())
    assert "font" in json.dumps(service_operation_schema())
