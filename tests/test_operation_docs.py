"""Every operation schema carries a summary, typed fields with descriptions, and working examples."""

import asyncio
import json

import pytest

from vixl.project import Project
from vixl.render import EFFECTS
from vixl.schema import operation_schema, validate_operation
from vixl import schema_docs

TYPED = ("type", "enum", "anyOf", "oneOf", "const", "$ref", "allOf")
# Fields whose description is deliberately inherited from the shared wording are not listed
# here: the lint requires a description everywhere, so there is nothing to exempt.
UNDOCUMENTED = {}


def variants():
    return {v["properties"]["type"]["const"]: v for v in operation_schema()["properties"]["operations"]["items"]["oneOf"]}


def test_every_operation_has_a_one_line_summary():
    problems = []
    for kind, variant in variants().items():
        text = variant.get("description", "")
        if not text:
            problems.append(f"{kind}: no description")
        elif "\n" in text or len(text) > 220:
            problems.append(f"{kind}: summary should be one short line ({len(text)} chars)")
    assert not problems, "\n".join(problems)


def test_every_field_has_a_json_type_and_a_description():
    missing_type, missing_text = [], []
    for kind, variant in variants().items():
        for field, schema in variant["properties"].items():
            if field == "type" or f"{kind}.{field}" in UNDOCUMENTED:
                continue
            if not any(key in schema for key in TYPED):
                missing_type.append(f"{kind}.{field}")
            if not schema.get("description"):
                missing_text.append(f"{kind}.{field}")
    assert not missing_type, f"fields without a JSON type: {missing_type}"
    assert not missing_text, f"fields without a description: {missing_text}"


def test_effect_operations_describe_their_amount():
    for name in EFFECTS:
        variant = variants()[name]
        assert name in variant["description"] or variant["description"]
        assert variant["properties"]["amount"]["description"], name
    assert "0-1" in variants()["grain"]["properties"]["amount"]["description"]


def test_docs_name_only_real_operations_and_fields():
    kinds = variants()
    unknown = set(schema_docs.SUMMARIES) | set(schema_docs.OVERRIDES) | set(schema_docs.EXAMPLES)
    assert not unknown - set(kinds), f"docs for operations that do not exist: {sorted(unknown - set(kinds))}"
    for kind, fields in schema_docs.OVERRIDES.items():
        stray = set(fields) - set(kinds[kind]["properties"])
        assert not stray, f"{kind}: described fields the schema does not have: {sorted(stray)}"


@pytest.fixture(scope="module")
def stage():
    project = Project(800, 600, "#f8fafc")
    project.apply([
        {"type": "shape", "shape": "rounded-rectangle", "name": "card", "x": 80, "y": 80, "width": 320,
         "height": 200, "radius": 24, "fill": "#ffffff"},
        {"type": "shape", "shape": "star", "name": "badge", "x": 60, "y": 320, "width": 120, "height": 120,
         "fill": "#facc15"},
        {"type": "shape", "shape": "ellipse", "name": "moon", "x": 500, "y": 80, "width": 160, "height": 160,
         "fill": "#e2e8f0"},
        {"type": "shape", "shape": "ellipse", "name": "bite", "x": 540, "y": 70, "width": 140, "height": 140,
         "fill": "#0f172a"},
        {"type": "solid", "name": "photo", "width": 200, "height": 140, "color": "#94a3b8", "x": 460, "y": 340},
        {"type": "shape", "shape": "rectangle", "name": "logo", "x": 10, "y": 10, "width": 20, "height": 20,
         "fill": "red"},
        {"type": "text", "text": "Hello", "name": "greeting", "size": 40, "color": "#111111", "x": 100, "y": 450},
    ])
    return project


EXAMPLES = [(kind, i, op) for kind, ops in schema_docs.EXAMPLES.items() for i, op in enumerate(ops)]


@pytest.mark.parametrize("kind, index, op", EXAMPLES, ids=[f"{k}-{i}" for k, i, _ in EXAMPLES])
def test_every_example_validates_and_applies(stage, kind, index, op):
    assert op["type"] == kind
    validate_operation(json.loads(json.dumps(op)))
    candidate = stage.clone()
    created = op.get("name")
    # An example that creates a layer replaces the stage's layer of that name.
    if kind in ("shape", "text", "gradient", "pathfinder", "radial-repeat", "organic") and created:
        existing = [layer["name"] for layer in candidate.state["layers"]]
        if created in existing:
            candidate.apply({"type": "remove", "target": created})
    if kind == "palette-apply":
        candidate.apply({"type": "palette-define", "name": op["name"], "colors": ["#0b132b", "#1c2541", "#3a506b", "#5bc0be"]})
    if kind == "effect-move":
        candidate.apply([{"type": name, "target": "photo"} for name in ("blur", "brightness", "grain")])
    result = candidate.apply(op, detail="compact")
    assert result["success"]


def test_docs_and_skills_name_only_real_mcp_tools():  # #252
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    real = {name for path in (root / "src" / "vixl").glob("*.py")
            for name in re.findall(r"def (vixl_\w+)\(", path.read_text(encoding="utf-8"))}
    assert "vixl_resource_get" in real and "vixl_operations_apply" in real
    unknown = {}
    for folder in ("docs", "skills"):
        for path in (root / folder).rglob("*.md"):
            for name in re.findall(r"\bvixl_\w+", path.read_text(encoding="utf-8")):
                if name not in real and name != "vixl_ai_":  # `vixl_ai_*` is the provider tool family
                    unknown.setdefault(name, set()).add(path.name)
    assert not unknown, f"docs name MCP tools that do not exist: {unknown}"


def test_operation_schema_tool_serves_summaries_and_examples_but_tools_list_stays_lean(tmp_path):
    from vixl.interfaces import Session
    from vixl.mcp_tools import build_server, service_operation_schema

    served = json.dumps(service_operation_schema())
    assert "flat-color rectangle" not in served  # summaries stay out of tools/list
    assert '"examples": [' not in served
    server = build_server(Session(workspace=tmp_path))

    async def call(name, **arguments):
        result = await server.call_tool(name, arguments)
        content = result[0] if isinstance(result, tuple) else result
        return json.loads(content[0].text)

    schema = asyncio.run(call("vixl_operation_schema", types=["gradient", "layer-style", "blur"]))
    assert schema["gradient"]["description"].startswith("Add a")
    assert schema["gradient"]["properties"]["stops"]["description"]
    assert any(example["direction"] == "radial" for example in schema["gradient"]["examples"])
    assert {e["name"] for e in schema["layer-style"]["examples"]} >= {"drop-shadow", "outer-glow"}
    assert "blur" in schema["blur"]["description"].lower()
