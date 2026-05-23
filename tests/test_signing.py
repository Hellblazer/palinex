# SPDX-License-Identifier: Apache-2.0
"""Producer-side signing tests for palinex.signing (RDR-004 Phase 4b).

Behavioural tests for Surface signing, payload verification, and the
in-memory replay cache. The companion structural tests for the RDR-004
design doc live in tests/test_rdr_004_structure.py.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone

import pytest

from palinex import Surface
from palinex.signing import (
    FreshnessError,
    IdentityError,
    MalformedTrustError,
    ReplayCache,
    SignatureError,
    SigningKey,
    TrustError,
    sign_payload,
    verify_payload,
)


# ---------------------------------------------------------------------------
# SigningKey
# ---------------------------------------------------------------------------


def test_signing_key_generate_round_trips() -> None:
    k = SigningKey.generate()
    raw = k.to_bytes()
    assert len(raw) == 32, "Ed25519 raw private key must be 32 bytes"
    k2 = SigningKey.from_seed(raw)
    assert k.producer_id == k2.producer_id
    assert k.public_key_bytes == k2.public_key_bytes


def test_signing_key_from_seed_rejects_wrong_length() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        SigningKey.from_seed(b"short")
    with pytest.raises(ValueError, match="32 bytes"):
        SigningKey.from_seed(b"x" * 31)


def test_producer_id_format() -> None:
    k = SigningKey.generate()
    pid = k.producer_id
    assert pid.startswith("k_"), "producerId MUST start with 'k_' per RDR-004 §Item 1"
    # base64url alphabet plus the k_ prefix
    body = pid[2:]
    assert all(c.isalnum() or c in "-_" for c in body), f"bad b64url chars: {pid!r}"
    # SHA-256 base64url-no-padding is exactly 43 chars
    assert len(body) == 43, f"k_<43-char-fp> expected, got {len(body)} chars"


def test_producer_id_deterministic_from_pubkey() -> None:
    seed = b"\x01" * 32
    k1 = SigningKey.from_seed(seed)
    k2 = SigningKey.from_seed(seed)
    assert k1.producer_id == k2.producer_id, "same seed must yield same producerId"


# ---------------------------------------------------------------------------
# sign_payload happy path
# ---------------------------------------------------------------------------


def _basic_payload() -> dict:
    return {
        "version": "v0.9",
        "createSurface": {"surfaceId": "s1", "catalogId": "a2ui.basic"},
    }


def test_sign_payload_roundtrip() -> None:
    key = SigningKey.generate()
    payload = _basic_payload()
    signed = sign_payload(payload, key, actions=["openChash"], producer_name="test.signer")
    trust = verify_payload(signed)
    assert trust["producerId"] == key.producer_id
    assert trust["producerName"] == "test.signer"
    assert trust["actions"] == ["openChash"]
    assert trust["algorithm"] == "Ed25519"


def test_sign_payload_does_not_mutate_input() -> None:
    key = SigningKey.generate()
    original = _basic_payload()
    original_str = json.dumps(original, sort_keys=True)
    sign_payload(original, key, actions=["openUrl"])
    assert json.dumps(original, sort_keys=True) == original_str, "input must not be mutated"


def test_sign_payload_includes_all_required_trust_fields() -> None:
    key = SigningKey.generate()
    signed = sign_payload(_basic_payload(), key, actions=["openChash"])
    trust = signed["trust"]
    required = {
        "producerId", "publicKey", "algorithm", "actions",
        "issuedAt", "expiresAt", "nonce", "signature",
    }
    assert required.issubset(trust.keys()), f"missing: {required - set(trust.keys())}"


def test_sign_payload_producer_name_is_optional() -> None:
    key = SigningKey.generate()
    signed = sign_payload(_basic_payload(), key, actions=["openChash"])
    assert "producerName" not in signed["trust"]
    verify_payload(signed)  # still verifies


def test_signed_payload_is_json_serialisable() -> None:
    key = SigningKey.generate()
    signed = sign_payload(_basic_payload(), key, actions=["openChash"])
    s = json.dumps(signed)
    reparsed = json.loads(s)
    verify_payload(reparsed)


# ---------------------------------------------------------------------------
# sign_payload rejection cases (malformed inputs)
# ---------------------------------------------------------------------------


def test_sign_payload_rejects_empty_actions() -> None:
    key = SigningKey.generate()
    with pytest.raises(MalformedTrustError, match="actions"):
        sign_payload(_basic_payload(), key, actions=[])


def test_sign_payload_rejects_non_string_actions() -> None:
    key = SigningKey.generate()
    with pytest.raises(MalformedTrustError, match="actions"):
        sign_payload(_basic_payload(), key, actions=["openUrl", ""])
    with pytest.raises(MalformedTrustError, match="actions"):
        sign_payload(_basic_payload(), key, actions=["openUrl", 123])  # type: ignore[list-item]


def test_sign_payload_rejects_existing_trust_block() -> None:
    key = SigningKey.generate()
    payload = _basic_payload()
    payload["trust"] = {"producerId": "k_evil"}
    with pytest.raises(MalformedTrustError, match="already has"):
        sign_payload(payload, key, actions=["openUrl"])


def test_sign_payload_rejects_ttl_too_long() -> None:
    key = SigningKey.generate()
    with pytest.raises(ValueError, match="3600"):
        sign_payload(_basic_payload(), key, actions=["openUrl"], ttl_seconds=3601)


def test_sign_payload_rejects_ttl_non_positive() -> None:
    key = SigningKey.generate()
    with pytest.raises(ValueError, match="positive"):
        sign_payload(_basic_payload(), key, actions=["openUrl"], ttl_seconds=0)
    with pytest.raises(ValueError, match="positive"):
        sign_payload(_basic_payload(), key, actions=["openUrl"], ttl_seconds=-10)


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
def test_sign_payload_rejects_non_finite_floats(bad_value: float) -> None:
    """RDR-004 critic finding: NaN/Infinity must fail closed before signing."""
    key = SigningKey.generate()
    payload = _basic_payload()
    payload["data"] = {"value": bad_value}
    with pytest.raises(MalformedTrustError, match=r"non-finite"):
        sign_payload(payload, key, actions=["openUrl"])


def test_sign_payload_rejects_short_nonce() -> None:
    key = SigningKey.generate()
    with pytest.raises(ValueError, match="16 bytes"):
        sign_payload(_basic_payload(), key, actions=["openUrl"], nonce=b"short")


def test_sign_payload_rejects_naive_datetime() -> None:
    key = SigningKey.generate()
    with pytest.raises(ValueError, match="timezone"):
        sign_payload(
            _basic_payload(),
            key,
            actions=["openUrl"],
            issued_at=datetime(2026, 5, 23, 12, 0, 0),  # no tzinfo
        )


# ---------------------------------------------------------------------------
# verify_payload rejection cases (tampered/malformed inputs)
# ---------------------------------------------------------------------------


def test_verify_rejects_missing_trust_block() -> None:
    with pytest.raises(MalformedTrustError, match="no `trust` block"):
        verify_payload(_basic_payload())


def test_verify_rejects_non_dict_trust() -> None:
    payload = _basic_payload()
    payload["trust"] = "not-an-object"
    with pytest.raises(MalformedTrustError, match="must be an object"):
        verify_payload(payload)


def test_verify_rejects_missing_required_fields() -> None:
    key = SigningKey.generate()
    signed = sign_payload(_basic_payload(), key, actions=["openUrl"])
    del signed["trust"]["nonce"]
    with pytest.raises(MalformedTrustError, match="missing required fields"):
        verify_payload(signed)


def test_verify_rejects_unsupported_algorithm() -> None:
    key = SigningKey.generate()
    signed = sign_payload(_basic_payload(), key, actions=["openUrl"])
    signed["trust"]["algorithm"] = "ES256"
    with pytest.raises(MalformedTrustError, match="algorithm"):
        verify_payload(signed)


def test_verify_rejects_producer_id_mismatch() -> None:
    """Critical: prevents an attacker from forging a producerId different from the pubkey hash."""
    key_a = SigningKey.generate()
    key_b = SigningKey.generate()
    signed = sign_payload(_basic_payload(), key_a, actions=["openUrl"])
    # Substitute producerId with another producer's fingerprint
    signed["trust"]["producerId"] = key_b.producer_id
    with pytest.raises(IdentityError, match="does not match"):
        verify_payload(signed)


def test_verify_rejects_byte_tampered_payload() -> None:
    key = SigningKey.generate()
    signed = sign_payload(_basic_payload(), key, actions=["openUrl"])
    # Tamper a content field
    signed["createSurface"]["surfaceId"] = "s2-tampered"
    with pytest.raises(SignatureError):
        verify_payload(signed)


def test_verify_rejects_tampered_actions_list() -> None:
    """Channel-tamper attacker tries to expand the allowlist after signing."""
    key = SigningKey.generate()
    signed = sign_payload(_basic_payload(), key, actions=["openChash"])
    signed["trust"]["actions"] = ["openChash", "openFile"]  # attacker adds openFile
    with pytest.raises(SignatureError):
        verify_payload(signed)


def test_verify_rejects_tampered_signature() -> None:
    key = SigningKey.generate()
    signed = sign_payload(_basic_payload(), key, actions=["openUrl"])
    sig = signed["trust"]["signature"]
    # Flip a bit in the signature
    raw = base64.urlsafe_b64decode(sig + "=" * ((-len(sig)) % 4))
    flipped = bytes([raw[0] ^ 0x01]) + raw[1:]
    signed["trust"]["signature"] = base64.urlsafe_b64encode(flipped).rstrip(b"=").decode("ascii")
    with pytest.raises(SignatureError):
        verify_payload(signed)


def test_verify_rejects_expired_payload() -> None:
    key = SigningKey.generate()
    # Sign with issued_at 2 hours ago, ttl 3600s — expiresAt is 1h ago.
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    signed = sign_payload(_basic_payload(), key, actions=["openUrl"],
                          issued_at=past, ttl_seconds=3600)
    with pytest.raises(FreshnessError, match="expired"):
        verify_payload(signed)


def test_verify_rejects_far_future_issuance() -> None:
    """Producer can't issue a payload >60s into the future (clock-skew tolerance)."""
    key = SigningKey.generate()
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    signed = sign_payload(_basic_payload(), key, actions=["openUrl"], issued_at=future)
    with pytest.raises(FreshnessError, match="future"):
        verify_payload(signed)


