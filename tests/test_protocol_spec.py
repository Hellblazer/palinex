# SPDX-License-Identifier: Apache-2.0
"""Conformance test for the postMessage RPC protocol spec.

Asserts that the reference implementations under ``web/`` continue to match
the normative claims in ``docs/protocols/postmessage-rpc.md``. If the spec
moves or either implementation drifts, this test fails — preventing silent
divergence between the documented contract and the shipping code.

The checks are deliberately regex-based source matches rather than runtime
behavioural assertions: there is no JS runtime in the pytest matrix, and the
spec's purpose is to describe the wire shape, not internal behaviour.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = REPO_ROOT / "docs" / "protocols" / "postmessage-rpc.md"
RENDERER_PATH = REPO_ROOT / "web" / "index.html"
BRIDGE_PATH = REPO_ROOT / "web" / "host-bridge.html"


@pytest.fixture(scope="module")
def spec_text() -> str:
    assert SPEC_PATH.exists(), f"protocol spec missing: {SPEC_PATH}"
    return SPEC_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def renderer_text() -> str:
    return RENDERER_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def bridge_text() -> str:
    return BRIDGE_PATH.read_text(encoding="utf-8")


# ---- spec self-checks ----


def test_spec_declares_protocol_version(spec_text: str) -> None:
    """Spec MUST declare an explicit protocol version (MAJOR.MINOR)."""
    assert re.search(r"protocol[- ]version[: ]+\s*[`\"]?1\.0[`\"]?", spec_text, re.I), \
        "spec must declare protocol version 1.0"


def test_spec_uses_rfc2119_language(spec_text: str) -> None:
    """Spec MUST use RFC 2119 conformance terminology."""
    for keyword in ("MUST", "SHOULD", "MAY"):
        assert keyword in spec_text, f"spec missing RFC 2119 keyword: {keyword}"


@pytest.mark.parametrize(
    "envelope",
    [
        "a2ui.ready",
        "a2ui.load",
        "a2ui.config",
        "a2ui.request",
        "a2ui.response",
        "a2ui.message",
    ],
)
def test_spec_documents_envelope(spec_text: str, envelope: str) -> None:
    """Spec MUST mention every wire envelope name used by the reference impls."""
    assert envelope in spec_text, f"spec missing envelope: {envelope}"


def test_spec_documents_first_class_methods(spec_text: str) -> None:
    """Spec MUST document the three first-class action methods from RDR-001."""
    for method in ("openChash", "openUrl", "copyToClipboard"):
        assert method in spec_text, f"spec missing method: {method}"


def test_spec_documents_timeout_value(spec_text: str) -> None:
    """Spec MUST state the 10-second renderer-side timeout."""
    assert re.search(r"10\s*s|10\s*000\s*ms|10[, ]?000", spec_text), \
        "spec must declare the 10s renderer-side timeout"


def test_spec_documents_retry_budget(spec_text: str) -> None:
    """Spec MUST state the retry-until-ack budget (~150ms × ~40 attempts ≈ 6s)."""
    assert re.search(r"150\s*ms", spec_text), "spec must declare the 150ms retry interval"
    assert re.search(r"40\s*(attempts|retries|times)", spec_text), \
        "spec must declare the ~40-attempt budget"
    assert re.search(r"6\s*s", spec_text), "spec must declare the ~6s retry budget"


# ---- renderer (index.html) conformance ----


def test_renderer_emits_ready_envelope(renderer_text: str) -> None:
    """Renderer MUST post {type:"a2ui.ready"} to its parent at startup."""
    assert re.search(
        r"postMessage\(\s*\{\s*type:\s*['\"]a2ui\.ready['\"]",
        renderer_text,
    ), "renderer must post {type:'a2ui.ready'} to parent"


def test_renderer_request_envelope_shape(renderer_text: str) -> None:
    """Renderer MUST emit a2ui.request with type, method, requestId, params."""
    pattern = re.compile(
        r"postMessage\(\s*\{\s*type:\s*['\"]a2ui\.request['\"]"
        r"[^}]*method[^}]*requestId[^}]*params",
        re.DOTALL,
    )
    assert pattern.search(renderer_text), \
        "renderer must emit a2ui.request envelope with type/method/requestId/params"


def test_renderer_listens_for_response(renderer_text: str) -> None:
    """Renderer MUST consume a2ui.response messages and dispatch by requestId."""
    assert re.search(
        r"['\"]a2ui\.response['\"][^}]*requestId",
        renderer_text,
    ), "renderer must dispatch a2ui.response by requestId"


def test_renderer_timeout_matches_spec(renderer_text: str) -> None:
    """Renderer MUST time out RPC requests at 10 000 ms."""
    assert "10000" in renderer_text, "renderer must use a 10 000 ms RPC timeout"


def test_renderer_listens_for_load_and_config(renderer_text: str) -> None:
    """Renderer MUST consume a2ui.load (payload) and a2ui.config envelopes."""
    assert re.search(r"['\"]a2ui\.load['\"]", renderer_text)
    assert re.search(r"['\"]a2ui\.config['\"]", renderer_text)


def test_renderer_implements_first_class_actions(renderer_text: str) -> None:
    """Renderer MUST resolve the three first-class actions in-renderer or via bridge."""
    for action in ("openUrl", "copyToClipboard", "openChash"):
        assert action in renderer_text, f"renderer missing first-class action: {action}"


# ---- reference host bridge (host-bridge.html) conformance ----


def test_bridge_handles_request_envelope(bridge_text: str) -> None:
    """Reference bridge MUST listen for a2ui.request and reply with a2ui.response."""
    assert re.search(r"['\"]a2ui\.request['\"]", bridge_text)
    assert re.search(r"['\"]a2ui\.response['\"]", bridge_text)


def test_bridge_uses_request_method_and_id(bridge_text: str) -> None:
    """Bridge MUST dispatch on m.method and echo m.requestId in the reply."""
    assert re.search(r"m\.method", bridge_text), "bridge must dispatch on m.method"
    assert re.search(r"requestId:\s*m\.requestId", bridge_text), \
        "bridge must echo m.requestId on the response"


def test_bridge_replies_with_result_or_error(bridge_text: str) -> None:
    """a2ui.response MUST carry either result or error (per spec error shape)."""
    assert re.search(r"a2ui\.response[^}]*result", bridge_text, re.DOTALL)
    assert re.search(r"a2ui\.response[^}]*error", bridge_text, re.DOTALL)


def test_bridge_exposes_documented_methods(bridge_text: str) -> None:
    """Reference bridge MOCK_BACKEND MUST expose openChash and runSkill methods."""
    assert "openChash" in bridge_text, "reference bridge must expose openChash"
    assert "runSkill" in bridge_text, "reference bridge must expose runSkill"


def test_bridge_implements_retry_until_ack(bridge_text: str) -> None:
    """Bridge MUST implement the retry-until-ack handshake — 150ms × ≥40 attempts."""
    assert re.search(r"a2ui\.ready", bridge_text), "bridge must watch for a2ui.ready"
    assert re.search(r"setInterval\([^,]+,\s*150\s*\)", bridge_text), \
        "bridge must use a 150 ms retry interval"
    assert re.search(r"attempts\s*>=\s*40", bridge_text), \
        "bridge must bound retry at 40 attempts (~6s budget)"


def test_bridge_pushes_config_via_envelope(bridge_text: str) -> None:
    """Bridge MUST deliver host config via {type:"a2ui.config", config:...}."""
    assert re.search(
        r"type:\s*['\"]a2ui\.config['\"]\s*,\s*config:", bridge_text,
    ), "bridge must deliver config as {type:'a2ui.config', config:...}"


# ---- cross-impl invariant ----


def test_spec_self_contained_size(spec_text: str) -> None:
    """Spec SHOULD be substantial enough to implement a bridge without source.

    Heuristic: a spec covering envelope shapes, methods, timeouts, retries, error
    shape, config push, and versioning policy lands around 200+ lines. Below
    150 indicates probable missing sections.
    """
    lines = spec_text.splitlines()
    assert len(lines) >= 150, (
        f"spec at {len(lines)} lines is likely too thin to implement against; "
        "expand the normative sections"
    )


def test_spec_documents_major_mismatch_behaviour(spec_text: str) -> None:
    """§9 MUST specify what each side does when MAJOR versions differ."""
    # The inference rule for "absence == 1.0" must live in §9, not just §4.1.
    assert re.search(
        r"absence of `protocolVersion`.*equivalent to `\"1\.0\"`", spec_text, re.S
    ), "spec must restate the absence==1.0 inference rule inside §9"
    # MAJOR-mismatch normative behaviour for both bridge and renderer.
    assert re.search(r"bridge sees renderer MAJOR", spec_text, re.I), \
        "spec must describe bridge-side MAJOR-mismatch behaviour"
    assert re.search(r"renderer sees bridge MAJOR", spec_text, re.I), \
        "spec must describe renderer-side MAJOR-mismatch behaviour"


def test_spec_resolves_hello_ordering_with_retry_loop(spec_text: str) -> None:
    """§9 MUST resolve the a2ui.hello vs §7 retry-loop sequencing conflict."""
    assert re.search(
        r"MUST NOT resend\s+`a2ui\.hello`\s+on every retry tick", spec_text
    ), "spec must state that a2ui.hello is one-shot, not retried"
    assert re.search(
        r"MUST NOT block processing of\s+`a2ui\.load`\s+on the\s+arrival of\s+`a2ui\.hello`",
        spec_text,
    ), "spec must state that renderer must not block load on hello arrival"
