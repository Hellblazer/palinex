---
title: "Trust-Gate Signature: Producer-Identity Claims and Host-Enforced Action Allowlists for a2ui Surfaces"
id: RDR-004
type: Security
status: draft
priority: high
author: Hal Hildebrand
reviewed-by: pending
created: 2026-05-23
related_rdrs: [RDR-001]
related_external: [a2ui-v0.9-spec, rfc-8032-ed25519, rfc-8037-jose-okp, rfc-8785-jcs]
---

# RDR-004: Trust-Gate Signature

> Identity = key fingerprint. Signature = Ed25519 over canonical JSON. Gate sits
> at the host bridge, not in the renderer.

## Problem Statement

RDR-001 §Item 7 ("Action allowlist for v1") commits palinex to a three-action
first-class set (`openUrl`, `copyToClipboard`, `openChash`) and routes
everything else through the postMessage RPC bridge under the informal rule
"default host-bridge behaviour: log but don't execute". The trust posture is
described as **producer-side discipline** — the producer is supposed to only
emit safe URLs, only invoke its own skills, only ask for chashes it has
permission to read.

Producer-side discipline is not a security boundary. Three failure modes are
unaddressed by the v1 design:

1. **Channel tamper.** A malicious intermediary (compromised MCP proxy, cached
   payload someone edited, untrusted iframe boundary) modifies the payload
   in transit and substitutes its own action (`openFile "/etc/passwd"`,
   `runSkill "exfiltrate"`). The producer never saw the modified payload;
   the host has no way to detect the tamper.
2. **Producer impersonation.** A producer the host has never seen sends a
   payload claiming to be `nexus.nx_answer`. The host bridge has no
   self-authenticating way to reject the claim — current "trust" is
   string-identifier-based at best, or absent.
3. **Action escalation by composition.** A producer the host trusts for
   `openChash` (read-only) emits a payload that *also* invokes `openFile`
   (write-capable). Current design has no per-producer-per-action gate; if
   the host implements `openFile` at all, any producer can call it.

This RDR defines a host-enforced gate: a producer signs its payload; the host
verifies the signature against a pinned public key; the host policy maps each
known producer to a set of allowed actions; the gate denies anything outside
the intersection.

### Enumerated gaps to close

1. **No self-authenticating producer identity.** Current model assumes named
   trust (`producer: "nexus"`) which is trivially forgeable.
2. **No tamper detection.** Without an integrity tag covering the payload,
   any channel-tamper attacker wins.
3. **No per-producer authorization.** All known producers get the same
   action surface; least-privilege is not expressible.
4. **No revocation mechanism.** If a producer's signing key is compromised,
   there is no way to tell existing hosts "stop trusting this key".

### Known limitations not closed by this RDR

This RDR closes gaps 1–4 at the **method-name** level and at the
**payload-integrity** level. Two further gaps are acknowledged as
out-of-scope and tracked as follow-up beads under the same Phase 3:

5. **Method-parameter scoping (the confused-deputy gap).** Even with a
   per-producer action allowlist, a producer trusted for `openChash` can
   request *any* chash — including chashes that belong to other
   producers' data. The method-name gate cannot prevent param-level
   escalation. Closing this requires param schemas in the trust store
   (e.g. `"openChash": {"chash_prefix": "sha384:nexus/"}`). Deferred to
   a follow-up bead; this RDR explicitly notes that "trusted for method X"
   does not mean "trusted for every parameterisation of X".
