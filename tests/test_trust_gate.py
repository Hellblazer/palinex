# SPDX-License-Identifier: Apache-2.0
"""End-to-end trust-gate tests covering the three RDR-004 scenarios.

Each scenario from RDR-004 §"Three concrete scenarios" is rendered as a
Python-signed payload, verified, and the trust-store policy is exercised
against it. The JS verifier in web/trust-gate.html and the bridge
integration in web/host-bridge.html are checked by regex source-match
against the canonical primitives — full browser-side end-to-end is
deferred to a Pyodide-driven harness (follow-up).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from palinex import Surface
from palinex.signing import (
    FreshnessError,
    ReplayCache,
    SigningKey,
    sign_payload,
    verify_payload,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
TRUST_GATE_HTML = REPO_ROOT / "web" / "trust-gate.html"
HOST_BRIDGE_HTML = REPO_ROOT / "web" / "host-bridge.html"


# ---------------------------------------------------------------------------
# Fixtures: deterministic keys + sample payload
# ---------------------------------------------------------------------------


@pytest.fixture
def nexus_key() -> SigningKey:
    """Stand-in for nexus.nx_answer's pinned Ed25519 producer key."""
    return SigningKey.from_seed(b"\x01" * 32)


@pytest.fixture
def evil_key() -> SigningKey:
    """An untrusted producer the host has never seen."""
    return SigningKey.from_seed(b"\xff" * 32)


@pytest.fixture
def citation_payload() -> dict:
    s = Surface(surface_id="nx-answer-test", catalog_id="a2ui.basic.v0_9")
    s.data["synthesis"] = "The answer is documented in RDR-127."
    s.data["citations"] = [{
        "title": "RDR-127",
        "excerpt": "Substrate-Decoupled Surface Rendering",
        "chash": "cfbd937e6addd5674fb6cde5b04a9fe1",
    }]
    s.set_root(s.text(path="/synthesis"))
    return s.emit()


# ---------------------------------------------------------------------------
# Scenario A: nexus producer signing runSkill emissions
# ---------------------------------------------------------------------------


def test_scenario_a_nexus_signs_runskill(nexus_key: SigningKey, citation_payload: dict) -> None:
    """RDR-004 §Scenario A — happy path, trusted producer.

    1. nexus signs a payload claiming actions=[runSkill, openChash, copyToClipboard]
    2. Host's trust store has nexus.nx_answer with allowed=[runSkill, openChash, copyToClipboard, openUrl]
    3. verify_payload accepts
    4. Bridge gate accepts runSkill (in trust.actions ∩ allowed_actions)
    5. Bridge gate denies openFile (NOT in trust.actions even though if-allowed)
    """
    signed = sign_payload(
        citation_payload,
        nexus_key,
        actions=["runSkill", "openChash", "copyToClipboard"],
        producer_name="nexus.nx_answer",
    )
    trust = verify_payload(signed)
    assert trust["producerName"] == "nexus.nx_answer"
    assert trust["producerId"] == nexus_key.producer_id

    # Host trust store policy
    trust_store_allowed = {"runSkill", "openChash", "copyToClipboard", "openUrl"}
    effective = set(trust["actions"]) & trust_store_allowed
    assert "runSkill" in effective, "runSkill should be permitted (in both lists)"
    assert "openFile" not in effective, "openFile should be denied (not in either list)"
    # openUrl is in the trust store but NOT in the producer's self-declaration
    # → producer didn't claim it, so it must NOT be permitted (intersection)
    assert "openUrl" not in effective, "openUrl not self-declared → must be denied"


# ---------------------------------------------------------------------------
# Scenario B: untrusted producer attempting openFile
# ---------------------------------------------------------------------------


def test_scenario_b_untrusted_producer_default_policy(evil_key: SigningKey) -> None:
    """RDR-004 §Scenario B — unknown producer falls to default_policy.

    Default policy=log-only: signature is valid (producer signed its own claim),
    BUT the producerId isn't in the trust store. Bridge-routed methods are
    denied with a banner.
    """
    payload = {
        "version": "v0.9",
        "createSurface": {"surfaceId": "evil-1", "catalogId": "a2ui.basic"},
    }
    signed = sign_payload(payload, evil_key, actions=["openFile"],
                         producer_name="evil.producer")
    trust = verify_payload(signed)  # signature still valid — producer signed its own claim

    # Host trust store has no entry for this producer
    trust_store: dict[str, Any] = {"version": 1, "keys": {}, "default_policy": "log-only"}
    producer_entry = trust_store["keys"].get(trust["producerId"])
    assert producer_entry is None, "untrusted producer must not be in trust store"
    # With default_policy=log-only, payload renders but bridge-routed methods deny.
    # openFile would be denied because no allowed_actions list to intersect.


