# SPDX-License-Identifier: Apache-2.0
"""
Producer-side trust-gate signing — Ed25519 over RFC 8785 JCS canonical JSON.

Implements palinex RDR-004 ``docs/rdr/rdr-004-trust-gate-signature.md`` for the
Python producer. The reference host-side verifier lives in
``web/host-bridge.html`` (JavaScript via Web Crypto API); the Python verifier
here is exposed as :func:`verify_payload` for symmetric tests and for hosts
that happen to also run Python.

The five entry points:

- :class:`SigningKey` — wraps an Ed25519 private key, exposes the producer
  identity (``k_<base64url-sha256-of-pubkey>``).
- :func:`sign_payload` — adds a normative ``trust`` block to a payload and
  signs it.
- :func:`verify_payload` — parses ``trust``, verifies signature + identity +
  freshness, returns the parsed trust block.
- :class:`ReplayCache` — in-memory ``(producerId, nonce)`` cache for the
  freshness window per RDR-004 §Item 4 step 5.
- The :class:`TrustError` hierarchy — one exception per failure mode in
  RDR-004 §Item 6.

Producer-side discipline (RDR-004 critic findings):
- NaN / Infinity float values are rejected before canonicalization. JCS
  inherits RFC 8259's prohibition; failing closed here beats silently
  serialising as ``null`` per some JSON encoders.
- ``ttl_seconds`` is capped at 3600 per RDR-004 §Item 3 (``expiresAt`` MUST
  be ≤ ``issuedAt + 1h``).
- The ``actions`` list MUST be non-empty.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import rfc8785  # type: ignore[import-untyped]
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519


__all__ = [
    "ALGORITHM",
    "FreshnessError",
    "IdentityError",
    "MalformedTrustError",
    "ReplayCache",
    "SignatureError",
    "SigningKey",
    "TrustError",
    "sign_payload",
    "verify_payload",
]


ALGORITHM = "Ed25519"
MAX_TTL_SECONDS = 3600
MIN_NONCE_BYTES = 16
CLOCK_SKEW_TOLERANCE_SECONDS = 60

# Required keys on a verified ``trust`` block (RDR-004 §Item 3 field table).
_REQUIRED_TRUST_FIELDS: frozenset[str] = frozenset({
    "producerId", "publicKey", "algorithm", "actions",
    "issuedAt", "expiresAt", "nonce", "signature",
})


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class TrustError(Exception):
    """Base class for every trust-gate verification failure (RDR-004 §Item 6)."""


class SignatureError(TrustError):
    """The Ed25519 signature did not verify against the declared ``publicKey``.

    Raised on tamper anywhere in the payload (data, components, trust fields)
    AND on a forged or bit-flipped signature.
    """


class IdentityError(TrustError):
    """``producerId`` did not equal ``"k_" + base64url(SHA-256(publicKey))``.

    Caught BEFORE the signature check; an attacker substituting a known
    producer's id while keeping their own pubkey gets stopped here.
    """


class FreshnessError(TrustError):
    """``now > effective_expiry`` or ``now + skew < issuedAt`` (RDR-004 §Item 6).

    The effective expiry is ``min(expiresAt, issuedAt + max_age_seconds)``;
    this verifier does not have access to a trust-store ``max_age_seconds``
    so it falls back to the payload-declared ``expiresAt``. Hosts that
    layer their own ``max_age_seconds`` enforce the stricter bound on top.
    """


class MalformedTrustError(TrustError):
    """The ``trust`` block is structurally invalid.

    Examples: missing required field, non-string ``actions`` element,
    NaN/Infinity in the data model (caught producer-side before signing),
    payload already carrying a ``trust`` block when signing.
    """


# ---------------------------------------------------------------------------
# base64url helpers (no padding, per RFC 7515 §2)
# ---------------------------------------------------------------------------


def _b64u_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64u_decode(s: str) -> bytes:
    padding = (-len(s)) % 4
    return base64.urlsafe_b64decode(s + ("=" * padding))


def _fingerprint(pubkey_bytes: bytes) -> str:
    """Compute ``k_<base64url-sha256-of-pubkey>`` per RDR-004 §Item 1."""
    digest = hashlib.sha256(pubkey_bytes).digest()
    return "k_" + _b64u_encode(digest)


# ---------------------------------------------------------------------------
# Producer-side payload sanity (RDR-004 critic finding: NaN/Infinity)
# ---------------------------------------------------------------------------


def _reject_non_finite_floats(obj: Any, path: str = "<root>") -> None:
    """Walk a JSON-serialisable structure; raise on NaN / ±Infinity.

    JCS inherits RFC 8259's prohibition; some JSON encoders silently
    serialise these as ``null``, which would land in the verifier's parsed
    payload as a different value than the producer thought it signed.
    Failing closed here removes the ambiguity.
    """
    if isinstance(obj, float):
        if obj != obj or obj == float("inf") or obj == float("-inf"):
            raise MalformedTrustError(f"non-finite float at {path}: {obj!r}")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _reject_non_finite_floats(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _reject_non_finite_floats(v, f"{path}[{i}]")


# ---------------------------------------------------------------------------
# RFC 3339 timestamp helpers (UTC, seconds precision)
# ---------------------------------------------------------------------------


def _iso(dt: datetime) -> str:
    """Render a UTC RFC 3339 timestamp with ``Z`` suffix, seconds precision."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s: str) -> datetime:
    """Parse RFC 3339; accept ``Z`` suffix or ``+00:00`` form."""
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError) as e:
        raise MalformedTrustError(f"invalid RFC 3339 timestamp: {s!r}") from e