6. **Operator UX for log-only → deny migration.** Default-log-only
   preserves backward compat but provides no tooling to help operators
   decide when their producer ecosystem is ready for `default_policy:
   "deny"`. A summary report ("you have seen N unsigned payloads in the
   last 30 days") is desirable but out-of-scope. Deferred to a follow-up
   bead.

## Context

### What palinex is (recap from RDR-001)

A Python producer library + single-file HTML renderer + reference host
bridge. Three delivery shapes (MCP UI resource, embedded artifact, external
URL). Action allowlist of three first-class actions plus extension methods
routed through the postMessage RPC protocol documented in
`docs/protocols/postmessage-rpc.md` (protocol v1.0).

### Where the trust-gate lives

```
producer → payload (signed) → delivery → renderer → a2ui.request → host bridge → backend
                                                                    ^^^^^^^^^^^
                                                                  trust-gate sits here
```

The host bridge is the boundary between in-iframe rendering and
out-of-iframe execution. Renderer-local actions (`openUrl`,
`copyToClipboard`) bypass the bridge entirely; they execute inside the
sandboxed iframe with no host-side privilege. Bridge-routed actions
(`openChash`, `runSkill`, `openFile`, any extension) are exactly the actions
that reach host-side resources, so that is exactly where the gate must sit.

The renderer SHOULD also verify the signature when it has access to the
producer's public key (loaded via `a2ui.config`); this is defense in depth
for renderer-local actions, not the primary gate.

### Technical environment

- **Ed25519** (RFC 8032): 32-byte private key, 32-byte public key, 64-byte
  signature, deterministic (no nonce-reuse risk), constant-time verify.
- **Python `cryptography` package**: Ed25519 support since v2.6 (2019),
  stable and audited.
- **Web Crypto API**: Ed25519 algorithm name in stable browsers since 2023+
  (Chrome 113, Edge 113, Safari 17, Firefox 130). For older browsers or
  Pyodide-loaded verifier, fallback path uses
  `@noble/ed25519` (single-file ESM, pinned version per
  `html-tool-patterns` discipline).
- **RFC 8785 JCS** (JSON Canonicalization Scheme): deterministic
  serialisation of JSON for signing. Single-pass, key-sorted, no whitespace.
- **postMessage RPC protocol v1.0** (`docs/protocols/postmessage-rpc.md`):
  the channel the gate guards.

### Constraints

- **No PKI.** Hosts pin keys directly. No CA, no DID resolution, no out-of-
  band introduction protocol beyond "operator copies a pubkey into the
  trust store".
- **No daemon.** The trust store is a local file. No revocation server, no
  network calls during verification.
- **Backward compatible.** Existing palinex payloads are unsigned. The
  default policy MUST permit them to render with reduced privilege — a
  flag day on signing would break every existing producer.
- **Apache-2.0.** All chosen libraries are Apache-2.0 or compatible (`cryptography`
  is Apache-2.0/BSD; `@noble/ed25519` is MIT).

## Decision

palinex commits to the following trust-gate architecture. Each numbered item
is a §Approach point eligible for downstream phase-review gating.

### Approach

**Item 1: Producer identity = Ed25519 public-key fingerprint.**

A producer's stable identity is the **base64url-encoded SHA-256 hash of its
Ed25519 public key**, prefixed with `k_` to disambiguate from arbitrary
strings. Example: `k_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789-_ABC`.

The fingerprint is self-authenticating — the producer holds the private key
matching this fingerprint, and no one else does. It is also stable across
key reads (canonical X25519 raw byte form per RFC 8032).

The `trust` block MAY also carry a human-readable `producerName` (e.g.
`"nexus.nx_answer"`) used by host UI for display only. The name is
**non-authoritative**; the host MUST NOT make trust decisions based on the
name field.

**Item 2: Signature scope = canonical JSON of the entire payload minus the
signature field.**

The producer:
1. Builds the surface payload (a2ui v0.9 message envelope or flat shape).
2. Constructs the `trust` block with all fields *except* `signature`.
3. Serialises the resulting object to RFC 8785 JCS canonical JSON.
4. Signs the canonical bytes with Ed25519.
5. Adds the base64url-encoded signature to the `trust` block under
   `signature`.

The host inverts: extracts `trust.signature`, removes it from the object,
canonicalises, verifies. Any byte change anywhere in the payload (renderer
content, action definitions, data model) invalidates the signature.

Algorithm choice rationale: Ed25519 is preferred over ECDSA-P256 because
(a) deterministic — no risk of nonce-reuse compromise, which has shipped
production breaks in ECDSA implementations historically; (b) smaller keys
and signatures; (c) Web Crypto API + `cryptography` both expose it as a
first-class primitive. ES256 is an explicit alternative considered and
rejected in §Alt 2.

**Item 3: Signature lives in the payload as a top-level `trust` block.**

```json
{
  "version": "v0.9",
  "createSurface": { "...": "..." },
  "updateComponents": { "...": "..." },
  "trust": {
    "producerId":   "k_AbCdEf...",
    "producerName": "nexus.nx_answer",
    "publicKey":    "base64url-of-32-byte-Ed25519-pubkey",
    "algorithm":    "Ed25519",
    "actions":      ["openUrl", "copyToClipboard", "openChash", "runSkill"],
    "issuedAt":     "2026-05-23T18:00:00Z",
    "expiresAt":    "2026-05-23T19:00:00Z",
    "nonce":        "base64url-of-16-random-bytes",
    "signature":    "base64url-of-Ed25519-sig"
  }
}
```

Field semantics:

| Field          | Required | Notes                                                   |
|----------------|----------|---------------------------------------------------------|
| `producerId`   | MUST     | `k_` + base64url(SHA-256(publicKey)). Self-authenticates. |
| `producerName` | SHOULD   | Display-only; not authoritative for trust decisions.    |
| `publicKey`    | MUST     | Inline so verifiers don't need a lookup just to verify the signature. Cross-checked against `producerId` and against trust store. |
| `algorithm`    | MUST     | `"Ed25519"`. Future versions MAY add others.            |
| `actions`      | MUST     | Producer's self-declared allowlist. Host intersects with its policy. |
| `issuedAt`     | MUST     | RFC 3339 UTC timestamp; enforces freshness window.      |
| `expiresAt`    | MUST     | RFC 3339 UTC timestamp; MUST be ≤ `issuedAt + 1h`. The host applies the stricter of `expiresAt` and `issuedAt + max_age_seconds` (see Item 5). |
| `nonce`        | MUST     | 16+ bytes of cryptographically random data, base64url-encoded. The bridge tracks seen `(producerId, nonce)` pairs for the freshness window (Item 6) to defeat replay-within-window. |
| `signature`    | MUST     | base64url-encoded Ed25519 signature. Excluded from canonicalization. |

The block lives inline because all three delivery shapes (MCP UI resource,
embedded artifact, external URL) flatten to a single payload object before
reaching the host bridge — there is no separate channel for a sidecar
signature.

**Item 4: Verification at the host bridge; renderer optional defense-in-depth.**

The **host bridge** is the authoritative verifier:

1. On receiving a payload (via `a2ui.load` reflection through the bridge,
   or by holding the payload before forwarding to the renderer), the bridge
   parses `trust` and verifies the signature with `publicKey`.
2. The bridge cross-checks `producerId == "k_" + base64url(SHA-256(publicKey))`.
3. The bridge looks up the producer in its trust store **by `producerId`**
   (see Item 5; the store is keyed on the cryptographic fingerprint, not
   on `producerName`). A scan over `producerId` index is the only
   conforming lookup algorithm.
4. The bridge checks freshness against `effective_expiry = min(expiresAt,
   issuedAt + max_age_seconds)`. If now > effective_expiry, deny.
5. The bridge checks replay: if `(producerId, nonce)` has been seen
   within the freshness window, deny. Otherwise record the pair in an
   in-memory cache scoped to the freshness window. The cache is per-bridge
   and per-session; on bridge restart the cache is empty and the freshness
   window provides the remaining bound.
6. The bridge caches the verification outcome for the lifetime of the
   surface load.
7. On every `a2ui.request {method}` from the renderer, the bridge checks
   `method ∈ trust.actions ∩ trustStore[producerId].allowed_actions`. Deny
   otherwise. Per Gap 5 in the Problem Statement, the bridge does NOT
   inspect `params` for sub-method authorisation in v1 — closing that gap
   is deferred to a follow-up RDR.

The **renderer**:

- **MUST** verify the signature when it has the producer's public key
  available (loaded via `a2ui.config` from the host). When verification
  fails or the producer is not in the renderer's trust store, the renderer
  MUST refuse to execute renderer-local actions (`openUrl`,
  `copyToClipboard`) — these never reach the bridge and are otherwise the
  primary phishing surface (`openUrl` to a malicious domain).
- **MAY** skip verification only in standalone mode (`file://` with no
  parent host), in which case it MUST display a banner: "Standalone mode
  — actions not verified." Standalone mode is an explicitly accepted risk
  documented in Phase 4c.

**Item 5: Host trust store schema.**

Operator-maintained JSON, the same shape whether persisted on disk
(`~/.config/palinex/trust-store.json` by default on a Python host) or in
the browser bridge's `localStorage` under key `a2ui-trust-store.v1`.
Single schema; the storage layer is environment-specific:

```json
{
  "version": 1,
  "keys": {
    "k_AbCdEf...": {
      "publicKey":       "base64url-of-pubkey",
      "producerName":    "nexus.nx_answer",
      "allowed_actions": ["openChash", "copyToClipboard", "openUrl", "runSkill"],
      "denied_actions":  [],
      "max_age_seconds": 3600,
      "valid_until":     "2026-08-01T00:00:00Z"
    },
    "k_XyZqRs...": {
      "publicKey":       "base64url-of-new-pubkey",
      "producerName":    "nexus.nx_answer",
      "allowed_actions": ["openChash", "copyToClipboard", "openUrl", "runSkill"],
      "max_age_seconds": 3600
    }
  },
  "default_policy": "log-only"
}
```

**Key design point:** the trust store is **keyed by `producerId`** (the
cryptographic fingerprint), not by `producerName`. The verifier scans the
`keys` dict using the `trust.producerId` from the incoming payload. The
`producerName` field inside each entry is for display only and SHOULD match
the `trust.producerName` claimed by the payload; a mismatch is logged but
does not affect the trust decision. This unambiguously avoids the
"payload claims `producerName: "evil"` but its `producerId` is registered
under `"nexus.nx_answer"`" lookup ambiguity: the lookup is fingerprint-
based, the name is metadata.

Key rotation is expressed as multiple entries sharing the same
`producerName` and (typically) `allowed_actions`. Soft rotation uses
`valid_until` on the outgoing key; hard revocation removes the entry
entirely.

`default_policy` applies to payloads where:
- the `trust` block is absent (unsigned, backward-compat path), or
- the `producerId` is not present as a key of the `keys` dict.

Three valid values:
- `"deny"`: refuse to forward any RPC; renderer-local actions still
  blocked (consistent with the renderer's MUST-verify rule in Item 4).
- `"log-only"` (default): log the missing/unknown signature; the renderer
  permits `openUrl` and `copyToClipboard` in this mode only when the
  payload is unsigned (backward compat); bridge-routed methods are denied
  with a modal explaining the missing-trust state.
- `"allow"`: permit everything (legacy mode; for development hosts only).

**Item 6: Failure modes and visible recovery.**

| Failure                            | Bridge response                                | Renderer-visible outcome                |
|------------------------------------|------------------------------------------------|------------------------------------------|
| No `trust` block (unsigned)        | Apply `default_policy`                         | If `log-only`: banner "unsigned payload — bridge-routed actions disabled". If `deny`: same banner + no actions execute. |
| `producerId` mismatch with `publicKey` hash | Reject before signature check         | Modal: "Producer identity tampered."     |
| Signature invalid                  | Deny everything                                | Modal: "Signature verification failed — payload integrity broken." |
| `producerId` not in trust store    | Apply `default_policy`                         | Banner: "Unknown producer `<id>` — `<policy>` applied." |
| now > `effective_expiry`           | Deny everything                                | Modal: "Payload expired — `effective_expiry = min(expiresAt, issuedAt + max_age_seconds)`; <duration> past." |
| Replay: `(producerId, nonce)` already seen in window | Deny everything; do NOT update cache | Modal: "Replay detected — payload nonce already accepted this session." |
| Key's `valid_until < now`          | Deny everything                                | Modal: "Producer key rotated out — please refresh from producer." |
| Action ∉ allowlist ∩ self-declared | Deny that one method, log others               | Modal: "Action `<method>` not permitted for producer `<name>`." |
| Param-level escalation (Gap 5)     | Not detected in v1 — explicit known limitation | No modal; logged for operator audit. Closing this requires a follow-up RDR. |

Every failure mode produces a **visible** signal to the user. Silent denial
is explicitly out of scope — RDR-001 §Failure-modes commits to visible
failure as a core architectural property and the trust-gate inherits this
commitment.

**Item 7: Default policy is `log-only` for backward compatibility.**

Existing palinex payloads (0.0.x – 0.3.x) are unsigned. A host that defaults
to `deny` would break every existing producer the day it ships. The default
`log-only` policy:

- Renders unsigned payloads normally.
- Permits renderer-local actions (`openUrl`, `copyToClipboard`).
- Denies bridge-routed actions with a clear banner explaining the missing
  signature.
- Logs every unsigned load for the operator to review.

A host operator MAY set `default_policy: "deny"` once their producer
ecosystem has migrated to signed payloads. The flag-day decision belongs to
the host operator, not to palinex.

### Three concrete scenarios

**Scenario A: nexus producer signing `runSkill` emissions.**

1. nexus has Ed25519 keypair at `~/.nexus/keys/producer-ed25519.json`.
   Fingerprint: `k_aBcDeFg...`.
2. nexus's `nx_answer` builds a surface with a Button bound to
   `runSkill {name:"research"}`.
3. nexus calls
   `Surface.sign(private_key, actions=["runSkill","openChash","copyToClipboard"], producer_name="nexus.nx_answer", ttl_seconds=3600)`.
4. The signed payload is delivered (MCP UI resource shape).
5. Host bridge verifies the signature, finds `k_aBcDeFg...` in trust store
   with `allowed_actions: ["runSkill", "openChash", "copyToClipboard", "openUrl"]`.
6. User clicks Button → renderer posts
   `a2ui.request {method:"runSkill"}` → bridge checks `runSkill ∈
   {runSkill, openChash, copyToClipboard, openUrl} ∩ {runSkill, openChash,
   copyToClipboard}` → permitted → invokes skill → returns result.

**Scenario B: untrusted producer attempting `openFile`.**

1. Producer with key `k_unknownXYZ` (not in trust store) sends a signed
   payload self-declaring `actions: ["openFile"]`.
2. Host bridge verifies signature is valid (the producer correctly signed
   its own claim).
3. Bridge looks up `k_unknownXYZ` — not found.
4. Default policy `log-only` applies: payload renders, banner shown:
   "Unknown producer `k_unknownXYZ` — log-only applied."
5. User clicks Button bound to `openFile` → renderer posts
   `a2ui.request {method:"openFile"}` → bridge denies — modal:
   "Action `openFile` not permitted for unknown producer."
6. `openUrl` and `copyToClipboard` still work (renderer-local), which is
   the documented `log-only` behaviour.

**Scenario C: producer key rotation.**

1. nexus rotates Ed25519 key on day D: old key
   `k_aBcDeFg...` → new key `k_xYzPdQr...`.
2. Host operator updates trust store:
   ```json
   "nexus.nx_answer": {
     "keys": [
       {"producerId": "k_aBcDeFg...", "publicKey": "...", "valid_until": "<D+30d>"},
       {"producerId": "k_xYzPdQr...", "publicKey": "..."}
     ],
     "allowed_actions": [...]
   }
   ```
3. **Day D — D+30**: both keys valid. Cached payloads signed by old key
   verify; new payloads signed by new key also verify.
4. **Day D+30+**: old key past `valid_until`. Old payloads now fail
   verification with the "Producer key rotated out" modal.
5. If the old key was compromised (urgent revocation), operator removes
   the old entry entirely instead of setting `valid_until`. All old
   payloads instantly invalid.

## Alternatives Considered

### Alt 1: did:web producer identity

Use W3C DID `did:web:example.org` as producer identity, resolve via HTTPS
GET to fetch the producer's current public key. Pro: standard, supports
discovery. Rejected because:
- Pulls in DID resolution complexity (URL fetch, JSON-LD context, key-
  binding rules) for one trust decision.
- Requires network access during verification, breaking `file://` and
  air-gapped hosts.
- The pin-key-by-fingerprint model already provides revocation (remove
  from trust store) and rotation (multi-key entry) without a resolution
  protocol.

### Alt 2: ES256 (P-256 ECDSA) instead of Ed25519

ES256 is the JWS default and ubiquitous in OAuth/OIDC ecosystems. Rejected
because:
- ECDSA requires a per-signature nonce; nonce-reuse leaks the private key.
  Production breaks have shipped historically (PS3, multiple Bitcoin
  wallets, Sony's PSN).
- Ed25519 is deterministic; same input always produces same signature, no
  nonce required. This is the more conservative choice for a small
  ecosystem where producers cannot be assumed to have audited PRNGs.
- Web Crypto support for both is now comparable; Ed25519 is the simpler
  primitive to integrate.

ES256 remains as an OPTIONAL future algorithm in case interop with an
existing JOSE-based pipeline becomes necessary; the spec's `algorithm`
field is designed to accommodate the addition.

### Alt 3: Named publisher string identity (no cryptography)

`{"trust": {"producer": "nexus.nx_answer", "level": "high"}}` — host pins
trusted publisher names, no signature. Rejected because the name is not
self-authenticating; anyone can put `"nexus.nx_answer"` in their payload.
This is the current de facto state RDR-001 §Item 7 implicitly relies on,
and it is exactly the gap this RDR closes.

### Alt 4: HTTP header signature (Signature: header per RFC 9421)

Sign the response headers + body using HTTP Message Signatures. Rejected
because the signature wouldn't survive the three delivery shapes:
embedded-artifact carries no HTTP envelope; external-URL distribution
loses headers when shared as a copy-pasted URL; MCP UI resource doesn't
expose host-bridge access to the originating HTTP transaction.

### Alt 5: Sidecar signature file (`.sig` accompanying the payload)

Separate file delivered alongside the payload. Rejected because base64-URL
distribution (`?payload=...`) has no second-file channel; embedded-artifact
inlines the payload as `<script>` content and a sidecar would have to be
inlined too, defeating the point.

### Alt 6: Sign action list only, not the whole payload

Lighter weight — only the `trust.actions` list and a payload hash are
covered. Rejected because the channel-tamper attacker can keep the action
list intact while modifying which Button invokes which action (the action
*targets* live elsewhere in the payload). Whole-payload signing is the
only way to bind the action declaration to its in-payload usage.

### Alt 7: JWS detached signature (RFC 7515 §A.5)

JOSE-standard detached signature with the JCS canonical payload as the
"deteached payload". Considered seriously. Rejected because:
- JWS adds a JOSE header layer (`{"alg":"EdDSA",...}`) that duplicates
  fields already in our `trust` block (`algorithm`, key reference).
- JWS expects base64url-encoded `payload` and `signature` glued by dots;
  for our case the payload IS the carrier object, not a JWS string.
- The standalone `trust` block with named fields is more discoverable for
  someone reading a raw payload than a `eyJh...` compact JWS string.

JWS interop remains an option for a future MINOR (`algorithm: "JWS-EdDSA"`)
if a downstream producer needs to plug into a JWS-based pipeline.

## Trade-offs

### Consequences

- **(+)** Self-authenticating identity (cryptographic fingerprint) closes
  the publisher-impersonation gap with no PKI.
- **(+)** Whole-payload signing catches any tamper, including subtle
  same-allowlist redirection attacks.
- **(+)** Backward compatible: `default_policy: "log-only"` keeps every
  existing unsigned payload working at reduced privilege.
- **(+)** Key rotation is operator-side; no signing service or revocation
  server required.
- **(+)** Renderer can perform defense-in-depth verification for
  renderer-local actions when it has the public key.
- **(−)** Operator burden: host operators must manage a trust store file
  and refresh keys on producer rotation. Mitigated by per-producer
  `valid_until` for soft rotation windows.
- **(−)** Replay window. A signed payload is replayable until `expiresAt`
  (default ≤ 1 h). True anti-replay would require server-side state we
  intentionally exclude.
- **(−)** RFC 8785 JCS canonicalization is implementation-fiddly (number
  formatting, key sorting). Mitigated by pinning a library implementation
  on both producer and verifier sides.

### Risks and Mitigations

- **Risk:** Producer's signing key leaks. *Mitigation:* operator removes
  the compromised `producerId` from the trust store; all payloads signed
  with it immediately fail verification. `valid_until` provides a soft
  window for cooperative rotation; hard removal for compromise.

- **Risk:** Host operator misconfigures `default_policy: "allow"` on a
  production host. *Mitigation:* default is `log-only` (not `allow`);
  the `allow` mode is documented as development-only; visible banners
  fire on every unsigned load even in `allow` mode.

- **Risk:** Browser drops Ed25519 support. *Mitigation:* `@noble/ed25519`
  fallback ESM library, pinned version per `html-tool-patterns`.

- **Risk:** JCS canonicalization disagrees between producer and verifier
  (e.g. number-format edge case). *Mitigation:* test corpus with adversarial
  edge cases (Unicode normalisation, integer vs float, deeply nested
  structures); pin a single JCS library on each side and version-test.

- **Risk:** Producer forgets `actions` list in `trust` block. *Mitigation:*
  REQUIRED field; verifier rejects signed payloads missing the list
  ("malformed trust block"). Better to fail closed than to default-allow.

### Failure modes

- *Visible:* every failure path in the Item 6 table renders either a banner
  (degraded-trust state) or a modal (hard denial). No silent denial.
- *Visible:* host bridge logs every trust decision (allow / deny / fallback)
  so operators can audit producer activity.
- *Recovery:* `default_policy: "log-only"` keeps existing producers
  functional; sign-and-pin is opt-in for hosts that want stronger
  guarantees.

## Implementation Plan

### Phase 4a: Design (this RDR)

- [x] Threat model: channel-tamper, untrusted-producer, key-compromise
  attackers
- [x] Identity claim (Ed25519 pubkey fingerprint)
- [x] Signature scope (whole payload, RFC 8785 JCS, Ed25519)
- [x] Signature location (top-level `trust` block)
- [x] Host verification flow
- [x] Trust store schema
- [x] Failure modes table
- [x] Three concrete scenarios
- [ ] **Substantive-critic gate on this RDR** (run before flipping to
  accepted)

### Phase 4b: Implementation (tracked as bead `palinex-4ae`)

This RDR's acceptance gates Phase 4b. The work splits into producer side,
host side, and tests.

Producer (Python):
- [ ] `palinex.signing.SigningKey` wrapper around
  `cryptography.hazmat.primitives.asymmetric.ed25519`
- [ ] `Surface.sign(private_key, actions, producer_name=None,
  ttl_seconds=3600)` method on the builder, emits the `trust` block
- [ ] RFC 8785 JCS implementation or vendored library (e.g.
  `rfc8785` package on PyPI)
- [ ] `tests/test_signing.py` — sign/verify round-trip, tamper-detection,
  malformed trust block rejection

Host bridge / renderer (JavaScript):
- [ ] Trust verifier module (separate file? `web/trust-gate.html` if
  inlining pushes `host-bridge.html` past 600 LOC; otherwise inline)
- [ ] `web/host-bridge.html` integration: load trust store from
  `localStorage` key `a2ui-trust-store.v1`, run verification before
  forwarding any `a2ui.request`
- [ ] `web/index.html` (renderer) optional defense-in-depth verification
  using same module (pulled in via Pyodide if needed)
- [ ] Web Crypto API path; `@noble/ed25519` fallback

Tests:
- [ ] `tests/test_trust_gate.py` — three scenario corpus (signed
  good-producer, unknown-producer-default-policy, key-rotation)
- [ ] Tamper test: byte-flip every offset, verifier rejects each
- [ ] Browser-side test runnable from Pyodide inspector

RDR updates:
- [ ] RDR-001 §Item 7 amended to reference RDR-004 as the formal mechanism
- [ ] RDR-001 Phase 3 Item 4 checkbox checked off
- [ ] `docs/protocols/postmessage-rpc.md` §5.4 (Trust gate hook) updated to
  reference the now-defined trust-gate

### Phase 4c: Deferred work (not part of palinex-pr1)

- **Gap 5 follow-up: param-level method scoping.** Extend trust store
  entries with `param_constraints` per method (e.g.
  `"openChash": {"chash_prefix": "sha384:nexus/"}`) so a producer trusted
  for `openChash` can only request chashes within its declared namespace.
  Closes the confused-deputy attack at the parameter level. Tracked as
  bead `palinex-rjm`.
- **Gap 6 follow-up: operator-UX tooling for log-only → deny migration.**
  Periodic summary report ("you have seen N unsigned payloads from M
  distinct producers in the last 30 days") so an operator can decide when
  to switch `default_policy` to `deny`. Tracked as bead `palinex-ciy`.
- **Renderer-side MUST-verify** (RDR-004 §Item 4 requirement). The
  Phase 4b implementation (`palinex-4ae`) shipped the bridge-side
  authoritative verifier but deferred the renderer-side check due to
  the renderer's LOC ceiling. Tracked as bead `palinex-rl0`. The
  bridge-side check is the security-critical path; the renderer-side
  is defense-in-depth for renderer-local actions (`openUrl`,
  `copyToClipboard`).
- Trust-store editor UI for host operators.
- Producer-key generation CLI (`palinex keygen`).
- Optional JWS-EdDSA `algorithm` variant for JOSE interop.
- Renderer-side verification in standalone (`file://`) mode — explicitly
  accepted risk for v1 because standalone mode has no trust store.

## Test Plan

- **Scenario:** Sign a typical citation surface in Python, verify the
  signature in a Python test, then verify the same payload using a JS
  reference verifier driven by Pyodide.
  **Verify:** both verifiers accept; tamper any byte, both reject; remove
  the producer from the trust store, both reject with `unknown-producer`
  banner.

- **Scenario:** Producer claims `actions: ["runSkill"]` but payload has a
  Button invoking `openFile`.
  **Verify:** signature still valid (producer signed the payload as-is),
  but host bridge denies the `openFile` RPC with the action-not-in-
  allowlist modal. Confirms intersection-not-union semantics.

- **Scenario:** Sign a payload, set `expiresAt = now - 1 second`, attempt
  verification.
  **Verify:** verifier rejects with expired-payload modal. Then move
  `expiresAt` forward, retry, succeeds. Confirms freshness window.

- **Scenario:** Sign with key A, advance trust store to add key B alongside
  A, sign new payload with B.
  **Verify:** both A-signed and B-signed payloads verify. Then mark A
  `valid_until = now - 1 second`. A-signed payloads now reject; B-signed
  still verify. Confirms key rotation.

- **Scenario:** Unsigned payload (no `trust` block) under
  `default_policy: "log-only"`.
  **Verify:** payload renders; `openUrl` button works; `runSkill` button
  produces deny modal. Confirms backward-compatible degraded-trust mode.

- **Scenario:** JCS canonicalization edge cases — keys in different orders,
  Unicode characters (including NFC/NFD-equivalent strings), integer vs
  float representation.
  **Verify:** producer and verifier produce identical canonical bytes for
  every test input. Catches canonicalization drift early.

- **Scenario:** Producer-side signing library is handed a data model
  containing JSON-illegal values (NaN, +Infinity, -Infinity).
  **Verify:** `Surface.sign()` raises with a clear error pointing at the
  offending path, BEFORE any canonicalization or signing happens. JCS
  inherits RFC 8259's prohibition; the producer must fail closed rather
  than silently serialising as `null`.

- **Scenario:** Channel-tamper attacker captures a signed payload and
  replays it 30 minutes later (within the freshness window).
  **Verify:** first delivery accepted (assuming valid signature); second
  delivery rejected by the replay-cache check on `(producerId, nonce)`.
  Confirms replay protection within the freshness window.

- **Scenario:** Renderer in a host-bridged context with the producer's
  pubkey loaded, receives a payload whose signature does not verify.
  **Verify:** clicking the `openUrl` button does NOT open the URL.
  Confirms the renderer-side MUST-verify rule for renderer-local actions.

- **Scenario:** Trust-store lookup with a payload whose `producerName`
  doesn't match the registered name for its `producerId`.
  **Verify:** trust decision is made on `producerId`; the lookup succeeds;
  the bridge logs the name mismatch as a warning but does not deny.
  Confirms name-is-display-only semantics.

## Validation

### Testing strategy

`tests/test_signing.py` (producer-side) and `tests/test_trust_gate.py`
(end-to-end including JS reference verifier) cover the scenarios above.
Tamper-detection runs against a corpus of representative payloads
(citation surface, multi-component surface, surface with data model).

Substantive-critic agent reviews this RDR before acceptance. Findings are
recorded in §Revision History and addressed inline in the relevant
§Approach items.

### Performance expectations

- Sign a typical citation surface: <10 ms (one Ed25519 sign + JCS canonical
  serialise of ~5 KB payload).
- Verify in browser: <5 ms (Web Crypto Ed25519 verify).
- Trust-store lookup: <0.1 ms (in-memory dict of ~10–100 producers).

The crypto operations are not on the rendering hot path — they fire once
per payload load, not per render.

### Performance expectations (additional caveat)

If a host receives many payloads in quick succession (e.g. an
agent stream emitting one signed surface per second), verifier cost
becomes ~1% of a single core at 100 signed-payloads/sec. Far below the
human-time-scale of any rendering use case.

## Finalization Gate

To be run after Phase 4b lands. Contents will mirror RDR-001's gate:
contradiction check (does shipped code match the design?), assumption
verification (is Web Crypto Ed25519 available in target hosts? is the JCS
library faithful?), scope verification (no silent expansion beyond the
seven items above).

This RDR remains in `draft` until both the substantive-critic gate passes
on the design AND Phase 4b ships, at which point the finalisation gate
runs and the status flips to `accepted`.

## References

- a2ui v0.9 specification — <https://a2ui.org/specification/v0.9-a2ui/>
- RDR-001 (palinex Architecture) — `docs/rdr/rdr-001-architecture.md`,
  §Item 7 (Action allowlist) and §Item 8 (Reference host-bridge wrapper).
  This RDR formalises the trust posture §Item 7 currently describes
  informally.
- postMessage RPC protocol v1.0 — `docs/protocols/postmessage-rpc.md`,
  §5 (Method dispatch) and §5.4 (Trust gate hook). The hook left open by
  the protocol spec is closed by this RDR.
- RFC 8032 — Ed25519 — <https://www.rfc-editor.org/rfc/rfc8032>
- RFC 8037 — JOSE OKP — <https://www.rfc-editor.org/rfc/rfc8037> (for
  reference; not used as the wire format)
- RFC 8785 — JSON Canonicalization Scheme (JCS) —
  <https://www.rfc-editor.org/rfc/rfc8785>
- `cryptography` (Python) — <https://cryptography.io>
- `@noble/ed25519` (browser fallback) — <https://github.com/paulmillr/noble-ed25519>
- Web Crypto Ed25519 (current browser support) —
  <https://caniuse.com/mdn-api_subtlecrypto_sign_ed25519>

## Revision History

_2026-05-23 — initial draft. Captures the trust-gate design described in
palinex bead `palinex-pr1` Phase 4a deliverable. Substantive-critic gate
pending; Phase 4b implementation will be a follow-up bead under the same
RDR._

_2026-05-23 — substantive-critic gate completed; six issues addressed in
this revision (two critical, four significant):_
_- **Critical:** replay-within-freshness-window had no failure-mode row.
  Added a `nonce` field (16+ random bytes) to the `trust` block (Item 3)
  + per-bridge in-memory `(producerId, nonce)` cache (Item 4 step 5).
  Failure modes table gains a "Replay detected" row._
_- **Critical:** openChash confused-deputy at the param level wasn't
  closed by the method-name allowlist. Explicit Gap 5 added to Problem
  Statement with follow-up bead reference; Item 6 failure modes table
  gains a "Param-level escalation" row stating it is a known limitation
  not detected in v1._
_- **Significant:** dual freshness-check paths (`expiresAt` SHOULD vs
  trust store `max_age_seconds`) had no precedence rule. `expiresAt`
  promoted to MUST with cap ≤ `issuedAt + 1h`; effective expiry
  formalised as `min(expiresAt, issuedAt + max_age_seconds)` (Items 3,
  4, 6)._
_- **Significant:** renderer SHOULD-verify rule left renderer-local
  actions (`openUrl`, `copyToClipboard`) vulnerable in misconfigured
  bridges. Renderer-side promoted to MUST when the public key is
  available; standalone (`file://`) mode is an explicitly accepted risk
  documented in Phase 4c._
_- **Significant:** trust store lookup algorithm was underspecified
  (could be keyed on `producerName` or scanned by `producerId`). Schema
  restructured to be keyed by `producerId`, with `producerName` as a
  display-only field inside each entry (Item 5). Eliminates the lookup
  ambiguity._
_- **Significant:** no deprecation signal for log-only default left
  operators with no migration tooling. Explicit Gap 6 added to Problem
  Statement with follow-up bead reference; Phase 4c work item explicit._
_- **Observation:** NaN/Infinity in data model values would silently
  serialise inconsistently. Producer-side `Surface.sign()` MUST raise
  before canonicalization; test plan gains a scenario._
_- **Observation:** trust store schema is identical for Python-on-disk
  and browser-localStorage storage; Item 5 makes this explicit. The
  storage layer differs; the schema does not._
