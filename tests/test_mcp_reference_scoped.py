"""Scoped references (#615 items 07, 13-20, 22): a small workflow index, brief operation schemas, dot paths,
reachable definitions only, ranked capabilities, and a schema version an agent can check a cached reference with."""

import asyncio
import json

import pytest

from vixl import __version__
from vixl.hashing import content_hash
from vixl.interfaces import mcp_server
from vixl.mcp_actions import one_line, schema_version
from vixl.schema import operation_schema
from vixl.schema_docs import property_schema, schema_brief


@pytest.fixture
def reference(tmp_path):
    server = mcp_server(workspace=tmp_path)

    def call(**arguments):
        async def run():
            try:
                result = await server.call_tool("vixl_reference", arguments)
            except Exception as exc:  # FastMCP surfaces tool failures as ToolError
                text = str(exc)
                return json.loads(text[text.index("{"):])
            content = result[0] if isinstance(result, tuple) else result
            return json.loads("".join(getattr(item, "text", "") for item in content))

        return asyncio.run(run())

    return call


def size(value):
    return len(json.dumps(value))


# Items 13/14: the workflow index ---------------------------------------------------------------------------


def test_workflow_index_is_one_line_per_action_under_8_kb(reference):
    index = reference(topic="workflows")
    assert size(index) < 8 * 1024
    assert all(isinstance(line, str) and "\n" not in line for line in index["actions"].values())
    assert "check" in index["actions"] and "form-fill" in index["actions"]
    assert "vixl_reference('workflows', name=" in index["next"]
    assert "properties" not in json.dumps(index["actions"])


def test_one_line_cuts_at_the_first_clause_and_a_word_boundary():
    assert one_line("Run a suite. Then more.") == "Run a suite"
    assert one_line("Render every variant (resuming if rerun); checks suites") == "Render every variant"
    long = "Measure loudness peaks clipping silence and onset timing and write a spectrogram of the whole track"
    assert one_line(long).endswith("…") and len(one_line(long)) <= 66 and " " not in one_line(long)[-2:]


def test_workflow_name_accepts_one_action_or_a_list_of_up_to_ten(reference):
    one = reference(topic="workflows", name="form-fill")
    assert one["action"] == "form-fill" and set(one["properties"]) == set(one["fields"])
    several = reference(topic="workflows", name=["check", "submit"])
    assert set(several["actions"]) == {"check", "submit"}
    assert "properties" in several["actions"]["check"]
    error = reference(topic="workflows", name=[f"a{n}" for n in range(11)])
    assert "1–10" in error["message"]
    unknown = reference(topic="workflows", name=["check", "no-such-action"])
    assert "no-such-action" in json.dumps(unknown) and "allowed" in json.dumps(unknown)


# Item 17: only the reachable definitions ---------------------------------------------------------------


def test_workflow_responses_carry_only_the_definitions_the_actions_reach(reference):
    check = reference(topic="workflows", name="check")
    assert set(check["definitions"]) == {"suite"}
    assert check["properties"]["suite"]["anyOf"][1] == {"$ref": "#/definitions/suite"}
    assert check["definitions"]["suite"]["properties"]["rules"]
    submit = reference(topic="workflows", name="submit")
    assert set(submit["definitions"]) == {"job"}
    both = reference(topic="workflows", name=["check", "submit", "act"])
    assert set(both["definitions"]) == {"suite", "job"}
    assert reference(topic="workflows", name="act")["definitions"] == {}


# Item 15: brief schemas -------------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["shape", "text", "keyframes", "chart", "pen", "effect", "container-place"])
def test_brief_schemas_stay_under_1_5_kb_and_name_the_required_fields(kind):
    from vixl.mcp_actions import operation_variant

    variant = operation_variant(kind)
    brief = schema_brief(variant)
    assert size(brief) < 1536, (kind, size(brief))
    assert brief["type"] == kind and brief["summary"]
    for field in variant.get("required", []):
        if field != "type":
            assert field in brief["required"]
    if variant.get("examples"):
        assert brief["example"] == variant["examples"][0]
    assert brief["example"]["type"] == kind
    assert "description" not in json.dumps(brief.get("fields", {}))


def test_reference_operations_detail_brief_and_full(reference):
    brief = reference(topic="operations", name=["shape", "text"], detail="brief")
    full = reference(topic="operations", name=["shape", "text"])
    assert size(brief["shape"]) < 1536 and size(brief["text"]) < 1536
    assert "enum: rectangle|rounded-rectangle" in brief["shape"]["fields"]["shape"] if isinstance(
        brief["shape"]["fields"], dict) else "shape" in brief["shape"]["fields"]
    assert "properties" in full["shape"] and "properties" in full["text"]
    assert full["shape"]["properties"]["shape"]["enum"]
    assert size(brief) < size(full) / 5
    step = reference(topic="operations", name=["import-image"], detail="brief")
    assert step["import-image"]["type"] == "import-image" and "path" in step["import-image"]["fields"]