def test_verify_accepts_with_explicit_now() -> None:
    key = SigningKey.generate()
    signed = sign_payload(_basic_payload(), key, actions=["openUrl"])
    issued = datetime.fromisoformat(signed["trust"]["issuedAt"].replace("Z", "+00:00"))
    # 30 minutes after issuance — within ttl, should verify.
    verify_payload(signed, now=issued + timedelta(minutes=30))


# ---------------------------------------------------------------------------
# JCS canonicalization invariants
# ---------------------------------------------------------------------------


def test_signature_stable_under_key_reordering() -> None:
    """JCS sorts keys; reordering source dict yields the same canonical bytes."""
    key = SigningKey.generate()
    signed = sign_payload(_basic_payload(), key, actions=["openUrl"])
    # Reorder the top-level keys
    reordered = dict(reversed(list(signed.items())))
    # And the trust block keys
    reordered["trust"] = dict(reversed(list(reordered["trust"].items())))
    verify_payload(reordered)  # must still verify


def test_signature_is_deterministic_per_inputs() -> None:
    """Ed25519 is deterministic; same payload + key + nonce + time → same signature."""
    key = SigningKey.from_seed(b"\x42" * 32)
    fixed_time = datetime(2026, 5, 23, 12, 0, 0, tzinfo=timezone.utc)
    fixed_nonce = b"\xaa" * 16
    p1 = _basic_payload()
    p2 = _basic_payload()
    s1 = sign_payload(p1, key, actions=["openUrl"], issued_at=fixed_time, nonce=fixed_nonce)
    s2 = sign_payload(p2, key, actions=["openUrl"], issued_at=fixed_time, nonce=fixed_nonce)
    assert s1["trust"]["signature"] == s2["trust"]["signature"]


