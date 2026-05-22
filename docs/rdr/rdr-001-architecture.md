---
title: "palinex Architecture: a2ui v0.9 IR, SurfaceBroker Port, Three Delivery Shapes, postMessage Host Bridge"
id: RDR-001
type: Architecture
status: draft
priority: high
author: Hal Hildebrand
reviewed-by: self
created: 2026-05-22
accepted_date:
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
- **Renderer host (primary)**: Claude Code via MCP UI resources. Sandboxed iframe with postMessage channel back to the host.
- **Renderer host (secondary)**: any browser. `file://` works; GitHub Pages hosts the canonical renderer at `https://hellblazer.github.io/palinex/`.
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

Size target: ~700 LOC (warn at 500 per `html-tool-patterns` discipline; current size 708). Bloat would indicate the design has lost coherence.

**Item 4: Three delivery shapes.**

| Shape | Host | Mechanism |
|---|---|---|
| **MCP UI resource** | Claude Code | Tool returns `{type: "resource", resource: {uri: "ui://...", mimeType: "text/html"}}` wrapping the renderer + payload |
| **Embedded artifact** | Any chat host | HTML returned inline with payload as `<script type="application/json">` and renderer pulled from `hellblazer.github.io/palinex/` via CDN-style URL |
| **External URL** | Any browser | `https://hellblazer.github.io/palinex/?payload=<base64>` for shareable links |

Default: caller picks based on host capability advertisement (MCP-aware → resource; chat host → embedded; CLI → URL). All three shapes carry the same a2ui v0.9 payload.

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
- PyPI: `palinex` (`pip install palinex`); optional `palinex[validate]` adds jsonschema
- Renderer hosted: `https://hellblazer.github.io/palinex/` (GitHub Pages)
- Release: tag-triggered (`v*`) GitHub Actions workflow with OIDC trusted publisher to PyPI + GitHub Release with sdist/wheel attached
- CI: pytest matrix on Python 3.10–3.13 plus build check on every PR/push
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
- **(−)** Renderer size (~700 LOC) is near the `html-tool-patterns` discipline ceiling; further feature growth needs careful design

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
- [x] `tests/` — 19 pytest tests covering envelope shape, action shapes, validation gates, markdown round-trip, template ChildList
- [x] `pyproject.toml` — hatchling build, optional `[validate]` extra, dev group
- [x] `.github/workflows/ci.yml` — pytest matrix on 3.10–3.13 + build check
- [x] `.github/workflows/release.yml` — tag-triggered OIDC trusted publisher + GitHub Release with artifacts
- [x] `CHANGELOG.md` — keep-a-changelog format
- [x] `README.md` — installation, quick start, URL params, component coverage
- [x] `LICENSE` — Apache-2.0
- [x] palinex 0.0.1 released to PyPI 2026-05-22

### Phase 2: Remaining Basic Catalog components

- [ ] Tabs (titles + children)
- [ ] DateTimeInput (ISO 8601 value, optional min/max, date/time toggles)
- [ ] Video (URL + minimal controls)
- [ ] AudioPlayer (URL + description)

Each follows the same dispatch pattern as the existing 14 — no architectural change. Ships as palinex 0.0.2 through the existing release workflow.

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

19 pytest tests cover the producer; CI matrix runs them on Python 3.10–3.13 for every PR and push. Renderer is browser-tested manually for v1; future Playwright tests would drive the renderer with payloads from the producer test corpus and assert DOM output.

### Performance expectations

- Surface construction (typical citation surface): <5ms
- Markdown sidecar generation: <5ms (tree walk, no I/O)
- Renderer cold load with warm CDN: <500ms
- Host-bridge round-trip with mock backend: <10ms; with real MCP call: <250ms
- Renderer rerender on data model change: <20ms for surfaces under 100 components

## Finalization Gate

(deferred — sketch only)

### Contradiction check

(deferred)

### Assumption verification

- [ ] **A1** — Claude Code MCP UI resource rendering is stable across the embedded artifact and resource shapes.
  **Method:** smoke test in Claude Code with a representative payload.
- [ ] **A2** — palinex's structural validation catches the producer errors that matter on a representative corpus.
  **Method:** mutation-test the demo payload (drop required fields, dangle refs, invalid variants).
- [ ] **A3** — Markdown sidecar is genuinely lossless for the surfaces nexus producers emit.
  **Method:** round-trip 100 representative nx_answer outputs.
- [ ] **A4** — postMessage RPC timeout (10s) is appropriate for typical host backends.
  **Method:** measure round-trip latency for chash resolution through Claude Code MCP and through HTTP sidecar.

### Scope verification

(deferred — this RDR covers only palinex itself; downstream integrations are their own RDRs)

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