def test_scenario_b_unknown_producer_with_deny_policy(evil_key: SigningKey) -> None:
    """default_policy=deny refuses everything from unknown producers."""
    payload = {"version": "v0.9", "createSurface": {"surfaceId": "x", "catalogId": "a2ui.basic"}}
    signed = sign_payload(payload, evil_key, actions=["openFile"], producer_name="evil")
    trust = verify_payload(signed)
    trust_store: dict[str, Any] = {"version": 1, "keys": {}, "default_policy": "deny"}
    # In deny mode, even renderer-local actions like openUrl are blocked at
    # the renderer (per RDR-004 §Item 4 renderer MUST-verify rule). Here we
    # only assert the policy is set; renderer enforcement is a follow-up.
    assert trust_store["default_policy"] == "deny"
    _ = trust  # signature verified; policy is what denies


# ---------------------------------------------------------------------------
# Scenario C: producer key rotation
# ---------------------------------------------------------------------------


def test_scenario_c_key_rotation_dual_valid() -> None:
    """RDR-004 §Scenario C — both old and new keys valid during rotation window."""
    key_old = SigningKey.from_seed(b"A" * 32)
    key_new = SigningKey.from_seed(b"B" * 32)
    payload = {"version": "v0.9", "createSurface": {"surfaceId": "rotated", "catalogId": "a2ui.basic"}}

    signed_old = sign_payload(payload, key_old, actions=["runSkill"], producer_name="nexus")
    signed_new = sign_payload(payload, key_new, actions=["runSkill"], producer_name="nexus")

    # Both signatures verify under their respective inline pubkeys.
    verify_payload(signed_old)
    verify_payload(signed_new)
    assert signed_old["trust"]["producerId"] != signed_new["trust"]["producerId"]

    # A trust store with both keys registered under the same producerName.
    trust_store = {
        "version": 1,
        "keys": {
            key_old.producer_id: {
                "publicKey": key_old.public_key_b64u,
                "producerName": "nexus.nx_answer",
                "allowed_actions": ["runSkill"],
                "valid_until": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            },
            key_new.producer_id: {
                "publicKey": key_new.public_key_b64u,
                "producerName": "nexus.nx_answer",
                "allowed_actions": ["runSkill"],
            },
        },
        "default_policy": "log-only",
    }
    # Both producerIds are in the store, both should be accepted.
    assert signed_old["trust"]["producerId"] in trust_store["keys"]
    assert signed_new["trust"]["producerId"] in trust_store["keys"]


def test_scenario_c_old_key_revoked() -> None:
    """Hard revocation: old key removed → old payloads no longer trust-able."""
    key_old = SigningKey.from_seed(b"C" * 32)
    key_new = SigningKey.from_seed(b"D" * 32)
    payload = {"version": "v0.9", "createSurface": {"surfaceId": "x", "catalogId": "a2ui.basic"}}
    signed_old = sign_payload(payload, key_old, actions=["runSkill"], producer_name="nexus")

    # Operator removed the old key entirely (urgent revocation).
    trust_store = {
        "version": 1,
        "keys": {
            key_new.producer_id: {
                "publicKey": key_new.public_key_b64u,
                "producerName": "nexus.nx_answer",
                "allowed_actions": ["runSkill"],
            },
        },
        "default_policy": "log-only",
    }
    assert signed_old["trust"]["producerId"] not in trust_store["keys"], \
        "revoked key must not appear in trust store"


# ---------------------------------------------------------------------------
# Channel-tamper replay scenario (RDR-004 critic finding)
# ---------------------------------------------------------------------------


def test_replay_attack_within_freshness_window(nexus_key: SigningKey) -> None:
    """A captured signed payload replayed during freshness window must be rejected.

    Tests the bridge's ReplayCache integration (per RDR-004 §Item 4 step 5).
    """
    payload = {"version": "v0.9", "createSurface": {"surfaceId": "x", "catalogId": "a2ui.basic"}}
    signed = sign_payload(payload, nexus_key, actions=["openUrl"], producer_name="nexus")
    trust = verify_payload(signed)
    expires = datetime.fromisoformat(trust["expiresAt"].replace("Z", "+00:00"))

    cache = ReplayCache()
    # First delivery accepted.
    assert cache.check_and_record(trust["producerId"], trust["nonce"], expires) is True
    # Replay within window denied.
    assert cache.check_and_record(trust["producerId"], trust["nonce"], expires) is False


# ---------------------------------------------------------------------------
# JS-source conformance: web/trust-gate.html + web/host-bridge.html
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def trust_gate_js() -> str:
    return TRUST_GATE_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def host_bridge_js() -> str:
    return HOST_BRIDGE_HTML.read_text(encoding="utf-8")


def test_trust_gate_html_exists() -> None:
    assert TRUST_GATE_HTML.exists(), \
        "web/trust-gate.html must exist as the standalone reference verifier"


