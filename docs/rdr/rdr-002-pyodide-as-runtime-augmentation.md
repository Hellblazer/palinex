---
title: "Pyodide as Preferred Runtime Augmentation: Producer + Validator + Inspector In-Browser, No Daemon"
id: RDR-002
type: Architecture
status: draft
priority: medium
author: Hal Hildebrand
reviewed-by: self
created: 2026-05-22
accepted_date:
related_rdrs: [RDR-001]
related_external: [pyodide, micropip, jsonschema]
---

# RDR-002: Pyodide as Preferred Runtime Augmentation

> The browser is the deployment unit. The daemon is overhead.

## Problem Statement

palinex 0.0.x ships in two halves that don't meet:

- **Producer side** (`palinex` Python package) runs wherever Python runs — typically a server, an agent runtime, or a Python script. Building a surface requires a Python environment.
- **Renderer side** (`index.html`) runs in any browser, including `file://`. Pure JavaScript.

Many palinex use cases sit at the seam between them and currently fall through:

1. **Drop-a-JSON-and-validate.** A developer pastes a candidate surface payload into a page and wants to know whether it conforms to v0.9, with structural and (eventually) schema-deep errors highlighted. Today: they install palinex with `pip install palinex[validate]` and run it locally. Friction enough that they probably won't.
2. **Inspector cell for the renderer's debug panel.** Renderer's debug panel currently shows raw JSON. With a Python-in-browser runtime, it could run `palinex.Surface.validate()` against the loaded payload, surface field-by-field errors, walk the data model, and explain what each component renders to in markdown — all client-side.
3. **Builder-on-the-page.** A small HTML form that constructs a surface visually (pick components, set data paths, preview) — without a backend. Today: requires a Python backend or a JS port of the builder. Tomorrow: load `palinex` via micropip, build the payload in-page.
4. **Producer prototyping by non-Python hosts.** A web app, a Tauri shell, a Pyodide-powered notebook — anything that wants to emit palinex surfaces but doesn't ship a Python runtime.

The shared shape across these: **palinex shouldn't require a daemon or local install for non-trivial use.** The browser is already the unit of deployment for the renderer; making it the unit of deployment for the producer too dissolves a class of friction.

Pyodide (CPython compiled to WebAssembly, ~10 MB initial download, ~1.5s cold load on a warm CDN) plus micropip (PyPI installs at runtime, in-browser) close the gap.

### Enumerated gaps

1. **No in-browser producer.** Browsers can render surfaces but can't construct them via palinex APIs.
2. **No in-browser deep validation.** `jsonschema` runs in Python only; deep validation requires a Python install.
3. **No interactive inspector.** Debug panel is read-only JSON; no walking, no diagnosis, no markdown preview from a paste.
4. **No precedent in palinex repo for the Pyodide pattern.** First-of-its-kind decision needs to be captured.

## Context

### Background

palinex RDR-001 §Item 3 commits to a single-file lit-html renderer with no build step, CDN-pinned deps, small footprint. Pyodide fits the same discipline:

- Loaded from CDN (`https://cdn.jsdelivr.net/pyodide/...`), pinned version
- Activates inside an existing HTML page; no new build pipeline
- No install required for the user
- ~10 MB initial load is *not* small, but it's a one-shot for the lifetime of the tab — comparable to a moderate React bundle, less than a Chromium-Electron install

### Technical environment

- **Pyodide** stable since 2021; production-grade. Used by JupyterLite, PyScript, and many "Python in browser" demos.
- **micropip** ships PyPI packages at runtime — palinex is pure Python, no native deps, installs cleanly.
- **jsonschema** is pure Python (with `referencing` for v0.9-style cross-schema refs); micropip-installable.
- **Web Workers** isolate Pyodide from the main thread so heavy work doesn't block UI.
- **lit-html** (already used in renderer) coexists with Pyodide-driven code via standard DOM access.

### Constraints

- **No new build step.** Pyodide stays inside single-file HTML pages — additional pages may be added, but each is a single file with CDN-loaded deps.
- **Optional augmentation, never required.** The base renderer (`index.html`) does not depend on Pyodide. Hosts that don't want a 10 MB download stay light.
- **Pyodide-using pages live alongside `index.html`** — not bolted into it. Page-per-purpose is the discipline.
- **Pyodide initialization is lazy.** Pages that include Pyodide show their non-Pyodide UI immediately and reveal Python-driven affordances after `pyodide.loadPackage()` resolves.
- **Match palinex semver to a2ui evolution, not to Pyodide.** Pyodide version is a CDN URL pin, refreshed as needed.

