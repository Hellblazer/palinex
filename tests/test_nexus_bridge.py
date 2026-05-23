# SPDX-License-Identifier: Apache-2.0
"""Tests for palinex.nexus_bridge — the lazy nexus integration shim.

These tests mock out the nexus imports so they run without conexus installed.
The real integration is exercised via the MCP server's own tests when the
[nexus] extra is present.
"""
from __future__ import annotations

import sys
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def reset_bridge_cache():
    """Reset the module-level _NEXUS_AVAILABLE cache between tests so that
    each test sees a fresh load attempt."""
    import palinex.nexus_bridge as nb
    original = nb._NEXUS_AVAILABLE
    nb._NEXUS_AVAILABLE = False
    yield
    nb._NEXUS_AVAILABLE = original


@pytest.fixture
def fake_nexus_modules(monkeypatch):
    """Inject fake nexus.mcp_infra and nexus.corpus modules into sys.modules.

    Returns the recording dict so tests can assert resolver calls landed.
    """
    from types import ModuleType
    calls: dict = {"get_by_id": [], "t3_collection_name": []}

    fake_t3 = type("T3", (), {})()
    def _get_by_id(col, doc_id):
        calls["get_by_id"].append((col, doc_id))
        return calls.get("_canned", {}).get(doc_id)
    fake_t3.get_by_id = _get_by_id

    def _get_t3():
        return fake_t3

    def _t3_collection_name(arg, *, t3=None):
        calls["t3_collection_name"].append(arg)
        return arg

    mcp_infra_mod = ModuleType("nexus.mcp_infra")
    mcp_infra_mod.get_t3 = _get_t3
    corpus_mod = ModuleType("nexus.corpus")
    corpus_mod.t3_collection_name = _t3_collection_name
    nexus_pkg = ModuleType("nexus")

    monkeypatch.setitem(sys.modules, "nexus", nexus_pkg)
    monkeypatch.setitem(sys.modules, "nexus.mcp_infra", mcp_infra_mod)
    monkeypatch.setitem(sys.modules, "nexus.corpus", corpus_mod)
    yield calls


# ---- shape validation (no nexus needed) -----------------------------------


def test_rejects_non_string():
    from palinex.nexus_bridge import chash_resolver
    assert chash_resolver(None) is None
    assert chash_resolver(42) is None
    assert chash_resolver({"a": 1}) is None


def test_rejects_wrong_length():
    from palinex.nexus_bridge import chash_resolver
    assert chash_resolver("abc") is None
    assert chash_resolver("a" * 31) is None
    assert chash_resolver("a" * 33) is None


def test_rejects_non_hex():
    from palinex.nexus_bridge import chash_resolver
    assert chash_resolver("g" * 32) is None
    assert chash_resolver("z" * 32) is None
    # Uppercase rejected per RDR-108 (lowercase hex only)
    assert chash_resolver("A" * 32) is None


# ---- lazy import behavior --------------------------------------------------


def test_raises_clear_error_when_nexus_missing(monkeypatch):
    """If nexus isn't importable, the first valid-shape call raises a
    clear ImportError naming the [nexus] extra."""
    import palinex.nexus_bridge as nb
    # Block nexus from being imported
    monkeypatch.setitem(sys.modules, "nexus", None)
    monkeypatch.setitem(sys.modules, "nexus.mcp_infra", None)
    monkeypatch.setitem(sys.modules, "nexus.corpus", None)
    with pytest.raises(ImportError, match=r"pip install palinex\[nexus\]"):
        nb.chash_resolver("a" * 32)


def test_is_available_returns_false_when_nexus_missing(monkeypatch):
    import palinex.nexus_bridge as nb
    monkeypatch.setitem(sys.modules, "nexus", None)
    monkeypatch.setitem(sys.modules, "nexus.mcp_infra", None)
    monkeypatch.setitem(sys.modules, "nexus.corpus", None)
    assert nb.is_available() is False


def test_is_available_returns_true_when_nexus_present(fake_nexus_modules):
    from palinex.nexus_bridge import is_available
    assert is_available() is True


# ---- resolver behavior with mocked nexus -----------------------------------


def test_returns_content_on_t3_hit(fake_nexus_modules):
    from palinex.nexus_bridge import chash_resolver
    chash = "a" * 32
    fake_nexus_modules["_canned"] = {chash: {"content": "resolved chunk text"}}
    assert chash_resolver(chash) == "resolved chunk text"
    assert fake_nexus_modules["get_by_id"] == [("knowledge", chash)]


def test_returns_none_on_t3_miss(fake_nexus_modules):
    from palinex.nexus_bridge import chash_resolver
    chash = "b" * 32
    fake_nexus_modules["_canned"] = {}  # nothing canned → returns None
    assert chash_resolver(chash) is None


def test_returns_none_on_non_string_content(fake_nexus_modules):
    from palinex.nexus_bridge import chash_resolver
    chash = "c" * 32
    fake_nexus_modules["_canned"] = {chash: {"content": {"oops": "structured"}}}
    assert chash_resolver(chash) is None


def test_custom_collection_routed_through(fake_nexus_modules):
    from palinex.nexus_bridge import chash_resolver
    chash = "d" * 32
    fake_nexus_modules["_canned"] = {chash: {"content": "doc text"}}
    chash_resolver(chash, collection="docs")
    assert fake_nexus_modules["t3_collection_name"] == ["docs"]
    assert fake_nexus_modules["get_by_id"][-1][0] == "docs"


def test_swallows_t3_exception(fake_nexus_modules):
    from palinex.nexus_bridge import chash_resolver
    chash = "e" * 32

    def boom(col, doc_id):
        raise RuntimeError("simulated T3 failure")

    # Override the fake's get_by_id to raise
    sys.modules["nexus.mcp_infra"].get_t3().get_by_id = boom
    # Returns None (logs warning); doesn't raise
    assert chash_resolver(chash) is None


# ---- cache behavior -------------------------------------------------------


def test_cache_avoids_repeated_import(fake_nexus_modules):
    """Repeated calls don't re-run the import logic — cache hit on _NEXUS_AVAILABLE."""
    import palinex.nexus_bridge as nb
    chash = "f" * 32
    fake_nexus_modules["_canned"] = {chash: {"content": "x"}}
    nb.chash_resolver(chash)
    assert nb._NEXUS_AVAILABLE is True
    # Second call: still cached, still works
    nb.chash_resolver(chash)
    assert nb._NEXUS_AVAILABLE is True


def test_cache_remembers_failure(monkeypatch):
    """Failed import is cached so we don't pay the import cost repeatedly."""
    import palinex.nexus_bridge as nb
    monkeypatch.setitem(sys.modules, "nexus", None)
    monkeypatch.setitem(sys.modules, "nexus.mcp_infra", None)
    monkeypatch.setitem(sys.modules, "nexus.corpus", None)
    # First call raises
    with pytest.raises(ImportError):
        nb.chash_resolver("a" * 32)
    # Cache now holds the ImportError; second call also raises with same shape
    assert isinstance(nb._NEXUS_AVAILABLE, ImportError)
    with pytest.raises(ImportError, match="palinex\\[nexus\\]"):
        nb.chash_resolver("a" * 32)
