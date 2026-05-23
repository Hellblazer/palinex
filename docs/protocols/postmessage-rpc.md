---
title: "postMessage RPC Protocol for a2ui Surfaces"
protocol-version: "1.0"
status: stable
applies-to: palinex >= 0.3.0
related: RDR-001 §Item 6
license: Apache-2.0
---

# postMessage RPC Protocol for a2ui Surfaces

This document specifies the `postMessage`-based RPC protocol used by an a2ui
surface renderer (hereafter **renderer**) and its containing host shell
(hereafter **host bridge** or **bridge**) to exchange a2ui v0.9 payloads, push
configuration, and dispatch surface actions back to a host-resolved data
source.

The reference renderer is `web/index.html` in the
[palinex repository](https://github.com/Hellblazer/palinex). The reference
host bridge is `web/host-bridge.html` in the same repository. This document
is the normative contract; both reference implementations conform to it. A
new host bridge — for a Tauri shell, a custom MCP UI host, an HTTP sidecar
index page, or any other embedding — MUST implement the requirements below to
be considered a conforming bridge.

## 1. Status & Scope

- **Protocol version:** `1.0`
- **Status:** stable, frozen for the v1.x line.
- **Scope:** the wire shape of messages exchanged through the
  `Window.postMessage` API between a parent host window and a child renderer
  iframe. Out of scope: the payload schema (defined by
  [a2ui v0.9](https://a2ui.org/specification/v0.9-a2ui/)), the host's data
  source (whatever the bridge chooses to talk to), and the renderer's
  internal state model.

This protocol is independent of palinex's package version. palinex's semver
tracks the a2ui spec version it supports; the protocol version below tracks
the wire contract documented here. A breaking change to envelope shapes bumps
the protocol MAJOR; an additive change (new method, new optional field) bumps
the protocol MINOR.

## 2. Conformance Terminology

The key words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, **MAY**,
**REQUIRED**, **RECOMMENDED**, and **OPTIONAL** in this document are to be
interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)
when, and only when, they appear in all capitals.

## 3. Transport

All messages travel through `Window.postMessage` with `targetOrigin` set to
`"*"` (a wildcard) on both sides. The reference renderer is sandboxed via
`<iframe sandbox="allow-scripts allow-same-origin">`; the bridge is the
parent window.

Implementations MUST treat received messages as untrusted input:

- The bridge MUST verify `event.source === iframe.contentWindow` before
  acting on any message.
- The renderer MUST verify `event.source === window.parent || event.source
  === window` before acting on any message.
- Both sides MUST treat `event.data` as `unknown` until type-narrowed by the
  `type` discriminator (see §4).
- Both sides MUST ignore messages whose `type` they do not recognise.

Using `targetOrigin: "*"` is intentional: the renderer is loaded from a
hosted origin (`hellblazer.github.io` or any user-chosen mirror) and embedded
in hosts whose origins are unknown ahead of time. Origin pinning is left to
the embedder via Content Security Policy `frame-src` / `frame-ancestors`.

## 4. Envelope Shapes

Every message is a JSON-serialisable object with a `type` field whose value
is a string starting with `a2ui.`. The `type` value is the discriminator;
unrecognised types MUST be ignored.

The seven envelopes defined by protocol v1.0 are:

| Envelope        | Direction       | Cardinality        | Purpose                              |
|-----------------|-----------------|--------------------|--------------------------------------|
| `a2ui.ready`    | renderer → host | once per load      | Renderer signals listener installed  |
| `a2ui.load`     | host → renderer | one or more        | Push a full payload                  |
| `a2ui.message` | host → renderer | zero or more       | Push a single a2ui v0.9 message      |
| `a2ui.config`   | host → renderer | zero or more       | Push runtime config (e.g. daemonBase)|
| `a2ui.request`  | renderer → host | many               | RPC call to a host-resolved method   |
| `a2ui.response` | host → renderer | once per request   | RPC reply (result or error)          |
| `a2ui.action`   | renderer → host | fire-and-forget    | Surface action signal (advisory)     |

### 4.1 `a2ui.ready`

The renderer MUST post exactly one `a2ui.ready` message to `window.parent`
immediately after attaching its `message` event listener. It MUST be sent
even when there is no parent (the renderer is opened standalone); the
attempt is allowed to fail silently in that case.

```javascript
{ "type": "a2ui.ready" }
```

The `a2ui.ready` envelope MAY in future protocol minor versions include
optional fields (e.g. `protocolVersion`). v1.0 receivers MUST ignore any
fields they do not recognise. v1.0 receivers MUST treat the absence of a
`protocolVersion` field as equivalent to the value `"1.0"`.

### 4.2 `a2ui.load`

Host pushes a complete payload — either an a2ui v0.9 message envelope
(`createSurface` / `updateComponents` / `updateDataModel` / `deleteSurface`),
a `{messages: [...]}` array, or palinex's convenience flat shape
(`{components: [...], dataModel: {...}}`).

```javascript
{ "type": "a2ui.load", "payload": <a2ui-payload> }
```

The renderer MUST treat `a2ui.load` as **idempotent** — the same payload
delivered multiple times yields the same final surface state. Bridges MAY
rely on this when implementing retry-until-ack (§7).

### 4.3 `a2ui.message`

Host pushes a single a2ui v0.9 message (incremental update). Use this when
the bridge already holds the payload and wants to apply an update without
re-pushing the whole envelope.

```javascript
{ "type": "a2ui.message", "message": <a2ui-v0.9-message> }
```

The renderer MUST apply the message in the order received. The renderer MAY
re-render synchronously after applying.

### 4.4 `a2ui.config`

Host pushes runtime configuration into the renderer. The renderer MUST
persist the supplied object under `localStorage` key `a2ui-renderer.v1`
(merging with any prior value) so subsequent loads see the same config
without a re-push.

```javascript
{ "type": "a2ui.config", "config": { "daemonBase": "http://localhost:9000", "...": "..." } }
```

Recognised config keys are not part of this protocol; they are renderer-
specific. The protocol defines only the envelope shape.

### 4.5 `a2ui.request`

The renderer's RPC call envelope. Sent when a surface action requires
host-side resolution (chash lookup, file open, custom skill dispatch, etc.).

```javascript
{
  "type": "a2ui.request",
  "method": "<method-name>",
  "requestId": "<unique-string>",
  "params": { /* method-specific */ }
}
```

Requirements:

- `method` MUST be a non-empty string. Method names are case-sensitive.
- `requestId` MUST be unique within the scope of a single renderer instance
  (e.g. `` `req-${Date.now()}-${random}` ``). The bridge MUST echo the same
  `requestId` in the matching `a2ui.response`.
- `params` MUST be a JSON-serialisable object (possibly empty). If absent,
  the bridge MUST treat it as `{}`.

The reference renderer's `requestId` generator follows the pattern
`` `req-${Date.now()}-${Math.random().toString(36).slice(2, 8)}` ``. The
exact format is non-normative; uniqueness is the only requirement.

### 4.6 `a2ui.response`

The bridge's RPC reply envelope. Sent exactly once per `a2ui.request`.

Success shape:

```javascript
{
  "type": "a2ui.response",
  "requestId": "<same-as-request>",
  "result": { /* method-specific success payload */ }
}
```

Error shape:

```javascript
{
  "type": "a2ui.response",
  "requestId": "<same-as-request>",
  "error": "<human-readable error message string>"
}
```

Requirements:

- The bridge MUST set exactly one of `result` or `error`. Sending both is a
  protocol violation; the renderer MAY treat such a message as an error with
  the `error` field winning.
- `error` MUST be a string. Structured error objects are reserved for a
  future protocol minor; v1.0 receivers MUST coerce non-string `error`
  values to strings (e.g. `JSON.stringify`) before displaying.
- The bridge MUST reply to every `a2ui.request` it receives, even when it
  cannot resolve the method (see §5).

### 4.7 `a2ui.action`

Fire-and-forget signal from the renderer announcing that the user invoked a
surface action. Advisory only — the bridge MAY log it, MAY surface it to its
host, but MUST NOT treat it as an RPC. No response is expected.

```javascript
{
  "type": "a2ui.action",
  "sourceId": "<component-id>",
  "action": { /* a2ui Action shape */ }
}
```

The reference bridge currently logs `a2ui.action` messages and takes no
further action. Custom bridges MAY use this hook to mirror actions into an
external event stream.

## 5. Method Dispatch and Allowlist Semantics

The bridge maintains a **method registry** — a mapping from method name to a
handler function. When an `a2ui.request` arrives, the bridge MUST:

1. Look up `m.method` in its registry.
2. If found, invoke the handler with `m.params`.
3. If not found, reply with an error response — the reference wording is
   `` `Unknown method: ${m.method}` `` — but any human-readable string is
   conforming. The renderer's modal panel displays this verbatim.

### 5.1 Default behaviour: log, don't execute

A new bridge SHOULD default to **logging** unrecognised methods rather than
executing them. The first-class methods listed in §5.2 are the only methods
a stock bridge resolves; everything else is logged.

### 5.2 First-class methods (v1.0)

| Method            | Resolution                       | Params shape                          | Result shape                          |
|-------------------|----------------------------------|---------------------------------------|---------------------------------------|
| `openUrl`         | Renderer-local (`window.open`)   | `{url: string}`                       | n/a — does not round-trip             |
| `copyToClipboard` | Renderer-local (`clipboard API`) | `{value: any}`                        | n/a — does not round-trip             |
| `openChash`       | Bridge-resolved (host-specific)  | `{chash: string, sourceId?: string}`  | `{text?: string, source?: string, ...}` |

`openUrl` and `copyToClipboard` never reach the bridge — they are resolved
inside the renderer because the renderer has direct access to the browser
APIs and the bridge would only proxy them. The renderer MUST resolve them
without posting an `a2ui.request`.

`openChash` is the canonical example of a bridge-resolved method. The
bridge's handler interprets `chash` against whatever data source the host
configured (an HTTP sidecar, an MCP tool call, an in-memory map, etc.) and
returns a result object whose `text` field, if present, the renderer
displays in a modal.

### 5.3 Extension methods

Any other method name (e.g. `runSkill`, `openFile`, `event`, `functionCall`)
goes through the same envelope. The reference bridge's MOCK_BACKEND
demonstrates an extension with `runSkill`:

```javascript
async runSkill({ name, args }) {
  return { result: `skill ${name} called with ${JSON.stringify(args)}` };
}
```

Adding an extension method requires (a) the bridge to register a handler,
(b) the producer to emit an `a2ui Action` whose `functionCall.call` matches
the method name. Producers SHOULD coordinate with the target bridges before
emitting actions that depend on host extensions, because the default
behaviour for unknown methods is to error.

### 5.4 Trust gate hook

The trust-gate is defined by RDR-004 (`docs/rdr/rdr-004-trust-gate-signature.md`).
A producer that wants its actions enforced by the host MAY attach a
`trust` block to its payload, signed Ed25519 over the RFC 8785 JCS
canonical form. A conforming host bridge:

1. MUST verify the signature, the `producerId` cross-check, the freshness
   window, and the replay nonce before forwarding any `a2ui.load` to the
   renderer.
2. MUST gate every `a2ui.request` on
   `m.method ∈ trust.actions ∩ trustStore[trust.producerId].allowed_actions`
   when a valid trust block was observed.
3. When the payload is unsigned (no `trust` block), the bridge MUST apply
   its configured `default_policy`. The RECOMMENDED default is
   `log-only`: bridge-routed methods deny with a visible banner; renderer-
   local methods (`openUrl`, `copyToClipboard`) execute. This preserves
   backward compatibility with payloads produced before the trust-gate
   was specified.
4. Renderer-local actions in standalone (`file://`) mode have no host
   bridge to gate them and are an explicit accepted residual risk for
   v1.0 (RDR-004 Phase 4c follow-up).

Bridges that do NOT yet implement the trust-gate continue to be
conforming under this protocol v1.0 — the trust block is OPTIONAL and
`default_policy: "allow"` is a valid (development-only) setting that
matches the pre-RDR-004 behaviour. Bridges SHOULD still be conservative
when exposing methods that have side effects beyond the renderer.

## 6. Timeout Semantics

The renderer MUST start a timer of 10 000 ms (10 s) when it posts an
`a2ui.request`. If no matching `a2ui.response` arrives before the timer
fires, the renderer MUST consider the request failed.

The visible failure mode is a modal panel showing:

1. The method name that timed out.
2. The text `No response from host within 10s. Host must reply with
   {type:"a2ui.response", requestId, result|error}.` (or equivalent
   instructional wording).
3. The `requestId` of the dropped request — implementations MAY include
   this to aid debugging, but it is not required by v1.0.

The bridge SHOULD complete `openChash` and similarly-shaped methods well
under 6 s under normal conditions, leaving margin for the retry-until-ack
budget (§7) to coexist with the request budget.

A future protocol minor MAY allow per-request timeout override via an
optional field on `a2ui.request`. v1.0 fixes the timeout at 10 s.

## 7. Retry-Until-Ack Handshake

The naïve wrapper bootstrap — a single `postMessage` gated on
`frame.contentDocument.readyState === 'complete'` — is broken by two races
and MUST NOT be reused:

### 7.1 Race A — early delivery to about:blank

A freshly-created cross-origin iframe presents an initial `about:blank`
document that is same-origin with the wrapper and trivially has
`readyState === 'complete'`. A naïve check fires `postMessage` against
`about:blank`, which has no listener; the payload is dropped before the
real renderer ever navigates in.

### 7.2 Race B — late listener attach (warm cache)

When the renderer is cached and already loaded by the time the bootstrap
runs, the `load` event has already fired. A bridge that only attaches a
`load` listener (and never retries) will never deliver the payload.

### 7.3 Required discipline

A conforming bridge MUST implement all four of the following:

1. **Attach a `load` listener on the iframe** that posts pending payloads
   when the iframe navigates. Covers the real renderer load that follows the
   initial about:blank.
2. **Run a bounded retry loop** of approximately 150 ms × approximately 40
   attempts (≈ 6 s budget) that re-posts pending payloads on each tick.
   Covers the warm-cache case (Race B). Payloads are idempotent (§4.2), so
   repeated delivery is safe.
3. **Stop retrying on receipt of `a2ui.ready`**. The renderer's ack signals
   that subsequent posts will reach a live listener.
4. **Deliver pending payloads on every relevant signal** — the `load` event,
   the `a2ui.ready` event, and each retry tick — until ack arrives.

The retry interval (150 ms) and attempt budget (40) are chosen so the total
~6 s budget sits comfortably inside the 10 s request timeout (§6); a future
protocol minor MAY widen either bound without breaking v1.0 bridges.

A bridge that omits any of these four points will fail to deliver in at
least one of the documented races. Empirically, the warm-cache race is
common in single-page hosts where the renderer iframe is reused across
navigations; the about:blank race is common in MCP UI resource hosts that
construct iframes lazily.

### 7.4 Renderer responsibility

The renderer MUST post `a2ui.ready` to `window.parent` immediately after
attaching its `message` listener (§4.1). A renderer that delays this signal
forces the bridge to retry for longer; a renderer that skips the signal
forces the bridge to retry to the budget limit.

## 8. Configuration Push

The renderer MAY accept runtime configuration from the host via the
`a2ui.config` envelope (§4.4). The reference renderer persists config under
`localStorage` key `a2ui-renderer.v1`. Recognised keys today:

- `daemonBase` — base URL of an HTTP sidecar that the renderer MAY fall
  back to when no parent host is present (standalone mode). Format:
  `http://host:port` with no trailing slash.

The reference host bridge persists its own config under `localStorage` key
`a2ui-host-bridge.v1`. Bridge config keys are not part of this protocol;
the reference shape is:

```javascript
{ "rendererUrl": "./index.html?demo=1", "backendUrl": "http://localhost:9000" }
```

Bridges MAY add or rename keys as they evolve, but the wire envelope
(`{type: "a2ui.config", config: ...}`) is fixed by this protocol.

The `.v1` suffix in the `localStorage` key names is a **storage-layout**
version, intentionally separate from the protocol version of §9. A future
protocol MAJOR MAY use the same `.v1` storage layout (if the persisted
shape didn't change) or bump to `.v2` (if it did). Implementations
encountering a stale storage layout SHOULD migrate or discard rather than
treat it as a protocol error.

## 9. Versioning Policy

The protocol version is `MAJOR.MINOR` (e.g. `1.0`, `1.1`, `2.0`).

- **MAJOR bump** — breaking change to any envelope shape, any required
  field's type, the dispatch model, the timeout semantics, or the retry
  discipline. Receivers SHOULD refuse messages from peers of a different
  MAJOR.
- **MINOR bump** — additive change: new envelope type, new optional field,
  new first-class method, widened bound. A peer of higher MINOR is
  compatible with a peer of lower MINOR; new fields are simply ignored by
  the older peer.

### 9.1 Handshake-driven version signalling

In v1.0, the renderer's `a2ui.ready` envelope MAY include `protocolVersion`;
absence is equivalent to `"1.0"`. In v1.1 and later the renderer MUST
include the field. The bridge MAY emit a symmetric `a2ui.hello` message
carrying its own `protocolVersion`; the renderer MAY inspect it to log or
refuse mismatched MAJORs.

```javascript
// future-compatible — illustrative for v1.1+
{ "type": "a2ui.ready", "protocolVersion": "1.1" }
{ "type": "a2ui.hello", "protocolVersion": "1.1" }
```

**Inference rule (normative).** A bridge of any version MUST treat the
absence of `protocolVersion` on `a2ui.ready` as equivalent to `"1.0"`. A
renderer of any version MUST treat the absence of `a2ui.hello` before the
first `a2ui.load` as equivalent to a bridge declaring `protocolVersion =
"1.0"`. These rules guarantee that a vN.x peer cannot accidentally refuse a
v1.x peer for "missing" handshake metadata that v1.0 never required.

**`a2ui.hello` ordering and the retry loop.** The bridge SHOULD send
`a2ui.hello` exactly once, on the same tick as the first delivery attempt,
**before** the first `a2ui.load` of that tick. The bridge MUST NOT resend
`a2ui.hello` on every retry tick of §7 — only the load and config payloads
are retried. The renderer MUST NOT block processing of `a2ui.load` on the
arrival of `a2ui.hello`; if the renderer wants to act on bridge version
information, it does so when (and if) `a2ui.hello` arrives, applying any
version-dependent policy retroactively. This keeps the §7 retry-until-ack
loop simple and avoids a dependency cycle between the version handshake and
payload delivery.

The version field lives on the handshake envelopes only. Per-message version
fields (on `a2ui.request`/`a2ui.response`/`a2ui.load`) are explicitly NOT
part of v1.0 — they were considered and rejected as redundant given the
handshake guarantee.

### 9.2 MAJOR-mismatch behaviour

When a peer detects that the other side declares a different protocol
MAJOR, it MUST NOT continue silently. The conforming responses are:

- **Bridge sees renderer MAJOR ≠ own MAJOR.** The bridge SHOULD stop
  sending `a2ui.load` and `a2ui.config`, log the mismatch, and surface it
  to its host (a status line, a banner, an MCP error response). The bridge
  MAY proceed at its own risk if the host explicitly opts in.
- **Renderer sees bridge MAJOR ≠ own MAJOR (via `a2ui.hello`).** The
  renderer SHOULD display a visible error panel naming the mismatch (the
  same modal channel §6 uses for timeouts is appropriate) and stop
  processing `a2ui.request` responses. The renderer MAY proceed if the user
  explicitly opts in (e.g. a "render anyway" button).
- **Renderer never receives `a2ui.hello`.** Per the inference rule in §9.1,
  the renderer MUST assume the bridge is v1.x. No additional behaviour is
  required.

These rules apply asymmetrically because `a2ui.hello` is OPTIONAL: a
renderer cannot rely on it arriving. The bridge has full information (it
always receives `a2ui.ready`) and is therefore the authoritative side for
detecting mismatch. A future protocol MAJOR MAY promote `a2ui.hello` to
REQUIRED, at which point the renderer becomes the authoritative side; v1.x
defers to the bridge.

### 9.3 Why not negotiation?

Negotiation (renderer offers version, bridge replies with a chosen version,
renderer commits) was considered and rejected as over-engineered for the
shape of this protocol. Each side declares its version; the side with full
information (the bridge in v1.x; either side once `a2ui.hello` is REQUIRED)
decides what to do with the mismatch. Asymmetric, simpler, and sufficient
for the expected use cases.

This decision is scoped to the v1.x line. The asymmetric model leans on
`a2ui.hello` being OPTIONAL and v1.0 being the implicit floor; both
properties are baked into §9.1's inference rule and §9.2's MAJOR-mismatch
behaviour. When a future RDR proposes the first MAJOR bump, the governance
question — "do we need negotiation now, or does asymmetric declaration
still suffice?" — will need to be re-opened.

### 9.3 Protocol vs palinex package version

These are independent. The current mapping is:

| palinex version | protocol version |
|-----------------|------------------|
| 0.0.x           | 1.0 (de facto)   |
| 0.2.x           | 1.0              |
| 0.3.x           | 1.0 (specified)  |

A palinex release MAY bump only the package version, only the protocol
version, both, or neither. Consumers SHOULD pin both ranges if they depend
on specific protocol behaviour beyond MAJOR-stability.

## 10. Conformance Test

The Python test module
[`tests/test_protocol_spec.py`](../../tests/test_protocol_spec.py) asserts
that:

- The spec at this path exists and declares protocol version `1.0`.
- The reference renderer (`web/index.html`) emits the documented envelope
  shapes with the documented field names and the documented 10 000 ms
  timeout.
- The reference bridge (`web/host-bridge.html`) dispatches on `m.method`,
  echoes `m.requestId`, replies with `result` or `error`, exposes the
  documented first-class methods, and implements the retry-until-ack
  handshake at 150 ms × 40 attempts.

A new bridge implementation SHOULD adopt analogous tests; the conformance
test in this repo covers the reference implementations only.

## 11. Examples

### 11.1 Normal openChash flow

```
renderer                                bridge
   │                                      │
   │── a2ui.ready ──────────────────────▶│
   │◀────────────────────── a2ui.load ───│
   │  (user clicks "Open chunk")         │
   │── a2ui.request {method:openChash,   │
   │     requestId:req-..., params:{...}}─▶│
   │                                      │── (resolve openChash; HTTP/MCP/etc.)
   │◀── a2ui.response {requestId:req-..., │
   │     result:{text:"..."}} ───────────│
   │  (renderer displays text in modal)  │
```

### 11.2 Timeout

```
renderer                                bridge (offline)
   │── a2ui.request {requestId:req-...}─▶  ✗
   │  (10 s passes)                       │
   │  (modal: "openChash timeout —        │
   │     no response within 10s")         │
```

### 11.3 Unknown method

```
renderer                                bridge
   │── a2ui.request {method:doFoo}─────▶│
   │                                      │  (no handler for doFoo)
   │◀── a2ui.response {requestId:...,    │
   │     error:"Unknown method: doFoo"} ─│
   │  (modal: "doFoo error — Unknown      │
   │     method: doFoo")                  │
```

### 11.4 Cold-cache vs warm-cache delivery

```
cold cache (Race A):                    warm cache (Race B):

bridge      iframe                       bridge      iframe
  │  create   │                            │  create   │ (already loaded)
  │──────────▶│ (about:blank)              │──────────▶│
  │ load post │                            │ load post │ (no load event)
  │ → about:blank (DROPPED)                │ ✗ never fires
  │           │ navigate to renderer       │── retry 150ms ──▶│
  │           │ install listener           │           │ (listener attaching)
  │           │ post a2ui.ready ──────────▶│── retry ──▶│ (caught by listener)
  │── retry caught by load listener ──────▶│           │
  │           │ apply payload              │           │ post a2ui.ready ──▶
  │◀── a2ui.ready ─────────────────────────│   stop retrying
  │   stop retrying                        │
```

## 12. Change Log

- **1.0 (2026-05-23)** — Initial published spec. Codifies the contract
  shipped in palinex 0.3.0. No behavioural change from palinex 0.2.x; this
  release adds the spec document and the conformance test. §9 versioning
  policy went through a substantive-critique pass that surfaced four issues
  (missing inference cross-reference, unspecified MAJOR-mismatch behaviour,
  `a2ui.hello` ordering vs the §7 retry loop, and the storage-layout
  versus protocol-version distinction). All four were addressed before
  publication; the change log records this so future readers know §9.1's
  inference rule and §9.2's renderer fallback are deliberate, not
  oversights.