# ---------------------------------------------------------------------------
# SigningKey
# ---------------------------------------------------------------------------


class SigningKey:
    """Ed25519 producer signing key.

    Wraps :class:`cryptography.hazmat.primitives.asymmetric.ed25519.Ed25519PrivateKey`
    plus the producer-identity computation defined in RDR-004 §Item 1.

    Construct one of:

    - :meth:`generate` — random key from the OS CSPRNG.
    - :meth:`from_seed` — deterministic from a 32-byte seed (testing).

    Persist as raw bytes via :meth:`to_bytes`; never log or commit the result.
    """

    __slots__ = ("_private", "_public_bytes", "_producer_id")

    def __init__(self, raw_private: bytes):
        if len(raw_private) != 32:
            raise ValueError(
                f"Ed25519 private key must be 32 bytes, got {len(raw_private)}"
            )
        self._private = ed25519.Ed25519PrivateKey.from_private_bytes(raw_private)
        self._public_bytes = self._private.public_key().public_bytes_raw()
        self._producer_id = _fingerprint(self._public_bytes)

    @classmethod
    def generate(cls) -> SigningKey:
        """Return a new :class:`SigningKey` with a random 32-byte private key."""
        raw = ed25519.Ed25519PrivateKey.generate().private_bytes_raw()
        return cls(raw)

    @classmethod
    def from_seed(cls, seed: bytes) -> SigningKey:
        """Return a :class:`SigningKey` from a 32-byte seed (Ed25519 raw form)."""
        if len(seed) != 32:
            raise ValueError(f"seed must be 32 bytes, got {len(seed)}")
        return cls(seed)

    def to_bytes(self) -> bytes:
        """Return the raw 32-byte Ed25519 private key. Treat as a secret."""
        return self._private.private_bytes_raw()

    @property
    def public_key_bytes(self) -> bytes:
        """The raw 32-byte Ed25519 public key."""
        return self._public_bytes

    @property
    def public_key_b64u(self) -> str:
        """The public key encoded as base64url-no-padding (as it appears in ``trust.publicKey``)."""
        return _b64u_encode(self._public_bytes)

    @property
    def producer_id(self) -> str:
        """The producer identity: ``k_`` + base64url(SHA-256(publicKey))."""
        return self._producer_id

    def sign_bytes(self, data: bytes) -> bytes:
        """Sign raw bytes; returns the 64-byte Ed25519 signature."""
        return self._private.sign(data)


# ---------------------------------------------------------------------------
# sign_payload / verify_payload
# ---------------------------------------------------------------------------


