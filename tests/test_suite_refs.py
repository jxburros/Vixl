"""Suite rules that read their expected value from another document (#558): {"ref": "doc.vixl#layer.field"} and
{"ref": "doc.vixl#suite:rule-id"}."""

import pytest

from vixl import Project
from vixl.assurance import MAX_REFS, digest, resolve_ref, suite_refs, validate_suite
from vixl.errors import VixlError
from vixl.interfaces import Session
from vixl.workflows import dispatch


def master(path, fill="#cc2200", rules=None):
    p = Project(200, 200, "white")
    p.apply([{"type": "shape", "shape": "rectangle", "name": "brand", "x": 0, "y": 0, "width": 200, "height": 200,
              "fill": fill},
             {"type": "text", "name": "title", "text": "Title", "size": 48, "x": 10, "y": 10, "color": "#111111"}])
    if rules is not None:
        p.apply({"type": "suite-set", "name": "brand", "suite": {"rules": rules}})
    p.save(path, overwrite=True)
    return p


def dependent(path, fill="#cc2200", workspace=None):
    p = Project(200, 200, "white")
    p.apply([{"type": "shape", "shape": "rectangle", "name": "box", "x": 0, "y": 0, "width": 200, "height": 200,
              "fill": fill},
             {"type": "text", "name": "head", "text": "Head", "size": 40, "x": 10, "y": 10, "color": "#111111"},
             {"type": "text", "name": "body", "text": "Body", "size": 20, "x": 10, "y": 120, "color": "#111111"}])
    p.save(path, overwrite=True)
    p._workspace = str(workspace or path.parent)
    return p


def results(project, rules):
    report = project.check_suite({"rules": rules})
    return report, {item["id"]: item for item in report["results"]}


COLOR = {"id": "brand-red", "kind": "color", "point": [100, 100], "expected": {"ref": "master.vixl#brand.fill"}}


def test_changing_the_master_color_fails_the_dependent(tmp_path):
    master(tmp_path / "master.vixl")
    doc = dependent(tmp_path / "dep.vixl")
    report, found = results(doc, [COLOR])
    assert found["brand-red"]["status"] == "passed"
    assert found["brand-red"]["expected"] == "#cc2200"
    master(tmp_path / "master.vixl", fill="#0044ff")
    report, found = results(doc, [COLOR])
    assert found["brand-red"]["status"] == "failed" and found["brand-red"]["expected"] == "#0044ff"
    # The suite and the dependent document are unchanged: the ref is read each run, never written back.
    assert doc.state["layers"][0]["fill"] == "#cc2200"


def test_the_digest_of_the_referenced_state_is_recorded(tmp_path):
    source = master(tmp_path / "master.vixl")
    doc = dependent(tmp_path / "dep.vixl")
    report, found = results(doc, [COLOR])
    expected = [{"path": "master.vixl", "digest": digest(Project.load(tmp_path / "master.vixl").state)}]
    assert found["brand-red"]["references"] == expected
    assert report["references"] == expected
    assert expected[0]["digest"] == digest(source.state)


@pytest.mark.parametrize("ref", ["missing.vixl#brand.fill", "master.vixl#nope.fill", "master.vixl#brand.nofield",
                                 "master.vixl#brand:missing-rule", "master.vixl#nosuite:rule"])
def test_a_missing_reference_needs_review_never_passes(tmp_path, ref):
    master(tmp_path / "master.vixl", rules=[{"id": "title-ratio", "kind": "hierarchy", "targets": ["title", "brand"],
                                             "ratio": 1.5}])
    doc = dependent(tmp_path / "dep.vixl")
    report, found = results(doc, [{**COLOR, "expected": {"ref": ref}}])
    assert found["brand-red"]["status"] == "needs_review"
    assert not report["passed"] and report["outcome"]["validation"] == "incomplete"
    if ref.startswith("missing"):
        assert found["brand-red"]["references"] == [{"path": "missing.vixl", "digest": None}]


def test_a_rule_ref_reads_the_same_field_of_the_master_rule(tmp_path):
    master(tmp_path / "master.vixl", rules=[{"id": "type-scale", "kind": "hierarchy", "targets": ["title", "title"],
                                             "ratio": 1.5}])
    doc = dependent(tmp_path / "dep.vixl")
    rule = {"id": "scale", "kind": "hierarchy", "targets": ["head", "body"],
            "ratio": {"ref": "master.vixl#brand:type-scale"}}
    _, found = results(doc, [rule])
    assert found["scale"]["status"] == "passed" and found["scale"]["expected"] == 1.5
    master(tmp_path / "master.vixl", rules=[{"id": "type-scale", "kind": "hierarchy", "targets": ["title", "title"],
                                             "ratio": 2.5}])
    _, found = results(doc, [rule])
    assert found["scale"]["status"] == "failed" and found["scale"]["expected"] == 2.5


def test_relation_to_reads_a_layer_name(tmp_path):
    p = Project(200, 200, "white")
    p.apply({"type": "text", "name": "config", "text": "head", "x": 0, "y": 0})
    p.save(tmp_path / "master.vixl")
    doc = dependent(tmp_path / "dep.vixl")
    _, found = results(doc, [{"id": "under", "kind": "relation", "target": "body",
                              "to": {"ref": "master.vixl#config.text"}, "position": "below"}])
    assert found["under"]["status"] == "passed"