# ---------------------------------------------------------------------------
# ReplayCache
# ---------------------------------------------------------------------------


def test_replay_cache_first_sighting_ok() -> None:
    cache = ReplayCache()
    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    assert cache.check_and_record("k_abc", "nonce-1", expires) is True


def test_replay_cache_second_sighting_denies() -> None:
    cache = ReplayCache()
    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    assert cache.check_and_record("k_abc", "nonce-1", expires) is True
    assert cache.check_and_record("k_abc", "nonce-1", expires) is False


def test_replay_cache_different_producers_dont_collide() -> None:
    cache = ReplayCache()
    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    assert cache.check_and_record("k_abc", "nonce-1", expires) is True
    assert cache.check_and_record("k_xyz", "nonce-1", expires) is True


def test_replay_cache_different_nonces_dont_collide() -> None:
    cache = ReplayCache()
    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    assert cache.check_and_record("k_abc", "nonce-1", expires) is True
    assert cache.check_and_record("k_abc", "nonce-2", expires) is True


def test_replay_cache_evicts_expired_entries() -> None:
    cache = ReplayCache()
    now = datetime.now(timezone.utc)
    expires_soon = now + timedelta(seconds=1)
    assert cache.check_and_record("k_abc", "nonce-1", expires_soon, now=now) is True
    # Force a later "now" past expiry → entry should be evicted, so the same
    # nonce is OK again. (In practice you'd never reuse a nonce; this just
    # asserts the cache doesn't grow unboundedly.)
    later = now + timedelta(seconds=5)
    assert cache.check_and_record("k_abc", "nonce-1", expires_soon, now=later) is True


# ---------------------------------------------------------------------------
# Surface.sign() integration
# ---------------------------------------------------------------------------


def test_surface_sign_produces_verifiable_payload() -> None:
    s = Surface(surface_id="test-1", catalog_id="a2ui.basic")
    body = s.text("Hello signed surface")
    s.set_root(body)
    key = SigningKey.generate()
    signed = s.sign(key, actions=["openUrl"], producer_name="test.surface")
    trust = verify_payload(signed)
    assert trust["producerName"] == "test.surface"
    assert "openUrl" in trust["actions"]
    # The signed payload should still carry the original messages
    assert "messages" in signed or "createSurface" in signed


def test_surface_sign_idempotent_for_emit() -> None:
    """Calling sign() twice should produce two independent valid envelopes."""
    s = Surface(surface_id="test-2", catalog_id="a2ui.basic")
    s.set_root(s.text("hi"))
    key = SigningKey.generate()
    sig1 = s.sign(key, actions=["openUrl"])
    sig2 = s.sign(key, actions=["openUrl"])
    # Different nonces and issuedAt → different signatures
    verify_payload(sig1)
    verify_payload(sig2)


def test_trust_error_base_class() -> None:
    """All four signing-related errors inherit from TrustError for easy except-handling."""
    assert issubclass(SignatureError, TrustError)
    assert issubclass(IdentityError, TrustError)
    assert issubclass(FreshnessError, TrustError)
    assert issubclass(MalformedTrustError, TrustError)