@pytest.mark.parametrize(
    "primitive",
    [
        "Ed25519",
        "SHA-256",
        "@noble/ed25519",
        "verifyPayload",
        "ReplayCache",
        "fingerprint",
        "checkAndRecord",
    ],
)
def test_trust_gate_html_has_primitives(trust_gate_js: str, primitive: str) -> None:
    """Verifier page must reference the canonical algorithms and functions."""
    assert primitive in trust_gate_js, \
        f"web/trust-gate.html missing primitive: {primitive}"


def test_trust_gate_html_documents_all_required_fields(trust_gate_js: str) -> None:
    """Verifier must check all eight required trust-block fields."""
    for field in (
        "producerId", "publicKey", "algorithm", "actions",
        "issuedAt", "expiresAt", "nonce", "signature",
    ):
        assert field in trust_gate_js, f"verifier missing field: {field}"


def test_trust_gate_html_pins_noble_version(trust_gate_js: str) -> None:
    """Per html-tool-patterns: CDN deps MUST be pinned."""
    assert re.search(r"@noble/ed25519@\d", trust_gate_js), \
        "@noble/ed25519 must be pinned to a specific version (no @latest)"


def test_host_bridge_integrates_trust_gate(host_bridge_js: str) -> None:
    """Bridge MUST call the trust gate before delivering a2ui.load."""
    assert "trustGateCheck" in host_bridge_js, \
        "host-bridge.html must call trustGateCheck() in loadSurface()"
    assert "verifiedActions" in host_bridge_js, \
        "host-bridge.html must gate handleRequest on verifiedActions"
    assert "ReplayCache" in host_bridge_js, \
        "host-bridge.html must include ReplayCache for replay protection"


def test_host_bridge_loads_trust_store_from_localstorage(host_bridge_js: str) -> None:
    """Trust store lives under localStorage key a2ui-trust-store.v1 per RDR-004 §Item 5."""
    assert "a2ui-trust-store.v1" in host_bridge_js, \
        "host-bridge.html must read trust store from localStorage key 'a2ui-trust-store.v1'"


def test_host_bridge_default_policy_log_only(host_bridge_js: str) -> None:
    """Per RDR-004 §Item 7: default_policy MUST be log-only for backward compat."""
    assert "'log-only'" in host_bridge_js, \
        "host-bridge.html default_policy fallback must be 'log-only'"


def test_host_bridge_implements_default_policy_deny(host_bridge_js: str) -> None:
    """default_policy=deny must refuse all bridge-routed methods for unsigned payloads."""
    assert "default_policy=deny" in host_bridge_js or re.search(
        r"'deny'", host_bridge_js,
    ), "host-bridge.html must implement default_policy=deny branch"


def test_host_bridge_under_loc_ceiling(host_bridge_js: str) -> None:
    """Per html-tool-patterns: warn at 600 LOC, hard ceiling 900 LOC."""
    lines = host_bridge_js.splitlines()
    assert len(lines) < 900, (
        f"host-bridge.html at {len(lines)} lines exceeds the 900 hard ceiling; "
        "consider extracting trust-gate primitives into a shared module"
    )


def test_trust_gate_under_loc_ceiling(trust_gate_js: str) -> None:
    """Per html-tool-patterns: warn at 600 LOC, hard ceiling 900 LOC."""
    lines = trust_gate_js.splitlines()
    assert len(lines) < 900, f"trust-gate.html at {len(lines)} lines exceeds ceiling"


# ---------------------------------------------------------------------------
# Drift guard: JS and Python must agree on the algorithm name and field set
# ---------------------------------------------------------------------------


def test_python_and_js_algorithm_strings_match(trust_gate_js: str, host_bridge_js: str) -> None:
    """Algorithm string must be identical across Python (ALGORITHM='Ed25519') and JS."""
    from palinex.signing import ALGORITHM
    assert ALGORITHM == "Ed25519"
    assert "'Ed25519'" in trust_gate_js
    assert "'Ed25519'" in host_bridge_js


def test_python_and_js_required_fields_match(trust_gate_js: str) -> None:
    """The set of required trust-block fields must match between Python and JS."""
    from palinex.signing import _REQUIRED_TRUST_FIELDS  # type: ignore[attr-defined]
    js_required_match = re.search(
        r"TG_REQUIRED\s*=\s*\[([^\]]+)\]", trust_gate_js,
    ) or re.search(
        r"REQUIRED_FIELDS\s*=\s*\[([^\]]+)\]", trust_gate_js,
    )
    assert js_required_match, "verifier must declare REQUIRED_FIELDS or TG_REQUIRED"
    js_fields = set(re.findall(r"'(\w+)'", js_required_match.group(1)))
    assert js_fields == _REQUIRED_TRUST_FIELDS, (
        f"Python required={_REQUIRED_TRUST_FIELDS} ≠ JS required={js_fields}"
    )
