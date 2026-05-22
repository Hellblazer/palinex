"""Tests for the palinex Surface builder."""
from __future__ import annotations

import json

import pytest

from palinex import DataPath, Event, FunctionCall, Surface, demo_nx_answer


def test_minimal_surface_round_trips():
    s = Surface(surface_id="t1", catalog_id="a2ui.basic.v0_9")
    body = s.text("hello")
    s.set_root(body)
    envelope = s.emit()
    assert envelope["version"] == "v0.9"
    assert envelope["messages"][0]["createSurface"]["surfaceId"] == "t1"
    assert envelope["messages"][-1]["updateComponents"]["components"][0]["id"] == "root"


def test_root_swap_keeps_payload():
    s = Surface(surface_id="t2", catalog_id="a2ui.basic.v0_9")
    s.text("first", id="first-text")
    second = s.text("second", id="second-text")
    s.set_root(second)
    components = {c["id"]: c for c in s.emit_flat()["components"]}
    assert "root" in components
    assert components["root"]["component"] == "Text"
    assert components["root"]["text"] == "second"


def test_data_path_serializes_as_path():
    s = Surface(surface_id="t3", catalog_id="a2ui.basic.v0_9")
    body = s.text(path="/greeting")
    s.set_root(body)
    components = {c["id"]: c for c in s.emit_flat()["components"]}
    assert components["root"]["text"] == {"path": "/greeting"}


def test_button_requires_action():
    s = Surface(surface_id="t4", catalog_id="a2ui.basic.v0_9")
    label = s.text("Click")
    btn = s.button(label, action=s.open_url("https://example.com"))
    s.set_root(btn)
    components = {c["id"]: c for c in s.emit_flat()["components"]}
    assert components["root"]["action"]["functionCall"]["call"] == "openUrl"


def test_event_action_shape():
    s = Surface(surface_id="t5", catalog_id="a2ui.basic.v0_9")
    label = s.text("Submit")
    btn = s.button(label, action=s.event("formSubmit", form="signup"))
    s.set_root(btn)
    components = {c["id"]: c for c in s.emit_flat()["components"]}
    assert components["root"]["action"]["event"]["name"] == "formSubmit"
    assert components["root"]["action"]["event"]["context"] == {"form": "signup"}


def test_card_rejects_list_of_children():
    s = Surface(surface_id="t6", catalog_id="a2ui.basic.v0_9")
    a = s.text("a")
    with pytest.raises(TypeError):
        s.card([a])  # Card.child is a single id; must wrap in Column/Row.


def test_validate_catches_dangling_child_ref():
    s = Surface(surface_id="t7", catalog_id="a2ui.basic.v0_9")
    a = s.text("a")
    s.column([a], id="col-only")
    s.set_root("col-only")
    # Now monkey-patch a broken ref to simulate corruption.
    s._components["root"]["children"].append("does-not-exist")
    with pytest.raises(ValueError, match="unknown child"):
        s.validate()


def test_validate_requires_root():
    s = Surface(surface_id="t8", catalog_id="a2ui.basic.v0_9")
    s.text("orphan")
    with pytest.raises(ValueError, match="set_root"):
        s.validate()


def test_demo_round_trips():
    s = demo_nx_answer()
    s.validate()
    envelope = s.emit()
    # Re-parse via json to confirm fully serializable.
    parsed = json.loads(json.dumps(envelope))
    assert parsed["version"] == "v0.9"
    assert any("updateDataModel" in m for m in parsed["messages"])
    assert any("updateComponents" in m for m in parsed["messages"])


def test_markdown_sidecar_lossless_for_demo():
    s = demo_nx_answer()
    md = s.to_markdown()
    # Synthesis appears verbatim.
    assert "A2UI v0.9 is a declarative UI protocol" in md
    # Both citation titles present.
    assert "a2ui v0.9 specification" in md
    assert "Basic Catalog reference" in md
    # Heading variants render.
    assert "##### Citations" in md
    assert "#### a2ui v0.9 specification" in md


def test_list_template_shape():
    s = Surface(surface_id="t9", catalog_id="a2ui.basic.v0_9")
    item = s.text(path="/@item/label")
    listing = s.list(template=item, template_path="/items")
    s.set_root(listing)
    components = {c["id"]: c for c in s.emit_flat()["components"]}
    children = components["root"]["children"]
    assert isinstance(children, dict)
    assert children["componentId"] == item
    assert children["path"] == "/items"


def test_emit_flat_shape():
    s = Surface(surface_id="t10", catalog_id="a2ui.basic.v0_9")
    s.set_root(s.text("hi"))
    flat = s.emit_flat()
    assert flat["surfaceId"] == "t10"
    assert flat["catalogId"] == "a2ui.basic.v0_9"
    assert isinstance(flat["components"], list)