def sign_payload(
    payload: dict[str, Any],
    key: SigningKey,
    actions: list[str],
    *,
    producer_name: str | None = None,
    ttl_seconds: int = MAX_TTL_SECONDS,
    nonce: bytes | None = None,
    issued_at: datetime | None = None,
) -> dict[str, Any]:
    """Add a normative ``trust`` block to ``payload`` and sign it.

    Returns a new payload dict (input is not mutated). The returned object
    is JSON-serialisable and can be round-tripped through :func:`verify_payload`.

    :param payload: the a2ui surface envelope (or flat shape) to sign. MUST NOT
        already contain a ``trust`` block.
    :param key: the producer's :class:`SigningKey`.
    :param actions: producer's self-declared allowlist (RDR-004 §Item 3). The
        host will intersect this with its per-producer policy. MUST be a
        non-empty list of non-empty strings.
    :param producer_name: optional human-readable name (display only; not
        authoritative for trust decisions per RDR-004 §Item 5).
    :param ttl_seconds: payload validity window. Default 3600 (1 hour);
        MUST NOT exceed 3600 per RDR-004 §Item 3.
    :param nonce: 16+ random bytes for replay protection. If ``None``, a
        fresh nonce is generated from the OS CSPRNG.
    :param issued_at: timezone-aware ``datetime`` for ``trust.issuedAt``.
        Defaults to ``datetime.now(timezone.utc)``. MUST be timezone-aware.

    :raises MalformedTrustError: ``actions`` is empty or contains non-string
        / empty entries, ``payload`` already carries ``trust``, or any nested
        value is non-finite (NaN, ±Infinity).
    :raises ValueError: ``ttl_seconds`` is not in ``(0, 3600]``, ``nonce`` is
        shorter than 16 bytes, or ``issued_at`` is naive.
    """
    if not isinstance(actions, list):
        raise MalformedTrustError("actions must be a list")
    if not actions:
        raise MalformedTrustError(
            "actions list MUST be non-empty per RDR-004 §Item 3"
        )
    for i, a in enumerate(actions):
        if not isinstance(a, str) or not a:
            raise MalformedTrustError(
                f"actions[{i}] must be a non-empty string: {a!r}"
            )

    if ttl_seconds <= 0:
        raise ValueError(f"ttl_seconds must be positive, got {ttl_seconds}")
    if ttl_seconds > MAX_TTL_SECONDS:
        raise ValueError(
            f"ttl_seconds MUST be <= {MAX_TTL_SECONDS} per RDR-004 §Item 3, "
            f"got {ttl_seconds}"
        )

    if "trust" in payload:
        raise MalformedTrustError(
            "payload already has a `trust` block; refusing to overwrite"
        )

    # Reject NaN/Infinity BEFORE canonicalization (RDR-004 critic finding).
    _reject_non_finite_floats(payload)

    if issued_at is None:
        issued_at = datetime.now(timezone.utc)
    elif issued_at.tzinfo is None:
        raise ValueError("issued_at must be timezone-aware")

    if nonce is None:
        nonce = secrets.token_bytes(MIN_NONCE_BYTES)
    if len(nonce) < MIN_NONCE_BYTES:
        raise ValueError(
            f"nonce must be at least {MIN_NONCE_BYTES} bytes, got {len(nonce)}"
        )

    expires_at = issued_at + timedelta(seconds=ttl_seconds)

    trust_block: dict[str, Any] = {
        "producerId": key.producer_id,
        "publicKey": key.public_key_b64u,
        "algorithm": ALGORITHM,
        "actions": list(actions),
        "issuedAt": _iso(issued_at),
        "expiresAt": _iso(expires_at),
        "nonce": _b64u_encode(nonce),
    }
    if producer_name is not None:
        trust_block["producerName"] = producer_name

    # Canonicalize the payload-with-trust-but-no-signature, sign, attach.
    signed_payload = {**payload, "trust": trust_block}
    canonical = rfc8785.dumps(signed_payload)
    signature = key.sign_bytes(canonical)
    trust_block["signature"] = _b64u_encode(signature)

    return signed_payload