def test_a_cycle_is_refused_in_the_link_cycle_shape(tmp_path):
    a = Project(100, 100, "white")
    a.apply({"type": "suite-set", "name": "s", "suite": {"rules": [
        {"id": "r", "kind": "hierarchy", "targets": ["x", "y"], "ratio": {"ref": "b.vixl#s:r"}}]}})
    a.save(tmp_path / "a.vixl")
    b = Project(100, 100, "white")
    b.apply({"type": "suite-set", "name": "s", "suite": {"rules": [
        {"id": "r", "kind": "hierarchy", "targets": ["x", "y"], "ratio": {"ref": "a.vixl#s:r"}}]}})
    b.save(tmp_path / "b.vixl")
    a._workspace = str(tmp_path)
    found = {item["id"]: item for item in a.check_suite("s")["results"]}
    assert found["r"]["status"] == "needs_review" and found["r"]["code"] == "link_cycle"
    assert "cycle" in found["r"]["message"] and len(found["r"]["chain"]) == 3
    with pytest.raises(VixlError) as caught:
        resolve_ref(b, {"ref": "a.vixl#s:r"}, "ratio", ((str((tmp_path / "b.vixl").resolve()), "s", "r"),))
    assert caught.value.code == "link_cycle" and caught.value.details["chain"][0].endswith("b.vixl#s:r")


def test_nesting_is_limited_to_the_link_depth(tmp_path):
    for i in range(6):
        p = Project(100, 100, "white")
        ratio = {"ref": f"d{i + 1}.vixl#s:r"} if i < 5 else 1.2
        p.apply({"type": "suite-set", "name": "s", "suite": {"rules": [
            {"id": "r", "kind": "hierarchy", "targets": ["x", "y"], "ratio": ratio}]}})
        p.save(tmp_path / f"d{i}.vixl")
    doc = Project.load(tmp_path / "d0.vixl")
    doc._workspace = str(tmp_path)
    found = {item["id"]: item for item in doc.check_suite("s")["results"]}
    assert found["r"]["code"] == "link_depth" and found["r"]["status"] == "needs_review"


def test_refs_are_bounded_per_suite_and_per_run(tmp_path):
    master(tmp_path / "master.vixl")
    for i in range(MAX_REFS + 1):
        master(tmp_path / f"m{i}.vixl")
    rules = [{**COLOR, "id": f"r{i}", "expected": {"ref": f"m{i}.vixl#brand.fill"}} for i in range(MAX_REFS + 1)]
    with pytest.raises(VixlError) as caught:
        validate_suite({"rules": rules})
    assert caught.value.code == "resource_limit"
    validate_suite({"rules": rules[:MAX_REFS]})
    # The same ref read by several rules counts once.
    doc = dependent(tmp_path / "dep.vixl")
    same = [{**COLOR, "id": f"same{i}"} for i in range(MAX_REFS)]
    _, found = results(doc, same)
    assert all(found[f"same{i}"]["status"] == "passed" for i in range(MAX_REFS))


def test_refs_are_only_accepted_where_a_value_is_compared(tmp_path):
    with pytest.raises(VixlError):
        validate_suite({"rules": [{"id": "t", "kind": "contrast", "target": {"ref": "m.vixl#a.b"}}]})
    with pytest.raises(VixlError):
        validate_suite({"rules": [{**COLOR, "expected": {"ref": "master.vixl"}}]})
    with pytest.raises(VixlError):
        validate_suite({"rules": [{**COLOR, "expected": {"ref": "master.txt#a.b"}}]})
    assert suite_refs({"rules": [COLOR]}) == [("brand-red", "expected", "master.vixl#brand.fill")]


def test_services_keep_references_inside_the_workspace(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    master(outside / "master.vixl")
    work = tmp_path / "work"
    work.mkdir()
    doc = dependent(work / "dep.vixl")
    _, found = results(doc, [{**COLOR, "expected": {"ref": "../outside/master.vixl#brand.fill"}}])
    assert found["brand-red"]["status"] == "needs_review" and found["brand-red"]["code"] == "forbidden"


def test_check_all_carries_reference_digests_and_since_last_names_the_master(tmp_path):
    master(tmp_path / "master.vixl")
    doc = dependent(tmp_path / "dep.vixl")
    doc.apply({"type": "suite-set", "name": "brand", "suite": {"rules": [COLOR]}})
    doc.save(tmp_path / "dep.vixl", overwrite=True)
    session = Session(None, workspace=tmp_path)
    request = {"documents": ["dep.vixl"], "checks": ["bounds"]}
    first = dispatch(session, "check-all", request)
    entry = first["documents"][0]
    assert entry["references"] == {"master.vixl": digest(Project.load(tmp_path / "master.vixl").state)}
    assert entry["status"] == "passed"
    master(tmp_path / "master.vixl", fill="#0044ff")
    second = dispatch(session, "check-all", {**request, "since_last": True})
    failing = second["since_last"]["newly_failing"]
    assert failing and failing[0]["path"] == "dep.vixl" and failing[0]["cause"] == "reference"
    assert failing[0]["changed_references"] == ["master.vixl"] and not failing[0]["document_changed"]