## Decision

Adopt Pyodide as the **preferred** path for any palinex feature that would otherwise require a Python install or a long-running daemon. Producer + validator + inspector all run in-browser; the daemon is reserved for cases that genuinely need server-side state (none yet identified).

### Approach

**Item 1: First Pyodide-enabled page — `inspector.html`.**

A new single-file HTML page (sibling of `index.html` and `host-bridge.html`) that:
- Loads Pyodide from pinned CDN URL
- `micropip.install('palinex[validate]')` on cold load
- Accepts a surface payload via file picker, paste, URL, or postMessage
- Runs `palinex.Surface.validate(deep=True)` and renders:
  - Structural errors with the offending component id + path
  - Schema errors (when `referencing` cooperates) with JSON-pointer paths
  - Markdown sidecar (`Surface.to_markdown()`) preview
  - Component table: id, type, role (root / child of X / template / orphan)
  - Data-model tree walker showing which paths the surface references

LOC target: similar to renderer (~700-800), single file, CDN-loaded Pyodide + lit-html.

**Item 2: Embed inspector capability in `index.html` debug panel (opt-in).**

Add a "Validate (deep)" button to the existing `<details class="debug">` panel. When clicked, lazily loads Pyodide, runs structural + deep validation, and displays the result inline. Opt-in so users who never click never pay the 10 MB cost.

**Item 3: Document the Pyodide pattern as palinex convention.**

Add a `docs/pyodide-pattern.md` that codifies:
- When to use Pyodide (avoids daemon, avoids install, enables in-browser use of Python-only logic)
- When NOT to use Pyodide (small JS-shaped tasks where lit-html or native JS is simpler)
- Standard load pattern (lazy, behind opt-in UI affordance)
- micropip version pinning (palinex versions tracked in the loader script)
- Worker isolation pattern (when work is heavy enough to block UI)

**Item 4: Producer-on-the-page page — `builder.html` (deferred).**

A future single-file HTML page that runs Pyodide + palinex + a small lit-html form to build surfaces interactively without leaving the browser. Out of v0.2.x scope; lands when the inspector pattern has settled.

**Item 5: Schema validator improvements riding on Pyodide.**

The deep-validation limitation documented in `palinex.Surface.validate` (jsonschema's `RefResolver` flaky on a2ui's catalog `$ref` chain) is more tractable in Pyodide because we can use the newer `referencing` library directly with custom URI resolvers per a2ui-catalog scheme. Tighter feedback loop in-browser makes iterating on this easier than fighting CI matrix.

**Item 6: No new server-side runtime.**

palinex does not introduce a long-running daemon, web service, or background process. If a use case appears to need one, first ask: can Pyodide do this in-browser? Default answer per this RDR: yes, until proven otherwise.

## Alternatives Considered

### Alt 1: Reimplement palinex in pure JavaScript

A `@palinex/builder` npm package mirroring the Python API. Rejected because:
- Doubles maintenance: every Python change requires a JS port
- Drifts in subtle ways (type coercion, validation behavior)
- The Python builders are already pure data construction; Pyodide runs them unchanged

### Alt 2: Server-side validator with REST/SSE

Stand up a `palinex-validator` daemon that accepts payloads and returns validation results. Rejected because:
- Requires hosting, CORS configuration, uptime
- One more moving part for every palinex consumer
- Defeats the "no daemon" discipline that scoped palinex 0.0.x in the first place

### Alt 3: WASM-compiled Python via Brython / Skulpt / Transcrypt

