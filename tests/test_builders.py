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
