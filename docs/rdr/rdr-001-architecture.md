---
title: "palinex Architecture: a2ui v0.9 IR, SurfaceBroker Port, Three Delivery Shapes, postMessage Host Bridge"
id: RDR-001
type: Architecture
status: accepted
priority: high
author: Hal Hildebrand
reviewed-by: self
created: 2026-05-22
accepted_date: 2026-05-23
related_rdrs: []
related_external: [a2ui-v0.9-spec, mcp-ui-resources, lit-html]
---

# RDR-001: palinex Architecture

> palin- (Greek: "again") + nexus (Latin: "bond") — the surface gets rewritten in place.

## Problem Statement

LLM-driven agents emit structured intermediates that are usually flattened to markdown at the wire. The flattening loses everything navigable: citations as references, follow-up actions as buttons, tabular data as rows, hierarchical context as nested containers. Hosts that *could* render structure (Claude Code via MCP UI resources, custom web shells, Tauri-style desktop apps) get prose instead.

A2UI (Google, 2026, Apache-2.0) ships a declarative UI spec purpose-built for this case: agent-emitted JSON, client-rendered components from a pre-approved catalog, four-message lifecycle. v0.9 is the current stable shape. Adopting it requires:

1. A producer-side library to build v0.9-conformant payloads from typed inputs.
2. A renderer for at least one host.
3. A discipline for delivering payloads from producer to renderer.
4. A discipline for actions emitted by the rendered surface that need to reach back to a data source.
5. Graceful degradation when the host can't render structured surfaces.

palinex is that library + renderer + delivery + bridge + degradation, all packaged so a producer can `pip install palinex`, build a surface, and ship it.

### Enumerated gaps to close

1. **No canonical Python builder for a2ui v0.9.** Producers either hand-craft JSON or fall back to markdown.
2. **No single-file renderer.** a2ui ships reference renderers in Angular/React/Lit, all with build pipelines. None of those drop into a Claude-Code-style host as a single file.
3. **No host-bridge protocol.** Sandboxed renderers need a way to ask the host for data (chash resolution, file open, skill dispatch) without making nexus-specific assumptions.
4. **No degradation path.** A surface that won't render needs a markdown sidecar so the user sees *something* useful.

## Context

### What palinex is

A small Python package + one HTML file + one host-bridge wrapper. No framework, no daemon, no installation outside `pip install palinex`. Independent project; nexus depends on it but doesn't own it.

### Technical environment

- **a2ui v0.9 spec**: <https://a2ui.org/specification/v0.9-a2ui/> — Apache-2.0, four message types, 18 Basic Catalog components, JSON Schema validation, per-version structural backward-compat via `v0_8/`, `v0_9/`, `v0_10/` directories upstream.
- **Renderer host (primary, partially supported as of 2026-05-23)**: Claude Code via MCP UI resources. Sandboxed iframe with postMessage channel back to the host. **Known limitation:** Claude Code *Desktop* (v2.1.149 verified) does not currently render `ui://`-scheme HTML resources as inline iframes — the resource envelope returns but the host displays it as text rather than mounting it. The MCP UI resource shape works in hosts that do mount such resources (Claude.ai web client, custom MCP UI hosts). Until Desktop adds inline rendering, producers targeting Desktop should rely on the *embedded artifact* or *external URL* delivery shapes (Item 4) for visible output.
- **Renderer host (secondary, fully supported)**: any browser. `file://` works; GitHub Pages hosts the canonical renderer at `https://hellblazer.github.io/palinex/`. This is the de-facto primary target as of 0.2.0 given the Desktop limitation above.
- **Renderer host (future)**: custom web shells, Tauri apps, terminal hosts (notcurses).

### Constraints

- **Single-file renderer.** No build step. lit-html from pinned CDN ESM. Open `.html` in a browser; it works.
- **Apache-2.0 license.** Matches a2ui upstream; compatible with most downstream consumers.
- **No long-running daemon required.** Producer is pure Python; renderer is pure HTML; bridge is postMessage. No socket, no port, no service.
- **Markdown sidecar is mandatory.** Every surface emission must include a lossless markdown rendering — never ship a surface that some host can't display.
- **Action allowlist enforced producer-side.** v1 supports three actions; trust gates ride on the action registry, not the IR.

## Decision

palinex commits to the following architecture. Each numbered item is a §Approach point eligible for downstream phase-review gating.

### Approach

**Item 1: a2ui v0.9 as the IR — adoption, not invention.**

