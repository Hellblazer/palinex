# SPDX-License-Identifier: Apache-2.0
"""Tests for the palinex MCP server (render_surface tool).

These tests exercise the tool's function logic directly. The full
FastMCP stdio plumbing is provided by the upstream mcp library and
isn't re-tested here.
"""
from __future__ import annotations

import json
import sys
from unittest.mock import patch

import pytest


# Skip the whole module if mcp isn't installed (the [mcp] extra). The
# tests are exercising the tool's logic, which requires the FastMCP
# decorator to import cleanly. CI installs the dev group which pulls mcp.
pytest.importorskip("mcp.server.fastmcp")


@pytest.fixture(autouse=True)
def reset_bridge_cache():
    """Each test gets a fresh nexus_bridge cache so the
    is_available() check sees what the test's monkeypatch set up."""
    import palinex.nexus_bridge as nb
    original = nb._NEXUS_AVAILABLE
    nb._NEXUS_AVAILABLE = False
    yield
    nb._NEXUS_AVAILABLE = original


@pytest.fixture
def render_surface():
    from palinex.mcp.server import render_surface
    return render_surface


@pytest.fixture
def fake_nexus(monkeypatch):
    """Install fake nexus modules so nexus_bridge.is_available() returns
    True and chash_resolver can return canned text."""
    from types import ModuleType
    canned: dict[str, str] = {}

    fake_t3 = type("T3", (), {})()
    fake_t3.get_by_id = lambda col, doc_id: (
        {"content": canned[doc_id]} if doc_id in canned else None
    )

    mcp_infra_mod = ModuleType("nexus.mcp_infra")
    mcp_infra_mod.get_t3 = lambda: fake_t3
    corpus_mod = ModuleType("nexus.corpus")
    corpus_mod.t3_collection_name = lambda arg, *, t3=None: arg
    nexus_pkg = ModuleType("nexus")

    monkeypatch.setitem(sys.modules, "nexus", nexus_pkg)
    monkeypatch.setitem(sys.modules, "nexus.mcp_infra", mcp_infra_mod)
    monkeypatch.setitem(sys.modules, "nexus.corpus", corpus_mod)
    yield canned


@pytest.fixture
def sample_payload():
    return {
        "version": "v0.9",
        "messages": [
            {"version": "v0.9", "createSurface": {"surfaceId": "t", "catalogId": "a2ui.basic.v0_9"}},
            {"version": "v0.9", "updateDataModel": {"surfaceId": "t", "path": "/", "value": {
                "items": [
                    {"title": "alpha", "chash": "a" * 32},
                    {"title": "beta", "chash": "b" * 32},
                ],
            }}},
            {"version": "v0.9", "updateComponents": {"surfaceId": "t", "components": [
                {"id": "root", "component": "Column", "children": ["btn"]},
                {"id": "btn-lbl", "component": "Text", "text": "Open"},
                {"id": "btn", "component": "Button", "child": "btn-lbl",
                 "action": {"functionCall": {"call": "openChash",
                                             "args": {"chash": {"path": "/items/0/chash"}}}}},
            ]}},
        ],
    }


# ---- shape / dispatch -----------------------------------------------------


def test_returns_mcp_resource_envelope(render_surface, sample_payload):
    result = render_surface(sample_payload)
    assert result["type"] == "resource"
    res = result["resource"]
    assert res["mimeType"] == "text/html"
    assert res["uri"].startswith("ui://palinex/")
    assert "<!DOCTYPE html>" in res["text"]
    # Payload was embedded
    assert '"surfaceId": "t"' in res["text"]


def test_accepts_dict_payload(render_surface, sample_payload):
    result = render_surface(sample_payload)
    assert result["type"] == "resource"


def test_accepts_json_string_payload(render_surface, sample_payload):
    result = render_surface(json.dumps(sample_payload))
    assert result["type"] == "resource"
    assert '"surfaceId": "t"' in result["resource"]["text"]


def test_rejects_invalid_json_string(render_surface):
    with pytest.raises(ValueError, match="not valid JSON"):
        render_surface("{not valid json")


def test_rejects_non_dict_non_string(render_surface):
    with pytest.raises(ValueError, match="must be a dict"):
        render_surface(42)


def test_unique_uri_per_call(render_surface, sample_payload):
    r1 = render_surface(sample_payload)
    r2 = render_surface(sample_payload)
    assert r1["resource"]["uri"] != r2["resource"]["uri"]


def test_custom_title_in_html(render_surface, sample_payload):
    result = render_surface(sample_payload, title="my custom title")
    assert "<title>my custom title</title>" in result["resource"]["text"]


def test_custom_renderer_url(render_surface, sample_payload):
    result = render_surface(
        sample_payload,
        renderer_url="https://example.com/r.html",
    )
    assert "https://example.com/r.html" in result["resource"]["text"]


# ---- nexus integration ----------------------------------------------------


def test_without_nexus_extra_payload_unchanged(render_surface, sample_payload):
    """Without nexus available, chashes are preserved (no substitution)."""
    result = render_surface(sample_payload)
    text = result["resource"]["text"]
    # Original chash IDs still present in the rendered HTML
    assert '"' + ("a" * 32) + '"' in text
    assert '"' + ("b" * 32) + '"' in text
    # openChash action NOT rewritten (no resolver, no rewrite)
    assert '"call": "openChash"' in text


def test_with_nexus_extra_chashes_substituted(render_surface, sample_payload, fake_nexus):
    """When nexus_bridge.is_available() returns True, the resolver runs."""
    fake_nexus["a" * 32] = "the alpha chunk text"
    fake_nexus["b" * 32] = "the beta chunk text"
    result = render_surface(sample_payload)
    text = result["resource"]["text"]
    assert "the alpha chunk text" in text
    assert "the beta chunk text" in text
    # Original chash IDs gone
    assert '"' + ("a" * 32) + '"' not in text
    # openChash rewritten
    assert '"call": "openChash"' not in text
    assert '"call": "copyToClipboard"' in text


def test_collection_routed_through_to_resolver(render_surface, sample_payload, fake_nexus):
    """Custom collection arg is passed through to nexus T3 lookup."""
    captured: list[str] = []
    sys.modules["nexus.corpus"].t3_collection_name = lambda arg, *, t3=None: (
        captured.append(arg) or arg
    )
    fake_nexus["a" * 32] = "x"
    render_surface(sample_payload, collection="docs")
    assert "docs" in captured