def verify_payload(
    payload: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Verify a signed payload; return the parsed ``trust`` block on success.

    Verification follows the order in RDR-004 §Item 4:

    1. Structural check on the ``trust`` block.
    2. ``producerId`` cross-check against ``SHA-256(publicKey)``.
    3. Ed25519 signature verification.
    4. Freshness check against ``expiresAt`` and ``issuedAt`` (with a
       60-second clock-skew tolerance for far-future issuance).

    The replay check (RDR-004 §Item 4 step 5) is NOT part of this function —
    it requires per-bridge state and lives in :class:`ReplayCache`. Callers
    are responsible for invoking the cache after :func:`verify_payload`
    returns.

    :param payload: the candidate signed payload.
    :param now: override the current time for testing. Default
        ``datetime.now(timezone.utc)``.

    :raises MalformedTrustError: the ``trust`` block is missing, not a dict,
        or missing one of the eight required fields.
    :raises IdentityError: ``producerId`` does not equal the SHA-256
        fingerprint of ``publicKey``.
    :raises SignatureError: the Ed25519 signature does not verify.
    :raises FreshnessError: ``now`` is past ``expiresAt`` or ``issuedAt`` is
        more than 60 seconds in the future.
    """
    if "trust" not in payload:
        raise MalformedTrustError("payload has no `trust` block")
    trust = payload["trust"]
    if not isinstance(trust, dict):
        raise MalformedTrustError("`trust` block must be an object")

    missing = _REQUIRED_TRUST_FIELDS - set(trust.keys())
    if missing:
        raise MalformedTrustError(
            f"trust block missing required fields: {sorted(missing)}"
        )

    if trust["algorithm"] != ALGORITHM:
        raise MalformedTrustError(
            f"unsupported algorithm: {trust['algorithm']!r} "
            f"(only {ALGORITHM!r} is recognised in v1.0)"
        )

    # 1. Identity cross-check before any signature work.
    try:
        pubkey_bytes = _b64u_decode(trust["publicKey"])
    except (ValueError, TypeError) as e:
        raise MalformedTrustError(f"publicKey is not valid base64url: {e}") from e
    expected_id = _fingerprint(pubkey_bytes)
    if trust["producerId"] != expected_id:
        raise IdentityError(
            f"producerId {trust['producerId']!r} does not match "
            f"k_<sha256(publicKey)>={expected_id!r}"
        )

    # 2. Signature verification over JCS(payload \ {trust.signature}).
    try:
        sig_bytes = _b64u_decode(trust["signature"])
    except (ValueError, TypeError) as e:
        raise MalformedTrustError(f"signature is not valid base64url: {e}") from e

    trust_no_sig = {k: v for k, v in trust.items() if k != "signature"}
    payload_no_sig = {**payload, "trust": trust_no_sig}
    canonical = rfc8785.dumps(payload_no_sig)

    public_key = ed25519.Ed25519PublicKey.from_public_bytes(pubkey_bytes)
    try:
        public_key.verify(sig_bytes, canonical)
    except InvalidSignature as e:
        raise SignatureError(
            "Ed25519 signature verification failed — payload tampered or signed "
            "by a different key"
        ) from e

    # 3. Freshness.
    if now is None:
        now = datetime.now(timezone.utc)
    issued = _parse_iso(trust["issuedAt"])
    expires = _parse_iso(trust["expiresAt"])
    if now > expires:
        raise FreshnessError(
            f"payload expired: expiresAt={trust['expiresAt']}, now={_iso(now)}"
        )
    if issued > now + timedelta(seconds=CLOCK_SKEW_TOLERANCE_SECONDS):
        raise FreshnessError(
            f"payload issued in the future: issuedAt={trust['issuedAt']}, "
            f"now={_iso(now)} (>{CLOCK_SKEW_TOLERANCE_SECONDS}s skew)"
        )

    return trust


# ---------------------------------------------------------------------------
# ReplayCache (RDR-004 §Item 4 step 5)
# ---------------------------------------------------------------------------


@dataclass
class _CacheEntry:
    expires_at: datetime


class ReplayCache:
    """In-memory ``(producerId, nonce)`` cache for the freshness window.

    Per RDR-004 §Item 4 step 5: the bridge tracks pairs it has seen during
    the current session; a second sighting of the same ``(producerId, nonce)``
    is a replay and must be denied.

    Entries are lazily evicted as their associated ``expires_at`` passes —
    once an entry has expired, the freshness check (§Item 4 step 4) would
    reject the payload anyway, so the cache no longer needs to remember it.

    This cache is **per-bridge** and **per-session**. On bridge restart it
    is empty; the freshness window provides the residual bound. Multi-bridge
    deployments do not share this cache — replay-across-bridges is an
    accepted residual risk for v1.0.
    """

    def __init__(self) -> None:
        self._seen: dict[tuple[str, str], _CacheEntry] = {}

    def check_and_record(
        self,
        producer_id: str,
        nonce: str,
        expires_at: datetime,
        *,
        now: datetime | None = None,
    ) -> bool:
        """Record a ``(producerId, nonce)`` sighting.

        :returns: ``True`` if this is the first sighting; ``False`` if the
            pair has been seen within its freshness window (replay).
        """
        if now is None:
            now = datetime.now(timezone.utc)

        # Lazy eviction of every entry whose freshness window has lapsed.
        # The cache is small (one entry per accepted payload per session) so
        # the linear scan is fine; switching to a heap is a future
        # micro-optimisation.
        expired = [k for k, entry in self._seen.items() if entry.expires_at < now]
        for k in expired:
            del self._seen[k]

        key = (producer_id, nonce)
        if key in self._seen:
            return False
        self._seen[key] = _CacheEntry(expires_at=expires_at)
        return True

    def __len__(self) -> int:
        return len(self._seen)