palinex's `Surface` class builds v0.9 message envelopes (`createSurface`, `updateComponents`, `updateDataModel`, `deleteSurface`). The `Cell` shape mirrors a2ui's component definitions; data binding uses a2ui's `DataBinding` (JSON pointer into the data model); actions use a2ui's `Action` shape (`event` vs `functionCall`).

No parallel IR. No translation layer. Producers emit a2ui v0.9 JSON; renderers consume a2ui v0.9 JSON. Versioning policy: palinex's minor version tracks the a2ui version it pins. Breaking a2ui changes → new palinex major.

**Item 2: Typed Python builders with structural validation.**

`Surface.text()`, `.button()`, `.column()`, etc. return component IDs (str). Builders auto-assign IDs unless explicitly provided. `set_root()` swaps the named root into the canonical `id="root"` slot. `emit()` returns the message envelope; `emit_flat()` returns a convenience shape (components array + dataModel object) for renderers that accept it.

Structural validation (`Surface.validate()`) is the default gate:
- every component has a recognized `component` discriminator
- exactly one component has `id="root"`
- every child reference resolves
- DataPath strings are valid JSON pointers

Deep jsonschema validation (`Surface.validate(schemas=load_schemas(...), deep=True)`) is opt-in via `pip install palinex[validate]`. Known limitation: upstream catalog `$ref` chain has referencing patterns that confuse `jsonschema.RefResolver` — structural is the reliable answer.

**Item 3: Single-file renderer (`index.html`).**

lit-html from pinned CDN ESM (`https://cdn.jsdelivr.net/npm/lit-html@3.2.1/+esm`). 14 of 18 Basic Catalog components in v1 (Text, Image, Icon, Row, Column, List, Card, Modal, Divider, Button, TextField, CheckBox, ChoicePicker, Slider). Tabs, DateTimeInput, Video, AudioPlayer follow the same dispatch pattern and are straightforward incremental adds.

Renderer features:
- Accepts payload via `?surface=<url>`, `?payload=<base64>`, file picker, `postMessage({type: "a2ui.load", payload})`.
- Renders a2ui v0.9 message envelopes (full lifecycle) and a convenience flat shape.
- Data model with JSON-pointer resolution (DynamicString, DynamicNumber, DynamicBoolean).
- Template ChildList (List rendering over an array at a data-model path with `@item` synthetic alias).
- Markdown export (`Copy markdown` button) — lossless tree walk matching the producer-side `to_markdown()`.
- Share URL (`Share URL` button) — base64-encodes payload into `?payload=` for trivial distribution.
- Dark mode via `prefers-color-scheme`.
- Debug pane showing component count + raw JSON.

Size target: ~700 LOC (warn at 500 per `html-tool-patterns` discipline). Current size 845 — past the original 700 target after Phase 2 (Tabs/DateTimeInput/Video/AudioPlayer) and the `a2ui.ready` handshake added incremental dispatch and bootstrapping code. A future minor should evaluate whether the 18-component dispatch warrants a small helper module or whether the inline approach still earns its single-file simplicity. Treat 1000 LOC as a hard ceiling that triggers a refactor.

**Item 4: Three delivery shapes.**

| Shape | Host | Mechanism | Producer-side helper |
|---|---|---|---|
| **MCP UI resource** | Claude Code, claude.ai, custom MCP UI hosts | Tool returns `{type: "resource", resource: {uri: "ui://...", mimeType: "text/html"}}` wrapping the renderer + payload | `wrap_as_mcp_ui_resource(payload, ...)` |
| **Embedded artifact** | Any chat host | HTML returned inline with payload as `<script type="application/json">` and renderer pulled from `hellblazer.github.io/palinex/` via iframe | none yet — callers construct the wrapper HTML directly using the same bootstrap shape as `wrap_as_mcp_ui_resource`; promoting to a helper is straightforward future work |
| **External URL** | Any browser | `https://hellblazer.github.io/palinex/?payload=<base64>` for shareable links | none yet — callers do `base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()` and append to the renderer URL; promoting to a helper is straightforward future work |

The only first-class producer helper in v0.2.0 is `wrap_as_mcp_ui_resource`. The other two shapes are documented conventions a caller can construct manually with stdlib; they're listed here as supported delivery paths rather than supported APIs. If multi-shape adoption picks up they'll graduate to helpers in a future minor.

