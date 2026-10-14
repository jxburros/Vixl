"""The published document schema (src/vixl/data/vixl-document.schema.json) matches the model."""

import ast
import json
from pathlib import Path
import re
import sys
import zipfile

import pytest

from vixl import Project
from vixl.document_schema import (COMMON_LAYER_FIELDS, INSPECT_ONLY, LAYER_FIELDS, SCHEMA_PATH, STATE_FIELDS,
                                  TRANSIENT, document_schema, schema_text, validate_manifest)

ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "src" / "vixl"

# Names the source scan picks up that are not layer fields: a variable called ``layer`` holding something else.
NOT_LAYER_FIELDS = {
    "children": "replace_across walks a tree of {children} nodes, not layers",
    "lookup": "pre-0.21 field, turned into a lookup effect by the conversion kit (vixl.convert)",
}
# Names the source scan picks up that are not document state keys.
NOT_STATE_FIELDS = {}


def _manifests():
    old = ROOT / "tests" / "fixtures" / "convert"  # documents saved by older releases: test_convert converts them
    for path in sorted(ROOT.glob("**/*.vixl")):
        if {".git", ".claude", "_failures"} & set(path.relative_to(ROOT).parts) or old in path.parents:
            continue
        with zipfile.ZipFile(path) as archive:
            yield path.relative_to(ROOT), json.loads(archive.read("project.json"))


def test_shipped_schema_is_generated_from_the_model():
    assert SCHEMA_PATH.read_text(encoding="utf-8") == schema_text(), (
        "Run `python -m vixl.document_schema` to regenerate src/vixl/data/vixl-document.schema.json")
    from jsonschema import Draft202012Validator

    Draft202012Validator.check_schema(document_schema())


@pytest.mark.parametrize("path,manifest", list(_manifests()), ids=lambda value: str(value)[-48:])
def test_every_vixl_file_in_the_repository_validates(path, manifest):
    assert validate_manifest(manifest) == [], path


def test_visual_fixtures_and_operation_examples_validate():
    sys.path.insert(0, str(ROOT / "tests" / "visual"))
    try:
        from visual_fixtures import FIXTURES
    finally:
        sys.path.pop(0)
    from vixl.schema_docs import EXAMPLES

    problems = []
    for name, build in FIXTURES.items():
        problems += [f"{name}: {e}" for e in validate_manifest(build().manifest())]
    for kind, examples in EXAMPLES.items():
        for example in examples:
            p = Project(640, 480, "white")
            p.apply([{"type": "shape", "shape": "rectangle", "name": "card", "width": 200, "height": 100,
                      "fill": "red"}, {"type": "text", "text": "Hello", "name": "title", "y": 200, "size": 32}])
            try:
                p.apply(example)
            except Exception:  # an example that needs other layers or a workspace: the base still validates
                pass
            problems += [f"{kind}: {e}" for e in validate_manifest(p.manifest())]
    assert problems == []


def test_layer_types_roles_and_blends_come_from_the_model():
    from vixl.model import LAYER_ROLES, LAYER_TYPES
    from vixl.render import BLENDS

    layer = document_schema()["$defs"]["layer"]["properties"]
    assert layer["type"]["enum"] == list(LAYER_TYPES)
    assert layer["role"]["enum"] == list(LAYER_ROLES)
    assert layer["blend"]["enum"] == list(BLENDS)


def test_unknown_layer_fields_and_types_are_rejected():
    p = Project(40, 40)
    p.apply({"type": "shape", "shape": "ellipse", "name": "dot", "width": 10, "height": 10})
    manifest = p.manifest()
    manifest["state"]["layers"][0]["sparkle"] = True
    assert any("sparkle" in error for error in validate_manifest(manifest))
    manifest["state"]["layers"][0].pop("sparkle")
    manifest["state"]["layers"][0]["type"] = "hologram"
    assert validate_manifest(manifest)


def _keyword_names(source):
    """Keyword argument names of every ``new_layer(...)`` and ``layer.update(...)`` call in a module."""
    names = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            target = node.func
            called = target.id if isinstance(target, ast.Name) else getattr(target, "attr", "")
            owner = target.value.id if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) else ""
            if called == "new_layer" or (called == "update" and owner == "layer"):
                names |= {keyword.arg for keyword in node.keywords if keyword.arg}
    return names


# A key read or written on ``layer`` / ``X.state``: subscripts, get/setdefault/pop with a literal key, and ``in``
# tests on the dict itself (not on one of its values, such as ``"logo" in layer["name"]``).
LAYER_PATTERNS = (r'\blayer\["([a-z_][a-z0-9_]*)"\]', r'\blayer\.(?:get|setdefault|pop)\("([a-z_][a-z0-9_]*)"\s*[,)]',
                  r'"([a-z_][a-z0-9_]*)" (?:not )?in layer\b(?![\[.])')
STATE_PATTERNS = (r'\.state\["([a-z_][a-z0-9_]*)"\]', r'\.state\.(?:get|setdefault|pop)\("([a-z_][a-z0-9_]*)"\s*[,)]',
                  r'"([a-z_][a-z0-9_]*)" (?:not )?in [a-z_]+\.state\b(?![\[.])')


def _scan(patterns, keywords=False):
    found = {}
    for path in sorted(SOURCE.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                found.setdefault(match.group(1), path.name)
        if keywords:
            for name in _keyword_names(text):
                found.setdefault(name, path.name)
    return found


def test_every_layer_field_the_code_uses_is_in_the_schema():
    from vixl.inplace import SHAPE_FIELDS, TEXT_FIELDS

    used = _scan(LAYER_PATTERNS, keywords=True)
    for name in (*SHAPE_FIELDS, *TEXT_FIELDS):
        used.setdefault(name, "inplace.py")
    known = {*COMMON_LAYER_FIELDS, *LAYER_FIELDS, *INSPECT_ONLY, *TRANSIENT, *NOT_LAYER_FIELDS}
    missing = {name: where for name, where in used.items() if name not in known}
    assert not missing, ("Layer fields used in code but missing from vixl.document_schema.LAYER_FIELDS "
                         f"(add them, then run python -m vixl.document_schema): {missing}")


def test_every_state_field_the_code_uses_is_in_the_schema():
    used = _scan(STATE_PATTERNS)
    known = {*STATE_FIELDS, *NOT_STATE_FIELDS}
    missing = {name: where for name, where in used.items() if name not in known}
    assert not missing, ("Document state fields used in code but missing from vixl.document_schema.STATE_FIELDS: "
                         f"{missing}")


def test_a_saved_paged_document_validates(tmp_path):
    p = Project(120, 80, "white")
    p.apply([{"type": "text", "text": "Hi", "name": "t", "size": 20},
             {"type": "shape", "shape": "ellipse", "name": "e", "width": 30, "height": 30},
             {"type": "group", "name": "g", "targets": ["t", "e"]},
             {"type": "page", "action": "add", "name": "second"}])
    path = p.save(tmp_path / "doc.vixl")
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read("project.json"))
        assert set(archive.namelist()) == {"project.json", *manifest["asset_hashes"]}
    assert manifest["state"]["pages"]
    assert validate_manifest(manifest) == []


def test_cli_prints_the_document_schema(capsys):
    from vixl.cli import main

    assert main(["schema", "document"]) == 0
    assert json.loads(capsys.readouterr().out) == document_schema()
