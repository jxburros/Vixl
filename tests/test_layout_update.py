"""Edited copy reflows instead of shrinking (#768): the overflow repair grows the box into free space and moves the
rows below before it shrinks the type, and ``layout-apply update: true`` re-runs the stored recipe with new copy."""
import pytest

from vixl import Project, VixlError
from vixl.render import resolve_layout
from vixl.repair import suggest

COPY = {"title": "Night Market", "label": "Saturday 7 pm", "body": "Riverside Park\nFood, music and makers\nFree entry",
        "cta": "RSVP", "caption": "example.com/market"}


def poster():
    project = Project.sized("instagram-portrait", seed=1)
    project.apply({"type": "layout-apply", "name": "event-poster", "seed": 1, **COPY})
    return project


def tops(project):
    bounds = resolve_layout(project)
    return {layer["name"]: bounds[layer["id"]][1] for layer in project.state["layers"] if layer["type"] == "text"}


def test_a_longer_headline_grows_its_box_and_moves_the_details_down():
    project = poster()
    size, before = project.layer("headline")["size"], tops(project)
    project.apply({"type": "text-set", "target": "headline", "text": "Night Market returns"})
    (finding,) = [x for x in project.check(checks=["bounds"])["issues"] if x["rule"] == "bounds.text-overflow"]
    repair = suggest(project, finding)
    assert repair["kind"] == "grow-box" and repair["operations"][0]["type"] == "text-layout"
    moved = {op["target"] for op in repair["operations"] if op["type"] == "move"}
    assert {project.layer(name)["id"] for name in ("date-block", "date", "detail-1", "detail-3")} <= moved
    assert all(op["type"] != "fit-text" for op in repair["operations"])
    project.apply(repair["operations"])
    after = tops(project)
    assert project.layer("headline")["size"] == size  # the type keeps its size
    assert after["date"] > before["date"] and after["detail-3"] > before["detail-3"]
    assert project.check(checks=["bounds"])["passed"]


def test_a_much_longer_headline_shrinks_only_to_its_role_floor_after_growing():
    project = poster()
    size = project.layer("headline")["size"]
    project.apply({"type": "text-set", "target": "headline", "text": "Night Market returns to the riverside this summer"})
    (finding,) = [x for x in project.check(checks=["bounds"])["issues"] if x["rule"] == "bounds.text-overflow"]
    repair = suggest(project, finding)
    assert repair["kind"] == "grow-box" and repair["operations"][-1]["type"] == "fit-text"
    floor = repair["operations"][-1]["minimum"]
    assert floor > project.layer("date")["size"]  # a headline stays above the date line
    project.apply(repair["operations"])
    assert floor <= project.layer("headline")["size"] < size
    assert project.check(checks=["bounds"])["passed"]
    # repair-layout ranks the growing candidate first and keeps the plain shrink as a later one.
    from vixl.plugins.layout_repair.layout_repair import repair_layout

    fresh = poster()
    fresh.apply({"type": "text-set", "target": "headline", "text": "Night Market returns to the riverside this summer"})
    plan = repair_layout(fresh, checks=["bounds"], dry_run=True)
    names = [attempt["candidate"] for attempt in plan["attempts"]]
    assert names[0] == "map:grow-box"


def test_layout_update_takes_new_copy_and_carries_manual_edits():
    project = poster()
    project.apply({"type": "text-set", "target": "detail-1", "color": "#ff0000"})
    project.apply({"type": "layout-apply", "name": "event-poster", "update": True, "title": "Night Market returns"})
    record = project.state["layout"]
    assert project.layer("headline")["text"] == "Night Market returns" and record["recipe"]["title"] == "Night Market returns"
    assert record["seed"] == 1 and record["update"] == {"carried": ["detail-1"]}
    assert project.layer("detail-1")["color"] == "#ff0000" and project.layer("detail-2")["color"] != "#ff0000"
    assert project.check(checks=["bounds"])["passed"]
    assert "manual edits carried over on 'detail-1'" in " ".join(record["notes"])
    with pytest.raises(VixlError, match="apply a layout first"):
        Project(400, 400).apply({"type": "layout-apply", "name": "event-poster", "update": True, "title": "x"})
    with pytest.raises(VixlError, match="re-runs the document's layout"):
        project.apply({"type": "layout-apply", "name": "hero-statement", "update": True, "title": "x"})