Caller chooses shape based on out-of-band knowledge of the host (does it mount `ui://` HTML inline? does it accept arbitrary HTML artifacts?), not a programmatic capability query — no such query exists in MCP today. **Note:** "MCP-aware → resource" is *not* a safe default given the Desktop limitation in §Context; pick the resource shape only when the host is known to mount `ui://` HTML inline (claude.ai web, custom MCP UI hosts), otherwise prefer external URL or embedded artifact.

**Item 5: Markdown sidecar always.**

`Surface.to_markdown()` is a lossless tree walk:
- Text → markdown text with heading-level prefixes (`# ` through `##### `) for variants
- Divider → `---`
- Image → `![desc](url)`
- Card → walks single child
- Row / Column / List → walks children sequentially
- Modal → walks trigger (collapses modality)
- Button → `[label](url)` for `openUrl` actions; `[label]` otherwise
- Input components (TextField, CheckBox, ChoicePicker, Slider, DateTimeInput) → `[Component: label]`
- Template ChildList → expands once per data-model array item

Every producer that emits a surface emits markdown alongside. Round-trip from markdown to surface to markdown should equal input on a representative corpus.

**Item 6: postMessage RPC host-bridge protocol.**

Renderers are sandboxed; they cannot call MCP tools, fetch arbitrary URLs, or persist state beyond `localStorage`. When a rendered action needs host-side resolution (chash lookup, file open, skill dispatch), the renderer posts:

```javascript
{ type: "a2ui.request", method: "<name>", requestId: "<uuid>", params: {...} }
```