@pytest.mark.parametrize("variant", ["h1", "h2", "h3", "h4", "h5", "caption", "body"])
def test_text_variants_round_trip(variant):
    s = Surface(surface_id=f"tv-{variant}", catalog_id="a2ui.basic.v0_9")
    s.set_root(s.text("x", variant=variant))
    components = {c["id"]: c for c in s.emit_flat()["components"]}
    if variant == "body":
        assert "variant" not in components["root"]
    else:
        assert components["root"]["variant"] == variant


def test_tabs_shape():
    s = Surface(surface_id="t-tabs", catalog_id="a2ui.basic.v0_9")
    a = s.text("first")
    b = s.text("second")
    s.set_root(s.tabs([{"title": "One", "child": a}, {"title": "Two", "child": b}]))
    components = {c["id"]: c for c in s.emit_flat()["components"]}
    root = components["root"]
    assert root["component"] == "Tabs"
    assert len(root["tabs"]) == 2
    assert root["tabs"][0] == {"title": "One", "child": a}
    assert root["tabs"][1]["child"] == b


def test_tabs_dynamic_title_serializes_as_path():
    s = Surface(surface_id="t-tabs-dyn", catalog_id="a2ui.basic.v0_9")
    a = s.text("content")
    s.set_root(s.tabs([{"title": DataPath("/active_tab_title"), "child": a}]))
    components = {c["id"]: c for c in s.emit_flat()["components"]}
    assert components["root"]["tabs"][0]["title"] == {"path": "/active_tab_title"}


def test_video_minimal():
    s = Surface(surface_id="t-video", catalog_id="a2ui.basic.v0_9")
    s.set_root(s.video("https://example.com/v.mp4"))
    components = {c["id"]: c for c in s.emit_flat()["components"]}
    assert components["root"] == {"id": "root", "component": "Video", "url": "https://example.com/v.mp4"}


def test_audio_player_with_description():
    s = Surface(surface_id="t-audio", catalog_id="a2ui.basic.v0_9")
    s.set_root(s.audio_player("https://example.com/a.mp3", description="Episode 42"))
    components = {c["id"]: c for c in s.emit_flat()["components"]}
    assert components["root"]["component"] == "AudioPlayer"
    assert components["root"]["url"] == "https://example.com/a.mp3"
    assert components["root"]["description"] == "Episode 42"


def test_audio_player_no_description_omits_field():
    s = Surface(surface_id="t-audio-bare", catalog_id="a2ui.basic.v0_9")
    s.set_root(s.audio_player("https://example.com/a.mp3"))
    components = {c["id"]: c for c in s.emit_flat()["components"]}
    assert "description" not in components["root"]


def test_date_time_input_combined():
    s = Surface(surface_id="t-dti", catalog_id="a2ui.basic.v0_9")
    s.set_root(s.date_time_input(value="2026-05-22T12:00",
                                  label="When",
                                  enable_date=True,
                                  enable_time=True,
                                  min="2026-01-01",
                                  max="2026-12-31"))
    components = {c["id"]: c for c in s.emit_flat()["components"]}
    root = components["root"]
    assert root["component"] == "DateTimeInput"
    assert root["enableDate"] is True
    assert root["enableTime"] is True
    assert root["min"] == "2026-01-01"
    assert root["max"] == "2026-12-31"
    assert root["label"] == "When"


def test_date_time_input_date_only_omits_time():
    s = Surface(surface_id="t-dti-date", catalog_id="a2ui.basic.v0_9")
    s.set_root(s.date_time_input(enable_date=True))
    components = {c["id"]: c for c in s.emit_flat()["components"]}
    assert components["root"]["enableDate"] is True
    assert "enableTime" not in components["root"]


def test_markdown_walks_new_components():
    s = Surface(surface_id="t-md", catalog_id="a2ui.basic.v0_9")
    tab_a = s.text("tab one body")
    tab_b = s.text("tab two body")
    tabs = s.tabs([{"title": "Alpha", "child": tab_a}, {"title": "Beta", "child": tab_b}])
    vid = s.video("https://example.com/v.mp4")
    aud = s.audio_player("https://example.com/a.mp3", description="Pod")
    dti = s.date_time_input(label="At", enable_date=True)
    s.set_root(s.column([tabs, vid, aud, dti]))
    md = s.to_markdown()
    assert "#### Alpha" in md
    assert "tab one body" in md
    assert "#### Beta" in md
    assert "tab two body" in md
    assert "[Video](https://example.com/v.mp4)" in md
    assert "[Audio: Pod](https://example.com/a.mp3)" in md
    assert "[DateTimeInput: At]" in md


def test_validate_catches_tabs_dangling_child():
    s = Surface(surface_id="t-tabs-bad", catalog_id="a2ui.basic.v0_9")
    a = s.text("a")
    s.tabs([{"title": "x", "child": a}], id="bad-tabs")
    s.set_root("bad-tabs")
    s._components["root"]["tabs"].append({"title": "y", "child": "missing-id"})
    with pytest.raises(ValueError, match="unknown tab child"):
        s.validate()
