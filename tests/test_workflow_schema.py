"""Workflow schemas and the check-suite object give every field a type and a description."""

import pytest

from vixl.assurance import RULE_FIELDS, validate_suite
from vixl.effect_workflows import SUITES
from vixl.project import Project
from vixl.schema import validate_operation
from vixl.workflow_schema import RULE_KINDS, SUITE
from vixl.workflows import ACTIONS, describe

TYPED = ("type", "enum", "anyOf", "oneOf", "const")


def walk(schema, path):
    """Yield (path, node) for a field schema and every nested property or item schema."""
    yield path, schema
    for key, child in schema.get("properties", {}).items():
        yield from walk(child, f"{path}.{key}")
    items = schema.get("items")
    if isinstance(items, dict):
        yield from walk(items, f"{path}[]")
    for option in schema.get("anyOf", []):
        yield from walk(option, path)
    if isinstance(schema.get("additionalProperties"), dict):
        yield from walk(schema["additionalProperties"], f"{path}.*")


def test_every_workflow_action_field_has_a_type_and_description():
    actions = describe()["actions"]
    assert set(actions) == set(ACTIONS)
    problems = []
    for action, entry in actions.items():
        assert entry["summary"], f"{action} has no summary"
        assert set(entry["properties"]) == set(entry["fields"]), f"{action}: fields without a schema"
        for field, schema in entry["properties"].items():
            if not any(key in schema for key in TYPED):
                problems.append(f"{action}.{field}: no type")
            if not schema.get("description") and not all(o.get("description") for o in schema.get("anyOf", [{}])):
                problems.append(f"{action}.{field}: no description")
            for path, node in walk(schema, f"{action}.{field}"):
                if path != f"{action}.{field}" and not any(key in node for key in TYPED):
                    problems.append(f"{path}: no type")
    assert not problems, "\n".join(problems)


def test_nested_properties_are_described():
    """Fields inside the structured values (suite rules, job, film shots …) say what they are too."""
    missing = []
    for action, entry in describe()["actions"].items():
        for field, schema in entry["properties"].items():
            for path, node in walk(schema, f"{action}.{field}"):
                if "properties" in node:
                    missing += [f"{path}.{k}" for k, child in node["properties"].items()
                                if not child.get("description") and "properties" not in child]
    assert not missing, "\n".join(missing)


def test_required_fields_are_listed_and_typed():
    for action, entry in describe()["actions"].items():
        assert set(entry["required"]) <= set(entry["properties"]), action


def test_suite_schema_matches_the_rule_kinds_the_engine_accepts():
    assert set(RULE_KINDS) == set(RULE_FIELDS)
    rule = SUITE["properties"]["rules"]["items"]["properties"]
    assert set(rule["kind"]["enum"]) == set(RULE_FIELDS)
    for kind, fields in RULE_FIELDS.items():
        assert fields <= set(rule), f"{kind}: fields missing from the suite schema: {fields - set(rule)}"
    assert {"version", "rules", "sampling", "description", "extends"} == set(SUITE["properties"])


def test_suite_object_is_in_the_workflow_and_operation_schemas():
    schema = describe()
    assert schema["definitions"]["suite"] is not None
    assert schema["actions"]["check"]["properties"]["suite"]["anyOf"][1]["properties"]["rules"]
    from vixl.schema import operation_schema

    variants = operation_schema()["properties"]["operations"]["items"]["oneOf"]
    suite_set = next(v for v in variants if v["properties"]["type"]["const"] == "suite-set")
    assert suite_set["properties"]["suite"]["properties"]["rules"]["items"]["properties"]["expression"]


def test_suite_examples_and_builtin_suites_validate_against_the_published_schema():
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(SUITE)
    for example in SUITE["examples"]:
        assert not list(validator.iter_errors(example))
        validate_suite(example)
    for name, suite in SUITES.items():
        errors = list(validator.iter_errors(suite))
        assert not errors, f"{name}: {errors[:1]}"


def test_documented_assert_suite_round_trips_through_the_tool_surface():
    """What an agent needs from the schema alone: the assert-rule suite, saved and then enforced."""
    project = Project(160, 100)
    suite = {"version": 1, "rules": [{"id": "logo-inside", "kind": "assert",
                                      "expression": "layer.logo.bounds within canvas"}]}
    project.apply([{"type": "shape", "shape": "rect", "name": "logo", "width": 20, "height": 20, "fill": "red",
                    "x": 10, "y": 10},
                   {"type": "suite-set", "name": "quality", "suite": suite}])
    assert project.check_suite("quality")["passed"]
    # An inline suite passes through check too, so no operation is needed to try a rule.
    assert project.check_suite(suite)["passed"]


@pytest.mark.parametrize("bad, field_hint", [
    ({"version": 1, "rules": []}, "rules"),
    ({"version": 1, "rules": [{"kind": "assert", "expression": "canvas.width > 1"}]}, "id"),
    ({"version": 1, "rules": [{"id": "a", "kind": "nonsense"}]}, "kind"),
    ({"version": 1, "rules": [{"id": "a", "kind": "assert", "severity": "fatal"}]}, "severity"),
])
def test_suite_errors_name_the_offending_field(bad, field_hint):
    with pytest.raises(Exception) as caught:
        validate_operation({"type": "suite-set", "name": "s", "suite": bad})
    assert field_hint in str(caught.value) or field_hint in str(getattr(caught.value, "field", ""))