# Item 16: dot paths ----------------------------------------------------------------------------------------


def test_dot_paths_return_one_property(reference):
    found = reference(topic="operations", name="text-layout.wrap")
    assert found["text-layout.wrap"]["schema"]["enum"] == ["greedy", "balance", "pretty"]
    assert found["text-layout.wrap"]["operation"] == "text-layout"
    mixed = reference(topic="operations", name=["shape.radius", "move"])
    assert "schema" in mixed["shape.radius"] and "properties" in mixed["move"]
    missing = reference(topic="operations", name="text-layout.wrapp")
    assert "wrap" in missing["text-layout.wrapp"]["suggestions"]


def test_property_schema_walks_nested_properties_and_items():
    variant = {"properties": {"type": {"const": "x"}, "slots": {"type": "object", "properties": {
        "title": {"type": "string"}}}, "points": {"type": "array", "items": {"type": "object", "properties": {
            "x": {"type": "number"}}}}}}
    assert property_schema(variant, "slots.title") == {"type": "string"}
    assert property_schema(variant, "points.x") == {"type": "number"}
    assert property_schema(variant, "points.z") is None


# Items 18-20: capabilities ---------------------------------------------------------------------------------


def test_capabilities_are_bounded_ranked_and_carry_the_top_operation_schema(reference):
    color = reference(topic="capabilities", name="color")
    assert len(color["operations"]) == 5 and color["more"] > 0
    assert size(color) < 4000
    more = reference(topic="capabilities", name="color", limit=20)
    assert len(more["operations"]) > 5
    everything = reference(topic="capabilities", name="color", options={"limit": None})
    assert "more" not in everything and len(everything["operations"]) == 5 + color["more"]
    with_fields = reference(topic="capabilities", name="color", fields=True)
    top = with_fields["top_operation"]
    assert top["type"] == next(iter(with_fields["operations"])) and "example" in top
    assert size(top) < 1536


def test_gotchas_are_filtered_by_topic(reference):
    from vixl.capabilities import GOTCHAS, gotchas

    assert all(entry["topics"] and entry["text"] for entry in GOTCHAS)
    assert gotchas() == [entry["text"] for entry in GOTCHAS]
    text = reference(topic="capabilities", name="text")["gotchas"]
    assert any("font accepts" in line for line in text)
    assert not any("literal local pixels" in line for line in text)
    drawing = reference(topic="capabilities", name="drawing")["gotchas"]
    assert any("literal local pixels" in line for line in drawing)
    assert not any("font accepts" in line for line in drawing)
    assert len(reference(topic="capabilities")["gotchas"]) == len(GOTCHAS)
    # Words that name no topic still find the gotchas that mention them.
    assert any("allow_crop" in line for line in gotchas([], ["bleed"]))


# Item 22: versions -----------------------------------------------------------------------------------------


def test_every_reference_result_carries_a_schema_version(reference):
    expected = f"{__version__}+{content_hash(operation_schema())[:12]}"
    assert schema_version() == expected
    for arguments in ({}, {"topic": "workflows"}, {"topic": "operations", "name": ["move"]},
                      {"topic": "vixl_export"}, {"topic": "natural-motion"}, {"topic": "capabilities"}):
        assert reference(**arguments)["schema_version"] == expected, arguments


def test_if_version_returns_unchanged_only_when_it_matches(reference):
    version = reference(topic="workflows")["schema_version"]
    assert reference(topic="workflows", if_version=version) == {"unchanged": True, "schema_version": version}
    assert reference(topic="workflows", options={"if_version": version})["unchanged"] is True
    assert reference(topic="vixl_export", if_version=version)["unchanged"] is True
    stale = reference(topic="workflows", if_version="0.0.0+000000000000")
    assert "unchanged" not in stale and stale["actions"] and stale["schema_version"] == version


# Item 07: guide names containers, layouts and create= -------------------------------------------------------


def test_guide_names_containers_layouts_and_a_create_object(reference):
    from vixl.briefs import CONTAINERS_FOR, KINDS
    from vixl.resources import catalog

    known = set(catalog("containers"))
    for kind, names in CONTAINERS_FOR.items():
        assert kind in KINDS and set(names) <= known, kind
    poster = reference(topic="a poster for a jazz night")
    assert poster["matched"] == "poster"
    assert "cta" in poster["containers"] and poster["layouts"]
    assert poster["create"]["size"] == KINDS["poster"]["sizes"][0]
    assert poster["create"]["layout"]["name"] == KINDS["poster"]["layouts"][0]
    assert poster["create"]["path"].endswith(".vixl") and "vixl_apply(create=" in poster["create_with"]
    social = reference(topic="social-card")
    assert "stat" in social["containers"] and social["create"]["purpose"] == "social"


def test_every_operation_brief_is_under_1_5_kb():
    largest = max((size(schema_brief(variant)), variant["properties"]["type"]["const"])
                  for variant in operation_schema()["properties"]["operations"]["items"]["oneOf"])
    assert largest[0] < 1536, largest