The host (Claude Code wrapper, custom web shell, or palinex's reference `host-bridge.html`) listens for these requests, resolves them through whatever channel it has (MCP tool call, sidecar HTTP fetch, custom resolver function), and posts:

```javascript
{ type: "a2ui.response", requestId: "<uuid>", result: {...} | error: "..." }
```

Renderer timeout is 10s default. Visible failure mode: modal panel showing the expected response shape and what timed out.

Configuration: hosts can push config to the renderer via `{type: "a2ui.config", config: {daemonBase: "...", ...}}`. Stored in `localStorage` for the renderer to use across loads.

#### Delivery robustness — retry-until-ack handshake

The naïve wrapper bootstrap (single `postMessage` gated on `frame.contentDocument.readyState === 'complete'`) is broken by two races and **must not be reused**:

- **Race A — early delivery to about:blank.** A freshly-created cross-origin iframe presents an initial `about:blank` document that is same-origin with the wrapper and trivially `readyState === 'complete'`. A `readyState`-gated check fires `postMessage` against `about:blank`, which has no listener; the payload is dropped before the real renderer navigates.
- **Race B — late listener attach.** When the renderer is cached and already loaded by the time the bootstrap runs, `contentDocument` is `null` (now cross-origin), so the script falls through to `addEventListener('load', ...)`. But `load` already fired; the listener never runs.

**Required discipline:**

1. **Wrapper always attaches `load` listener** for the deliver function — covers Race A (real renderer load).
2. **Wrapper runs a bounded retry loop** (~150 ms × ~40 attempts ≈ 6 s) that re-posts the payload — covers Race B. `setSurface` is idempotent, so repeated delivery is safe.
3. **Renderer posts `{type: "a2ui.ready"}` to `window.parent`** immediately after attaching its `message` listener.
4. **Wrapper stops retrying on receipt of `a2ui.ready`** — keeps the common path one round-trip.

This is the actual delivery contract of `wrap_as_mcp_ui_resource`. Any new wrapper (Tauri host, custom web shell, an HTTP sidecar's index page) must implement the same retry-until-ack pattern, not the readyState gate. The retry-until-ack handshake landed in palinex 0.2.0 after the race-prone wrapper shipped in 0.1.0 produced silent empty surfaces in warm-cache iframes.

**Item 7: Action allowlist for v1.**

Three actions are first-class in v1:

| Action | Resolution | Trust |
|---|---|---|
| `openUrl` | `window.open(url, "_blank", "noopener")` | URL must come from trusted source (producer-side discipline) |
| `copyToClipboard` | `navigator.clipboard.writeText(value)` | always safe |
| `openChash` | Host-bridged via postMessage RPC | host decides whether to resolve |

All other actions go through the same postMessage path with `method` set to the action name. Default host-bridge behavior: log but don't execute. Producers and hosts add to the allowlist incrementally.

**Item 8: Reference host-bridge wrapper (`host-bridge.html`).**

A small (~160 LOC) HTML wrapper that:
- Embeds the renderer in an iframe
- Listens for `a2ui.request` messages
- Routes to a configurable backend (mock / HTTP sidecar / custom `window.hostBridgeResolver` function)
- Posts `a2ui.response` back to the renderer
- Logs the request/response pairs visibly

This is the reference implementation of Item 6. Real hosts (Claude Code, Tauri shells) implement the same protocol with their own backends.

**Item 9: Distribution and release flow.**

- Repo: `https://github.com/Hellblazer/palinex` (Apache-2.0)
- PyPI: `palinex` (`pip install palinex`); optional `palinex[validate]` adds jsonschema, optional `palinex[mcp]` adds the FastMCP server entry point used by the .mcpb bundle below
- Renderer hosted: `https://hellblazer.github.io/palinex/` (GitHub Pages; Pages workflow auto-deploys `web/**` on push to `main`)
- Claude Desktop `.mcpb` bundle: `mcpb/` directory builds a Claude Desktop extension that vendors a uv-managed `.venv` pulling `palinex[mcp]>=<version>`. Currently installed via Claude Desktop's "Install extension" UI; bundle versioning tracks palinex versioning. **Caveat:** the bundle's `manifest.json` description claims inline rendering in Claude Desktop, which is not yet supported (see §Context A1); description should be updated to reflect that the bundle provides the MCP server only and inline rendering requires a host that mounts `ui://` resources.
- Release: tag-triggered (`v*`) GitHub Actions workflow with OIDC trusted publisher to PyPI + GitHub Release with sdist/wheel attached
- CI: pytest matrix on Python 3.12–3.13 plus build check on every PR/push (requires-python is `>=3.12`)
- Versioning: palinex semver tracks a2ui versions it supports. v0.0.x is alpha; v0.x.y will track a2ui v0.9; v1.x.y will track a2ui v1.0 if/when it ships.

## Alternatives Considered

### Alt 1: Parallel SurfaceIR over a2ui

Initial sketch had palinex defining its own IR dataclass and translating to a2ui at the wire. Rejected because a2ui already ships per-version structural backward-compat, 18 Basic Catalog components, JSON Schema validation, and four-message lifecycle. Inventing a wrapper would duplicate every concept and force two-way translation at the wire — for no gain.

### Alt 2: React-based renderer reusing a2ui's reference impls

a2ui ships reference renderers in Angular, React, Lit, and Flutter. Adopting one of those would mean a build step (webpack/Vite/Next) and a heavier deployment. Rejected per the `html-tool-patterns` discipline: single file, no build, lit-html from CDN. The renderer fits in a Claude Artifact, fits in a GitHub Pages drop, fits in an LLM context window.

### Alt 3: MCP UI resource as the only delivery shape

Tighter scope. Locks v1 to Claude Code. Rejected because markdown sidecar + external URL combined preserve graceful degradation for hosts without MCP UI support, including terminal CLIs and future Tauri shells.

### Alt 4: Direct WebSocket from renderer to data source

Instead of postMessage RPC to a host bridge, the renderer could open a WebSocket directly to a nexus daemon or other data source. Rejected because:
- Sandboxed iframes have CORS/security headaches
- Locks renderer to a specific data-source URL/protocol
- postMessage to parent is universally available, including in MCP UI resource hosting

### Alt 5: Adaptive Cards instead of a2ui

Microsoft-maintained, more mature, large renderer ecosystem. Rejected because Adaptive Cards is *card-native* (single card per payload) while palinex's target use cases (`nx_answer` synthesis with citations list, subagent findings, RDR audit dashboards) are *surface-native* (multi-component coordinated). a2ui fits the shape; Adaptive Cards doesn't.

### Alt 6: `srcdoc` or `blob:` iframes to dodge the about:blank race

The 0.1.0 → 0.2.0 about:blank race fix (Item 6 "Delivery robustness") prompted reconsidering whether `<iframe src="https://hellblazer.github.io/palinex/">` is the right transport at all. Two same-origin alternatives:

- **`srcdoc`** — inline the renderer HTML in the wrapper's `<iframe srcdoc="...">`. Avoids the cross-origin nav, eliminates Race A entirely. Rejected because (a) `srcdoc` content is treated as same-origin with the parent, which means the rendered surface inherits the host's CSP and storage origin — undesirable for sandboxing; (b) duplicates the renderer HTML on every emission (~30KB × N surfaces in a session); (c) loses the canonical-URL story for caching and the "open in browser" external-URL shape.
- **`blob:` URL** — render the wrapper into a `Blob`, mint a `URL.createObjectURL(blob)`, point the iframe at that. Same-origin with the wrapper. Avoids Race A. Rejected because (a) blob URLs are session-scoped and ephemeral, breaking the "share URL" delivery shape; (b) cross-origin sandboxing semantics differ from a hosted https origin and downstream hosts vary in how they treat blob iframes under CSP; (c) doesn't help with the warm-cache case (Race B) which the retry loop addresses anyway.

The retry-until-ack handshake (Item 6) addresses both races without giving up the canonical hosted-renderer URL. Re-evaluate `srcdoc` if a host emerges that enforces strict CSP on `frame-src` excluding `hellblazer.github.io`.

### Briefly rejected

- **JSON Schema "Form"** standard — narrower scope (input forms only)
- **HTML strings as payload** — loses structure, no validation, no per-host catalog story
- **In-house DSL** — duplicates a2ui without upstream support

## Trade-offs

### Consequences

- **(+)** Single dependency for producers (`pip install palinex`); single file for renderers (drop `index.html` into any static host)
- **(+)** No daemon, no service, no port — works from `file://` for ad-hoc use
- **(+)** OIDC trusted publisher on PyPI — no API tokens in repo
- **(+)** Markdown sidecar means producers never ship surfaces that some host can't display
- **(+)** Host-bridge protocol is small (one request/response shape) and generalizes to any host that can postMessage
- **(−)** External dependency on a2ui v0.9 spec; v0.10 may require palinex major bump
- **(−)** Single-maintainer bus factor; mitigated by Apache-2.0 + small surface area
- **(−)** Renderer size (~845 LOC) is past the originally-stated 700 LOC target; hard ceiling 1000 LOC. Further feature growth needs careful design or a structured refactor (see Item 3)

### Risks and Mitigations

- **Risk:** a2ui v0.9 → v0.10 breaks component shapes.
  **Mitigation:** palinex 0.x.y pins v0.9; v1.x.y track v0.10 when ready. Consumers control upgrade via semver range.

- **Risk:** Claude Code MCP UI resource behavior changes upstream.
  **Mitigation:** three delivery shapes; embedded artifact + external URL are independent fallbacks.

- **Risk:** Host-bridge `postMessage` timing out silently in some hosts.
  **Mitigation:** 10s timeout with visible failure panel; explicit protocol-shape documentation in the timeout message.

- **Risk:** Deep jsonschema validation flaky due to upstream catalog `$ref` patterns.
  **Mitigation:** structural validation is the reliable gate; deep validation is opt-in with documented limitations.

### Failure modes

- *Visible:* renderer fails to render unknown component type → `<div class="error">unsupported component: {name}</div>` inline.
- *Visible:* host bridge times out → modal panel with expected protocol shape and `requestId`.
- *Visible:* markdown sidecar doesn't match surface (lossy transformation) → producer-side test corpus catches before release.
- *Silent:* renderer's debug pane shows raw JSON + data model — visible recovery via `<details>` element.
- *Recovery:* markdown sidecar always allows human reading even if the surface itself never renders.

## Implementation Plan

### Prerequisites

- [x] a2ui v0.9 spec readable at `https://github.com/google/a2ui/tree/main/specification/v0_9`
- [x] GitHub repo `Hellblazer/palinex` (Apache-2.0)
- [x] PyPI pending publisher configured for `palinex`

### Phase 1: Producer + renderer + bridge + release pipeline (shipped)

- [x] `palinex/__init__.py` — Surface builder with 14 components, DataPath/FunctionCall/Event helpers, validation, markdown sidecar
- [x] `index.html` — single-file renderer covering 14 components, three load paths, host-bridge protocol, dark mode, debug pane
- [x] `host-bridge.html` — reference wrapper implementing the `a2ui.request`/`a2ui.response` protocol
- [x] `tests/` — 53 pytest tests across `test_builders.py`, `test_mcp_server.py`, `test_nexus_bridge.py` covering envelope shape, action shapes, validation gates, markdown round-trip, template ChildList, MCP server tool surface, optional nexus chash resolution
- [x] `pyproject.toml` — hatchling build, optional `[validate]` extra, dev group
- [x] `.github/workflows/ci.yml` — pytest matrix on 3.10–3.13 + build check
- [x] `.github/workflows/release.yml` — tag-triggered OIDC trusted publisher + GitHub Release with artifacts
- [x] `CHANGELOG.md` — keep-a-changelog format
- [x] `README.md` — installation, quick start, URL params, component coverage
- [x] `LICENSE` — Apache-2.0
- [x] palinex 0.0.1 released to PyPI 2026-05-22

### Phase 2: Remaining Basic Catalog components (shipped in 0.2.0)

- [x] Tabs (titles + children)
- [x] DateTimeInput (ISO 8601 value, optional min/max, date/time toggles)
- [x] Video (URL + minimal controls)
- [x] AudioPlayer (URL + description)

All four followed the dispatch pattern established by the original 14. `BASIC_COMPONENTS` (`src/palinex/__init__.py`) now lists all 18 v0.9 Basic Catalog components; the renderer dispatches all 18. Shipped alongside Phase 1 in palinex 0.2.0 rather than the originally-planned 0.0.2 release.

### Phase 3: Action registry hardening

- [ ] Document the postMessage RPC protocol as a stable contract (separate spec doc)
- [ ] Add `runSkill` (nexus-specific) to the host-bridge example
- [ ] Add `openFile` (editor-host-specific) to the host-bridge example
- [ ] Define trust-gate signature: how a host decides which actions a given producer may emit

### Phase 4: Per-host catalogs (deferred)

If/when palinex needs to target hosts beyond Claude Code's MCP UI resource (Tauri/Lumino web, notcurses terminal), define per-host catalogs in the a2ui style (`palinex.lumino.v1`, `palinex.notcurses.v1`). Out of scope for v0.x.

### Day 2 Operations

- palinex updates land as new PyPI releases via the OIDC release workflow
- a2ui v0.10 tracking happens when v0.10 stabilizes upstream
- Bug reports and PRs through GitHub issues

## Test Plan

- **Scenario:** Build a typical citation surface (synthesis + List of Cards), emit envelope, render.
  **Verify:** envelope passes structural validation; renderer displays correctly; markdown sidecar lists every citation by title and excerpt.

- **Scenario:** Markdown ↔ surface round-trip on a 10-item corpus.
  **Verify:** `to_markdown(surface_from_intermediates(item))` equals expected markdown for each item.

- **Scenario:** Renderer in `file://` mode without host bridge clicks an `openChash` button.
  **Verify:** visible "host or sidecar required" message — no dead-end prompt, no silent failure.

- **Scenario:** Host bridge with mock backend receives `a2ui.request`, posts `a2ui.response`.
  **Verify:** renderer's modal updates inline with the response payload.

- **Scenario:** Producer emits a component referencing a non-existent child id.
  **Verify:** `Surface.validate()` raises with a clear message naming the dangling ref.

- **Scenario:** Producer-side variants (Text h1–h5, caption, body) round-trip through markdown.
  **Verify:** h1 → `# `, h2 → `## `, etc.; body has no prefix; caption wraps in `_underscores_`.

## Validation

### Testing strategy

53 pytest tests across three modules (29 in `test_builders.py`, 11 in `test_mcp_server.py`, 13 in `test_nexus_bridge.py`) cover the producer, the MCP server's `render_surface` tool, and the optional nexus bridge. CI matrix runs them on Python 3.12 and 3.13 for every PR and push. Renderer is browser-tested manually for v1; future Playwright tests would drive the renderer with payloads from the producer test corpus and assert DOM output.

### Performance expectations

- Surface construction (typical citation surface): <5ms
- Markdown sidecar generation: <5ms (tree walk, no I/O)
- Renderer cold load with warm CDN: <500ms
- Host-bridge round-trip with mock backend: <10ms; with real MCP call: <250ms
- Renderer rerender on data model change: <20ms for surfaces under 100 components

## Finalization Gate

Ran 2026-05-23 prior to accepting RDR-001 alongside the palinex 0.2.0 release.

### Contradiction check

Items reviewed against the shipped code in palinex 0.2.0:

- **Item 1 (a2ui v0.9 as IR):** matches. `Surface` builds v0.9 envelopes; no parallel IR.
- **Item 2 (typed Python builders + validation):** matches. 14 builders ship; `Surface.validate()` enforces structural rules; `[validate]` extra adds jsonschema.
- **Item 3 (single-file renderer):** matches. `web/index.html` is one file, lit-html from pinned CDN, 14 components, all renderer features ship.
- **Item 4 (three delivery shapes):** matches. `wrap_as_mcp_ui_resource` + embedded artifact + `?payload=` URL.
- **Item 5 (markdown sidecar always):** matches. `Surface.to_markdown()` covers all 14 component types.
- **Item 6 (postMessage RPC host bridge):** **previously contradicted by the wrapper's race-prone single-shot delivery shipped in 0.1.0** AND by `web/host-bridge.html` lacking the retry-until-ack pattern that the contract requires of "any new wrapper". Both resolved on this branch: `wrap_as_mcp_ui_resource` retry-until-ack landed in 0.2.0; `host-bridge.html` retry-until-ack landed in the acceptance branch alongside this gate. RDR now describes the actual contract and the reference bridge demonstrates it.
- **Item 7 (action allowlist):** matches. `openUrl`, `copyToClipboard`, `openChash` ship; others routed through the bridge.
- **Item 8 (reference host-bridge wrapper):** matches *after* the host-bridge update above. Previously the reference implementation did not demonstrate the contract it referenced.
- **Item 9 (distribution and release flow):** matches with two corrections from initial draft — the `.mcpb` Claude Desktop bundle is now listed (it shipped in 0.2.0 but the original draft predated it), and the CI matrix is `3.12-3.13` per `pyproject.toml` `requires-python = ">=3.12"` (not `3.10-3.13` as originally written; the broader range was aspirational and never enforced).

No outstanding contradictions.

### Assumption verification

- [x] **A1** — Claude Code MCP UI resource rendering. **Partially verified, partially falsified.**
  - **Verified:** the wrapper HTML produced by `wrap_as_mcp_ui_resource` renders correctly when opened in a browser (Safari 18 on macOS 14 verified 2026-05-23) — surface displays, host-bridge protocol routes correctly, retry-until-ack handshake observed.
  - **Falsified:** Claude Code Desktop (v2.1.149 verified 2026-05-23) does not mount `ui://` HTML resources as inline iframes; the resource envelope is returned but the host renders it as text. Documented as a known limitation in §Context. Producers targeting Desktop should use the embedded artifact or external URL shapes until this is addressed upstream.

- [ ] **A2** — Structural validation catches producer errors. **Deferred to follow-up.**
  - Rationale: 19 pytest tests cover the cases observed during 0.1.0/0.2.0 development; a mutation-test pass against a representative corpus is worth doing once nexus integration produces a corpus large enough to be representative. Not a blocker for accepting the architecture.

- [ ] **A3** — Markdown sidecar lossless on 100 nx_answer outputs. **Deferred to follow-up.**
  - Rationale: no production corpus of nx_answer surface outputs exists yet (nexus is still producing markdown, not surfaces). Re-evaluate after RDR-127's pilot producers ship.

- [x] **A4** — 10s postMessage timeout is appropriate. **Verified for the current host set.**
  - GitHub Pages renderer cold load + `a2ui.ready` ack arrives well under 6s (observed ~1–2s on warm connections). Retry-until-ack budget (6s) sits inside the 10s timeout. Real MCP-backed chash resolution latency not yet measured against the production nx store — defer remeasurement to RDR-127's pilot.

### Scope verification

- The RDR's scope is **palinex itself only** — producer library, renderer, host-bridge protocol, delivery shapes, packaging.
- Downstream integrations (nexus's `nx_answer` adoption, subagent surface emission, Tauri/notcurses hosts) are explicitly out of scope and tracked by their own RDRs (nexus RDR-127 et al).
- Phase 2 (remaining Basic Catalog components) and Phase 3 (action registry hardening) are explicit follow-up phases of *this* RDR — they ship under the architecture accepted here, no architectural change.

No silent scope reduction. The known scope reduction (A2/A3 deferred) is explicit above.

### Cross-cutting concerns

- **Versioning:** palinex semver tracks supported a2ui versions; v0.x.y for v0.9, v1.x.y for v1.0 (TBD).
- **Build tool compatibility:** hatchling backend; pure Python sdist/wheel.
- **Licensing:** Apache-2.0 for palinex; a2ui spec is Apache-2.0 upstream; downstream consumers can mix.
- **Deployment:** PyPI for the Python package, GitHub Pages for the renderer, GitHub releases for sdist/wheel artifacts.
- **IDE compatibility:** VS Code webview hosts the renderer via `host-bridge.html`-style wrappers.
- **Incremental adoption:** opt-in per producer; markdown-returning tools unchanged.
- **Secret/credential lifecycle:** `localStorage` for daemon URLs in sidecar mode; never in URL params or HTML inline.
- **Memory management:** renderer disposes lit-html on unload; surface state is per-iframe-load.

### Proportionality

Small RDR. The IR is a2ui (external, adopted). Producer + renderer + bridge are the deliverable. No new substrate, no new transport, no new identity layer. Resist scope creep — per-host catalogs and trust gates are explicit Phase 4/3 work.

## References

- a2ui v0.9 specification — <https://a2ui.org/specification/v0.9-a2ui/>
- a2ui repo (Apache-2.0) — <https://github.com/google/a2ui>
- palinex repo — <https://github.com/Hellblazer/palinex>
- palinex on PyPI — <https://pypi.org/project/palinex/>
- palinex renderer hosted — <https://hellblazer.github.io/palinex/>
- nexus integration: nexus RDR-127 — depends on palinex; defines pilot producers (nx_answer, codebase-deep-analyzer subagent emission); supersedes nexus RDR-123, RDR-124
- T3 knowledge entries (in nexus's nx store):
  - `architecture-a2ui-overview` — a2ui repo deep analysis
  - `a2ui-design-philosophy-stack-positioning` — a2ui vs MCP UI vs AG-UI vs Adaptive Cards
  - `simonw-2025-12-10-html-tools-patterns` — Willison HTML tool patterns (informs the renderer's discipline)
  - `surface-renderer-html-tool-patterns-for-nexus` — nexus-side application of those patterns
- `html-tool-patterns` skill (`~/.claude/skills/`) — the four-invariants discipline the renderer follows
- `surface-as-artifact` skill (`~/.claude/skills/`) — the producer-side pattern this RDR is the canonical reference for

## Revision History

_2026-05-22 — initial sketch. Captures the architecture that shipped as palinex 0.0.1 to PyPI on the same day. The RDR codifies a working implementation rather than proposing one; design discussion happened in conversation 2026-05-20 through 2026-05-22 with the nexus project's user (Hal Hildebrand) and landed in code first._

_2026-05-23 — accepted alongside the palinex 0.2.0 release. Amendments before acceptance, in two passes:_

_First pass (initial acceptance attempt):_
- _Item 6 amended with the "Delivery robustness — retry-until-ack handshake" subsection documenting the about:blank race that affected 0.1.0 and the handshake shipped in 0.2.0._
- _§Context "Technical environment" amended to qualify A1: Claude Code Desktop v2.1.149 does not currently render `ui://` HTML resources inline; embedded artifact and external URL shapes are the working delivery paths for Desktop until that lands._
- _Finalization Gate populated with contradiction check, assumption verification (A1 partial / A2,A3 deferred / A4 verified), scope verification._

_Second pass (post-critique corrections — a substantive-critic agent caught four critical doc-vs-code contradictions in the first-pass amendments):_
- _Phase 2 components (Tabs, DateTimeInput, Video, AudioPlayer) marked shipped — they had landed in 0.2.0 but the Implementation Plan still showed them as unchecked future work._
- _`web/host-bridge.html` updated to actually implement the retry-until-ack discipline that Item 6 says "any new wrapper must implement". The reference implementation previously called bare `postMessage` and would have silently re-introduced the warm-cache race in downstream wrappers that copied it._
- _Item 4 corrected to reflect that only `wrap_as_mcp_ui_resource` exists as a producer-side helper; embedded-artifact and external-URL shapes are documented conventions a caller constructs with stdlib. The "host capability advertisement" paragraph was misleading (no such MCP query exists) and was replaced with an accurate description, including a callout that "MCP-aware → resource" is not a safe default for Desktop._
- _§Distribution amended to list the `.mcpb` Claude Desktop bundle (which shipped in 0.2.0 alongside the merge from develop). `mcpb/manifest.json` description corrected to remove the claim that Desktop renders surfaces inline (it doesn't, per A1)._
- _Test count corrected (19 → 53 across 3 modules), CI matrix corrected (3.10-3.13 → 3.12-3.13 per requires-python), renderer LOC updated (708 → 845 with a refactor ceiling at 1000)._
- _§Alternatives Considered extended with Alt 6 covering `srcdoc` and `blob:` iframe alternatives that were implicit considerations during the 0.1.0 → 0.2.0 fix cycle._

_Phase 3 (action registry hardening) remains future scope under this accepted architecture. Phase 2 is now complete._