Smaller footprints than Pyodide but vastly less compatible (Skulpt doesn't run jsonschema; Brython is interpreter-shaped, not full CPython). Rejected because palinex depends on real CPython behavior in jsonschema and the referencing library.

### Alt 4: GitHub Actions + comment bot for validation

Push a candidate surface to a PR, get a comment back with validation result. Rejected as a misfit for the use cases — works for repo-stored surfaces but not for ad-hoc inspection or interactive building.

### Briefly rejected

- **Service Workers caching Pyodide for instant subsequent loads** — fine optimization but premature; revisit once any of the new pages has real users.
- **Pyodide in a Web Worker for parallelism** — adds complexity; main thread is fine for the validation-shaped workloads.

## Trade-offs

### Consequences

- **(+)** No daemon, no install, no backend — the browser is the deployment unit
- **(+)** palinex's Python builders run identically client-side and server-side (no JS-shaped drift)
- **(+)** jsonschema + referencing libraries cooperate better in Pyodide than in CI Python (tighter iteration on the v0.9 catalog ref problem)
- **(+)** Pattern generalizes: any Python-only logic palinex grows can be exposed in-browser
- **(+)** Aligns with the broader observation that WebAssembly Python should be leveraged across our use cases (captured for future RDRs in adjacent projects)
- **(−)** 10 MB initial load per Pyodide-using page — substantial but bounded
- **(−)** Cold-start latency (~1-2s on warm CDN, ~5s on cold) — opt-in lazy load minimizes
- **(−)** New dependency on Pyodide's stability — mitigated by version-pinning and Pyodide's mature track record
- **(−)** Two ways to do the same thing (browser via Pyodide, server via direct Python) — discipline says producer is producer; the runtime is incidental

### Risks and Mitigations

- **Risk:** Pyodide version compatibility drifts under us (a stdlib quirk, a numpy ABI change, etc.).
  **Mitigation:** pin Pyodide CDN URL exactly; bump deliberately with a PR.

- **Risk:** Users on slow connections experience the 10 MB load as broken.
  **Mitigation:** loading indicator with "this loads Python in your browser — one-time download" copy; cache via browser HTTP cache; revisit Service Worker caching if it becomes a real problem.

- **Risk:** `referencing` library still has the same catalog `$ref` issue in Pyodide that we see in Python CI.
  **Mitigation:** the issue is upstream to a2ui's referencing patterns; same workaround applies (structural validation as the reliable gate, deep as opt-in).

- **Risk:** palinex package size grows and micropip install becomes slow.
  **Mitigation:** palinex is pure Python, currently ~700 LOC builder + tests; sdist is tiny. Will stay small.

### Failure modes

- *Visible:* Pyodide fails to load (CDN outage) → page shows "Python runtime unavailable" + offers the markdown sidecar as fallback
- *Visible:* `micropip.install('palinex[validate]')` fails → page shows the pip error and offers structural-only validation via a tiny pure-JS validator (separate work, out of v0.2.x)
- *Visible:* Validation throws an unexpected exception → traceback shown in the inspector panel (Pyodide's `pyodide.runPython` exposes Python exceptions cleanly)
- *Silent:* user mistakes 5s cold-load for a hang — UX mitigated by progress indicator

## Implementation Plan

### Prerequisites

- [x] palinex 0.0.2 on PyPI with full Basic Catalog coverage
- [x] palinex package is pure Python (no native extensions)
- [ ] RDR-002 accepted

### Phase 1: Inspector page (Item 1)

`docs/inspector.html` — single-file HTML page:
- Loads Pyodide from pinned CDN URL
- `micropip.install('palinex[validate]')` on cold load (~5s first time)
- Accepts payload via file picker, paste textarea, URL param, postMessage
- Runs validation and renders inline:
  - Errors per component with id + path
  - Markdown sidecar via `Surface.to_markdown()`
  - Component table with role inference
  - Data-model JSON-pointer reference list
- Opt-in deep validation toggle

Lands as palinex 0.0.3 or 0.1.0 depending on whether other changes ship alongside.

### Phase 2: Embed in renderer debug panel (Item 2)

Modify `index.html` debug panel to include a "Validate (deep)" button that lazy-loads Pyodide and runs the same logic as `inspector.html`. Single-file constraint preserved by inlining the loader; opt-in gating preserves base renderer's small footprint for users who never click.

### Phase 3: Document the pattern (Item 3)

`docs/pyodide-pattern.md` — codifies when and how to use Pyodide in palinex pages. Becomes the reference for any future Python-in-browser feature.

### Phase 4: Builder page (Item 4, deferred)

`builder.html` — a future single-file page that constructs surfaces interactively. Lands when the inspector pattern has run for a while and the use case sharpens.

### Day 2 Operations

- Pyodide version pinned in each page's `<script>` tag; bumped deliberately
- palinex semver tracks a2ui versions (per RDR-001); Pyodide-augmented features ship in the same palinex release
- micropip install command in each page references a specific palinex version range
- New use cases default to "can this be Pyodide?" before reaching for a daemon

### New dependencies

- **Pyodide** (Apache-2.0, CDN-loaded, pinned URL)
- **micropip** (Apache-2.0, ships with Pyodide)
- No new PyPI deps for palinex itself

## Test Plan

- **Scenario:** Open `inspector.html` from `file://`, paste a valid v0.9 envelope.
  **Verify:** Pyodide loads (with progress indicator); palinex installs via micropip; validation runs; markdown sidecar appears; component table populated.

- **Scenario:** Paste a structurally-broken payload (dangling child ref).
  **Verify:** Validation error names the offending component and the missing id.

- **Scenario:** Paste a payload with deep schema violations.
  **Verify:** Deep validation surfaces the JSON-pointer path of the violation (when referencing cooperates) or falls back to structural with a note.

- **Scenario:** Click "Validate (deep)" in renderer's debug panel.
  **Verify:** Pyodide lazy-loads (loading indicator visible); validation runs; result panel appears inline; no impact on the rest of the renderer.

- **Scenario:** Cold load on a slow network.
  **Verify:** Loading indicator visible throughout; eventual success or clear error message; never a silent hang.

## Validation

### Testing strategy

Pyodide pages are tested manually for v1; Playwright-driven automated tests would assert that:
- Pyodide loads within a configurable timeout
- micropip install succeeds for the pinned palinex version
- A representative payload produces the expected validation output

### Performance expectations

- Pyodide cold load: 1-2s warm CDN, 5s cold; mitigated by loading indicator
- micropip install palinex: <1s (pure Python, tiny sdist)
- Validation runtime per payload: <100ms for typical surfaces
- Subsequent page loads (with HTTP cache warm): <500ms total

## Finalization Gate

(deferred — sketch only)

### Assumption verification

- [ ] **A1** — Pyodide loads reliably on the browsers palinex targets (Chrome/Edge/Firefox/Safari recent).
  **Method:** smoke test inspector.html in each.
- [ ] **A2** — `micropip.install('palinex[validate]')` succeeds and exposes the same API as native Python.
  **Method:** test corpus from `tests/test_builders.py` runs in Pyodide via REPL.
- [ ] **A3** — Deep validation via `referencing` library in Pyodide handles a2ui v0.9 catalog refs better than `RefResolver` in CI Python.
  **Method:** validate a 10-payload corpus deep and compare error rates.

### Cross-cutting concerns

- **Versioning:** Pyodide CDN URL pinned per page; palinex micropip install pinned to a version range; bumps via deliberate PRs.
- **Build tool compatibility:** none — single HTML files, CDN-loaded everything.
- **Licensing:** Pyodide (Apache-2.0) compatible with palinex (Apache-2.0).
- **Deployment model:** static hosting alongside `index.html` and `host-bridge.html`.
- **IDE compatibility:** unchanged — pages are standalone HTML.
- **Incremental adoption:** new pages are independent; base renderer stays light.
- **Secret/credential lifecycle:** unchanged — no new credentials introduced.
- **Memory management:** Pyodide runtime persists for tab lifetime; not a concern for short-lived diagnostic use.

### Proportionality

Small RDR that captures a load-bearing pattern. The pattern itself is one decision (use Pyodide for Python-in-browser); the implementation work spans multiple pages but each is a single file. Resist the urge to grow this into a "palinex daemon" or "palinex server" sub-project — that's the failure mode this RDR forecloses.

## References

- Pyodide — <https://pyodide.org/>
- micropip — <https://github.com/pyodide/micropip>
- palinex repo — <https://github.com/Hellblazer/palinex>
- palinex RDR-001 — Architecture (single-file HTML discipline, no build step, no daemon)
- a2ui v0.9 spec — <https://a2ui.org/specification/v0.9-a2ui/>
- T3 knowledge entries:
  - `simonw-2025-12-10-html-tools-patterns` — names Pyodide as an "escape hatch" for browser tools needing Python
  - `surface-renderer-html-tool-patterns-for-nexus` — design note that already flagged Pyodide as a candidate runtime augmentation

## Revision History

_2026-05-22 — initial sketch. Captures the directive that emerged in conversation 2026-05-22 to leverage WebAssembly Python "to the hilt" across our use cases. Codifies the discipline before implementation: Pyodide is the default for Python-in-browser needs; daemons stay rejected unless proven necessary._
